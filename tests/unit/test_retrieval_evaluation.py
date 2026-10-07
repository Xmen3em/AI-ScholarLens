"""Protect evaluation denominators and fail-closed stream accounting."""

import pytest
from src.commands.evaluate_retrieval import parse_sse, retrieval_metrics, summarize, validate_reviews


def test_evidence_recall_requires_passage_and_counts_all_units():
    case = {
        "support": [
            {"locators": [{"arxiv_id": "a", "section_index": 2, "chunk_index": 0}]},
            {"locators": [{"arxiv_id": "b", "section_index": 3, "chunk_index": 1}]},
        ]
    }
    hits = [
        {"arxiv_id": "a", "passages": [{"section_index": 9, "chunk_index": 0}]},
        {"arxiv_id": "b", "passages": [{"section_index": 3, "chunk_index": 1}]},
    ]
    scores = retrieval_metrics(case, hits, 3)
    assert scores["hit"] == 1
    assert scores["recall"] == 0.5
    assert scores["mrr"] == 0.5
    assert 0 < scores["ndcg"] < 1


def test_repeated_alternative_passages_do_not_inflate_recall():
    locator = {"arxiv_id": "a", "section_index": 2, "chunk_index": 0}
    case = {"support": [{"locators": [locator, locator]}]}
    hits = [{"arxiv_id": "a", "passages": [locator, locator]}]
    assert retrieval_metrics(case, hits, 3)["recall"] == 1
    assert retrieval_metrics(case, [], 3) == {"hit": 0, "recall": 0, "mrr": 0, "ndcg": 0}
    assert retrieval_metrics({"support": []}, [], 3) is None


def test_stream_errors_and_partial_output_cannot_be_success():
    events = 'event: sources\ndata: {"citations": []}\n\nevent: delta\ndata: {"delta": "partial"}\n\n'
    with pytest.raises(ValueError, match="done"):
        parse_sse(events)
    with pytest.raises(ValueError, match="error"):
        parse_sse(events + 'event: error\ndata: {"error": "failed"}\n\n')


def test_stream_must_match_deltas_but_allows_no_delta_abstention():
    prefix = 'event: sources\ndata: {"citations": []}\n\n'
    assert parse_sse(
        prefix + 'event: done\ndata: {"answer": "The retrieved evidence is insufficient to answer this question."}\n\n'
    )["answer"].startswith("The retrieved")
    with pytest.raises(ValueError, match="deltas"):
        parse_sse(prefix + 'event: delta\ndata: {"delta": "x"}\n\nevent: done\ndata: {"answer": "y"}\n\n')


def test_attributed_but_irrelevant_answers_earn_no_semantic_credit_and_errors_are_not_abstentions():
    benchmark = {
        "cases": [
            {"id": "supported", "answerable": True, "kind": "paraphrase", "facts": [{"id": "fact"}]},
            {"id": "unsupported", "answerable": False, "kind": "unrelated", "facts": []},
        ]
    }
    records, reviews = [], {}
    for mode in ("bm25", "hybrid"):
        for case in benchmark["cases"]:
            for k in (3, 5):
                records.append(
                    {
                        "case_id": case["id"],
                        "endpoint": "search",
                        "requested_mode": mode,
                        "k": k,
                        "ok": True,
                        "seconds": 1,
                        "metrics": {"hit": 1, "recall": 1, "mrr": 1, "ndcg": 1},
                    }
                )
            for endpoint in ("ask", "stream"):
                key = f"{case['id']}:{mode}:{endpoint}:3"
                records.append(
                    {
                        "key": key,
                        "case_id": case["id"],
                        "endpoint": endpoint,
                        "requested_mode": mode,
                        "ok": case["answerable"],
                        "seconds": 1,
                        "response": {"answer": '"Unrelated source text." [1.1]', "citations": [], "search_mode": mode},
                        "audit": {"abstained": False, "words": 15, "attribution_error": None, "citation_checks": []},
                    }
                )
                if case["answerable"]:
                    reviews[key] = {"covered_facts": [], "relevant_excerpts": 0, "total_excerpts": 1}
    summary = summarize(benchmark, records, reviews)
    for scores in summary["answers"].values():
        assert scores["mean_fact_coverage"] == 0
        assert scores["excerpt_relevance"] == 0
        assert scores["attribution_failures"] == 0
        assert scores["failures"] == 1
        assert scores["correct_abstentions"] == 0
        assert scores["abstention_decision_accuracy"] == 0.5
    assert summary["endpoint_consistency"]["hybrid"]["both_successful"] == 1


def test_stale_semantic_reviews_cannot_score_changed_answers():
    records = [{"endpoint": "ask", "ok": True, "key": "case:bm25:ask:3", "response": {"answer": "changed answer"}}]
    reviews = {"case:bm25:ask:3": {"answer_digest": "old digest"}}
    with pytest.raises(ValueError, match="reviewed answer changed"):
        validate_reviews(records, reviews)
