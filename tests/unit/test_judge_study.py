import json
import subprocess
import sys

import httpx
import pytest
from src.commands.judge_study import CallCounter, agreement, calibrated, calibration_rows, score_rows

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


@pytest.mark.asyncio
async def test_call_counter_stops_at_its_ceiling():
    counter = CallCounter(2)
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={}))
    async with httpx.AsyncClient(transport=transport, event_hooks={"request": [counter]}) as client:
        await client.get("https://example.test/a")
        await client.get("https://example.test/b")
        with pytest.raises(RuntimeError, match="judge_call_ceiling"):
            await client.get("https://example.test/c")
    assert counter.count == 3


def test_calibration_starts_from_the_science_cases():
    rows = calibration_rows()
    assert len(rows) == 16
    assert all(row["claim_ar"] and row["quote_en"] and row["owner_faithful"] is None for row in rows)


def test_importing_the_judge_does_not_import_ragas():
    code = "import sys, src.commands.judge_study; print('ragas' in sys.modules)"
    output = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout
    assert json.loads(output.strip().lower()) is False
