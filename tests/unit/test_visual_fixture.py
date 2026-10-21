"""Scientific regression facts; independent of the generated old RAG lesson."""

import json
from pathlib import Path

FIXTURE = Path(__file__).resolve().parents[2] / "evaluation/visual_learning/rag-method.v1.json"


def test_rag_reference_preserves_source_and_training_policy():
    reference = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert reference["source"]["paper_id"] == "2005.11401v4"
    assert reference["source"]["sha256"] == "23e3249e9a1e75418d82efecab0ea8c4d033b89c93742f63208d47ce01f21233"
    assert reference["source"]["parser_revision"] == "pdfium-5.14.0-v1"
    assert reference["training_policy"] == {
        "query_encoder": "updated", "generator": "updated", "document_encoder": "fixed", "index": "fixed",
    }
    assert {fact["id"] for fact in reference["facts"]} >= {"training", "retrieval", "marginalization"}
    training = next(fact for fact in reference["facts"] if fact["id"] == "training")
    assert set(training["evidence_ids"]) == {"training-p4", "query-update-p4", "generator-update-p4"}
    source = next(item for item in reference["evidence"] if item["id"] == "training-p4")
    assert source["page"] == 4 and source["block_id"] == "p4b0"


def test_science_regressions_preserve_granularity_and_compared_setting():
    reference = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert reference["token_unit"] == "token"
    result = reference["reviewed_comparison"]
    assert (result["dataset"], result["split"], result["metric"]) == ("TriviaQA", "TQA-Wiki", "EM")
    assert result["values"]["RAG-Sequence"] == 68.0
    assert result["values"]["RAG-Token"] == 66.1
    assert result["values"]["RAG-Sequence"] > result["values"]["RAG-Token"]
    assert {case["id"] for case in reference["rejected_claims"]} == {
        "document_encoder_updated", "token_is_paragraph", "token_best_tqa_wiki",
    }
