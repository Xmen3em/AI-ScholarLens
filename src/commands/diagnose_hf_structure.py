"""Offline by default; one approved synthetic request with bounded structural error diagnostics."""

import argparse
import asyncio
import json
from pathlib import Path

from src.commands.evaluate_agent import free_memory_mib, write_json
from src.commands.evaluate_hf_agent import live_snapshot, plan_collection, provider_available, source_hashes
from src.commands.hf_allowance import PILOT_CASE, PILOT_MODEL, PilotAllowance
from src.commands.hf_error_structure import STRUCTURE_SHA256, diagnose_structure, load_structure_protocol
from src.commands.hf_evaluation import hosted_admission, hosted_work, load_protocol
from src.config import Settings


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    profile = load_structure_protocol()
    output = args.output.resolve()
    roots = [(Path.cwd() / name).resolve() for name in ("test_output", "tests/test_output")]
    if output.exists() or not any(output.is_relative_to(root) and output != root for root in roots):
        parser.error("Output must be fresh local ignored evidence")
    metadata = plan_collection(args.snapshot, split="development", model=PILOT_MODEL,
        case_ids=[PILOT_CASE], modes=["bm25"], transports=["json"], qualification_v2=True)
    metadata.update(kind=profile["kind"], diagnostic_manifest_sha256=STRUCTURE_SHA256,
                    planned_outbound_budget=1, outbound_budget=1)
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "metadata.json", metadata)
    if not args.execute:
        print(json.dumps({"status": "offline_plan", "outbound_budget": 1}))
        return
    settings, hosted_profile = Settings(), load_protocol()
    reason = hosted_admission(settings, metadata["jobs"], free_memory_mib(), hosted_profile)
    if reason:
        metadata.update(status="not_started", reason=reason, free_memory_mib=free_memory_mib())
        write_json(output / "metadata.json", metadata)
        print(json.dumps({"status": "not_started", "reason": reason}))
        return
    try:
        before, _, _ = live_snapshot(settings)
        if before != json.loads((args.snapshot / "state.json").read_text(encoding="utf-8")):
            raise ValueError("Live source snapshot differs")
        metadata["provider_catalog"] = provider_available(PILOT_MODEL)
        local = Settings.model_validate(settings.model_copy(update={"hf_inference_enabled": True,
            "hf_models": [PILOT_MODEL], "hf_default_model": PILOT_MODEL, "answer_cache_enabled": False,
            "local_tracing_enabled": False, "monitoring_directory": None,
            "api_rate_limit_path": str(output / "quotas.sqlite3")}).model_dump())
        grant = PilotAllowance()
        if grant.reserve(str(output), 1) != 1:
            raise ValueError("Allowance cannot fund this diagnostic")
    except Exception as exc:
        metadata.update(status="not_started", error_class=type(exc).__name__)
        write_json(output / "metadata.json", metadata)
        print(json.dumps({"status": "not_started", "error_class": type(exc).__name__}))
        return
    metadata.update(status="diagnosing", inference_started=None, free_memory_mib=free_memory_mib(),
                    allowance={"prior_evidence_sha256": grant.signature, "reserved_for_run": 1, "total_ceiling": 13})
    write_json(output / "metadata.json", metadata)
    try:
        result = asyncio.run(diagnose_structure(local))
    except Exception as exc:
        result = {"kind": profile["kind"], "qualification_accepted": False,
                  "error_class": type(exc).__name__, "outbound_attempts": None}
    grant.settle(str(output), result["outbound_attempts"])
    preservation = {"source_unchanged": source_hashes() == metadata["source_sha256"],
                    "frozen_labels_unchanged": False, "corpus_unchanged": False, "models_unchanged": False}
    try:
        load_structure_protocol()
        load_protocol()
        plan_collection(args.snapshot, split="development", model=PILOT_MODEL,
                        case_ids=[PILOT_CASE], modes=["bm25"], transports=["json"], qualification_v2=True)
        preservation["frozen_labels_unchanged"] = True
        after, _, _ = live_snapshot(settings)
        preservation.update(corpus_unchanged=after == before, models_unchanged=True)
    except Exception as exc:
        result["preservation_error_class"] = type(exc).__name__
    result["preservation"] = preservation
    checks = result.get("qualification", {}).get("checks", [])
    for check in checks:
        if hosted_work(check["calls"], hosted_profile, PILOT_MODEL) != check["work"]:
            raise ValueError("Diagnostic work ledger differs")
    result["known_usage_cost_usd"] = sum(check["work"]["known_usage_cost_usd"] for check in checks)
    result["unknown_usage_attempts"] = (sum(check["work"]["unknown_usage_attempts"] for check in checks)
                                         if result["outbound_attempts"] is not None else None)
    write_json(output / "diagnostic.json", result)
    metadata.update(status="diagnostic_stopped" if result.get("error_class") else "diagnostic_completed",
                    inference_started=result["outbound_attempts"] > 0 if result["outbound_attempts"] is not None else None)
    write_json(output / "metadata.json", metadata)
    print(json.dumps({"status": metadata["status"], "outbound_attempts": result["outbound_attempts"],
                      "qualification_accepted": False, "preservation": preservation}), flush=True)


if __name__ == "__main__":
    main()
