import json
from pathlib import Path
from unittest.mock import Mock

import httpx
import pytest
from src.commands import qualify_hf_schema as command
from src.commands.hf_cerebras_allowance import CerebrasAllowance
from src.commands.hf_cerebras_selectors import SelectorAllowance, approval_proposal
from src.commands.hf_schema_execution import load_cerebras, load_execution, load_selectors

from tests.unit.test_hf_cerebras_remaining import setup as controller_setup
from tests.unit.test_hf_client import envelope, settings
from tests.unit.test_hf_schema_command import arguments


def setup(tmp_path, *, approved=True):
    controller_approval, paths = controller_setup(tmp_path / "old")
    grant = CerebrasAllowance(controller_approval, **paths)
    run = tmp_path / "controller-success"
    run.mkdir()
    for arm in load_cerebras()["arms"]:
        grant.reserve(str(run.resolve()), arm); grant.settle(arm, 1)
    profile = load_cerebras()
    metadata = {"kind": profile["kind"], "status": "schema_qualification_completed", "approval_sha256": grant.signature}
    checks = [{"id": case["id"], "ok": True, "schema_sha256": command.digest(case["schema"]),
               "fixture_sha256": command.digest(case), "work": {"usage_complete": True, "schema_violations": 0}}
              for case in profile["cases"]]
    for check in checks:
        check["calls"] = [{"model": profile["model"], "outbound_attempts": 1, "schema_valid": True}]
    result = {"diagnostic_passed": True, "schema_qualified": False, "app_accepted": False, "outbound_attempts": 3,
              "schema_execution_manifest_sha256": profile["manifest_sha256"],
              "qualification": {"fixture_manifest_sha256": profile["qualification_manifest_sha256"], "checks": checks},
              "preservation": dict.fromkeys(["source_unchanged", "frozen_labels_unchanged", "corpus_unchanged", "models_unchanged"], True)}
    (run / "metadata.json").write_text(json.dumps(metadata));(run / "qualification.json").write_text(json.dumps(result))
    parents = {key: value for key, value in paths.items() if key not in {"path", "allocation"}}
    parents.update(controller_path=paths["path"], controller_approval=controller_approval,
                   allocation=paths["allocation"], controller_run=run)
    receipt = approval_proposal(**parents)
    if approved:
        receipt.update(status="approved", authorization_source="explicit_user_approval")
    approval = tmp_path / "selector-approval.json"
    approval.write_text(json.dumps(receipt))
    return approval, {**parents, "path": tmp_path / "selectors.sqlite3"}


def test_selectors_keep_original_last_two_cases_and_controls():
    profile = load_selectors();original = load_execution()
    assert profile["cases"] == original["cases"][3:]
    assert profile["arms"] == ["selector-1", "selector-10"] and profile["maximum_outbound_attempts"] == 2
    assert profile["payloads"] == [{**payload, "model": profile["model"]} for payload in original["payloads"][3:]]


def test_pending_selectors_need_new_funds_and_never_spend_old_controller_counter(tmp_path):
    approval, paths = setup(tmp_path, approved=False)
    before = paths["controller_path"].read_bytes()
    with pytest.raises(ValueError):
        SelectorAllowance(approval, **paths)
    assert not paths["path"].exists() and paths["controller_path"].read_bytes() == before


def test_selector_budget_survives_restart_and_changed_controller_proof_blocks_reservation(tmp_path):
    approval, paths = setup(tmp_path)
    grant = SelectorAllowance(approval, **paths)
    for arm in load_selectors()["arms"]:
        grant.reserve("selectors", arm);grant.settle(arm, 1)
    assert SelectorAllowance(approval, **paths).used == 2
    with pytest.raises(ValueError):
        grant.reserve("new-directory", "selector-1")
    proof = paths["controller_run"] / "qualification.json"
    proof.write_text(proof.read_text() + " ")
    with pytest.raises(ValueError):
        SelectorAllowance(approval, **paths)


@pytest.mark.anyio
@pytest.mark.parametrize("failure", [None, "400", "semantic", "timeout"])
async def test_selector_pair_exact_payloads_patterns_failure_stops_and_no_app_acceptance(tmp_path, stub_httpx, monkeypatch, failure):
    approval, paths = setup(tmp_path)
    grant = SelectorAllowance(approval, **paths)
    profile = load_selectors()
    config = settings().model_copy(update={"hf_models": [profile["model"]], "hf_default_model": profile["model"],
                                         "api_rate_limit_path": str(tmp_path / "quotas.sqlite3")})
    monkeypatch.setattr(command, "source_hashes", lambda: {})
    bodies = []

    def answer(request):
        index = len(bodies);bodies.append(json.loads(request.content))
        if failure == "400":
            return httpx.Response(400, json={"error": {"code": "json_validate_failed", "type": "invalid_request_error"}})
        if failure == "timeout":
            raise httpx.ReadTimeout("private timeout", request=request)
        expected = {"answer": "NONE"} if failure == "semantic" else profile["cases"][index]["expected"]
        return httpx.Response(200, json=envelope(json.dumps(expected), usage={"prompt_tokens": 100, "completion_tokens": 20}))

    stub_httpx(answer)
    result = await command.collect(config, grant, tmp_path, {}, memory=lambda: 4096, experiment="cerebras-selectors-v1")
    assert result["qualification"]["qualified"] is result["app_accepted"] is False
    assert result["diagnostic_passed"] == (failure is None)
    assert len(bodies) == grant.used == (2 if failure is None else 1)
    assert bodies == profile["payloads"][:len(bodies)]
    assert "private" not in json.dumps(result)


def test_selector_default_plan_has_no_private_or_funding_access(tmp_path, monkeypatch):
    _, output = arguments(tmp_path, monkeypatch, "--experiment", "cerebras-selectors-v1")
    for name in ["Settings", "SelectorAllowance", "selector_proposal", "provider_available", "live_snapshot"]:
        monkeypatch.setattr(command, name, Mock(side_effect=AssertionError("Offline access")))
    command.main()
    metadata = json.loads((output / "metadata.json").read_text())
    assert metadata["outbound_budget"] == 0 and metadata["proposed_outbound_budget"] == 2


def test_pending_selector_execution_blocks_before_credentials_and_funding(tmp_path, monkeypatch):
    approval, paths = setup(tmp_path, approved=False)
    _, output = arguments(tmp_path, monkeypatch, "--experiment", "cerebras-selectors-v1", "--execute", "--approval", str(approval))
    monkeypatch.setattr(command, "SelectorAllowance", lambda receipt: SelectorAllowance(receipt, **paths))
    monkeypatch.setattr(command, "Settings", Mock(side_effect=AssertionError("Unapproved credentials read")))
    command.main()
    assert json.loads((output / "metadata.json").read_text())["reason"] == "approval_required"
    assert not paths["path"].exists()
