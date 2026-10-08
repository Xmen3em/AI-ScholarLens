"""Construction of the embedding client, mirroring the other service factories."""

from src.config import get_settings
from src.services.embeddings.ollama import OllamaEmbedder


def make_embedder() -> OllamaEmbedder:
    settings = get_settings()
    return OllamaEmbedder(host=settings.ollama_host, model=settings.ollama_embedding_model)
