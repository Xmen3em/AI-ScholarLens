import copy
import json
import sqlite3
from pathlib import Path

import pytest
from src.commands.evaluate_hf_agent import source_hashes
from src.commands.evaluate_retrieval import digest
from src.commands.hf_cerebras_selectors import SelectorAllowance, approval_proposal
from src.commands.hf_evaluation import hosted_work
from src.commands.hf_schema_evidence import summarize, validate_run
from src.commands.hf_schema_execution import load_cerebras, load_selectors, measurement_profile

from tests.unit.test_hf_cerebras_selectors import setup


def proof(profile, signature):
    checks = []
    for case in profile["cases"]:
        schema = digest(case["schema"])
        calls = [{"ordinal": 1, "model": profile["model"], "outcome": "completed", "schema_valid": True,
                  "input_tokens": 100, "output_tokens": 20, "reasoning_tokens": 5,
                  "output_limit": 512 if case["id"].startswith("selector") else 256,
                  "schema_sha256": schema, "outbound_attempts": 1, "duration_ms": 200.0}]
        diagnostics = {"expected_match": True}
        if case["id"] == "relevance":
            diagnostics.update(supplied_marker_membership=True, duplicate_markers=False, marker_count=1)
        checks.append({"id": case["id"], "ok": True, "schema_sha256": schema, "fixture_sha256": digest(case),
                       "diagnostics": diagnostics, "minimum_free_mib": 1500,
                       "calls": calls, "work": hosted_work(calls, measurement_profile("cerebras-selectors-v1"), profile["model"])})
    count = len(checks)
    metadata = {"kind": profile["kind"], "status": "schema_qualification_completed", "approval_sha256": signature,
                "configuration": {"model": profile["model"], "policy": "hosted-agent-v1"}, "arms": profile["arms"],
                "jobs": [], "paper_collection_planned": False, "app_accepted": False,
                "admission_free_mib": 2000, "source_sha256": source_hashes(),
                "schema_execution_manifest_sha256": profile["manifest_sha256"],
                "fixture_manifest_sha256": profile["qualification_manifest_sha256"]}
    result = {"kind": "schema_qualification_only", "app_accepted": False, "schema_qualified": False,
              "diagnostic_passed": True, "outbound_attempts": count, "extension_attempts_used": count,
              "schema_execution_manifest_sha256": profile["manifest_sha256"],
              "preservation": dict.fromkeys(["source_unchanged", "frozen_labels_unchanged", "corpus_unchanged", "models_unchanged"], True),
              "qualification": {"qualified": False, "large_schema_preflight_rejected": True,
                                "fixture_manifest_sha256": profile["qualification_manifest_sha256"], "checks": checks}}
    return metadata, result


@pytest.mark.parametrize("mutation", [
    "order", "fixture", "schema", "call_schema", "model", "attempts", "missing_usage", "work", "output_limit",
    "reasoning", "nan_duration", "memory", "nan_memory", "admission", "preflight", "semantic", "preservation", "paper",
])
def test_rejects_incomplete_or_inconsistent_proof(mutation):
    profile = load_selectors()
    metadata, result = proof(profile, "signature")
    check = result["qualification"]["checks"][0]
    call = check["calls"][0]
    if mutation == "order": result["qualification"]["checks"].reverse()
    elif mutation == "fixture": check["fixture_sha256"] = "changed"
    elif mutation == "schema": check["schema_sha256"] = "changed"
    elif mutation == "call_schema": call["schema_sha256"] = "changed"
    elif mutation == "model": call["model"] = "other/provider"
    elif mutation == "attempts": call["outbound_attempts"] = 0
    elif mutation == "missing_usage": call["input_tokens"] = None
    elif mutation == "work": check["work"]["known_usage_cost_usd"] = 0
    elif mutation == "output_limit": call["output_limit"] = 256
    elif mutation == "reasoning": call["reasoning_tokens"] = 21
    elif mutation == "nan_duration": call["duration_ms"] = float("nan")
    elif mutation == "memory": check["minimum_free_mib"] = 599
    elif mutation == "nan_memory": check["minimum_free_mib"] = float("nan")
    elif mutation == "admission": metadata["admission_free_mib"] = 1023
    elif mutation == "preflight": result["qualification"]["large_schema_preflight_rejected"] = False
    elif mutation == "semantic": check["diagnostics"]["expected_match"] = False
    elif mutation == "preservation": result["preservation"]["corpus_unchanged"] = False
    elif mutation == "paper": metadata["jobs"] = [{"query": "paper query"}]
    with pytest.raises(ValueError):
        validate_run(metadata, result, profile, "signature")


def prepared(tmp_path):
    approval, paths = setup(tmp_path)
    controller = paths["controller_run"]
    old = json.loads((controller / "metadata.json").read_text())
    metadata, result = proof(load_cerebras(), old["approval_sha256"])
    for name, value in (("metadata.json", metadata), ("qualification.json", result)):
        (controller / name).write_text(json.dumps(value))
    parents = {key: value for key, value in paths.items() if key != "path"}
    receipt = approval_proposal(**parents)
    receipt.update(status="approved", authorization_source="explicit_user_approval")
    approval.write_text(json.dumps(receipt))
    grant = SelectorAllowance(approval, **paths)
    run = tmp_path / "selectors"
    run.mkdir()
    for arm in load_selectors()["arms"]:
        grant.reserve(str(run.resolve()), arm); grant.settle(arm, 1)
    metadata, result = proof(load_selectors(), grant.signature)
    for name, value in (("metadata.json", metadata), ("qualification.json", result)):
        (run / name).write_text(json.dumps(value))
    return dict(selector_run=run, selector_approval=approval, selector_path=paths["path"], **parents)


def test_full_five_report_is_read_only_and_does_not_accept_app(tmp_path):
    paths = prepared(tmp_path)
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    report = summarize(**paths)
    assert report["five_schema_cases_verified"] is True
    assert report["app_accepted"] is report["task_evaluation_accepted"] is False
    assert report["outbound_attempts"] == 5
    assert report["cases"] == ["scope", "relevance", "rewrite", "selector-1", "selector-10"]
    assert before == {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}


@pytest.mark.parametrize("mutation", ["unsettled", "missing_ledger", "missing_marker", "runtime_drift", "controller_drift", "pending"])
def test_summary_requires_complete_approved_accounting_and_same_runtime(tmp_path, mutation):
    paths = prepared(tmp_path)
    if mutation == "unsettled":
        with sqlite3.connect(paths["selector_path"]) as db:
            db.execute("UPDATE arms SET used=NULL WHERE arm='selector-1'")
    elif mutation == "missing_ledger": Path(paths["selector_path"]).unlink()
    elif mutation == "missing_marker": Path(paths["selector_path"]).with_suffix(".registered").unlink()
    elif mutation == "pending":
        receipt = json.loads(paths["selector_approval"].read_text())
        receipt["status"] = "pending_user_approval"
        paths["selector_approval"].write_text(json.dumps(receipt))
    else:
        run = paths["controller_run"] if mutation == "controller_drift" else paths["selector_run"]
        metadata = json.loads((run / "metadata.json").read_text())
        metadata["source_sha256"]["src/services/hf/client.py"] = "changed"
        (run / "metadata.json").write_text(json.dumps(metadata))
    with pytest.raises((ValueError, FileNotFoundError)):
        summarize(**paths)
    if mutation == "missing_ledger": assert not Path(paths["selector_path"]).exists()


def test_unmodified_proof_and_frozen_inputs_are_accepted_without_credentials():
    profile = load_cerebras()
    metadata, result = proof(profile, "signature")
    before = copy.deepcopy(result)
    assert validate_run(metadata, result, profile, "signature") == result["qualification"]["checks"]
    assert before == result
