import json
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
from src.commands import run_pc_api as command
from src.config import Settings
from src.services import pc_api

KEY = "synthetic-private-api-key-1234567890"


def config(tmp_path, **updates):
    return Settings(_env_file=None, api_key=KEY, api_rate_limit_path=str(tmp_path / "quotas.sqlite3"), **updates)


def test_preview_settings_force_no_generation_and_keep_private_env_unchanged(tmp_path):
    original = config(tmp_path, hf_token="hf_synthetic1234567890", hf_inference_enabled=True, agent_enabled=True)
    before = original.model_dump()
    preview = command.preview_settings(original, tmp_path)
    assert preview.api_key == original.api_key and preview.hf_token == original.hf_token
    assert preview.hf_inference_enabled is preview.agent_enabled is preview.answer_cache_enabled is False
    assert preview.local_tracing_enabled is False and preview.monitoring_directory is None
    assert preview.api_rate_limit_path == str(tmp_path / "data/pc-app/api-quotas.sqlite3")
    assert original.model_dump() == before and not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    "field,value",
    [
        ("opensearch_host", "https://external.invalid:9200"),
        ("ollama_host", "http://127.0.0.1:11434/?secret=x"),
        ("postgres_database_url", "postgresql://user:password@external.invalid:5432/db"),
        ("postgres_database_url", "postgresql://user:password@localhost:5433/db"),
    ],
)
def test_candidate_requires_retained_loopback_dependencies(tmp_path, field, value):
    with pytest.raises(ValueError):
        command.preview_settings(config(tmp_path, **{field: value}), tmp_path)


def test_preview_rejects_enabled_generation_before_constructing_any_client(tmp_path, monkeypatch):
    monkeypatch.setattr(pc_api, "ReadOnlyDatabase", lambda *args: pytest.fail("Enabled preview constructed database"))
    with pytest.raises(ValueError):
        pc_api.create_preview_app(config(tmp_path, agent_enabled=True))


def test_readonly_database_connects_without_migrations_and_closes_owned_engine(tmp_path, monkeypatch):
    statements = []
    engine = SimpleNamespace(disposed=False)

    @contextmanager
    def connect():
        yield SimpleNamespace(execute=lambda statement: statements.append(str(statement)))

    engine.connect = connect
    engine.dispose = lambda: setattr(engine, "disposed", True)
    captured = {}

    def create_engine(url, **kwargs):
        captured.update(kwargs)
        return engine

    monkeypatch.setattr(pc_api, "create_engine", create_engine)
    monkeypatch.setattr(pc_api, "sessionmaker", lambda **kwargs: lambda: None)
    monkeypatch.setattr("src.db.interfaces.postgresql.run_migrations", lambda *args: pytest.fail("Preview ran migrations"))
    database = pc_api.ReadOnlyDatabase(config(tmp_path))
    database.startup()
    assert statements == ["SELECT 1"]
    assert captured["connect_args"]["options"] == "-c default_transaction_read_only=on"
    assert captured["echo"] is False and captured["pool_size"] == 3 and captured["max_overflow"] == 0
    database.teardown()
    assert engine.disposed


@pytest.mark.anyio
async def test_preview_preserves_auth_and_blocks_every_generation_route_without_models(tmp_path):
    app = pc_api.create_preview_app(config(tmp_path))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://local") as client:
        for path in ("/ask", "/stream", "/agent/ask", "/agent/stream"):
            denied = await client.post("/api/v1" + path, json={"query": "Explain AI retrieval"})
            assert denied.status_code == 401
            response = await client.post("/api/v1" + path, json={"query": "Explain AI retrieval"}, headers={"X-API-Key": KEY})
            assert response.status_code == 503 and response.json() == {"detail": "The research service is not ready."}
    assert app.state.hf is None and app.state.agent is None
    assert app.state.settings.hf_inference_enabled is False


@pytest.mark.anyio
async def test_preview_owns_and_closes_only_its_readonly_clients(tmp_path, monkeypatch):
    events = []

    class Database:
        def __init__(self, *args):
            pass

        def startup(self):
            events.append("database_readonly")

        def teardown(self):
            events.append("database_closed")

    class Ollama:
        async def aclose(self):
            events.append("ollama_closed")

    search = SimpleNamespace(close=lambda: events.append("search_closed"))
    monkeypatch.setattr(pc_api, "ReadOnlyDatabase", Database)
    monkeypatch.setattr(pc_api, "make_search_client", lambda settings: search)
    monkeypatch.setattr(pc_api, "make_embedder", lambda settings: SimpleNamespace())
    monkeypatch.setattr(pc_api, "make_ollama_client", lambda settings: Ollama())
    app = pc_api.create_preview_app(config(tmp_path))
    async with app.router.lifespan_context(app):
        assert app.state.database and app.state.search
        assert app.state.hf is None and app.state.agent is None
    assert events == ["database_readonly", "ollama_closed", "search_closed", "database_closed"]


def test_offline_preview_check_never_constructs_server_or_state(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    factory = Mock(return_value=config(tmp_path))
    factory.model_validate = Settings.model_validate
    monkeypatch.setattr(command, "Settings", factory)
    monkeypatch.setattr(command, "load_protocol", lambda: {"admission_mib": {"bm25": 1024}})
    monkeypatch.setattr(command, "free_memory_mib", lambda: 512)
    monkeypatch.setattr(command, "create_preview_app", lambda *args: pytest.fail("Offline check constructed API"))
    monkeypatch.setattr("sys.argv", ["run_pc_api", "--check"])
    command.main()
    result = json.loads(capsys.readouterr().out)
    assert result["outbound_calls"] == 0 and result["status"] == "preview_prepared_memory_required"
    assert not list(tmp_path.iterdir())


def test_low_memory_stops_preview_before_state_or_server_creation(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    factory = Mock(return_value=config(tmp_path))
    factory.model_validate = Settings.model_validate
    monkeypatch.setattr(command, "Settings", factory)
    monkeypatch.setattr(command, "load_protocol", lambda: {"admission_mib": {"bm25": 1024}})
    monkeypatch.setattr(command, "free_memory_mib", lambda: 512)
    monkeypatch.setattr(command, "create_preview_app", lambda *args: pytest.fail("Unadmitted API start"))
    monkeypatch.setattr("sys.argv", ["run_pc_api", "--execute-preview"])
    command.main()
    assert json.loads(capsys.readouterr().out)["status"] == "not_started_insufficient_memory"
    assert not list(tmp_path.iterdir())


@pytest.mark.anyio
@pytest.mark.parametrize("failure", ["database", "search", "embedder", "ollama"])
async def test_partial_startup_failure_disposes_every_owned_resource(tmp_path, monkeypatch, failure):
    events = []

    def fail(stage):
        if failure == stage:
            raise RuntimeError("synthetic startup failure")

    class Database:
        def __init__(self, *args):
            pass

        def startup(self):
            fail("database")

        def teardown(self):
            events.append("database_closed")

    expected_settings = config(tmp_path)

    def search_client(settings):
        assert settings is expected_settings
        fail("search")
        return SimpleNamespace(close=lambda: events.append("search_closed"))

    def embedder(settings):
        assert settings is expected_settings
        fail("embedder")
        return SimpleNamespace()

    def ollama(settings):
        assert settings is expected_settings
        fail("ollama")

    monkeypatch.setattr(pc_api, "ReadOnlyDatabase", Database)
    monkeypatch.setattr(pc_api, "make_search_client", search_client)
    monkeypatch.setattr(pc_api, "make_embedder", embedder)
    monkeypatch.setattr(pc_api, "make_ollama_client", ollama)
    app = pc_api.create_preview_app(expected_settings)
    with pytest.raises(RuntimeError):
        async with app.router.lifespan_context(app):
            pytest.fail("Failed preview startup became ready")
    assert events == (["search_closed", "database_closed"] if failure in {"embedder", "ollama"} else ["database_closed"])


def test_missing_api_key_cannot_start_a_candidate(tmp_path):
    original = Settings(_env_file=None, api_key=None)
    with pytest.raises(ValueError):
        command.preview_settings(original, tmp_path)


def test_quota_symlink_cannot_escape_workspace(tmp_path, monkeypatch):
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "data").mkdir()
    try:
        (tmp_path / "data/pc-app").symlink_to(outside, target_is_directory=True)
    except OSError:
        real_resolve = Path.resolve
        monkeypatch.setattr(
            Path, "resolve", lambda self: outside / self.name if self.name == "api-quotas.sqlite3" else real_resolve(self)
        )
    with pytest.raises(ValueError):
        command.preview_settings(config(tmp_path), tmp_path)


def test_explicit_preview_binds_only_loopback8002_with_one_worker_and_separate_quota(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    original = config(tmp_path)
    before = original.model_dump()
    factory = Mock(return_value=original)
    factory.model_validate = Settings.model_validate
    monkeypatch.setattr(command, "Settings", factory)
    monkeypatch.setattr(command, "load_protocol", lambda: {"admission_mib": {"bm25": 1024}})
    monkeypatch.setattr(command, "free_memory_mib", lambda: 4096)
    local = object()
    captured = {}

    def create(settings):
        assert settings.api_rate_limit_path == str(tmp_path / "data/pc-app/api-quotas.sqlite3")
        assert settings.hf_inference_enabled is settings.agent_enabled is False
        return local

    def serve(app, **kwargs):
        assert app is local
        captured.update(kwargs)

    monkeypatch.setattr(command, "create_preview_app", create)
    monkeypatch.setattr(command.uvicorn, "run", serve)
    monkeypatch.setattr("sys.argv", ["run_pc_api", "--execute-preview"])
    command.main()
    assert captured["host"] == "127.0.0.1" and captured["port"] == 8002 and captured["workers"] == 1
    assert captured["access_log"] is False and captured["ws"] == "none"
    assert original.model_dump() == before
