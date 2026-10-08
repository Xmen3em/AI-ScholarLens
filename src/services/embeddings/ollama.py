"""Turning text into vectors with a locally hosted embedding model."""

import logging
from typing import Any, Dict, List, Sequence

import httpx
from src.exceptions import EmbeddingError, OllamaConnectionError, OllamaTimeoutError

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "nomic-embed-text"
EMBEDDING_DIMENSIONS = 768

# nomic-embed-text is trained with task prefixes. Without them a query and a passage
# land in different regions of the space and cosine similarity between them degrades,
# which is invisible in the output — the vectors still have the right shape.
DOCUMENT_PREFIX = "search_document: "
QUERY_PREFIX = "search_query: "

# Measured on this host: batching gives no throughput gain (CPU-bound, ~1.5 chunks a
# second either way), so the batch is sized for failure granularity and progress
# logging rather than speed.
BATCH_SIZE = 8

# Minutes, not seconds. A batch of eight 2000-character passages takes roughly five
# seconds on CPU; the generous ceiling is for a cold model load, which is a one-time
# multi-second stall that a 30-second timeout would turn into a failed DAG run.
TIMEOUT_SECONDS = 180.0


class OllamaEmbedder:
    """Embeds text through Ollama's /api/embed endpoint.

    Synchronous, unlike OllamaClient: the only caller is the indexer, which runs
    inside an Airflow task, and an embedding pass is measured in minutes rather than
    the 30 seconds a health check budgets for.
    """

    def __init__(self, host: str, model: str = EMBEDDING_MODEL, dimensions: int = EMBEDDING_DIMENSIONS):
        self.host = host.rstrip("/")
        self.model = model
        self.dimensions = dimensions

    def embed_documents(self, texts: Sequence[str]) -> List[List[float]]:
        """Embed passages for indexing, in the same order they were given."""
        vectors: List[List[float]] = []
        for start in range(0, len(texts), BATCH_SIZE):
            batch = texts[start : start + BATCH_SIZE]
            vectors.extend(self._embed([DOCUMENT_PREFIX + text for text in batch]))
        return vectors

    def embed_query(self, text: str) -> List[float]:
        """Embed a search query, which the model treats differently from a passage."""
        return self._embed([QUERY_PREFIX + text])[0]

    def _embed(self, inputs: List[str]) -> List[List[float]]:
        try:
            with httpx.Client(timeout=TIMEOUT_SECONDS) as client:
                response = client.post(f"{self.host}/api/embed", json={"model": self.model, "input": inputs})
                response.raise_for_status()
                payload = response.json()
        except httpx.ConnectError as e:
            raise OllamaConnectionError(f"Cannot connect to Ollama at {self.host}: {e}") from e
        except httpx.TimeoutException as e:
            raise OllamaTimeoutError(f"Embedding with {self.model} timed out after {TIMEOUT_SECONDS}s: {e}") from e
        except httpx.HTTPStatusError as e:
            # A missing model is a 404 here, and it is the most likely failure on a
            # fresh stack, so name it rather than reporting a bare status code.
            raise EmbeddingError(f"Ollama refused to embed with {self.model}: {e.response.text.strip()[:200]}") from e

        return self._validate(payload, expected=len(inputs))

    def _validate(self, payload: Dict[str, Any], expected: int) -> List[List[float]]:
        """Check the response before it can reach the index.

        A wrong width is the dangerous case: OpenSearch rejects it outright if the
        mapping disagrees, but a model swapped for one of the same width would be
        accepted and silently poison every similarity score in the index.
        """
        vectors = payload.get("embeddings")
        if not isinstance(vectors, list) or len(vectors) != expected:
            raise EmbeddingError(f"{self.model} returned {type(vectors).__name__} for {expected} inputs, not a list of {expected}")
        for vector in vectors:
            if not isinstance(vector, list) or len(vector) != self.dimensions:
                width = len(vector) if isinstance(vector, list) else "no"
                raise EmbeddingError(f"{self.model} returned a vector of {width} dimensions, expected {self.dimensions}")
        return vectors
