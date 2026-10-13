from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
import src.main as application
from fastapi import FastAPI
from src.dependencies import get_settings
from src.main import app
from src.services.agent import AgentService
from src.services.hf.client import HFClient
from src.services.hf.rag import HostedRAGService
from src.services.rag import RAGService

from tests.api.test_agent_routes import events
from tests.api.test_operational_health import SearchHealth
from tests.api.test_operational_health import healthy_dependencies as healthy_dependencies
from tests.unit.test_agent_service import EVIDENCE, QUESTION, Search
from tests.unit.test_hf_client import envelope, settings
from tests.unit.test_hf_configuration import KEY, MODEL, TOKEN


def enable(monkeypatch, stub_httpx, tmp_path, outputs, **values):
    import json

    def respond(request):
        output = outputs.pop(0)
        return httpx.Response(200, json=envelope(json.dumps(output) if isinstance(output, dict) else output))

    calls = stub_httpx(respond)
    config = settings(agent_enabled=True, api_rate_limit_path=str(tmp_path / "limits.sqlite3"), **values)
    hf = HFClient(config)
    rag = HostedRAGService(Search(), hf, config)
    monkeypatch.setattr(app.state, "settings", config)
    monkeypatch.setattr(app.state, "rag", rag, raising=False)
    monkeypatch.setattr(app.state, "agent", AgentService(rag, config), raising=False)
    return hf, calls, config


@pytest.mark.anyio
@pytest.mark.parametrize("route", ["/ask", "/stream", "/agent/ask", "/agent/stream"])
async def test_hosted_json_and_sse_preserve_citations_identity_and_token_privacy(client, monkeypatch, stub_httpx, tmp_path, route):
    outputs = [{"answer": "E1"}]
    if "/agent/" in route:
        outputs = [{"in_scope": True}, {"relevant_markers": ["[1.1]"]}] + outputs
    hf, calls, config = enable(monkeypatch, stub_httpx, tmp_path, outputs)
    try:
        response = await client.post("/api/v1" + route, json={"query": QUESTION, "use_hybrid": False}, headers={"X-API-Key": KEY})
        assert response.status_code == 200 and TOKEN not in response.text
        if route.endswith("stream"):
            messages = events(response.text)
            assert messages[-1][0] == "done"
            assert messages[-1][1]["answer"] == f'"{EVIDENCE}" [1.1]'
            sources = next(data for kind, data in messages if kind == "sources")
            assert sources["model"] == MODEL and sources["query"] == QUESTION
            assert sources["citations"][0]["evidence"] == EVIDENCE
        else:
            assert response.json()["answer"] == f'"{EVIDENCE}" [1.1]'
            assert response.json()["model"] == MODEL
        assert len(calls) == hf.attempts == (3 if "/agent/" in route else 1)
    finally:
        await hf.aclose()


@pytest.mark.anyio
async def test_hosted_auth_and_shared_quota_precede_any_paid_work(client, monkeypatch, stub_httpx, tmp_path):
    hf, calls, config = enable(monkeypatch, stub_httpx, tmp_path, [{"in_scope": False}], api_generations_per_minute=1)
    try:
        assert (await client.post("/api/v1/agent/ask", json={"query": QUESTION})).status_code == 401
        assert not calls
        assert (await client.post("/api/v1/agent/ask", json={"query": QUESTION}, headers={"X-API-Key": KEY})).status_code == 200
        assert (await client.post("/api/v1/ask", json={"query": QUESTION}, headers={"X-API-Key": KEY})).status_code == 429
        assert len(calls) == hf.attempts == 1
    finally:
        await hf.aclose()


@pytest.mark.anyio
async def test_hosted_unregistered_model_rejected_before_stream_or_provider_work(client, monkeypatch, stub_httpx, tmp_path):
    hf, calls, config = enable(monkeypatch, stub_httpx, tmp_path, [])
    try:
        response = await client.post("/api/v1/agent/stream", json={"query": QUESTION, "model": "openai/gpt-oss-120b:cerebras"},
                                     headers={"X-API-Key": KEY})
        assert response.status_code == 422 and not calls
    finally:
        await hf.aclose()


@pytest.mark.anyio
async def test_hosted_readiness_is_honest_configuration_only_and_never_calls_generation(
        client, monkeypatch, stub_httpx, tmp_path, healthy_dependencies):
    from src.dependencies import get_search

    hf, calls, config = enable(monkeypatch, stub_httpx, tmp_path, [])
    monkeypatch.setitem(app.dependency_overrides, get_settings, lambda: config)
    monkeypatch.setitem(app.dependency_overrides, get_search, lambda: SearchHealth())
    try:
        response = await client.get("/api/v1/health", headers={"X-API-Key": KEY})
        assert response.status_code == 200 and response.json()["status"] == "degraded"
        assert response.json()["services"]["hf_generation"]["status"] == "degraded"
        assert "qualification" in response.json()["services"]["hf_generation"]["message"]
        assert not calls
    finally:
        await hf.aclose()


@pytest.mark.anyio
@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("failure", [False, True])
async def test_lifespan_selects_opt_in_generation_and_closes_both_clients(monkeypatch, enabled, failure):
    config = settings() if enabled else settings().model_copy(update={"hf_inference_enabled": False})
    local = SimpleNamespace(aclose=AsyncMock())
    remote = SimpleNamespace(aclose=AsyncMock())
    search = Search()
    database = SimpleNamespace(teardown=Mock())
    remote_factory = Mock(return_value=remote)
    cache_factory = Mock(return_value=None)
    monkeypatch.setattr(application, "get_settings", lambda: config)
    monkeypatch.setattr(application, "make_database", lambda: database)
    monkeypatch.setattr(application, "make_arxiv_client", lambda: object())
    monkeypatch.setattr(application, "make_search_client", lambda: object())
    monkeypatch.setattr(application, "make_embedder", lambda: object())
    monkeypatch.setattr(application, "SearchService", lambda *args: search)
    monkeypatch.setattr(application, "make_ollama_client", lambda *args: local)
    monkeypatch.setattr(application, "HFClient", remote_factory, raising=False)
    monkeypatch.setattr(application, "make_answer_cache", cache_factory)
    isolated = FastAPI()
    try:
        async with application.lifespan(isolated):
            assert isolated.state.ollama is local
            assert isolated.state.rag.ollama is (remote if enabled else local)
            assert type(isolated.state.rag) is (HostedRAGService if enabled else RAGService)
            assert isolated.state.rag.cache is None
            assert isolated.state.settings.ollama_embedding_model == "nomic-embed-text"
            assert remote_factory.call_count == int(enabled)
            assert cache_factory.call_count == int(not enabled)
            if failure:
                raise RuntimeError("test-owned lifespan failure")
    except RuntimeError:
        assert failure
    local.aclose.assert_awaited_once()
    assert remote.aclose.await_count == int(enabled)
    database.teardown.assert_called_once()


@pytest.mark.anyio
@pytest.mark.parametrize("status,expected", [(401, 503), (402, 503), (429, 503), (500, 503)])
async def test_provider_failures_keep_api_errors_generic_without_retry(client, monkeypatch, stub_httpx, tmp_path, status, expected):
    hf, calls, config = enable(monkeypatch, stub_httpx, tmp_path, [])
    await hf.aclose()
    calls = stub_httpx(lambda request: httpx.Response(status, json={"error": TOKEN}))
    hf = HFClient(config)
    monkeypatch.setattr(app.state, "rag", HostedRAGService(Search(), hf, config))
    try:
        response = await client.post("/api/v1/ask", json={"query": QUESTION, "use_hybrid": False}, headers={"X-API-Key": KEY})
        assert response.status_code == expected and TOKEN not in response.text
        assert len(calls) == hf.attempts == 1
    finally:
        await hf.aclose()
