from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from src.answer_cache import AnswerCache
from src.config import Settings
from src.dependencies import get_rag
from src.main import app
from src.middlewares import OperationalMiddleware
from src.routers.ask import router
from src.schemas.api.rag import AskRequest
from src.schemas.api.search import ChunkSearchResponse, PaperPassages, PassageHit
from src.schemas.ollama import OllamaGenerateResponse
from src.services.rag.service import RAGService


def service(settings):
    search = SimpleNamespace(search_chunks=lambda *a, **kw: ChunkSearchResponse(query=a[0], total=0, took_ms=1, hits=[]))
    rag = RAGService(search, SimpleNamespace(), settings)
    redis = AsyncMock()
    entries = {}
    redis.get.side_effect = lambda key: entries.get(key)
    async def store(key, value, **kwargs):
        entries[key] = value
    redis.set.side_effect = store
    rag.cache = AnswerCache(redis, AsyncMock(return_value={'revision': 1}), settings)
    return rag, redis


@pytest.mark.anyio
async def test_ask_and_stream_share_validated_entries_and_still_spend_quota(writable_cache_dir):
    settings = Settings(_env_file=None, api_key='k' * 32, api_generations_per_minute=2,
                        api_rate_limit_path=str(writable_cache_dir / 'cache-route-limits'))
    rag, redis = service(settings)
    local = FastAPI()
    local.include_router(router, prefix='/api/v1')
    local.dependency_overrides[get_rag] = lambda: rag
    local.add_middleware(OperationalMiddleware, settings=settings)
    async with AsyncClient(transport=ASGITransport(app=local), base_url='http://test') as client:
        body = {'query': 'private question', 'use_hybrid': False}
        assert (await client.post('/api/v1/ask', json=body)).status_code == 401
        redis.get.assert_not_awaited()
        headers = {'X-API-Key': 'k' * 32}
        ask = await client.post('/api/v1/ask', json=body, headers=headers)
        stream = await client.post('/api/v1/stream', json=body, headers=headers)
        assert ask.status_code == stream.status_code == 200
        assert ask.json()['answer'] in stream.text
        assert redis.set.await_count == 1
        before = redis.get.await_count
        assert (await client.post('/api/v1/ask', json=body, headers=headers)).status_code == 429
        assert redis.get.await_count == before


@pytest.mark.anyio
async def test_stream_stores_only_after_successful_delivery(writable_cache_dir):
    settings = Settings(_env_file=None, api_key='k' * 32, api_rate_limit_path=str(writable_cache_dir / 'limits-stream'))
    rag, redis = service(settings)
    local = FastAPI()
    local.include_router(router, prefix='/api/v1')
    local.dependency_overrides[get_rag] = lambda: rag
    local.add_middleware(OperationalMiddleware, settings=settings)
    async with AsyncClient(transport=ASGITransport(app=local), base_url='http://test') as client:
        response = await client.post('/api/v1/stream', json={'query': 'q', 'use_hybrid': False},
                                     headers={'X-API-Key': 'k' * 32})
    assert 'event: done' in response.text
    redis.set.assert_awaited_once()


@pytest.mark.anyio
async def test_interrupted_delivery_does_not_store(writable_cache_dir):
    settings = Settings(_env_file=None, api_key='k' * 32, api_rate_limit_path=str(writable_cache_dir / 'limits-disconnect'))
    rag, redis = service(settings)
    local = FastAPI()
    local.include_router(router, prefix='/api/v1')
    local.dependency_overrides[get_rag] = lambda: rag
    local.add_middleware(OperationalMiddleware, settings=settings)
    request = AskRequest(query='q', use_hybrid=False).model_dump_json().encode()
    delivered = False
    async def receive():
        nonlocal delivered
        if not delivered:
            delivered = True
            return {'type': 'http.request', 'body': request, 'more_body': False}
        return {'type': 'http.disconnect'}
    async def send(message):
        if message['type'] == 'http.response.body' and b'event: done' in message.get('body', b''):
            raise OSError('client disconnected')
    scope = {'type': 'http', 'method': 'POST', 'path': '/api/v1/stream', 'query_string': b'',
             'headers': [(b'x-api-key', b'k' * 32), (b'content-type', b'application/json')],
             'scheme': 'http', 'server': ('test', 80), 'client': ('127.0.0.1', 1),
             'http_version': '1.1', 'asgi': {'version': '3.0', 'spec_version': '2.4'}}
    with pytest.raises(Exception):
        await local(scope, receive, send)
    redis.set.assert_not_awaited()


@pytest.mark.anyio
async def test_nonempty_server_owned_citations_and_exact_answer_survive_cache(client):
    import json

    settings = Settings(_env_file=None, api_key='k' * 32)
    rag, redis = service(settings)
    paper = PaperPassages(arxiv_id='2601.00001v2', title='Grounded Generation', categories=['cs.CL'], score=1,
                         passages=[PassageHit(section_title='Methods', section_index=3, chunk_index=1, score=1,
                                              content='The method binds claims to retrieved evidence.')])
    from unittest.mock import Mock
    search = Mock(wraps=lambda *args, **kwargs: ChunkSearchResponse(query=args[0], total=1, took_ms=1, hits=[paper]))
    rag.search = SimpleNamespace(search_chunks=search)
    rag.ollama = SimpleNamespace(generate=AsyncMock(return_value=OllamaGenerateResponse(
        model='llama3.2:1b', response='{"answer":"E1"}', done=True)))
    app.dependency_overrides[get_rag] = lambda: rag
    try:
        body = {'query': 'How does the method bind claims to retrieved evidence?', 'use_hybrid': False}
        first = await client.post('/api/v1/ask', json=body)
        stream = await client.post('/api/v1/stream', json=body)
        assert first.status_code == stream.status_code == 200
        frames = [(frame.splitlines()[0][7:], json.loads(frame.splitlines()[1][6:]))
                  for frame in stream.text.strip().split('\n\n')]
        assert frames[0][1]['citations'] == first.json()['citations']
        assert frames[0][1]['sources'] == first.json()['sources']
        assert frames[-1][1]['answer'] == first.json()['answer']
        assert '"The method binds claims to retrieved evidence." [1.1]' == first.json()['answer']
        search.assert_called_once()
        rag.ollama.generate.assert_awaited_once()
    finally:
        app.dependency_overrides.pop(get_rag, None)
