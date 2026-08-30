from src.config import get_settings
from src.db.interfaces.base import BaseDatabase
from src.db.interfaces.postgresql import PostgreSQLDatabase, PostgreSQLSettings


def make_database() -> BaseDatabase:
    settings = get_settings()
    postgres_settings = PostgreSQLSettings(
        database_url=settings.postgres_database_url,
        echo_sql=settings.postgres_echo_sql,
        pool_size=settings.postgres_pool_size,
        max_overflow=settings.postgres_max_overflow
    )
    database = PostgreSQLDatabase(config=postgres_settings)
    database.startup()
    return database