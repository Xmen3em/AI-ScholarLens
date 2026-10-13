import copy
import hashlib
import json
from collections import Counter

import pytest
from src.commands.evaluate_retrieval import digest
from src.commands.validate_agent_evaluation import normalized_query, validate_freeze, validate_suite


def fixtures():
    papers = [{"arxiv_id": pid, "sections": [{"title": "Methods", "content": "The method uses local evidence for validation."}]}
              for pid in ("dev-paper", "holdout-paper", "holdout-second")]
    chunks = [{"arxiv_id": p["arxiv_id"], "section_index": 0, "chunk_index": 0, "section_title": "Methods",
               "content": p["sections"][0]["content"]} for p in papers]
    corpus = {"paper_count": 3, "chunk_count": 3, "paper_digest": digest(sorted(papers, key=lambda p: p["arxiv_id"])),
              "chunk_digest": digest(sorted(chunks, key=lambda c: (c["arxiv_id"], c["section_index"], c["chunk_index"])))}

    def dataset(split, kinds, paper):
        cases = []
        for i, kind in enumerate(kinds):
            supported = kind not in {"unsupported", "out_of_scope"}
            fact = {"id": "fact", "text": "Uses local evidence."}
            quote = chunks[0]["content"]
            support = {"id": "unit", "fact_ids": ["fact"], "locators": [{
                "arxiv_id": paper, "section_index": 0, "chunk_index": 0, "section_title": "Methods",
                "source_excerpt": quote, "chunk_sha256": hashlib.sha256(quote.encode()).hexdigest()}]}
            case = {"id": f"{split}-{i}", "kind": kind, "query": f"Which local evidence does {split} method {i} use?",
                    "answerable": supported, "expected_scope": "out" if kind == "out_of_scope" else "in",
                    "facts": [fact] if supported else [], "support": [support] if supported else []}
            if kind == "multi_paper":
                case["facts"].append({"id": "second-fact", "text": "Other source uses local evidence."})
                second = copy.deepcopy(support)
                second["id"] = "second-unit"
                second["fact_ids"] = ["second-fact"]
                second["locators"][0]["arxiv_id"] = "holdout-second"
                case["support"].append(second)
            if kind in {"literal", "paraphrase"}:
                case["pair_id"] = f"{split}-pair-{i // 2}"
                if kind == "paraphrase":
                    case["query"] = f"How is support employed by {split} system {i}?"
            if not supported:
                case["negative_review"] = {"scope_papers": [] if kind == "out_of_scope" else [paper],
                    "rationale": "External task." if kind == "out_of_scope" else "Requested nonexistent detail absent from methods.",
                    "reviewed_sections": [] if kind == "out_of_scope" else [{"arxiv_id": paper, "section_index": 0}],
                    "scans": [] if kind == "out_of_scope" else [{"term": "missing detail", "scope_section_hits": 0,
                                                                "corpus_chunk_hits": 0}]}
            cases.append(case)
        return {"version": f"week7-agent-{split}-v1", "split": split, "corpus": corpus, "cases": cases}

    dev = dataset("development", ["literal", "paraphrase"] * 3 + ["unsupported", "out_of_scope"], "dev-paper")
    holdout = dataset("holdout", ["literal", "paraphrase"] * 6 + ["multi_paper"] * 2 + ["numeric"] * 2
                      + ["unsupported"] * 4 + ["out_of_scope"] * 4, "holdout-paper")
    return dev, holdout, papers, chunks


def check(values):
    return validate_suite(*values, prior_questions=["Old question?"], prior_support_papers=["old-paper"])


def test_source_reviewed_split_and_counts_are_validated():
    result = check(fixtures())
    assert result["development_cases"] == 8 and result["holdout_cases"] == 24
    assert result["holdout_kinds"] == dict(Counter(fixtures()[1]["cases"][i]["kind"] for i in range(24)))
    assert result["source_checks"] > 0 and result["negative_scan_checks"] == 5


@pytest.mark.parametrize("mutation", ["quote", "coordinate", "section", "hash", "corpus", "facts", "scope", "pair", "counts"])
def test_corrupted_labels_or_provenance_fail_closed(mutation):
    values = fixtures()
    case = values[1]["cases"][0]
    locator = case["support"][0]["locators"][0]
    if mutation == "quote":
        locator["source_excerpt"] = "Invented quotation."
    elif mutation == "coordinate":
        locator["chunk_index"] = 999
    elif mutation == "section":
        values[2][1]["sections"][0]["content"] = "A different section."
    elif mutation == "hash":
        locator["chunk_sha256"] = "0" * 64
    elif mutation == "corpus":
        values[1]["corpus"]["chunk_digest"] = "0" * 64
    elif mutation == "facts":
        case["support"][0]["fact_ids"] = ["nonexistent fact"]
    elif mutation == "scope":
        case["expected_scope"] = "out"
    elif mutation == "pair":
        values[1]["cases"][1]["facts"][0]["text"] = "Different expected claim."
    else:
        values[1]["cases"].pop()
    with pytest.raises(ValueError):
        check(values)


@pytest.mark.parametrize("collision", ["old_query", "cross_query", "old_paper", "cross_paper"])
def test_data_leakage_is_rejected(collision):
    values = fixtures()
    if collision == "old_query":
        values[1]["cases"][0]["query"] = "  OLD   question! "
    elif collision == "cross_query":
        values[1]["cases"][0]["query"] = values[0]["cases"][0]["query"]
    elif collision == "old_paper":
        values[1]["cases"][-5]["negative_review"]["scope_papers"] = ["old-paper"]
    else:
        values[1]["cases"][-5]["negative_review"]["scope_papers"] = ["dev-paper"]
    with pytest.raises(ValueError):
        check(values)


def test_negative_scan_is_recomputed_instead_of_trusting_label():
    values = fixtures()
    values[1]["cases"][-5]["negative_review"]["scans"][0]["term"] = "local evidence"
    with pytest.raises(ValueError, match="scan"):
        check(values)


def test_query_normalization_catches_punctuation_and_case_overlap():
    assert normalized_query(" How Does It Work? ") == normalized_query("how does it work!")


def test_freeze_checks_exact_bytes_and_existing_evaluations(writable_cache_dir):
    frozen = writable_cache_dir / "holdout.json"
    frozen.write_text(json.dumps({"cases": []}), encoding="utf-8")
    sha = hashlib.sha256(frozen.read_bytes()).hexdigest()
    manifest = {"sha256": {"holdout.json": sha}, "prior_evaluation_sha256": {"holdout.json": sha}}
    assert validate_freeze(manifest, writable_cache_dir, writable_cache_dir) == 2
    frozen.write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError, match="fingerprint"):
        validate_freeze(manifest, writable_cache_dir, writable_cache_dir)


def test_freeze_rejects_paths_outside_dataset_root(writable_cache_dir):
    with pytest.raises(ValueError, match="path"):
        validate_freeze({"sha256": {"../escape.json": "0" * 64}, "prior_evaluation_sha256": {}},
                        writable_cache_dir, writable_cache_dir)
