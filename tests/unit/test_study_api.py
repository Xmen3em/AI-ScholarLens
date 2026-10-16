from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from src.middlewares import OperationalMiddleware
from src.services.study.api import add_study_routes
from src.services.study.store import StudyStore

from tests.unit.test_development_bot import config


@pytest.mark.anyio
async def test_study_auth_schema_generation_quota_and_claim_are_shared(tmp_path):
    settings = config(tmp_path).model_copy(update={"api_generations_per_minute": 1})
    app = FastAPI()
    store = StudyStore(tmp_path / "study.sqlite3", "trusted-owner")
    calls = []
    def submit(intent, text):
        calls.append((intent, text))
        return {"reply": "ok"}
    app.state.study = SimpleNamespace(store=store, submit=submit)
    app.add_middleware(OperationalMiddleware, settings=settings)
    add_study_routes(app)
    headers = {"X-API-Key": settings.api_key.get_secret_value()}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://local") as client:
        assert (await client.post("/api/v1/study/messages", json={"intent": "x", "text": "paper"})).status_code == 401
        assert not calls
        first = await client.post("/api/v1/study/messages", headers=headers, json={"intent": "x", "text": "paper"})
        assert first.status_code == 200 and calls == [("x", "paper")]
        assert (await client.post("/api/v1/study/messages", headers=headers, json={"intent": "y", "text": "paper"})).status_code == 429
        job = store.create_job("test", {})
        store.finish_job(job["id"], {"text": "lesson"})
        # Polling/delivery consume request quota, but no inference quota.
        assert (await client.post("/api/v1/study/pending", headers=headers)).json()["jobs"][0]["id"] == job["id"]
        first = await client.post("/api/v1/study/claim", headers=headers, json={"job_id": job["id"]})
        assert first.json() == {"claimed": True, "result": {"text": "lesson"}}
        assert (await client.post("/api/v1/study/claim", headers=headers, json={"job_id": job["id"]})).json() == {"claimed": False}


@pytest.mark.anyio
async def test_caller_cannot_override_the_configured_owner(tmp_path):
    app = FastAPI()
    app.state.study = SimpleNamespace(submit=lambda *args: pytest.fail("invalid input reached service"))
    add_study_routes(app)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://local") as client:
        response = await client.post("/api/v1/study/messages", json={"intent": "x", "text": "paper", "owner": "other"})
    assert response.status_code == 422
