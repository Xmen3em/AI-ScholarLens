"""Offline, response-bound semantic review and fixed Week 7 comparison metrics.

Templates deliberately leave judgments unset. Attribution, exact quotes and model
outcomes never automatically earn semantic fact/relevance credit. No model calls.
"""

import argparse
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path

from src.commands.agent_collection import audit_response, build_jobs
from src.commands.evaluate_agent import MANIFEST_SHA256, load_labels
from src.commands.evaluate_retrieval import digest
from src.schemas.api.rag import AskRequest
from src.services.rag.context import EXCERPT_LINE_PATTERN, INSUFFICIENT_EVIDENCE_ANSWER


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _excerpts(answer: str) -> list[dict]:
    if answer == INSUFFICIENT_EVIDENCE_ANSWER:
        return []
    result = []
    for line in answer.splitlines():
        if not line.strip():
            continue
        match = EXCERPT_LINE_PATTERN.fullmatch(line.strip())
        _require(match is not None, "answer is not a validated quotation")
        assert match is not None
        quote, marker = match.groups()
        result.append({"quote": quote, "marker": marker,
                       "quote_sha256": hashlib.sha256(line.strip().encode()).hexdigest()})
    _require(bool(result), "substantive answer has no excerpts")
    return result


def make_review_template(records: list[dict], cases: list[dict]) -> dict:
    by_case = {case["id"]: case for case in cases}
    reviews = []
    for record in records:
        if not record["ok"]:
            continue
        response = record["response"]
        _require(digest(response) == record["response_sha256"], "record response fingerprint differs")
        excerpts = _excerpts(response["answer"])
        if not excerpts:
            continue
        case = by_case[record["case_id"]]
        reviews.append({"key": record["key"], "response_sha256": record["response_sha256"], "reviewer": None,
                        "query": case["query"], "required_facts": case["facts"], "rationale": None,
                        "covered_fact_ids": None,
                        "excerpts": [{**excerpt, "relevant": None, "fact_ids": None, "rationale": None}
                                     for excerpt in excerpts]})
    return {"manifest_sha256": MANIFEST_SHA256, "reviews": reviews}


def _semantic(record: dict, case: dict, reviews: dict) -> tuple[list[str], int, int]:
    review = reviews.get(record["key"])
    _require(review is not None, "substantive response is unreviewed")
    assert review is not None
    _require(review.get("query") == case["query"] and review.get("required_facts") == case["facts"], "reviewed question/facts differ")
    _require(review["response_sha256"] == record["response_sha256"], "reviewed response changed")
    _require(isinstance(review.get("reviewer"), str) and bool(review["reviewer"].strip()), "reviewer is unset")
    _require(isinstance(review.get("rationale"), str) and bool(review["rationale"].strip()), "review rationale is unset")
    allowed = {fact["id"] for fact in case["facts"]}
    covered = review.get("covered_fact_ids")
    _require(isinstance(covered, list) and len(set(covered)) == len(covered) and set(covered) <= allowed,
             "unknown/duplicate/unset covered fact IDs")
    expected = _excerpts(record["response"]["answer"])
    _require(len(review["excerpts"]) == len(expected), "excerpt review count differs")
    assigned = set()
    relevant = 0
    for actual, excerpt in zip(review["excerpts"], expected):
        _require(all(actual.get(key) == excerpt[key] for key in ("quote_sha256", "quote", "marker")), "reviewed quotation changed")
        _require(type(actual.get("relevant")) is bool, "excerpt relevance is unreviewed")
        _require(isinstance(actual.get("rationale"), str) and bool(actual["rationale"].strip()), "excerpt rationale is unset")
        facts = actual.get("fact_ids")
        _require(isinstance(facts, list) and len(set(facts)) == len(facts) and set(facts) <= allowed, "excerpt facts are invalid")
        _require(actual["relevant"] or not facts, "irrelevant excerpt cannot cover a required fact")
        assigned.update(facts)
        relevant += int(actual["relevant"])
    _require(assigned == set(covered), "covered facts differ from excerpt assignments")
    return covered, relevant, len(expected)


def _mean(values):
    return sum(values) / len(values) if values else None


def _cell(records: list) -> dict:
    positives = [r for r in records if r["answerable"]]
    negatives = [r for r in records if not r["answerable"]]
    substantive = [r for r in records if r["ok"] and not r["abstained"]]
    durations = sorted(r["duration_ms"] for r in records)
    strata = {kind: _mean([r["coverage"] for r in positives if r["kind"] == kind])
              for kind in ("literal", "paraphrase", "numeric", "multi_paper")}
    return {"attempts": len(records), "positive_attempts": len(positives), "negative_attempts": len(negatives),
            "failures": sum(not r["ok"] for r in records),
            "false_abstentions": sum(r["ok"] and r["abstained"] for r in positives),
            "negative_correct_abstentions": sum(r["ok"] and r["abstained"] for r in negatives),
            "negative_substantive_answers": sum(r["ok"] and not r["abstained"] for r in negatives),
            "fact_coverage_mean": _mean([r["coverage"] for r in positives]), "coverage_by_kind": strata,
            "relevance_mean": _mean([r["relevant_excerpts"] / r["total_excerpts"] for r in substantive]),
            "substantive_responses": len(substantive), "relevant_excerpts": sum(r["relevant_excerpts"] for r in substantive),
            "total_excerpts": sum(r["total_excerpts"] for r in substantive),
            "generation_calls": sum(r["measured"].get("generation_calls", 0) for r in records),
            "embedding_calls": sum(r["measured"].get("embedding_calls", 0) for r in records),
            "latency": {"samples": len(durations), **{f"p{p}_ms": durations[math.ceil(len(durations) * p / 100) - 1]
                         for p in (50, 95)}}}


def score_records(records: list[dict], cases: list[dict], reviews: dict, papers: list, chunks: list, *,
                  planned_keys: list[str], split: str, expected_model="llama3.2:1b") -> dict:
    _require(reviews["manifest_sha256"] == MANIFEST_SHA256, "review manifest differs")
    _require(split in {"development", "holdout"}, "unknown split")
    _require(len(set(planned_keys)) == len(planned_keys), "duplicate planned jobs")
    by_case = {case["id"]: case for case in cases}
    by_review = {review["key"]: review for review in reviews["reviews"]}
    _require(len(by_review) == len(reviews["reviews"]), "duplicate semantic review")
    seen = set()
    groups: dict[str, list] = defaultdict(list)
    work_breaches = scope_errors = hybrid_fallbacks = 0
    for record in records:
        key = record["key"]
        _require(key not in seen and key in planned_keys, "duplicate/unplanned collection job")
        seen.add(key)
        case = by_case[record["case_id"]]
        _require(key == f"{case['id']}:{record['mode']}:{record['path']}:{record['transport']}", "job identity differs")
        _require(record["mode"] in {"bm25", "hybrid"} and record["path"] in {"baseline", "agent"}
                 and record["transport"] in {"json", "sse"}, "unknown comparison cell")
        duration = record["duration_ms"]
        _require(isinstance(duration, (float, int)) and math.isfinite(duration) and duration >= 0, "invalid attempt duration")
        agent = record["path"] == "agent"
        measured = record.get("measured") or {}
        work_breaches += int(measured.get("generation_calls", 0) > (6 if agent else 2)
                            or measured.get("retrieval_calls", 0) > (2 if agent else 1)
                            or measured.get("embedding_calls", 0) > (2 if agent else 1))
        row = {**record, "measured": measured, "kind": case["kind"], "answerable": case["answerable"],
               "abstained": False, "coverage": 0, "relevant_excerpts": 0, "total_excerpts": 0}
        if record["ok"]:
            _require(digest(record["response"]) == record["response_sha256"], "collected response changed")
            audit = audit_response(record["response"], AskRequest(query=case["query"], use_hybrid=record["mode"] == "hybrid"),
                                   papers, chunks, agent=agent, measured=measured, expected_model=expected_model)
            row["abstained"] = audit["abstained"]
            if measured.get("retrieval_calls", 0) and record["mode"] == "hybrid" and audit["actual_mode"] != "hybrid":
                hybrid_fallbacks += 1
            scope_errors += int(agent and record["response"].get("outcome") == "out_of_scope" and case["expected_scope"] == "in")
            if not audit["abstained"]:
                covered, relevant, total = _semantic(record, case, by_review)
                row.update(coverage=len(covered) / len(case["facts"]) if case["facts"] else 0,
                           relevant_excerpts=relevant, total_excerpts=total)
        groups[f"{record['path']}:{record['mode']}:{record['transport']}"].append(row)
    expected_reviews = {r["key"] for r in records if r["ok"] and r["response"]["answer"] != INSUFFICIENT_EVIDENCE_ANSWER}
    _require(set(by_review) == expected_reviews, "reviews do not match substantive collected responses")
    cells = {key: _cell(rows) for key, rows in sorted(groups.items())}
    complete = seen == set(planned_keys)
    gates = []
    holdout_keys = {job["key"] for job in build_jobs(cases)}
    if split != "holdout" or len(cases) != 24 or len(planned_keys) != 192 or set(planned_keys) != holdout_keys or not complete:
        gates.append("holdout_matrix_incomplete")
    if any(r.get("integrity_breach") for r in records) or work_breaches:
        gates.append("integrity_or_work_budget_breach")
    if any(not r.get("resource_passed", False) for r in records):
        gates.append("resource_margin_failed")
    if scope_errors:
        gates.append("in_scope_question_rejected_by_scope")
    if hybrid_fallbacks:
        gates.append("hybrid_operation_incomplete")
    comparisons = []
    for mode in ("bm25", "hybrid"):
        for transport in ("json", "sse"):
            baseline, agent_cell = cells.get(f"baseline:{mode}:{transport}"), cells.get(f"agent:{mode}:{transport}")
            if not baseline or not agent_cell:
                continue
            regression = (agent_cell["failures"] > baseline["failures"] or agent_cell["false_abstentions"] > baseline["false_abstentions"])
            deltas = {}
            for metric in ("fact_coverage_mean", "relevance_mean"):
                b, a = baseline[metric], agent_cell[metric]
                deltas[metric] = a - b if a is not None and b is not None else None
                difference = deltas[metric]
                regression |= difference is None or difference < 0
            for kind in ("paraphrase", "multi_paper"):
                b, a = baseline["coverage_by_kind"][kind], agent_cell["coverage_by_kind"][kind]
                if b is not None:
                    regression |= a is None or a < b
            comparisons.append({"mode": mode, "transport": transport, "observed_differences": deltas, "regression": regression})
            if regression:
                gates.append(f"regression_or_empty_relevance:{mode}:{transport}")
            if agent_cell["negative_correct_abstentions"] != agent_cell["negative_attempts"]:
                gates.append(f"negative_abstention_failed:{mode}:{transport}")
            if agent_cell["failures"]:
                gates.append(f"agent_failures:{mode}:{transport}")
    return {"split": split, "collection_complete": complete, "attempts": len(records), "planned_attempts": len(planned_keys),
            "holdout_accepted": split == "holdout" and not gates, "gate_failures": gates,
            "cells": cells, "comparisons": comparisons, "scope_errors": scope_errors, "hybrid_fallbacks": hybrid_fallbacks,
            "interpretation": "Observed convenience-sample comparison; no population-quality or deployment acceptance."}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("template", "score"))
    parser.add_argument("--run", type=Path, required=True, help="Collector directory with metadata.json and records.jsonl")
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--reviews", type=Path)
    parser.add_argument("--output", type=Path, required=True, help="New local ignored JSON file")
    args = parser.parse_args()
    output = args.output.resolve()
    roots = [(Path.cwd() / name).resolve() for name in ("test_output", "tests/test_output")]
    _require(any(output.is_relative_to(root) and output != root for root in roots) and not output.exists(), "output must be a new ignored file")
    read = lambda path: json.loads(path.read_text(encoding="utf-8"))
    metadata = read(args.run / "metadata.json")
    _require(metadata["manifest_sha256"] == MANIFEST_SHA256 and metadata["inference_started"], "run did not collect inference")
    _, datasets, papers, chunks = load_labels(Path("evaluation/week7_agent"), args.snapshot)
    records = [json.loads(line) for line in (args.run / "records.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    cases = datasets[metadata["split"]]["cases"]
    result = make_review_template(records, cases)
    if args.operation == "score":
        _require(args.reviews is not None, "score requires completed semantic reviews")
        result = score_records(records, cases, read(args.reviews), papers, chunks,
                               planned_keys=[job["key"] for job in metadata["jobs"]], split=metadata["split"],
                               expected_model=metadata["configuration"]["model"])
        completion = read(args.run / "completion.json")
        preserved = completion.get("preservation") or {}
        if completion.get("status") != "collected" or set(preserved) != {
            "corpus_unchanged", "models_unchanged", "source_unchanged", "frozen_labels_unchanged"} or not all(preserved.values()):
            result["holdout_accepted"] = False
            result["gate_failures"].append("collection_or_preservation_incomplete")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"written": str(output), "operation": args.operation, "holdout_accepted": result.get("holdout_accepted", False)}))


if __name__ == "__main__":
    main()
