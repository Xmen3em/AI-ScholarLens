import json
from pathlib import Path
from unittest.mock import Mock

import pytest
import src.commands.compare_hf_routes as command
from src.commands.hf_allowance import PilotAllowance

from tests.unit.test_hf_allowance import seed
from tests.unit.test_hf_client import settings


def arguments(tmp_path, monkeypatch, *, execute):
    root = Path("tests/test_output/week7-source-review-20261013-01")
    # Command output checks stay enabled; tmp_path is under the test-owned ignored basetemp.
    output = tmp_path / "comparison"
    args = ["compare", "--snapshot", str(root), "--output", str(output)]
    if execute:
        args.append("--execute")
    monkeypatch.setattr("sys.argv", args)
    return root, output


def test_offline_command_does_not_read_credentials_or_create_paid_allowance(tmp_path, monkeypatch):
    _, output = arguments(tmp_path, monkeypatch, execute=False)
    monkeypatch.setattr(command, "Settings", Mock(side_effect=AssertionError("Credentials accessed")))
    monkeypatch.setattr(command, "public_mapping", Mock(side_effect=AssertionError("Network accessed")))
    monkeypatch.setattr(command, "PilotAllowance", Mock(side_effect=AssertionError("Allowance accessed")))
    command.main()
    metadata = json.loads((output / "metadata.json").read_text())
    assert not metadata["inference_started"] and metadata["outbound_budget"] == 2


def test_one_remaining_slot_cannot_start_partial_paired_experiment(tmp_path, monkeypatch):
    root, output = arguments(tmp_path, monkeypatch, execute=True)
    grant, prior = seed(tmp_path)
    grant.reserve("historical", 10)
    grant.settle("historical", 10)
    real_settings = settings()
    settings_factory = Mock(return_value=real_settings)
    settings_factory.model_validate = lambda value: real_settings
    monkeypatch.setattr(command, "Settings", settings_factory)
    monkeypatch.setattr(command, "free_memory_mib", lambda: 4096)
    state = json.loads((root / "state.json").read_text())
    monkeypatch.setattr(command, "live_snapshot", lambda settings: (state, [], []))
    monkeypatch.setattr(command, "provider_available", lambda model: {})
    monkeypatch.setattr(command, "public_mapping", lambda: {})
    monkeypatch.setattr(command, "PilotAllowance", lambda: PilotAllowance(grant.path, prior=prior))
    inference = Mock(side_effect=AssertionError("Unfunded inference started"))
    monkeypatch.setattr(command, "compare_routes", inference)
    command.main()
    inference.assert_not_called()
    metadata = json.loads((output / "metadata.json").read_text())
    assert metadata["status"] == "not_started" and metadata["inference_started"] is False
    # The unspent single-slot reservation was settled at zero, rather than charged or reset.
    assert grant.reserve("later", 2) == 1
