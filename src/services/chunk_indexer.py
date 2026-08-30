"""Writing stored papers into the OpenSearch chunk index."""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, NamedTuple, Optional

from opensearchpy import OpenSearch
from opensearchpy.helpers import bulk
from src.policies.chunking import Chunk, chunk_document_id, chunk_sections
from src.repositories.paper import IndexableRow, PaperRepository
from src.search.index import CHUNK_ALIAS, ensure_chunk_index

logger = logging.getLogger(__name__)


class PaperResult(NamedTuple):
    """What one paper's bulk write achieved."""

    chunks_written: int
    error: Optional[str]


@dataclass
class IndexRun:
    """What one pass over the corpus did, for the daily report."""

    papers_seen: int = 0
    papers_indexed: int = 0
    papers_without_chunks: int = 0
    chunks_indexed: int = 0
    stale_chunks_deleted: int = 0
    errors: List[str] = field(default_factory=list)


class ChunkIndexer:
    """Turns stored papers into retrievable chunks in OpenSearch.

    Every pass rewrites the whole corpus. That is cheap at this size and it is what
    makes the pass idempotent: chunk ids are derived from position, so a rewrite
    overwrites rather than duplicates, and a paper parsed before indexing existed is
    picked up without anyone tracking which papers are new.
    """

    def __init__(self, client: OpenSearch, repository: PaperRepository, alias: str = CHUNK_ALIAS):
        self.client = client
        self.repository = repository
        self.alias = alias

    def index_corpus(self) -> IndexRun:
        ensure_chunk_index(self.client)
        stamp = datetime.now(timezone.utc)
        run = self._index_all_papers(stamp)

        if run.errors:
            logger.warning("Skipping stale-chunk cleanup: %d papers failed to index", len(run.errors))
        else:
            run.stale_chunks_deleted = self._delete_chunks_older_than(stamp)

        logger.info(
            "Indexed %d/%d papers, %d chunks, %d stale chunks removed",
            run.papers_indexed,
            run.papers_seen,
            run.chunks_indexed,
            run.stale_chunks_deleted,
        )
        return run

    def _index_all_papers(self, stamp: datetime) -> IndexRun:
        run = IndexRun()
        for paper in self.repository.list_indexable():
            run.papers_seen += 1
            chunks = chunk_sections(paper.sections)
            if not chunks:
                run.papers_without_chunks += 1
                continue
            result = self._index_paper(paper, chunks, stamp)
            run.chunks_indexed += result.chunks_written
            if result.error:
                run.errors.append(result.error)
            else:
                run.papers_indexed += 1
        return run

    def _index_paper(self, paper: IndexableRow, chunks: List[Chunk], stamp: datetime) -> PaperResult:
        written, failures = bulk(
            self.client,
            list(self._documents(paper, chunks, stamp)),
            raise_on_error=False,
            raise_on_exception=False,
        )
        if failures:
            return PaperResult(written, f"{paper.arxiv_id}: {len(failures)} of {len(chunks)} chunks rejected: {failures[0]}")
        return PaperResult(written, None)

    def _documents(self, paper: IndexableRow, chunks: List[Chunk], stamp: datetime) -> Iterator[Dict[str, Any]]:
        indexed_at = stamp.isoformat()
        published_date = paper.published_date.isoformat()
        for chunk in chunks:
            yield {
                "_index": self.alias,
                "_id": chunk_document_id(paper.arxiv_id, chunk.section_index, chunk.chunk_index),
                "_source": {
                    "arxiv_id": paper.arxiv_id,
                    "title": paper.title,
                    # JSON columns hold whatever the parser and the arXiv API produced;
                    # a nested object here would be rejected by the strict mapping and
                    # cost the paper every one of its chunks.
                    "authors": _strings(paper.authors),
                    "categories": _strings(paper.categories),
                    "published_date": published_date,
                    "section_title": chunk.section_title,
                    "section_index": chunk.section_index,
                    "chunk_index": chunk.chunk_index,
                    "content": chunk.content,
                    "char_count": len(chunk.content),
                    "indexed_at": indexed_at,
                },
            }

    def _delete_chunks_older_than(self, stamp: datetime) -> int:
        """Remove chunks this pass did not rewrite.

        Superseded chunks (the paper was re-parsed into fewer sections) and orphans
        (the paper was purged from the database) both look the same from here: still
        in the index, carrying an older stamp. Only safe after a clean pass, which is
        why the caller checks for errors first — otherwise a paper that failed to
        index would have its previous, good chunks deleted.
        """
        # Refresh first, or the query still sees this run's documents at their previous
        # indexed_at and tries to delete every one of them; each then aborts on a version
        # conflict, and the whole cleanup returns deleted=0. conflicts="proceed" covers
        # the same case for a document a concurrent run rewrites mid-delete: a conflict
        # means the document is current, which is precisely when it must be kept.
        self.client.indices.refresh(index=self.alias)
        response = self.client.delete_by_query(
            index=self.alias,
            body={"query": {"range": {"indexed_at": {"lt": stamp.isoformat()}}}},
            conflicts="proceed",
            refresh=True,
        )
        return int(response.get("deleted", 0))


def _strings(value: Any) -> List[str]:
    """The string entries of a JSON list column, dropping anything else."""
    if not isinstance(value, (list, tuple)):
        return []
    return [item for item in value if isinstance(item, str)]
