"""Offline by default; execute exactly one frozen synthetic HF/Groq reproduction arm."""

import argparse
import asyncio
import json
from pathlib import Path

from src.commands.evaluate_agent import free_memory_mib, write_json
from src.commands.evaluate_hf_agent import live_snapshot, plan_collection, provider_available, source_hashes
from src.commands.hf_allowance import ALLOWANCE_PATH, PILOT_CASE, PILOT_MODEL, PilotAllowance
from src.commands.hf_evaluation import hosted_admission, load_protocol
from src.commands.hf_reproduction import REPRODUCTION_SHA256, load_reproduction, reproduce
from src.config import Settings


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    profile = load_reproduction()
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--arm", choices=tuple(profile["arms"]), required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    roots = [(Path.cwd() / name).resolve() for name in ("test_output", "tests/test_output")]
    if output.exists() or not any(output.is_relative_to(root) and output != root for root in roots):
        parser.error("Output must be fresh local ignored evidence")
    metadata = plan_collection(args.snapshot, split="development", model=PILOT_MODEL,
                               case_ids=[PILOT_CASE], modes=["bm25"], transports=["json"], qualification_v2=True)
    metadata.update(kind=profile["kind"], arm=args.arm, reproduction_manifest_sha256=REPRODUCTION_SHA256,
                    planned_outbound_budget=1, outbound_budget=1, qualification_accepted=False)
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "metadata.json", metadata)
    if not args.execute:
        print(json.dumps({"status": "offline_plan", "arm": args.arm, "outbound_budget": 1}))
        return
    settings, hosted_profile = Settings(), load_protocol()
    # Persist the actual admission sample, distinct from the later pre-request sample.
    metadata["admission_free_mib"] = free_memory_mib()
    reason = hosted_admission(settings, metadata["jobs"], metadata["admission_free_mib"], hosted_profile)
    if reason:
        metadata.update(status="not_started", reason=reason)
        write_json(output / "metadata.json", metadata)
        print(json.dumps({"status": "not_started", "reason": reason}))
        return
    try:
        if not ALLOWANCE_PATH.is_file():
            raise ValueError("Retained allowance missing")
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
            raise ValueError("Allowance cannot fund reproduction")
    except Exception:
        metadata.update(status="not_started", reason="preflight_failed")
        write_json(output / "metadata.json", metadata)
        print(json.dumps({"status": "not_started", "reason": "preflight_failed"}))
        return
    metadata.update(status="reproducing", inference_started=None,
                    allowance={"prior_evidence_sha256": grant.signature, "reserved_for_run": 1, "total_ceiling": 13})
    write_json(output / "metadata.json", metadata)
    try:
        result = asyncio.run(reproduce(local, args.arm))
    except Exception:
        result = {"arm": args.arm, "qualification_accepted": False,
                  "category": "transport_or_response_error", "outbound_attempts": None}
    grant.settle(str(output), result["outbound_attempts"])
    preservation = {"source_unchanged": source_hashes() == metadata["source_sha256"],
                    "frozen_labels_unchanged": False, "corpus_unchanged": False, "models_unchanged": False}
    try:
        load_reproduction()
        load_protocol()
        plan_collection(args.snapshot, split="development", model=PILOT_MODEL,
                        case_ids=[PILOT_CASE], modes=["bm25"], transports=["json"], qualification_v2=True)
        preservation["frozen_labels_unchanged"] = True
        after, _, _ = live_snapshot(settings)
        preservation.update(corpus_unchanged=after == before, models_unchanged=True)
    except Exception:
        pass
    result["preservation"] = preservation
    write_json(output / "diagnostic.json", result)
    metadata.update(status="diagnostic_completed", inference_started=(
        result["outbound_attempts"] > 0 if result["outbound_attempts"] is not None else None))
    write_json(output / "metadata.json", metadata)
    print(json.dumps({"status": metadata["status"], "arm": args.arm, "category": result["category"],
                      "outbound_attempts": result["outbound_attempts"], "preservation": preservation}), flush=True)


if __name__ == "__main__":
    main()
