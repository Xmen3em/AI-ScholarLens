"""Loopback preview configuration shared without loading evaluation runners."""

from pathlib import Path
from urllib.parse import urlsplit

from sqlalchemy.engine import make_url
from src.config import Settings


def preview_settings(original: Settings, workspace: Path) -> Settings:
    allowed = {"127.0.0.1", "localhost", "::1"}
    for value, port in [(original.opensearch_host, 9200), (original.ollama_host, 11434)]:
        origin = urlsplit(value)
        if (
            origin.scheme != "http"
            or origin.hostname not in allowed
            or origin.port != port
            or origin.path not in {"", "/"}
            or origin.query
            or origin.fragment
            or origin.username
            or origin.password
        ):
            raise ValueError("Preview requires retained loopback dependencies")
    database = make_url(original.postgres_database_url)
    if (
        database.drivername not in {"postgresql", "postgresql+psycopg2"}
        or database.host not in allowed
        or database.port not in {None, 5432}
        or database.query
    ):
        raise ValueError("Preview requires retained loopback database")
    workspace = workspace.resolve()
    quota = (workspace / "data/pc-app/api-quotas.sqlite3").resolve()
    if not quota.is_relative_to(workspace / "data/pc-app"):
        raise ValueError("Preview quota must stay in its ignored workspace directory")
    settings = Settings.model_validate(
        original.model_copy(
            update={
                "hf_inference_enabled": False,
                "agent_enabled": False,
                "answer_cache_enabled": False,
                "local_tracing_enabled": False,
                "monitoring_directory": None,
                "api_rate_limit_path": str(quota),
                "postgres_pool_size": 3,
                "postgres_max_overflow": 0,
            }
        ).model_dump()
    )
    if settings.api_key is None:
        raise ValueError("Preview requires the existing API key")
    return settings

