"""Bind explicit source/semantic annotations to each exact saved answer and run."""

import argparse
import hashlib
import json
from pathlib import Path

from src.commands.evaluate_retrieval import summarize, validate_reviews

ROOT = Path("evaluation/selector_reliability")
OUT = Path("test_output/selector_reliability")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("run", choices=("before", "after", "regression", "final", "string-regression", "string-initial"))
    args = parser.parse_args()
    folder = OUT / args.run
    benchmark_path = (Path("evaluation/quality_fixes/regression.json") if args.run in ("regression", "string-regression")
                      else ROOT / ("final_holdout.json" if args.run == "final" else "holdout.json"))
    benchmark = json.loads(benchmark_path.read_text(encoding="utf-8"))
    cases = {c["id"]: c for c in benchmark["cases"]}
    path = folder / "records.jsonl"
    records = [json.loads(s) for s in path.read_text(encoding="utf-8").splitlines()]
    annotations = json.loads((ROOT / f"annotations.{args.run}.json").read_text(encoding="utf-8"))
    reviews = {"_meta": {"records_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                         "reviewer": "Codex source/semantic review; all distinct successful answers inspected",
                         "reviewed_on": "2026-10-08"}}
    for row in records:
        if row["endpoint"] == "search" or not row["ok"]:
            continue
        case = cases[row["case_id"]]
        if row["audit"]["abstained"]:
            annotation = dict(facts=[], relevant=0, rationale="False abstention on supported evidence." if case["answerable"] else "Correct unsupported abstention.")
        else:
            annotation = annotations[row["case_id"] + ":" + row["requested_mode"] + ":" + row["endpoint"]] if row["case_id"] + ":" + row["requested_mode"] + ":" + row["endpoint"] in annotations else annotations[row["case_id"] + ":" + row["requested_mode"]]
        reviews[row["key"]] = dict(answer_digest=hashlib.sha256(row["response"]["answer"].encode()).hexdigest(),
                                   covered_facts=[case["facts"][i-1]["id"] for i in annotation["facts"]],
                                   relevant_excerpts=annotation["relevant"], total_excerpts=0 if row["audit"]["abstained"] else len(row["response"]["answer"].splitlines()),
                                   rationale=annotation["rationale"])
    assert len(records) == len(cases) * 8
    assert len({r["key"] for r in records}) == len(records)
    validate_reviews(records, reviews)
    summary = summarize(benchmark, records, reviews)
    for target in (folder / "semantic_reviews.json", ROOT / f"reviews.{args.run}.json"):
        target.write_text(json.dumps(reviews, indent=2), encoding="utf-8")
    for target in (folder / "summary.json", ROOT / f"results.{args.run}.json"):
        target.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
