import json
from contextlib import asynccontextmanager
from dataclasses import replace

import httpx
import pytest
from pydantic import SecretStr
from src.commands import evaluate_study
from src.commands.evaluate_study import BenchJob, SpendLedger, plan_jobs, qualify, run_stage, worst_call_usd
from src.services.study.intake import StudyPaper
from src.services.study.models import DEFAULT_PROFILE, ModelProfile
from src.services.study.service import StudyService
from src.services.study.store import StudyStore
from src.services.study.tutor import StudyModel

from tests.unit.test_study_service import Content, honest_verdicts
from tests.unit.test_study_tutor import lesson

QWEN = ModelProfile("qwen-27b", "Qwen/Qwen3.8-27B:deepinfra", "utf8_bytes_div_3", {"reasoning_effort": "low"},
                    0.20, 2.50, "2026-11-03")
PAPER = "1706.03762v1"
SHA = {PAPER: "a" * 64}
USAGE = {"prompt_tokens": 1000, "completion_tokens": 200}


class Intake:
    async def resolve(self, text):
        return [StudyPaper(arxiv_id=PAPER, title="Attention Is All You Need", authors=["A"], abstract="Attention.",
                           categories=["cs.CL"], published="2017-06-12T00:00:00Z")]


def reply(output, usage=USAGE):
    body = {"choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": json.dumps(output, ensure_ascii=False)}}]}
    if usage is not None:
        body["usage"] = usage
    return httpx.Response(200, json=body)


def honest(request, usage=USAGE):
    messages = json.loads(request.content)["messages"]
    if "items" in json.loads(messages[-1]["content"]):
        return reply(honest_verdicts(messages), usage)
    return reply(lesson(), usage)


def factory_for(handler, seen_profiles=None):
    @asynccontextmanager
    async def factory(store, profile, audit, observer):
        if seen_profiles is not None:
            seen_profiles.append(profile)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            model = StudyModel(SecretStr("private-test"), store, client=client, memory=lambda: 2000,
                               counter=lambda _: 100, audit=audit, profile=profile)
            service = StudyService(store, Intake(), Content(), model, observer=observer)
            try:
                yield service
            finally:
                await service.aclose()
    return factory


def jobs():
    return [BenchJob(PAPER, "L", PAPER), BenchJob(PAPER, "Q1", "الدقة كانت كام؟"),
            BenchJob(PAPER, "Q2", "إزاي الطريقة بتشتغل؟"), BenchJob(PAPER, "Q3", "الورقة جربت على القطط؟")]


async def run(tmp_path, handler, *, ledger=None, ceiling=96, expected=SHA, memory=lambda: 2000, profile=QWEN):
    return await run_stage("dev", profile, jobs(), root=tmp_path, service_factory=factory_for(handler),
                           ledger=ledger or SpendLedger(tmp_path / "spend.json"), call_ceiling=ceiling,
                           expected_sha=expected, memory=memory)


def test_plan_jobs_orders_each_paper_l_q1_q2_q3():
    papers = {"papers": [{"id": "a1", "split": "dev"}, {"id": "b1", "split": "holdout"}]}
    questions = {"papers": {key: {kind: {"text": kind + key} for kind in ("Q1", "Q2", "Q3")} for key in ("a1", "b1")}}
    assert [(job.paper, job.kind, job.text) for job in plan_jobs(papers, questions, "dev")] == [
        ("a1", "L", "a1"), ("a1", "Q1", "Q1a1"), ("a1", "Q2", "Q2a1"), ("a1", "Q3", "Q3a1")]


@pytest.mark.asyncio
async def test_followups_carry_contexts_and_lesson_from_the_observer(tmp_path):
    rows = await run(tmp_path, honest)
    assert [row["status"] for row in rows] == ["ready"] * 4
    first = rows[0]
    assert first["contexts"] == ["The model uses attention."]
    assert first["lesson"]["sections"][0]["kind"] == "paper"
    assert [call["purpose"] for call in first["calls"]] == ["lesson", "grounding_review"]
    assert first["calls"][0]["cost_usd"] == pytest.approx((1000 * 0.20 + 200 * 2.50) / 1e6)
    assert first["review"]["kept"] == 1 and first["question"] == PAPER
    saved = [json.loads(line) for line in (tmp_path / "dev-qwen-27b" / "jobs.jsonl").read_text(encoding="utf-8").splitlines()]
    assert saved == rows


@pytest.mark.asyncio
async def test_failed_first_lesson_blocks_its_followups(tmp_path):
    def broken(request):
        return reply({"title": "x", "sections": []})

    rows = await run(tmp_path, broken)
    assert rows[0]["status"] == "failed" and rows[0]["failure_code"]
    assert [row["status"] for row in rows[1:]] == ["blocked"] * 3
    assert all(row["calls"] == [] for row in rows[1:])


@pytest.mark.asyncio
async def test_resume_skips_finished_and_marks_interrupted_unknown(tmp_path):
    store_path = tmp_path / "dev-qwen-27b" / "state.sqlite3"
    store_path.parent.mkdir(parents=True)
    store = StudyStore(store_path, "paper-benchmark")
    job = store.create_job(f"bench:dev:{PAPER}:L", {"text": PAPER}, max_calls=4)
    store.reserve_attempt(job["id"], "lesson", QWEN.route)  # the process died after reserving

    sent = []

    def counting(request):
        sent.append(request)
        return honest(request)

    rows = await run(tmp_path, counting)
    assert rows[0]["status"] == "unknown" and rows[0]["calls"][0]["state"] == "unknown"
    assert rows[0]["calls"][0]["cost_usd"] == pytest.approx(worst_call_usd(QWEN))
    assert [row["status"] for row in rows[1:]] == ["blocked"] * 3
    assert sent == []
    again = await run(tmp_path, counting)
    assert again == rows and sent == []


@pytest.mark.asyncio
async def test_call_without_usage_is_charged_its_maximum(tmp_path):
    rows = await run(tmp_path, lambda request: honest(request, usage=None))
    assert rows[0]["status"] == "failed" and rows[0]["diagnostic"] == "invalid_usage"
    assert rows[0]["calls"] == [{"purpose": "lesson", "state": "unknown", "usage": None,
                                 "cost_usd": pytest.approx(worst_call_usd(QWEN))}]
    assert SpendLedger(tmp_path / "spend.json").spent() == pytest.approx(worst_call_usd(QWEN))


@pytest.mark.asyncio
async def test_price_ceiling_stops_before_the_call_that_could_exceed_it(tmp_path):
    ledger = SpendLedger(tmp_path / "spend.json", ceiling_usd=2 * worst_call_usd(QWEN) + 0.0001)
    rows = await run(tmp_path, honest, ledger=ledger)
    # The first job's worst case fits; after it is charged, two more worst-case calls no longer do.
    assert rows[0]["status"] == "ready"
    assert [row["status"] for row in rows[1:]] == ["stopped"] * 3
    assert ledger.spent() <= ledger.ceiling_usd


@pytest.mark.asyncio
async def test_call_ceiling_stops_before_a_job_that_could_exceed_it(tmp_path):
    rows = await run(tmp_path, honest, ceiling=3)
    assert [row["status"] for row in rows] == ["ready", "stopped", "stopped", "stopped"]


@pytest.mark.asyncio
async def test_low_memory_refuses_the_stage(tmp_path):
    with pytest.raises(RuntimeError, match="insufficient_memory"):
        await run(tmp_path, honest, memory=lambda: 900)


@pytest.mark.asyncio
async def test_changed_source_is_recorded_and_blocks_the_paper(tmp_path):
    rows = await run(tmp_path, honest, expected={PAPER: "b" * 64})
    assert rows[0]["status"] == "failed" and rows[0]["failure_code"] == "source_changed"
    assert [row["status"] for row in rows[1:]] == ["blocked"] * 3


@pytest.mark.asyncio
async def test_qualification_retries_once_without_options_after_http_400(tmp_path):
    seen: list[ModelProfile] = []

    def picky(request):
        if "reasoning_effort" in json.loads(request.content):
            return httpx.Response(400)
        return honest(request)

    result = await qualify(QWEN, jobs()[0], root=tmp_path, service_factory=factory_for(picky, seen),
                           ledger=SpendLedger(tmp_path / "spend.json"), expected_sha=SHA, memory=lambda: 2000)
    assert result == {"model": "qwen-27b", "passed": True, "request_options": {}}
    assert [profile.request_options for profile in seen] == [{"reasoning_effort": "low"}, {}]
    assert json.loads((tmp_path / "qualification.json").read_text(encoding="utf-8"))["qwen-27b"] == result


@pytest.mark.asyncio
async def test_qualification_fails_on_unusable_output(tmp_path):
    result = await qualify(replace(QWEN, request_options={}), jobs()[0], root=tmp_path,
                           service_factory=factory_for(lambda request: honest(request, usage=None)),
                           ledger=SpendLedger(tmp_path / "spend.json"), expected_sha=SHA, memory=lambda: 2000)
    assert result["passed"] is False


def test_cli_without_execute_opens_no_client(monkeypatch, capsys):
    def refuse(*args, **kwargs):
        raise AssertionError("network used without --execute")

    monkeypatch.setattr(evaluate_study.httpx, "AsyncClient", refuse)
    assert evaluate_study.main(["--stage", "dev", "--model", "baseline"]) == 0
    out = capsys.readouterr().out
    assert "--execute" in out and "96" in out


def test_holdout_refuses_before_development_is_closed(tmp_path, monkeypatch):
    monkeypatch.setattr(evaluate_study, "DATA", tmp_path)
    monkeypatch.setattr(evaluate_study, "verify_frozen", lambda *args: "hash")
    with pytest.raises(SystemExit, match="development"):
        evaluate_study.main(["--stage", "holdout", "--model", "baseline", "--execute"])


def test_unqualified_challenger_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(evaluate_study, "DATA", tmp_path)
    monkeypatch.setattr(evaluate_study, "verify_frozen", lambda *args: "hash")
    with pytest.raises(SystemExit, match="qualif"):
        evaluate_study.main(["--stage", "dev", "--model", "qwen-27b", "--execute"])


def test_changed_manifest_is_refused(tmp_path, monkeypatch):
    def changed(*args):
        raise ValueError("manifest_changed")

    monkeypatch.setattr(evaluate_study, "verify_frozen", changed)
    with pytest.raises(SystemExit, match="manifest_changed"):
        evaluate_study.main(["--stage", "dev", "--model", "baseline", "--execute"])


def test_default_profile_is_the_baseline():
    assert DEFAULT_PROFILE.name == "baseline"


@pytest.mark.asyncio
async def test_runs_resolve_papers_from_the_frozen_content_cache(tmp_path):
    from src.commands.evaluate_study import ManifestIntake
    from src.services.study.intake import StudyInputError

    from tests.unit.test_paper_benchmark import content

    document = content()
    (tmp_path / (document.paper.arxiv_id + ".json")).write_text(document.model_dump_json(), encoding="utf-8")
    papers = await ManifestIntake(tmp_path).resolve("2510.26807v1")
    assert papers == [document.paper]
    with pytest.raises(StudyInputError):
        await ManifestIntake(tmp_path).resolve("2005.11401v4")
