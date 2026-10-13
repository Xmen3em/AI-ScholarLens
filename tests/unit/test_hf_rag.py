import json
from unittest.mock import AsyncMock

import httpx
import pytest
from src.exceptions import GroundingError, OllamaResponseError, UnsupportedModelError
from src.schemas.api.rag import AskRequest
from src.services.agent import AgentService
from src.services.hf.client import HFClient, HFGenerationError
from src.services.hf.rag import HostedRAGService

from tests.unit.test_agent_service import EVIDENCE, QUESTION, Search
from tests.unit.test_hf_client import envelope, settings
from tests.unit.test_hf_configuration import MODEL


def hosted(stub_httpx, outputs):
    def respond(request):
        output = outputs.pop(0)
        return httpx.Response(200, json=envelope(json.dumps(output) if isinstance(output, dict) else output))

    calls = stub_httpx(respond)
    config = settings(agent_enabled=True)
    client = HFClient(config)
    rag = HostedRAGService(Search(), client, config)
    rag.cache = AsyncMock()
    return config, client, rag, calls


@pytest.mark.anyio
async def test_hosted_agent_uses_original_domain_retrieval_and_quote_guards(stub_httpx):
    config, client, rag, calls = hosted(stub_httpx, [{"in_scope": True}, {"relevant_markers": ["[1.1]"]}, {"answer": "E1"}])
    try:
        response = await AgentService(rag, config).ask(AskRequest(query=QUESTION, use_hybrid=False))
        assert response.answer == f'"{EVIDENCE}" [1.1]' and response.model == MODEL
        assert response.model_calls == client.attempts == len(calls) == 3
        assert response.query == QUESTION and response.citations[0].evidence == EVIDENCE
        assert not rag.cache.mock_calls
        bodies = [json.loads(call.content) for call in calls]
        assert [body["max_tokens"] for body in bodies] == [256, 256, 512]
        assert bodies[-1]["response_format"]["json_schema"]["schema"]["properties"]["answer"]["pattern"].startswith("^")
    finally:
        await client.aclose()


@pytest.mark.anyio
@pytest.mark.parametrize("decision", [{"in_scope": "true"}, {"in_scope": 1}, {"in_scope": True, "extra": 1}])
async def test_bad_controller_decision_cannot_start_retrieval(stub_httpx, decision):
    config, client, rag, calls = hosted(stub_httpx, [decision])
    try:
        with pytest.raises(OllamaResponseError):
            await AgentService(rag, config).ask(AskRequest(query=QUESTION, use_hybrid=False))
        assert not rag.search.calls and len(calls) == 1
    finally:
        await client.aclose()


@pytest.mark.anyio
@pytest.mark.parametrize("selection", ["E999", "E1 E1", "E2 E1", "invented answer [1.1]"])
async def test_invalid_selection_is_never_rendered_and_only_existing_retry_is_allowed(stub_httpx, selection):
    config, client, rag, calls = hosted(stub_httpx, [{"in_scope": True}, {"relevant_markers": ["[1.1]"]},
                                                {"answer": selection}, selection])
    try:
        with pytest.raises((GroundingError, OllamaResponseError)):
            await AgentService(rag, config).ask(AskRequest(query=QUESTION, use_hybrid=False))
        assert client.attempts == len(calls) == 4
        assert "response_format" not in json.loads(calls[-1].content)
        assert not rag.cache.mock_calls
    finally:
        await client.aclose()


@pytest.mark.anyio
async def test_hosted_baseline_reports_effective_model_and_original_question(stub_httpx):
    config, client, rag, calls = hosted(stub_httpx, [{"answer": "E1"}])
    # The main hosted factory leaves cache absent; baseline never uses local entries.
    rag.cache = None
    try:
        response = await rag.ask(AskRequest(query=QUESTION, use_hybrid=False))
        assert response.answer == f'"{EVIDENCE}" [1.1]' and response.model == MODEL
        assert client.attempts == len(calls) == 1
        with pytest.raises(UnsupportedModelError):
            await rag.prepare(AskRequest(query=QUESTION, model="llama3.2:1b", use_hybrid=False))
        assert len(calls) == 1
    finally:
        await client.aclose()


@pytest.mark.anyio
async def test_oversize_original_schema_aborts_without_paid_attempt_or_schema_downgrade(stub_httpx):
    from src.services.rag.service import _selection_pattern

    config, client, rag, calls = hosted(stub_httpx, [])
    schema = {"type": "object", "properties": {"answer": {"type": "string", "pattern": _selection_pattern(30)}},
              "required": ["answer"], "additionalProperties": False}
    try:
        with pytest.raises(HFGenerationError):
            await client.generate(MODEL, "question", response_format=schema)
        assert not calls and client.attempts == 0
    finally:
        await client.aclose()
