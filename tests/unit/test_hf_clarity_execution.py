import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import pytest
from src.commands.hf_clarity_allowance import ClarityAllowance, approval_proposal
from src.commands.hf_clarity_execution import load_execution
from src.commands.hf_fixture_clarity import load_clarity
from src.commands.hf_prompt_allowance import PromptAllowance
from src.commands.hf_reproduction import load_experiment, load_prompt_comparison, reproduce

from tests.unit.test_hf_client import envelope, settings
from tests.unit.test_hf_prompt_allowance import setup as prompt_setup


def setup(tmp_path, *, approved=True):
    (tmp_path / "old").mkdir(parents=True)
    original, prior, old_approval, old_path = prompt_setup(tmp_path / "old")
    old = PromptAllowance(old_approval, path=old_path, original=original.path, prior=prior)
    for arm in load_prompt_comparison()["arms"]:
        old.reserve("old-" + arm, arm)
        old.settle(arm, 1)
    parents = {"original": original.path, "prior": prior, "prompt_path": old_path, "prompt_approval": old_approval}
    receipt = approval_proposal(**parents)
    if approved:
        receipt.update(status="approved", authorization_source="explicit_user_approval")
    approval = tmp_path / "clarity-approval.json"
    approval.write_text(json.dumps(receipt))
    return approval, {**parents, "path": tmp_path / "clarity.sqlite3"}


def test_new_execution_contract_references_unchanged_offline_requests():
    profile = load_execution()
    clarity = load_clarity()
    assert profile["maximum_outbound_attempts"] == 2
    assert profile["arms"] == clarity["arms"]
    assert profile["candidate_manifest_sha256"] == clarity["manifest_sha256"]
    assert load_experiment("clarity-execution-v1")["manifest_sha256"] == profile["manifest_sha256"]
    with pytest.raises(ValueError):
        load_experiment("fixture-clarity-v1")


@pytest.mark.parametrize("name", ["manifest.json", "profile.json", "PROTOCOL.md"])
def test_changed_execution_freeze_fails_closed(tmp_path, name):
    for path in Path("evaluation/week7_hf/clarity-execution-v1").iterdir():
        (tmp_path / path.name).write_bytes(path.read_bytes())
    (tmp_path / name).write_bytes(b"{}")
    with pytest.raises(ValueError):
        load_execution(tmp_path)


def test_pending_proposal_cannot_initialize_extension_or_change_closed_parents(tmp_path):
    approval, paths = setup(tmp_path, approved=False)
    before = {name: paths[name].read_bytes() for name in ("original", "prompt_path", "prompt_approval")}
    with pytest.raises(ValueError):
        ClarityAllowance(approval, **paths)
    assert not paths["path"].exists()
    assert all(paths[name].read_bytes() == value for name, value in before.items())


@pytest.mark.parametrize(
    "field,value",
    [
        ("maximum_outbound_attempts", 3),
        ("maximum_outbound_attempts", True),
        ("model", "other:provider"),
        ("endpoint", "https://evil.invalid"),
        ("authorization_source", None),
        ("paper_data_sent", True),
        ("paper_data_sent", 0),
        ("manifest_sha256", "0" * 64),
        ("prompt_allowance_binding", "0" * 64),
    ],
)
def test_exact_approval_scope_cannot_expand_or_change(tmp_path, field, value):
    approval, paths = setup(tmp_path)
    receipt = json.loads(approval.read_text())
    receipt[field] = value
    approval.write_text(json.dumps(receipt))
    with pytest.raises(ValueError):
        ClarityAllowance(approval, **paths)
    assert not paths["path"].exists()


def test_two_arm_grant_survives_restart_without_repeats_or_parent_mutation(tmp_path):
    approval, paths = setup(tmp_path)
    before = {name: paths[name].read_bytes() for name in ("original", "prompt_path", "prompt_approval")}
    grant = ClarityAllowance(approval, **paths)
    for arm in load_execution()["arms"]:
        grant.reserve("run-" + arm, arm)
        grant.settle(arm, 1)
    fresh = ClarityAllowance(approval, **paths)
    assert fresh.used == 2
    for arm in load_execution()["arms"]:
        with pytest.raises(ValueError):
            fresh.reserve("fresh-folder", arm)
    assert all(paths[name].read_bytes() == value for name, value in before.items())


def test_unknown_work_consumes_arm_and_cannot_be_settled_or_reserved_twice(tmp_path):
    approval, paths = setup(tmp_path)
    grant = ClarityAllowance(approval, **paths)
    grant.reserve("unknown", "clarity-positive")
    assert grant.used == 1
    grant.settle("clarity-positive", None)
    with pytest.raises(ValueError):
        grant.settle("clarity-positive", 0)
    with pytest.raises(ValueError):
        grant.reserve("retry", "clarity-positive")


@pytest.mark.parametrize("which", ["ledger", "marker", "original", "prompt_path", "prompt_approval"])
def test_missing_retained_registration_parent_or_receipt_never_reconstructs_it(tmp_path, which):
    approval, paths = setup(tmp_path)
    grant = ClarityAllowance(approval, **paths)
    missing = grant.path if which == "ledger" else grant.marker if which == "marker" else paths[which]
    missing.unlink()
    with pytest.raises((ValueError, OSError, sqlite3.Error)):
        ClarityAllowance(approval, **paths)
    assert not missing.exists()


@pytest.mark.parametrize("which", ["original", "prompt_path", "prompt_approval"])
def test_changed_parent_blocks_next_arm(tmp_path, which):
    approval, paths = setup(tmp_path)
    grant = ClarityAllowance(approval, **paths)
    if which == "prompt_approval":
        receipt = json.loads(paths[which].read_text())
        receipt["maximum_outbound_attempts"] = 7
        paths[which].write_text(json.dumps(receipt))
    else:
        with sqlite3.connect(paths[which]) as db:
            table = "reservations" if which == "original" else "arms"
            db.execute(f"UPDATE {table} SET run='tampered'")
    with pytest.raises(ValueError):
        grant.reserve("blocked", "clarity-positive")


def test_zero_attempt_still_cannot_repeat_an_admitted_arm(tmp_path):
    approval, paths = setup(tmp_path)
    grant = ClarityAllowance(approval, **paths)
    grant.reserve("pre-request-stop", "clarity-positive")
    grant.settle("clarity-positive", 0)
    assert grant.used == 0
    with pytest.raises(ValueError):
        grant.reserve("retry", "clarity-positive")


def test_parallel_reservations_cannot_fund_same_arm_twice(tmp_path):
    approval, paths = setup(tmp_path)
    grant = ClarityAllowance(approval, **paths)

    def reserve(name):
        try:
            grant.reserve(name, "clarity-positive")
            return True
        except ValueError:
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(reserve, ["first", "second"])) == [False, True]


@pytest.mark.anyio
@pytest.mark.parametrize("arm", ["clarity-positive", "clarity-negative"])
async def test_clarity_execution_sends_only_exact_public_payload_and_bounded_diagnostics(stub_httpx, tmp_path, arm):
    config = settings().model_copy(update={"api_rate_limit_path": str(tmp_path / "quotas.sqlite3")})
    case = load_execution()["arms"][arm]
    response = envelope(json.dumps(case["case"]["expected"]), usage={"prompt_tokens": 80, "completion_tokens": 12})
    response["choices"][0]["message"].update(
        reasoning="synthetic-private-reasoning", reasoning_content="synthetic-private-reasoning"
    )
    calls = stub_httpx(lambda request: httpx.Response(200, json=response))
    result = await reproduce(config, arm, experiment="clarity-execution-v1", memory=lambda: 4096)
    assert len(calls) == 1 and json.loads(calls[0].content) == case["payload"]
    assert result["category"] == "passed" and result["qualification_accepted"] is False
    assert result["decision_diagnostics"]["expected_match"] is True
    saved = json.dumps(result)
    for private in ("relevant_markers", "[1.1]", "synthetic-private-reasoning", "Authorization", "Neural AI retrieval"):
        assert private not in saved
    assert all("reasoning" not in call and "reasoning_content" not in call for call in result["calls"])


def test_changed_boolean_receipt_cannot_exploit_false_equals_zero(tmp_path):
    approval, paths = setup(tmp_path)
    grant = ClarityAllowance(approval, **paths)
    receipt = json.loads(approval.read_text())
    receipt["paper_data_sent"] = 0
    approval.write_text(json.dumps(receipt))
    with pytest.raises(ValueError):
        grant.reserve("blocked", "clarity-positive")


@pytest.mark.anyio
async def test_clarity_retains_original_expected_and_schema_guards(stub_httpx, tmp_path):
    config = settings().model_copy(update={"api_rate_limit_path": str(tmp_path / "quotas.sqlite3")})
    stub_httpx(lambda request: httpx.Response(200, json=envelope('{"relevant_markers":[]}')))
    result = await reproduce(config, "clarity-positive", experiment="clarity-execution-v1", memory=lambda: 4096)
    assert result["category"] == "expected_mismatch" and result["decision_diagnostics"]["missing_expected_marker_count"] == 1
