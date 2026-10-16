import json
from pathlib import Path

import pytest
from src.commands import hf_paper_profile as profiles

NAME = "hosted-cerebras-paced-v4"


def test_paced_profile_preserves_every_inherited_gate():
    parent = profiles.load_evidence_profile()
    selected, manifest = profiles.get_profile(NAME)
    assert selected == {**parent, "version": NAME}
    assert NAME in profiles.PAPER_PROFILES
    assert profiles.get_profile_by_manifest(manifest) == selected


@pytest.mark.parametrize("name", ["manifest.json", "profile.json", "PROTOCOL.md"])
def test_paced_profile_rejects_changed_frozen_bytes(tmp_path, name):
    for source in Path("evaluation/week7_hf/cerebras-paced-v4").iterdir():
        (tmp_path / source.name).write_bytes(source.read_bytes())
    target = tmp_path / name
    target.write_bytes(target.read_bytes() + b" ")
    with pytest.raises(ValueError):
        profiles.load_paced_profile(tmp_path)


@pytest.mark.parametrize("split,count,budget", [("development", 8, 261), ("holdout", 24, 773)])
def test_paced_plan_is_complete_and_unfunded(tmp_path, monkeypatch, split, count, budget):
    cases = [{"id": f"case-{i}", "query": "synthetic paper question"} for i in range(count)]
    monkeypatch.setattr(profiles, "load_labels", lambda *a: ({}, {split: {"cases": cases}}, [], []))
    monkeypatch.setattr(profiles, "source_hashes", lambda: {"src/frozen.py": "source"})
    (tmp_path / "state.json").write_text("{}")
    plan = profiles.plan_collection(tmp_path, split=split, profile_name=NAME)
    assert len(plan["jobs"]) == count * 8 and plan["planned_outbound_budget"] == budget
    assert plan["approved_outbound_budget"] == plan["outbound_budget"] == 0
    assert plan["app_accepted"] is plan["inference_started"] is False
    assert "synthetic paper question" not in json.dumps(plan)
