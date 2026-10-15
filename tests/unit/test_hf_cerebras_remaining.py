import json
from pathlib import Path

import httpx
import pytest
from src.commands import qualify_hf_schema as command
from src.commands.hf_cerebras_allowance import CerebrasAllowance, allocation_proposal, approval_proposal
from src.commands.hf_schema_allowance import SchemaAllowance
from src.commands.hf_schema_execution import load_cerebras, load_execution, measurement_profile

from tests.unit.test_hf_client import envelope, settings
from tests.unit.test_hf_provider_alternative import setup as stopped_setup


def setup(tmp_path, *, approved=True):
    _, old = stopped_setup(tmp_path / "old")
    parents = {key: value for key, value in old.items() if key != "path"}
    allocation = tmp_path / "allocation.json"
    allocation.write_text(json.dumps(allocation_proposal(**parents)))
    receipt = approval_proposal(**parents)
    if approved:
        receipt.update(status="approved", authorization_source="user_provider_instruction_with_remaining_approved_budget")
    approval = tmp_path / "cerebras-approval.json"
    approval.write_text(json.dumps(receipt))
    return approval, {**parents, "allocation": allocation, "path": tmp_path / "cerebras.sqlite3"}


def test_remaining_diagnostic_keeps_original_first_three_cases_and_full_qualification_gate():
    from src.commands.hf_evaluation import load_protocol

    original, candidate = load_execution(), load_cerebras()
    assert candidate["cases"] == original["cases"][:3]
    assert candidate["maximum_outbound_attempts"] == 3
    assert candidate["arms"] == ["scope", "relevance", "rewrite"]
    for first, second in zip(original["payloads"][:3], candidate["payloads"], strict=True):
        assert {**first, "model": candidate["model"]} == second
    measurement = measurement_profile("cerebras-remaining-v1")
    assert measurement["qualification_calls"] == 5
    assert measurement["prices_per_million"][candidate["model"]] == {"input": .35, "output": .75}
    assert candidate["model"] not in load_protocol()["prices_per_million"]


@pytest.mark.parametrize("name", ["manifest.json", "requests.json", "PROTOCOL.md"])
def test_changed_remaining_budget_freeze_rejected(tmp_path, name):
    for path in Path("evaluation/week7_hf/cerebras-remaining-v1").iterdir():
        (tmp_path / path.name).write_bytes(path.read_bytes())
    (tmp_path / name).write_bytes(b"{}")
    with pytest.raises(ValueError):
        load_cerebras(tmp_path)


def test_allocation_keeps_old_counter_readable_but_blocks_its_remaining_spending(tmp_path, monkeypatch):
    from src.commands import hf_schema_allowance as original

    approval, paths = setup(tmp_path)
    monkeypatch.setattr(original, "REALLOCATION_PATH", paths["allocation"])
    monkeypatch.setattr(original, "SCHEMA_ALLOWANCE_PATH", paths["stopped_path"])
    old_parents = {key: paths[key] for key in ["original", "prior", "prompt_path", "prompt_approval", "clarity_path", "clarity_approval", "clarity_run"]}
    old = SchemaAllowance(paths["stopped_approval"], path=paths["stopped_path"], **old_parents)
    before = old.path.read_bytes()
    assert old.used == 2
    with pytest.raises(ValueError):
        old.reserve("duplicate-budget", "rewrite")
    grant = CerebrasAllowance(approval, **paths)
    for arm in load_cerebras()["arms"]:
        grant.reserve("cerebras", arm); grant.settle(arm, 1)
    assert grant.used == 3 and old.path.read_bytes() == before
    with pytest.raises(ValueError):
        grant.reserve("fourth", "selector-1")


def test_reallocation_marker_does_not_close_unrelated_test_or_candidate_ledgers(tmp_path, monkeypatch):
    from src.commands import hf_schema_allowance as original

    from tests.unit.test_hf_schema_execution import setup as schema_setup

    approval, paths = schema_setup(tmp_path)
    marker = tmp_path / "other-allocation.json"
    marker.write_text("{}")
    monkeypatch.setattr(original, "REALLOCATION_PATH", marker)
    grant = SchemaAllowance(approval, **paths)
    grant.reserve("independent", "scope")
    assert grant.used == 1


@pytest.mark.parametrize("failure", ["missing_allocation", "changed_allocation", "new_budget", "wrong_authority", "pending"])
def test_remaining_budget_cannot_expand_or_fund_without_exact_model_instruction(tmp_path, failure):
    approval, paths = setup(tmp_path, approved=failure != "pending")
    if failure == "missing_allocation":
        paths["allocation"].unlink()
    elif failure == "changed_allocation":
        paths["allocation"].write_text("{}")
    elif failure in {"new_budget", "wrong_authority"}:
        receipt = json.loads(approval.read_text())
        receipt["maximum_outbound_attempts" if failure == "new_budget" else "authorization_source"] = 5 if failure == "new_budget" else "explicit_user_approval"
        approval.write_text(json.dumps(receipt))
    with pytest.raises((ValueError, OSError)):
        CerebrasAllowance(approval, **paths)
    assert not paths["path"].exists()


@pytest.mark.anyio
@pytest.mark.parametrize("failure", [None, "relevance400", "semantic", "timeout"])
async def test_three_call_cerebras_diagnostic_is_never_full_qualification(tmp_path, stub_httpx, monkeypatch, failure):
    approval, paths = setup(tmp_path)
    grant = CerebrasAllowance(approval, **paths)
    profile = load_cerebras()
    config = settings().model_copy(update={"hf_models": [profile["model"]], "hf_default_model": profile["model"],
                                         "api_rate_limit_path": str(tmp_path / "quotas.sqlite3")})
    monkeypatch.setattr(command, "source_hashes", lambda: {})
    bodies = []

    def answer(request):
        index = len(bodies); bodies.append(json.loads(request.content))
        if failure == "timeout":
            raise httpx.ReadTimeout("private timeout", request=request)
        if failure == "relevance400" and index == 1:
            return httpx.Response(400, json={"error": {"code": "json_validate_failed", "type": "invalid_request_error"}})
        expected = profile["cases"][index]["expected"] or {"query": "neural retrieval"}
        if failure == "semantic" and index == 1:
            expected = {"relevant_markers": []}
        return httpx.Response(200, json=envelope(json.dumps(expected), usage={"prompt_tokens": 100, "completion_tokens": 20}))

    stub_httpx(answer)
    result = await command.collect(config, grant, tmp_path, {}, memory=lambda: 4096, experiment="cerebras-remaining-v1")
    assert result["qualification"]["qualified"] is result["app_accepted"] is False
    assert result["diagnostic_passed"] == (failure is None)
    assert grant.used == len(bodies) == (3 if failure is None else 1 if failure == "timeout" else 2)
    assert bodies == profile["payloads"][:len(bodies)]
    assert "private" not in json.dumps(result)
