"""Thin private clients; no database, API routers or evaluation execution imports."""

from opensearchpy import OpenSearch
from src.config import Settings
from src.services.embeddings.ollama import OllamaEmbedder


def make_search_client(settings: Settings):
    return OpenSearch(hosts=[settings.opensearch_host], retry_on_timeout=False, max_retries=0, timeout=30)


def make_embedder(settings: Settings):
    return OllamaEmbedder(host=settings.ollama_host, model=settings.ollama_embedding_model)

