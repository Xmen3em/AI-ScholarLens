import pytest
from src.dependencies import get_db_session
from src.main import app


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
