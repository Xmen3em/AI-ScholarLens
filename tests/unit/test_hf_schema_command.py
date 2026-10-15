import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from src.commands import qualify_hf_schema as command
from src.commands.hf_schema_allowance import SchemaAllowance

from tests.unit.test_hf_client import settings
from tests.unit.test_hf_schema_execution import setup


def arguments(tmp_path, monkeypatch, *extra):
    snapshot = Path("tests/test_output/week7-source-review-20261013-01")
    output = tmp_path / "schema-qualification"
    monkeypatch.setattr("sys.argv", ["qualify_hf_schema", "--snapshot", str(snapshot), "--output", str(output), *extra])
    return snapshot, output


def test_default_schema_plan_never_reads_credentials_funding_or_services(tmp_path, monkeypatch):
    _, output = arguments(tmp_path, monkeypatch)
    for name in ("Settings", "SchemaAllowance", "approval_proposal", "provider_available", "live_snapshot"):
        monkeypatch.setattr(command, name, Mock(side_effect=AssertionError("Offline plan accessed private/service state")))
    command.main()
    metadata = json.loads((output / "metadata.json").read_text())
    assert metadata["outbound_budget"] == metadata["approved_outbound_budget"] == 0
    assert metadata["proposed_outbound_budget"] == metadata["planned_outbound_budget"] == 5
    assert metadata["paper_collection_planned"] is metadata["app_accepted"] is False
    assert metadata["jobs"] == []


def test_schema_proposal_is_not_a_funded_or_executable_receipt(tmp_path, monkeypatch):
    from src.commands.hf_schema_allowance import approval_proposal

    approval, paths = setup(tmp_path, approved=False)
    _, output = arguments(tmp_path, monkeypatch, "--propose-approval")
    parents = {key: value for key, value in paths.items() if key != "path"}
    monkeypatch.setattr(command, "approval_proposal", lambda: approval_proposal(**parents))
    monkeypatch.setattr(command, "Settings", Mock(side_effect=AssertionError("Proposal read credentials")))
    monkeypatch.setattr(command, "SchemaAllowance", Mock(side_effect=AssertionError("Proposal initialized a counter")))
    command.main()
    result = json.loads((output / "proposed-approval.json").read_text())
    assert result == json.loads(approval.read_text())
    assert result["status"] == "pending_user_approval"
    assert not paths["path"].exists()


@pytest.mark.parametrize("missing", [True, False])
def test_unapproved_schema_execution_stops_before_credentials_or_network(tmp_path, monkeypatch, missing):
    approval, paths = setup(tmp_path, approved=False)
    extra = ["--execute"] + ([] if missing else ["--approval", str(approval)])
    _, output = arguments(tmp_path, monkeypatch, *extra)
    monkeypatch.setattr(command, "SchemaAllowance", lambda receipt: SchemaAllowance(receipt, **paths))
    monkeypatch.setattr(command, "Settings", Mock(side_effect=AssertionError("Unapproved private settings read")))
    command.main()
    assert json.loads((output / "metadata.json").read_text())["reason"] == "approval_required"
    assert not paths["path"].exists()


@pytest.mark.parametrize("failure", [None, "memory", "provider_preflight", "collection", "corpus", "source"])
def test_mocked_schema_execution_preserves_gates_and_never_accepts_application(tmp_path, monkeypatch, failure):
    approval, paths = setup(tmp_path)
    snapshot, output = arguments(tmp_path, monkeypatch, "--execute", "--approval", str(approval))
    factory = Mock(return_value=settings())
    factory.model_validate = lambda values: settings()
    monkeypatch.setattr(command, "Settings", factory)
    monkeypatch.setattr(command, "SchemaAllowance", lambda receipt: SchemaAllowance(receipt, **paths))
    monkeypatch.setattr(command, "free_memory_mib", lambda: 1023 if failure == "memory" else 4096)
    initial_source = command.source_hashes()
    monkeypatch.setattr(command, "source_hashes", lambda: {} if failure == "source" else initial_source)
    state = json.loads((snapshot / "state.json").read_text())
    reads = []

    def live(config):
        assert failure != "memory"
        reads.append(True)
        return ({"changed": True} if failure == "corpus" and len(reads) > 1 else state, [], [])

    monkeypatch.setattr(command, "live_snapshot", live)
    monkeypatch.setattr(command, "provider_available", Mock(side_effect=ValueError("private service error"))
                        if failure == "provider_preflight" else lambda model: {})
    calls = []

    async def synthetic(config, grant, directory, source):
        calls.append(True)
        if failure == "collection":
            grant.reserve(str(directory), "scope")
            raise RuntimeError("private uncertain response")
        for arm in command.load_execution()["arms"]:
            grant.reserve(str(directory), arm)
            grant.settle(arm, 1)
        return {"kind": "schema_qualification_only", "app_accepted": False,
                "qualification": {"qualified": True}, "outbound_attempts": 5}

    monkeypatch.setattr(command, "collect", synthetic)
    command.main()
    metadata = json.loads((output / "metadata.json").read_text())
    if failure in {"memory", "provider_preflight"}:
        assert not calls and metadata["status"] == "not_started"
        assert metadata["reason"] == ("insufficient_memory" if failure == "memory" else "preflight_failed")
        return
    result = json.loads((output / "qualification.json").read_text())
    assert result["schema_qualified"] == (failure is None)
    assert result["app_accepted"] is False and result["original_attempts_used"] == 21
    assert SchemaAllowance(approval, **paths).used == (1 if failure == "collection" else 5)
    assert "private" not in json.dumps(result)


def test_schema_proposal_and_execution_cannot_be_combined(tmp_path, monkeypatch):
    arguments(tmp_path, monkeypatch, "--propose-approval", "--execute")
    with pytest.raises(SystemExit) as exc:
        command.main()
    assert exc.value.code == 2
