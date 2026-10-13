import json
from pathlib import Path
from unittest.mock import Mock

import pytest
import src.commands.reproduce_hf_groq as command
from src.commands.hf_allowance import PilotAllowance

from tests.unit.test_hf_allowance import seed
from tests.unit.test_hf_client import settings


def arguments(tmp_path, monkeypatch, execute=False):
    root = Path("tests/test_output/week7-source-review-20261013-01")
    output = tmp_path / "reproduction"
    argv = ["reproduce", "--snapshot", str(root), "--output", str(output), "--arm", "exact-relevance-512"]
    if execute:
        argv.append("--execute")
    monkeypatch.setattr("sys.argv", argv)
    return root, output


def test_offline_never_reads_credentials_allowance_or_services(tmp_path, monkeypatch):
    _, output = arguments(tmp_path, monkeypatch)
    for name in ("Settings", "PilotAllowance", "live_snapshot", "provider_available", "reproduce"):
        monkeypatch.setattr(command, name, Mock(side_effect=AssertionError("unexpected execution")))
    command.main()
    metadata = json.loads((output / "metadata.json").read_text())
    assert metadata["outbound_budget"] == 1 and metadata["arm"] == "exact-relevance-512"
    assert metadata["qualification_accepted"] is False and not metadata["inference_started"]


@pytest.mark.parametrize("outbound", [0, 1, None])
def test_actual_or_uncertain_settlement_cannot_reset_allowance(tmp_path, monkeypatch, outbound):
    root, output = arguments(tmp_path, monkeypatch, True)
    grant, prior = seed(tmp_path)
    factory = Mock(return_value=settings())
    factory.model_validate = lambda value: settings()
    monkeypatch.setattr(command, "Settings", factory)
    monkeypatch.setattr(command, "free_memory_mib", lambda: 4096)
    state = json.loads((root / "state.json").read_text())
    monkeypatch.setattr(command, "live_snapshot", lambda settings: (state, [], []))
    monkeypatch.setattr(command, "provider_available", lambda model: {})
    monkeypatch.setattr(command, "ALLOWANCE_PATH", grant.path)
    monkeypatch.setattr(command, "PilotAllowance", lambda: PilotAllowance(grant.path, prior=prior))

    async def synthetic(settings, arm):
        if outbound is None:
            raise RuntimeError("private exception message")
        return {"category": "passed", "qualification_accepted": False, "outbound_attempts": outbound}

    monkeypatch.setattr(command, "reproduce", synthetic)
    command.main()
    result = json.loads((output / "diagnostic.json").read_text())
    assert all(result["preservation"].values()) and result["qualification_accepted"] is False
    assert "private exception message" not in json.dumps(result)
    assert grant.reserve("later", 11) == (11 if outbound == 0 else 10)


@pytest.mark.parametrize("problem", ["memory", "missing_allowance", "exhausted"])
def test_preflight_problem_prevents_inference_and_new_allowance(tmp_path, monkeypatch, problem):
    root, output = arguments(tmp_path, monkeypatch, True)
    grant, prior = seed(tmp_path)
    if problem == "exhausted":
        grant.reserve("used", 11)
        grant.settle("used", 11)
    factory = Mock(return_value=settings())
    factory.model_validate = lambda value: settings()
    monkeypatch.setattr(command, "Settings", factory)
    monkeypatch.setattr(command, "free_memory_mib", lambda: 1023 if problem == "memory" else 4096)
    state = json.loads((root / "state.json").read_text())
    monkeypatch.setattr(command, "live_snapshot", lambda settings: (state, [], []))
    monkeypatch.setattr(command, "provider_available", lambda model: {})
    monkeypatch.setattr(command, "ALLOWANCE_PATH", tmp_path / "missing.db" if problem == "missing_allowance" else grant.path)
    monkeypatch.setattr(command, "PilotAllowance", lambda: PilotAllowance(grant.path, prior=prior))
    inference = Mock(side_effect=AssertionError("unadmitted inference"))
    monkeypatch.setattr(command, "reproduce", inference)
    command.main()
    inference.assert_not_called()
    assert json.loads((output / "metadata.json").read_text())["status"] == "not_started"
    assert not (tmp_path / "missing.db").exists()
