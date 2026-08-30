"""Writing stored papers into the OpenSearch chunk index, one passage at a time."""

from datetime import datetime
from typing import Any, Dict, List, Sequence

from opensearchpy import OpenSearch
from src.policies.chunking import chunk_document_id, chunk_sections
from src.repositories.paper import IndexableRow, PaperRepository
from src.search.indices import CHUNK_ALIAS, ensure_chunk_index
from src.services.reindex import CorpusReindexer, strings


class ChunkIndexer(CorpusReindexer):
    """Turns stored papers into retrievable passages in OpenSearch.

    Chunk ids are positional, so a rewrite overwrites the passage that was at that
    position rather than appending a second copy of it.
    """

    def __init__(self, client: OpenSearch, repository: PaperRepository, alias: str = CHUNK_ALIAS):
        super().__init__(client, alias)
        self.repository = repository

    def ensure_index(self) -> None:
        ensure_chunk_index(self.client)

    def papers(self) -> Sequence[IndexableRow]:
        return self.repository.list_indexable()

    def documents(self, paper: IndexableRow, stamp: datetime) -> List[Dict[str, Any]]:
        indexed_at = stamp.isoformat()
        published_date = paper.published_date.isoformat()
        authors, categories = strings(paper.authors), strings(paper.categories)
        return [
            {
                "_index": self.alias,
                "_id": chunk_document_id(paper.arxiv_id, chunk.section_index, chunk.chunk_index),
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
                    "indexed_at": indexed_at,
                },
            }
            for chunk in chunk_sections(paper.sections)
        ]
