import json

import pytest
from src.dependencies import get_ollama, get_rag
from src.exceptions import GroundingError, OllamaConnectionError, OllamaTimeoutError, UnsupportedModelError
from src.main import app
from src.schemas.api.rag import AskRequest, AskResponse
from src.schemas.api.search import PaperPassages, PassageHit
from src.schemas.ollama import OllamaGenerateResponse, OllamaReadiness
from src.services.rag.context import build_context
from src.services.rag.service import PreparedRAG


def _paper():
    return PaperPassages(
        arxiv_id="2601.00001v2",
        title="Grounded Generation",
        categories=["cs.CL"],
        score=0.03,
        passages=[
            PassageHit(
                section_title="Methods",
                section_index=3,
                chunk_index=1,
                content="The method binds claims to retrieved evidence.",
                score=0.03,
            )
        ],
    )


def _prepared(request):
    return PreparedRAG(
        request=request,
        context=build_context([_paper()]),
        search_mode="hybrid",
        model=request.model or "llama3.2:1b",
    )


class StubRAG:
    def __init__(self, *, raises=None, invalid_stream=False, empty=False):
        self.raises = raises
        self.invalid_stream = invalid_stream
        self.empty = empty
        self.requests = []

    async def ask(self, request):
        self.requests.append(request)
        if self.raises:
            raise self.raises
        prepared = _prepared(request)
        return AskResponse(
            query=request.query,
            answer="Grounded answer [1.1].",
            sources=prepared.context.sources,
            citations=prepared.context.citations,
            chunks_used=1,
            search_mode="hybrid",
            model=prepared.model,
        )

    async def prepare(self, request):
        self.requests.append(request)
        if self.raises:
            raise self.raises
        prepared = _prepared(request)
        if self.empty:
            return PreparedRAG(
                request=request,
                context=build_context([]),
                search_mode="bm25",
                model="llama3.2:1b",
            )
        return prepared

    async def generate_stream(self, prepared):
        answer = "Ungrounded" if self.invalid_stream else "Grounded answer [1.1]."
        yield OllamaGenerateResponse(model=prepared.model, response="Grounded ", done=False)
        yield OllamaGenerateResponse(model=prepared.model, response=answer.removeprefix("Grounded "), done=True)

    def validate_answer(self, prepared, answer):
        if self.invalid_stream:
            raise GroundingError("details must not leak")


@pytest.fixture
def rag_service():
    stub = StubRAG()
    app.dependency_overrides[get_rag] = lambda: stub
    yield stub
    app.dependency_overrides.pop(get_rag, None)


@pytest.mark.anyio
async def test_ask_contract_forwards_controls_and_returns_traceable_citations(client, rag_service):
    response = await client.post(
        "/api/v1/ask",
        json={
            "query": "grounded rag",
            "top_k": 5,
            "use_hybrid": False,
            "model": "llama3.2:1b",
            "categories": ["cs.CL"],
        },
    )

    assert response.status_code == 200
    assert rag_service.requests == [
        AskRequest(query="grounded rag", top_k=5, use_hybrid=False, model="llama3.2:1b", categories=["cs.CL"])
    ]
    body = response.json()
    assert body["answer"] == "Grounded answer [1.1]."
    assert body["sources"] == ["https://arxiv.org/pdf/2601.00001.pdf"]
    assert body["citations"][0]["marker"] == "[1.1]"
    assert (body["citations"][0]["section_index"], body["citations"][0]["chunk_index"]) == (3, 1)


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("error", "status", "detail"),
    [
        (UnsupportedModelError("secret internal model"), 422, "Requested model is not allowed"),
        (GroundingError("raw model output"), 502, "Generated answer failed grounding validation"),
        (OllamaConnectionError("localhost refused"), 503, "Answer generation is unavailable"),
        (OllamaTimeoutError("waited 300 seconds"), 504, "Answer generation timed out"),
    ],
)
async def test_ask_maps_failures_without_leaking_internal_errors(client, error, status, detail):
    app.dependency_overrides[get_rag] = lambda: StubRAG(raises=error)
    try:
        response = await client.post("/api/v1/ask", json={"query": "grounded rag"})
    finally:
        app.dependency_overrides.pop(get_rag, None)

    assert response.status_code == status
    assert response.json() == {"detail": detail}
    assert str(error) not in response.text


def _sse_events(body):
    events = []
    for frame in body.strip().split("\n\n"):
        lines = frame.splitlines()
        events.append((lines[0].removeprefix("event: "), json.loads(lines[1].removeprefix("data: "))))
    return events


@pytest.mark.anyio
async def test_stream_orders_sources_deltas_and_done(client, rag_service):
    response = await client.post("/api/v1/stream", json={"query": "grounded rag"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = _sse_events(response.text)
    assert [name for name, _ in events] == ["sources", "delta", "delta", "done"]
    assert events[0][1]["citations"][0]["marker"] == "[1.1]"
    assert events[-1][1] == {"answer": "Grounded answer [1.1]."}


@pytest.mark.anyio
async def test_stream_emits_generic_error_instead_of_done_when_grounding_fails(client):
    app.dependency_overrides[get_rag] = lambda: StubRAG(invalid_stream=True)
    try:
        response = await client.post("/api/v1/stream", json={"query": "grounded rag"})
    finally:
        app.dependency_overrides.pop(get_rag, None)

    events = _sse_events(response.text)
    assert [name for name, _ in events][-1] == "error"
    assert all(name != "done" for name, _ in events)
    assert events[-1][1] == {"error": "Answer generation failed. Discard partial output."}
    assert "details must not leak" not in response.text


@pytest.mark.anyio
async def test_stream_empty_retrieval_skips_generation_and_finishes_deterministically(client):
    app.dependency_overrides[get_rag] = lambda: StubRAG(empty=True)
    try:
        response = await client.post("/api/v1/stream", json={"query": "unknown"})
    finally:
        app.dependency_overrides.pop(get_rag, None)

    events = _sse_events(response.text)
    assert [name for name, _ in events] == ["sources", "done"]
    assert events[0][1]["citations"] == []
    assert "insufficient" in events[-1][1]["answer"].lower()


class StubOllamaHealth:
    def __init__(self, readiness=None, raises=None):
        self.result = readiness
        self.raises = raises

    async def readiness(self):
        if self.raises:
            raise self.raises
        return self.result


class HealthyDatabase:
    class Session:
        def execute(self, statement):
            return 1

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

    def get_session(self):
        return self.Session()


@pytest.mark.anyio
async def test_health_is_503_when_default_generation_model_is_missing(client):
    result = OllamaReadiness(
        status="unhealthy", installed=["nomic-embed-text:latest"], missing_required=["llama3.2:1b"], missing_optional=[]
    )
    app.dependency_overrides[get_ollama] = lambda: StubOllamaHealth(readiness=result)
    from src.dependencies import get_database

    app.dependency_overrides[get_database] = lambda: HealthyDatabase()
    try:
        response = await client.get("/api/v1/health")
    finally:
        app.dependency_overrides.pop(get_ollama, None)
        app.dependency_overrides.pop(get_database, None)

    assert response.status_code == 503
    assert response.json()["status"] == "unhealthy"
    assert "llama3.2:1b" in response.json()["services"]["ollama"]["message"]


@pytest.mark.anyio
async def test_health_is_200_and_degraded_when_only_optional_model_is_missing(client):
    result = OllamaReadiness(
        status="degraded", installed=["llama3.2:1b"], missing_required=[], missing_optional=["nomic-embed-text:latest"]
    )
    app.dependency_overrides[get_ollama] = lambda: StubOllamaHealth(readiness=result)
    from src.dependencies import get_database

    app.dependency_overrides[get_database] = lambda: HealthyDatabase()
    try:
        response = await client.get("/api/v1/health")
    finally:
        app.dependency_overrides.pop(get_ollama, None)
        app.dependency_overrides.pop(get_database, None)

    assert response.status_code == 200
    assert response.json()["status"] == "degraded"
