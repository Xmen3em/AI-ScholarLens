import json
from pathlib import Path
from unittest.mock import Mock

import pytest
import src.commands.diagnose_hf_structure as command
from src.commands.hf_allowance import PilotAllowance
from src.commands.hf_error_structure import load_structure_protocol

from tests.unit.test_hf_allowance import seed
from tests.unit.test_hf_client import settings


def arguments(tmp_path, monkeypatch, *, execute):
    root = Path("tests/test_output/week7-source-review-20261013-01")
    output = tmp_path / "diagnostic"
    args = ["diagnose", "--snapshot", str(root), "--output", str(output)]
    if execute:
        args.append("--execute")
    monkeypatch.setattr("sys.argv", args)
    return root, output


def test_frozen_profile_and_protocol_cannot_change_after_acceptance(tmp_path):
    profile = load_structure_protocol()
    assert profile["maximum_outbound_attempts"] == 1 and profile["qualification_accepted"] is False
    root = Path("evaluation/week7_hf/structure-diagnostic-v1")
    for file in root.iterdir():
        (tmp_path / file.name).write_bytes(file.read_bytes())
    (tmp_path / "PROTOCOL.md").write_text("changed contract")
    with pytest.raises(ValueError):
        load_structure_protocol(tmp_path)


def test_offline_plan_never_reads_settings_or_contacts_any_service(tmp_path, monkeypatch):
    _, output = arguments(tmp_path, monkeypatch, execute=False)
    for name in ("Settings", "PilotAllowance", "provider_available", "live_snapshot", "diagnose_structure"):
        monkeypatch.setattr(command, name, Mock(side_effect=AssertionError("Execution during offline plan")))
    command.main()
    metadata = json.loads((output / "metadata.json").read_text())
    assert metadata["outbound_budget"] == 1 and not metadata["inference_started"]
    assert metadata["kind"] == "error_structure_diagnostic_only"


@pytest.mark.parametrize("outbound", [0, 1, None])
def test_command_settles_actual_or_unknown_attempts_and_never_qualifies(tmp_path, monkeypatch, outbound):
    root, output = arguments(tmp_path, monkeypatch, execute=True)
    grant, prior = seed(tmp_path)
    config = settings()
    factory = Mock(return_value=config)
    factory.model_validate = lambda value: config
    monkeypatch.setattr(command, "Settings", factory)
    monkeypatch.setattr(command, "free_memory_mib", lambda: 4096)
    state = json.loads((root / "state.json").read_text())
    monkeypatch.setattr(command, "live_snapshot", lambda settings: (state, [], []))
    monkeypatch.setattr(command, "provider_available", lambda model: {})
    monkeypatch.setattr(command, "PilotAllowance", lambda: PilotAllowance(grant.path, prior=prior))

    async def synthetic(settings):
        if outbound is None:
            raise RuntimeError("private provider text")
        return {"kind": "error_structure_diagnostic_only", "qualification_accepted": False,
                "outbound_attempts": outbound, "qualification": {"checks": []}, "error_structure": None}

    monkeypatch.setattr(command, "diagnose_structure", synthetic)
    command.main()
    result = json.loads((output / "diagnostic.json").read_text())
    metadata = json.loads((output / "metadata.json").read_text())
    assert result["qualification_accepted"] is False and all(result["preservation"].values())
    assert metadata["inference_started"] is (None if outbound is None else outbound == 1)
    assert "private provider text" not in json.dumps(result)
    assert grant.reserve("later", 11) == (11 if outbound == 0 else 10)


def test_exhausted_allowance_stops_before_inference_without_creating_a_new_budget(tmp_path, monkeypatch):
    root, output = arguments(tmp_path, monkeypatch, execute=True)
    grant, prior = seed(tmp_path)
    grant.reserve("already_used", 11)
    grant.settle("already_used", 11)
    config = settings()
    factory = Mock(return_value=config)
    factory.model_validate = lambda value: config
    monkeypatch.setattr(command, "Settings", factory)
    monkeypatch.setattr(command, "free_memory_mib", lambda: 4096)
    state = json.loads((root / "state.json").read_text())
    monkeypatch.setattr(command, "live_snapshot", lambda settings: (state, [], []))
    monkeypatch.setattr(command, "provider_available", lambda model: {})
    monkeypatch.setattr(command, "PilotAllowance", lambda: PilotAllowance(grant.path, prior=prior))
    inference = Mock(side_effect=AssertionError("Unfunded inference"))
    monkeypatch.setattr(command, "diagnose_structure", inference)
    command.main()
    inference.assert_not_called()
    metadata = json.loads((output / "metadata.json").read_text())
    assert metadata["status"] == "not_started" and metadata["inference_started"] is False
