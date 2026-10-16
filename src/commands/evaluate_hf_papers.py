"""Offline-first Cerebras paper comparison; explicit funding is required to execute."""

import argparse
import asyncio
import json
from functools import partial
from pathlib import Path

from src.commands import hf_paper_allowance as funding
from src.commands.evaluate_agent import free_memory_mib, load_labels, write_json
from src.commands.evaluate_hf_agent import live_snapshot, provider_available, run_collection, source_hashes, validate_selection
from src.commands.evaluate_retrieval import digest
from src.commands.hf_evaluation import hosted_admission
from src.commands.hf_paper_client import FundedHF
from src.commands.hf_paper_profile import CEREBRAS_PROFILE, PAPER_PROFILES, get_profile, load_profile, plan_collection
from src.commands.hf_qualification import load_revision
from src.config import Settings


def _ignored(path: Path) -> bool:
    workspace = Path.cwd().resolve()
    return any(path.is_relative_to(workspace / name) and path != workspace / name
               for name in ("test_output", "tests/test_output"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--split", choices=("development", "holdout"), default="development")
    parser.add_argument("--profile", choices=PAPER_PROFILES, default=CEREBRAS_PROFILE)
    parser.add_argument("--selection", type=Path)
    parser.add_argument("--approval", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--execute", action="store_true")
    mode.add_argument("--propose-approval", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists() or not _ignored(output):
        parser.error("Output must be a fresh ignored workspace directory")
    profile_extra = {"profile_name": args.profile} if args.profile != CEREBRAS_PROFILE else {}
    metadata = plan_collection(args.snapshot, split=args.split, **profile_extra)
    metadata.update(kind="hf_cerebras_paper_comparison_v1", app_accepted=False)
    output.mkdir(parents=True, exist_ok=False)

    def stop(reason: str) -> None:
        metadata.update(status="not_started", reason=reason)
        write_json(output / "metadata.json", metadata)
        print(json.dumps({"status": "not_started", "reason": reason, "app_accepted": False}))

    write_json(output / "metadata.json", metadata)
    if not args.execute and not args.propose_approval:
        print(json.dumps({"status": "offline_plan", "jobs": len(metadata["jobs"]),
                          "proposed_attempts": metadata["planned_outbound_budget"], "approved_attempts": 0}))
        return
    profile = load_profile() if args.profile == CEREBRAS_PROFILE else get_profile(args.profile)[0]
    model = profile["model_pairs"][0]
    if args.split == "holdout":
        try:
            if args.selection is None:
                raise ValueError("Selection required")
            selection = json.loads(args.selection.read_text(encoding="utf-8"))
            validate_selection(selection, model, args.snapshot, profile_name=args.profile)
            metadata.update(selection_lock=selection, selection_sha256=digest(selection))
        except Exception:
            stop("accepted_development_required")
            return
    if args.propose_approval:
        write_json(output / "proposed-approval.json", funding.approval_proposal(metadata))
        write_json(output / "metadata.json", metadata)
        print(json.dumps({"status": "pending_user_approval", "maximum_attempts": metadata["planned_outbound_budget"],
                          "paper_data_planned": True, "app_accepted": False}))
        return
    try:
        ledger = funding.allowance_path(metadata)
        if args.approval is None or not _ignored(args.approval.resolve()) or not _ignored(ledger.resolve()):
            raise ValueError("Exact local approval required")
        grant = funding.TaskAllowance(args.approval, metadata, snapshot=args.snapshot)
        if grant.started:
            stop("allowance_already_started")
            return
    except Exception:
        stop("approval_required")
        return
    try:
        settings = Settings()
        if args.profile != CEREBRAS_PROFILE:
            settings = settings.model_validate(settings.model_copy(update={
                "rag_sentence_candidates_per_passage": profile["candidates_per_passage"],
                "rag_max_sentence_candidates": profile["max_sentence_candidates"],
            }).model_dump())
    except Exception:
        stop("configuration_required")
        return
    metadata["admission_free_mib"] = free_memory_mib()
    reason = hosted_admission(settings, metadata["jobs"], metadata["admission_free_mib"], profile)
    if reason:
        stop(reason)
        return
    try:
        before, papers, chunks = live_snapshot(settings)
        if before != json.loads((args.snapshot / "state.json").read_text(encoding="utf-8")):
            raise ValueError("Live source differs")
        catalog = provider_available(model)
        if any(catalog.get("pricing", {}).get(key) != value for key, value in profile["prices_per_million"][model].items()):
            raise ValueError("Provider pricing differs from the reviewed profile")
        metadata["provider_catalog"] = catalog
        local = Settings.model_validate(settings.model_copy(update={"hf_inference_enabled": True,
            "hf_models": [model], "hf_default_model": model, "agent_enabled": True, "answer_cache_enabled": False,
            "local_tracing_enabled": False, "monitoring_directory": None,
            "api_rate_limit_path": str(output / "quotas.sqlite3")}).model_dump())
        _, labels, _, _ = load_labels(Path("evaluation/week7_agent"), args.snapshot)
        by_case = {case["id"]: case for case in labels[args.split]["cases"]}
        jobs = [{**job, "query": by_case[job["case_id"]]["query"]} for job in metadata["jobs"]]
    except Exception:
        stop("preflight_failed")
        return
    budget = metadata["planned_outbound_budget"]
    metadata.update(status="collecting", execution_started=True, inference_started=None, outbound_budget=budget,
                    approved_outbound_budget=budget, allowance={"path": str(grant.path.resolve()),
                    "approval_path": str(args.approval.resolve()), "signature": grant.signature})
    write_json(output / "metadata.json", metadata)
    (output / "records.jsonl").touch(exist_ok=False)
    factory = partial(FundedHF, grant=grant, output=output, source=metadata["source_sha256"], **profile_extra)
    try:
        completion = asyncio.run(run_collection(local, jobs, papers, chunks, output, profile, budget,
                                                revision=load_revision(), hf_factory=factory))
    except (Exception, KeyboardInterrupt) as exc:
        completion = {"status": "stopped", "error_class": type(exc).__name__, "outbound_attempts": None}
    preservation = {"source_unchanged": source_hashes() == metadata["source_sha256"], "frozen_labels_unchanged": False,
                    "corpus_unchanged": False, "models_unchanged": False}
    try:
        get_profile(args.profile)
        load_labels(Path("evaluation/week7_agent"), args.snapshot)
        preservation["frozen_labels_unchanged"] = True
        after, _, _ = live_snapshot(settings)
        preservation.update(corpus_unchanged=after == before, models_unchanged=True)
    except Exception as exc:
        completion["preservation_error_class"] = type(exc).__name__
    completion.update(preservation=preservation, accounted_attempts_used=grant.used, app_accepted=False)
    attempts = completion.get("outbound_attempts")
    metadata.update(status=completion["status"], inference_started=attempts > 0 if type(attempts) is int else None)
    write_json(output / "completion.json", completion)
    write_json(output / "metadata.json", metadata)
    print(json.dumps({"status": completion["status"], "outbound_attempts": attempts,
                      "accounted_attempts_used": grant.used, "preservation": preservation, "app_accepted": False}))


if __name__ == "__main__":
    main()
