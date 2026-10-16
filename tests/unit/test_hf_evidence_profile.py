import json
from pathlib import Path

import pytest
from src.commands import hf_paper_profile as profiles


def test_evidence_profile_changes_only_candidate_availability():
    parent = profiles.load_profile()
    selected = profiles.load_evidence_profile()
    assert {k for k in parent if parent[k] != selected[k]} == {"version", "candidates_per_passage"}
    assert set(selected) - set(parent) == {"max_sentence_candidates"}
    assert selected["candidates_per_passage"] == 3 and selected["max_sentence_candidates"] == 10
    assert profiles.get_profile(profiles.EVIDENCE_PROFILE) == (selected, profiles.EVIDENCE_TASK_SHA256)
    assert profiles.get_profile_by_manifest(profiles.EVIDENCE_TASK_SHA256) == selected
    assert profiles.get_profile_by_manifest(profiles.CEREBRAS_TASK_SHA256) == parent
    assert profiles.get_profile(profiles.CEREBRAS_PROFILE)[0] == parent
    with pytest.raises(ValueError):
        profiles.get_profile_by_manifest("unregistered")


@pytest.mark.parametrize("name", ["manifest.json", "profile.json", "PROTOCOL.md"])
def test_evidence_profile_rejects_changed_frozen_bytes(tmp_path, name):
    for source in Path("evaluation/week7_hf/cerebras-evidence-v3").iterdir():
        (tmp_path / source.name).write_bytes(source.read_bytes())
    target = tmp_path / name
    target.write_bytes(target.read_bytes() + b" ")
    with pytest.raises(ValueError):
        profiles.load_evidence_profile(tmp_path)


@pytest.mark.parametrize("split,count,budget", [("development", 8, 261), ("holdout", 24, 773)])
def test_evidence_plan_remains_complete_and_offline(tmp_path, monkeypatch, split, count, budget):
    cases = [{"id": f"case-{i}", "query": "synthetic paper question"} for i in range(count)]
    monkeypatch.setattr(profiles, "load_labels", lambda *a: ({}, {split: {"cases": cases}}, [], []))
    monkeypatch.setattr(profiles, "source_hashes", lambda: {"src/frozen.py": "source"})
    (tmp_path / "state.json").write_text("{}")
    plan = profiles.plan_collection(tmp_path, split=split, profile_name=profiles.EVIDENCE_PROFILE)
    assert plan["hosted_manifest_sha256"] == profiles.EVIDENCE_TASK_SHA256
    assert plan["configuration"]["policy"] == profiles.EVIDENCE_PROFILE
    assert len(plan["jobs"]) == count * 8 and plan["planned_outbound_budget"] == budget
    assert plan["approved_outbound_budget"] == plan["outbound_budget"] == 0
    assert plan["app_accepted"] is plan["inference_started"] is False
    assert "synthetic paper question" not in json.dumps(plan)
