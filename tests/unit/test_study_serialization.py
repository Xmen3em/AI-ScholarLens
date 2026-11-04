import asyncio
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from src.services import development_pc_api as runtime
from src.services.study.api import add_study_routes
from src.services.study.service import StudyService
from src.services.study.store import StudyStore

from tests.unit.test_development_bot import config
from tests.unit.test_study_service import Content, Model


@pytest.mark.anyio
async def test_a_general_question_cannot_overlap_a_paper_being_prepared(tmp_path):
    started = asyncio.Event()
    class WaitingIntake:
        async def resolve(self, text):
            started.set()
            await asyncio.Event().wait()
    service = StudyService(StudyStore(tmp_path / "state.sqlite3", "owner"), WaitingIntake(), Content(), Model())
    try:
        service.submit("first", "/paper 1706.03762")
        await started.wait()
        result = service.submit("second", "what is RAG")
        assert result.get("fallback") is not True and result.get("reply")
    finally:
        await service.aclose()


@pytest.mark.anyio
@pytest.mark.parametrize("command", ["/paper", "/choose", "/ask", "/deep"])
async def test_commands_requiring_arguments_do_not_start_empty_work(tmp_path, command):
    service = StudyService(StudyStore(tmp_path / "state.sqlite3", "owner"), None, None, None)
    try:
        result = service.submit("empty", command)
        assert result.get("reply") and not result.get("job_id") and not service.tasks
    finally:
        await service.aclose()


@pytest.mark.anyio
async def test_study_api_respects_an_active_legacy_question():
    app = FastAPI()
    app.state.legacy_question_busy = True
    app.state.study = SimpleNamespace(submit=lambda *args: pytest.fail("Overlapping study was admitted"))
    add_study_routes(app)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://local") as client:
        result = await client.post("/api/v1/study/messages", json={"intent": "test", "text": "/paper 1706.03762"})
    assert result.status_code == 200 and result.json().get("reply")


@pytest.mark.anyio
async def test_legacy_api_respects_an_active_study_job(tmp_path, monkeypatch):
    class HF:
        attempts = 0
        def __init__(self, settings): pass
        async def aclose(self): pass
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(runtime, "make_search_client", lambda _: SimpleNamespace(close=lambda: None))
    monkeypatch.setattr(runtime, "make_embedder", lambda _: None)
    monkeypatch.setattr(runtime, "DevelopmentHF", HF)
    monkeypatch.setattr(runtime, "free_memory_mib", lambda: 4096)
    calls = []
    async def legacy(*args):
        calls.append(True)
        return {}
    monkeypatch.setattr(runtime, "ask_agent", legacy)
    settings = config(tmp_path)
    app = runtime.create_development_app(settings, study_owner=123)
    async with app.router.lifespan_context(app):
        pending = asyncio.create_task(asyncio.Event().wait())
        app.state.study.tasks.add(pending)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://local") as client:
            result = await client.post("/api/v1/agent/ask", headers={"X-API-Key": settings.api_key.get_secret_value()},
                                       json={"query": "Explain AI"})
        assert result.status_code == 503 and calls == []


@pytest.mark.anyio
async def test_multi_user_mode_wires_the_gate_registry_and_startup_recovery(tmp_path, monkeypatch):
    from src.services.study.store import StudyStore

    class HF:
        attempts = 0
        def __init__(self, settings): pass
        async def aclose(self): pass
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("STUDY_MULTI_USER", "true")
    monkeypatch.setattr(runtime, "make_search_client", lambda _: SimpleNamespace(close=lambda: None))
    monkeypatch.setattr(runtime, "make_embedder", lambda _: None)
    monkeypatch.setattr(runtime, "DevelopmentHF", HF)
    stale = StudyStore(tmp_path / "data/study/sessions.sqlite3", "777")
    crashed = stale.create_job("crashed", {}, max_calls=2)
    settings = config(tmp_path)
    app = runtime.create_development_app(settings, study_owner=123)
    async with app.router.lifespan_context(app):
        assert app.state.gate.role(123) == "owner" and app.state.study is app.state.registry.service(123)
        assert stale.get_job(crashed["id"])["status"] == "interrupted"
        headers = {"X-API-Key": settings.api_key.get_secret_value()}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://local") as client:
            reply = await client.post("/api/v1/study/messages", headers=headers,
                                      json={"intent": "t:1", "text": "1706.03762", "user_id": 999})
            status = await client.get("/api/v1/development", headers=headers)
        assert reply.json() == {"reply": "البوت ده في تجربة محدودة بالدعوة. لو معاك كود دعوة ابعت: /start الكود"}
        assert status.json()["study_enabled"] is True
