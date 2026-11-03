import pytest
from src.commands.score_study import decide, model_metrics, nearest_rank, ragas_rows, rubric_sheet


def row(paper, job, status, *, failure=None, diagnostic=None, seconds=10.0, calls=2, cost=0.01, review=None,
        lesson=None, contexts=(), question="q"):
    states = [] if status in {"blocked", "stopped"} else [
        {"purpose": "lesson", "state": "succeeded" if status == "ready" else "unknown", "usage": None, "cost_usd": cost}
    ] * calls
    return {"paper": paper, "job": job, "status": status, "failure_code": failure, "diagnostic": diagnostic,
            "stage": None, "review": review, "seconds": None if status in {"blocked", "stopped"} else seconds,
            "calls": states, "lesson": lesson, "contexts": list(contexts), "question": question}


LESSON = {"title": "t", "sections": [
    {"heading": "الفكرة", "kind": "paper", "text": "الطريقة بتستخدم attention.", "evidence": []},
    {"heading": "تشبيه", "kind": "analogy", "text": "زي المكتبة.", "evidence": []}]}
REVIEW = {"claims": 3, "kept": 2, "withheld": {"unsupported": 1}}


def two_papers():
    # Paper a: everything delivered, Q3 declined. Paper b: the first lesson failed on format, so follow-ups are blocked.
    return [
        row("a", "L", "ready", seconds=20, review=REVIEW, lesson=LESSON, contexts=["ctx"]),
        row("a", "Q1", "ready", seconds=30, review=REVIEW, lesson=LESSON),
        row("a", "Q2", "ready", seconds=40, review={"claims": 1, "kept": 1, "withheld": {}}, lesson=LESSON),
        row("a", "Q3", "failed", failure="lesson_validation_failed", seconds=50, review={"claims": 1, "kept": 0,
                                                                                         "withheld": {"unsupported": 1}}),
        row("b", "L", "failed", failure="study_response_invalid_or_unavailable", diagnostic="incomplete_output",
            seconds=60, calls=1),
        row("b", "Q1", "blocked"), row("b", "Q2", "blocked"), row("b", "Q3", "blocked"),
    ]


def test_nearest_rank():
    assert nearest_rank([float(value) for value in range(1, 21)], 0.95) == 19
    assert nearest_rank([5.0], 0.95) == 5


def test_model_metrics_match_hand_counts():
    metrics = model_metrics(two_papers())
    assert metrics["delivered"] == pytest.approx(3 / 6)
    assert metrics["format_compliance"] == pytest.approx(1 - 1 / 9)  # 9 calls made, one format failure
    assert metrics["claims"] == 8 and metrics["kept"] == 5
    assert metrics["withheld"] == {"unsupported": 3}
    assert metrics["q3_decline"] == pytest.approx(1.0) and metrics["q3_answered"] == []
    assert metrics["latency_median"] == 40 and metrics["latency_p95"] == 60
    assert metrics["cost_usd"] == pytest.approx(0.09) and metrics["cost_per_delivered"] == pytest.approx(0.03)
    assert metrics["failures"] == {"lesson_validation_failed": 1, "study_response_invalid_or_unavailable": 1}
    assert metrics["blocked"] == 3


def test_a_q3_with_a_kept_claim_is_listed_for_reading():
    rows = two_papers()
    rows[3] = row("a", "Q3", "ready", review={"claims": 1, "kept": 1, "withheld": {}}, lesson=LESSON)
    metrics = model_metrics(rows)
    assert metrics["q3_decline"] == 0 and metrics["q3_answered"] == ["a"]


def base(**changes):
    return {"delivered": 0.6, "format_compliance": 0.99, "latency_p95": 30.0, "cost_per_delivered": 0.01, **changes}


JUDGED = {"calibrated": True, "models": {"baseline": {"unfaithful": 0.10, "factual": 0.50},
                                        "qwen": {"unfaithful": 0.11, "factual": 0.55}}}


def test_baseline_stays_without_a_clear_win():
    result = decide({"baseline": base(), "qwen": base(delivered=0.65)}, judged=JUDGED, owner_unfaithful=None)
    assert result["choice"] == "baseline" and set(result["eligible"]) == {"baseline", "qwen"}


def test_challenger_wins_with_ten_points_more_delivered():
    result = decide({"baseline": base(), "qwen": base(delivered=0.71)}, judged=JUDGED, owner_unfaithful=None)
    assert result["choice"] == "qwen"


def test_slow_or_unfaithful_challengers_are_ineligible():
    slow = decide({"baseline": base(), "qwen": base(delivered=0.9, latency_p95=95.0)}, judged=JUDGED, owner_unfaithful=None)
    assert slow["choice"] == "baseline" and "latency_p95" in slow["reasons"]["qwen"]
    judged = {"calibrated": True, "models": {**JUDGED["models"], "qwen": {"unfaithful": 0.13, "factual": 0.9}}}
    unfaithful = decide({"baseline": base(), "qwen": base(delivered=0.9)}, judged=judged, owner_unfaithful=None)
    assert unfaithful["choice"] == "baseline" and "unfaithful" in unfaithful["reasons"]["qwen"]


def test_uncalibrated_judge_falls_back_to_owner_reading():
    judged = {**JUDGED, "calibrated": False}
    result = decide({"baseline": base(), "qwen": base(delivered=0.9)}, judged=judged,
                    owner_unfaithful={"baseline": 0.05, "qwen": 0.06})
    assert result["choice"] == "qwen"


def test_unmeasured_faithfulness_blocks_a_switch():
    result = decide({"baseline": base(), "qwen": base(delivered=0.9)}, judged=None, owner_unfaithful=None)
    assert result["choice"] == "baseline"
    assert "unfaithful_not_measured" in result["reasons"]["qwen"]


def test_ragas_export_keeps_only_kept_paper_claims():
    questions = {"papers": {"a": {"Q1": {"facts": [{"fact": "Fact one."}, {"fact": "Fact two."}]},
                                  "Q2": {"facts": [{"fact": "Method fact."}]}, "Q3": {}}}}
    exported = ragas_rows(two_papers(), questions, "qwen")
    assert [(item["paper"], item["job"]) for item in exported] == [("a", "L"), ("a", "Q1"), ("a", "Q2")]
    assert exported[0]["answer"] == "الطريقة بتستخدم attention." and exported[0]["reference"] is None
    assert exported[0]["contexts"] == ["ctx"] and "زي المكتبة" not in exported[0]["answer"]
    assert exported[1]["reference"] == "Fact one. Fact two." and exported[1]["model"] == "qwen"


def test_rubric_sheet_hides_models_and_keys_every_code():
    papers = {"papers": [{"id": f"p{index}", "field": field, "split": "holdout"}
                         for index, field in enumerate(("ml_nlp", "medicine", "physics", "biology", "economics", "systems"))]}
    rows_by_model = {model: [row(f"p{index}", "L", "ready", lesson=LESSON) for index in range(6)]
                     for model in ("baseline", "qwen-27b", "qwen-397b", "control")}
    sheet, key = rubric_sheet(rows_by_model, papers)
    assert len(key) == 24 and sheet.count("## R") == 24
    for model in rows_by_model:
        assert model not in sheet
    assert {entry["model"] for entry in key.values()} == set(rows_by_model)


def test_non_finite_judge_scores_are_dropped_not_averaged(tmp_path):
    import json
    import math

    from src.commands.score_study import judged_summary

    judged = tmp_path / "judged.jsonl"
    rows = [{"model": "qwen", "faithfulness": math.nan}, {"model": "qwen", "faithfulness": 0.8, "factual_correctness": math.nan},
            {"model": "qwen", "faithfulness": 0.6, "factual_correctness": 0.5}]
    judged.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
    summary = judged_summary(judged, tmp_path / "missing.json")["models"]["qwen"]
    assert summary["unfaithful"] == pytest.approx(0.3) and summary["factual"] == pytest.approx(0.5)
    assert summary["dropped"] == 2


def test_a_nan_rate_cannot_pass_the_faithfulness_gate():
    import math

    judged = {"calibrated": True, "models": {"baseline": {"unfaithful": 0.10, "factual": 0.5},
                                            "qwen": {"unfaithful": math.nan, "factual": math.nan}}}
    result = decide({"baseline": base(), "qwen": base(delivered=0.9)}, judged=judged, owner_unfaithful=None)
    assert result["choice"] == "baseline" and "unfaithful_not_measured" in result["reasons"]["qwen"]
