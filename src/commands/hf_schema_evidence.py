"""Read-only verification of the separate Cerebras controller and selector runs."""

import argparse
import hashlib
import json
import math
import sqlite3
from contextlib import closing
from pathlib import Path

from src.commands.evaluate_hf_agent import source_hashes
from src.commands.evaluate_retrieval import digest
from src.commands.hf_cerebras_selectors import CONTROLLER_APPROVAL, CONTROLLER_RUN, SELECTOR_ALLOWANCE_PATH, approval_proposal
from src.commands.hf_evaluation import hosted_work
from src.commands.hf_schema_execution import load_cerebras, load_selectors, measurement_profile

SELECTOR_RUN = Path("tests/test_output/hf-cerebras-selectors-live-20261015-01")
SELECTOR_APPROVAL = Path("tests/test_output/hf-cerebras-selectors-execution-20261015-01/approval.json")
# These four files only prepare, fund, collect or inspect the separate diagnostics.
# All runtime, schema, canonical measurement and other command files must match.
ORCHESTRATION_FILES = frozenset(f"src/commands/{name}.py" for name in (
    "hf_schema_execution", "qualify_hf_schema", "hf_cerebras_selectors", "hf_schema_evidence"))
PRESERVATION = {"source_unchanged", "frozen_labels_unchanged", "corpus_unchanged", "models_unchanged"}


def _margin(value, minimum: int) -> bool:
    return type(value) in {int, float} and math.isfinite(value) and value >= minimum


def validate_run(metadata: dict, result: dict, profile: dict, signature: str) -> list[dict]:
    """Recompute work and verify canonical case identity; retain no generated text."""
    qualification = result.get("qualification", {})
    checks = qualification.get("checks", [])
    count = profile["maximum_outbound_attempts"]
    if (metadata.get("status") != "schema_qualification_completed" or metadata.get("kind") != profile["kind"]
            or metadata.get("approval_sha256") != signature
            or metadata.get("configuration") != {"model": profile["model"], "policy": "hosted-agent-v1"}
            or metadata.get("arms") != profile["arms"] or metadata.get("jobs") != []
            or metadata.get("paper_collection_planned") is not False or metadata.get("app_accepted") is not False
            or metadata.get("schema_execution_manifest_sha256") != profile["manifest_sha256"]
            or metadata.get("fixture_manifest_sha256") != profile["qualification_manifest_sha256"]
            or not _margin(metadata.get("admission_free_mib"), 1024)
            or result.get("kind") != "schema_qualification_only" or result.get("diagnostic_passed") is not True
            or result.get("app_accepted") is not False or result.get("schema_qualified") is not False
            or type(result.get("outbound_attempts")) is not int or result["outbound_attempts"] != count
            or type(result.get("extension_attempts_used")) is not int or result["extension_attempts_used"] != count
            or result.get("schema_execution_manifest_sha256") != profile["manifest_sha256"]
            or qualification.get("qualified") is not False or qualification.get("large_schema_preflight_rejected") is not True
            or qualification.get("fixture_manifest_sha256") != profile["qualification_manifest_sha256"]
            or [check.get("id") for check in checks] != profile["arms"]
            or set(result.get("preservation", {})) != PRESERVATION
            or any(value is not True for value in result["preservation"].values())):
        raise ValueError("Incomplete preserved synthetic run")
    measurements = measurement_profile("cerebras-selectors-v1")
    for check, case in zip(checks, profile["cases"], strict=True):
        calls = check.get("calls", [])
        diagnostics: dict[str, bool | int] = {"expected_match": True}
        if case["id"] == "relevance":
            diagnostics.update(supplied_marker_membership=True, duplicate_markers=False, marker_count=1)
        if (check.get("ok") is not True or "error_class" in check or check.get("schema_sha256") != digest(case["schema"])
                or check.get("fixture_sha256") != digest(case) or digest(check.get("diagnostics")) != digest(diagnostics)
                or not _margin(check.get("minimum_free_mib"), 600) or len(calls) != 1):
            raise ValueError("Canonical case or semantic/resource evidence differs")
        call = calls[0]
        work = hosted_work(calls, measurements, profile["model"])
        reasoning = call.get("reasoning_tokens")
        if (call.get("outcome") != "completed" or call.get("schema_valid") is not True
                or call.get("schema_sha256") != digest(case["schema"])
                or call.get("output_limit") != (512 if case["id"].startswith("selector") else 256)
                or work["outbound_attempts"] != 1 or not work["usage_complete"] or work["schema_violations"] != 0
                or digest(check.get("work")) != digest(work)
                or reasoning is not None and (type(reasoning) is not int or not 0 <= reasoning <= call["output_tokens"])):
            raise ValueError("Complete schema and token accounting is required")
    return checks


def summarize(*, selector_run=SELECTOR_RUN, selector_approval=SELECTOR_APPROVAL, selector_path=SELECTOR_ALLOWANCE_PATH,
              controller_run=CONTROLLER_RUN, controller_approval=CONTROLLER_APPROVAL, **parents) -> dict:
    """Never initialize an allowance or a service; missing evidence fails closed."""
    run, approval, path = Path(selector_run), Path(selector_approval), Path(selector_path)
    marker = path.with_suffix(".registered")
    if not all(item.is_file() for item in (path, marker, approval)):
        raise ValueError("Completed approved selector evidence is required")
    expected = approval_proposal(controller_run=controller_run, controller_approval=controller_approval, **parents)
    expected.update(status="approved", authorization_source="explicit_user_approval")
    receipt = json.loads(approval.read_text(encoding="utf-8"))
    signature = digest(receipt)
    if digest(receipt) != digest(expected) or marker.read_text(encoding="utf-8") != signature:
        raise ValueError("Selector approval or retained controller history differs")
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        seeds = db.execute("SELECT signature FROM seed").fetchall()
        rows = db.execute("SELECT arm,run,used FROM arms ORDER BY arm").fetchall()
    if (seeds != [(signature,)] or [row[0] for row in rows] != ["selector-1", "selector-10"]
            or any(row[1] != str(run.resolve()) or type(row[2]) is not int or row[2] != 1 for row in rows)):
        raise ValueError("Complete exhausted two-arm selector accounting is required")
    current = {name: value for name, value in source_hashes().items() if name not in ORCHESTRATION_FILES}
    checks, evidence = [], {}
    for directory, approved, profile in ((Path(controller_run), Path(controller_approval), load_cerebras()),
                                         (run, approval, load_selectors())):
        metadata_path, result_path = directory / "metadata.json", directory / "qualification.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        result = json.loads(result_path.read_text(encoding="utf-8"))
        source = metadata.get("source_sha256", {})
        if {name: value for name, value in source.items() if name not in ORCHESTRATION_FILES} != current:
            raise ValueError("Diagnostic runtime or canonical measurement source differs")
        approved_signature = digest(json.loads(approved.read_text(encoding="utf-8")))
        checks.extend(validate_run(metadata, result, profile, approved_signature))
        for item in (metadata_path, result_path, approved):
            evidence[str(item)] = hashlib.sha256(item.read_bytes()).hexdigest()
    return {"kind": "hf_cerebras_five_case_evidence_v1", "five_schema_cases_verified": True,
            "model": load_selectors()["model"], "cases": [check["id"] for check in checks], "outbound_attempts": 5,
            "known_usage_cost_usd": round(sum(check["work"]["known_usage_cost_usd"] for check in checks), 10),
            "minimum_free_mib": min(check["minimum_free_mib"] for check in checks),
            "runtime_source_sha256": digest(current), "selector_approval_sha256": signature,
            "complete_controller_history_binding": receipt["complete_controller_history_binding"],
            "selector_accounting_sha256": digest({"seed": signature, "arms": rows,
                                                 "sqlite_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}),
            "evidence_sha256": evidence, "task_evaluation_accepted": False, "app_accepted": False}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selector-run", type=Path, default=SELECTOR_RUN)
    parser.add_argument("--selector-approval", type=Path, default=SELECTOR_APPROVAL)
    args = parser.parse_args()
    try:
        report = summarize(selector_run=args.selector_run, selector_approval=args.selector_approval)
    except (ValueError, OSError, KeyError, TypeError, sqlite3.Error):
        print(json.dumps({"five_schema_cases_verified": False, "reason": "complete_valid_evidence_required", "app_accepted": False}))
        raise SystemExit(2) from None
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
