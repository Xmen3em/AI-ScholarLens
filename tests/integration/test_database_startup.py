"""The service entry point: make_database() -> startup() -> a usable session.

Every process begins here, and since startup() now runs migrations rather than
create_all, what it does to a database is worth pinning down. Nothing else in the
suite exercises it: the migration tests call run_migrations directly.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session
from src.db.factory import make_database
from src.db.interfaces.postgresql import Base, PostgreSQLDatabase, PostgreSQLSettings
from src.db.migrations import BASELINE_REVISION, VERSION_TABLE
from src.models.paper import Paper
from src.repositories.paper import PaperRepository

from tests.integration.test_paper_repository import make_paper


@pytest.fixture
def started_database(scratch_database):
    """Start PostgreSQLDatabase against a throwaway database and tear it down after."""
    databases = []

    def start(name: str) -> PostgreSQLDatabase:
        engine = scratch_database(name)
        database = PostgreSQLDatabase(config=PostgreSQLSettings(database_url=str(engine.url)))
        database.startup()
        databases.append(database)
        return database

    yield start

    for database in databases:
        database.teardown()


def revision_of(database: PostgreSQLDatabase) -> str:
    with database.get_session() as session:
        return session.execute(text(f"SELECT version_num FROM {VERSION_TABLE}")).scalar()


def test_startup_migrates_an_empty_database_and_yields_a_usable_session(started_database):
    database = started_database("scope_startup_empty")

    with database.get_session() as session:
        assert PaperRepository(session).get_count() == 0, "the papers table should exist and be empty"
    assert revision_of(database) == BASELINE_REVISION


def test_a_second_service_starting_against_the_same_database_is_a_no_op(started_database, scratch_database):
    """The API and the Airflow DAG both call make_database() against one database."""
    first = started_database("scope_startup_shared")
    url = str(first.engine.url)

    second = PostgreSQLDatabase(config=PostgreSQLSettings(database_url=url))
    try:
        second.startup()
        assert revision_of(second) == BASELINE_REVISION
        with second.get_session() as session:
            assert PaperRepository(session).get_count() == 0
    finally:
        second.teardown()


def test_startup_baselines_a_database_created_before_migrations_existed(scratch_database):
    """The deployed database was built by the old create_all and has no history."""
    engine = scratch_database("scope_startup_legacy")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Paper(**make_paper("2401.00001").model_dump()))
        session.commit()

    database = PostgreSQLDatabase(config=PostgreSQLSettings(database_url=str(engine.url)))
    try:
        database.startup()

        assert revision_of(database) == BASELINE_REVISION
        with database.get_session() as session:
            assert PaperRepository(session).get_count() == 1, "startup must not disturb existing rows"
    finally:
        database.teardown()


def test_a_session_before_startup_fails_loudly(scratch_database):
    """Better a clear error than a connection to nothing."""
    engine = scratch_database("scope_startup_unstarted")
    database = PostgreSQLDatabase(config=PostgreSQLSettings(database_url=str(engine.url)))

    with pytest.raises(RuntimeError, match="startup"):
        with database.get_session():
            pass


def test_make_database_wires_settings_through_to_a_working_session(monkeypatch, scratch_database):
    """The path every service actually takes, settings included."""
    engine = scratch_database("scope_startup_factory")
    monkeypatch.setenv("POSTGRES_DATABASE_URL", str(engine.url))

    database = make_database()
    try:
        with database.get_session() as session:
            repository = PaperRepository(session)
            repository.upsert(make_paper("2401.00001"))
            session.commit()
            assert repository.get_count() == 1
    finally:
        database.teardown()
