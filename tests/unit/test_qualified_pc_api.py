from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from src.commands.hf_schema_execution import load_cerebras
from src.operations import request_context
from src.services import qualified_pc_api as runtime
from src.services.agent import AgentService
from src.services.hf.client import HFGenerationError, HFResponseError

from tests.unit.test_hf_client import envelope, settings
from tests.unit.test_hf_paper_client import arguments


def config(tmp_path, **updates):
    return settings(hf_models=["openai/gpt-oss-120b:cerebras"], hf_default_model="openai/gpt-oss-120b:cerebras",
                    agent_enabled=True, answer_cache_enabled=False, local_tracing_enabled=False,
                    monitoring_directory=None, rag_sentence_candidates_per_passage=1,
                    api_rate_limit_path=str(tmp_path / "quotas.sqlite3"), **updates)


def accepted(monkeypatch):
    proof = {"model": "openai/gpt-oss-120b:cerebras", "source_files": {"src/test": "frozen"}}
    monkeypatch.setattr(runtime, "validate_acceptance", lambda path: dict(proof))
    return proof


def test_unaccepted_runtime_never_allocates_provider_client(tmp_path, monkeypatch):
    def reject(path): raise ValueError("No accepted evidence")
    monkeypatch.setattr(runtime, "validate_acceptance", reject)
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: pytest.fail("Unaccepted runtime allocated HTTP"))
    with pytest.raises(ValueError): runtime.QualifiedHF(config(tmp_path), Path("missing.json"))


@pytest.mark.anyio
@pytest.mark.parametrize("method", ["generate", "generate_result"])
async def test_qualified_runtime_limits_both_apis_per_request_and_revalidates_proof(
    tmp_path, monkeypatch, stub_httpx, method,
):
    accepted(monkeypatch)
    calls = stub_httpx(lambda request: httpx.Response(200, json=envelope('{"in_scope":true}',
                           usage={"prompt_tokens": 100, "completion_tokens": 20})))
    hf = runtime.QualifiedHF(config(tmp_path), tmp_path / "acceptance.json", memory=lambda: 4096)
    case = load_cerebras()["cases"][0]
    token = request_context.set({"request_id": "owner-question"})
    try:
        for _ in range(6): await getattr(hf, method)(hf.settings.hf_default_model, case["prompt"], **arguments(case))
        with pytest.raises(HFGenerationError):
            await getattr(hf, method)(hf.settings.hf_default_model, case["prompt"], **arguments(case))
        assert hf.attempts == len(calls) == 6
        request_context.set({"request_id": "next-question"})
        def changed(path): raise ValueError("Evidence changed")
        monkeypatch.setattr(runtime, "validate_acceptance", changed)
        with pytest.raises(HFGenerationError):
            await hf.generate_result(hf.settings.hf_default_model, case["prompt"], **arguments(case))
        assert len(calls) == 6
    finally:
        request_context.reset(token)
        await hf.aclose()


@pytest.mark.anyio
@pytest.mark.parametrize("startup_failure", [False, True])
async def test_qualified_app_owns_readonly_clients_auth_and_langgraph(tmp_path, monkeypatch, startup_failure):
    proof = accepted(monkeypatch)
    events = []
    class Database:
        def __init__(self, settings): pass
        def startup(self): events.append("database_readonly")
        def teardown(self): events.append("database_closed")
    class HF:
        def __init__(self, *args):
            if startup_failure: raise ValueError("Invalid evidence")
        async def aclose(self): events.append("hf_closed")
    class Ollama:
        async def aclose(self): events.append("ollama_closed")
    search = SimpleNamespace(close=lambda: events.append("search_closed"))
    monkeypatch.setattr(runtime, "ReadOnlyDatabase", Database)
    monkeypatch.setattr(runtime, "make_search_client", lambda settings: search)
    monkeypatch.setattr(runtime, "make_embedder", lambda settings: None)
    monkeypatch.setattr(runtime, "make_ollama_client", lambda settings: Ollama())
    monkeypatch.setattr(runtime, "QualifiedHF", HF)
    monkeypatch.setattr(runtime, "verify_live_source", lambda *args: None)
    app = runtime.create_qualified_app(config(tmp_path), tmp_path / "acceptance.json")
    if startup_failure:
        with pytest.raises(ValueError):
            async with app.router.lifespan_context(app): pytest.fail("Failed startup yielded app")
    else:
        async with app.router.lifespan_context(app):
            assert isinstance(app.state.agent, AgentService)
            assert app.state.rag.ollama is app.state.hf
            assert app.state.rag.cache is None
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://local") as client:
                denied = await client.post("/api/v1/agent/ask", json={"query": "Explain retrieval"})
                assert denied.status_code == 401
                response = await client.post("/api/v1/agent/ask", json={"query": "Explain retrieval", "model": "unapproved"},
                                            headers={"X-API-Key": app.state.settings.api_key.get_secret_value()})
                assert response.status_code == 422
        assert events.pop(1) == "hf_closed"
    assert events == ["database_readonly", "ollama_closed", "search_closed", "database_closed"]
    assert proof["model"] == app.state.settings.hf_default_model


def test_live_source_comparison_is_readonly_and_rejects_changed_corpus(tmp_path, monkeypatch):
    (tmp_path / "state.json").write_text('{"corpus":"accepted"}')
    proof = {"source_snapshot": str(tmp_path)}
    monkeypatch.setattr(runtime, "live_snapshot", lambda settings: ({"corpus": "changed"}, [], []))
    with pytest.raises(ValueError): runtime.verify_live_source(config(tmp_path), proof)


@pytest.mark.anyio
@pytest.mark.parametrize("failure", ["memory", "nan", "context", "schema", "missing_usage", "invalid_output"])
async def test_runtime_rejects_unsafe_calls_and_never_continues_failed_request(
    tmp_path, monkeypatch, stub_httpx, failure,
):
    accepted(monkeypatch)
    usage = {} if failure == "missing_usage" else {"usage": {"prompt_tokens": 100, "completion_tokens": 20}}
    calls = stub_httpx(lambda request: httpx.Response(200, json=envelope(
        '{"in_scope":"invalid"}' if failure == "invalid_output" else '{"in_scope":true}', **usage)))
    hf = runtime.QualifiedHF(config(tmp_path), tmp_path / "acceptance.json",
        memory=lambda: float("nan") if failure == "nan" else 599 if failure == "memory" else 4096)
    case = load_cerebras()["cases"][0]
    kwargs = arguments(case)
    if failure == "schema": kwargs["response_format"] = {"type": "object"}
    token = request_context.set(None if failure == "context" else {"request_id": "owner-question"})
    try:
        with pytest.raises((HFGenerationError, HFResponseError)):
            await hf.generate_result(hf.settings.hf_default_model, case["prompt"], **kwargs)
        if failure != "context":
            with pytest.raises(HFGenerationError):
                await hf.generate_result(hf.settings.hf_default_model, case["prompt"], **arguments(case))
        assert hf.attempts == len(calls) == (1 if failure in {"missing_usage", "invalid_output"} else 0)
    finally:
        request_context.reset(token)
        await hf.aclose()
