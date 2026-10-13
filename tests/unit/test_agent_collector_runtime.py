import asyncio
import json
import logging

import pytest
from src.commands.evaluate_agent import Measurements, collect_attempt, memory_watch
from src.operations import emit_event, request_context


def test_request_measurements_count_unsuccessful_calls_and_preserve_privacy():
    handler = Measurements()
    logger = logging.getLogger("src.operations")
    previous = logger.level
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    context = {"request_id": "a" * 32, "evaluation_counts": {"generation_calls": 2, "retrieval_calls": 1, "embedding_calls": 0}}
    token = request_context.set(context)
    try:
        emit_event("rag_generation", prompt_tokens=10, output_tokens=3, answer="private output")
        emit_event("http_request_completed", duration_ms=10, outcome="failed", query="private query")
        recorded = handler.requests["a" * 32]
        assert recorded["generation_calls"] == 2 and recorded["completed_generations"] == 1
        assert recorded["prompt_tokens"] == 10
        assert "private" not in json.dumps(recorded)
    finally:
        request_context.reset(token)
        logger.removeHandler(handler)
        logger.setLevel(previous)


@pytest.mark.anyio
async def test_memory_watch_cancels_at_emergency_floor_without_sending_new_work():
    finished = asyncio.Event()
    cancelled = asyncio.Event()
    task_started = asyncio.Event()

    async def blocked():
        task_started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    task = asyncio.create_task(blocked())
    await task_started.wait()
    samples = []
    await memory_watch(task, finished, samples, lambda: 383)
    with pytest.raises(asyncio.CancelledError):
        await task
    assert cancelled.is_set() and samples[0]["free_mib"] == 383


@pytest.mark.anyio
async def test_unavailable_memory_monitor_cancels_inflight_request():
    task = asyncio.create_task(asyncio.Event().wait())
    samples = []

    def unavailable():
        raise OSError("cannot inspect RAM")

    await memory_watch(task, asyncio.Event(), samples, unavailable)
    with pytest.raises(asyncio.CancelledError):
        await task
    assert samples[0]["error_type"] == "MemoryInspectionFailure"


@pytest.mark.anyio
async def test_http_failure_is_recorded_and_never_retried():
    import httpx

    calls = []

    def failed(request):
        calls.append(request)
        return httpx.Response(429, headers={"Retry-After": "2"}, json={"detail": "Rate limit exceeded"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(failed), base_url="http://test") as client:
        record = await collect_attempt(client, {"key": "test", "case_id": "case", "query": "test", "mode": "bm25",
                                               "path": "agent", "transport": "json"},
                                       Measurements(), [], [], memory=lambda: 4096)
    assert len(calls) == 1 and not record["ok"] and record["http_status"] == 429
    assert record["retry_after_seconds"] == 2 and "response" not in record


@pytest.mark.anyio
async def test_post_response_client_timeout_is_a_failure_not_an_abstention():
    import httpx

    def timeout(request):
        raise httpx.ReadTimeout("private timeout message", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(timeout), base_url="http://test") as client:
        record = await collect_attempt(client, {"key": "test", "case_id": "case", "query": "test", "mode": "hybrid",
                                               "path": "baseline", "transport": "json"},
                                       Measurements(), [], [], memory=lambda: 4096)
    assert not record["ok"] and record["error_type"] == "ReadTimeout"
    assert "private" not in json.dumps(record)


@pytest.mark.anyio
async def test_real_loopback_runner_counts_both_uncached_paths_with_mocked_provider(monkeypatch, writable_cache_dir):
    import httpx
    from src.commands.agent_collection import build_jobs
    from src.commands.evaluate_agent import run_jobs
    from src.config import Settings
    from src.services.search import SearchService

    from tests.unit.test_agent_service import EVIDENCE, QUESTION, search_result

    settings = Settings(_env_file=None, api_key="a" * 32)
    real_client = httpx.AsyncClient
    provider_requests = []

    def provider(request):
        provider_requests.append(request)
        payload = json.loads(request.content)
        properties = payload.get("format", {}).get("properties", {})
        output = ({"in_scope": True} if "in_scope" in properties else
                  {"relevant_markers": ["[1.1]"]} if "relevant_markers" in properties else {"answer": "E1"})
        return httpx.Response(200, json={"model": "llama3.2:1b", "response": json.dumps(output), "done": True,
                                         "prompt_eval_count": 10, "eval_count": 3})

    def client(*args, **kwargs):
        if kwargs.get("base_url") == settings.ollama_host:
            kwargs["transport"] = httpx.MockTransport(provider)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client)
    monkeypatch.setattr(SearchService, "search_chunks", lambda *args, **kwargs: search_result())
    monkeypatch.setattr("src.commands.evaluate_agent.free_memory_mib", lambda: 4096)
    # collect_attempt's default memory callback is bound at definition time;
    # patch the wrapper to pass the deterministic sampler explicitly.
    from src.commands.evaluate_agent import collect_attempt as collect

    async def collect_with_memory(*args, **kwargs):
        return await collect(*args, **kwargs, memory=lambda: 4096)

    monkeypatch.setattr("src.commands.evaluate_agent.collect_attempt", collect_with_memory)
    jobs = build_jobs([{"id": "loopback", "query": QUESTION}], modes=("bm25",), transports=("json",))
    papers = [{"arxiv_id": "2609.99999", "sections": [{"content": ""}, {"content": ""}, {"content": EVIDENCE}]}]
    chunks = [{"arxiv_id": "2609.99999", "section_index": 2, "chunk_index": 3, "section_title": "Method", "content": EVIDENCE}]
    completion = await run_jobs(settings, jobs, papers, chunks, writable_cache_dir)
    assert completion["status"] == "collected" and completion["failures"] == 0
    records = [json.loads(line) for line in (writable_cache_dir / "records.jsonl").read_text().splitlines()]
    assert [r["measured"]["generation_calls"] for r in records] == [1, 3]
    assert [r["measured"]["retrieval_calls"] for r in records] == [1, 1]
    assert len(provider_requests) == 4
    assert all(r["attribution_passed"] and r["resource_passed"] for r in records)
