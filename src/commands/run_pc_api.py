"""Offline default; explicitly start a read-only private preview on loopback8002."""

import argparse
import json
import math
from pathlib import Path
from urllib.parse import urlsplit

import uvicorn
from sqlalchemy.engine import make_url
from src.commands.evaluate_agent import free_memory_mib
from src.commands.hf_evaluation import load_protocol
from src.config import Settings
from src.services.pc_api import create_preview_app
from src.services.telegram_bot import single_instance


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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="Offline configuration/resource check (default)")
    mode.add_argument("--execute-preview", action="store_true", help="Serve authenticated read-only preview on127.0.0.1:8002")
    args = parser.parse_args()
    try:
        settings = preview_settings(Settings(), Path.cwd())
        free_mib = free_memory_mib()
        admitted = math.isfinite(free_mib) and free_mib >= load_protocol()["admission_mib"]["bm25"]
        if not args.execute_preview:
            print(
                json.dumps(
                    {
                        "status": "preview_prepared" if admitted else "preview_prepared_memory_required",
                        "outbound_calls": 0,
                        "generation_enabled": False,
                        "port": 8002,
                    }
                )
            )
            return
        if not admitted:
            print(json.dumps({"status": "not_started_insufficient_memory", "outbound_calls": 0}))
            return
        with single_instance(Path(settings.api_rate_limit_path)):
            local = create_preview_app(settings)
            uvicorn.run(local, host="127.0.0.1", port=8002, workers=1, access_log=False, ws="none", timeout_graceful_shutdown=3)
    except KeyboardInterrupt:
        print(json.dumps({"status": "stopped"}))
    except Exception:
        print(json.dumps({"status": "preview_configuration_or_startup_error"}))
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
