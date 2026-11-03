"""Score paper-benchmark runs (no model calls): metrics, the decision rule, RAGAS export and the blind rubric."""

import argparse
import csv
import json
import math
import random
import statistics
import sys
from pathlib import Path

from src.commands.build_benchmark import DATA, FIELDS, ROOT, load_questions, write_json

FORMAT_FAILURES = {"study_response_invalid_or_unavailable", "review_validation_failed"}
ANSWERED = ("L", "Q1", "Q2")
FIRST_LESSON_QUESTION = "ابدأ درس تمهيدي متكامل عن الورقة."
GATE_FORMAT, GATE_P95, GATE_UNFAITHFUL, WIN_MARGIN = 0.95, 90.0, 0.02, 0.10
CHALLENGERS = ("baseline", "qwen-27b", "qwen-397b", "control")


def nearest_rank(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(q * len(ordered)) - 1)]


def _format_failed(row: dict) -> bool:
    return row["failure_code"] in FORMAT_FAILURES or row["diagnostic"] == "shape"


def _answers(row: dict) -> bool:
    # A delivered answer counts as answering only if it keeps a paper section; "the paper is silent" declines.
    return row["status"] == "ready" and any(section["kind"] == "paper" for section in (row["lesson"] or {}).get("sections", []))


def model_metrics(rows: list[dict]) -> dict:
    papers = {row["paper"] for row in rows}
    delivered = sum(row["status"] == "ready" for row in rows if row["job"] in ANSWERED)
    calls = sum(len(row["calls"]) for row in rows)
    # A format failure ends its job at the call that failed, so it is one failed call.
    format_failed = sum(_format_failed(row) for row in rows if row["status"] == "failed")
    reviews = [row["review"] for row in rows if row["review"]]
    withheld: dict[str, int] = {}
    for review in reviews:
        for reason, count in review.get("withheld", {}).items():
            withheld[reason] = withheld.get(reason, 0) + count
    q3 = [row for row in rows if row["job"] == "Q3" and row["status"] in {"ready", "failed"}
          and not _format_failed(row) and not str(row["failure_code"] or "").startswith("study_provider_http_")]
    declined = [row for row in q3 if row["failure_code"] == "lesson_validation_failed" or not _answers(row)]
    seconds = [float(row["seconds"]) for row in rows if row["status"] not in {"blocked", "stopped"} and row["seconds"] is not None]
    cost = sum(call["cost_usd"] for row in rows for call in row["calls"])
    failures: dict[str, int] = {}
    for row in rows:
        if row["status"] == "failed":
            failures[row["failure_code"]] = failures.get(row["failure_code"], 0) + 1
    return {
        "papers": len(papers),
        "delivered": delivered / (3 * len(papers)) if papers else 0.0,
        "format_compliance": 1 - format_failed / calls if calls else 0.0,
        "claims": sum(review.get("claims", 0) for review in reviews),
        "kept": sum(review.get("kept", 0) for review in reviews),
        "withheld": withheld,
        "q3_decline": len(declined) / len(q3) if q3 else 0.0,
        "q3_answered": sorted(row["paper"] for row in q3 if _answers(row)),
        "latency_median": statistics.median(seconds) if seconds else None,
        "latency_p95": nearest_rank(seconds, 0.95) if seconds else None,
        "cost_usd": cost,
        "cost_per_delivered": cost / delivered if delivered else None,
        "failures": failures,
        "blocked": sum(row["status"] == "blocked" for row in rows),
        "stopped": sum(row["status"] == "stopped" for row in rows),
    }


def _finite(value) -> float | None:
    # RAGAS can return NaN (for example an answer with no statements); NaN must never pass a gate.
    return float(value) if isinstance(value, (int, float)) and math.isfinite(value) else None


def decide(metrics: dict[str, dict], *, baseline: str = "baseline", judged: dict | None,
           owner_unfaithful: dict | None, rubric: dict | None = None) -> dict:
    calibrated = bool(judged and judged.get("calibrated"))

    def unfaithful(model: str):
        if calibrated:
            return _finite(judged["models"].get(model, {}).get("unfaithful"))  # type: ignore[index]
        return _finite((owner_unfaithful or {}).get(model))

    def factual(model: str) -> float:
        # Factual correctness is judge-made too, so it counts only when the judge passed calibration.
        return _finite(judged["models"].get(model, {}).get("factual")) or 0.0 if calibrated else 0.0  # type: ignore[index]

    reasons: dict[str, list[str]] = {}
    for model, values in metrics.items():
        problems = []
        if values["format_compliance"] < GATE_FORMAT:
            problems.append("format_compliance")
        if values["latency_p95"] is None or values["latency_p95"] > GATE_P95:
            problems.append("latency_p95")
        mine, theirs = unfaithful(model), unfaithful(baseline)
        if mine is None or theirs is None:
            problems.append("unfaithful_not_measured")
        elif mine > theirs + GATE_UNFAITHFUL:
            problems.append("unfaithful")
        reasons[model] = problems
    eligible = [model for model in metrics if not reasons[model]]
    eligible.sort(key=lambda model: (-metrics[model]["delivered"], -factual(model), -(rubric or {}).get(model, 0.0),
                                     metrics[model]["cost_per_delivered"] or float("inf")))
    choice = baseline
    best = next((model for model in eligible if model != baseline), None)
    if best is not None and baseline in metrics:
        gain = metrics[best]["delivered"] - metrics[baseline]["delivered"]
        if gain >= WIN_MARGIN - 1e-9 or factual(best) - factual(baseline) >= WIN_MARGIN - 1e-9:
            choice = best
    return {"choice": choice, "eligible": eligible, "reasons": reasons}


def _answer(lesson: dict) -> str:
    return " ".join(section["text"] for section in lesson["sections"] if section["kind"] == "paper")


def ragas_rows(rows: list[dict], questions: dict, model: str) -> list[dict]:
    exported = []
    for row in rows:
        if row["job"] not in ANSWERED or row["status"] != "ready" or not row["lesson"]:
            continue
        reference = None
        if row["job"] != "L":
            reference = " ".join(fact["fact"] for fact in questions["papers"][row["paper"]][row["job"]]["facts"])
        exported.append({"model": model, "paper": row["paper"], "job": row["job"],
                         "question": FIRST_LESSON_QUESTION if row["job"] == "L" else row["question"],
                         "answer": _answer(row["lesson"]), "contexts": row["contexts"], "reference": reference})
    return exported


def rubric_sheet(rows_by_model: dict[str, list[dict]], papers: dict, seed: int = 20261103) -> tuple[str, dict]:
    chosen = []
    for field in FIELDS:
        holdout = [row["id"] for row in papers["papers"] if row["field"] == field and row["split"] == "holdout"]
        if holdout:
            chosen.append(holdout[0])
    items = []
    for model, rows in rows_by_model.items():
        lessons = {row["paper"]: row for row in rows if row["job"] == "L"}
        items += [(model, paper, lessons.get(paper)) for paper in chosen]
    random.Random(seed).shuffle(items)
    lines = ["# Blind lesson rubric", "", "Rate each lesson 1-5 for Arabic clarity and for teaching value.",
             "Fill rubric-scores.csv with columns: code,clarity,teaching", ""]
    key = {}
    for index, (model, paper, row) in enumerate(items, 1):
        code = f"R{index:02}"
        key[code] = {"model": model, "paper": paper}
        lines += [f"## {code}", ""]
        if row and row["status"] == "ready" and row["lesson"]:
            lines.append("**" + row["lesson"]["title"] + "**")
            for section in row["lesson"]["sections"]:
                lines += ["", "### " + section["heading"], "", section["text"]]
        else:
            lines.append("(no lesson was delivered)")
        lines.append("")
    return chr(10).join(lines), key


def rubric_means(scores_path: Path, key: dict) -> dict[str, float]:
    totals: dict[str, list[float]] = {}
    with scores_path.open(encoding="utf-8", newline="") as handle:
        for entry in csv.DictReader(handle):
            model = key[entry["code"]]["model"]
            totals.setdefault(model, []).append((float(entry["clarity"]) + float(entry["teaching"])) / 2)
    return {model: statistics.mean(values) for model, values in totals.items()}


def judged_summary(path: Path, calibration: Path) -> dict:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    models: dict[str, dict] = {}
    for model in {row["model"] for row in rows}:
        mine = [row for row in rows if row["model"] == model]
        raw = [row.get(key) for row in mine for key in ("faithfulness", "factual_correctness") if key in row]
        faithful = [value for value in (_finite(row.get("faithfulness")) for row in mine) if value is not None]
        factual = [value for value in (_finite(row.get("factual_correctness")) for row in mine) if value is not None]
        models[model] = {"unfaithful": 1 - statistics.mean(faithful) if faithful else None,
                         "factual": statistics.mean(factual) if factual else None,
                         "dropped": len(raw) - len(faithful) - len(factual)}
    calibrated = calibration.exists() and json.loads(calibration.read_text(encoding="utf-8")).get("calibrated") is True
    return {"calibrated": calibrated, "models": models}


def _load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", default="holdout")
    parser.add_argument("--export-ragas", action="store_true")
    parser.add_argument("--rubric-sheet", action="store_true")
    parser.add_argument("--rubric-scores", type=Path)
    parser.add_argument("--judged", type=Path)
    parser.add_argument("--owner-unfaithful", type=Path, help="JSON {model: rate} from the owner's reading")
    args = parser.parse_args(argv)
    rows_by_model = {model: _load(DATA / f"{args.stage}-{model}" / "jobs.jsonl") for model in CHALLENGERS
                     if (DATA / f"{args.stage}-{model}" / "jobs.jsonl").exists()}
    if not rows_by_model:
        raise SystemExit("no runs found for stage " + args.stage)
    metrics = {model: model_metrics(rows) for model, rows in rows_by_model.items()}
    papers = json.loads((ROOT / "papers.v1.json").read_text(encoding="utf-8"))
    if args.export_ragas:
        questions = load_questions()
        with (DATA / "ragas-input.jsonl").open("w", encoding="utf-8", newline="") as handle:
            for model, rows in rows_by_model.items():
                for item in ragas_rows(rows, questions, model):
                    handle.write(json.dumps(item, ensure_ascii=False) + chr(10))
    if args.rubric_sheet:
        sheet, key = rubric_sheet(rows_by_model, papers)
        (DATA / "rubric.md").write_text(sheet, encoding="utf-8", newline="")
        write_json(DATA / "rubric-key.json", key)
    rubric = None
    if args.rubric_scores:
        rubric = rubric_means(args.rubric_scores, json.loads((DATA / "rubric-key.json").read_text(encoding="utf-8")))
    judged = judged_summary(args.judged, DATA / "calibration-result.json") if args.judged else None
    owner = json.loads(args.owner_unfaithful.read_text(encoding="utf-8")) if args.owner_unfaithful else None
    decision = decide(metrics, judged=judged, owner_unfaithful=owner, rubric=rubric)
    write_json(DATA / f"{args.stage}-metrics.json", {"metrics": metrics, "judged": judged, "rubric": rubric,
                                                      "decision": decision})
    print(json.dumps(decision, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
