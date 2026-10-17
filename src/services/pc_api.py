"""Isolated read-only API preview; no production startup, migrations or generation."""

from contextlib import asynccontextmanager, contextmanager
from typing import Iterator

import anyio
from fastapi import FastAPI, HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from src.config import Settings
from src.db.interfaces.base import BaseDatabase
from src.dependencies import get_settings
from src.middlewares import OperationalMiddleware
from src.routers import papers, ping, search
from src.schemas.api.rag import AskRequest
from src.services.ollama.factory import make_ollama_client
from src.services.pc_clients import make_embedder, make_search_client
from src.services.search import SearchService


class ReadOnlyDatabase(BaseDatabase):
    def __init__(self, settings: Settings):
        self.settings = settings
        self.engine: Engine | None = None
        self.session_factory: sessionmaker | None = None

    def startup(self) -> None:
        # PostgreSQL applies this option to every connection, including pooled
        # reconnects. This startup deliberately performs no schema migrations.
        self.engine = create_engine(
            self.settings.postgres_database_url,
            echo=False,
            pool_size=3,
            max_overflow=0,
            pool_pre_ping=True,
            connect_args={"options": "-c default_transaction_read_only=on", "connect_timeout": 3},
        )
        self.session_factory = sessionmaker(bind=self.engine, expire_on_commit=False)
        with self.engine.connect() as connection:
            connection.execute(text("SELECT 1"))

    @contextmanager
    def get_session(self) -> Iterator[Session]:
        if self.session_factory is None:
            raise RuntimeError("Preview database is not ready")
        with self.session_factory() as session:
            try:
                yield session
            except Exception:
                session.rollback()
                raise

    def teardown(self) -> None:
        if self.engine is not None:
            self.engine.dispose()


def create_preview_app(settings: Settings) -> FastAPI:
    if settings.api_key is None or settings.hf_inference_enabled or settings.agent_enabled or settings.answer_cache_enabled:
        raise ValueError("Preview requires authentication and disabled generation/cache")

    @asynccontextmanager
    async def lifespan(app):
        database = ReadOnlyDatabase(settings)
        search_client = ollama = None
        try:
            database.startup()
            search_client = make_search_client(settings)
            app.state.search = SearchService(search_client, make_embedder(settings))
            ollama = make_ollama_client(settings)
            app.state.database, app.state.ollama = database, ollama
            yield
        finally:
            with anyio.CancelScope(shield=True):
                try:
                    if ollama is not None:
                        await ollama.aclose()
                finally:
                    try:
                        if search_client is not None:
                            search_client.close()
                    finally:
                        database.teardown()

    local = create_local_app(settings, lifespan)

    async def unavailable(request: AskRequest):
        raise HTTPException(status_code=503, detail="The research service is not ready.")

    for path in ("/ask", "/stream", "/agent/ask", "/agent/stream"):
        local.add_api_route("/api/v1" + path, unavailable, methods=["POST"])
    return local


def create_local_app(settings: Settings, lifespan) -> FastAPI:
    from src.main import app as production

    local = FastAPI(title="ScholarLens private PC API", lifespan=lifespan)
    local.exception_handlers = production.exception_handlers.copy()
    local.state.settings = settings
    local.state.hf = local.state.agent = local.state.rag = None
    local.state.monitoring = local.state.tracing = None
    local.dependency_overrides[get_settings] = lambda: settings
    for router in (ping.router, papers.router, search.router):
        local.include_router(router, prefix="/api/v1")
    local.add_middleware(OperationalMiddleware, settings=settings)
    return local
