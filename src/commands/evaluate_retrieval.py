"""Read-only live benchmark collector and judged-evidence metrics.

Run with python -m src.commands.evaluate_retrieval --help. No application writes.
Semantic answer judgments are deliberately reviewed separately from attribution.
"""

import argparse
import hashlib
import json
import math
import time
from pathlib import Path
from typing import Any

import httpx
from src.schemas.api.rag import Citation
from src.services.rag.context import INSUFFICIENT_EVIDENCE_ANSWER, validate_answer_evidence
from src.services.rag.excerpts import MIN_QUERY_COVERAGE, _terms, build_excerpts


def coordinate(item: dict, arxiv_id: str | None = None) -> tuple:
    return (arxiv_id or item["arxiv_id"], item["section_index"], item["chunk_index"])


def retrieval_metrics(case: dict, hits: list, k: int) -> dict | None:
    """Score reviewed evidence units, never title matches or citation markers."""
    if not case["support"]:
        return None
    units = [{coordinate(loc) for loc in unit["locators"]} for unit in case["support"]]
    ranks = []
    seen = set()
    paper_gains = []
    for rank, paper in enumerate(hits[:k], 1):
        coords = {coordinate(p, paper["arxiv_id"]) for p in paper["passages"]}
        found = {i for i, unit in enumerate(units) if unit & coords}
        seen.update(found)
        if found:
            ranks.append(rank)
            paper_gains.append(1 / math.log2(rank + 1))
    ideal_papers = len({loc[0] for unit in units for loc in unit})
    ideal = sum(1 / math.log2(rank + 1) for rank in range(1, min(k, ideal_papers) + 1))
    return {
        "hit": int(bool(ranks)),
        "recall": len(seen) / len(units),
        "mrr": 1 / ranks[0] if ranks else 0,
        "ndcg": sum(paper_gains) / ideal,
    }


def parse_sse(raw: str) -> dict:
    events = []
    for block in raw.replace("\r\n", "\n").split("\n\n"):
        fields = block.splitlines()
        names = [line[6:].strip() for line in fields if line.startswith("event:")]
        data = [line[5:].strip() for line in fields if line.startswith("data:")]
        if names and data:
            events.append((names[0], json.loads("\n".join(data))))
    if any(name == "error" for name, _ in events):
        raise ValueError("stream error event")
    sources = [data for name, data in events if name == "sources"]
    done = [data for name, data in events if name == "done"]
    if len(sources) != 1 or len(done) != 1:
        raise ValueError("stream requires one sources and one done event")
    if events[0][0] != "sources" or events[-1][0] != "done":
        raise ValueError("stream event ordering")
    deltas = "".join(data["delta"] for name, data in events if name == "delta")
    if deltas != done[0]["answer"] and not (not deltas and done[0]["answer"] == INSUFFICIENT_EVIDENCE_ANSWER):
        raise ValueError("stream deltas differ from done answer")
    return {**sources[0], **done[0]}


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def validate_reviews(records: list, reviews: dict) -> None:
    """Prevent semantic judgments from being reused for different model outputs."""
    for record in records:
        if record["endpoint"] == "search" or not record["ok"]:
            continue
        review = reviews[record["key"]]
        answer_digest = hashlib.sha256(record["response"]["answer"].encode()).hexdigest()
        if review["answer_digest"] != answer_digest:
            raise ValueError(f"reviewed answer changed: {record['key']}")


def snapshot(client: httpx.Client, api: str, search: str) -> tuple[dict, list, list]:
    def get(url: str) -> Any:
        response = client.get(url)
        response.raise_for_status()
        return response.json()

    papers = get(api + "/papers/?limit=100")["papers"]
    response = client.post(
        search + "/paper-chunks/_search", json={"size": 10000, "query": {"match_all": {}}, "_source": {"excludes": ["embedding"]}}
    )
    response.raise_for_status()
    chunks = [hit["_source"] for hit in response.json()["hits"]["hits"]]
    state = {
        "paper_count": len(papers),
        "chunk_count": len(chunks),
        "alias": get(search + "/_alias/paper-chunks"),
        "v1_count": get(search + "/paper-chunks-v1/_count")["count"],
        "paper_digest": digest(sorted(papers, key=lambda p: p["arxiv_id"])),
        "chunk_digest": digest(sorted(chunks, key=coordinate)),
    }
    return state, papers, chunks


def audit_answer(response: dict, case: dict, chunks: list, papers: list) -> dict:
    citations = [Citation.model_validate(c) for c in response["citations"]]
    by_coord = {coordinate(c): c for c in chunks}
    by_id = {p["arxiv_id"]: p for p in papers}
    citation_checks = []
    for citation in citations:
        item = citation.model_dump()
        stored = by_coord.get(coordinate(item))
        section = by_id.get(citation.arxiv_id, {}).get("sections") or []
        section_text = section[citation.section_index].get("content", "") if citation.section_index < len(section) else ""
        normalized = " ".join(citation.evidence.split())
        citation_checks.append(
            {
                "coordinate": coordinate(item),
                "index_match": bool(stored and stored["content"] == citation.evidence),
                "stored_section_match": normalized in " ".join(section_text.split()),
            }
        )
    try:
        validate_answer_evidence(response["answer"], citations)
        attribution_error = None
    except ValueError as exc:
        attribution_error = str(exc)
    candidates = build_excerpts(citations, case["query"])
    terms = _terms(case["query"])
    coverage = {}
    for aid in {c.arxiv_id for c in citations}:
        available = _terms(" ".join(c.evidence for c in citations if c.arxiv_id == aid))
        coverage[aid] = len(terms & available) / len(terms) if terms else 0
    context_coords = {coordinate(c.model_dump()) for c in citations}
    return {
        "words": len(response["answer"].split()),
        "abstained": response["answer"] == INSUFFICIENT_EVIDENCE_ANSWER,
        "attribution_error": attribution_error,
        "citation_checks": citation_checks,
        "support_in_context": [bool(context_coords & {coordinate(loc) for loc in u["locators"]}) for u in case["support"]],
        "paper_query_coverage": coverage,
        "lexically_eligible": [a for a, c in coverage.items() if c >= MIN_QUERY_COVERAGE],
        "candidates": {key: {"text": value.text, "marker": value.marker} for key, value in candidates.items()},
    }


def collect(args: argparse.Namespace) -> None:
    benchmark = json.loads(args.benchmark.read_text(encoding="utf-8"))
    args.output.mkdir(parents=True, exist_ok=True)
    fingerprint = digest(benchmark)
    meta_path = args.output / "metadata.json"
    records_path = args.output / "records.jsonl"
    with httpx.Client(timeout=args.timeout) as client:
        before, papers, chunks = snapshot(client, args.api, args.search)
        expected = benchmark["corpus"]
        if (before["paper_count"], before["chunk_count"], before["v1_count"], list(before["alias"])) != (
            expected["papers"],
            expected["chunks"],
            expected["preserved_v1_chunks"],
            [expected["alias_target"]],
        ):
            raise ValueError("corpus differs from the benchmark; review labels before collecting")
        for case in benchmark["cases"]:
            for unit in case["support"]:
                for loc in unit["locators"]:
                    source = next(c for c in chunks if coordinate(c) == coordinate(loc))
                    if source["content"] != loc["source_excerpt"]:
                        raise ValueError(f"reviewed evidence changed: {case['id']}")
        if meta_path.exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if meta["benchmark_digest"] != fingerprint or meta["before"] != before:
                raise ValueError("cannot resume with changed labels or corpus")
        else:
            meta = {
                "benchmark_digest": fingerprint,
                "before": before,
                "api": args.api,
                "search": args.search,
                "timeout": args.timeout,
                "started_unix": time.time(),
                "models": client.get("http://localhost:11434/api/tags").json(),
            }
            meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        (args.output / "corpus.json").write_text(json.dumps({"papers": papers}), encoding="utf-8")
        (args.output / "chunks.json").write_text(json.dumps(chunks), encoding="utf-8")
        records = (
            [json.loads(line) for line in records_path.read_text(encoding="utf-8").splitlines()] if records_path.exists() else []
        )
        completed = {r["key"] for r in records}
        # Finish retrieval first, then endpoints. Every call is serial.
        jobs = [(case, mode, "search", k) for case in benchmark["cases"] for mode in ("bm25", "hybrid") for k in (3, 5)]
        jobs += [
            (case, mode, endpoint, 3)
            for case in benchmark["cases"]
            for mode in ("bm25", "hybrid")
            for endpoint in ("ask", "stream")
        ]
        for case, mode, endpoint, k in jobs:
            key = f"{case['id']}:{mode}:{endpoint}:{k}"
            if key in completed:
                continue
            record: dict[str, Any] = {"key": key, "case_id": case["id"], "requested_mode": mode, "endpoint": endpoint, "k": k}
            started = time.perf_counter()
            try:
                if endpoint == "search":
                    route = "/search/hybrid" if mode == "hybrid" else "/search/chunks"
                    result = client.post(args.api + route, json={"query": case["query"], "size": k})
                    record["status_code"] = result.status_code
                    result.raise_for_status()
                    response = result.json()
                    record["metrics"] = retrieval_metrics(case, response["hits"], k)
                else:
                    payload = {"query": case["query"], "top_k": k, "use_hybrid": mode == "hybrid"}
                    if endpoint == "ask":
                        result = client.post(args.api + "/ask", json=payload)
                        record["status_code"] = result.status_code
                        result.raise_for_status()
                        response = result.json()
                    else:
                        lines = []
                        current_event = ""
                        with client.stream("POST", args.api + "/stream", json=payload) as result:
                            record["status_code"] = result.status_code
                            result.raise_for_status()
                            for line in result.iter_lines():
                                lines.append(line)
                                if line.startswith("event:"):
                                    current_event = line[6:].strip()
                                    record.setdefault("first_event_seconds", time.perf_counter() - started)
                                    if current_event == "delta":
                                        record.setdefault("first_delta_seconds", time.perf_counter() - started)
                        record["raw_sse"] = "\n".join(lines) + "\n\n"
                        response = parse_sse(record["raw_sse"])
                    record["audit"] = audit_answer(response, case, chunks, papers)
                record["response"] = response
                record["ok"] = True
            except Exception as exc:
                record["ok"] = False
                record["error"] = f"{type(exc).__name__}: {exc}"
                if endpoint == "search":
                    record["metrics"] = retrieval_metrics(case, [], k)
            record["seconds"] = time.perf_counter() - started
            with records_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            print(f"{key} ok={record['ok']} seconds={record['seconds']:.2f}", flush=True)
        after, _, _ = snapshot(client, args.api, args.search)
        meta.update(after=after, corpus_unchanged=before == after, finished_unix=time.time())
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        if before != after:
            raise ValueError("corpus changed during evaluation")


def summarize(benchmark: dict, records: list, reviews: dict) -> dict:
    """Combine independent semantic reviews with mechanical endpoint audits."""
    cases = {c["id"]: c for c in benchmark["cases"]}
    result: dict[str, Any] = {"retrieval": {}, "answers": {}}
    for mode in ("bm25", "hybrid"):
        for k in (3, 5):
            rows = [r for r in records if r["endpoint"] == "search" and r["requested_mode"] == mode and r["k"] == k]
            supported = [r for r in rows if cases[r["case_id"]]["answerable"]]
            result["retrieval"][f"{mode}@{k}"] = {
                **{m: sum(r["metrics"][m] for r in supported) / len(supported) for m in ("hit", "recall", "mrr", "ndcg")},
                "supported_n": len(supported),
                **operational(rows),
            }
        for endpoint in ("ask", "stream"):
            rows = [r for r in records if r["endpoint"] == endpoint and r["requested_mode"] == mode]
            positive = [r for r in rows if cases[r["case_id"]]["answerable"]]
            negative = [r for r in rows if not cases[r["case_id"]]["answerable"]]
            paraphrases = [r for r in positive if cases[r["case_id"]]["kind"] == "paraphrase"]
            success = [r for r in rows if r["ok"]]
            abstains = lambda rs: sum(r["ok"] and r["audit"]["abstained"] for r in rs)
            substantive = [r for r in success if not r["audit"]["abstained"]]
            for r in success:
                review = reviews[r["key"]]
                known = {f["id"] for f in cases[r["case_id"]]["facts"]}
                if not set(review["covered_facts"]) <= known or not 0 <= review["relevant_excerpts"] <= review["total_excerpts"]:
                    raise ValueError("invalid semantic review")
            covered = sum(
                len(set(reviews[r["key"]]["covered_facts"])) / len(cases[r["case_id"]]["facts"]) for r in positive if r["ok"]
            )
            total_excerpts = sum(reviews[r["key"]]["total_excerpts"] for r in substantive)
            result["answers"][f"{mode}/{endpoint}"] = {
                **operational(rows),
                "supported_n": len(positive),
                "unsupported_n": len(negative),
                "false_abstentions": abstains(positive),
                "paraphrase_false_abstentions": abstains(paraphrases),
                "paraphrase_n": len(paraphrases),
                "correct_abstentions": abstains(negative),
                "abstention_decision_accuracy": (
                    sum(r["ok"] and not r["audit"]["abstained"] for r in positive) + abstains(negative)
                )
                / len(rows),
                "unsupported_substantive": sum(r["ok"] and not r["audit"]["abstained"] for r in negative),
                "mean_fact_coverage": covered / len(positive),
                "excerpt_relevance": sum(reviews[r["key"]]["relevant_excerpts"] for r in substantive) / total_excerpts
                if total_excerpts
                else None,
                "substantive_n": len(substantive),
                "word_limit_violations": sum(r["audit"]["words"] > 200 for r in success),
                "attribution_failures": sum(r["audit"]["attribution_error"] is not None for r in success),
                "citation_audit_failures": sum(
                    not c["index_match"] or not c["stored_section_match"] for r in success for c in r["audit"]["citation_checks"]
                ),
            }
    result["endpoint_consistency"] = {}
    for mode in ("bm25", "hybrid"):
        paired = []
        for case in benchmark["cases"]:
            rows = [
                r for r in records if r["case_id"] == case["id"] and r["requested_mode"] == mode and r["endpoint"] != "search"
            ]
            if len(rows) == 2 and all(r["ok"] for r in rows):
                paired.append(rows)
        result["endpoint_consistency"][mode] = {
            "both_successful": len(paired),
            "total_pairs": len(benchmark["cases"]),
            "same_answer": sum(a["response"]["answer"] == b["response"]["answer"] for a, b in paired),
            "same_abstention": sum(a["audit"]["abstained"] == b["audit"]["abstained"] for a, b in paired),
            "same_citation_coordinates": sum(
                [coordinate(c) for c in a["response"]["citations"]] == [coordinate(c) for c in b["response"]["citations"]]
                for a, b in paired
            ),
            "same_effective_mode": sum(a["response"]["search_mode"] == b["response"]["search_mode"] for a, b in paired),
        }
    return result


def operational(rows: list) -> dict:
    seconds = sorted(r["seconds"] for r in rows)
    return {
        "n": len(rows),
        "failures": sum(not r["ok"] for r in rows),
        "median_seconds": (seconds[(len(seconds) - 1) // 2] + seconds[len(seconds) // 2]) / 2,
        "p95_seconds": seconds[math.ceil(0.95 * len(seconds)) - 1],
        "fallbacks": sum(
            r.get("response", {}).get("mode") == "keyword"
            or (r["requested_mode"] == "hybrid" and r.get("response", {}).get("search_mode") == "bm25")
            for r in rows
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", type=Path, default=Path("evaluation/benchmark.json"))
    parser.add_argument("--output", type=Path, default=Path("test_output/retrieval_eval/run-v1"))
    parser.add_argument("--api", default="http://localhost:8000/api/v1")
    parser.add_argument("--search", default="http://localhost:9200")
    parser.add_argument("--timeout", type=float, default=240)
    parser.add_argument("--score", action="store_true", help="Score saved records using semantic_reviews.json; no network")
    args = parser.parse_args()
    if args.score:
        benchmark = json.loads(args.benchmark.read_text(encoding="utf-8"))
        metadata = json.loads((args.output / "metadata.json").read_text(encoding="utf-8"))
        if metadata["benchmark_digest"] != digest(benchmark):
            raise ValueError("benchmark changed after collection")
        records = [json.loads(line) for line in (args.output / "records.jsonl").read_text(encoding="utf-8").splitlines()]
        if len(records) != len(benchmark["cases"]) * 8 or len({r["key"] for r in records}) != len(records):
            raise ValueError("incomplete or duplicate evaluation records")
        reviews = json.loads((args.output / "semantic_reviews.json").read_text(encoding="utf-8"))
        records_digest = hashlib.sha256((args.output / "records.jsonl").read_bytes()).hexdigest()
        if reviews["_meta"]["records_sha256"] != records_digest:
            raise ValueError("semantic reviews belong to different collected records")
        validate_reviews(records, reviews)
        summary = summarize(benchmark, records, reviews)
        (args.output / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(json.dumps(summary, indent=2))
    else:
        collect(args)


if __name__ == "__main__":
    main()
