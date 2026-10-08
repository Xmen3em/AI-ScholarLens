"""Validate saved collections and aggregate mechanical guards without model calls."""

import hashlib
import json
from pathlib import Path

from src.commands.evaluate_retrieval import digest, parse_sse, validate_reviews

OUT = Path("test_output/selector_reliability")
ROOT = Path("evaluation/selector_reliability")


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    initial = read(OUT / "initial.json")
    runs = {}
    for run in ("before", "after", "regression", "final", "string-regression", "string-initial"):
        folder = OUT / run
        path = folder / "records.jsonl"
        records = [json.loads(s) for s in path.read_text(encoding="utf-8").splitlines()]
        benchmark_path = (Path("evaluation/quality_fixes/regression.json") if run in ("regression", "string-regression")
                          else ROOT / ("final_holdout.json" if run == "final" else "holdout.json"))
        benchmark = read(benchmark_path)
        meta = read(folder / "metadata.json")
        reviews = read(folder / "semantic_reviews.json")
        assert len(records) == len(benchmark["cases"]) * 8
        assert len({r["key"] for r in records}) == len(records)
        assert meta["benchmark_digest"] == digest(benchmark)
        assert meta["before"] == meta["after"] == initial["state"]
        assert reviews["_meta"]["records_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
        validate_reviews(records, reviews)
        answers = [r for r in records if r["endpoint"] != "search"]
        success = [r for r in answers if r["ok"]]
        failures = [r for r in answers if not r["ok"]]
        checks = [c for r in success for c in r["audit"]["citation_checks"]]
        assert all(c["index_match"] and c["stored_section_match"] for c in checks)
        assert all(not r["audit"]["attribution_error"] and r["audit"]["words"] <= 200 for r in success)
        streams = [r for r in success if r["endpoint"] == "stream"]
        for row in streams:
            assert parse_sse(row["raw_sse"]) == row["response"]
        failed_streams = [r for r in failures if r["endpoint"] == "stream"]
        for row in failed_streams:
            events = [s for s in row["raw_sse"].splitlines() if s.startswith("event:")]
            assert events == ["event: sources", "event: error"], events
        runs[run] = dict(requests=len(records), answer_attempts=len(answers), successful_answers=len(success),
                         failures=len(failures), citation_records=len(checks), maximum_words=max(r["audit"]["words"] for r in success),
                         validated_successful_streams=len(streams), failed_streams_without_deltas_or_done=len(failed_streams),
                         corpus_snapshots_equal=True, benchmark_and_answer_review_hashes_valid=True)
    image = read(OUT / "image-source-string.json")
    mismatches = [p for p, h in image["hashes"].items() if hashlib.sha256(Path(p).read_bytes()).hexdigest() != h]
    assert not mismatches and image["candidates_per_passage"] == 1
    result = dict(runs=runs, total={k: sum(r[k] for r in runs.values()) for k in
                                   ("requests", "answer_attempts", "successful_answers", "failures", "citation_records",
                                    "validated_successful_streams", "failed_streams_without_deltas_or_done")},
                  maximum_words=max(r["maximum_words"] for r in runs.values()),
                  final_image_source_files=len(image["hashes"]), final_image_source_mismatches=mismatches,
                  final_image_candidate_default=image["candidates_per_passage"])
    (ROOT / "collection_audit.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
