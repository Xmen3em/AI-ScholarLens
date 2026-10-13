import json
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from src.commands.agent_collection import admission, audit_response, build_jobs, create_evaluation_app, parse_agent_sse
from src.config import Settings
from src.schemas.api.rag import AskRequest
from src.services.rag.service import INSUFFICIENT_EVIDENCE_ANSWER

from tests.unit.test_agent_service import EVIDENCE, QUESTION, search_result, service


def frame(name, data):
    return f"event: {name}\ndata: {json.dumps(data)}\n\n"


def substantive():
    return {"query": QUESTION, "answer": f'"{EVIDENCE}" [1.1]', "sources": ["https://arxiv.org/pdf/2609.99999.pdf"],
            "citations": [{"marker": "[1.1]", "arxiv_id": "2609.99999", "title": "Neural Retrieval", "section_title": "Method",
                           "section_index": 2, "chunk_index": 3, "evidence": EVIDENCE}], "chunks_used": 1,
            "search_mode": "bm25", "model": "llama3.2:1b", "policy_version": "bounded-agent-v1", "outcome": "answered",
            "retrieval_attempts": 1, "model_calls": 3, "rewritten": False, "steps": ["validate", "retrieve", "grade", "answer"]}


def test_holdout_jobs_are_complete_counterbalanced_and_never_repeat():
    cases = [{"id": f"case-{i}", "query": "test"} for i in range(24)]
    jobs = build_jobs(cases)
    assert len(jobs) == 192 and len({j["key"] for j in jobs}) == 192
    assert jobs[0]["path"] == "baseline" and jobs[8]["path"] == "agent"
    assert jobs[0]["transport"] == "json" and jobs[8]["transport"] == "sse"
    assert {j["mode"] for j in jobs} == {"bm25", "hybrid"}


def test_admission_never_lowers_frozen_memory_or_policy_bar():
    assert admission(3072, candidate_count=1, required_installed=True) is None
    assert admission(3071, candidate_count=1, required_installed=True) == "insufficient_memory"
    assert admission(4096, candidate_count=2, required_installed=True) == "candidate_policy_changed"
    assert admission(4096, candidate_count=1, required_installed=False) == "required_model_missing"


def test_status_aware_parser_validates_delivery_and_terminal_metadata():
    response = substantive()
    raw = "".join(frame("status", {"operation": op, "attempt": 1}) for op in response["steps"])
    raw += frame("sources", {k: v for k, v in response.items() if k in {"query", "sources", "citations", "chunks_used", "search_mode", "model"}})
    raw += frame("delta", {"delta": response["answer"]}) + frame("done", response)
    assert parse_agent_sse(raw, agent=True) == response


@pytest.mark.parametrize("bad", ["late_status", "delta_before_source", "mismatched_delta", "two_done", "error_done", "private_status", "source_mismatch"])
def test_invalid_or_failed_sse_never_becomes_success(bad):
    response = substantive()
    source = {k: v for k, v in response.items() if k in {"query", "sources", "citations", "chunks_used", "search_mode", "model"}}
    frames = [("status", {"operation": "validate", "attempt": 0}), ("sources", source),
              ("delta", {"delta": response["answer"]}), ("done", response)]
    if bad == "late_status":
        frames.insert(3, ("status", {"operation": "answer", "attempt": 1}))
    elif bad == "delta_before_source":
        frames[1], frames[2] = frames[2], frames[1]
    elif bad == "mismatched_delta":
        frames[2] = ("delta", {"delta": "unvalidated"})
    elif bad == "two_done":
        frames.append(("done", response))
    elif bad == "error_done":
        frames.insert(3, ("error", {"error": "failed"}))
    elif bad == "private_status":
        frames[0][1]["query"] = "private question"
    else:
        source["model"] = "wrong model"
    with pytest.raises(ValueError):
        parse_agent_sse("".join(frame(*item) for item in frames), agent=True)


def test_baseline_sse_abstention_without_deltas_remains_supported():
    response = {k: v for k, v in substantive().items() if k not in {"policy_version", "outcome", "retrieval_attempts", "model_calls", "rewritten", "steps"}}
    response.update(answer=INSUFFICIENT_EVIDENCE_ANSWER, citations=[], sources=[], chunks_used=0)
    source = {k: v for k, v in response.items() if k != "answer"}
    assert parse_agent_sse(frame("sources", source) + frame("done", {"answer": response["answer"]}), agent=False) == response


def test_audit_binds_original_request_source_coordinates_and_measured_calls():
    paper = {"arxiv_id": "2609.99999", "sections": [{"content": ""}, {"content": ""}, {"content": EVIDENCE}]}
    chunk = {"arxiv_id": "2609.99999", "section_index": 2, "chunk_index": 3, "section_title": "Method", "content": EVIDENCE}
    measured = {"generation_calls": 3, "retrieval_calls": 1, "embedding_calls": 0}
    assert audit_response(substantive(), AskRequest(query=QUESTION, use_hybrid=False), [paper], [chunk],
                          agent=True, measured=measured)["attribution_passed"]
    for altered in ({"query": "rewritten question"}, {"model_calls": 6}, {"sources": []}, {"answer": '"Invented fact" [1.1]'}):
        with pytest.raises(ValueError):
            audit_response({**substantive(), **altered}, AskRequest(query=QUESTION, use_hybrid=False), [paper], [chunk],
                           agent=True, measured=measured)


@pytest.mark.anyio
async def test_evaluation_app_is_uncached_has_no_database_lifespan_and_uses_same_quotas(writable_cache_dir):
    fake = service([{"in_scope": True}, {"relevant_markers": ["[1.1]"]}, {"answer": "E1"}])
    settings = Settings(_env_file=None, api_key="a" * 32, agent_enabled=True, api_generations_per_minute=1,
                        api_rate_limit_path=str(writable_cache_dir / "limits"))
    local = create_evaluation_app(settings, fake.rag.search, fake.rag.ollama)
    assert isinstance(local, FastAPI) and local.state.rag.cache is None
    assert not hasattr(local.state, "database")
    async with AsyncClient(transport=ASGITransport(app=local), base_url="http://test") as client:
        payload = {"query": QUESTION, "use_hybrid": False}
        assert (await client.post("/api/v1/agent/ask", json=payload)).status_code == 401
        assert not fake.rag.ollama.calls
        response = await client.post("/api/v1/agent/ask", json=payload, headers={"X-API-Key": "a" * 32})
        assert response.status_code == 200 and response.json()["model_calls"] == 3
        assert (await client.post("/api/v1/ask", json=payload, headers={"X-API-Key": "a" * 32})).status_code == 429
