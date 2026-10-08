import json
import logging
from concurrent.futures import ThreadPoolExecutor

import anyio
import pytest
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from src.config import Settings
from src.middlewares import OperationalMiddleware, RateLimiter


def config(tmp_path, **overrides):
    return Settings(_env_file=None, api_rate_limit_path=str(tmp_path / "limits.sqlite3"), **overrides)


def test_non_development_requires_a_strong_key(tmp_path):
    with pytest.raises(ValidationError):
        config(tmp_path, environment="production")
    with pytest.raises(ValidationError):
        config(tmp_path, api_key="short")
    assert config(tmp_path, environment="production", api_key="a" * 32).api_key


def test_worker_shared_limits_reset_without_charging_rejections(tmp_path):
    settings = config(tmp_path, api_requests_per_minute=3, api_generations_per_minute=1)
    first, second = RateLimiter(settings), RateLimiter(settings)
    assert first.reserve(generation=True, now=10) == 0
    assert second.reserve(generation=True, now=11) == 59
    assert second.reserve(generation=False, now=12) == 0
    assert first.reserve(generation=False, now=13) == 0
    assert second.reserve(generation=False, now=14) == 56
    assert second.reserve(generation=True, now=70) == 0


def test_concurrent_workers_cannot_overspend(tmp_path):
    settings = config(tmp_path, api_requests_per_minute=4)
    limiters = [RateLimiter(settings) for _ in range(12)]
    with ThreadPoolExecutor(max_workers=12) as pool:
        results = list(pool.map(lambda limiter: limiter.reserve(generation=False, now=10), limiters))
    assert results.count(0) == 4


@pytest.mark.anyio
async def test_auth_limits_and_correlated_safe_logs(tmp_path, caplog):
    settings = config(tmp_path, api_key="s" * 32, api_requests_per_minute=1)
    app = FastAPI()
    calls = []

    @app.get("/api/v1/ping")
    async def ping():
        return {"status": "ok"}

    @app.post("/api/v1/ask")
    async def ask():
        calls.append(1)
        return {"answer": "ok"}

    app.add_middleware(OperationalMiddleware, settings=settings)
    caplog.set_level(logging.INFO)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/api/v1/ping")).status_code == 200
        assert (await client.post("/api/v1/ask", headers={"X-API-Key": "wrong"})).status_code == 401
        assert not calls
        headers = {"X-API-Key": "s" * 32, "X-Request-ID": "untrusted-id"}
        ok = await client.post("/api/v1/ask?secret=hidden", headers=headers, json={"query": "private question"})
        denied = await client.post("/api/v1/ask", headers=headers)
        assert ok.status_code == 200
        assert denied.status_code == 429
        assert int(denied.headers["Retry-After"]) > 0
        assert len(calls) == 1
        assert ok.headers["X-Request-ID"] != "untrusted-id"
    events = [json.loads(r.message) for r in caplog.records if r.name == "src.operations"]
    event = next(e for e in events if e.get("request_id") == ok.headers["X-Request-ID"])
    assert event["event"] == "http_request_completed"
    assert event["duration_ms"] >= 0
    assert event["route"] == "/api/v1/ask"
    log_text = json.dumps(events)
    assert not any(s in log_text for s in ("private question", "hidden", "s" * 32, "wrong", "untrusted-id"))


@pytest.mark.anyio
async def test_unavailable_limit_store_fails_closed(tmp_path):
    settings = config(tmp_path)
    (tmp_path / "limits.sqlite3").mkdir()
    app = FastAPI()
    @app.get("/api/v1/health")
    async def health():
        return {"status": "healthy"}
    app.add_middleware(OperationalMiddleware, settings=settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/docs")
        assert (await client.get("/api/v1/health")).status_code == 200
    assert response.status_code == 503
    assert "sqlite" not in response.text


@pytest.mark.anyio
async def test_unhandled_failure_records_500_without_exception_text(tmp_path, caplog):
    app = FastAPI()

    @app.get("/broken")
    async def broken():
        raise RuntimeError("private provider response")

    app.add_middleware(OperationalMiddleware, settings=config(tmp_path))
    caplog.set_level(logging.INFO)
    async with AsyncClient(transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test") as client:
        response = await client.get("/broken")
    assert response.status_code == 500
    assert response.headers["X-Request-ID"]
    event = next(json.loads(r.message) for r in caplog.records if r.name == "src.operations")
    assert event["status"] == 500
    assert event["outcome"] == "failed"
    assert "private provider response" not in caplog.text


@pytest.mark.anyio
async def test_stream_latency_includes_body_and_context_is_isolated(tmp_path, caplog):
    from src.operations import emit_event

    app = FastAPI()

    @app.get("/slow-stream")
    async def stream():
        async def body():
            await anyio.sleep(0.04)
            emit_event("test_stream_body")
            yield b"done"
        return StreamingResponse(body())

    app.add_middleware(OperationalMiddleware, settings=config(tmp_path))
    caplog.set_level(logging.INFO, logger="src.operations")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        responses = []
        async def request():
            responses.append(await client.get("/slow-stream"))
        async with anyio.create_task_group() as group:
            group.start_soon(request)
            group.start_soon(request)
    ids = {r.headers["X-Request-ID"] for r in responses}
    assert len(ids) == 2
    events = [json.loads(r.message) for r in caplog.records if r.name == "src.operations"]
    for request_id in ids:
        correlated = [e for e in events if e["request_id"] == request_id]
        assert {e["event"] for e in correlated} == {"test_stream_body", "http_request_completed"}
        assert next(e for e in correlated if e["event"] == "http_request_completed")["duration_ms"] >= 35
