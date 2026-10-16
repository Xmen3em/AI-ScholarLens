import hashlib
import json
import sqlite3
from pathlib import Path

import pytest
from src.commands import hf_paper_allowance as funding
from src.commands.hf_paper_profile import EVIDENCE_PROFILE, EVIDENCE_TASK_SHA256

from tests.unit.test_hf_paper_allowance import setup


def evidence_setup(tmp_path, monkeypatch, *, approved=True):
    metadata, approval, _ = setup(tmp_path, monkeypatch, approved=False)
    metadata.update(hosted_manifest_sha256=EVIDENCE_TASK_SHA256)
    metadata["configuration"]["policy"] = EVIDENCE_PROFILE
    monkeypatch.setattr(funding, "prior_development_binding", lambda: "retained-97-call-proof")
    path = tmp_path / "new-profile" / "allowance.sqlite3"
    monkeypatch.setattr(funding, "EVIDENCE_DEVELOPMENT_ALLOWANCE", path)
    receipt = funding.approval_proposal(metadata)
    if approved:
        receipt.update(status="approved", authorization_source="explicit_user_approval")
    approval.write_text(json.dumps(receipt))
    return metadata, approval, path


def test_evidence_allowance_needs_fresh_approval_and_has_a_separate_fixed_path(tmp_path, monkeypatch):
    metadata, approval, path = evidence_setup(tmp_path, monkeypatch, approved=False)
    receipt = json.loads(approval.read_text())
    assert receipt["prior_development_binding"] == "retained-97-call-proof"
    assert receipt["prior_attempts_used"] == 125 and receipt["maximum_outbound_attempts"] == 261
    assert funding.allowance_path(metadata) == path
    with pytest.raises(ValueError):
        funding.TaskAllowance(approval, metadata, snapshot=tmp_path)
    assert not path.exists() and not path.with_suffix(".registered").exists()


def test_evidence_grant_rechecks_prior_history_before_reserving(tmp_path, monkeypatch):
    metadata, approval, path = evidence_setup(tmp_path, monkeypatch)
    grant = funding.TaskAllowance(approval, metadata, snapshot=tmp_path)
    grant.reserve("new-run", 1, "request-1"); grant.settle(1, 1)
    assert grant.path == path and grant.used == 1
    monkeypatch.setattr(funding, "prior_development_binding", lambda: "changed-history")
    with pytest.raises(ValueError):
        grant.reserve("new-run", 2, "request-2")
    assert grant.used == 1


def prior_run(tmp_path, monkeypatch):
    metadata, approval, ledger = setup(tmp_path, monkeypatch)
    run = tmp_path / "old-run"; run.mkdir()
    grant = funding.TaskAllowance(approval, metadata, snapshot=tmp_path, path=ledger)
    metadata["allowance"] = {"path": str(ledger.resolve()), "approval_path": str(approval.resolve()), "signature": grant.signature}
    with sqlite3.connect(ledger) as db:
        db.executemany("INSERT INTO calls VALUES (?, ?, ?, ?)", [(i, str(run.resolve()), f"r-{i}", 1) for i in range(1, 98)])
    completion = {"status": "collected", "outbound_attempts": 97, "accounted_attempts_used": 97, "attempts": 64, "planned": 64}
    report = {"development_accepted": False, "collection_complete": True, "attempts": 64, "planned_attempts": 64,
              "model": metadata["configuration"]["model"], "hosted_manifest_sha256": metadata["hosted_manifest_sha256"],
              "funding_binding": funding.validate_task_accounting(metadata, run, completion, path=ledger)}
    for name, value in [("metadata.json", metadata), ("completion.json", completion), ("score.json", report),
                        ("qualification.json", {}), ("reviews.json", {})]:
        (run / name).write_text(json.dumps(value))
    (run / "records.jsonl").write_text("{}\n")
    seal = tmp_path / "seal.json"
    files = [*run.iterdir(), ledger, ledger.with_suffix(".registered"), approval]
    seal.write_text(json.dumps({"files": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}}))
    return {"run": run, "ledger": ledger, "seal_path": seal,
            "seal_sha256": hashlib.sha256(seal.read_bytes()).hexdigest()}


def test_previous_development_binding_is_read_only_and_checks_all_sealed_evidence(tmp_path, monkeypatch):
    arguments = prior_run(tmp_path, monkeypatch)
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    assert len(funding.prior_development_binding(**arguments)) == 64
    assert before == {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    victim = arguments["run"] / "qualification.json"
    victim.write_text('{"changed":true}')
    with pytest.raises(ValueError):
        funding.prior_development_binding(**arguments)
    victim.unlink()
    with pytest.raises((ValueError, OSError)):
        funding.prior_development_binding(**arguments)
    assert not victim.exists()


def test_previous_development_cannot_claim_an_unsettled_attempt(tmp_path, monkeypatch):
    arguments = prior_run(tmp_path, monkeypatch)
    with sqlite3.connect(arguments["ledger"]) as db:
        db.execute("UPDATE calls SET used=NULL WHERE ordinal=97")
    seal = arguments["seal_path"]
    manifest = json.loads(seal.read_text())
    manifest["files"][str(arguments["ledger"])]=hashlib.sha256(arguments["ledger"].read_bytes()).hexdigest()
    seal.write_text(json.dumps(manifest)); arguments["seal_sha256"]=hashlib.sha256(seal.read_bytes()).hexdigest()
    with pytest.raises(ValueError):
        funding.prior_development_binding(**arguments)
