"""Guarded local comparison collector. Default is an offline plan, never inference.

Creates a test-owned loopback app only after live source/model/memory admission.
Both paths are uncached. Existing API, databases, containers and quotas are untouched.
"""

import argparse
import asyncio
import ctypes
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
from src.commands.agent_collection import admission, audit_response, build_jobs, create_evaluation_app, parse_agent_sse
from src.commands.evaluate_retrieval import digest, snapshot
from src.commands.validate_agent_evaluation import validate_freeze, validate_suite
from src.config import Settings
from src.operations import request_context
from src.schemas.api.rag import AskRequest
from src.services.embeddings.ollama import OllamaEmbedder
from src.services.ollama.client import OllamaClient, normalize_model_name
from src.services.search import SearchService
from src.tracing import safe_fields

MANIFEST_SHA256 = "58b099eead49d8fd22d96be7a7ceba3142de9524ce6f80846e2e8ddee884b0db"
MODEL_DIGESTS = {
    "llama3.2:1b": "baf6a787fdffd633537aa2eb51cfd54cb93ff08e28040095462bb63daf552878",
    "nomic-embed-text:latest": "0a109f422b47e3a30ba2b10eca18548e944e8a23073ee3f3e947efcf3c45e59f",
}


def free_memory_mib() -> float:
    class Memory(ctypes.Structure):
        _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong),
                    *[(name, ctypes.c_ulonglong) for name in ("physical", "available", "page", "available_page", "virtual", "available_virtual", "extended")]]
    state = Memory()
    state.length = ctypes.sizeof(state)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(state)):
        raise OSError("host memory inspection failed")
    return state.available / 1048576


def _count(key: str) -> None:
    context = request_context.get()
    if context is not None:
        counts = context.setdefault("evaluation_counts", {"generation_calls": 0, "retrieval_calls": 0, "embedding_calls": 0})
        counts[key] += 1


class CountedOllama(OllamaClient):
    async def generate(self, model, prompt, **kwargs):
        _count("generation_calls")
        return await super().generate(model, prompt, **kwargs)


class CountedEmbedder(OllamaEmbedder):
    def embed_query(self, text):
        _count("embedding_calls")
        return super().embed_query(text)


class CountedSearch(SearchService):
    def search_chunks(self, query, **kwargs):
        _count("retrieval_calls")
        return super().search_chunks(query, **kwargs)

    def search_hybrid(self, query, **kwargs):
        _count("retrieval_calls")
        return super().search_hybrid(query, **kwargs)


class Measurements(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.requests: dict[str, dict] = {}

    def emit(self, record):
        context = request_context.get()
        if not context or not context.get("request_id"):
            return
        event = json.loads(record.getMessage())
        state = self.requests.setdefault(context["request_id"], {"events": [], "completed_generations": 0,
                                                               "prompt_tokens": 0, "output_tokens": 0})
        if len(state["events"]) < 64:
            state["events"].append({"event": event["event"], **safe_fields(event)})
        if event["event"] == "rag_generation":
            state["completed_generations"] += 1
            state["prompt_tokens"] += event.get("prompt_tokens") or 0
            state["output_tokens"] += event.get("output_tokens") or 0
        state.update(context.get("evaluation_counts") or {"generation_calls": 0, "retrieval_calls": 0, "embedding_calls": 0})


async def memory_watch(task, finished: asyncio.Event, samples: list, memory=free_memory_mib) -> None:
    while not finished.is_set():
        try:
            value = memory()
        except Exception:
            samples.append({"error_type": "MemoryInspectionFailure"})
            task.cancel()
            return
        if len(samples) < 2000:
            samples.append({"monotonic": time.monotonic(), "free_mib": round(value, 2)})
        if value < 384:
            task.cancel()
            return
        try:
            await asyncio.wait_for(finished.wait(), timeout=0.1)
        except TimeoutError:
            pass


async def collect_attempt(client: httpx.AsyncClient, job: dict, measurements: Measurements, papers: list, chunks: list, *,
                          memory=free_memory_mib, expected_model="llama3.2:1b") -> dict:
    started = time.perf_counter()
    result = {key: value for key, value in job.items() if key != "query"}
    result.update(ok=False, integrity_breach=False, query_sha256=hashlib.sha256(job["query"].encode()).hexdigest())
    request = AskRequest(query=job["query"], use_hybrid=job["mode"] == "hybrid", top_k=3)
    path = ("/api/v1/agent" if job["path"] == "agent" else "/api/v1") + ("/ask" if job["transport"] == "json" else "/stream")
    samples: list = []
    finished = asyncio.Event()

    async def call():
        async with client.stream("POST", path, json=request.model_dump()) as response:
            result["http_status"] = response.status_code
            result["request_id"] = response.headers.get("x-request-id")
            result["retry_after_seconds"] = int(response.headers.get("retry-after", "0"))
            if not 0 <= result["retry_after_seconds"] <= 60:
                raise ValueError("unbounded quota wait")
            parts = []
            async for part in response.aiter_text():
                if sum(map(len, parts)) + len(part) > 1_000_000:
                    raise ValueError("collection response exceeds size limit")
                parts.append(part)
                if "first_body_ms" not in result:
                    result["first_body_ms"] = round((time.perf_counter() - started) * 1000, 2)
                if job["transport"] == "sse":
                    accumulated = "".join(parts)
                    for event in ("status", "delta"):
                        if f"first_{event}_ms" not in result and f"event: {event}\n" in accumulated:
                            result[f"first_{event}_ms"] = round((time.perf_counter() - started) * 1000, 2)
            if response.status_code != 200:
                result["error_type"] = f"HTTP{response.status_code}"
                return None
            raw = "".join(parts)
            return parse_agent_sse(raw, agent=job["path"] == "agent") if job["transport"] == "sse" else json.loads(raw)

    task = asyncio.create_task(call())
    watcher = asyncio.create_task(memory_watch(task, finished, samples, memory))
    try:
        async with asyncio.timeout(150):
            response = await task
        if response is not None:
            measured = measurements.requests.get(result["request_id"], {})
            if not measured:
                raise ValueError("request measurement missing")
            checked = audit_response(response, request, papers, chunks, agent=job["path"] == "agent",
                                     measured=measured, expected_model=expected_model)
            result.update(ok=True, **checked, measured=measured, response_sha256=digest(checked["response"]))
    except asyncio.CancelledError:
        if any("error_type" in sample for sample in samples):
            result["error_type"] = "MemoryMonitorUnavailable"
        elif not samples or min(s["free_mib"] for s in samples) >= 384:
            raise
        else:
            result["error_type"] = "EmergencyMemoryStop"
    except Exception as exc:
        result["error_type"] = type(exc).__name__
        # HTTP/SSE generation errors are transport failures, not attribution
        # success. Invalid ordering/source/budgets stop the run for investigation.
        result["integrity_breach"] = isinstance(exc, ValueError) and str(exc) != "SSE failed or missing terminal output"
    finally:
        finished.set()
        await watcher
    result["duration_ms"] = round((time.perf_counter() - started) * 1000, 2)
    values = [s["free_mib"] for s in samples if "free_mib" in s]
    result["memory"] = {"samples": samples, "minimum_free_mib": min(values) if values else None}
    result["resource_passed"] = bool(values) and min(values) >= 600 and not any("error_type" in s for s in samples)
    result.setdefault("measured", measurements.requests.get(result.get("request_id") or "", {}))
    return result


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_labels(dataset: Path, source: Path) -> tuple[dict, dict, list, list]:
    read = lambda path: json.loads(path.read_text(encoding="utf-8"))
    if hashlib.sha256((dataset / "manifest.json").read_bytes()).hexdigest() != MANIFEST_SHA256:
        raise ValueError("unreviewed manifest version")
    manifest = read(dataset / "manifest.json")
    validate_freeze(manifest, dataset, Path.cwd())
    development, holdout = read(dataset / "development.json"), read(dataset / "holdout.json")
    papers, chunks = read(source / "papers.json"), read(source / "chunks.json")
    validate_suite(development, holdout, papers, chunks, prior_questions=manifest["prior_questions"],
                   prior_support_papers=manifest["prior_support_papers"])
    if read(source / "state.json") != manifest["corpus_snapshot"]:
        raise ValueError("snapshot alias/state differs")
    return manifest, {"development": development, "holdout": holdout}, papers, chunks


async def run_jobs(settings: Settings, jobs: list, papers: list, chunks: list, output: Path) -> dict:
    counted = CountedOllama(settings)
    search_client = OpenSearch(hosts=[settings.opensearch_host], retry_on_timeout=True, max_retries=3, timeout=30)
    search = CountedSearch(search_client, CountedEmbedder(settings.ollama_host, settings.ollama_embedding_model))
    local_settings = settings.model_copy(update={"agent_enabled": True, "answer_cache_enabled": False,
        "local_tracing_enabled": False, "monitoring_directory": None, "api_rate_limit_path": str(output / "quotas.sqlite3")})
    app = create_evaluation_app(local_settings, search, counted)
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, workers=1, access_log=False,
                                          log_level="error", lifespan="off", ws="none", timeout_graceful_shutdown=1))
    handler = Measurements()
    logger = logging.getLogger("src.operations")
    level, propagate = logger.level, logger.propagate
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.addHandler(handler)
    server_task = asyncio.create_task(server.serve(sockets=[listener]))
    records = []
    stopped = None
    try:
        async with asyncio.timeout(5):
            while not server.started:
                if server_task.done():
                    await server_task
                    raise RuntimeError("evaluation server did not start")
                await asyncio.sleep(0.02)
        headers = {"X-API-Key": settings.api_key.get_secret_value()} if settings.api_key else {}
        async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}", timeout=150, headers=headers, trust_env=False) as client:
            # Leave the frozen six-generation budget unchanged. Groups of six
            # requests are separated by a complete window, including failed calls.
            window_start = time.monotonic()
            for index, job in enumerate(jobs):
                if index and index % settings.api_generations_per_minute == 0:
                    remaining = max(0, 61 - (time.monotonic() - window_start))
                    while remaining > 0:
                        await asyncio.sleep(min(remaining, 1))
                        remaining = max(0, 61 - (time.monotonic() - window_start))
                    window_start = time.monotonic()
                if free_memory_mib() < 600:
                    stopped = "pre_request_resource_floor"
                    break
                record = await collect_attempt(client, job, handler, papers, chunks, expected_model=settings.ollama_default_model)
                records.append(record)
                with (output / "records.jsonl").open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps(record, ensure_ascii=False) + "\n")
                print(json.dumps({"completed": len(records), "planned": len(jobs), "case_id": job["case_id"],
                                  "path": job["path"], "ok": record["ok"], "error_type": record.get("error_type"),
                                  "minimum_free_mib": record["memory"]["minimum_free_mib"]}), flush=True)
                if record["integrity_breach"] or not record["resource_passed"]:
                    stopped = "integrity_breach" if record["integrity_breach"] else "resource_floor"
                    break
                if record.get("error_type") in {"TimeoutError", "ReadTimeout"}:
                    stopped = "client_timeout_inflight_work_uncertain"
                    break
                # A rejected attempt stays recorded and is never retried; honor
                # Retry-After before the next distinct scheduled attempt.
                for _ in range(record.get("retry_after_seconds", 0)):
                    await asyncio.sleep(1)
    finally:
        server.should_exit = True
        try:
            await asyncio.wait_for(server_task, timeout=5)
        except (TimeoutError, asyncio.CancelledError):
            server_task.cancel()
            try:
                await server_task
            except asyncio.CancelledError:
                pass
        await counted.aclose()
        search_client.close()
        listener.close()
        logger.removeHandler(handler)
        logger.setLevel(level)
        logger.propagate = propagate
    return {"status": "stopped" if stopped else "collected", "stop_reason": stopped, "attempts": len(records),
            "planned": len(jobs), "failures": sum(not r["ok"] for r in records), "semantic_review": "pending"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, default=Path("evaluation/week7_agent"))
    parser.add_argument("--split", choices=("development", "holdout"), default="development")
    parser.add_argument("--case-id", action="append", help="Development-only pilot subset")
    parser.add_argument("--mode", choices=("bm25", "hybrid"), action="append", help="Development-only pilot subset")
    parser.add_argument("--transport", choices=("json", "sse"), action="append", help="Development-only pilot subset")
    parser.add_argument("--output", type=Path, required=True, help="New directory under ignored tests/test_output or test_output")
    parser.add_argument("--execute", action="store_true", help="Attempt guarded live preflight and collection; default offline plan")
    args = parser.parse_args()
    if args.split == "holdout" and (args.case_id or args.mode or args.transport):
        parser.error("holdout matrix cannot be subset or reordered")
    if len(set(args.mode or [])) != len(args.mode or []) or len(set(args.transport or [])) != len(args.transport or []):
        parser.error("comparison modes/transports cannot be repeated")
    output = args.output.resolve()
    roots = [(Path.cwd() / name).resolve() for name in ("test_output", "tests/test_output")]
    if not any(output.is_relative_to(root) and output != root for root in roots) or output.exists():
        parser.error("output must be a fresh directory under local ignored test output")
    manifest, labels, papers, chunks = load_labels(args.dataset, args.snapshot)
    cases = labels[args.split]["cases"]
    if args.case_id:
        unknown = set(args.case_id) - {case["id"] for case in cases}
        if unknown:
            parser.error("unknown development case ID")
        cases = [case for case in cases if case["id"] in args.case_id]
    jobs = build_jobs(cases, modes=tuple(args.mode or ["bm25", "hybrid"]), transports=tuple(args.transport or ["json", "sse"]))
    output.mkdir(parents=True, exist_ok=False)
    metadata = {"manifest_sha256": MANIFEST_SHA256, "split": args.split, "jobs": [{k: v for k, v in job.items() if k != "query"} for job in jobs],
                "created_unix": time.time(), "source_sha256": {p.as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in Path("src").rglob("*") if p.is_file() and "__pycache__" not in p.parts}, "inference_started": False}
    if not args.execute:
        metadata["status"] = "offline_plan"
        write_json(output / "metadata.json", metadata)
        print(json.dumps({"status": "offline_plan", "jobs": len(jobs), "output": str(output)}))
        return
    settings = Settings()
    for origin in (settings.opensearch_host, settings.ollama_host):
        parsed = urlsplit(origin)
        if (parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
                or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {"", "/"}):
            raise ValueError("evaluation resources must use credential-free loopback origins")
    if not settings.api_key or settings.api_generations_per_minute != 6:
        raise ValueError("evaluation requires the original key and unchanged six-generation quota")
    headers = {"X-API-Key": settings.api_key.get_secret_value()} if settings.api_key else {}
    with httpx.Client(timeout=30, headers=headers, trust_env=False) as client:
        before, live_papers, live_chunks = snapshot(client, "http://127.0.0.1:8000/api/v1", settings.opensearch_host)
        tags = client.get(settings.ollama_host.rstrip("/") + "/api/tags")
        tags.raise_for_status()
        loaded = client.get(settings.ollama_host.rstrip("/") + "/api/ps")
        loaded.raise_for_status()
    if before != manifest["corpus_snapshot"]:
        raise ValueError("live corpus changed; refuse collection")
    installed = {entry["name"]: entry["digest"] for entry in tags.json()["models"]}
    memory = free_memory_mib()
    required_names = {normalize_model_name(settings.ollama_default_model), normalize_model_name(settings.ollama_embedding_model)}
    required = all(name in MODEL_DIGESTS and installed.get(name) == MODEL_DIGESTS[name] for name in required_names)
    reason = admission(memory, candidate_count=settings.rag_sentence_candidates_per_passage, required_installed=required)
    metadata.update(status="not_started" if reason else "admitted", admission_reason=reason, free_mib=memory, models=installed,
                    loaded_before=loaded.json(), corpus_before=before,
                    configuration={"model": settings.ollama_default_model, "embedding_model": settings.ollama_embedding_model,
                        "agent_deadline_seconds": settings.agent_deadline_seconds, "agent_node_timeout_seconds": settings.agent_node_timeout_seconds,
                        "generations_per_minute": settings.api_generations_per_minute, "candidate_count": settings.rag_sentence_candidates_per_passage})
    write_json(output / "metadata.json", metadata)
    if reason:
        print(json.dumps({"status": "not_started", "reason": reason, "free_mib": round(memory, 2), "required_mib": 3072,
                          "inference_requests": 0, "output": str(output)}))
        return
    metadata["inference_started"] = True
    write_json(output / "metadata.json", metadata)
    result = asyncio.run(run_jobs(settings, jobs, live_papers, live_chunks, output))
    validate_freeze(manifest, args.dataset, Path.cwd())
    with httpx.Client(timeout=30, headers=headers, trust_env=False) as client:
        after, _, _ = snapshot(client, "http://127.0.0.1:8000/api/v1", settings.opensearch_host)
        model_tags = client.get(settings.ollama_host.rstrip("/") + "/api/tags")
        model_tags.raise_for_status()
    models_after = {entry["name"]: entry["digest"] for entry in model_tags.json()["models"]}
    source_unchanged = all(Path(name).is_file() and hashlib.sha256(Path(name).read_bytes()).hexdigest() == sha
                           for name, sha in metadata["source_sha256"].items())
    result["preservation"] = {"corpus_unchanged": after == before, "models_unchanged": models_after == installed,
                              "source_unchanged": source_unchanged, "frozen_labels_unchanged": True}
    if not all(result["preservation"].values()):
        result.update(status="stopped", stop_reason="preservation_mismatch")
    write_json(output / "completion.json", result)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
