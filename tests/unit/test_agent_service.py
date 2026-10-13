import asyncio
import json
import threading
from unittest.mock import AsyncMock

import pytest
from src.config import Settings
from src.exceptions import GroundingError, OllamaResponseError, UnsupportedModelError
from src.schemas.api.agent import AgentResponse
from src.schemas.api.rag import AskRequest
from src.schemas.api.search import ChunkSearchResponse, HybridSearchResponse, PaperPassages, PassageHit
from src.schemas.ollama import OllamaGenerateResponse
from src.services.agent import AgentService, _Run
from src.services.rag.context import INSUFFICIENT_EVIDENCE_ANSWER
from src.services.rag.service import RAGService

QUESTION = "How does the neural retrieval method bind claims to evidence?"
EVIDENCE = "The neural retrieval method binds claims to evidence using passage identifiers."


def search_result(empty=False):
    return ChunkSearchResponse(query=QUESTION, total=0 if empty else 1, took_ms=1, hits=[] if empty else [
        PaperPassages(arxiv_id="2609.99999", title="Neural Retrieval", categories=["cs.AI"], score=1,
                      passages=[PassageHit(section_title="Method", section_index=2, chunk_index=3,
                                           content=EVIDENCE, score=1)])
    ])


class Search:
    def __init__(self, results=None):
        self.results = results or [search_result()]
        self.calls = []

    def search_chunks(self, query, **controls):
        self.calls.append((query, controls))
        return self.results[min(len(self.calls) - 1, len(self.results) - 1)]

    search_hybrid = search_chunks


class Model:
    def __init__(self, outputs):
        self.outputs = outputs
        self.calls = []

    async def generate(self, model, prompt, **kwargs):
        self.calls.append((model, prompt, kwargs))
        output = self.outputs.pop(0)
        if isinstance(output, Exception):
            raise output
        return OllamaGenerateResponse(model=model, response=output if isinstance(output, str) else json.dumps(output), done=True)


def service(outputs, results=None, **settings):
    config = Settings(_env_file=None, agent_enabled=True, **settings)
    rag = RAGService(Search(results), Model(outputs), config)
    rag.cache = AsyncMock()  # Any cache access is a failure of path isolation.
    return AgentService(rag, config)


async def answer(agent, **controls):
    return await agent.ask(AskRequest(query=QUESTION, use_hybrid=False, **controls))


@pytest.mark.anyio
async def test_direct_answer_uses_real_selector_guards_and_never_cache():
    agent = service([{"in_scope": True}, {"relevant_markers": ["[1.1]"]}, {"answer": "E1"}])
    response = await answer(agent, categories=["cs.AI"], top_k=2)
    assert response.answer == f'"{EVIDENCE}" [1.1]'
    assert response.query == QUESTION and response.outcome == "answered"
    assert response.model_calls == 3 and response.retrieval_attempts == 1
    assert response.steps == ["validate", "retrieve", "grade", "answer"]
    assert response.citations[0].evidence == EVIDENCE
    assert agent.rag.search.calls == [(QUESTION, {"size": 2, "offset": 0, "categories": ["cs.AI"]})]
    agent.rag.cache.lookup.assert_not_called()
    agent.rag.cache.store.assert_not_called()


@pytest.mark.anyio
async def test_refinement_and_selector_retry_stay_within_six_calls_and_original_question():
    rewrite = "neural retrieval passage identifiers"
    agent = service([{"in_scope": True}, {"relevant_markers": []}, {"query": rewrite},
                     {"relevant_markers": ["[1.1]"]}, {"answer": "E999"}, "E1"])
    response = await answer(agent)
    assert response.outcome == "answered" and response.rewritten
    assert response.retrieval_attempts == 2 and response.model_calls == 6
    assert [call[0] for call in agent.rag.search.calls] == [QUESTION, rewrite]
    assert QUESTION in agent.rag.ollama.calls[-1][1]
    assert rewrite not in agent.rag.ollama.calls[-1][1]
    assert response.query == QUESTION and len(response.steps) <= 8


@pytest.mark.anyio
async def test_scope_rejection_has_no_retrieval_and_no_evidence():
    agent = service([{"in_scope": False}])
    response = await answer(agent)
    assert response.outcome == "out_of_scope" and response.answer == INSUFFICIENT_EVIDENCE_ANSWER
    assert response.citations == [] and response.sources == [] and response.model_calls == 1
    assert not agent.rag.search.calls


@pytest.mark.anyio
@pytest.mark.parametrize("empty", [False, True])
async def test_exhausted_refinement_abstains_without_third_retrieval(empty):
    outputs = [{"in_scope": True}]
    if not empty:
        outputs.append({"relevant_markers": []})
    outputs.append({"query": "neural claim attribution"})
    if not empty:
        outputs.append({"relevant_markers": []})
    agent = service(outputs, [search_result(empty)])
    response = await answer(agent)
    assert response.outcome == "abstained" and response.answer == INSUFFICIENT_EVIDENCE_ANSWER
    assert response.retrieval_attempts == 2 and response.citations == []
    assert len(agent.rag.search.calls) == 2 and not agent.rag.ollama.outputs


@pytest.mark.anyio
@pytest.mark.parametrize("bad", ["{}", '{"in_scope":true,"in_scope":false}', '{"in_scope":"yes"}',
                                     '{"in_scope":true,"reason":"private"}', "x" * 4097])
async def test_invalid_scope_fails_closed(bad):
    agent = service([bad])
    with pytest.raises(OllamaResponseError):
        await answer(agent)
    assert not agent.rag.search.calls and len(agent.rag.ollama.calls) == 1


@pytest.mark.anyio
@pytest.mark.parametrize("bad", [{"relevant_markers": ["[9.9]"]}, {"relevant_markers": ["[1.1]", "[1.1]"]},
                                     {"relevant_markers": "[1.1]"}, {}, {"relevant_markers": [], "extra": 1}])
async def test_invalid_grading_cannot_reach_generation(bad):
    agent = service([{"in_scope": True}, bad])
    with pytest.raises(OllamaResponseError):
        await answer(agent)
    assert len(agent.rag.ollama.calls) == 2 and len(agent.rag.search.calls) == 1


@pytest.mark.anyio
@pytest.mark.parametrize("query", ["", " " * 4, "x" * 501])
async def test_invalid_rewrite_cannot_retrieve_again(query):
    agent = service([{"in_scope": True}, {"relevant_markers": []}, {"query": query}])
    with pytest.raises(OllamaResponseError):
        await answer(agent)
    assert len(agent.rag.search.calls) == 1


@pytest.mark.anyio
async def test_unchanged_rewrite_abstains():
    agent = service([{"in_scope": True}, {"relevant_markers": []}, {"query": QUESTION}])
    response = await answer(agent)
    assert response.outcome == "abstained" and response.retrieval_attempts == 1 and not response.rewritten


@pytest.mark.anyio
async def test_both_invalid_selector_attempts_fail_closed():
    agent = service([{"in_scope": True}, {"relevant_markers": ["[1.1]"]}, {"answer": "E999"}, "E999"])
    with pytest.raises(GroundingError):
        await answer(agent)
    assert len(agent.rag.ollama.calls) == 4


@pytest.mark.anyio
async def test_unconfigured_model_precedes_work():
    agent = service([])
    with pytest.raises(UnsupportedModelError):
        await answer(agent, model="uninstalled")
    assert not agent.rag.ollama.calls and not agent.rag.search.calls


@pytest.mark.anyio
async def test_deadline_cancels_inflight_model(monkeypatch):
    agent = service([], agent_node_timeout_seconds=1, agent_deadline_seconds=1)
    cancelled = asyncio.Event()

    async def blocked(*args, **kwargs):
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    monkeypatch.setattr(agent.rag.ollama, "generate", blocked)
    with pytest.raises(TimeoutError):
        await answer(agent)
    assert cancelled.is_set() and not agent.rag.search.calls


@pytest.mark.anyio
@pytest.mark.parametrize("stage", ["validate", "retrieve", "grade", "rewrite", "answer"])
async def test_cancellation_propagates_at_every_work_boundary(monkeypatch, stage):
    markers = ["[1.1]"] if stage == "answer" else []
    agent = service([{"in_scope": True}, {"relevant_markers": markers}, {"query": "neural retrieval"}])
    started = asyncio.Event()

    async def blocked(*args, **kwargs):
        started.set()
        await asyncio.Event().wait()

    events = agent.events(AskRequest(query=QUESTION, use_hybrid=False))
    async for event in events:
        if not isinstance(event, AgentResponse) and event.operation == stage:
            monkeypatch.setattr(agent, "_retrieve" if stage == "retrieve" else "_model", blocked)
            task = asyncio.create_task(anext(events))
            await started.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            break
    else:
        pytest.fail("requested stage not reached")


@pytest.mark.anyio
async def test_cancelled_sync_retrieval_retains_single_worker_occupancy(monkeypatch):
    agent = service([{"in_scope": True}, {"in_scope": True}])
    started, release = threading.Event(), threading.Event()

    def blocked(*args, **kwargs):
        started.set()
        release.wait(5)
        return search_result()

    monkeypatch.setattr(agent.rag.search, "search_chunks", blocked)
    task = asyncio.create_task(answer(agent))
    try:
        while not started.is_set():
            await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        with pytest.raises(RuntimeError, match="retrieval busy"):
            await answer(agent)
    finally:
        release.set()


@pytest.mark.anyio
@pytest.mark.parametrize("mode", ["hybrid", "keyword"])
async def test_controls_and_actual_hybrid_fallback_are_preserved(mode):
    result = HybridSearchResponse(**search_result().model_dump(), mode=mode,
                                  score_kind="rrf" if mode == "hybrid" else "bm25")
    agent = service([{"in_scope": True}, {"relevant_markers": ["[1.1]"]}, {"answer": "E1"}],
                    [result], ollama_models=["local-test"], ollama_default_model="local-test")
    response = await agent.ask(AskRequest(query=QUESTION, top_k=4, model="local-test", categories=["cs.AI"]))
    assert response.model == "local-test" and all(call[0] == "local-test" for call in agent.rag.ollama.calls)
    assert response.search_mode == ("hybrid" if mode == "hybrid" else "bm25")
    assert agent.rag.search.calls[0][1] == {"size": 4, "offset": 0, "categories": ["cs.AI"]}


@pytest.mark.anyio
async def test_grading_filters_evidence_without_changing_marker_or_source_ownership():
    result = search_result()
    second = result.hits[0].model_copy(deep=True)
    second.arxiv_id = "2609.99998"
    second.passages[0].content = "The neural retrieval method binds claims to evidence with immutable passage keys."
    result.hits.append(second)
    agent = service([{"in_scope": True}, {"relevant_markers": ["[2.1]"]}, {"answer": "E1"}], [result])
    response = await answer(agent)
    assert [c.marker for c in response.citations] == ["[2.1]"]
    assert response.sources == ["https://arxiv.org/pdf/2609.99998.pdf"]
    assert response.citations[0].evidence == second.passages[0].content
    assert response.answer.endswith("[2.1]") and EVIDENCE not in response.answer


@pytest.mark.anyio
async def test_selector_none_is_validated_abstention():
    agent = service([{"in_scope": True}, {"relevant_markers": ["[1.1]"]}, {"answer": "NONE"}])
    response = await answer(agent)
    assert response.answer == INSUFFICIENT_EVIDENCE_ANSWER and response.outcome == "abstained"


@pytest.mark.anyio
async def test_selector_raw_output_size_is_bounded():
    agent = service([{"in_scope": True}, {"relevant_markers": ["[1.1]"]}, "x" * 8193])
    with pytest.raises(OllamaResponseError):
        await answer(agent)
    assert len(agent.rag.ollama.calls) == 3


@pytest.mark.anyio
async def test_prompt_size_failure_precedes_model_call():
    agent = service([])
    run = _Run(AskRequest(query=QUESTION), "llama3.2:1b", float("inf"))
    with pytest.raises(OllamaResponseError):
        await agent._model(run, "x" * 20001, system="", options={}, output_limit=4096)
    assert not agent.rag.ollama.calls and run.calls == 0


@pytest.mark.anyio
async def test_call_budget_cannot_be_overspent():
    agent = service([])
    run = _Run(AskRequest(query=QUESTION), "llama3.2:1b", float("inf"), calls=6)
    with pytest.raises(OllamaResponseError):
        await agent._model(run, "test", system="", options={}, output_limit=4096)
    assert not agent.rag.ollama.calls and run.calls == 6


@pytest.mark.anyio
async def test_total_deadline_includes_time_between_operations(monkeypatch):
    agent = service([{"in_scope": True}])
    now = [100.0]
    monkeypatch.setattr("src.services.agent.time.monotonic", lambda: now[0])
    stream = agent.events(AskRequest(query=QUESTION))
    assert (await anext(stream)).operation == "validate"
    now[0] += agent.settings.agent_deadline_seconds + 1
    with pytest.raises(TimeoutError):
        await anext(stream)
    assert not agent.rag.ollama.calls and not agent.rag.search.calls


def test_operation_budget_cannot_be_overspent():
    run = _Run(AskRequest(query=QUESTION), "llama3.2:1b", float("inf"), steps=["grade"] * 8)
    with pytest.raises(TimeoutError):
        run.status("answer")


def test_agent_monitoring_and_tracing_keep_only_fixed_metadata(writable_cache_dir):
    import logging

    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    from src.monitoring import attach_monitoring, summarize
    from src.operations import emit_event, request_context
    from src.tracing import LocalTracing

    logger = logging.getLogger("src.operations")
    previous = logger.level
    logger.setLevel(logging.INFO)
    handler = attach_monitoring(str(writable_cache_dir))
    exporter = InMemorySpanExporter()
    tracing = LocalTracing(SimpleSpanProcessor(exporter))
    token = request_context.set({"request_id": "a" * 32, "tracing": tracing})
    root = tracing.start("a" * 32)
    request_context.get()["trace_root"] = root
    try:
        emit_event("agent_stage", operation="grade", attempt=2, model_calls=4, query=QUESTION, evidence=EVIDENCE)
        emit_event("agent_completed", outcome="answered", model_calls=6, retrieval_attempts=2, stages=7, rewritten=True,
                   answer="private answer", rewritten_query="private query")
        emit_event("agent_selector_retry", attempt=1)
        emit_event("agent_error", reason="private exception", operation="private operation")
        handler.flush()
        records = [json.loads(line) for path in writable_cache_dir.glob("events-*.jsonl")
                   for line in path.read_text().splitlines()]
        assert len(records) == 4 and records[0]["operation"] == "grade"
        assert records[1]["model_calls"] == 6 and records[1]["outcome"] == "answered"
        assert records[1]["rewritten"] is True
        assert summarize(records)["retries"] == 1
        spans = [dict(s.attributes) for s in exporter.get_finished_spans()]
        assert len(spans) == 4 and spans[0]["operation"] == "grade"
        serialized = json.dumps(records + spans)
        assert not any(text in serialized for text in (QUESTION, EVIDENCE, "private"))
    finally:
        root.end()
        request_context.reset(token)
        tracing.close()
        logger.removeHandler(handler)
        handler.close()
        logger.setLevel(previous)
