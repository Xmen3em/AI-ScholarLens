"""Offline validation of fresh, source-reviewed Week 7 labels and their freeze.

No HTTP, model work, file writes or semantic scoring. Content checks establish
provenance and split integrity; they do not replace source/meaning review.
"""

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path, PureWindowsPath

from src.commands.evaluate_retrieval import coordinate, digest

EXPECTED_KINDS = {
    "development": {"literal": 3, "paraphrase": 3, "unsupported": 1, "out_of_scope": 1},
    "holdout": {"literal": 6, "paraphrase": 6, "multi_paper": 2, "numeric": 2,
                "unsupported": 4, "out_of_scope": 4},
}


def normalized_query(query: str) -> str:
    return " ".join(re.sub(r"[^\w]+", " ", query.casefold()).split())


def _text(text: str) -> str:
    return " ".join(text.casefold().split())


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate_suite(development: dict, holdout: dict, papers: list, chunks: list, *,
                   prior_questions: list[str], prior_support_papers: list[str]) -> dict:
    by_id = {paper["arxiv_id"]: paper for paper in papers}
    by_coord = {coordinate(chunk): chunk for chunk in chunks}
    _require(len(by_id) == len(papers) and len(by_coord) == len(chunks), "duplicate source coordinates")
    corpus = {"paper_count": len(papers), "chunk_count": len(chunks),
              "paper_digest": digest(sorted(papers, key=lambda p: p["arxiv_id"])),
              "chunk_digest": digest(sorted(chunks, key=coordinate))}
    seen_queries = {normalized_query(query) for query in prior_questions}
    seen_ids: set[str] = set()
    split_papers: dict[str, set[str]] = {}
    source_checks, negative_checks = 0, 0
    for dataset, split in ((development, "development"), (holdout, "holdout")):
        _require(dataset["split"] == split, "unexpected split")
        _require(all(dataset["corpus"].get(key) == value for key, value in corpus.items()), "source corpus fingerprint changed")
        kinds = Counter(case["kind"] for case in dataset["cases"])
        _require(dict(kinds) == EXPECTED_KINDS[split], "case counts do not match protocol")
        used_papers: set[str] = set()
        pairs: dict[str, list[dict]] = {}
        for case in dataset["cases"]:
            case_id, query = case["id"], case["query"]
            _require(isinstance(case_id, str) and bool(case_id) and case_id not in seen_ids, "duplicate or empty case ID")
            seen_ids.add(case_id)
            _require(isinstance(query, str) and 0 < len(query.strip()) <= 500, "invalid query")
            query_key = normalized_query(query)
            _require(query_key not in seen_queries, "question overlaps inspected/prior/split questions")
            seen_queries.add(query_key)
            supported = case["kind"] not in {"unsupported", "out_of_scope"}
            _require(case["answerable"] is supported, "answerability does not match case kind")
            _require(case["expected_scope"] == ("out" if case["kind"] == "out_of_scope" else "in"), "scope label mismatch")
            if case["kind"] in {"literal", "paraphrase"}:
                _require(bool(case.get("pair_id")), "missing pair identity")
                pairs.setdefault(case["pair_id"], []).append(case)
            facts = case["facts"]
            _require(all(isinstance(f.get("text"), str) and f["text"].strip() for f in facts), "missing fact text")
            fact_ids = {fact["id"] for fact in facts}
            _require(len(fact_ids) == len(facts), "duplicate fact IDs")
            if supported:
                _require(bool(facts) and bool(case["support"]), "positive case lacks reviewed facts/support")
                covered_facts: set[str] = set()
                support_papers: set[str] = set()
                unit_ids: set[str] = set()
                for unit in case["support"]:
                    _require(unit["id"] not in unit_ids and bool(unit["locators"]), "duplicate/empty support unit")
                    unit_ids.add(unit["id"])
                    _require(bool(unit["fact_ids"]) and set(unit["fact_ids"]) <= fact_ids, "invalid support fact mapping")
                    covered_facts.update(unit["fact_ids"])
                    for loc in unit["locators"]:
                        indexed = by_coord.get(coordinate(loc))
                        _require(indexed is not None, "support coordinate absent from source snapshot")
                        assert indexed is not None
                        _require(loc["section_title"] == indexed["section_title"], "support section title differs")
                        _require(hashlib.sha256(indexed["content"].encode()).hexdigest() == loc["chunk_sha256"],
                                 "support chunk fingerprint changed")
                        excerpt = _text(loc["source_excerpt"])
                        _require(bool(excerpt) and excerpt in _text(indexed["content"]), "support quote absent from indexed passage")
                        sections = by_id[loc["arxiv_id"]].get("sections") or []
                        _require(0 <= loc["section_index"] < len(sections), "stored source section absent")
                        _require(excerpt in _text(sections[loc["section_index"]]["content"]), "support quote absent from stored section")
                        support_papers.add(loc["arxiv_id"])
                        source_checks += 1
                _require(covered_facts == fact_ids, "required fact lacks reviewed source support")
                if case["kind"] == "multi_paper":
                    _require(len(support_papers) >= 2, "two-paper case requires separately attributed support")
                used_papers.update(support_papers)
            else:
                _require(not facts and not case["support"], "negative case must not carry supported facts")
                review = case["negative_review"]
                _require(bool(review["rationale"].strip()), "negative case lacks source-review rationale")
                scoped = set(review["scope_papers"])
                _require(scoped <= set(by_id), "negative source review names unknown paper")
                used_papers.update(scoped)
                reviewed = review["reviewed_sections"]
                for loc in reviewed:
                    _require(loc["arxiv_id"] in scoped and 0 <= loc["section_index"] < len(by_id[loc["arxiv_id"]]["sections"]),
                             "negative reviewed section is outside scope")
                if case["kind"] == "unsupported":
                    _require(bool(scoped) and bool(reviewed) and bool(review["scans"]), "unsupported case lacks bounded review")
                    for scan in review["scans"]:
                        term = _text(scan["term"])
                        _require(bool(term), "empty negative scan term")
                        section_hits = sum(term in _text(section["content"]) for pid in scoped
                                           for section in by_id[pid].get("sections") or [])
                        corpus_hits = sum(term in _text(chunk["content"]) for chunk in chunks)
                        _require(section_hits == scan["scope_section_hits"] and corpus_hits == scan["corpus_chunk_hits"],
                                 "negative source scan differs from frozen label")
                    negative_checks += 1
        for pair in pairs.values():
            _require(len(pair) == 2 and {c["kind"] for c in pair} == {"literal", "paraphrase"}, "invalid literal/paraphrase pair")
            _require(pair[0]["facts"] == pair[1]["facts"] and pair[0]["support"] == pair[1]["support"], "paired labels differ")
        _require(not used_papers & set(prior_support_papers), "split source overlaps previously inspected support papers")
        split_papers[split] = used_papers
    _require(not split_papers["development"] & split_papers["holdout"], "development/holdout source-paper overlap")
    return {"development_cases": len(development["cases"]), "holdout_cases": len(holdout["cases"]),
            "holdout_kinds": dict(Counter(c["kind"] for c in holdout["cases"])), "source_checks": source_checks,
            "negative_scan_checks": negative_checks, "development_papers": sorted(split_papers["development"]),
            "holdout_papers": sorted(split_papers["holdout"]), "corpus": corpus}


def _safe_file(root: Path, name: str) -> Path:
    _require(not PureWindowsPath(name).is_absolute() and not PureWindowsPath(name).drive
             and ".." not in PureWindowsPath(name).parts, "unsafe manifest path")
    path = (root / name).resolve(strict=True)
    _require(path.is_relative_to(root.resolve()), "manifest path escapes root")
    return path


def validate_freeze(manifest: dict, dataset_root: Path, repository_root: Path) -> int:
    verified = 0
    for root, fingerprints in ((dataset_root, manifest["sha256"]), (repository_root, manifest["prior_evaluation_sha256"])):
        for name, expected in fingerprints.items():
            actual = hashlib.sha256(_safe_file(root, name).read_bytes()).hexdigest()
            _require(actual == expected, "frozen file fingerprint differs")
            verified += 1
    return verified


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True, help="Read-only snapshot directory with papers.json/chunks.json")
    parser.add_argument("--dataset", type=Path, default=Path("evaluation/week7_agent"))
    args = parser.parse_args()

    def read(path: Path):
        return json.loads(path.read_text(encoding="utf-8"))

    manifest = read(args.dataset / "manifest.json")
    _require(set(manifest["sha256"]) == {"development.json", "holdout.json", "PROTOCOL.md", "SOURCE_REVIEW.md"},
             "manifest omits a required frozen label/review file")
    _require(read(args.snapshot / "state.json") == manifest["corpus_snapshot"], "source state/alias fingerprint differs")
    result = validate_suite(read(args.dataset / "development.json"), read(args.dataset / "holdout.json"),
                            read(args.snapshot / "papers.json"), read(args.snapshot / "chunks.json"),
                            prior_questions=manifest["prior_questions"], prior_support_papers=manifest["prior_support_papers"])
    result["frozen_files_verified"] = validate_freeze(manifest, args.dataset, Path.cwd())
    print(json.dumps({"verified": True, **result}, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
