from src.config import Settings
from src.services.ollama.client import OllamaClient


def make_ollama_client(settings: Settings) -> OllamaClient:
    """Build the worker-scoped Ollama client."""
    return OllamaClient(settings)
