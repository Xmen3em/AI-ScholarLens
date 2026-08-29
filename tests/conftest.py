"""Shared fixtures for the current API and ingestion components."""

from datetime import datetime, timezone
from pathlib import Path
from shutil import rmtree
from uuid import uuid4

import httpx
import pytest
from src.config import Settings
from src.schemas.arxiv.paper import ArxivPaper, PaperCreate


@pytest.fixture
def settings() -> Settings:
    """Return deterministic settings without reading the developer's .env."""
    return Settings(_env_file=None)


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    """Run async tests with asyncio only; the application does not require Trio."""
    return "asyncio"


@pytest.fixture
def paper_create_data() -> PaperCreate:
    """A valid paper payload for repository and schema tests."""
    return PaperCreate(
        arxiv_id="2401.00001",
        title="Test paper",
        authors=["Ada Lovelace"],
        abstract="A test abstract.",
        categories=["cs.AI"],
        published_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
        pdf_url="https://arxiv.org/pdf/2401.00001",
    )


@pytest.fixture
def arxiv_paper() -> ArxivPaper:
    """A valid arXiv API model for client tests."""
    return ArxivPaper(
        arxiv_id="2401.00001",
        title="Test paper",
        authors=["Ada Lovelace"],
        abstract="A test abstract.",
        categories=["cs.AI"],
        published_date="2024-01-01T00:00:00Z",
        pdf_url="https://arxiv.org/pdf/2401.00001",
    )


@pytest.fixture
def writable_cache_dir():
    """Provide a project-local temporary directory for restricted Windows environments."""
    cache_dir = Path(__file__).parent / "test_output" / f"cache-{uuid4().hex}"
    cache_dir.mkdir(parents=True)
    yield cache_dir
    rmtree(cache_dir, ignore_errors=True)


@pytest.fixture
def stub_httpx(monkeypatch):
    """Route every ``httpx.AsyncClient`` through a handler and record the outbound requests.

    Mocks only the HTTP boundary: real ``Request``/``Response`` objects still flow
    through the client under test, and the patch is per-test, so no state leaks
    between tests.
    """

    real_client_cls = httpx.AsyncClient

    def install(handler) -> list[httpx.Request]:
        requests: list[httpx.Request] = []

        def recording_handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return handler(request)

        def factory(*args, **kwargs):
            kwargs.pop("transport", None)
            return real_client_cls(*args, transport=httpx.MockTransport(recording_handler), **kwargs)

        monkeypatch.setattr(httpx, "AsyncClient", factory)
        return requests

    return install
