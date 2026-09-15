from functools import lru_cache
from typing import Annotated, Generator

from fastapi import Depends, Request
from sqlalchemy.orm import Session
from src.config import Settings
from src.db.interfaces.base import BaseDatabase
from src.services.ollama import OllamaClient
from src.services.rag import RAGService
from src.services.search import SearchService


@lru_cache
def get_settings() -> Settings:
    """Get application settings."""
    return Settings()


def get_request_settings(request: Request) -> Settings:
    """Get settings from the request state."""
    return request.app.state.settings


def get_database(request: Request) -> BaseDatabase:
    """Get database from the request state."""
    return request.app.state.database


def get_db_session(database: Annotated[BaseDatabase, Depends(get_database)]) -> Generator[Session, None, None]:
    """Get database session dependency."""
    with database.get_session() as session:
        yield session


def get_search(request: Request) -> SearchService:
    """Get the search service from the request state."""
    return request.app.state.search


def get_ollama(request: Request) -> OllamaClient:
    """Get the worker-scoped Ollama client."""
    return request.app.state.ollama


def get_rag(request: Request) -> RAGService:
    """Get the grounded-answer service."""
    return request.app.state.rag


SettingsDep = Annotated[Settings, Depends(get_settings)]
DatabaseDep = Annotated[BaseDatabase, Depends(get_database)]
SessionDep = Annotated[Session, Depends(get_db_session)]
SearchDep = Annotated[SearchService, Depends(get_search)]
OllamaDep = Annotated[OllamaClient, Depends(get_ollama)]
RAGDep = Annotated[RAGService, Depends(get_rag)]
