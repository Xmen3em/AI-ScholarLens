"""Standard and Server-Sent Events grounded-answer endpoints."""

import json
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from src.answer_cache import CacheTicket
from src.dependencies import RAGDep
from src.operations import emit_event, request_context
from src.schemas.api.rag import AskRequest, AskResponse, DeltaEvent, DoneEvent, ErrorEvent
from src.services.rag.context import validate_answer_length
from src.services.rag.service import INSUFFICIENT_EVIDENCE_ANSWER, PreparedRAG

logger = logging.getLogger(__name__)
router = APIRouter(tags=["RAG"])


@router.post("/ask", response_model=AskResponse, summary="Answer from retrieved paper evidence")
async def ask(request: AskRequest, rag: RAGDep) -> AskResponse:
    return await rag.ask(request)


@router.post("/stream", response_class=StreamingResponse, summary="Stream an answer as typed SSE events")
async def stream(request: AskRequest, rag: RAGDep) -> StreamingResponse:
    cache = getattr(rag, "cache", None)
    ticket = await cache.lookup(request) if cache else None
    if ticket and ticket.response:
        return StreamingResponse(_cached_events(ticket.response), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
    prepared = await rag.prepare(request)
    return StreamingResponse(
        _events(prepared, rag, ticket),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _events(prepared: PreparedRAG, rag: RAGDep, ticket: CacheTicket | None = None) -> AsyncIterator[str]:
    answer = ""
    try:
        yield _event("sources", prepared.sources_event())
        if not prepared.context.citations:
            yield _event("done", DoneEvent(answer=INSUFFICIENT_EVIDENCE_ANSWER))
            _pending_cache(rag, ticket, prepared, INSUFFICIENT_EVIDENCE_ANSWER)
            emit_event("rag_stream_completed")
            return
        async for chunk in rag.generate_stream(prepared):
            if chunk.response:
                answer += chunk.response
                validate_answer_length(answer)
                yield _event("delta", DeltaEvent(delta=chunk.response))
        rag.validate_answer(prepared, answer)
        yield _event("done", DoneEvent(answer=answer))
        _pending_cache(rag, ticket, prepared, answer)
        emit_event("rag_stream_completed")
    except BaseException as exc:
        if isinstance(exc, Exception):
            context = request_context.get()
            if context is not None:
                context["stream_failed"] = True
            emit_event("rag_stream_error", level=logging.ERROR, reason=type(exc).__name__)
            yield _event("error", ErrorEvent(error="Answer generation failed. Discard partial output."))
        else:
            context = request_context.get()
            if context is not None:
                context["stream_interrupted"] = True
            emit_event("rag_stream_interrupted")
            raise


def _pending_cache(rag, ticket, prepared, answer):
    context = request_context.get()
    if ticket and context is not None and getattr(rag, "cache", None):
        # Middleware stores only after the complete ASGI response was sent.
        context["cache_commit"] = (rag.cache, ticket, rag._response(prepared, answer))


async def _cached_events(response: AskResponse) -> AsyncIterator[str]:
    from src.schemas.api.rag import SourcesEvent
    try:
        yield _event("sources", SourcesEvent(**response.model_dump(exclude={"answer"})))
        for line in response.answer.splitlines(keepends=True):
            yield _event("delta", DeltaEvent(delta=line))
        yield _event("done", DoneEvent(answer=response.answer))
        emit_event("rag_stream_completed")
    except BaseException:
        context = request_context.get()
        if context is not None:
            context["stream_interrupted"] = True
        emit_event("rag_stream_interrupted")
        raise


def _event(name: str, payload: object) -> str:
    if hasattr(payload, "model_dump"):
        payload = payload.model_dump(mode="json")
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return f"event: {name}\ndata: {data}\n\n"
