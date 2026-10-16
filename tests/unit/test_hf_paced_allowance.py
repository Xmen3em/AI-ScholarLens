import hashlib
import json
import sqlite3
from pathlib import Path

import pytest
from src.commands import hf_paper_allowance as funding
from src.commands.hf_paper_profile import EVIDENCE_TASK_SHA256, PACED_PROFILE, PACED_TASK_SHA256

from tests.unit.test_hf_evidence_allowance import evidence_setup


def paced_setup(tmp_path, monkeypatch, *, approved=True):
    metadata, approval, _ = evidence_setup(tmp_path, monkeypatch, approved=False)
    metadata["configuration"]["policy"] = PACED_PROFILE
    metadata["hosted_manifest_sha256"] = PACED_TASK_SHA256
    monkeypatch.setattr(funding, "prior_evidence_binding", lambda: "retained-124-call-proof", raising=False)
    path = tmp_path / "paced" / "allowance.sqlite3"
    monkeypatch.setattr(funding, "PACED_DEVELOPMENT_ALLOWANCE", path, raising=False)
    receipt = funding.approval_proposal(metadata)
    if approved:
        receipt.update(status="approved", authorization_source="explicit_user_approval")
    approval.write_text(json.dumps(receipt), encoding="utf-8")
    return metadata, approval, path


def test_paced_scope_binds_all_249_previous_attempts_and_allocates_nothing_pending(tmp_path, monkeypatch):
    metadata, approval, path = paced_setup(tmp_path, monkeypatch, approved=False)
    receipt = json.loads(approval.read_text(encoding="utf-8"))
    assert receipt["prior_attempts_used"] == 249
    assert receipt["prior_development_binding"] == "retained-97-call-proof"
    assert receipt["prior_evidence_binding"] == "retained-124-call-proof"
    assert receipt["maximum_outbound_attempts"] == 261
    assert "164 and 137 unused slots are not transferred" in receipt["scope"]
    assert funding.allowance_path(metadata) == path
    with pytest.raises(ValueError):
        funding.TaskAllowance(approval, metadata, snapshot=tmp_path)
    assert not path.exists() and not path.with_suffix(".registered").exists()


def test_paced_grant_rechecks_stopped_history_on_reservation_and_settlement(tmp_path, monkeypatch):
    metadata, approval, path = paced_setup(tmp_path, monkeypatch)
    grant = funding.TaskAllowance(approval, metadata, snapshot=tmp_path)
    grant.reserve("new-run", 1, "request-1")
    monkeypatch.setattr(funding, "prior_evidence_binding", lambda: "changed-history")
    with pytest.raises(ValueError):
        grant.settle(1, 1)
    with pytest.raises(ValueError):
        grant.reserve("new-run", 2, "request-2")
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT used FROM calls").fetchall() == [(None,)]
    assert grant.used == 1


def stopped_run(tmp_path, monkeypatch):
    metadata, approval, ledger = evidence_setup(tmp_path, monkeypatch)
    run = tmp_path / "stopped-run"; run.mkdir()
    grant = funding.TaskAllowance(approval, metadata, snapshot=tmp_path)
    metadata["allowance"] = {"path": str(ledger.resolve()), "approval_path": str(approval.resolve()), "signature": grant.signature}
    with sqlite3.connect(ledger) as db:
        db.executemany("INSERT INTO calls VALUES (?, ?, ?, ?)", [(i, str(run.resolve()), f"r-{i}", 1) for i in range(1, 125)])
    completion = {"status": "stopped", "stop_reason": "failed_paper_request", "outbound_attempts": 124,
                  "accounted_attempts_used": 124, "attempts": 63, "planned": 64}
    report = {"development_accepted": False, "collection_complete": False, "attempts": 63, "planned_attempts": 64,
              "model": metadata["configuration"]["model"], "hosted_manifest_sha256": EVIDENCE_TASK_SHA256,
              "funding_binding": funding.validate_task_accounting(metadata, run, completion, path=ledger)}
    for name, value in [("metadata.json", metadata), ("completion.json", completion), ("score.json", report),
                        ("qualification.json", {}), ("reviews.json", {})]:
        (run / name).write_text(json.dumps(value), encoding="utf-8")
    (run / "records.jsonl").write_text("{}\n", encoding="utf-8")
    seal = tmp_path / "seal.json"
    files = [*run.iterdir(), ledger, ledger.with_suffix(".registered"), approval]
    seal.write_text(json.dumps({"files": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}}), encoding="utf-8")
    return {"run": run, "ledger": ledger, "seal_path": seal,
            "seal_sha256": hashlib.sha256(seal.read_bytes()).hexdigest()}


def test_stopped_history_reader_is_read_only_and_rejects_changed_or_missing_proof(tmp_path, monkeypatch):
    arguments = stopped_run(tmp_path, monkeypatch)
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    assert len(funding.prior_evidence_binding(**arguments)) == 64
    assert before == {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    victim = arguments["run"] / "qualification.json"
    victim.write_text('{"changed":true}', encoding="utf-8")
    with pytest.raises(ValueError):
        funding.prior_evidence_binding(**arguments)
    victim.unlink()
    with pytest.raises((ValueError, OSError)):
        funding.prior_evidence_binding(**arguments)
    assert not victim.exists()


@pytest.mark.parametrize("mutation", ["unsettled", "count", "status", "accepted"])
def test_stopped_history_rejects_invalid_accounting_even_with_a_matching_test_seal(tmp_path, monkeypatch, mutation):
    arguments = stopped_run(tmp_path, monkeypatch)
    run = arguments["run"]
    if mutation == "unsettled":
        with sqlite3.connect(arguments["ledger"]) as db:
            db.execute("UPDATE calls SET used=NULL WHERE ordinal=124")
    else:
        target = run / ("score.json" if mutation == "accepted" else "completion.json")
        value = json.loads(target.read_text(encoding="utf-8"))
        value.update({"count": {"outbound_attempts": 123}, "status": {"status": "collected"},
                      "accepted": {"development_accepted": True}}[mutation])
        target.write_text(json.dumps(value), encoding="utf-8")
    seal = arguments["seal_path"]
    data = json.loads(seal.read_text(encoding="utf-8"))
    data["files"] = {name: hashlib.sha256(Path(name).read_bytes()).hexdigest() for name in data["files"]}
    seal.write_text(json.dumps(data), encoding="utf-8")
    arguments["seal_sha256"] = hashlib.sha256(seal.read_bytes()).hexdigest()
    with pytest.raises(ValueError):
        funding.prior_evidence_binding(**arguments)


def test_paced_scope_cannot_be_funded_by_the_old_evidence_receipt(tmp_path, monkeypatch):
    metadata, approval, _ = evidence_setup(tmp_path, monkeypatch)
    metadata["configuration"]["policy"] = PACED_PROFILE
    metadata["hosted_manifest_sha256"] = PACED_TASK_SHA256
    monkeypatch.setattr(funding, "prior_evidence_binding", lambda: "retained-124-call-proof", raising=False)
    path = tmp_path / "new" / "allowance.sqlite3"
    with pytest.raises(ValueError):
        funding.TaskAllowance(approval, metadata, snapshot=tmp_path, path=path)
    assert not path.exists() and not path.with_suffix(".registered").exists()
