import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from src.commands import run_dev_bot as command
from src.config import Settings
from src.operations import request_context
from src.schemas.api.rag import AskRequest
from src.services import development_pc_api as runtime
from src.services.hf.client import HFGenerationError, HFResponseError

from tests.unit.test_hf_client import OPTIONS, envelope, settings
from tests.unit.test_hf_tokenizer import install_vocabulary


def config(tmp_path):
    return runtime.development_settings(settings(), tmp_path)


def test_development_settings_are_isolated_and_keep_original_quotas(tmp_path):
    original = settings()
    before = original.model_dump()
    local = runtime.development_settings(original, tmp_path)
    assert original.model_dump() == before
    assert local.hf_default_model == "openai/gpt-oss-120b:cerebras"
    assert local.hf_inference_enabled and local.agent_enabled
    assert not local.answer_cache_enabled and not local.local_tracing_enabled
    assert Path(local.api_rate_limit_path) == tmp_path / "data/pc-app/development-quotas.sqlite3"
    assert local.api_generations_per_minute == original.api_generations_per_minute
    assert not list(tmp_path.iterdir())


@pytest.mark.anyio
@pytest.mark.parametrize("memory", [599, float("nan"), 4096])
async def test_development_hf_retains_resource_and_per_question_limits(tmp_path, monkeypatch, stub_httpx, memory):
    install_vocabulary(tmp_path, monkeypatch)
    calls = stub_httpx(lambda request: httpx.Response(200, json=envelope(
        usage={"prompt_tokens": 100, "completion_tokens": 20})))
    hf = runtime.DevelopmentHF(config(tmp_path), memory=lambda: memory)
    token = request_context.set({"request_id": "manual-owner-question"})
    schema = {"type": "object", "properties": {"in_scope": {"type": "boolean"}}, "required": ["in_scope"]}
    try:
        if memory == 4096:
            for _ in range(6):
                await hf.generate(hf.settings.hf_default_model, "Synthetic question", response_format=schema, options=OPTIONS)
        with pytest.raises(HFGenerationError):
            await hf.generate(hf.settings.hf_default_model, "Synthetic question", response_format=schema, options=OPTIONS)
        assert len(calls) == hf.attempts == (6 if memory == 4096 else 0)
    finally:
        request_context.reset(token)
        await hf.aclose()


@pytest.mark.anyio
@pytest.mark.parametrize("failure", ["usage", "schema", "context"])
async def test_failed_or_unattributed_dev_generation_never_retries(tmp_path, monkeypatch, stub_httpx, failure):
    install_vocabulary(tmp_path, monkeypatch)
    calls = stub_httpx(lambda request: httpx.Response(200, json=envelope(
        '{"in_scope":"invalid"}' if failure == "schema" else '{"in_scope":true}',
        **({} if failure == "usage" else {"usage": {"prompt_tokens": 100, "completion_tokens": 20}}))))
    hf = runtime.DevelopmentHF(config(tmp_path), memory=lambda: 4096)
    token = request_context.set(None if failure == "context" else {"request_id": "owner-question"})
    schema = {"type": "object", "properties": {"in_scope": {"type": "boolean"}}, "required": ["in_scope"]}
    try:
        with pytest.raises((HFGenerationError, HFResponseError)):
            await hf.generate(hf.settings.hf_default_model, "Synthetic question", response_format=schema, options=OPTIONS)
        with pytest.raises(HFGenerationError):
            await hf.generate(hf.settings.hf_default_model, "Synthetic question", response_format=schema, options=OPTIONS)
        assert len(calls) == (0 if failure == "context" else 1)
    finally:
        request_context.reset(token)
        await hf.aclose()


@pytest.mark.anyio
@pytest.mark.parametrize("startup_failure", [False, True])
async def test_dev_api_requires_auth_forces_bm25_and_closes_owned_clients(tmp_path, monkeypatch, startup_failure):
    events = []
    class HF:
        attempts = 0
        def __init__(self, settings):
            if startup_failure: raise ValueError("Synthetic HF startup failure")
        async def aclose(self): events.append("hf_closed")
    monkeypatch.setattr(runtime, "make_search_client", lambda settings: SimpleNamespace(close=lambda: events.append("search_closed")))
    monkeypatch.setattr(runtime, "make_embedder", lambda settings: None)
    monkeypatch.setattr(runtime, "DevelopmentHF", HF)
    monkeypatch.setattr(runtime, "free_memory_mib", lambda: 4096)
    local = config(tmp_path)
    app = runtime.create_development_app(local)
    if startup_failure:
        with pytest.raises(ValueError):
            async with app.router.lifespan_context(app): pytest.fail("Failed startup yielded")
        assert events == ["search_closed"]
        return
    async with app.router.lifespan_context(app):
        seen = []
        async def ask(request):
            seen.append(request)
            return {"query": request.query, "answer": "The retrieved evidence is insufficient to answer this question.",
                    "sources": [], "citations": [], "chunks_used": 0, "search_mode": "bm25", "model": runtime.MODEL,
                    "outcome": "abstained", "retrieval_attempts": 0, "model_calls": 0, "rewritten": False, "steps": []}
        app.state.agent.ask = ask
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://local") as client:
            denied = await client.post("/api/v1/agent/ask", json={"query": "Explain AI"})
            assert denied.status_code == 401 and not seen
            headers = {"X-API-Key": local.api_key.get_secret_value()}
            status = await client.get("/api/v1/development", headers=headers)
            assert status.json()["accepted"] is False and status.json()["mode"] == "development"
            response = await client.post("/api/v1/agent/ask", json=AskRequest(query="Explain AI").model_dump(), headers=headers)
            assert response.status_code == 200 and seen[0].use_hybrid is False
            monkeypatch.setattr(runtime, "free_memory_mib", lambda: 599)
            low = await client.post("/api/v1/agent/ask", json={"query": "Explain AI"}, headers=headers)
            assert low.status_code == 503 and len(seen) == 1
    assert events == ["hf_closed", "search_closed"]


def test_dev_check_never_starts_services_or_writes_state(tmp_path, monkeypatch, capsys):
    from src.services.telegram_bot import TelegramSettings
    original = settings()
    paired = TelegramSettings(_env_file=None, owner_id=123, bot_token="12345:synthetic-private-token-1234567890")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(command, "Settings", lambda: original)
    monkeypatch.setattr(command, "TelegramSettings", lambda: paired)
    monkeypatch.setattr(command, "free_memory_mib", lambda: 4096)
    monkeypatch.setattr(command, "verify_vocabulary", lambda: None)
    monkeypatch.setattr(command, "run", lambda *args: pytest.fail("Offline check started services"))
    monkeypatch.setattr("sys.argv", ["run_dev_bot", "--check"])
    command.main()
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "development_ready" and result["outbound_calls"] == 0
    assert not original.agent_enabled and not paired.enabled and not list(tmp_path.iterdir())


@pytest.mark.anyio
@pytest.mark.parametrize("bot_failure", [False, True])
async def test_stop_closes_both_development_api_and_bot(tmp_path, monkeypatch, bot_failure):
    events = []
    class Server:
        started = False
        should_exit = False
        async def serve(self):
            self.started = True
            while not self.should_exit:
                await asyncio.sleep(0.01)
            events.append("api_closed")
    async def bot(*args, **kwargs):
        try:
            if bot_failure: raise RuntimeError("Synthetic polling failure")
            await asyncio.sleep(100)
        finally:
            events.append("bot_closed")
    stop = tmp_path / "development.stop"
    stop.touch()
    monkeypatch.setattr(command, "STOP_PATH", stop)
    monkeypatch.setattr(command, "create_development_app", lambda settings, **kwargs: object())
    monkeypatch.setattr(command.uvicorn, "Server", lambda config: Server())
    monkeypatch.setattr(command, "run_bot", bot)
    if bot_failure:
        with pytest.raises(RuntimeError): await command.run(settings(), SimpleNamespace(owner_id=123))
    else:
        await command.run(settings(), SimpleNamespace(owner_id=123))
    assert events == ["bot_closed", "api_closed"]
