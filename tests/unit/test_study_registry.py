import asyncio

import httpx
import pytest
from fastapi import FastAPI
from pydantic import SecretStr
from src.services.study import access_text
from src.services.study.access import AccessGate
from src.services.study.access_settings import AccessSettings
from src.services.study.api import add_study_routes, install_multi_user
from src.services.study.pool import ModelPool
from src.services.study.registry import ServiceRegistry
from src.services.study.service import HELP
from src.services.study.store import StudyStore

from tests.unit.test_access_gate import OWNER, Clock
from tests.unit.test_study_service import Content, Intake, honest_verdicts, paper
from tests.unit.test_study_tutor import lesson

USAGE = {"prompt_tokens": 1000, "completion_tokens": 200}  # $0.0017 on GLM-5.3


class FakeModel:
    """Answers like the provider, reports usage through audit, and can be held open."""

    def __init__(self, store, audit, pool, hold: asyncio.Event | None = None, fail_unknown: bool = False):
        self.store, self.audit, self.pool, self.hold, self.fail_unknown = store, audit, pool, hold, fail_unknown

    async def complete(self, job, purpose, messages, **kwargs):
        # Like the pooled StudyModel: wait for a slot, then make the call.
        async with self.pool.slot(job):
            return await self._call(job, purpose, messages)

    async def _call(self, job, purpose, messages):
        if self.hold is not None:
            await self.hold.wait()
        if self.fail_unknown:
            self.store.reserve_attempt(job, purpose, "m")
            raise RuntimeError("connection lost")
        output = honest_verdicts(messages) if purpose == "grounding_review" else lesson()
        self.audit({"purpose": purpose, "result": {"output": output, "usage": USAGE}})
        return {"output": output}

    async def aclose(self):
        pass


class Harness:
    def __init__(self, tmp_path, *, hold=None, fail_unknown=False, **settings):
        self.path = tmp_path / "sessions.sqlite3"
        self.clock = Clock()
        self.settings = AccessSettings(_env_file=None, multi_user=True, **settings)
        self.gate = AccessGate(self.path, self.settings, OWNER, now=self.clock)
        self.pool = ModelPool(SecretStr("x" * 40), self.settings.parallel_jobs)
        self.registry = ServiceRegistry(self.path, self.pool, self.gate, Intake(), Content(), owner_id=OWNER,
                                        research_python=None, token=SecretStr("x" * 40),
                                        model_factory=lambda store, audit: FakeModel(store, audit, self.pool, hold, fail_unknown))
        self.app = FastAPI()
        install_multi_user(self.app, self.gate, self.registry, self.path, OWNER)
        add_study_routes(self.app)
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://local")
        self.count = 0

    async def send(self, user, text):
        self.count += 1
        response = await self.client.post("/api/v1/study/messages",
                                          json={"intent": f"telegram:{self.count}", "text": text, "user_id": user})
        assert response.status_code == 200, response.text
        return response.json()

    def join(self, *users):
        for user, code in zip(users, self.gate.create_invites(len(users))):
            assert self.gate.redeem(user, code)

    async def done(self, user, job_id):
        store = StudyStore(self.path, str(user))
        for _ in range(200):
            job = store.get_job(job_id)
            if job["status"] != "running" and not self.registry.busy(user):
                return job
            await asyncio.sleep(0.01)
        pytest.fail("job did not finish")

    async def aclose(self):
        await self.client.aclose()
        await self.registry.aclose()
        await self.pool.aclose()


@pytest.fixture
async def h(tmp_path):
    harness = Harness(tmp_path)
    yield harness
    await harness.aclose()


async def test_students_get_separate_papers_and_dialogue(h):
    h.join(111, 222)
    first = await h.send(111, "1706.03762")
    await h.done(111, first["job_id"])
    assert StudyStore(h.path, "111").context()["paper_id"] == "1706.03762v1"
    assert StudyStore(h.path, "222").context() is None
    reply = await h.send(222, "اشرح الطريقة بمثال")
    assert "job_id" not in reply


async def test_a_delivered_lesson_counts_one_paper_and_its_real_cost(h):
    h.join(111)
    job = await h.done(111, (await h.send(111, "1706.03762"))["job_id"])
    assert job["status"] == "ready"
    assert h.gate.usage(111)["papers_left"] == 2
    usage = h.gate.owner_usage()
    assert usage["spent"] == pytest.approx(2 * 0.0017) and usage["reserved"] == 0


async def test_a_busy_submit_releases_its_reservation(tmp_path):
    hold = asyncio.Event()
    h = Harness(tmp_path, hold=hold)
    try:
        h.join(111)
        first = await h.send(111, "1706.03762")
        reserved = h.gate.owner_usage()["reserved"]
        second = await h.send(111, "1706.03762v2")
        assert "job_id" not in second and h.gate.owner_usage()["reserved"] == pytest.approx(reserved)
        hold.set()
        await h.done(111, first["job_id"])
        assert h.gate.usage(111)["papers_left"] == 2 and h.gate.owner_usage()["reserved"] == 0
    finally:
        hold.set()
        await h.aclose()


async def test_owner_history_survives_enabling_multi_user(tmp_path):
    StudyStore(tmp_path / "sessions.sqlite3", str(OWNER)).activate("1706.03762v1", {"title": "Attention Is All You Need"})
    h = Harness(tmp_path)
    try:
        reply = await h.send(OWNER, "/study")
        assert "Attention Is All You Need" in reply["reply"]
    finally:
        await h.aclose()


async def test_student_deep_is_refused_without_a_job(h):
    h.join(111)
    assert await h.send(111, "/deep اشرح الطريقة") == {"reply": access_text.DEEP_OWNER_ONLY}
    assert h.gate.owner_usage()["reserved"] == 0


async def test_non_member_gets_the_note_once_and_touches_nothing(h):
    assert await h.send(999, "1706.03762") == {"reply": access_text.NOT_MEMBER}
    assert await h.send(999, "1706.03762") == {"reply": None}
    assert StudyStore(h.path, "999").context() is None and h.gate.owner_usage()["reserved"] == 0


async def test_start_with_a_code_joins_and_a_bad_code_is_refused(h):
    [code] = h.gate.create_invites(1)
    assert await h.send(555, "/start WRONGCODE1") == {"reply": access_text.BAD_CODE}
    assert await h.send(555, "/start " + code.lower()) == {"reply": access_text.WELCOME}
    assert h.gate.role(555) == "student"
    assert await h.send(555, "/start " + code) == {"reply": access_text.WELCOME}


async def test_revoked_member_gets_the_revoked_note(h):
    h.join(111)
    await h.send(OWNER, "/revoke 111")
    assert await h.send(111, "hello") == {"reply": access_text.REVOKED}


async def test_owner_commands_need_the_owner_role(h):
    h.join(111)
    assert (await h.send(111, "/invite 2"))["reply"] == HELP
    reply = (await h.send(OWNER, "/invite 2"))["reply"]
    codes = [line.strip() for line in reply.splitlines() if len(line.strip()) == 10 and line.strip().isalnum()]
    assert len(codes) == 2 and all(h.gate.redeem(600 + i, code) for i, code in enumerate(codes))
    members = (await h.send(OWNER, "/members"))["reply"]
    assert "111" in members and "600" in members


async def test_revoke_blocks_and_forgets_the_student(h):
    h.join(111)
    await h.done(111, (await h.send(111, "1706.03762"))["job_id"])
    reply = (await h.send(OWNER, "/revoke 111"))["reply"]
    assert "111" in reply and h.gate.role(111) is None and StudyStore(h.path, "111").context() is None
    assert await h.send(OWNER, "/revoke 111") == {"reply": access_text.NO_SUCH_MEMBER}


async def test_usage_and_privacy(h):
    h.join(111)
    assert await h.send(111, "/usage") == {"reply": access_text.USAGE.format(p=3, P=3, q=30, Q=30)}
    assert await h.send(111, "/privacy") == {"reply": access_text.PRIVACY}
    owner = (await h.send(OWNER, "/usage"))["reply"]
    assert "2.00" in owner


async def test_help_adds_the_beta_commands(h):
    h.join(111)
    student = (await h.send(111, "/help"))["reply"]
    owner = (await h.send(OWNER, "/help"))["reply"]
    assert "/usage" in student and "/invite" not in student and "/invite" in owner


async def test_students_without_a_paper_get_no_general_fallback(h):
    h.join(111)
    reply = await h.send(111, "what is attention?")
    assert reply.get("fallback") is not True and "job_id" not in reply and h.gate.owner_usage()["reserved"] == 0


async def test_too_many_messages_are_slowed_down(h):
    h.join(111)
    for _ in range(6):
        await h.send(111, "/usage")
    assert await h.send(111, "/usage") == {"reply": access_text.TOO_FAST}


async def test_ceiling_refuses_before_any_job(tmp_path):
    h = Harness(tmp_path, daily_usd_ceiling=0.10)
    try:
        h.join(111, 222)
        await h.send(111, "1706.03762")
        assert await h.send(222, "1706.03762") == {"reply": access_text.CEILING}
    finally:
        await h.aclose()


async def test_unknown_attempts_are_charged_their_worst_case(tmp_path):
    h = Harness(tmp_path, fail_unknown=True)
    try:
        h.join(111)
        job = await h.done(111, (await h.send(111, "1706.03762"))["job_id"])
        assert job["status"] == "failed" and h.gate.usage(111)["papers_left"] == 3
        usage = h.gate.owner_usage()
        assert usage["spent"] == pytest.approx(h.gate.worst_call_usd()) and usage["reserved"] == 0
    finally:
        await h.aclose()


async def test_pending_and_claim_work_across_students(h):
    h.join(111, 222)
    first = await h.send(111, "1706.03762")
    second = await h.send(222, "1706.03762")
    await h.done(111, first["job_id"])
    await h.done(222, second["job_id"])
    jobs = (await h.client.post("/api/v1/study/pending")).json()["jobs"]
    assert {(row["user"], row["id"]) for row in jobs} == {(111, first["job_id"]), (222, second["job_id"])}
    claimed = await h.client.post("/api/v1/study/claim", json={"job_id": second["job_id"], "user_id": 222})
    assert claimed.json()["claimed"] is True
    wrong = await h.client.post("/api/v1/study/claim", json={"job_id": first["job_id"], "user_id": 222})
    assert wrong.status_code == 404


async def test_queued_jobs_report_their_place(tmp_path):
    hold = asyncio.Event()
    h = Harness(tmp_path, hold=hold, parallel_jobs=1)
    try:
        h.join(111, 222)
        await h.send(111, "1706.03762")
        await h.send(222, "1706.03762")
        await asyncio.sleep(0.05)
        running = (await h.client.post("/api/v1/study/pending")).json()["running"]
        stages = {row["user"]: (row["stage"], row["position"]) for row in running}
        assert stages[111][1] is None and stages[222] == ("queued", 1)
    finally:
        hold.set()
        await asyncio.sleep(0.05)
        await h.aclose()


async def test_undeliverable_marks_the_student_inactive(h):
    h.join(111)
    response = await h.client.post("/api/v1/study/undeliverable", json={"user_id": 111})
    assert response.status_code == 200 and h.gate.is_inactive(111)


async def test_sweep_forgets_inactive_students_never_the_owner(h):
    h.join(111)
    StudyStore(h.path, "111").activate(paper().arxiv_id, {"title": "t"})
    StudyStore(h.path, str(OWNER)).activate(paper().arxiv_id, {"title": "t"})
    h.clock.advance(31 * 86400)
    assert h.registry.sweep(30) == 1
    assert StudyStore(h.path, "111").context() is None and StudyStore(h.path, str(OWNER)).context() is not None


async def test_single_user_mode_rejects_user_id(tmp_path):
    from types import SimpleNamespace

    app = FastAPI()
    app.state.study = SimpleNamespace(submit=lambda *args: pytest.fail("reached the service"))
    add_study_routes(app)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://local") as client:
        response = await client.post("/api/v1/study/messages", json={"intent": "x", "text": "paper", "user_id": 5})
    assert response.status_code == 422


async def test_multi_user_mode_requires_user_id(h):
    response = await h.client.post("/api/v1/study/messages", json={"intent": "x", "text": "paper"})
    assert response.status_code == 422


async def test_startup_settles_reservations_a_crash_left_open(h):
    from src.services.study.registry import settle_interrupted
    from src.services.study.store import recover_all_interrupted

    h.join(111)
    store = StudyStore(h.path, "111")
    job = store.create_job("crashed", {}, max_calls=2)
    store.reserve_attempt(job["id"], "lesson", "m")
    h.gate.admit(111, "paper", "111:crashed", 2)
    h.gate.bind("111:crashed", job["id"])
    h.gate.admit(111, "question", "111:never-bound", 2)
    recover_all_interrupted(h.path)
    assert settle_interrupted(h.gate, h.path) == 2
    usage = h.gate.owner_usage()
    assert usage["reserved"] == 0 and usage["spent"] == pytest.approx(h.gate.worst_call_usd())
    assert h.gate.usage(111)["papers_left"] == 3


async def test_idle_services_are_closed_and_rebuilt(tmp_path):
    h = Harness(tmp_path)
    ticks = [0.0]
    h.registry.now = lambda: ticks[0]
    try:
        h.join(111)
        first = h.registry.service(111)
        ticks[0] = 1801.0
        await h.registry.close_idle()
        assert h.registry.service(111) is not first
    finally:
        await h.aclose()
