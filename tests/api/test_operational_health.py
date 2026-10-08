from types import SimpleNamespace

import pytest
from src.dependencies import get_database, get_ollama, get_search
from src.main import app
from src.schemas.ollama import OllamaReadiness
from tests.api.test_rag_routes import HealthyDatabase, StubOllamaHealth


class SearchHealth:
    def __init__(self, status="yellow", aliases=True, raises=False):
        self.status, self.aliases, self.raises = status, aliases, raises
        self.client = self
        self.cluster = self
        self.indices = self

    def health(self, **kwargs):
        if self.raises:
            raise RuntimeError("private connection details")
        return {"status": self.status}

    def exists_alias(self, **kwargs):
        return self.aliases


@pytest.fixture
def healthy_dependencies():
    app.dependency_overrides[get_database] = lambda: HealthyDatabase()
    result = OllamaReadiness(status="healthy", installed=[], missing_required=[], missing_optional=[])
    app.dependency_overrides[get_ollama] = lambda: StubOllamaHealth(readiness=result)
    yield
    for dependency in (get_database, get_ollama, get_search):
        app.dependency_overrides.pop(dependency, None)


@pytest.mark.anyio
@pytest.mark.parametrize("search,expected", [
    (SearchHealth(), 200), (SearchHealth(status="red"), 503),
    (SearchHealth(aliases=False), 503), (SearchHealth(raises=True), 503),
])
async def test_search_readiness_requires_usable_cluster_and_both_aliases(client, healthy_dependencies, search, expected):
    app.dependency_overrides[get_search] = lambda: search
    response = await client.get("/api/v1/health")
    assert response.status_code == expected
    assert response.json()["services"]["opensearch"]["status"] == ("healthy" if expected == 200 else "unhealthy")
    assert "private" not in response.text


@pytest.mark.anyio
async def test_health_handles_broken_database(client, healthy_dependencies):
    def broken():
        raise RuntimeError("private database details")
    app.dependency_overrides[get_database] = lambda: SimpleNamespace(get_session=broken)
    app.dependency_overrides[get_search] = lambda: SearchHealth()
    response = await client.get("/api/v1/health")
    assert response.status_code == 503
    assert response.json()["services"]["database"]["status"] == "unhealthy"
    assert "private" not in response.text
