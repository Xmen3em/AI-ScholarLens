import copy
import hashlib

import pytest
from src.commands.agent_collection import build_jobs
from src.commands.evaluate_retrieval import digest
from src.commands.score_agent import make_review_template, score_records
from src.services.rag.context import INSUFFICIENT_EVIDENCE_ANSWER

from tests.unit.test_agent_collection import substantive
from tests.unit.test_agent_service import EVIDENCE, QUESTION


def fixture():
    cases = [{"id": "supported", "query": QUESTION, "kind": "literal", "answerable": True, "expected_scope": "in",
              "facts": [{"id": "binding", "text": "Binds claims to evidence using passage identifiers."}]},
             {"id": "unsupported", "query": "What does this method cost in kilowatt-hours?", "kind": "unsupported",
              "answerable": False, "expected_scope": "in", "facts": []}]
    records = []
    for case in cases:
        for path in ("baseline", "agent"):
            response = substantive()
            response["query"] = case["query"]
            if case["id"] == "unsupported":
                response.update(answer=INSUFFICIENT_EVIDENCE_ANSWER, outcome="abstained", sources=[], citations=[], chunks_used=0)
            if path == "baseline":
                response = {k: v for k, v in response.items() if k not in {
                    "policy_version", "outcome", "retrieval_attempts", "model_calls", "rewritten", "steps"}}
            record = {"key": f"{case['id']}:bm25:{path}:json", "case_id": case["id"], "path": path,
                      "mode": "bm25", "transport": "json", "ok": True, "response": response,
                      "response_sha256": digest(response), "duration_ms": 10 if path == "baseline" else 30,
                      "integrity_breach": False, "resource_passed": True,
                      "measured": {"generation_calls": 3 if path == "agent" else 1, "retrieval_calls": 1, "embedding_calls": 0}}
            records.append(record)
    papers = [{"arxiv_id": "2609.99999", "sections": [{"content": ""}, {"content": ""}, {"content": EVIDENCE}]}]
    chunks = [{"arxiv_id": "2609.99999", "section_index": 2, "chunk_index": 3, "section_title": "Method", "content": EVIDENCE}]
    template = make_review_template(records, cases)
    for review in template["reviews"]:
        review.update(reviewer="Source reviewer", rationale="The quoted method states this requested fact.", covered_fact_ids=["binding"])
        for excerpt in review["excerpts"]:
            excerpt.update(relevant=True, fact_ids=["binding"], rationale="Directly supports passage-identifier binding.")
    return records, cases, template, papers, chunks


def score(values, split="development"):
    records, cases, reviews, papers, chunks = values
    return score_records(records, cases, reviews, papers, chunks, planned_keys=[r["key"] for r in records], split=split)


def test_templates_do_not_invent_semantic_judgments():
    records, cases, _, _, _ = fixture()
    template = make_review_template(records, cases)
    assert len(template["reviews"]) == 2  # Fixed abstentions need no semantic quotation judgment.
    assert all(review["covered_fact_ids"] is None and review["reviewer"] is None for review in template["reviews"])
    assert all(excerpt["relevant"] is None for review in template["reviews"] for excerpt in review["excerpts"])


def test_scored_pilot_remains_distinct_from_holdout_acceptance():
    result = score(fixture())
    assert result["collection_complete"] and not result["holdout_accepted"]
    baseline = result["cells"]["baseline:bm25:json"]
    agent = result["cells"]["agent:bm25:json"]
    assert baseline["fact_coverage_mean"] == agent["fact_coverage_mean"] == 1
    assert agent["relevance_mean"] == 1 and agent["negative_correct_abstentions"] == 1
    assert agent["latency"]["p95_ms"] == 30


@pytest.mark.parametrize("bad", ["response", "quote_hash", "unknown_fact", "fact_union", "unreviewed", "irrelevant_fact", "duplicate", "wrong_manifest"])
def test_stale_or_inconsistent_reviews_cannot_score(bad):
    values = fixture()
    review = values[2]["reviews"][0]
    if bad == "response":
        review["response_sha256"] = "0" * 64
    elif bad == "quote_hash":
        review["excerpts"][0]["quote_sha256"] = "0" * 64
    elif bad == "unknown_fact":
        review["covered_fact_ids"] = ["invented-fact"]
    elif bad == "fact_union":
        review["covered_fact_ids"] = []
    elif bad == "unreviewed":
        review["excerpts"][0]["relevant"] = None
    elif bad == "irrelevant_fact":
        review["excerpts"][0]["relevant"] = False
    elif bad == "duplicate":
        values[2]["reviews"].append(copy.deepcopy(review))
    else:
        values[2]["manifest_sha256"] = "0" * 64
    with pytest.raises(ValueError):
        score(values)


def test_errors_are_not_correct_abstentions_and_remain_in_latency_denominator():
    values = fixture()
    failed = values[0][-1]
    failed.update(ok=False, error_type="HTTP502", duration_ms=70)
    failed.pop("response")
    failed.pop("response_sha256")
    result = score(values)
    agent = result["cells"]["agent:bm25:json"]
    assert agent["failures"] == 1 and agent["negative_correct_abstentions"] == 0
    assert agent["negative_attempts"] == 1 and agent["latency"]["p95_ms"] == 70


def test_partial_and_subset_holdouts_never_pass_acceptance():
    values = fixture()
    result = score(values, split="holdout")
    assert not result["holdout_accepted"] and "holdout_matrix_incomplete" in result["gate_failures"]
    values[0].pop()
    records, cases, reviews, papers, chunks = values
    result = score_records(records, cases, reviews, papers, chunks,
                           planned_keys=["supported:bm25:baseline:json", "supported:bm25:agent:json",
                                         "unsupported:bm25:baseline:json", "unsupported:bm25:agent:json"], split="development")
    assert not result["collection_complete"]


@pytest.mark.parametrize("bad", ["duplicate_job", "unexpected_job", "bad_source", "false_digest"])
def test_collection_records_are_reaudited_before_semantic_scoring(bad):
    values = fixture()
    if bad == "duplicate_job":
        values[0].append(copy.deepcopy(values[0][0]))
    elif bad == "unexpected_job":
        values[0][0]["key"] = "unplanned"
    elif bad == "bad_source":
        values[4][0]["content"] = "Different source text."
    else:
        values[0][0]["response_sha256"] = "0" * 64
    with pytest.raises(ValueError):
        score(values)


def full_holdout_fixture():
    initial, initial_cases, _, papers, chunks = fixture()
    kinds = ["literal"] * 6 + ["paraphrase"] * 6 + ["multi_paper"] * 2 + ["numeric"] * 2 + ["unsupported"] * 4 + ["out_of_scope"] * 4
    cases = []
    for index, kind in enumerate(kinds):
        case = copy.deepcopy(initial_cases[0 if index < 16 else 1])
        case.update(id=f"synthetic-{index}", kind=kind, expected_scope="out" if kind == "out_of_scope" else "in")
        cases.append(case)
    by_case = {case["id"]: case for case in cases}
    jobs = build_jobs(cases)
    records = []
    for job in jobs:
        case = by_case[job["case_id"]]
        base = initial[(0 if case["answerable"] else 2) + int(job["path"] == "agent")]
        record = {**copy.deepcopy(base), **{k: v for k, v in job.items() if k != "query"}}
        record["response"]["search_mode"] = job["mode"]
        record["measured"]["embedding_calls"] = int(job["mode"] == "hybrid")
        if job["path"] == "agent" and case["expected_scope"] == "out":
            record["response"]["outcome"] = "out_of_scope"
        record["response_sha256"] = digest(record["response"])
        records.append(record)
    reviews = make_review_template(records, cases)
    for review in reviews["reviews"]:
        review.update(reviewer="Synthetic test reviewer", rationale="Direct fact match in synthetic fixture.", covered_fact_ids=["binding"])
        for excerpt in review["excerpts"]:
            excerpt.update(relevant=True, fact_ids=["binding"], rationale="Requested fact present.")
    return records, cases, reviews, papers, chunks


def test_complete_reviewed_matrix_passes_observed_gates_but_regression_rejects_it():
    values = full_holdout_fixture()
    accepted = score(values, split="holdout")
    assert accepted["attempts"] == 192 and accepted["holdout_accepted"] and accepted["gate_failures"] == []
    for review in values[2]["reviews"]:
        if ":agent:" in review["key"]:
            review["covered_fact_ids"] = []
            for excerpt in review["excerpts"]:
                excerpt["fact_ids"] = []
    rejected = score(values, split="holdout")
    assert not rejected["holdout_accepted"]
    assert any(gate.startswith("regression_or_empty_relevance") for gate in rejected["gate_failures"])


def test_stopped_resource_run_and_substantive_negative_answer_reject_acceptance():
    values = full_holdout_fixture()
    values[0][0]["resource_passed"] = False
    rejected = score(values, split="holdout")
    assert not rejected["holdout_accepted"] and "resource_margin_failed" in rejected["gate_failures"]
    values = full_holdout_fixture()
    target = next(r for r in values[0] if r["case_id"] == "synthetic-16" and r["path"] == "agent")
    target["response"] = substantive()
    target["response"]["query"] = values[1][16]["query"]
    target["response_sha256"] = digest(target["response"])
    extra = make_review_template([target], values[1])["reviews"][0]
    extra.update(reviewer="Synthetic test reviewer", rationale="Quote does not answer missing-cost question.", covered_fact_ids=[])
    for excerpt in extra["excerpts"]:
        excerpt.update(relevant=False, fact_ids=[], rationale="Method description gives no electrical cost.")
    values[2]["reviews"].append(extra)
    rejected = score(values, split="holdout")
    assert not rejected["holdout_accepted"]
    assert any(gate.startswith("negative_abstention_failed") for gate in rejected["gate_failures"])
