import asyncio
import json
import logging

import pytest
from pydantic import SecretStr
from src.main import app
from src.operations import request_context
from src.schemas.api.rag import AskRequest
from src.services.agent import AgentBusyError

from tests.unit.test_agent_service import EVIDENCE, QUESTION, service


def events(text):
    result = []
    for block in text.strip().split("\n\n"):
        lines = block.splitlines()
        result.append((lines[0].removeprefix("event: "), json.loads(lines[1].removeprefix("data: "))))
    return result


def enable(monkeypatch, outputs):
    agent = service(outputs)
    monkeypatch.setattr(app.state, "agent", agent, raising=False)
    monkeypatch.setattr(app.state, "settings", app.state.settings.model_copy(update={"agent_enabled": True}))
    return agent


@pytest.mark.anyio
@pytest.mark.parametrize("route", ["ask", "stream"])
async def test_disabled_by_default_returns_503_without_service_access(client, route):
    response = await client.post(f"/api/v1/agent/{route}", json={"query": QUESTION})
    assert response.status_code == 503 and response.json()["detail"] == "Agent workflow is disabled"


@pytest.mark.anyio
@pytest.mark.parametrize("route", ["ask", "stream"])
async def test_auth_and_shared_generation_quota_precede_agent_work(client, monkeypatch, route):
    agent = enable(monkeypatch, [{"in_scope": False}])
    monkeypatch.setattr(app.state, "settings", app.state.settings.model_copy(update={
        "api_key": SecretStr("s" * 32), "api_generations_per_minute": 1}))
    path = f"/api/v1/agent/{route}"
    assert (await client.post(path, json={"query": QUESTION})).status_code == 401
    assert not agent.rag.ollama.calls
    headers = {"X-API-Key": "s" * 32}
    assert (await client.post(path, json={"query": QUESTION}, headers=headers)).status_code == 200
    for other in (path, "/api/v1/ask", "/api/v1/stream"):
        rejected = await client.post(other, json={"query": QUESTION}, headers=headers)
        assert rejected.status_code == 429 and int(rejected.headers["Retry-After"]) > 0
    assert len(agent.rag.ollama.calls) == 1


@pytest.mark.anyio
async def test_stream_exposes_only_validated_answer_after_fixed_statuses(client, monkeypatch, caplog):
    agent = enable(monkeypatch, [{"in_scope": True}, {"relevant_markers": ["[1.1]"]}, {"answer": "E1"}])
    caplog.set_level(logging.INFO, logger="src.operations")
    response = await client.post("/api/v1/agent/stream", json={"query": QUESTION, "use_hybrid": False})
    assert response.status_code == 200 and response.headers["X-Request-ID"]
    output = events(response.text)
    assert [name for name, _ in output] == ["status"] * 4 + ["sources", "delta", "done"]
    assert [data["operation"] for name, data in output if name == "status"] == ["validate", "retrieve", "grade", "answer"]
    assert output[-1][1]["answer"] == f'"{EVIDENCE}" [1.1]'
    assert output[-1][1]["model_calls"] == 3
    assert "".join(data["delta"] for name, data in output if name == "delta") == output[-1][1]["answer"]
    assert "E1" not in response.text
    log_events = [json.loads(record.message) for record in caplog.records if record.name == "src.operations"]
    serialized = json.dumps(log_events)
    assert QUESTION not in serialized and EVIDENCE not in serialized and "E1" not in serialized
    assert all(event["request_id"] == response.headers["X-Request-ID"] for event in log_events)
    agent.rag.cache.lookup.assert_not_called()


@pytest.mark.anyio
async def test_json_and_sse_contracts_match(client, monkeypatch):
    outputs = [{"in_scope": True}, {"relevant_markers": ["[1.1]"]}, {"answer": "E1"}]
    enable(monkeypatch, outputs.copy())
    standard = await client.post("/api/v1/agent/ask", json={"query": QUESTION, "use_hybrid": False})
    enable(monkeypatch, outputs.copy())
    streamed = await client.post("/api/v1/agent/stream", json={"query": QUESTION, "use_hybrid": False})
    assert standard.status_code == streamed.status_code == 200
    assert standard.json() == events(streamed.text)[-1][1]


@pytest.mark.anyio
@pytest.mark.parametrize("route", ["ask", "stream"])
async def test_invalid_output_has_no_answer_or_source_events(client, monkeypatch, route):
    enable(monkeypatch, [{"in_scope": True}, {"relevant_markers": ["[99.99]"]}])
    response = await client.post(f"/api/v1/agent/{route}", json={"query": QUESTION})
    if route == "ask":
        assert response.status_code == 502
    else:
        output = events(response.text)
        assert output[-1][0] == "error" and all(name in {"status", "error"} for name, _ in output)
    assert "99.99" not in response.text


@pytest.mark.anyio
async def test_agent_timeout_maps_to_504(client, monkeypatch):
    agent = enable(monkeypatch, [])

    async def timeout(*args):
        raise TimeoutError("private timeout detail")

    monkeypatch.setattr(agent, "ask", timeout)
    response = await client.post("/api/v1/agent/ask", json={"query": QUESTION})
    assert response.status_code == 504 and "private" not in response.text


@pytest.mark.anyio
async def test_busy_search_maps_to_503(client, monkeypatch):
    agent = enable(monkeypatch, [])

    async def busy(*args):
        raise AgentBusyError("private thread detail")

    monkeypatch.setattr(agent, "ask", busy)
    response = await client.post("/api/v1/agent/ask", json={"query": QUESTION})
    assert response.status_code == 503 and "private" not in response.text


@pytest.mark.anyio
async def test_cancelled_stream_propagates_and_marks_interrupted(monkeypatch):
    from src.routers.agent import _events

    agent = service([])
    started, cancelled = asyncio.Event(), asyncio.Event()

    async def block(*args, **kwargs):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    monkeypatch.setattr(agent.rag.ollama, "generate", block)
    context = {}
    token = request_context.set(context)
    try:
        stream = _events(AskRequest(query=QUESTION), agent)
        assert "event: status" in await anext(stream)
        task = asyncio.create_task(anext(stream))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert cancelled.is_set() and context["stream_interrupted"]
        agent.rag.cache.store.assert_not_called()
    finally:
        request_context.reset(token)


@pytest.mark.anyio
@pytest.mark.parametrize("route", ["ask", "stream"])
async def test_disabled_attempts_still_reserve_generation_budget(client, monkeypatch, route):
    monkeypatch.setattr(app.state, "settings", app.state.settings.model_copy(update={"api_generations_per_minute": 1}))
    path = f"/api/v1/agent/{route}"
    assert (await client.post(path, json={"query": QUESTION})).status_code == 503
    assert (await client.post("/api/v1/ask", json={"query": QUESTION})).status_code == 429


@pytest.mark.anyio
@pytest.mark.parametrize("body", [{"query": " "}, {"query": "x" * 501}, {"query": QUESTION, "max_retries": 100},
                                      {"query": QUESTION, "top_k": 11}, {"query": QUESTION, "categories": ["physics"]}])
async def test_request_cannot_override_budgets_or_scope(client, monkeypatch, body):
    agent = enable(monkeypatch, [])
    assert (await client.post("/api/v1/agent/ask", json=body)).status_code == 422
    assert not agent.rag.ollama.calls and not agent.rag.search.calls


@pytest.mark.anyio
async def test_stream_unknown_model_rejected_before_http_200(client, monkeypatch):
    agent = enable(monkeypatch, [])
    result = await client.post("/api/v1/agent/stream", json={"query": QUESTION, "model": "unconfigured"})
    assert result.status_code == 422 and not agent.rag.ollama.calls


@pytest.mark.anyio
async def test_asgi_disconnect_cancels_model_without_answer_or_cache(monkeypatch):
    agent = enable(monkeypatch, [])
    started, cancelled = asyncio.Event(), asyncio.Event()

    async def blocked(*args, **kwargs):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    monkeypatch.setattr(agent.rag.ollama, "generate", blocked)
    payload = AskRequest(query=QUESTION).model_dump_json().encode()
    delivered = False
    output = []

    async def receive():
        nonlocal delivered
        if not delivered:
            delivered = True
            return {"type": "http.request", "body": payload, "more_body": False}
        await started.wait()
        return {"type": "http.disconnect"}

    async def send(message):
        output.append(message)

    scope = {"type": "http", "method": "POST", "path": "/api/v1/agent/stream", "query_string": b"",
             "headers": [(b"content-type", b"application/json")], "scheme": "http", "server": ("test", 80),
             "client": ("127.0.0.1", 1), "http_version": "1.1", "asgi": {"version": "3.0", "spec_version": "2.3"}}
    await asyncio.wait_for(app(scope, receive, send), timeout=3)
    assert cancelled.is_set()
    bodies = b"".join(message.get("body", b"") for message in output)
    assert b"event: status" in bodies
    assert all(f"event: {name}".encode() not in bodies for name in ("sources", "delta", "done"))
    agent.rag.cache.store.assert_not_called()
