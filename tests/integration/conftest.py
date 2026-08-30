"""Real PostgreSQL for the tests where persistence itself is the subject.

The repository's query and upsert logic cannot be verified against a mocked session:
a fake returns whatever it was told to, so schema mistakes, constraint violations and
`exclude_unset` behaviour all pass silently. These tests run against a throwaway
PostgreSQL 16 container with the real schema applied.

They skip cleanly when Docker is unavailable, so `pytest -q` stays green without it.
"""

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from src.db.interfaces.postgresql import Base
from src.models.paper import Paper  # noqa: F401  (registers the table on Base.metadata)


@pytest.fixture(scope="session")
def postgres_engine():
    """A PostgreSQL container with the project's schema created from the models."""
    try:
        from testcontainers.postgres import PostgresContainer
    except ImportError as exc:  # pragma: no cover - depends on the local environment
        pytest.skip(f"testcontainers is not installed: {exc}")

    try:
        # Constructing the container already talks to the Docker daemon, so it has to
        # sit inside the guard too or an absent daemon errors instead of skipping.
        container = PostgresContainer("postgres:16-alpine")
        container.start()
    except Exception as exc:  # pragma: no cover - depends on the local environment
        pytest.skip(f"Docker is not available for database tests: {exc}")

    engine = create_engine(container.get_connection_url())
    try:
        Base.metadata.create_all(engine)
        yield engine
    finally:
        engine.dispose()
        container.stop()


@pytest.fixture
def db_session(postgres_engine) -> Session:
    """A session on the real schema, left empty for the next test.

    The repository no longer commits, but the code under test does (MetadataFetcher
    commits per paper, ai_scope commits a purge), so the table is truncated between
    tests rather than wrapped in a transaction those commits would end.
    """
    with Session(postgres_engine) as session:
        yield session
        session.rollback()
        session.execute(text("TRUNCATE TABLE papers"))
        session.commit()
