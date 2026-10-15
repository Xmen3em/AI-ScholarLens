import copy
import hashlib
import json
import sqlite3
from pathlib import Path

import pytest
from src.commands import hf_paper_allowance as funding
from src.commands.agent_collection import build_jobs
from src.commands.hf_paper_profile import CEREBRAS_PROFILE, CEREBRAS_TASK_SHA256


def setup(tmp_path, monkeypatch, *, approved=True):
    metadata = {"split": "development", "hosted_manifest_sha256": CEREBRAS_TASK_SHA256,
                "configuration": {"model": "openai/gpt-oss-120b:cerebras", "policy": CEREBRAS_PROFILE},
                "source_sha256": {"src/client.py": "source"}, "source_snapshot_sha256": "snapshot",
                "fixture_manifest_sha256": funding.load_cerebras()["qualification_manifest_sha256"],
                "jobs": [{k: v for k, v in job.items() if k != "query"} for job in
                         build_jobs([{"id": f"case-{index}", "query": "synthetic question"} for index in range(8)])],
                "planned_outbound_budget": 261, "outbound_budget": 0, "approved_outbound_budget": 0}
    monkeypatch.setattr(funding, "schema_history_binding", lambda: "exhausted-28-history")
    monkeypatch.setattr(funding, "plan_collection", lambda *args, **kwargs: copy.deepcopy(metadata))
    receipt = funding.approval_proposal(metadata)
    if approved:
        receipt.update(status="approved", authorization_source="explicit_user_approval")
    approval = tmp_path / "approval.json"
    approval.write_text(json.dumps(receipt))
    return metadata, approval, tmp_path / "allowance.sqlite3"


def test_pending_paper_scope_cannot_initialize_funding(tmp_path, monkeypatch):
    metadata, approval, path = setup(tmp_path, monkeypatch, approved=False)
    with pytest.raises(ValueError):
        funding.TaskAllowance(approval, metadata, snapshot=tmp_path, path=path)
    assert not path.exists() and not path.with_suffix(".registered").exists()


def test_paper_approval_binds_model_jobs_source_and_history(tmp_path, monkeypatch):
    metadata, approval, path = setup(tmp_path, monkeypatch)
    receipt = json.loads(approval.read_text())
    assert receipt["maximum_outbound_attempts"] == 261
    assert receipt["paper_data_planned"] is True
    assert receipt["exhausted_history_binding"] == "exhausted-28-history"
    grant = funding.TaskAllowance(approval, metadata, snapshot=tmp_path, path=path)
    grant.reserve("run", 1, "request-1"); grant.settle(1, 1)
    assert grant.used == 1
    monkeypatch.setattr(funding, "schema_history_binding", lambda: "changed-history")
    with pytest.raises(ValueError): grant.reserve("run", 2, "request-2")
    assert grant.used == 1


def test_uncertain_work_survives_restart_and_cannot_replay(tmp_path, monkeypatch):
    metadata, approval, path = setup(tmp_path, monkeypatch)
    grant = funding.TaskAllowance(approval, metadata, snapshot=tmp_path, path=path)
    grant.reserve("run", 1, "request-1")
    restarted = funding.TaskAllowance(approval, metadata, snapshot=tmp_path, path=path)
    assert restarted.used == 1
    with pytest.raises(ValueError): restarted.reserve("run", 1, "request-1")
    with pytest.raises(ValueError): restarted.reserve("other-run", 2, "request-2")
    restarted.settle(1, None)
    assert restarted.used == 1
    with pytest.raises(ValueError): restarted.settle(1, 0)


def test_ceiling_is_persistent_and_independent_of_output_folders(tmp_path, monkeypatch):
    metadata, approval, path = setup(tmp_path, monkeypatch)
    grant = funding.TaskAllowance(approval, metadata, snapshot=tmp_path, path=path)
    with sqlite3.connect(path) as db:
        db.executemany("INSERT INTO calls VALUES (?, ?, ?, ?)", [(i, "run", f"r-{i}", 1) for i in range(1, 261)])
    grant.reserve("run", 261, "last"); grant.settle(261, 1)
    assert funding.TaskAllowance(approval, metadata, snapshot=tmp_path, path=path).used == 261
    with pytest.raises(ValueError): grant.reserve("run", 262, "extra")
    with pytest.raises(ValueError): grant.reserve("fresh-folder", 1, "extra")


@pytest.mark.parametrize("missing", ["ledger", "registration"])
def test_missing_registered_state_is_never_reconstructed(tmp_path, monkeypatch, missing):
    metadata, approval, path = setup(tmp_path, monkeypatch)
    funding.TaskAllowance(approval, metadata, snapshot=tmp_path, path=path)
    target = path if missing == "ledger" else path.with_suffix(".registered")
    target.unlink()
    with pytest.raises(ValueError): funding.TaskAllowance(approval, metadata, snapshot=tmp_path, path=path)
    assert not target.exists()


@pytest.mark.parametrize("mutation", ["source", "jobs", "model"])
def test_scope_mismatch_rejects_before_ledger_creation(tmp_path, monkeypatch, mutation):
    metadata, approval, path = setup(tmp_path, monkeypatch)
    changed = copy.deepcopy(metadata)
    if mutation == "source": changed["source_sha256"]["src/client.py"] = "changed"
    elif mutation == "jobs": changed["jobs"][0]["key"] = "unapproved-job"
    else: changed["configuration"]["model"] = "unapproved/provider"
    with pytest.raises(ValueError): funding.TaskAllowance(approval, changed, snapshot=tmp_path, path=path)
    assert not path.exists()


@pytest.mark.parametrize("ordinal,used", [(1, False), (1, 2), (1, -1), (True, 1)])
def test_invalid_settlement_never_refunds_uncertain_work(tmp_path, monkeypatch, ordinal, used):
    metadata, approval, path = setup(tmp_path, monkeypatch)
    grant = funding.TaskAllowance(approval, metadata, snapshot=tmp_path, path=path)
    grant.reserve("run", 1, "request")
    with pytest.raises(ValueError): grant.settle(ordinal, used)
    assert grant.used == 1


@pytest.mark.parametrize("column,value", [("run", b"corrupt"), ("request_id", b"corrupt"), ("used", 2), ("ordinal", 2)])
def test_corrupt_registered_rows_are_not_accepted_on_restart(tmp_path, monkeypatch, column, value):
    metadata, approval, path = setup(tmp_path, monkeypatch)
    grant = funding.TaskAllowance(approval, metadata, snapshot=tmp_path, path=path)
    grant.reserve("run", 1, "request")
    with sqlite3.connect(path) as db:
        db.execute(f"UPDATE calls SET {column}=?", (value,))
    with pytest.raises(ValueError): funding.TaskAllowance(approval, metadata, snapshot=tmp_path, path=path)


def test_historical_proof_reader_preserves_files_and_rejects_changed_or_missing_evidence(tmp_path, monkeypatch):
    from src.commands.hf_schema_evidence import summarize

    from tests.unit.test_hf_schema_evidence import prepared

    paths = prepared(tmp_path / "history")
    report_path = tmp_path / "five-case-report.json"
    report_path.write_text(json.dumps(summarize(**paths)))
    monkeypatch.setattr(funding, "SCHEMA_REPORT_SHA256", hashlib.sha256(report_path.read_bytes()).hexdigest())
    arguments = {**paths, "report_path": report_path}
    before = {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    assert len(funding.schema_history_binding(**arguments)) == 64
    assert before == {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    marker = Path(paths["selector_path"]).with_suffix(".registered")
    for target in (report_path, marker, paths["selector_path"], paths["controller_run"] / "qualification.json"):
        target.unlink()
        with pytest.raises((ValueError, OSError, sqlite3.Error)):
            funding.schema_history_binding(**arguments)
        assert not target.exists()
        target.write_bytes(before[target])
    ledger = paths["selector_path"]
    with sqlite3.connect(ledger) as db:
        db.execute("UPDATE arms SET used=NULL WHERE arm='selector-1'")
    with pytest.raises(ValueError): funding.schema_history_binding(**arguments)
    ledger.write_bytes(before[ledger])
    assert before == {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}


def test_completed_accounting_reader_is_read_only_and_requires_settled_work(tmp_path, monkeypatch):
    metadata, approval, path = setup(tmp_path, monkeypatch)
    grant = funding.TaskAllowance(approval, metadata, snapshot=tmp_path, path=path)
    for ordinal in range(1, 6):
        grant.reserve(str(tmp_path.resolve()), ordinal, f"request-{ordinal}"); grant.settle(ordinal, 1)
    metadata["allowance"] = {"path": str(path), "approval_path": str(approval), "signature": grant.signature}
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    assert len(funding.validate_task_accounting(metadata, tmp_path, {"outbound_attempts": 5}, path=path)) == 64
    assert before == {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    with pytest.raises(ValueError): funding.validate_task_accounting(metadata, tmp_path, {"outbound_attempts": 6}, path=path)
    with sqlite3.connect(path) as db: db.execute("UPDATE calls SET used=NULL WHERE ordinal=5")
    with pytest.raises(ValueError): funding.validate_task_accounting(metadata, tmp_path, {"outbound_attempts": 5}, path=path)


@pytest.mark.parametrize("accepted", [False, True])
def test_holdout_requires_recalculated_cerebras_selection_and_stops_on_later_artifact_change(tmp_path, monkeypatch, accepted):
    metadata, approval, path = setup(tmp_path, monkeypatch)
    dev = tmp_path / "development"
    dev.mkdir()
    for name in ("metadata.json", "completion.json", "qualification.json", "reviews.json", "records.jsonl", "selection-report.json"):
        (dev / name).write_text("{}")
    sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    selection = {"development_run": str(dev), "report_sha256": sha(dev / "selection-report.json"),
                 "evidence_sha256": {p.name: sha(p) for p in dev.iterdir() if p.name != "selection-report.json"}}
    metadata.update(split="holdout", planned_outbound_budget=773, selection_lock=selection, selection_sha256=funding.digest(selection),
                    jobs=[{k: v for k, v in job.items() if k != "query"} for job in
                          build_jobs([{"id": f"holdout-{i}", "query": "synthetic question"} for i in range(24)])])
    checked = []

    def validate(value, model, snapshot, **kwargs):
        checked.append((value, model, kwargs.get("profile_name")))
        if not accepted: raise ValueError("Development is not accepted")

    monkeypatch.setattr("src.commands.evaluate_hf_agent.validate_selection", validate)
    receipt = funding.approval_proposal(metadata)
    receipt.update(status="approved", authorization_source="explicit_user_approval")
    approval.write_text(json.dumps(receipt))
    if not accepted:
        with pytest.raises(ValueError): funding.TaskAllowance(approval, metadata, snapshot=tmp_path, path=path)
        assert not path.exists() and not path.with_suffix(".registered").exists()
        return
    grant = funding.TaskAllowance(approval, metadata, snapshot=tmp_path, path=path)
    assert grant.ceiling == 773 and checked[0][1:] == ("openai/gpt-oss-120b:cerebras", CEREBRAS_PROFILE)
    grant.reserve("holdout-run", 1, "request-1"); grant.settle(1, 1)
    (dev / "reviews.json").write_text("changed")
    with pytest.raises(ValueError): grant.reserve("holdout-run", 2, "request-2")
    assert grant.used == 1
