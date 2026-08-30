"""Bring the application's schema up to date at startup.

This replaces ``Base.metadata.create_all``, which only ever creates *missing tables*
and silently ignores changes to tables that already exist — so any later column would
never have reached a deployed database.

PostgreSQL-specific: the advisory lock below has no portable equivalent.
"""

import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

ALEMBIC_DIRECTORY = Path(__file__).parent / "alembic"

#: Distinct from Airflow's ``alembic_version``: compose points Airflow at the same
#: database, and it runs Alembic too. Defined here rather than in env.py because that
#: module only imports inside an Alembic run.
VERSION_TABLE = "alembic_version_scholarlens"

#: The revision matching a schema built by the old create_all() call.
BASELINE_REVISION = "0001_papers_baseline"

#: Both the API and the Airflow DAG call make_database(), so two processes can reach
#: this at once. Alembic takes no lock of its own; this one is released on commit.
#: The value is arbitrary — it only has to be the same in every process.
MIGRATION_LOCK_KEY = 8_811_027_314_159_265


def _alembic_config(connection) -> Config:
    """An Alembic config bound to a caller-owned connection, independent of the CWD."""
    config = Config()
    config.set_main_option("script_location", str(ALEMBIC_DIRECTORY))
    config.attributes["connection"] = connection
    return config


def _predates_migrations(connection) -> bool:
    """Whether this database has the old create_all schema but no migration history."""
    if MigrationContext.configure(connection, opts={"version_table": VERSION_TABLE}).get_current_revision():
        return False
    return inspect(connection).has_table("papers")


def run_migrations(engine: Engine) -> None:
    """Upgrade the schema to head, baselining a pre-migration database on the way."""
    with engine.begin() as connection:
        connection.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": MIGRATION_LOCK_KEY})
        config = _alembic_config(connection)

        if _predates_migrations(connection):
            logger.info("Found a papers table with no migration history; stamping %s", BASELINE_REVISION)
            command.stamp(config, BASELINE_REVISION)

        command.upgrade(config, "head")
        logger.info("Database schema is at head")
