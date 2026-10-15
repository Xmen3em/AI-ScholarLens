import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from src.commands import compare_hf_clarity as command
from src.commands import compare_hf_prompts as shared
from src.commands.hf_clarity_allowance import ClarityAllowance

from tests.unit.test_hf_clarity_execution import setup
from tests.unit.test_hf_client import settings


def arguments(tmp_path, monkeypatch, *extra):
    snapshot = Path("tests/test_output/week7-source-review-20261013-01")
    output = tmp_path / "clarity-comparison"
    monkeypatch.setattr("sys.argv", ["compare_hf_clarity", "--snapshot", str(snapshot), "--output", str(output), *extra])
    return snapshot, output


def test_default_clarity_plan_never_reads_credentials_or_allowances(monkeypatch, tmp_path):
    _, output = arguments(tmp_path, monkeypatch)
    for name in ("Settings", "ClarityAllowance", "approval_proposal", "provider_available", "live_snapshot"):
        monkeypatch.setattr(command, name, Mock(side_effect=AssertionError("Offline plan read credentials/service/allowance")))
    command.main()
    metadata = json.loads((output / "metadata.json").read_text())
    assert metadata["approved_outbound_budget"] == metadata["outbound_budget"] == 0
    assert metadata["proposed_outbound_budget"] == 2
    assert metadata["qualification_accepted"] is metadata["paper_collection_planned"] is False


def test_proposal_reads_closed_parent_evidence_but_never_initializes_funding(monkeypatch, tmp_path):
    approval, paths = setup(tmp_path, approved=False)
    _, output = arguments(tmp_path, monkeypatch, "--propose-approval")
    from src.commands.hf_clarity_allowance import approval_proposal

    parents = {key: value for key, value in paths.items() if key != "path"}
    monkeypatch.setattr(command, "approval_proposal", lambda: approval_proposal(**parents))
    monkeypatch.setattr(command, "Settings", Mock(side_effect=AssertionError("Proposal read credentials")))
    monkeypatch.setattr(command, "ClarityAllowance", Mock(side_effect=AssertionError("Proposal funded a grant")))
    before = paths["original"].read_bytes(), paths["prompt_path"].read_bytes()
    command.main()
    result = json.loads((output / "proposed-approval.json").read_text())
    assert result["status"] == "pending_user_approval" and result["maximum_outbound_attempts"] == 2
    assert not paths["path"].exists()
    assert (paths["original"].read_bytes(), paths["prompt_path"].read_bytes()) == before


@pytest.mark.parametrize("missing", [True, False])
def test_pending_or_missing_approval_blocks_before_settings_and_network(monkeypatch, tmp_path, missing):
    approval, paths = setup(tmp_path, approved=False)
    extra = ["--execute"] + ([] if missing else ["--approval", str(approval)])
    _, output = arguments(tmp_path, monkeypatch, *extra)
    monkeypatch.setattr(command, "ClarityAllowance", lambda receipt: ClarityAllowance(receipt, **paths))
    monkeypatch.setattr(command, "Settings", Mock(side_effect=AssertionError("Unapproved settings read")))
    command.main()
    assert json.loads((output / "metadata.json").read_text())["reason"] == "approval_required"
    assert not paths["path"].exists()


@pytest.mark.parametrize("failure", [None, "timeout", "uncertain", "provider400", "provider429", "memory", "preservation"])
def test_approved_mocked_two_case_run_obeys_caps_stops_and_never_qualifies(monkeypatch, tmp_path, failure):
    approval, paths = setup(tmp_path)
    snapshot, output = arguments(tmp_path, monkeypatch, "--execute", "--approval", str(approval))
    factory = Mock(return_value=settings())
    factory.model_validate = lambda values: settings()
    monkeypatch.setattr(command, "Settings", factory)
    monkeypatch.setattr(command, "ClarityAllowance", lambda receipt: ClarityAllowance(receipt, **paths))
    monkeypatch.setattr(command, "free_memory_mib", lambda: 1023 if failure == "memory" else 4096)
    monkeypatch.setattr(shared, "free_memory_mib", lambda: 4096)
    state = json.loads((snapshot / "state.json").read_text())
    reads = []

    def live(config):
        reads.append(True)
        return ({"changed": True} if failure == "preservation" and len(reads) > 1 else state, [], [])

    monkeypatch.setattr(command, "live_snapshot", live)
    monkeypatch.setattr(command, "provider_available", lambda model: {})
    calls = []

    async def synthetic(config, arm, *, experiment):
        assert experiment == "clarity-execution-v1"
        calls.append(arm)
        if failure == "uncertain":
            raise RuntimeError("private provider error")
        category = (
            "provider_json_validation"
            if failure in {"provider400", "provider429"}
            else "timeout"
            if failure == "timeout"
            else "passed"
        )
        return {
            "arm": arm,
            "category": category,
            "qualification_accepted": False,
            "outbound_attempts": 1,
            "work": {"usage_complete": category == "passed"},
            "calls": [{"provider_status": 400 if failure == "provider400" else 429}]
            if category == "provider_json_validation"
            else [],
        }

    monkeypatch.setattr(shared, "reproduce", synthetic)
    command.main()
    if failure == "memory":
        assert not calls and json.loads((output / "metadata.json").read_text())["reason"] == "insufficient_memory"
        return
    result = json.loads((output / "comparison.json").read_text())
    assert len(calls) == (1 if failure in {"timeout", "uncertain", "provider429"} else 2)
    assert result["pair_passed"] == (failure is None)
    assert result["qualification_accepted"] is False
    assert "private provider error" not in json.dumps(result)
    assert result["original_attempts_used"] == 19
    assert ClarityAllowance(approval, **paths).used == len(calls)


def test_cannot_combine_proposal_and_execution(monkeypatch, tmp_path):
    arguments(tmp_path, monkeypatch, "--execute", "--propose-approval")
    with pytest.raises(SystemExit) as exc:
        command.main()
    assert exc.value.code == 2
