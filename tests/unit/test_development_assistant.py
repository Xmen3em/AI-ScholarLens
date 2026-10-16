import asyncio
import json

import httpx
import pytest
from pydantic import SecretStr, ValidationError
from src.operations import request_context
from src.schemas.api.assistant import LearningDecision, LearningResponse
from src.schemas.api.rag import AskRequest
from src.services.development_assistant import DevelopmentAssistant
from src.services.development_pc_api import DevelopmentHF
from src.services.hf.client import HFGenerationError, HFResponseError
from src.services.hf.rag import HostedRAGService
from src.services.telegram_bot import OffsetStore, PrivateTelegramBot

from tests.unit.test_agent_service import EVIDENCE, QUESTION, Model, Search
from tests.unit.test_development_bot import config
from tests.unit.test_hf_client import envelope
from tests.unit.test_hf_tokenizer import install_vocabulary
from tests.unit.test_telegram_bot import KEY
from tests.unit.test_telegram_bot import settings as bot_settings
from tests.unit.test_telegram_policy import update


@pytest.mark.anyio
@pytest.mark.parametrize('question', ['what is the RAG', 'understand ML systems'])
async def test_concept_question_uses_one_call_and_no_paper_search(tmp_path, question):
    model = Model([{'kind': 'general', 'explanation': 'A clear explanation of this machine learning concept.'}])
    rag = HostedRAGService(Search(), model, config(tmp_path))
    assistant = DevelopmentAssistant(rag, rag.settings)
    response = await assistant.ask(AskRequest(query=question, use_hybrid=False))
    assert isinstance(response, LearningResponse) and response.kind == 'general_explanation'
    assert response.query == question and response.model_calls == 1
    assert not rag.search.calls and len(model.calls) == 1
    assert 'citations' not in response.model_dump()


@pytest.mark.anyio
async def test_paper_question_keeps_real_langgraph_quotes_and_total_call_count(tmp_path):
    model = Model([{'kind': 'paper', 'explanation': ''}, {'relevant_markers': ['[1.1]']}, {'answer': 'E1'}])
    rag = HostedRAGService(Search(), model, config(tmp_path))
    assistant = DevelopmentAssistant(rag, rag.settings)
    response = await assistant.ask(AskRequest(query=QUESTION, use_hybrid=False))
    assert response.answer == f'"{EVIDENCE}" [1.1]'
    assert response.model_calls == len(model.calls) == 3
    assert response.steps == ['validate', 'retrieve', 'grade', 'answer']
    assert len(rag.search.calls) == 1


@pytest.mark.anyio
async def test_missing_paper_fact_never_falls_back_to_model_knowledge(tmp_path):
    model = Model([{'kind': 'paper', 'explanation': ''}, {'relevant_markers': ['[1.1]']}, {'answer': 'NONE'}])
    rag = HostedRAGService(Search(), model, config(tmp_path))
    response = await DevelopmentAssistant(rag, rag.settings).ask(AskRequest(query=QUESTION, use_hybrid=False))
    assert response.outcome == 'abstained' and response.model_calls == 3
    assert len(model.calls) == 3


@pytest.mark.anyio
async def test_out_of_scope_question_gets_fixed_help_without_retrieval(tmp_path):
    model = Model([{'kind': 'out_of_scope', 'explanation': ''}])
    rag = HostedRAGService(Search(), model, config(tmp_path))
    response = await DevelopmentAssistant(rag, rag.settings).ask(AskRequest(query='Plan a beach holiday'))
    assert response.kind == 'out_of_scope' and 'AI/ML' in response.answer
    assert not rag.search.calls and len(model.calls) == 1


@pytest.mark.parametrize('answer', ['invented source [1.1]', 'https://example.com/source', 'word ' * 201])
def test_general_explanation_cannot_impersonate_paper_citations_or_overflow(answer):
    with pytest.raises(ValidationError):
        LearningResponse(query='Explain RAG', kind='general_explanation', answer=answer,
                         model='openai/gpt-oss-120b:cerebras')


def test_router_cannot_generate_an_unverified_paper_answer():
    with pytest.raises(ValidationError):
        LearningDecision(kind='paper', explanation='This paper achieves 99 percent accuracy.')


@pytest.mark.anyio
@pytest.mark.parametrize('invalid', [False, True])
async def test_learning_contract_is_validated_at_actual_hf_boundary(tmp_path, monkeypatch, stub_httpx, invalid):
    install_vocabulary(tmp_path, monkeypatch)
    value = {'kind': 'paper', 'explanation': 'An invented paper result.'} if invalid else {
        'kind': 'general', 'explanation': 'RAG combines retrieval with generation.'}
    calls = stub_httpx(lambda request: httpx.Response(200, json=envelope(
        json.dumps(value), usage={'prompt_tokens': 150, 'completion_tokens': 50})))
    hf = DevelopmentHF(config(tmp_path), memory=lambda: 4096)
    token = request_context.set({'request_id': 'concept-question'})
    kwargs = {'response_format': LearningDecision.model_json_schema()}
    try:
        if invalid:
            with pytest.raises(HFResponseError): await hf.generate(hf.settings.hf_default_model, 'Explain RAG', **kwargs)
            with pytest.raises(HFGenerationError): await hf.generate(hf.settings.hf_default_model, 'Explain RAG', **kwargs)
        else:
            result = await hf.generate(hf.settings.hf_default_model, 'Explain RAG', **kwargs)
            assert json.loads(result.response) == value
        assert len(calls) == hf.attempts == 1
    finally:
        request_context.reset(token)
        await hf.aclose()


@pytest.mark.anyio
async def test_router_is_inside_original_question_deadline(tmp_path):
    class SlowModel:
        async def generate(self, *args, **kwargs):
            await asyncio.sleep(10)
    rag = HostedRAGService(Search(), SlowModel(), config(tmp_path))
    assistant = DevelopmentAssistant(rag, rag.settings)
    assistant.deadline_seconds = 0.01
    with pytest.raises(TimeoutError): await assistant.ask(AskRequest(query='Explain RAG'))
    assert not rag.search.calls


@pytest.mark.anyio
@pytest.mark.parametrize('development_assistant', [False, True])
async def test_only_opted_in_bot_displays_labeled_concept_answers(tmp_path, stub_httpx, development_assistant):
    body = {'query': 'what is RAG', 'kind': 'general_explanation', 'answer': 'RAG combines retrieval with generation.',
            'model': 'openai/gpt-oss-120b:cerebras', 'model_calls': 1}
    def handler(request):
        if request.url.host == '127.0.0.1': return httpx.Response(200, json=body)
        return httpx.Response(200, json={'ok': True, 'result': {'message_id': 1}})
    calls = stub_httpx(handler)
    async with PrivateTelegramBot(bot_settings(), SecretStr(KEY), OffsetStore(tmp_path / 'offset.json'),
                                  development_assistant=development_assistant) as bot:
        result = await bot.handle(update('what is RAG'))
    assert result == ('answered' if development_assistant else 'api_failed')
    text = json.loads(calls[-1].content)['text']
    if development_assistant:
        assert 'model knowledge' in text and 'Papers:' not in text
        assert 'RAG combines retrieval' in text
    else:
        assert 'RAG combines retrieval' not in text


@pytest.mark.anyio
@pytest.mark.parametrize('owner', [True, False])
async def test_development_help_explains_modes_and_still_rejects_nonowner(tmp_path, stub_httpx, owner):
    from tests.unit.test_telegram_policy import OWNER
    calls = stub_httpx(lambda request: httpx.Response(200, json={'ok': True, 'result': {'message_id': 1}}))
    message = update('/start')
    if not owner: message['message']['from']['id'] = OWNER + 1
    async with PrivateTelegramBot(bot_settings(), SecretStr(KEY), OffsetStore(tmp_path / 'offset.json'),
                                  development_assistant=True) as bot:
        assert await bot.handle(message) == ('help' if owner else 'ignored')
    if owner:
        assert len(calls) == 1 and calls[0].url.host == 'api.telegram.org'
        text = json.loads(calls[0].content)['text']
        assert 'model knowledge' in text and 'paper answers include citations' in text
    else:
        assert not calls
