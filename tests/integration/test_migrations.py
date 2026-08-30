"""Schema migrations against a real PostgreSQL server.

These cannot be faked: the point is that the SQL Alembic emits produces exactly the
schema the models declare, on a database that also hosts Airflow's own tables.
"""

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session
from src.db.interfaces.postgresql import Base
from src.db.migrations import BASELINE_REVISION, VERSION_TABLE, run_migrations
from src.models.paper import Paper  # noqa: F401  (registers `papers` on Base.metadata)

from tests.integration.test_paper_repository import make_paper


@pytest.fixture
def scratch_database(postgres_engine):
    """A throwaway database on the same server, so migrations start from nothing."""
    created = []

    def make(name: str):
        admin = create_engine(postgres_engine.url, isolation_level="AUTOCOMMIT")
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
            connection.execute(text(f'CREATE DATABASE "{name}"'))
        admin.dispose()
        engine = create_engine(postgres_engine.url.set(database=name))
        created.append((engine, name))
        return engine

    yield make

    for engine, name in created:
        engine.dispose()
        admin = create_engine(postgres_engine.url, isolation_level="AUTOCOMMIT")
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


def current_revision(engine):
    with engine.connect() as connection:
        if not inspect(connection).has_table(VERSION_TABLE):
            return None
        return connection.execute(text(f"SELECT version_num FROM {VERSION_TABLE}")).scalar()


def test_empty_database_gets_the_papers_table(scratch_database):
    engine = scratch_database("scope_mig_empty")

    run_migrations(engine)

    assert inspect(engine).has_table("papers")
    assert current_revision(engine) == BASELINE_REVISION


def test_schema_built_before_migrations_is_baselined_without_losing_rows(scratch_database):
    """The deployed database was created by create_all and has no migration history."""
    engine = scratch_database("scope_mig_legacy")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Paper(**make_paper("2401.00001").model_dump()))
        session.commit()
    assert current_revision(engine) is None

    run_migrations(engine)

    assert current_revision(engine) == BASELINE_REVISION
    with Session(engine) as session:
        assert session.query(Paper).count() == 1, "baselining must not touch existing rows"


def test_running_migrations_twice_is_idempotent(scratch_database):
    engine = scratch_database("scope_mig_twice")

    run_migrations(engine)
    run_migrations(engine)

    assert current_revision(engine) == BASELINE_REVISION


def test_airflow_tables_in_the_same_database_are_left_alone(scratch_database):
    """Compose points Airflow at this same database, and Airflow runs Alembic too."""
    engine = scratch_database("scope_mig_airflow")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE dag (dag_id VARCHAR(250) PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)"))
        connection.execute(text("INSERT INTO alembic_version VALUES ('airflow_head_abc123')"))

    run_migrations(engine)

    with engine.connect() as connection:
        assert inspect(connection).has_table("dag")
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar() == "airflow_head_abc123"
    assert current_revision(engine) == BASELINE_REVISION


def describe(engine) -> tuple:
    inspector = inspect(engine)
    return (
        {column["name"]: (str(column["type"]), column["nullable"]) for column in inspector.get_columns("papers")},
        sorted((i["name"], tuple(i["column_names"]), i["unique"]) for i in inspector.get_indexes("papers")),
        tuple(inspector.get_pk_constraint("papers")["constrained_columns"]),
        sorted((u["name"], tuple(u["column_names"])) for u in inspector.get_unique_constraints("papers")),
    )


def test_migrated_schema_matches_the_models(scratch_database):
    """Fails when a model changes and nobody wrote the migration for it."""
    migrated = scratch_database("scope_mig_head")
    from_models = scratch_database("scope_mig_models")

    run_migrations(migrated)
    Base.metadata.create_all(from_models)

    assert describe(migrated) == describe(from_models)
