import asyncio
from contextlib import aclosing

import pytest
from src.schemas.api.agent import AgentResponse, AgentStatus
from src.schemas.api.rag import AskRequest

from tests.unit.test_agent_service import QUESTION, answer, service


def test_agent_uses_real_graph_with_conditional_retrieval_and_no_checkpoint():
    from langgraph.graph.state import CompiledStateGraph

    agent = service([])
    assert isinstance(agent._graph, CompiledStateGraph)
    graph = agent._graph.get_graph()
    assert set(graph.nodes) == {'__start__', '__end__', 'validate', 'retrieve', 'grade', 'rewrite', 'answer', 'abstain'}
    assert any(edge.source == 'grade' and edge.target == 'rewrite' and edge.conditional for edge in graph.edges)
    assert agent._graph.checkpointer is None


@pytest.mark.anyio
async def test_status_consumption_pauses_graph_before_any_model_or_search_work():
    agent = service([{'in_scope': False}])
    async with aclosing(agent.events(AskRequest(query=QUESTION))) as stream:
        event = await anext(stream)
        assert isinstance(event, AgentStatus) and event.operation == 'validate'
        for _ in range(5):
            await asyncio.sleep(0)
        assert agent.rag.ollama.calls == [] and agent.rag.search.calls == []
    assert agent.rag.ollama.calls == []


@pytest.mark.anyio
async def test_ambient_langsmith_tracing_is_disabled_and_graph_only_emits_public_models(monkeypatch):
    from langsmith import get_tracing_context

    monkeypatch.setenv('LANGSMITH_TRACING', 'true')
    monkeypatch.setenv('LANGCHAIN_TRACING_V2', 'true')
    agent = service([{'in_scope': True}, {'relevant_markers': ['[1.1]']}, {'answer': 'E1'}])
    generate = agent.rag.ollama.generate
    async def checked(*args, **kwargs):
        assert get_tracing_context()['enabled'] is False
        return await generate(*args, **kwargs)
    monkeypatch.setattr(agent.rag.ollama, 'generate', checked)
    events = [event async for event in agent.events(AskRequest(query=QUESTION))]
    assert all(isinstance(event, (AgentStatus, AgentResponse)) for event in events)
    assert isinstance(events[-1], AgentResponse) and events[-1].model_calls == 3


@pytest.mark.anyio
async def test_each_graph_invocation_has_independent_counters():
    agent = service([{'in_scope': False}, {'in_scope': False}])
    first, second = await answer(agent), await answer(agent)
    assert first.model_calls == second.model_calls == 1
    assert first.steps == second.steps == ['validate', 'abstain']


@pytest.mark.anyio
async def test_public_event_yield_does_not_change_callers_tracing_context():
    from langsmith import get_tracing_context, tracing_context

    agent=service([{'in_scope':False}])
    with tracing_context(enabled=True):
        async with aclosing(agent.events(AskRequest(query=QUESTION))) as stream:
            assert isinstance(await anext(stream),AgentStatus)
            assert get_tracing_context()['enabled'] is True
        assert get_tracing_context()['enabled'] is True
