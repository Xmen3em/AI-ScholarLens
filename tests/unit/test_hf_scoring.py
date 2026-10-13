import copy
import json

import pytest
from src.commands.agent_collection import build_jobs
from src.commands.evaluate_retrieval import digest
from src.commands.hf_evaluation import HF_MANIFEST_SHA256, hosted_work, load_protocol, qualification_cases
from src.commands.score_hf_agent import hosted_gates, hosted_review_template, score_run

from tests.unit.test_agent_scoring import full_holdout_fixture
from tests.unit.test_hf_configuration import MODEL


def call(**updates):
    return {"ordinal": 1, "model": MODEL, "outcome": "completed", "outbound_attempts": 1,
            "schema_valid": True, "input_tokens": 100, "output_tokens": 20, "output_limit": 256,
            "duration_ms": 10} | updates


def base():
    calls = [call()]
    record = {"key": "case:bm25:agent:json", "hf_calls": calls, "hosted": hosted_work(calls, load_protocol(), MODEL),
              "measured": {"generation_calls": 1}}
    original = {"gate_failures": ["holdout_matrix_incomplete"], "collection_complete": True,
                "cells": {"agent:bm25:json": {"latency": {"p95_ms": 100}}}}
    qualification = {"qualified": True, "large_schema_preflight_rejected": True,
                     "checks": [{"ok": True, "calls": [call()], "work": hosted_work([call()], load_protocol(), MODEL),
                                 "minimum_free_mib": 4096} for _ in range(5)]}
    completion = {"status": "collected", "outbound_attempts": 6, "preservation": {key: True for key in
                  ("corpus_unchanged", "models_unchanged", "source_unchanged", "frozen_labels_unchanged")}}
    return [record], original, qualification, completion


def test_hosted_review_binds_entire_records_and_provider_identity():
    review = hosted_review_template([], [], MODEL)
    assert review["hosted_manifest_sha256"] == HF_MANIFEST_SHA256 and review["model"] == MODEL
    assert "records_sha256" in review


@pytest.mark.parametrize("change,gate", [
    ("unknown_usage", "hosted_usage_incomplete"), ("schema", "hosted_schema_violation"),
    ("latency", "hosted_latency_target_failed"), ("partial", "hosted_matrix_incomplete"),
    ("preservation", "hosted_preservation_incomplete"), ("qualification", "hosted_qualification_failed"),
])
def test_hosted_acceptance_never_credits_incomplete_or_invalid_work(change, gate):
    records, original, qualification, completion = base()
    if change == "unknown_usage":
        records[0]["hf_calls"][0]["output_tokens"] = None
        records[0]["hosted"] = hosted_work(records[0]["hf_calls"], load_protocol(), MODEL)
    elif change == "schema":
        records[0]["hf_calls"][0]["schema_valid"] = False
        records[0]["hosted"] = hosted_work(records[0]["hf_calls"], load_protocol(), MODEL)
    elif change == "latency":
        original["cells"]["agent:bm25:json"]["latency"]["p95_ms"] = 20001
    elif change == "partial":
        original["collection_complete"] = False
    elif change == "preservation":
        completion["preservation"]["models_unchanged"] = False
    else:
        qualification["qualified"] = False
    assert gate in hosted_gates(records, original, qualification, completion, load_protocol(), MODEL,
                                split="development", planned_count=64)


def test_fabricated_work_aggregate_is_rejected():
    records, original, qualification, completion = base()
    records[0]["hosted"]["known_usage_cost_usd"] = 0
    with pytest.raises(ValueError):
        hosted_gates(records, original, qualification, completion, load_protocol(), MODEL, split="development", planned_count=64)


def test_token_limits_cannot_be_raised_in_saved_work():
    calls = [call(output_tokens=257)]
    with pytest.raises(ValueError):
        hosted_work(calls, load_protocol(), MODEL)
    bad = copy.deepcopy(calls)
    bad[0]["ordinal"] = True
    with pytest.raises(ValueError):
        hosted_work(bad, load_protocol(), MODEL)


@pytest.mark.parametrize("duration", [-1, float("nan"), float("inf"), True, None])
def test_saved_call_duration_must_be_finite_nonnegative(duration):
    with pytest.raises(ValueError):
        hosted_work([call(duration_ms=duration)], load_protocol(), MODEL)


def test_qualification_cannot_hide_extra_attempts_or_missing_schema_validation():
    records, original, qualification, completion = base()
    calls = [call(), call(ordinal=2)]
    qualification["checks"][0].update(calls=calls, work=hosted_work(calls, load_protocol(), MODEL))
    gates = hosted_gates(records, original, qualification, completion, load_protocol(), MODEL, split="development", planned_count=64)
    assert "hosted_qualification_failed" in gates and "hosted_attempt_accounting_incomplete" in gates
    assert hosted_work([call(schema_valid=None)], load_protocol(), MODEL)["schema_violations"] == 1


def complete_run(tmp_path, monkeypatch):
    records, cases, reviews, papers, chunks = full_holdout_fixture()
    for record in records:
        calls = [call(ordinal=index + 1) for index in range(record["measured"]["generation_calls"])]
        record.update(hf_calls=calls, hosted=hosted_work(calls, load_protocol(), MODEL))
        record["response"]["model"] = MODEL
        record["response_sha256"] = digest(record["response"])
    by_key = {record["key"]: record for record in records}
    for review in reviews["reviews"]:
        review["response_sha256"] = by_key[review["key"]]["response_sha256"]
    reviews.update(hosted_manifest_sha256=HF_MANIFEST_SHA256, model=MODEL, records_sha256=digest(records))
    checks = []
    for case in qualification_cases():
        calls = [call(schema_sha256=digest(case["schema"]), output_limit=512 if case["id"].startswith("selector") else 256)]
        checks.append({"id": case["id"], "schema_sha256": digest(case["schema"]), "ok": True,
                       "calls": calls, "work": hosted_work(calls, load_protocol(), MODEL), "minimum_free_mib": 4096})
    _, _, _, completion = base()
    completion["outbound_attempts"] = 5 + sum(len(record["hf_calls"]) for record in records)
    metadata = {"hosted_manifest_sha256": HF_MANIFEST_SHA256, "inference_started": True, "split": "holdout",
                "configuration": {"model": MODEL}, "source_sha256": {"synthetic": "test"}, "jobs": build_jobs(cases)}
    for name, value in {"metadata.json": metadata, "completion.json": completion,
                        "qualification.json": {"qualified": True, "large_schema_preflight_rejected": True, "checks": checks}}.items():
        (tmp_path / name).write_text(json.dumps(value), encoding="utf-8")
    (tmp_path / "records.jsonl").write_text("\n".join(json.dumps(record) for record in records), encoding="utf-8")
    monkeypatch.setattr("src.commands.score_hf_agent.load_labels", lambda *args: ({}, {"holdout": {"cases": cases}}, papers, chunks))
    monkeypatch.setattr("src.commands.score_hf_agent.source_hashes", lambda: {"synthetic": "test"})
    return reviews


def test_complete_hosted_matrix_passes_and_includes_qualification_cost(tmp_path, monkeypatch):
    reviews = complete_run(tmp_path, monkeypatch)
    report = score_run(tmp_path, tmp_path, reviews)
    assert report["attempts"] == 192 and report["holdout_accepted"] and report["gate_failures"] == []
    assert report["qualification_known_usage_cost_usd"] > 0
    assert report["known_usage_cost_usd"] > report["case_known_usage_cost_usd"]


@pytest.mark.parametrize("binding", ["model", "records_sha256", "hosted_manifest_sha256"])
def test_hosted_review_cannot_be_reused_for_another_provider_or_run(tmp_path, monkeypatch, binding):
    reviews = complete_run(tmp_path, monkeypatch)
    reviews[binding] = "changed"
    with pytest.raises(ValueError, match="Hosted review binding differs"):
        score_run(tmp_path, tmp_path, reviews)


def test_versioned_review_binds_exact_qualification_manifest(tmp_path, monkeypatch):
    from src.commands.hf_qualification import REVISION_SHA256

    reviews = complete_run(tmp_path, monkeypatch)
    path = tmp_path / "metadata.json"
    metadata = json.loads(path.read_text())
    metadata["fixture_manifest_sha256"] = REVISION_SHA256
    path.write_text(json.dumps(metadata))
    reviews["fixture_manifest_sha256"] = REVISION_SHA256
    with pytest.raises(ValueError, match="revision binding differs"):
        score_run(tmp_path, tmp_path, reviews)


def test_fabricated_complete_matrix_cannot_expand_versioned_pilot_approval(tmp_path, monkeypatch):
    from src.commands.hf_qualification import load_revision

    revision = load_revision()
    reviews = complete_run(tmp_path, monkeypatch)
    reviews["fixture_manifest_sha256"] = revision["manifest_sha256"]
    path = tmp_path / "metadata.json"
    metadata = json.loads(path.read_text())
    metadata.update(fixture_manifest_sha256=revision["manifest_sha256"], outbound_budget=11, allowance={"reserved_for_run": 11})
    path.write_text(json.dumps(metadata))
    path = tmp_path / "qualification.json"
    qualification = json.loads(path.read_text())
    qualification["fixture_manifest_sha256"] = revision["manifest_sha256"]
    for check, case in zip(qualification["checks"], revision["cases"], strict=True):
        check.update(fixture_sha256=digest(case), diagnostics={"expected_match": True})
    path.write_text(json.dumps(qualification))
    result = score_run(tmp_path, tmp_path, reviews)
    assert not result["holdout_accepted"]
    assert "hosted_pilot_scope_changed" in result["gate_failures"]
    assert "hosted_pilot_allowance_incomplete" in result["gate_failures"]
