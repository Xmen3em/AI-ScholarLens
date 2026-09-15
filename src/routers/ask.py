"""Standard and Server-Sent Events grounded-answer endpoints."""

import json
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from src.dependencies import RAGDep
from src.schemas.api.rag import AskRequest, AskResponse, DeltaEvent, DoneEvent, ErrorEvent
from src.services.rag.service import INSUFFICIENT_EVIDENCE_ANSWER, PreparedRAG

logger = logging.getLogger(__name__)
router = APIRouter(tags=["RAG"])


@router.post("/ask", response_model=AskResponse, summary="Answer from retrieved paper evidence")
async def ask(request: AskRequest, rag: RAGDep) -> AskResponse:
    return await rag.ask(request)


@router.post("/stream", response_class=StreamingResponse, summary="Stream an answer as typed SSE events")
async def stream(request: AskRequest, rag: RAGDep) -> StreamingResponse:
    prepared = await rag.prepare(request)
    return StreamingResponse(
        _events(prepared, rag),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _events(prepared: PreparedRAG, rag: RAGDep) -> AsyncIterator[str]:
    yield _event("sources", prepared.sources_event())
    if not prepared.context.citations:
        yield _event("done", DoneEvent(answer=INSUFFICIENT_EVIDENCE_ANSWER))
        return

    answer = ""
    try:
        async for chunk in rag.generate_stream(prepared):
            if chunk.response:
                answer += chunk.response
                yield _event("delta", DeltaEvent(delta=chunk.response))
        rag.validate_answer(prepared, answer)
        yield _event("done", DoneEvent(answer=answer))
    except Exception:
        logger.exception("RAG stream failed after response started")
        yield _event("error", ErrorEvent(error="Answer generation failed. Discard partial output."))


def _event(name: str, payload: object) -> str:
    if hasattr(payload, "model_dump"):
        payload = payload.model_dump(mode="json")
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return f"event: {name}\ndata: {data}\n\n"
