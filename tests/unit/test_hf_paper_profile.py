import json
from pathlib import Path

import pytest
from src.commands.agent_collection import build_jobs
from src.commands.hf_evaluation import HF_MANIFEST_SHA256, load_protocol
from src.commands.hf_paper_profile import CEREBRAS_TASK_SHA256, get_profile, load_profile, plan_collection
from src.commands.hf_qualification import REVISION_SHA256


def test_selected_profile_keeps_every_quality_and_resource_limit():
    original, selected = load_protocol(), load_profile()
    assert {key for key in original if original[key] != selected[key]} == {"version", "model_pairs", "prices_per_million"}
    assert selected["model_pairs"] == ["openai/gpt-oss-120b:cerebras"]
    assert selected["prices_per_million"] == {"openai/gpt-oss-120b:cerebras": {"input": .35, "output": .75}}
    assert selected["qualification_calls"] == 5
    assert selected["admission_mib"] == {"bm25": 1024, "hybrid": 1536}
    assert get_profile("hosted-cerebras-v1") == (selected, CEREBRAS_TASK_SHA256)
    assert get_profile() == (original, HF_MANIFEST_SHA256)


@pytest.mark.parametrize("name", ["manifest.json", "profile.json", "PROTOCOL.md"])
def test_tampered_profile_is_rejected(tmp_path, name):
    for path in Path("evaluation/week7_hf/cerebras-evaluation-v1").iterdir():
        (tmp_path / path.name).write_bytes(path.read_bytes())
    path = tmp_path / name
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError):
        load_profile(tmp_path)


@pytest.mark.parametrize("name", ["unregistered", "openai/gpt-oss-120b:cerebras"])
def test_profile_names_are_explicit_and_cannot_be_replaced_by_models(name):
    with pytest.raises(ValueError):
        get_profile(name)


@pytest.mark.parametrize("split,count,budget", [("development", 8, 261), ("holdout", 24, 773)])
def test_offline_plan_contains_complete_matrix_with_zero_spending(tmp_path, monkeypatch, split, count, budget):
    from src.commands import hf_paper_profile as command

    cases = [{"id": f"case-{index}", "query": "private fixture question"} for index in range(count)]
    labels = {split: {"cases": cases}}
    monkeypatch.setattr(command, "load_labels", lambda *args: ({}, labels, [], []))
    monkeypatch.setattr(command, "source_hashes", lambda: {"src/frozen.py": "source-hash"})
    (tmp_path / "state.json").write_text('{"papers":58,"chunks":2775}')
    before = {path: path.read_bytes() for path in tmp_path.iterdir()}
    metadata = plan_collection(tmp_path, split=split)
    expected = [{key: value for key, value in job.items() if key != "query"} for job in build_jobs(cases)]
    assert metadata["jobs"] == expected
    assert len(metadata["jobs"]) == count * 8
    assert metadata["planned_outbound_budget"] == budget
    assert metadata["outbound_budget"] == metadata["approved_outbound_budget"] == 0
    assert metadata["app_accepted"] is metadata["inference_started"] is False
    assert metadata["hosted_manifest_sha256"] == CEREBRAS_TASK_SHA256
    assert metadata["fixture_manifest_sha256"] == REVISION_SHA256
    assert metadata["configuration"] == {"model": "openai/gpt-oss-120b:cerebras", "policy": "hosted-cerebras-v1"}
    assert "private fixture question" not in json.dumps(metadata)
    assert before == {path: path.read_bytes() for path in tmp_path.iterdir()}


def test_invalid_split_does_not_touch_snapshot(tmp_path):
    with pytest.raises(ValueError):
        plan_collection(tmp_path, split="unknown")
    assert not list(tmp_path.iterdir())
