import json
from pathlib import Path
from unittest.mock import Mock

import pytest
import src.commands.compare_hf_prompts as command
from src.commands.hf_prompt_allowance import PromptAllowance

from tests.unit.test_hf_client import settings
from tests.unit.test_hf_prompt_allowance import setup


def arguments(tmp_path, monkeypatch, *extra):
    snapshot = Path("tests/test_output/week7-source-review-20261013-01")
    output = tmp_path / "comparison"
    monkeypatch.setattr("sys.argv", ["compare", "--snapshot", str(snapshot), "--output", str(output), *extra])
    return snapshot, output


def test_offline_default_never_reads_credentials_or_allowance(tmp_path, monkeypatch):
    _, output = arguments(tmp_path, monkeypatch)
    for name in ("Settings", "PromptAllowance", "approval_proposal", "provider_available", "live_snapshot", "reproduce"):
        monkeypatch.setattr(command, name, Mock(side_effect=AssertionError("offline execution")))
    command.main()
    metadata = json.loads((output / "metadata.json").read_text())
    assert metadata["proposed_outbound_budget"] == 6 and metadata["approved_outbound_budget"] == 0
    assert not metadata["paper_collection_planned"] and not metadata["inference_started"]


def test_pending_proposal_is_read_only_and_cannot_execute(tmp_path, monkeypatch):
    original, prior, approval, ledger = setup(tmp_path, approved=False)
    snapshot, output = arguments(tmp_path, monkeypatch, "--execute", "--approval", str(approval))
    before = original.path.read_bytes()
    monkeypatch.setattr(command, "PromptAllowance", lambda receipt: PromptAllowance(receipt, path=ledger, original=original.path, prior=prior))
    monkeypatch.setattr(command, "Settings", Mock(side_effect=AssertionError("credential read before approval")))
    command.main()
    assert json.loads((output / "metadata.json").read_text())["reason"] == "approval_required"
    assert not ledger.exists() and original.path.read_bytes() == before


@pytest.mark.parametrize("failure", [None, "timeout", "uncertain", "provider_json_validation", "memory"])
def test_approved_mocked_run_obeys_caps_stop_rules_and_never_qualifies(tmp_path, monkeypatch, failure):
    original, prior, approval, ledger = setup(tmp_path)
    snapshot, output = arguments(tmp_path, monkeypatch, "--execute", "--approval", str(approval))
    factory = Mock(return_value=settings())
    factory.model_validate = lambda values: settings()
    monkeypatch.setattr(command, "Settings", factory)
    monkeypatch.setattr(command, "free_memory_mib", lambda: 1023 if failure == "memory" else 4096)
    state = json.loads((snapshot / "state.json").read_text())
    monkeypatch.setattr(command, "live_snapshot", lambda config: (state, [], []))
    monkeypatch.setattr(command, "provider_available", lambda model: {})
    monkeypatch.setattr(command, "PromptAllowance", lambda receipt: PromptAllowance(receipt, path=ledger, original=original.path, prior=prior))
    calls = []

    async def synthetic(config, arm, *, experiment):
        calls.append(arm)
        if failure == "uncertain":
            raise RuntimeError("private exception message")
        return {"arm": arm, "category": failure or "passed", "qualification_accepted": False,
                "outbound_attempts": 1, "work": {"usage_complete": failure is None},
                "calls": [{"provider_status": 400}] if failure == "provider_json_validation" else []}

    monkeypatch.setattr(command, "reproduce", synthetic)
    command.main()
    if failure == "memory":
        assert not calls and json.loads((output / "metadata.json").read_text())["reason"] == "insufficient_memory"
        return
    result = json.loads((output / "comparison.json").read_text())
    assert result["qualification_accepted"] is False and all(result["preservation"].values())
    assert "private exception message" not in json.dumps(result)
    assert len(calls) == (1 if failure in {"timeout", "uncertain"} else 6)
    assert all(value == (failure is None) for value in result["pair_passed"].values())
    grant = PromptAllowance(approval, path=ledger, original=original.path, prior=prior)
    assert grant.used == len(calls)


def test_mutually_exclusive_execution_and_proposal_flags(tmp_path, monkeypatch):
    arguments(tmp_path, monkeypatch, "--execute", "--propose-approval")
    with pytest.raises(SystemExit):
        command.main()


def test_missing_approval_never_reads_private_settings(tmp_path, monkeypatch):
    _, output = arguments(tmp_path, monkeypatch, "--execute")
    monkeypatch.setattr(command, "Settings", Mock(side_effect=AssertionError("private settings read")))
    command.main()
    assert json.loads((output / "metadata.json").read_text())["reason"] == "approval_required"


@pytest.mark.anyio
@pytest.mark.parametrize("status", [401, 402, 429, 503])
async def test_non400_provider_error_stops_even_with_json_validation_label(tmp_path, monkeypatch, status):
    original, prior, approval, ledger = setup(tmp_path)
    grant = PromptAllowance(approval, path=ledger, original=original.path, prior=prior)
    calls = []
    monkeypatch.setattr(command, "free_memory_mib", lambda: 4096)

    async def synthetic(config, arm, *, experiment):
        calls.append(arm)
        return {"arm": arm, "category": "provider_json_validation", "outbound_attempts": 1,
                "calls": [{"provider_status": status}], "qualification_accepted": False}

    monkeypatch.setattr(command, "reproduce", synthetic)
    arms = ["concise-positive", "concise-negative"]
    result = await command.collect(settings(), arms, grant, tmp_path, command.source_hashes())
    assert len(calls) == 1 and result["status"] == "stopped" and grant.used == 1
