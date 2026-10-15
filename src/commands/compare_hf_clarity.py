"""Default-offline two-case clarity diagnostic; live execution requires new exact approval."""

import argparse
import asyncio
import json
from pathlib import Path

from src.commands.compare_hf_prompts import collect
from src.commands.evaluate_agent import free_memory_mib, write_json
from src.commands.evaluate_hf_agent import live_snapshot, plan_collection, provider_available, source_hashes
from src.commands.hf_allowance import PILOT_CASE, PILOT_MODEL
from src.commands.hf_clarity_allowance import ClarityAllowance, approval_proposal
from src.commands.hf_clarity_execution import load_execution
from src.commands.hf_evaluation import hosted_admission, load_protocol
from src.config import Settings


def main() -> None:
    profile = load_execution()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--approval", type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--execute", action="store_true")
    mode.add_argument("--propose-approval", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    roots = [(Path.cwd() / name).resolve() for name in ("test_output", "tests/test_output")]
    if output.exists() or not any(output.is_relative_to(root) and output != root for root in roots):
        parser.error("Output must be fresh local ignored evidence")
    arms = list(profile["arms"])
    metadata = plan_collection(
        args.snapshot,
        split="development",
        model=PILOT_MODEL,
        case_ids=[PILOT_CASE],
        modes=["bm25"],
        transports=["json"],
        qualification_v2=True,
    )
    metadata.update(
        kind=profile["kind"],
        experiment="clarity-execution-v1",
        arms=arms,
        reproduction_manifest_sha256=profile["manifest_sha256"],
        candidate_manifest_sha256=profile["candidate_manifest_sha256"],
        success_diagnostic_manifest_sha256=profile["measurement_manifest_sha256"],
        qualification_accepted=False,
        proposed_outbound_budget=2,
        approved_outbound_budget=0,
        outbound_budget=0,
        paper_collection_planned=False,
    )
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "metadata.json", metadata)
    if args.propose_approval:
        write_json(output / "proposed-approval.json", approval_proposal())
        print(json.dumps({"status": "pending_user_approval", "maximum_additional_attempts": 2}))
        return
    if not args.execute:
        print(json.dumps({"status": "offline_plan", "proposed_attempts": 2, "approved_attempts": 0}))
        return
    try:
        if args.approval is None:
            raise ValueError("Additional approval required")
        grant = ClarityAllowance(args.approval)
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
        local = Settings.model_validate(
            settings.model_copy(
                update={
                    "hf_inference_enabled": True,
                    "hf_models": [PILOT_MODEL],
                    "hf_default_model": PILOT_MODEL,
                    "answer_cache_enabled": False,
                    "local_tracing_enabled": False,
                    "monitoring_directory": None,
                    "api_rate_limit_path": str(output / "quotas.sqlite3"),
                }
            ).model_dump()
        )
    except Exception:
        metadata.update(status="not_started", reason="preflight_failed")
        write_json(output / "metadata.json", metadata)
        print(json.dumps({"status": "not_started", "reason": "preflight_failed"}))
        return
    metadata.update(
        status="comparing", inference_started=None, approved_outbound_budget=2, outbound_budget=2, approval_sha256=grant.signature
    )
    write_json(output / "metadata.json", metadata)
    result = asyncio.run(collect(local, arms, grant, output, metadata["source_sha256"], experiment="clarity-execution-v1"))
    preservation = {
        "source_unchanged": source_hashes() == metadata["source_sha256"],
        "frozen_labels_unchanged": False,
        "corpus_unchanged": False,
        "models_unchanged": False,
    }
    try:
        load_execution()
        plan_collection(
            args.snapshot,
            split="development",
            model=PILOT_MODEL,
            case_ids=[PILOT_CASE],
            modes=["bm25"],
            transports=["json"],
            qualification_v2=True,
        )
        preservation["frozen_labels_unchanged"] = True
        after, _, _ = live_snapshot(settings)
        preservation.update(corpus_unchanged=after == before, models_unchanged=True)
    except Exception:
        pass
    result.update(
        preservation=preservation,
        pair_passed=(
            all(preservation.values())
            and len(result["records"]) == 2
            and [row["arm"] for row in result["records"]] == arms
            and all(
                row["category"] == "passed" and row.get("work", {}).get("usage_complete") is True for row in result["records"]
            )
        ),
        extension_attempts_used=grant.used,
        original_attempts_used=19,
        reproduction_manifest_sha256=profile["manifest_sha256"],
    )
    write_json(output / "comparison.json", result)
    metadata.update(
        status=result["status"],
        inference_started=(result["outbound_attempts"] > 0 if result["outbound_attempts"] is not None else None),
    )
    write_json(output / "metadata.json", metadata)
    print(
        json.dumps(
            {
                "status": result["status"],
                "outbound_attempts": result["outbound_attempts"],
                "pair_passed": result["pair_passed"],
                "preservation": preservation,
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
