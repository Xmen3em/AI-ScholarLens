import hashlib
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest
from src.commands.hf_prompt_allowance import PromptAllowance, approval_proposal, original_binding
from src.commands.hf_reproduction import load_prompt_comparison

from tests.unit.test_hf_allowance import seed


def setup(tmp_path, *, approved=True):
    original, prior = seed(tmp_path)
    original.reserve("original-used", 11)
    original.settle("original-used", 11)
    proposal = approval_proposal(original=original.path, prior=prior)
    if approved:
        proposal.update(status="approved", authorization_source="explicit_user_approval")
    path = tmp_path / "approval.json"
    path.write_text(json.dumps(proposal))
    return original, prior, path, tmp_path / "extension.sqlite3"


def test_pending_proposal_cannot_initialize_a_new_allowance(tmp_path):
    original, prior, approval, ledger = setup(tmp_path, approved=False)
    before = original.path.read_bytes()
    with pytest.raises(ValueError):
        PromptAllowance(approval, path=ledger, original=original.path, prior=prior)
    assert not ledger.exists() and original.path.read_bytes() == before


@pytest.mark.parametrize("field,value", [("maximum_outbound_attempts", 7), ("model", "other:provider"),
                                       ("status", "pending_user_approval"), ("authorization_source", None),
                                       ("manifest_sha256", "0" * 64), ("paper_data_sent", True), ("paper_data_sent", 0)])
def test_approval_scope_cannot_expand_or_change(tmp_path, field, value):
    original, prior, approval, ledger = setup(tmp_path)
    value_record = json.loads(approval.read_text())
    value_record[field] = value
    approval.write_text(json.dumps(value_record))
    with pytest.raises(ValueError):
        PromptAllowance(approval, path=ledger, original=original.path, prior=prior)
    assert not ledger.exists()


def test_new_outputs_cannot_repeat_arms_or_reset_six_call_extension(tmp_path):
    original, prior, approval, ledger = setup(tmp_path)
    before = hashlib.sha256(original.path.read_bytes()).hexdigest()
    grant = PromptAllowance(approval, path=ledger, original=original.path, prior=prior)
    arms = list(load_prompt_comparison()["arms"])
    for i, arm in enumerate(arms):
        grant.reserve(str(tmp_path / f"run-{i}"), arm)
        grant.settle(arm, 1)
    fresh = PromptAllowance(approval, path=ledger, original=original.path, prior=prior)
    with pytest.raises(ValueError):
        fresh.reserve("fresh-folder", arms[0])
    assert fresh.used == 6 and hashlib.sha256(original.path.read_bytes()).hexdigest() == before


def test_unknown_work_consumes_one_and_cannot_settle_twice(tmp_path):
    original, prior, approval, ledger = setup(tmp_path)
    grant = PromptAllowance(approval, path=ledger, original=original.path, prior=prior)
    arm = next(iter(load_prompt_comparison()["arms"]))
    grant.reserve("unknown", arm)
    grant.settle(arm, None)
    assert grant.used == 1
    with pytest.raises(ValueError):
        grant.settle(arm, 0)
    with pytest.raises(ValueError):
        grant.reserve("retry", arm)


def test_changed_old_allowance_or_receipt_blocks_next_arm(tmp_path):
    original, prior, approval, ledger = setup(tmp_path)
    grant = PromptAllowance(approval, path=ledger, original=original.path, prior=prior)
    with sqlite3.connect(original.path) as db:
        db.execute("UPDATE reservations SET run='altered-original-evidence'")
    arm = next(iter(load_prompt_comparison()["arms"]))
    with pytest.raises(ValueError):
        grant.reserve("blocked", arm)


def test_missing_old_allowance_never_reconstructs_partial_evidence(tmp_path):
    missing = tmp_path / "missing.sqlite3"
    with pytest.raises((ValueError, sqlite3.OperationalError)):
        original_binding(missing, prior=tmp_path / "missing-prior")
    assert not missing.exists()


def test_deleted_registered_extension_cannot_be_recreated(tmp_path):
    original, prior, approval, ledger = setup(tmp_path)
    grant = PromptAllowance(approval, path=ledger, original=original.path, prior=prior)
    arm = next(iter(load_prompt_comparison()["arms"]))
    grant.reserve("spent", arm)
    grant.settle(arm, 1)
    ledger.unlink()
    with pytest.raises(ValueError):
        PromptAllowance(approval, path=ledger, original=original.path, prior=prior)
    assert not ledger.exists() and grant.marker.is_file()


def test_modified_receipt_rejects_existing_grant(tmp_path):
    original, prior, approval, ledger = setup(tmp_path)
    grant = PromptAllowance(approval, path=ledger, original=original.path, prior=prior)
    receipt = json.loads(approval.read_text())
    receipt["maximum_outbound_attempts"] = 7
    approval.write_text(json.dumps(receipt))
    with pytest.raises(ValueError):
        grant.reserve("blocked", next(iter(load_prompt_comparison()["arms"])))


def test_simultaneous_reservations_cannot_both_fund_the_same_arm(tmp_path):
    original, prior, approval, ledger = setup(tmp_path)
    grant = PromptAllowance(approval, path=ledger, original=original.path, prior=prior)
    arm = next(iter(load_prompt_comparison()["arms"]))

    def reserve(run):
        try:
            grant.reserve(run, arm)
            return True
        except ValueError:
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(reserve, ["first", "second"])) == [False, True]
    assert grant.used == 1
