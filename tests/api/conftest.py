"""API test configuration and fixtures."""

import pytest
from httpx import ASGITransport, AsyncClient
from src.config import Settings
from src.main import app


@pytest.fixture(autouse=True)
def local_access_controls(writable_cache_dir):
    previous = getattr(app.state, "settings", None)
    app.state.settings = Settings(_env_file=None, api_requests_per_minute=10000, api_generations_per_minute=10000,
                                  api_rate_limit_path=str(writable_cache_dir / "limits.sqlite3"))
    yield
    if previous is None:
        del app.state.settings
    else:
        app.state.settings = previous


@pytest.fixture
async def client():
    """HTTP client for API testing."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
