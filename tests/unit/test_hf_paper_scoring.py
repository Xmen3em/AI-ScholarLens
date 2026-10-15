import copy
import hashlib
import json

import pytest
from src.commands import score_hf_agent as command
from src.commands.agent_collection import build_jobs
from src.commands.evaluate_retrieval import digest
from src.commands.hf_evaluation import hosted_work
from src.commands.hf_paper_profile import CEREBRAS_PROFILE, CEREBRAS_TASK_SHA256, load_profile
from src.commands.hf_qualification import load_revision

from tests.unit.test_agent_scoring import full_holdout_fixture
from tests.unit.test_hf_scoring import call


def complete_development(tmp_path, monkeypatch):
    records, cases, reviews, papers, chunks = full_holdout_fixture()
    cases = [cases[index] for index in (0, 1, 6, 7, 12, 14, 16, 20)]
    jobs = build_jobs(cases)
    indexed = {record["key"]: record for record in records}
    records = [indexed[job["key"]] for job in jobs]
    profile = load_profile()
    model = profile["model_pairs"][0]
    for record in records:
        calls = [call(model=model, ordinal=index + 1) for index in range(record["measured"]["generation_calls"])]
        record.update(hf_calls=calls, hosted=hosted_work(calls, profile, model))
        record["response"]["model"] = model
        record["response_sha256"] = digest(record["response"])
    indexed = {record["key"]: record for record in records}
    reviews["reviews"] = [review for review in reviews["reviews"] if review["key"] in indexed]
    for review in reviews["reviews"]:
        review["response_sha256"] = indexed[review["key"]]["response_sha256"]
    revision = load_revision()
    reviews.update(hosted_manifest_sha256=CEREBRAS_TASK_SHA256, model=model,
                   records_sha256=digest(records), fixture_manifest_sha256=revision["manifest_sha256"])
    checks = []
    for case in revision["cases"]:
        calls = [call(model=model, schema_sha256=digest(case["schema"]), output_limit=512 if case["id"].startswith("selector") else 256)]
        diagnostics = {"expected_match": True}
        if case["id"] == "relevance": diagnostics.update(supplied_marker_membership=True, duplicate_markers=False, marker_count=1)
        checks.append({"id": case["id"], "schema_sha256": digest(case["schema"]), "fixture_sha256": digest(case),
                       "diagnostics": diagnostics, "ok": True, "calls": calls,
                       "work": hosted_work(calls, profile, model), "minimum_free_mib": 4096})
    (tmp_path / "state.json").write_text("{}")
    metadata = {"hosted_manifest_sha256": CEREBRAS_TASK_SHA256, "inference_started": True, "split": "development",
                "fixture_manifest_sha256": revision["manifest_sha256"], "configuration": {"model": model, "policy": CEREBRAS_PROFILE},
                "source_sha256": {"synthetic": "test"}, "source_snapshot_sha256": hashlib.sha256((tmp_path / "state.json").read_bytes()).hexdigest(),
                "jobs": [{k: v for k, v in job.items() if k != "query"} for job in jobs],
                "planned_outbound_budget": 261, "approved_outbound_budget": 261, "outbound_budget": 261,
                "allowance": {"signature": "funded", "path": str(tmp_path / "allowance.sqlite3"), "approval_path": str(tmp_path / "approval.json")}}
    completion = {"status": "collected", "outbound_attempts": 5 + sum(len(record["hf_calls"]) for record in records),
                  "preservation": dict.fromkeys(["corpus_unchanged", "models_unchanged", "source_unchanged", "frozen_labels_unchanged"], True)}
    qualification = {"qualified": True, "large_schema_preflight_rejected": True,
                     "fixture_manifest_sha256": revision["manifest_sha256"], "checks": checks}
    for name, value in (("metadata.json", metadata), ("completion.json", completion), ("qualification.json", qualification)):
        (tmp_path / name).write_text(json.dumps(value))
    (tmp_path / "records.jsonl").write_text("\n".join(json.dumps(record) for record in records))
    monkeypatch.setattr(command, "load_labels", lambda *args: ({}, {"development": {"cases": cases}}, papers, chunks))
    monkeypatch.setattr(command, "source_hashes", lambda: {"synthetic": "test"})
    monkeypatch.setattr(command, "validate_task_accounting", lambda *args: "funded-proof")
    return reviews


def test_explicit_cerebras_profile_scores_full_reviewed_development_without_using_old_pilot_scope(tmp_path, monkeypatch):
    reviews = complete_development(tmp_path, monkeypatch)
    report = command.score_run(tmp_path, tmp_path, reviews, profile_name=CEREBRAS_PROFILE)
    assert report["development_accepted"] and not report["holdout_accepted"]
    assert report["attempts"] == 64 and report["gate_failures"] == []
    assert report["hosted_manifest_sha256"] == CEREBRAS_TASK_SHA256
    assert report["funding_binding"] == "funded-proof"
    with pytest.raises(ValueError): command.score_run(tmp_path, tmp_path, reviews)


@pytest.mark.parametrize("mutation", ["profile", "model", "revision", "usage", "semantic", "funding"])
def test_cerebras_profile_never_credits_wrong_identity_incomplete_usage_or_unreviewed_funding(tmp_path, monkeypatch, mutation):
    reviews = complete_development(tmp_path, monkeypatch)
    if mutation in {"profile", "model", "revision"}:
        key = {"profile": "hosted_manifest_sha256", "model": "model", "revision": "fixture_manifest_sha256"}[mutation]
        reviews[key] = "changed"
        with pytest.raises(ValueError): command.score_run(tmp_path, tmp_path, reviews, profile_name=CEREBRAS_PROFILE)
        return
    if mutation == "funding":
        def invalid(*args): raise ValueError("missing or changed funding")
        monkeypatch.setattr(command, "validate_task_accounting", invalid)
    elif mutation == "semantic":
        for review in reviews["reviews"]:
            if ":agent:" in review["key"]:
                review["covered_fact_ids"] = []
                for excerpt in review["excerpts"]: excerpt["fact_ids"] = []
    else:
        path = tmp_path / "qualification.json"
        qualification = json.loads(path.read_text())
        qualification["checks"][0]["calls"][0]["output_tokens"] = None
        qualification["checks"][0]["work"] = hosted_work(qualification["checks"][0]["calls"], load_profile(), load_profile()["model_pairs"][0])
        path.write_text(json.dumps(qualification))
    report = command.score_run(tmp_path, tmp_path, reviews, profile_name=CEREBRAS_PROFILE)
    assert not report["development_accepted"] and report["gate_failures"]


def test_review_template_binds_actual_profile_without_changing_original_default():
    review = command.hosted_review_template([], [], load_profile()["model_pairs"][0], profile_name=CEREBRAS_PROFILE)
    assert review["hosted_manifest_sha256"] == CEREBRAS_TASK_SHA256


def test_cerebras_development_lock_recalculates_actual_profile_and_rejects_changed_evidence(tmp_path, monkeypatch):
    from src.commands.evaluate_hf_agent import validate_selection

    reviews = complete_development(tmp_path, monkeypatch)
    (tmp_path / "reviews.json").write_text(json.dumps(reviews))
    report = command.score_run(tmp_path, tmp_path, reviews, profile_name=CEREBRAS_PROFILE)
    report_path = tmp_path / "selection-report.json"
    report_path.write_text(json.dumps(report))
    sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    selection = {"hosted_manifest_sha256": CEREBRAS_TASK_SHA256, "model": report["model"],
                 "development_accepted": True, "development_jobs": 64, "development_run": str(tmp_path.resolve()),
                 "report_sha256": sha(report_path), "evidence_sha256": {name: sha(tmp_path / name) for name in
                     ("metadata.json", "completion.json", "qualification.json", "records.jsonl", "reviews.json")}}
    validate_selection(selection, report["model"], tmp_path, profile_name=CEREBRAS_PROFILE)
    with pytest.raises(ValueError): validate_selection(selection, report["model"], tmp_path)
    (tmp_path / "reviews.json").write_text("changed")
    with pytest.raises(ValueError): validate_selection(selection, report["model"], tmp_path, profile_name=CEREBRAS_PROFILE)
