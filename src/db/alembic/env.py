"""Alembic environment for this application's tables.

Airflow's metadata database is the *same* PostgreSQL database as the application's
(compose points both at rag_db), and Airflow runs Alembic itself. Two consequences,
both enforced below:

* The version table cannot be the default ``alembic_version`` — that one is Airflow's,
  and sharing it would interleave two unrelated migration histories.
* Autogenerate must ignore every table that is not ours, or it will happily emit
  ``drop_table()`` for Airflow's ~30 tables.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool
from src.db.interfaces.postgresql import Base, PostgreSQLSettings
from src.db.migrations import VERSION_TABLE
from src.models.paper import Paper  # noqa: F401  (registers `papers` on Base.metadata)

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    """Read POSTGRES_DATABASE_URL only; migrations have no use for the rest of the app config."""
    return PostgreSQLSettings().database_url


def include_name(name, type_, parent_names) -> bool:
    """Restrict autogenerate to tables this project owns."""
    if type_ == "table":
        return name in target_metadata.tables
    return True


def _configure(**kwargs) -> None:
    context.configure(
        target_metadata=target_metadata,
        version_table=VERSION_TABLE,
        include_name=include_name,
        include_schemas=False,
        compare_type=True,
        **kwargs,
    )


def run_migrations_offline() -> None:
    """Emit SQL to stdout without connecting."""
    _configure(
        url=_database_url(),
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run against a live database, reusing a caller's connection when given one."""
    connection = config.attributes.get("connection")
    if connection is not None:
        # The caller owns the transaction (see src/db/migrations.py).
        _configure(connection=connection)
        context.run_migrations()
        return

    config.set_main_option("sqlalchemy.url", _database_url())
    engine = engine_from_config(config.get_section(config.config_ini_section, {}), prefix="sqlalchemy.", poolclass=pool.NullPool)
    with engine.connect() as conn:
        _configure(connection=conn)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
