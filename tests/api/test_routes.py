import pytest
from opensearchpy.exceptions import ConnectionError as OpenSearchConnectionError
from src.dependencies import get_db_session, get_search
from src.main import app
from src.schemas.api.search import ChunkHit, ChunkSearchResponse, SearchHit, SearchResponse


class EmptyDatabaseSession:
    def scalars(self, statement):
        return []

    def scalar(self, statement):
        return 0


@pytest.fixture
def empty_database_session():
    def override_database_session():
        yield EmptyDatabaseSession()

    app.dependency_overrides[get_db_session] = override_database_session
    yield
    app.dependency_overrides.pop(get_db_session, None)


@pytest.mark.anyio
async def test_ping_endpoint(client):
    response = await client.get("/api/v1/ping")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "message": "pong"}


@pytest.mark.anyio
async def test_list_papers_returns_empty_page(client, empty_database_session):
    response = await client.get("/api/v1/papers/")

    assert response.status_code == 200
    assert response.json() == {"papers": [], "total": 0}


@pytest.mark.anyio
async def test_get_unknown_paper_returns_not_found(client, empty_database_session):
    response = await client.get("/api/v1/papers/2401.00001")

    assert response.status_code == 404
    assert response.json() == {"detail": "Paper not found"}


@pytest.mark.anyio
async def test_malformed_arxiv_id_is_rejected_before_lookup(client, empty_database_session):
    response = await client.get("/api/v1/papers/not-an-arxiv-id")

    assert response.status_code == 422


class StubSearch:
    """Records the arguments the router forwards, and returns a fixed response."""

    def __init__(self, raises=None):
        self.calls = []
        self.raises = raises

    def search_papers(self, query, *, size, offset, categories, newest_first):
        self.calls.append({"query": query, "size": size, "offset": offset, "categories": categories, "newest_first": newest_first})
        if self.raises:
            raise self.raises
        return SearchResponse(
            query=query,
            total=1,
            took_ms=5,
            hits=[
                SearchHit(
                    arxiv_id="2608.26469v1",
                    title="Retrieval Augmented Generation",
                    authors="Ada Lovelace",
                    abstract="We study retrieval.",
                    categories=["cs.CL"],
                    published_date="2026-08-26T00:00:00",
                    pdf_url="https://arxiv.org/pdf/2608.26469v1",
                    score=9.5,
                    highlights={"title": ["<mark>Retrieval</mark> Augmented Generation"]},
                )
            ],
        )


    def search_chunks(self, query, *, size, offset, categories):
        self.calls.append({"query": query, "size": size, "offset": offset, "categories": categories})
        if self.raises:
            raise self.raises
        return ChunkSearchResponse(
            query=query,
            total=1,
            took_ms=3,
            hits=[
                ChunkHit(
                    arxiv_id="2608.26469v1",
                    title="Active Curriculum Refinement",
                    section_title="2.1 Reinforcement Learning",
                    section_index=4,
                    chunk_index=0,
                    content="In many reinforcement learning domains...",
                    categories=["cs.LG"],
                    published_date="2026-08-26T00:00:00",
                    score=11.2,
                    highlights={"content": ["In many <mark>reinforcement</mark> learning domains"]},
                )
            ],
        )


@pytest.fixture
def search_service():
    stub = StubSearch()
    app.dependency_overrides[get_search] = lambda: stub
    yield stub
    app.dependency_overrides.pop(get_search, None)


@pytest.mark.anyio
async def test_search_returns_scored_hits(client, search_service):
    response = await client.post("/api/v1/search/", json={"query": "retrieval augmented generation"})

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["hits"][0]["arxiv_id"] == "2608.26469v1"
    assert body["hits"][0]["score"] == 9.5
    assert "<mark>" in body["hits"][0]["highlights"]["title"][0]


@pytest.mark.anyio
async def test_search_forwards_every_option(client, search_service):
    await client.post(
        "/api/v1/search/",
        json={"query": "rag", "size": 25, "offset": 50, "categories": ["cs.CL"], "newest_first": True},
    )

    assert search_service.calls == [
        {"query": "rag", "size": 25, "offset": 50, "categories": ["cs.CL"], "newest_first": True}
    ]


@pytest.mark.anyio
async def test_search_defaults_are_applied_when_only_a_query_is_sent(client, search_service):
    await client.post("/api/v1/search/", json={"query": "rag"})

    assert search_service.calls == [{"query": "rag", "size": 10, "offset": 0, "categories": None, "newest_first": False}]


@pytest.mark.anyio
async def test_an_empty_body_browses_rather_than_failing(client, search_service):
    response = await client.post("/api/v1/search/", json={})

    assert response.status_code == 200
    assert search_service.calls[0]["query"] == ""


@pytest.mark.anyio
@pytest.mark.parametrize(
    "payload",
    [
        {"query": "rag", "size": 0},
        {"query": "rag", "size": 51},
        {"query": "rag", "offset": -1},
        {"query": "rag", "offset": 1001},
        {"query": "x" * 501},
        {"query": "rag", "categories": ["hep-th"]},  # outside the ingested AI scope
        {"query": "rag", "newest_first": "maybe"},
    ],
)
async def test_invalid_search_input_is_rejected_before_the_backend(client, search_service, payload):
    response = await client.post("/api/v1/search/", json=payload)

    assert response.status_code == 422
    assert search_service.calls == []


@pytest.mark.anyio
async def test_an_unreachable_search_backend_is_a_503(client):
    stub = StubSearch(raises=OpenSearchConnectionError("N/A", "refused", Exception()))
    app.dependency_overrides[get_search] = lambda: stub
    try:
        response = await client.post("/api/v1/search/", json={"query": "rag"})
    finally:
        app.dependency_overrides.pop(get_search, None)

    assert response.status_code == 503
    assert response.json()["detail"] == "Search is unavailable"


@pytest.mark.anyio
async def test_chunk_search_returns_positioned_passages(client, search_service):
    response = await client.post("/api/v1/search/chunks", json={"query": "reinforcement learning"})

    assert response.status_code == 200
    hit = response.json()["hits"][0]
    assert (hit["arxiv_id"], hit["section_index"], hit["chunk_index"]) == ("2608.26469v1", 4, 0)
    assert hit["section_title"] == "2.1 Reinforcement Learning"
    assert "<mark>" in hit["highlights"]["content"][0]


@pytest.mark.anyio
async def test_chunk_search_forwards_paging_and_filters(client, search_service):
    await client.post("/api/v1/search/chunks", json={"query": "rag", "size": 5, "offset": 10, "categories": ["cs.CL"]})

    assert search_service.calls == [{"query": "rag", "size": 5, "offset": 10, "categories": ["cs.CL"]}]


@pytest.mark.anyio
@pytest.mark.parametrize("payload", [{}, {"query": ""}, {"query": "rag", "size": 51}, {"query": "rag", "categories": ["hep-th"]}])
async def test_chunk_search_rejects_invalid_input(client, search_service, payload):
    """A passage search with no query has nothing to answer, unlike a paper browse."""
    response = await client.post("/api/v1/search/chunks", json=payload)

    assert response.status_code == 422
    assert search_service.calls == []


@pytest.mark.anyio
async def test_an_unreachable_backend_is_a_503_for_chunk_search_too(client):
    stub = StubSearch(raises=OpenSearchConnectionError("N/A", "refused", Exception()))
    app.dependency_overrides[get_search] = lambda: stub
    try:
        response = await client.post("/api/v1/search/chunks", json={"query": "rag"})
    finally:
        app.dependency_overrides.pop(get_search, None)

    assert response.status_code == 503
