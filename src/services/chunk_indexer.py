"""Writing stored papers into the OpenSearch chunk index, one passage at a time."""

import hashlib
import logging
from datetime import datetime
from typing import Any, Dict, List, Sequence, Tuple

from opensearchpy import OpenSearch
from src.policies.chunking import Chunk, chunk_document_id, chunk_sections
from src.repositories.paper import IndexableRow, PaperRepository
from src.search.indices import CHUNK_ALIAS, CHUNK_INDEX, ensure_chunk_index
from src.services.embeddings.ollama import OllamaEmbedder
from src.services.reindex import CorpusReindexer, IndexRun, strings

logger = logging.getLogger(__name__)


class ChunkIndexer(CorpusReindexer):
    """Turns stored papers into retrievable passages, each with its embedding.

    Chunk ids are positional, so a rewrite overwrites the passage that was at that
    position rather than appending a second copy of it.

    Embedding is the expensive part — roughly two thirds of a second a passage on
    CPU, so re-embedding the whole corpus every pass would cost a quarter of an hour
    and grow with it. Each document therefore carries a hash of its text, and a
    rewrite reuses the stored vector whenever that hash still matches.
    """

    def __init__(
        self,
        client: OpenSearch,
        repository: PaperRepository,
        embedder: OllamaEmbedder,
        index: str = CHUNK_INDEX,
        alias: str = CHUNK_ALIAS,
    ):
        super().__init__(client, index, alias)
        self.repository = repository
        self.embedder = embedder
        # Tallied while building documents, which happens a paper at a time, and folded
        # into the run report the base class assembles.
        self._embedded = 0
        self._reused = 0

    def index_corpus(self) -> IndexRun:
        self._embedded = self._reused = 0
        run = super().index_corpus()
        run.embeddings_computed, run.embeddings_reused = self._embedded, self._reused
        logger.info("Embedded %d passages, reused %d", self._embedded, self._reused)
        return run

    def ensure_index(self) -> None:
        ensure_chunk_index(self.client)

    def papers(self) -> Sequence[IndexableRow]:
        return self.repository.list_indexable()

    def documents(self, paper: IndexableRow, stamp: datetime) -> List[Dict[str, Any]]:
        chunks = chunk_sections(paper.sections)
        if not chunks:
            return []

        identified = [(chunk_document_id(paper.arxiv_id, c.section_index, c.chunk_index), c) for c in chunks]
        vectors = self._embeddings([(doc_id, chunk.content) for doc_id, chunk in identified])

        indexed_at = stamp.isoformat()
        published_date = paper.published_date.isoformat()
        authors, categories = strings(paper.authors), strings(paper.categories)
        return [
            {
                "_index": self.index,
                "_id": doc_id,
                "_source": {
                    "arxiv_id": paper.arxiv_id,
                    "title": paper.title,
                    "authors": authors,
                    "categories": categories,
                    "published_date": published_date,
                    "section_title": chunk.section_title,
                    "section_index": chunk.section_index,
                    "chunk_index": chunk.chunk_index,
                    "content": chunk.content,
                    "char_count": len(chunk.content),
                    "content_hash": content_hash(chunk.content),
                    "embedding": vectors[doc_id],
                    "indexed_at": indexed_at,
                },
            }
            for doc_id, chunk in identified
        ]

    def _embeddings(self, passages: Sequence[Tuple[str, str]]) -> Dict[str, List[float]]:
        """A vector for every passage, reusing whatever the index already holds."""
        stored = self._stored_embeddings([doc_id for doc_id, _content in passages])

        vectors: Dict[str, List[float]] = {}
        stale: List[Tuple[str, str]] = []
        for doc_id, content in passages:
            reusable = stored.get(doc_id)
            if reusable and reusable[0] == content_hash(content):
                vectors[doc_id] = reusable[1]
            else:
                stale.append((doc_id, content))

        self._reused += len(vectors)
        self._embedded += len(stale)
        if stale:
            computed = self.embedder.embed_documents([content for _doc_id, content in stale])
            vectors.update({doc_id: vector for (doc_id, _content), vector in zip(stale, computed)})
        return vectors

    def _stored_embeddings(self, doc_ids: Sequence[str]) -> Dict[str, Tuple[str, List[float]]]:
        """What the index already holds for these ids, as hash to vector.

        Reads the concrete index rather than the alias: during a mapping migration the
        alias still points at the previous index, which has no vectors to reuse.
        """
        if not self.client.indices.exists(index=self.index):
            return {}
        response = self.client.mget(
            index=self.index,
            body={"ids": list(doc_ids)},
            _source=["content_hash", "embedding"],
        )
        stored = {}
        for doc in response.get("docs", []):
            source = doc.get("_source") or {}
            stored_hash, embedding = source.get("content_hash"), source.get("embedding")
            if isinstance(stored_hash, str) and isinstance(embedding, list):
                stored[doc["_id"]] = (stored_hash, embedding)
        return stored


def content_hash(content: str) -> str:
    """Identifies the exact text a stored vector was computed from.

    Truncated to 16 hex characters: this distinguishes passages within one paper, not
    across a security boundary, and the full digest triples the field's size in an
    index that already stores a 768-float vector per document.
    """
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
