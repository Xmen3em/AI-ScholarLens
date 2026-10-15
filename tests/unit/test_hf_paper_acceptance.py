import copy
import hashlib
import json

import pytest
from src.commands import hf_paper_acceptance as command
from src.commands.hf_paper_profile import CEREBRAS_PROFILE, CEREBRAS_TASK_SHA256, load_profile


def evidence(tmp_path, monkeypatch, *, accepted=True):
    run, source = tmp_path / "holdout", tmp_path / "snapshot"
    run.mkdir(); source.mkdir()
    (source / "state.json").write_text("{}")
    model = load_profile()["model_pairs"][0]
    metadata = {"split": "holdout", "hosted_manifest_sha256": CEREBRAS_TASK_SHA256,
                "configuration": {"model": model, "policy": CEREBRAS_PROFILE}, "source_sha256": {"src/a.py": "source"},
                "source_snapshot_sha256": hashlib.sha256((source / "state.json").read_bytes()).hexdigest()}
    (run / "metadata.json").write_text(json.dumps(metadata))
    for name in ("completion.json", "qualification.json", "reviews.json", "records.jsonl"):
        (run / name).write_text("{}")
    report = {"holdout_accepted": accepted, "development_accepted": False, "attempts": 192,
              "hosted_manifest_sha256": CEREBRAS_TASK_SHA256, "model": model, "gate_failures": [] if accepted else ["failed"]}
    monkeypatch.setattr(command, "score_run", lambda *args, **kwargs: copy.deepcopy(report))
    monkeypatch.setattr(command, "source_hashes", lambda: metadata["source_sha256"].copy())
    return run, source


def test_accepted_source_and_complete_evidence_can_create_and_validate_local_lock(tmp_path, monkeypatch):
    run, source = evidence(tmp_path, monkeypatch)
    lock = command.create_acceptance_lock(run, source)
    path = tmp_path / "acceptance.json"
    path.write_text(json.dumps(lock))
    validated = command.validate_acceptance(path)
    assert validated["model"] == "openai/gpt-oss-120b:cerebras"
    assert validated["source_snapshot"] == str(source.resolve())
    assert validated["holdout_accepted"] is True
    with pytest.raises(ValueError): command.create_acceptance_lock(run, source)


def test_unaccepted_holdout_does_not_create_an_acceptance_report(tmp_path, monkeypatch):
    run, source = evidence(tmp_path, monkeypatch, accepted=False)
    with pytest.raises(ValueError): command.create_acceptance_lock(run, source)
    assert not (run / "acceptance-report.json").exists()


@pytest.mark.parametrize("mutation", ["source", "snapshot", "reviews", "report", "model", "partial"])
def test_lock_never_accepts_stale_changed_or_wrong_model_evidence(tmp_path, monkeypatch, mutation):
    run, source = evidence(tmp_path, monkeypatch)
    lock = command.create_acceptance_lock(run, source)
    path = tmp_path / "acceptance.json"
    if mutation == "source": monkeypatch.setattr(command, "source_hashes", lambda: {"changed": "source"})
    elif mutation == "snapshot": (source / "state.json").write_text("changed")
    elif mutation == "reviews": (run / "reviews.json").write_text("changed")
    elif mutation == "report": (run / "acceptance-report.json").write_text("changed")
    elif mutation == "model": lock["model"] = "unreviewed/provider"
    else: lock["holdout_jobs"] = 1
    path.write_text(json.dumps(lock))
    with pytest.raises(ValueError): command.validate_acceptance(path)
