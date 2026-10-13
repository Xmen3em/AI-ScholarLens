"""Isolated app, fixed comparison jobs and strict collection integrity checks."""

import json
from collections.abc import Sequence

from fastapi import FastAPI
from src.config import Settings
from src.middlewares import OperationalMiddleware
from src.routers import agent as agent_routes
from src.routers import ask as rag_routes
from src.schemas.api.agent import AgentResponse, AgentStatus
from src.schemas.api.rag import AskRequest, AskResponse
from src.services.agent import AgentService
from src.services.rag.context import INSUFFICIENT_EVIDENCE_ANSWER, _pdf_url, validate_answer_evidence
from src.services.rag.service import RAGService


def admission(free_mib: float, *, candidate_count: int, required_installed: bool) -> str | None:
    if candidate_count != 1:
        return "candidate_policy_changed"
    if not required_installed:
        return "required_model_missing"
    return "insufficient_memory" if free_mib < 3072 else None


def build_jobs(cases: Sequence[dict], *, modes=("bm25", "hybrid"), transports=("json", "sse")) -> list[dict]:
    jobs = []
    for index, case in enumerate(cases):
        paths = ("baseline", "agent") if index % 2 == 0 else ("agent", "baseline")
        ordered_transports = transports if index % 2 == 0 else tuple(reversed(transports))
        for mode in modes:
            for transport in ordered_transports:
                for path in paths:
                    jobs.append({"key": f"{case['id']}:{mode}:{path}:{transport}", "case_id": case["id"],
                                 "query": case["query"], "mode": mode, "path": path, "transport": transport})
    return jobs


def create_evaluation_app(settings: Settings, search, ollama) -> FastAPI:
    # Import handlers without running the production lifespan (no DB migrations,
    # cache connection, model install, tracing backend or existing runtime changes).
    from src.main import app as production

    local = FastAPI()
    local.exception_handlers = production.exception_handlers.copy()
    local.state.settings = settings
    local.state.rag = RAGService(search, ollama, settings)
    local.state.rag.cache = None
    local.state.agent = AgentService(local.state.rag, settings)
    local.include_router(rag_routes.router, prefix="/api/v1")
    local.include_router(agent_routes.router, prefix="/api/v1")
    local.add_middleware(OperationalMiddleware, settings=settings)
    return local


def parse_agent_sse(raw: str, *, agent: bool) -> dict:
    frames = []
    for block in raw.replace("\r\n", "\n").split("\n\n"):
        if not block.strip():
            continue
        fields = block.splitlines()
        names = [line[6:].strip() for line in fields if line.startswith("event:")]
        data = [line[5:].strip() for line in fields if line.startswith("data:")]
        if len(names) != 1 or not data:
            raise ValueError("invalid SSE frame")
        frames.append((names[0], json.loads("\n".join(data))))
    names = [name for name, _ in frames]
    if "error" in names or names.count("sources") != 1 or names.count("done") != 1 or names[-1] != "done":
        raise ValueError("SSE failed or missing terminal output")
    source_index = names.index("sources")
    if any(name != "status" for name in names[:source_index]) or any(name != "delta" for name in names[source_index + 1:-1]):
        raise ValueError("SSE ordering failed")
    if not agent and source_index:
        raise ValueError("baseline SSE contains unexpected status")
    statuses = []
    for _, payload in frames[:source_index]:
        if set(payload) != {"operation", "attempt"}:
            raise ValueError("SSE status contains nonpublic state")
        statuses.append(AgentStatus.model_validate(payload).operation)
    source, done = frames[source_index][1], frames[-1][1]
    for key in source:
        if key in done and source[key] != done[key]:
            raise ValueError("terminal SSE source metadata differs")
    result = {**source, **done}
    joined = "".join(payload["delta"] for _, payload in frames[source_index + 1:-1])
    if joined != result["answer"] and not (not joined and result["answer"] == INSUFFICIENT_EVIDENCE_ANSWER):
        raise ValueError("SSE deltas differ from final answer")
    if agent and (not statuses or statuses != result.get("steps")):
        raise ValueError("SSE statuses differ from terminal stages")
    return result


def audit_response(response: dict, request: AskRequest, papers: list, chunks: list, *,
                   agent: bool, measured: dict, expected_model: str = "llama3.2:1b") -> dict:
    parsed = AgentResponse.model_validate(response) if agent else AskResponse.model_validate(response)
    if parsed.query != request.query or parsed.model != (request.model or expected_model):
        raise ValueError("answer request/model identity differs")
    if parsed.chunks_used != len(parsed.citations) or parsed.sources != list(dict.fromkeys(_pdf_url(c.arxiv_id) for c in parsed.citations)):
        raise ValueError("citation ownership/count differs")
    if len({c.marker for c in parsed.citations}) != len(parsed.citations):
        raise ValueError("duplicate source markers")
    indexed = {(c["arxiv_id"], c["section_index"], c["chunk_index"]): c for c in chunks}
    stored = {p["arxiv_id"]: p for p in papers}
    for citation in parsed.citations:
        chunk = indexed.get((citation.arxiv_id, citation.section_index, citation.chunk_index))
        sections = stored.get(citation.arxiv_id, {}).get("sections") or []
        if (not chunk or chunk["content"] != citation.evidence or chunk["section_title"] != citation.section_title
                or chunk.get("title", citation.title) != citation.title or not 0 <= citation.section_index < len(sections)
                or " ".join(citation.evidence.split()) not in " ".join(sections[citation.section_index]["content"].split())):
            raise ValueError("citation differs from preserved source")
    validate_answer_evidence(parsed.answer, parsed.citations)
    if not request.use_hybrid and parsed.search_mode != "bm25":
        raise ValueError("BM25 request reported hybrid")
    if agent:
        parsed_agent = AgentResponse.model_validate(response)
        if (parsed_agent.model_calls != measured["generation_calls"]
                or parsed_agent.retrieval_attempts != measured["retrieval_calls"]
                or measured["embedding_calls"] > 2 or (not request.use_hybrid and measured["embedding_calls"])):
            raise ValueError("agent measured/reported work differs")
        if len(parsed_agent.steps) > 8 or parsed_agent.steps.count("rewrite") > 1:
            raise ValueError("agent operation budget exceeded")
        if (parsed_agent.outcome == "answered") != (parsed.answer != INSUFFICIENT_EVIDENCE_ANSWER):
            raise ValueError("agent answer/outcome differs")
    elif measured["generation_calls"] > 2 or measured["retrieval_calls"] != 1 or measured["embedding_calls"] > 1:
        raise ValueError("baseline work exceeded unchanged policy")
    return {"attribution_passed": True, "words": len(parsed.answer.split()),
            "abstained": parsed.answer == INSUFFICIENT_EVIDENCE_ANSWER,
            "actual_mode": parsed.search_mode, "response": parsed.model_dump(mode="json")}
