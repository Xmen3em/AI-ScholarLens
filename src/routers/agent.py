"""Opt-in bounded agent endpoints; no cache or internal state streaming."""

import logging
from collections.abc import AsyncIterator
from contextlib import aclosing
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from src.operations import emit_event, request_context
from src.routers.ask import _event
from src.schemas.api.agent import AgentResponse
from src.schemas.api.rag import AskRequest, DeltaEvent, ErrorEvent, SourcesEvent
from src.services.agent import AgentBusyError, AgentService

router = APIRouter(prefix="/agent", tags=["Agent"])


def get_agent(request: Request) -> AgentService:
    if not request.app.state.settings.agent_enabled:
        raise HTTPException(status_code=503, detail="Agent workflow is disabled")
    return request.app.state.agent


AgentDep = Annotated[AgentService, Depends(get_agent)]


@router.post("/ask", response_model=AgentResponse)
async def ask(request: AskRequest, agent: AgentDep) -> AgentResponse:
    try:
        return await agent.ask(request)
    except TimeoutError:
        emit_event("agent_error", reason="TimeoutError")
        raise HTTPException(status_code=504, detail="Agent workflow timed out") from None
    except AgentBusyError:
        emit_event("agent_error", reason="AgentBusyError")
        raise HTTPException(status_code=503, detail="Agent retrieval is busy") from None
    except Exception as exc:
        emit_event("agent_error", reason=type(exc).__name__)
        raise


@router.post("/stream", response_class=StreamingResponse)
async def stream(request: AskRequest, agent: AgentDep) -> StreamingResponse:
    # Validate the configured model before sending HTTP 200/starting SSE.
    agent.rag._model_for(request)
    return StreamingResponse(_events(request, agent), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


async def _events(request: AskRequest, agent: AgentService) -> AsyncIterator[str]:
    try:
        async with aclosing(agent.events(request)) as events:
            async for event in events:
                if not isinstance(event, AgentResponse):
                    yield _event("status", event)
                    continue
                # The service has validated the entire selection before exposing
                # any citation, answer delta or terminal response.
                yield _event("sources", SourcesEvent(**event.model_dump(exclude={"answer"})))
                for line in event.answer.splitlines(keepends=True):
                    yield _event("delta", DeltaEvent(delta=line))
                yield _event("done", event)
        emit_event("agent_stream_completed")
    except BaseException as exc:
        context = request_context.get()
        if isinstance(exc, Exception):
            if context is not None:
                context["stream_failed"] = True
            emit_event("agent_stream_error", level=logging.ERROR, reason=type(exc).__name__)
            yield _event("error", ErrorEvent(error="Agent workflow failed. Discard partial output."))
        else:
            if context is not None:
                context["stream_interrupted"] = True
            emit_event("agent_stream_interrupted")
            raise
