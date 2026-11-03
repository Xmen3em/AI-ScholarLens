import json
import subprocess
import sys

import httpx
import pytest
from src.commands.judge_study import agreement, calibrated, calibration_rows, score_rows

ROWS = [
    {"model": "qwen", "paper": "a", "job": "L", "question": "q", "answer": "ans", "contexts": ["ctx"], "reference": None},
    {"model": "qwen", "paper": "a", "job": "Q1", "question": "q1", "answer": "ans", "contexts": ["ctx"], "reference": "ref"},
]


@pytest.mark.asyncio
async def test_lessons_get_faithfulness_and_answers_get_all_three():
    async def metric(value):
        async def score(row):
            return value
        return score

    metrics = {"faithfulness": await metric(0.9), "factual_correctness": await metric(0.5), "context_recall": await metric(1.0)}
    scored = await score_rows(ROWS, metrics)
    assert scored[0] == {**ROWS[0], "faithfulness": 0.9}
    assert scored[1] == {**ROWS[1], "faithfulness": 0.9, "factual_correctness": 0.5, "context_recall": 1.0}


def test_agreement_and_kappa_by_hand():
    result = agreement([True, True, False, False], [True, False, False, False])
    assert result == {"agreement": pytest.approx(0.75), "kappa": pytest.approx(0.5), "n": 4}
    assert calibrated(result) is False
    assert calibrated({"agreement": 0.9, "kappa": 0.7, "n": 40}) is True
    assert agreement([True] * 4, [True] * 4)["kappa"] == 1.0


def test_calibration_starts_from_the_science_cases():
    rows = calibration_rows()
    assert len(rows) == 16
    assert all(row["claim_ar"] and row["quote_en"] and row["owner_faithful"] is None for row in rows)


def test_importing_the_judge_does_not_import_ragas():
    code = "import sys, src.commands.judge_study; print('ragas' in sys.modules)"
    output = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout
    assert json.loads(output.strip().lower()) is False


def judge_profile():
    from src.services.study.models import ModelProfile

    return ModelProfile("judge", "deepseek-ai/DeepSeek-V4-Pro:deepinfra", "utf8_bytes_div_3", {}, 1.30, 2.60, "2026-11-03")


def usage_body(usage):
    body = {"choices": [{"index": 0, "message": {"role": "assistant", "content": "{}"}, "finish_reason": "stop"}]}
    if usage is not None:
        body["usage"] = usage
    return body


@pytest.mark.asyncio
async def test_judge_calls_are_charged_to_the_shared_ledger(tmp_path):
    from src.commands.evaluate_study import SpendLedger
    from src.commands.judge_study import JudgeMeter, worst_judge_usd

    ledger = SpendLedger(tmp_path / "spend.json")
    meter = JudgeMeter(judge_profile(), ledger, ceiling=10, state=tmp_path / "judge-calls.json")
    bodies = [usage_body({"prompt_tokens": 1000, "completion_tokens": 100}), usage_body(None)]
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=bodies.pop(0)))
    async with httpx.AsyncClient(transport=transport, event_hooks=meter.hooks()) as client:
        await client.post("https://example.test/v1/chat/completions", json={})
        await client.post("https://example.test/v1/chat/completions", json={})
    # Real usage when the provider reports it, the worst case when it does not.
    assert ledger.spent() == pytest.approx((1000 * 1.30 + 100 * 2.60) / 1e6 + worst_judge_usd(judge_profile()))
    assert json.loads((tmp_path / "judge-calls.json").read_text(encoding="utf-8"))["calls"] == 2


@pytest.mark.asyncio
async def test_judge_refuses_a_call_the_ledger_cannot_afford(tmp_path):
    from src.commands.evaluate_study import SpendLedger
    from src.commands.judge_study import JudgeMeter, worst_judge_usd

    ledger = SpendLedger(tmp_path / "spend.json", ceiling_usd=worst_judge_usd(judge_profile()) / 2)
    meter = JudgeMeter(judge_profile(), ledger, ceiling=10, state=tmp_path / "judge-calls.json")
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=usage_body(None)))
    async with httpx.AsyncClient(transport=transport, event_hooks=meter.hooks()) as client:
        with pytest.raises(RuntimeError, match="judge_price_ceiling"):
            await client.post("https://example.test/v1/chat/completions", json={})
    assert ledger.spent() == 0


@pytest.mark.asyncio
async def test_judge_call_count_survives_a_restart(tmp_path):
    from src.commands.evaluate_study import SpendLedger
    from src.commands.judge_study import JudgeMeter

    state = tmp_path / "judge-calls.json"
    state.write_text(json.dumps({"calls": 2}), encoding="utf-8")
    meter = JudgeMeter(judge_profile(), SpendLedger(tmp_path / "spend.json"), ceiling=2, state=state)
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=usage_body(None)))
    async with httpx.AsyncClient(transport=transport, event_hooks=meter.hooks()) as client:
        with pytest.raises(RuntimeError, match="judge_call_ceiling"):
            await client.post("https://example.test/v1/chat/completions", json={})


@pytest.mark.asyncio
async def test_judged_rows_are_saved_as_they_finish_and_skipped_on_rerun(tmp_path):
    from src.commands.judge_study import judge_into

    calls, failing = [], {"Q1"}

    async def faithful(row):
        calls.append(row["job"])
        if row["job"] in failing:
            raise RuntimeError("judge_call_ceiling")
        return 0.8

    metrics = {"faithfulness": faithful, "factual_correctness": faithful, "context_recall": faithful}
    output = tmp_path / "judged.jsonl"
    with pytest.raises(RuntimeError):
        await judge_into(ROWS, metrics, output)
    assert [json.loads(line)["job"] for line in output.read_text(encoding="utf-8").splitlines()] == ["L"]
    calls.clear()
    failing.clear()
    await judge_into(ROWS, metrics, output)
    # The paid-for L score is kept; only Q1 is judged again.
    assert [json.loads(line)["job"] for line in output.read_text(encoding="utf-8").splitlines()] == ["L", "Q1"]
    assert calls == ["Q1", "Q1", "Q1"]


def test_judge_client_never_retries(tmp_path):
    from src.commands.evaluate_study import SpendLedger
    from src.commands.judge_study import JudgeMeter, judge_client

    meter = JudgeMeter(judge_profile(), SpendLedger(tmp_path / "spend.json"), ceiling=1, state=tmp_path / "c.json")
    assert judge_client("private-test", meter).max_retries == 0


def test_calibration_rows_never_come_from_the_private_paper():
    from src.commands.judge_study import check_calibration

    rows = calibration_rows()
    assert all(row["paper"] == "2005.11401v4" for row in rows)
    check_calibration(rows)
    with pytest.raises(ValueError, match="private_paper"):
        check_calibration(rows + [{**rows[0], "paper": "2510.26807v1"}])
    committed = json.loads(open("evaluation/paper_benchmark/calibration.v1.json", encoding="utf-8").read())["rows"]
    check_calibration(committed)


def test_development_claims_for_calibration_are_spread_and_public():
    from src.commands.judge_study import dev_calibration_rows

    def lesson(paper, n):
        return {"paper": paper, "job": "L", "status": "ready", "lesson": {"title": "t", "sections": [
            {"heading": f"h{i}", "kind": "paper", "text": f"جملة {paper} رقم {i}.",
             "evidence": [{"block_id": f"p{i}b0", "quote": f"Quote {paper} {i} from the paper."}]} for i in range(n)] + [
            {"heading": "two", "kind": "paper", "text": "جملتين.", "evidence": [{"block_id": "a", "quote": "q one"},
                                                                                {"block_id": "b", "quote": "q two"}]},
            {"heading": "bg", "kind": "background", "text": "خلفية.", "evidence": []}]}}

    rows = [lesson("1111.00001v1", 9), lesson("2222.00002v1", 9), lesson("2510.26807v1", 9),
            {"paper": "3333.00003v1", "job": "L", "status": "failed", "lesson": None}]
    picked = dev_calibration_rows(rows, count=6)
    assert len(picked) == 6 and [row["paper"] for row in picked].count("1111.00001v1") == 3
    assert all(row["paper"] != "2510.26807v1" and row["owner_faithful"] is None for row in picked)
    # Only single-source paper sections, so each claim sits beside exactly the quote that supports it.
    assert all(row["quote_en"].startswith("Quote ") and row["claim_ar"].startswith("جملة") for row in picked)
    assert picked == dev_calibration_rows(rows, count=6)
    assert len({row["id"] for row in picked}) == 6
