"""One explicitly bounded synthetic request for private provider error classification."""

import argparse
import asyncio
import hashlib
import json
from pathlib import Path

from src.commands.evaluate_agent import free_memory_mib, write_json
from src.commands.evaluate_hf_agent import live_snapshot, plan_collection, provider_available, source_hashes
from src.commands.hf_allowance import PILOT_CASE, PILOT_MODEL, PilotAllowance
from src.commands.hf_evaluation import MeasuredHF, hosted_admission, load_protocol, qualify
from src.commands.hf_qualification import load_revision
from src.config import Settings
from src.middlewares import RateLimiter

DIAGNOSTIC_SHA256 = "f6dbb28536907fdefa4240f93e62cb93c354e21112c8bb5cbe31287133b4b1b5"


def validate_protocol() -> None:
    path = Path("evaluation/week7_hf/qualification-v2/DIAGNOSTIC.md")
    if hashlib.sha256(path.read_bytes()).hexdigest() != DIAGNOSTIC_SHA256:
        raise ValueError("Diagnostic protocol differs")


async def diagnose(settings: Settings, revision: dict, *, memory=free_memory_mib) -> dict:
    validate_protocol()
    hf = MeasuredHF(settings, outbound_budget=1)
    try:
        selected = {**revision, "cases": [revision["cases"][1]]}
        result = await qualify(hf, load_protocol(), limiter=RateLimiter(settings), memory=memory, revision=selected)
        return {"kind": "diagnostic_only", "qualification_accepted": False,
                "qualification": result, "outbound_attempts": hf.attempts}
    finally:
        await hf.aclose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    validate_protocol()
    output = args.output.resolve()
    roots = [(Path.cwd() / name).resolve() for name in ("test_output", "tests/test_output")]
    if output.exists() or not any(output.is_relative_to(root) and output != root for root in roots):
        parser.error("Output must be fresh local ignored evidence")
    metadata = plan_collection(args.snapshot, split="development", model=PILOT_MODEL,
        case_ids=[PILOT_CASE], modes=["bm25"], transports=["json"], qualification_v2=True)
    metadata.update(kind="diagnostic_only", diagnostic_protocol_sha256=DIAGNOSTIC_SHA256, outbound_budget=1)
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "metadata.json", metadata)
    if not args.execute:
        print(json.dumps({"status": "offline_plan", "outbound_budget": 1}))
        return
    settings, revision = Settings(), load_revision()
    reason = hosted_admission(settings, metadata["jobs"], free_memory_mib(), load_protocol())
    if reason:
        metadata.update(status="not_started", reason=reason, free_memory_mib=free_memory_mib())
        write_json(output / "metadata.json", metadata)
        print(json.dumps({"status": "not_started", "reason": reason}))
        return
    try:
        before, _, _ = live_snapshot(settings)
        if before != json.loads((args.snapshot / "state.json").read_text(encoding="utf-8")):
            raise ValueError("Live source differs")
        metadata["provider_catalog"] = provider_available(PILOT_MODEL)
        local = Settings.model_validate(settings.model_copy(update={"hf_inference_enabled": True,
            "hf_models": [PILOT_MODEL], "hf_default_model": PILOT_MODEL, "answer_cache_enabled": False,
            "local_tracing_enabled": False, "monitoring_directory": None,
            "api_rate_limit_path": str(output / "quotas.sqlite3")}).model_dump())
        grant = PilotAllowance()
        grant.reserve(str(output), 1)
    except Exception as exc:
        metadata.update(status="not_started", error_class=type(exc).__name__)
        write_json(output / "metadata.json", metadata)
        print(json.dumps({"status": "not_started", "error_class": type(exc).__name__}))
        return
    metadata.update(status="diagnosing", inference_started=None, free_memory_mib=free_memory_mib(),
                    allowance={"prior_evidence_sha256": grant.signature, "reserved_for_run": 1, "total_ceiling": 13})
    write_json(output / "metadata.json", metadata)
    try:
        result = asyncio.run(diagnose(local, revision))
    except Exception as exc:
        result = {"kind": "diagnostic_only", "qualification_accepted": False,
                  "error_class": type(exc).__name__, "outbound_attempts": None}
    grant.settle(str(output), result["outbound_attempts"])
    preservation = {"source_unchanged": source_hashes() == metadata["source_sha256"],
                    "frozen_labels_unchanged": False, "corpus_unchanged": False, "models_unchanged": False}
    try:
        validate_protocol()
        load_protocol()
        load_revision()
        # Also revalidate the original labels/snapshot through the unchanged planner.
        plan_collection(args.snapshot, split="development", model=PILOT_MODEL, case_ids=[PILOT_CASE], modes=["bm25"], transports=["json"])
        preservation["frozen_labels_unchanged"] = True
        after, _, _ = live_snapshot(settings)
        preservation.update(corpus_unchanged=after == before, models_unchanged=True)
    except Exception as exc:
        result["preservation_error_class"] = type(exc).__name__
    result["preservation"] = preservation
    write_json(output / "diagnostic.json", result)
    metadata.update(status="diagnostic_completed", inference_started=result["outbound_attempts"] > 0 if result["outbound_attempts"] is not None else None)
    write_json(output / "metadata.json", metadata)
    print(json.dumps({"status": metadata["status"], "outbound_attempts": result["outbound_attempts"],
                      "qualification_accepted": False, "preservation": preservation}), flush=True)


if __name__ == "__main__":
    main()
