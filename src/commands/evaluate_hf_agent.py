"""Offline by default; explicitly executed HF qualification/isolated collection."""

import argparse
import asyncio
import hashlib
import json
import logging
import socket
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import uvicorn
from opensearchpy import OpenSearch
from src.commands.agent_collection import build_jobs
from src.commands.evaluate_agent import (
    MANIFEST_SHA256,
    MODEL_DIGESTS,
    CountedEmbedder,
    CountedSearch,
    Measurements,
    collect_attempt,
    free_memory_mib,
    load_labels,
    write_json,
)
from src.commands.evaluate_retrieval import digest, snapshot
from src.commands.hf_allowance import PRIOR_RUN, PilotAllowance, validate_pilot_scope
from src.commands.hf_evaluation import (
    HF_MANIFEST_SHA256,
    MeasuredHF,
    create_hosted_app,
    hosted_admission,
    hosted_work,
    load_protocol,
    qualify,
)
from src.commands.hf_qualification import load_revision
from src.config import Settings
from src.middlewares import RateLimiter
from src.services.ollama.client import normalize_model_name


def source_hashes() -> dict:
    return {p.as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(Path("src").rglob("*"))
            if p.is_file() and "__pycache__" not in p.parts}


def plan_collection(source: Path, *, split: str, model: str, case_ids=None, modes=None, transports=None, qualification_v2=False) -> dict:
    profile = load_protocol()
    if model not in profile["model_pairs"] or split not in {"development", "holdout"}:
        raise ValueError("Unregistered hosted model or split")
    if split == "holdout" and (case_ids or modes or transports):
        raise ValueError("Hosted holdout cannot be subset or reordered")
    modes, transports = modes or ["bm25", "hybrid"], transports or ["json", "sse"]
    if (len(set(modes)) != len(modes) or not set(modes) <= {"bm25", "hybrid"}
            or len(set(transports)) != len(transports) or not set(transports) <= {"json", "sse"}):
        raise ValueError("Invalid hosted comparison cells")
    _, labels, _, _ = load_labels(Path("evaluation/week7_agent"), source)
    cases = labels[split]["cases"]
    if case_ids:
        if len(set(case_ids)) != len(case_ids) or not set(case_ids) <= {case["id"] for case in cases}:
            raise ValueError("Unknown or duplicate development case")
        cases = [case for case in cases if case["id"] in case_ids]
    jobs = build_jobs(cases, modes=tuple(modes), transports=tuple(transports))
    budget = profile["qualification_calls"] + sum(6 if job["path"] == "agent" else 2 for job in jobs)
    metadata = {"status": "offline_plan", "inference_started": False, "created_unix": time.time(),
            "manifest_sha256": MANIFEST_SHA256, "hosted_manifest_sha256": HF_MANIFEST_SHA256,
            "split": split, "configuration": {"model": model, "policy": profile["version"]},
            "jobs": [{k: v for k, v in job.items() if k != "query"} for job in jobs],
            "outbound_budget": budget, "source_sha256": source_hashes()}
    if qualification_v2:
        validate_pilot_scope(metadata)
        metadata.update(fixture_manifest_sha256=load_revision()["manifest_sha256"], planned_outbound_budget=budget, outbound_budget=11)
    return metadata


def validate_selection(selection: dict, model: str, source: Path | None = None) -> None:
    if (selection.get("hosted_manifest_sha256") != HF_MANIFEST_SHA256 or selection.get("model") != model
            or selection.get("development_accepted") is not True or selection.get("development_jobs") != 64):
        raise ValueError("Holdout requires a reviewed development selection lock")
    run = Path(selection["development_run"]).resolve()
    report_path = run / "selection-report.json"
    roots = [(Path.cwd() / name).resolve() for name in ("test_output", "tests/test_output")]
    if not any(run.is_relative_to(root) and run != root for root in roots) or not report_path.is_file():
        raise ValueError("Selection evidence is unavailable")
    if hashlib.sha256(report_path.read_bytes()).hexdigest() != selection.get("report_sha256"):
        raise ValueError("Development selection evidence changed")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if (report.get("development_accepted") is not True or report.get("model") != model
            or report.get("hosted_manifest_sha256") != HF_MANIFEST_SHA256):
        raise ValueError("Development selection report differs")
    for name, expected in selection.get("evidence_sha256", {}).items():
        if name not in {"metadata.json", "completion.json", "qualification.json", "records.jsonl", "reviews.json"}:
            raise ValueError("Invalid selection evidence path")
        if hashlib.sha256((run / name).read_bytes()).hexdigest() != expected:
            raise ValueError("Selection run changed")
    if set(selection.get("evidence_sha256", {})) != {"metadata.json", "completion.json", "qualification.json", "records.jsonl", "reviews.json"}:
        raise ValueError("Selection omits required development evidence")
    if source is None:
        raise ValueError("Selection validation requires the preserved source snapshot")
    from src.commands.score_hf_agent import score_run

    recalculated = score_run(run, source, json.loads((run / "reviews.json").read_text(encoding="utf-8")))
    if recalculated != report or recalculated.get("development_accepted") is not True:
        raise ValueError("Development selection no longer validates")


async def collect_hosted_attempt(client, job, measurements, papers, chunks, hf: MeasuredHF, profile: dict, *, memory=free_memory_mib) -> dict:
    result = await collect_attempt(client, job, measurements, papers, chunks,
                                   expected_model=hf.settings.hf_default_model, memory=memory)
    calls = hf.ledger.pop(result.get("request_id") or "", [])
    result["hf_calls"] = calls
    result["hosted"] = hosted_work(calls, profile, hf.settings.hf_default_model)
    if len(calls) != result["measured"].get("generation_calls", 0) or result["hosted"]["schema_violations"]:
        result["integrity_breach"] = True
    return result


async def wait_window(start: float, seconds: int) -> None:
    while time.monotonic() - start < seconds:
        await asyncio.sleep(min(1, seconds - (time.monotonic() - start)))


async def run_collection(settings: Settings, jobs: list, papers: list, chunks: list, output: Path, profile: dict, budget: int, *, revision=None) -> dict:
    hf = MeasuredHF(settings, outbound_budget=budget)
    qualification = None
    search_client = listener = server = server_task = None
    handler = Measurements()
    logger = logging.getLogger("src.operations")
    previous_level, previous_propagate = logger.level, logger.propagate
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.addHandler(handler)
    records = []
    stop = None
    try:
        started = time.monotonic()
        extra = {"revision": revision} if revision else {}
        qualification = await qualify(hf, profile, limiter=RateLimiter(settings), **extra)
        write_json(output / "qualification.json", qualification)
        if not qualification["qualified"]:
            return {"status": "qualification_failed", "attempts": 0, "planned": len(jobs), "outbound_attempts": hf.attempts}
        await wait_window(started, profile["window_seconds"])
        search_client = OpenSearch(hosts=[settings.opensearch_host], retry_on_timeout=False, max_retries=0, timeout=30)
        search = CountedSearch(search_client, CountedEmbedder(settings.ollama_host, settings.ollama_embedding_model))
        local = create_hosted_app(settings, search, hf)
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(local, host="127.0.0.1", port=port, workers=1, access_log=False,
            log_level="error", lifespan="off", ws="none", timeout_graceful_shutdown=1))
        server_task = asyncio.create_task(server.serve(sockets=[listener]))
        async with asyncio.timeout(5):
            while not server.started:
                if server_task.done():
                    await server_task
                    raise RuntimeError("Hosted evaluation server failed to start")
                await asyncio.sleep(0.02)
        headers = {"X-API-Key": settings.api_key.get_secret_value()} if settings.api_key else {}
        async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}", timeout=150, headers=headers, trust_env=False) as client:
            window_start = time.monotonic()
            for index, job in enumerate(jobs):
                if index and index % profile["generations_per_minute"] == 0:
                    await wait_window(window_start, profile["window_seconds"])
                    window_start = time.monotonic()
                if free_memory_mib() < profile["live_margin_mib"]:
                    stop = "pre_request_resource_floor"
                    break
                record = await collect_hosted_attempt(client, job, handler, papers, chunks, hf, profile)
                records.append(record)
                with (output / "records.jsonl").open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps(record, ensure_ascii=False) + "\n")
                print(json.dumps({"completed": len(records), "planned": len(jobs), "path": job["path"],
                    "case_id": job["case_id"], "ok": record["ok"], "outbound_attempts": record["hosted"]["outbound_attempts"],
                    "unknown_usage_attempts": record["hosted"]["unknown_usage_attempts"], "error_type": record.get("error_type")}), flush=True)
                if record["integrity_breach"] or not record["resource_passed"] or not record["hosted"]["usage_complete"]:
                    stop = "integrity_resource_or_usage_failure"
                    break
                if record.get("error_type") in {"TimeoutError", "ReadTimeout"}:
                    stop = "inflight_work_uncertain"
                    break
                for _ in range(record.get("retry_after_seconds", 0)):
                    await asyncio.sleep(1)
        return {"status": "stopped" if stop else "collected", "stop_reason": stop, "attempts": len(records),
                "planned": len(jobs), "outbound_attempts": hf.attempts, "semantic_review": "pending"}
    except Exception as exc:
        return {"status": "stopped", "error_class": type(exc).__name__, "attempts": len(records),
                "planned": len(jobs), "outbound_attempts": hf.attempts}
    finally:
        if server is not None:
            server.should_exit = True
        if server_task is not None:
            try:
                await asyncio.wait_for(server_task, timeout=5)
            except (TimeoutError, asyncio.CancelledError):
                server_task.cancel()
                try:
                    await server_task
                except asyncio.CancelledError:
                    pass
        await hf.aclose()
        if search_client is not None:
            search_client.close()
        if listener is not None:
            listener.close()
        logger.removeHandler(handler)
        logger.setLevel(previous_level)
        logger.propagate = previous_propagate


def live_snapshot(settings: Settings):
    for origin, port in ((settings.opensearch_host, 9200), (settings.ollama_host, 11434)):
        value = urlsplit(origin)
        if (value.scheme != "http" or value.hostname not in {"localhost", "127.0.0.1", "::1"} or value.port != port
                or value.username or value.password or value.query or value.fragment or value.path not in {"", "/"}):
            raise ValueError("Hosted local resources require the preserved loopback origins")
    headers = {"X-API-Key": settings.api_key.get_secret_value()} if settings.api_key else {}
    with httpx.Client(timeout=30, headers=headers, trust_env=False, follow_redirects=False) as client:
        state, papers, chunks = snapshot(client, "http://127.0.0.1:8000/api/v1", settings.opensearch_host)
        response = client.get(settings.ollama_host.rstrip("/") + "/api/tags")
        response.raise_for_status()
        installed = {normalize_model_name(item.get("model") or item["name"]): item["digest"] for item in response.json()["models"]}
        if any(installed.get(name) != expected for name, expected in MODEL_DIGESTS.items()):
            raise ValueError("Preserved local model digests differ")
    return state, papers, chunks


def provider_available(model: str) -> dict:
    # Deliberately separate from authenticated loopback client: no API key/token.
    with httpx.Client(timeout=10, trust_env=False, follow_redirects=False) as client:
        response = client.get("https://router.huggingface.co/v1/models")
        response.raise_for_status()
        data = response.json()["data"]
    model_id, provider = model.rsplit(":", 1)
    row = next((p for item in data if item["id"] == model_id for p in item["providers"] if p["provider"] == provider), None)
    if not row or row.get("status") != "live" or not row.get("supports_structured_output"):
        raise ValueError("Hosted candidate is not advertised live/structured")
    return {key: row[key] for key in ("provider", "status", "supports_structured_output", "supports_tools", "pricing") if key in row}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--split", choices=("development", "holdout"), default="development")
    parser.add_argument("--model", default="openai/gpt-oss-120b:groq")
    parser.add_argument("--case-id", action="append")
    parser.add_argument("--mode", choices=("bm25", "hybrid"), action="append")
    parser.add_argument("--transport", choices=("json", "sse"), action="append")
    parser.add_argument("--selection", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--qualification-v2", action="store_true", help="Frozen production-format pilot qualification with cumulative allowance")
    args = parser.parse_args()
    output = args.output.resolve()
    roots = [(Path.cwd() / name).resolve() for name in ("test_output", "tests/test_output")]
    if output.exists() or not any(output.is_relative_to(root) and output != root for root in roots):
        parser.error("Output must be a fresh ignored directory")
    metadata = plan_collection(args.snapshot, split=args.split, model=args.model, case_ids=args.case_id,
                               modes=args.mode, transports=args.transport, qualification_v2=args.qualification_v2)
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "metadata.json", metadata)
    if not args.execute:
        print(json.dumps({"status": "offline_plan", "jobs": len(metadata["jobs"]), "outbound_budget": metadata["outbound_budget"]}))
        return
    profile = load_protocol()
    revision = load_revision() if args.qualification_v2 else None
    grant = None
    if revision is None and PRIOR_RUN.exists():
        try:
            validate_pilot_scope(metadata)
        except ValueError:
            pass
        else:
            metadata.update(status="not_started", reason="failed_pilot_requires_versioned_qualification")
            write_json(output / "metadata.json", metadata)
            print(json.dumps({"status": "not_started", "reason": metadata["reason"]}))
            return
    settings = Settings()
    jobs = metadata["jobs"]
    reason = hosted_admission(settings, jobs, free_memory_mib(), profile)
    if reason:
        metadata.update(status="not_started", reason=reason, free_memory_mib=free_memory_mib())
        write_json(output / "metadata.json", metadata)
        print(json.dumps({"status": "not_started", "reason": reason}))
        return
    if args.split == "holdout":
        if args.selection is None:
            parser.error("Holdout execution needs a locked development selection")
        selection = json.loads(args.selection.read_text(encoding="utf-8"))
        validate_selection(selection, args.model, args.snapshot)
        metadata["selection_sha256"] = digest(selection)
    _, labels, _, _ = load_labels(Path("evaluation/week7_agent"), args.snapshot)
    by_case = {case["id"]: case for case in labels[args.split]["cases"]}
    jobs = [{**job, "query": by_case[job["case_id"]]["query"]} for job in jobs]
    try:
        before, papers, chunks = live_snapshot(settings)
        expected = json.loads((args.snapshot / "state.json").read_text(encoding="utf-8"))
        if before != expected:
            raise ValueError("Live source snapshot differs")
        metadata["provider_catalog"] = provider_available(args.model)
        local = Settings.model_validate(settings.model_copy(update={"hf_inference_enabled": True,
            "hf_models": [args.model], "hf_default_model": args.model, "agent_enabled": True,
            "answer_cache_enabled": False, "local_tracing_enabled": False, "monitoring_directory": None,
            "api_rate_limit_path": str(output / "quotas.sqlite3")}).model_dump())
        if revision:
            grant = PilotAllowance()
            budget = grant.reserve(str(output), metadata["planned_outbound_budget"])
            if budget < profile["qualification_calls"]:
                grant.settle(str(output), 0)
                raise ValueError("Remaining allowance cannot complete qualification")
            metadata.update(outbound_budget=budget, allowance={"path": str(grant.path.resolve()),
                "prior_evidence_sha256": grant.signature, "total_ceiling": 13, "prior_attempts": 2, "reserved_for_run": budget})
    except Exception as exc:
        metadata.update(status="not_started", reason="preflight_failed", error_class=type(exc).__name__)
        write_json(output / "metadata.json", metadata)
        print(json.dumps({"status": "not_started", "reason": "preflight_failed", "error_class": type(exc).__name__}))
        return
    metadata.update(status="collecting", execution_started=True, inference_started=None, free_memory_mib=free_memory_mib())
    write_json(output / "metadata.json", metadata)
    (output / "records.jsonl").touch(exist_ok=False)
    try:
        extra = {"revision": revision} if revision else {}
        completion = asyncio.run(run_collection(local, jobs, papers, chunks, output, profile, metadata["outbound_budget"], **extra))
    except Exception as exc:
        completion = {"status": "stopped", "error_class": type(exc).__name__, "outbound_attempts": None}
    if grant is not None:
        grant.settle(str(output), completion.get("outbound_attempts"))
    metadata["inference_started"] = (completion["outbound_attempts"] > 0 if completion.get("outbound_attempts") is not None else None)
    write_json(output / "metadata.json", metadata)
    preserved = {"source_unchanged": source_hashes() == metadata["source_sha256"],
                 "frozen_labels_unchanged": False, "corpus_unchanged": False, "models_unchanged": False}
    try:
        load_protocol()
        load_labels(Path("evaluation/week7_agent"), args.snapshot)
        preserved["frozen_labels_unchanged"] = True
        after, _, _ = live_snapshot(settings)
        preserved["corpus_unchanged"] = after == before
        preserved["models_unchanged"] = True
    except Exception as exc:
        completion["preservation_error_class"] = type(exc).__name__
    completion["preservation"] = preserved
    write_json(output / "completion.json", completion)
    metadata["status"] = completion["status"]
    write_json(output / "metadata.json", metadata)
    print(json.dumps(completion), flush=True)


if __name__ == "__main__":
    main()
