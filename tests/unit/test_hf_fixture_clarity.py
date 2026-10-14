import copy
import json
import sqlite3
from pathlib import Path

import httpx
import pytest
from src.commands import hf_fixture_clarity as command
from src.commands.hf_qualification import load_revision
from src.commands.hf_reproduction import load_experiment, load_prompt_comparison
from src.config import Settings


def test_prospective_fixtures_change_only_question_and_keep_original_labels_local():
    profile = command.load_clarity()
    original = load_prompt_comparison()
    qualification = next(case for case in load_revision()["cases"] if case["id"] == "relevance")
    for polarity in ("positive", "negative"):
        case = profile["arms"]["clarity-" + polarity]
        baseline = original["arms"]["concise-" + polarity]
        data = json.loads(case["case"]["prompt"].split("\nData:\n")[1])
        old_data = json.loads(baseline["case"]["prompt"].split("\nData:\n")[1])
        assert data["question"] == "What kind of passages does neural AI retrieval select?"
        assert data["passages"] == old_data["passages"]
        assert case["case"]["prompt"].split("\nData:\n")[0] == qualification["prompt"].split("\nData:\n")[0]
        assert case["case"]["schema"] == qualification["schema"]
        assert case["case"]["expected"] == baseline["case"]["expected"]
        assert case["case"]["system"] == qualification["system"]
        expected = copy.deepcopy(baseline["payload"])
        expected["messages"][-1]["content"] = case["case"]["prompt"]
        assert case["payload"] == expected
        assert '"relevant_markers":' not in case["case"]["prompt"]
    # Prospective requests are deliberately unavailable to any existing live runner.
    with pytest.raises(ValueError):
        load_experiment("fixture-clarity-v1")


@pytest.mark.parametrize("name", ["manifest.json", "requests.json", "PROTOCOL.md"])
def test_frozen_fixture_changes_rejected(tmp_path, name):
    for path in Path("evaluation/week7_hf/fixture-clarity-v1").iterdir():
        (tmp_path / path.name).write_bytes(path.read_bytes())
    (tmp_path / name).write_bytes(b"{}")
    with pytest.raises(ValueError):
        command.load_clarity(tmp_path)


def test_offline_plan_never_reads_settings_or_contacts_a_service(monkeypatch, tmp_path):
    def forbidden(*args, **kwargs):
        raise AssertionError("Offline planning accessed credentials or network")

    monkeypatch.setattr(Settings, "__init__", forbidden)
    monkeypatch.setattr(httpx.Client, "request", forbidden)
    monkeypatch.setattr(httpx.AsyncClient, "request", forbidden)
    monkeypatch.setattr(sqlite3, "connect", forbidden)
    output = Path("tests/test_output") / tmp_path.parent.name / tmp_path.name / "clarity-plan"
    monkeypatch.setattr("sys.argv", ["hf_fixture_clarity", "--output", str(output)])
    command.main()
    result = json.loads((output / "metadata.json").read_text())
    assert result["status"] == "offline_plan" and result["inference_started"] is False
    assert result["candidate_outbound_attempts"] == 2 and result["approved_outbound_budget"] == 0
    assert result["outbound_budget"] == 0 and result["qualification_accepted"] is False
    assert result["paper_collection_planned"] is False
    assert result["source_sha256"] and set(result["payload_sha256"]) == {"clarity-positive", "clarity-negative"}
    assert sorted(p.name for p in output.iterdir()) == ["metadata.json"]
    assert result["success_diagnostic_manifest_sha256"] == command.load_clarity()["measurement_manifest_sha256"]


@pytest.mark.parametrize("mode", ["outside", "existing", "execute"])
def test_cli_rejects_unsafe_or_live_output(monkeypatch, tmp_path, mode):
    output = (
        Path("evaluation") / tmp_path.name
        if mode == "outside"
        else Path("tests/test_output") / tmp_path.parent.name / tmp_path.name / "rejected-clarity-plan"
    )
    if mode == "existing":
        output.mkdir(parents=True)
    args = ["hf_fixture_clarity", "--output", str(output)] + (["--execute"] if mode == "execute" else [])
    monkeypatch.setattr("sys.argv", args)
    with pytest.raises(SystemExit) as exc:
        command.main()
    assert exc.value.code == 2
    assert not (output / "metadata.json").exists()
