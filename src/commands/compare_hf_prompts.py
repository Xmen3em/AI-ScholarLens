"""Offline semantic prompt plan; live work needs a separate explicit six-attempt approval."""

import argparse
import asyncio
import json
from pathlib import Path
from typing import Protocol

from src.commands.evaluate_agent import free_memory_mib, write_json
from src.commands.evaluate_hf_agent import live_snapshot, plan_collection, provider_available, source_hashes
from src.commands.hf_allowance import PILOT_CASE, PILOT_MODEL
from src.commands.hf_evaluation import hosted_admission, load_protocol
from src.commands.hf_prompt_allowance import PromptAllowance, approval_proposal
from src.commands.hf_reproduction import PROMPT_COMPARISON_SHA256, load_prompt_comparison, reproduce
from src.config import Settings


class ArmAllowance(Protocol):
    def reserve(self, run: str, arm: str) -> None: ...
    def settle(self, arm: str, used: int | None) -> None: ...


async def collect(settings: Settings, arms: list[str], grant: ArmAllowance, output: Path, expected_source: dict,
                  *, experiment="prompt-comparison-v1") -> dict:
    records = []
    stopped = None
    for arm in arms:
        if source_hashes() != expected_source or free_memory_mib() < load_protocol()["live_margin_mib"]:
            stopped = "source_or_resource_stop"
            break
        try:
            grant.reserve(str(output), arm)
        except Exception:
            stopped = "allowance_or_preservation_stop"
            break
        try:
            result = await reproduce(settings, arm, experiment=experiment)
        except Exception:
            result = {"arm": arm, "category": "transport_or_response_error",
                      "qualification_accepted": False, "outbound_attempts": None}
        grant.settle(arm, result["outbound_attempts"])
        records.append(result)
        write_json(output / (arm + ".json"), result)
        print(json.dumps({"arm": arm, "category": result["category"],
                          "outbound_attempts": result["outbound_attempts"]}), flush=True)
        if result["category"] not in {"passed", "expected_mismatch", "schema_invalid", "provider_json_validation"}:
            stopped = "uncertain_provider_or_resource_stop"
            break
        if (result["category"] == "provider_json_validation"
                and not any(row.get("provider_status") == 400 for row in result.get("calls", []))):
            stopped = "uncertain_provider_or_resource_stop"
            break
    return {"status": "stopped" if stopped else "diagnostic_completed", "stop_reason": stopped,
            "qualification_accepted": False, "records": records,
            "known_outbound_attempts": sum(row["outbound_attempts"] or 0 for row in records),
            "outbound_attempts": (None if any(row["outbound_attempts"] is None for row in records)
                                  else sum(row["outbound_attempts"] for row in records))}


def main() -> None:
    profile = load_prompt_comparison()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--arm", action="append", choices=tuple(profile["arms"]))
    parser.add_argument("--approval", type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--execute", action="store_true")
    mode.add_argument("--propose-approval", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    roots = [(Path.cwd() / name).resolve() for name in ("test_output", "tests/test_output")]
    if output.exists() or not any(output.is_relative_to(root) and output != root for root in roots):
        parser.error("Output must be fresh local ignored evidence")
    if args.arm and len(args.arm) != len(set(args.arm)):
        parser.error("Duplicate arms are not permitted")
    arms = [arm for arm in profile["arms"] if args.arm is None or arm in args.arm]
    metadata = plan_collection(args.snapshot, split="development", model=PILOT_MODEL,
                               case_ids=[PILOT_CASE], modes=["bm25"], transports=["json"], qualification_v2=True)
    metadata.update(kind=profile["kind"], experiment="prompt-comparison-v1", arms=arms,
                    reproduction_manifest_sha256=PROMPT_COMPARISON_SHA256, qualification_accepted=False,
                    proposed_outbound_budget=len(arms), approved_outbound_budget=0,
                    outbound_budget=0, paper_collection_planned=False)
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "metadata.json", metadata)
    if args.propose_approval:
        write_json(output / "proposed-approval.json", approval_proposal())
        print(json.dumps({"status": "pending_user_approval", "maximum_additional_attempts": 6}))
        return
    if not args.execute:
        print(json.dumps({"status": "offline_plan", "proposed_attempts": len(arms), "approved_attempts": 0}))
        return
    try:
        if args.approval is None:
            raise ValueError("Additional approval required")
        grant = PromptAllowance(args.approval)
    except Exception:
        metadata.update(status="not_started", reason="approval_required")
        write_json(output / "metadata.json", metadata)
        print(json.dumps({"status": "not_started", "reason": "approval_required"}))
        return
    settings, hosted_profile = Settings(), load_protocol()
    metadata["admission_free_mib"] = free_memory_mib()
    reason = hosted_admission(settings, metadata["jobs"], metadata["admission_free_mib"], hosted_profile)
    if reason:
        metadata.update(status="not_started", reason=reason)
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
    except Exception:
        metadata.update(status="not_started", reason="preflight_failed")
        write_json(output / "metadata.json", metadata)
        print(json.dumps({"status": "not_started", "reason": "preflight_failed"}))
        return
    metadata.update(status="comparing", inference_started=None, approved_outbound_budget=6,
                    outbound_budget=len(arms), approval_sha256=grant.signature)
    write_json(output / "metadata.json", metadata)
    result = asyncio.run(collect(local, arms, grant, output, metadata["source_sha256"]))
    preservation = {"source_unchanged": source_hashes() == metadata["source_sha256"],
                    "frozen_labels_unchanged": False, "corpus_unchanged": False, "models_unchanged": False}
    try:
        load_prompt_comparison()
        plan_collection(args.snapshot, split="development", model=PILOT_MODEL,
                        case_ids=[PILOT_CASE], modes=["bm25"], transports=["json"], qualification_v2=True)
        preservation["frozen_labels_unchanged"] = True
        after, _, _ = live_snapshot(settings)
        preservation.update(corpus_unchanged=after == before, models_unchanged=True)
    except Exception:
        pass
    result["preservation"] = preservation
    result["pair_passed"] = {}
    for variant in ("concise", "json-shape", "per-passage"):
        pair = [row for row in result["records"] if profile["arms"][row["arm"]]["variant"] == variant]
        result["pair_passed"][variant] = (all(preservation.values()) and len(pair) == 2
            and all(row["category"] == "passed" and row.get("work", {}).get("usage_complete") is True for row in pair))
    result.update(extension_attempts_used=grant.used, original_attempts_used=13,
                  reproduction_manifest_sha256=PROMPT_COMPARISON_SHA256)
    write_json(output / "comparison.json", result)
    metadata.update(status=result["status"], inference_started=(
        result["outbound_attempts"] > 0 if result["outbound_attempts"] is not None else None))
    write_json(output / "metadata.json", metadata)
    print(json.dumps({"status": result["status"], "outbound_attempts": result["outbound_attempts"],
                      "pair_passed": result["pair_passed"], "preservation": preservation}), flush=True)


if __name__ == "__main__":
    main()
