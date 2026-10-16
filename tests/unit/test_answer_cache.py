import json
from unittest.mock import AsyncMock

import pytest
from src.answer_cache import AnswerCache, ResourceIdentity, cache_policy_digest
from src.config import Settings
from src.schemas.api.rag import AskRequest, AskResponse
from src.services.rag.context import INSUFFICIENT_EVIDENCE_ANSWER


def response(request):
    return AskResponse(query=request.query, answer=INSUFFICIENT_EVIDENCE_ANSWER, sources=[], citations=[],
                       chunks_used=0, search_mode='bm25', model='llama3.2:1b')


@pytest.fixture
def cache():
    store = AsyncMock()
    store.get.return_value = None
    settings = Settings(_env_file=None, api_key='k' * 32)
    identity = AsyncMock(return_value={'corpus': 'revision1', 'indexes': 'index1', 'models': 'digest1'})
    return AnswerCache(store, identity, settings), store, identity


@pytest.mark.anyio
async def test_only_validated_results_are_signed_and_expire(cache):
    service, store, identity = cache
    request = AskRequest(query='private exact query', use_hybrid=False)
    ticket = await service.lookup(request)
    await service.store(ticket, response(request))
    key, payload = store.set.call_args.args
    assert 'private' not in key
    assert store.set.call_args.kwargs['ex'] == 3600
    store.get.return_value = payload
    hit = await service.lookup(request)
    assert hit.response == response(request)
    # Cache tampering must not acquire server ownership of citations or text.
    store.get.return_value = payload.replace('insufficient', 'sufficient')
    assert (await service.lookup(request)).response is None
    # A structurally valid but forged citation catalog must fail the signature,
    # even though the fixed abstention and schema still validate.
    envelope = json.loads(payload)
    content = json.loads(envelope['payload'])
    content['citations'] = [dict(marker='[1.1]', arxiv_id='2601.00001', title='forged paper',
                                section_title='Methods', section_index=0, chunk_index=0, evidence='forged evidence')]
    content['chunks_used'] = 1
    content['sources'] = ['https://arxiv.org/pdf/2601.00001.pdf']
    envelope['payload'] = json.dumps(content)
    store.get.return_value = json.dumps(envelope)
    assert (await service.lookup(request)).response is None


@pytest.mark.anyio
async def test_invalidation_includes_effective_options_and_revision(cache):
    service, store, identity = cache
    original = AskRequest(query='q', use_hybrid=False)
    first = await service.lookup(original)
    explicit_default = await service.lookup(original.model_copy(update={'model': 'llama3.2:1b'}))
    assert first.key == explicit_default.key
    for changes in [{'query': 'Q'}, {'top_k': 4}, {'use_hybrid': True}, {'categories': ['cs.AI']}, {'categories': []}]:
        assert (await service.lookup(original.model_copy(update=changes))).key != first.key
    identity.return_value = {'corpus': 'revision2', 'indexes': 'index1', 'models': 'digest1'}
    assert (await service.lookup(original)).key != first.key
    await service.store(first, response(original))
    store.set.assert_not_awaited()
    assert len(cache_policy_digest()) == 64


def test_candidate_catalog_limits_cannot_share_a_cached_answer(cache):
    service, store, identity = cache
    request = AskRequest(query='same paper question')
    revision = {'corpus': 'unchanged'}
    keys = {service.key(request, revision)}
    for limit in (2, 10):
        bounded = AnswerCache(store, identity, service.settings.model_copy(update={'rag_max_sentence_candidates': limit}))
        keys.add(bounded.key(request, revision))
    assert len(keys) == 3


@pytest.mark.anyio
async def test_unavailability_invalid_answers_and_degradation_never_break_requests(cache):
    service, store, identity = cache
    request = AskRequest(query='q', use_hybrid=False)
    ticket = await service.lookup(request)
    await service.store(ticket, response(request).model_copy(update={'answer': 'unsupported [1.1]'}))
    store.set.assert_not_awaited()
    store.get.side_effect = RuntimeError('private Redis error')
    assert (await service.lookup(request)).response is None
    identity.side_effect = RuntimeError('private backend error')
    assert (await service.lookup(request)).key is None


@pytest.mark.anyio
async def test_hybrid_fallback_is_not_cached(cache):
    service, store, identity = cache
    request = AskRequest(query='q', use_hybrid=True)
    ticket = await service.lookup(request)
    await service.store(ticket, response(request))
    store.set.assert_not_awaited()


@pytest.mark.anyio
async def test_runtime_revision_probes_track_corpus_indexes_visibility_and_models(monkeypatch):
    from copy import deepcopy

    identity = ResourceIdentity(Settings(_env_file=None))
    metadata = {'index-v2': {'aliases': {'arxiv-papers': {}, 'paper-chunks': {}},
                            'settings': {'index': {'uuid': 'uuid-1'}}, 'mappings': {}}}
    stats = {'_shards': {'failed': 0}, 'indices': {'index-v2': {'shards': {'0': [
        {'routing': {'primary': True}, 'seq_no': {'max_seq_no': 10, 'global_checkpoint': 10}}
    ]}}}}
    segments = {'_shards': {'failed': 0}, 'indices': {'index-v2': {'shards': {'0': [
        {'routing': {'primary': True}, 'segments': {'_1': {'generation': 1, 'num_docs': 58, 'deleted_docs': 0, 'search': True}}}
    ]}}}}
    models = {'models': [{'name': 'llama3.2:1b', 'digest': 'generation-digest'},
                         {'name': 'nomic-embed-text:latest', 'digest': 'embedding-digest'}]}
    corpus = {'content_md5': 'full-corpus-content', 'schema_revision': '1', 'papers': 58}
    monkeypatch.setattr(identity, 'corpus', lambda: deepcopy(corpus))
    async def get(origin, path):
        if path.endswith('_segments'):
            return deepcopy(segments)
        if '_stats' in path:
            return deepcopy(stats)
        if path == '/api/tags':
            return deepcopy(models)
        return deepcopy(metadata)
    monkeypatch.setattr(identity, 'get', get)
    try:
        original = await identity()
        stats['indices']['index-v2']['shards']['0'][0]['seq_no']['max_seq_no'] = 11
        assert (await identity())['indexes'] != original['indexes']
        stats['indices']['index-v2']['shards']['0'][0]['seq_no']['max_seq_no'] = 10
        segments['indices']['index-v2']['shards']['0'][0]['segments']['_1']['generation'] = 2
        assert (await identity())['indexes'] != original['indexes']
        corpus['content_md5'] = 'changed'
        assert (await identity())['corpus'] != original['corpus']
        models['models'][0]['digest'] = 'changed-model'
        assert (await identity())['models'] != original['models']
        metadata['index-v2']['aliases'].pop('paper-chunks')
        with pytest.raises(ValueError):
            await identity()
    finally:
        await identity.close()


@pytest.mark.anyio
async def test_cache_store_failure_and_wrong_controls_are_bypassed(cache):
    service, redis, identity = cache
    request = AskRequest(query='q', use_hybrid=False)
    ticket = await service.lookup(request)
    redis.set.side_effect = RuntimeError('secret Redis failure')
    await service.store(ticket, response(request))
    redis.set.assert_awaited_once()
    redis.set.reset_mock()
    await service.store(ticket, response(request).model_copy(update={'query': 'different'}))
    redis.set.assert_not_awaited()


def test_cache_disabled_by_default_and_cloud_redis_rejected():
    from pydantic import ValidationError
    from src.answer_cache import make_answer_cache
    assert make_answer_cache(Settings(_env_file=None)) is None
    with pytest.raises(ValidationError):
        Settings(_env_file=None, answer_cache_enabled=True, api_key='k' * 32,
                 answer_cache_url='redis://remote.example:6379/0')
