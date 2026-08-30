"""The shape every search index is rebuilt with.

Both indices are rewritten the same way, and the way is subtle enough that a second
copy would drift: the stale-document cleanup has to refresh first, has to tolerate
version conflicts, and has to be skipped entirely when anything failed. A fix to any
of those belongs in one place.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, NamedTuple, Optional, Sequence

from opensearchpy import OpenSearch
from opensearchpy.helpers import bulk

logger = logging.getLogger(__name__)


class SourceResult(NamedTuple):
    """What one paper's bulk write achieved."""

    documents_written: int
    error: Optional[str]


@dataclass
class IndexRun:
    """What one pass over the corpus did, for the daily report."""

    papers_seen: int = 0
    papers_indexed: int = 0
    papers_without_documents: int = 0
    documents_indexed: int = 0
    stale_documents_deleted: int = 0
    errors: List[str] = field(default_factory=list)


class CorpusReindexer(ABC):
    """A full, idempotent rewrite of one search index from the papers table.

    Every pass rewrites the whole corpus rather than just what changed. That is cheap
    at this size and it is what makes the pass self-healing: document ids are derived
    from the paper, so a rewrite overwrites rather than duplicates, a run that failed
    halfway is repaired by the next one, and a paper stored before this index existed
    is picked up without anyone tracking which papers are new.
    """

    def __init__(self, client: OpenSearch, alias: str):
        self.client = client
        self.alias = alias

    def index_corpus(self) -> IndexRun:
        self.ensure_index()
        stamp = datetime.now(timezone.utc)
        run = self._index_all_papers(stamp)

        if run.errors:
            logger.warning("Skipping stale-document cleanup: %d papers failed to index", len(run.errors))
        else:
            run.stale_documents_deleted = self._delete_documents_older_than(stamp)

        logger.info(
            "%s: indexed %d/%d papers, %d documents, %d stale removed",
            self.alias,
            run.papers_indexed,
            run.papers_seen,
            run.documents_indexed,
            run.stale_documents_deleted,
        )
        return run

    @abstractmethod
    def ensure_index(self) -> None:
        """Create this index and its alias if they are not already there."""

    @abstractmethod
    def papers(self) -> Sequence[Any]:
        """The rows to index. Each must carry an ``arxiv_id``."""

    @abstractmethod
    def documents(self, paper: Any, stamp: datetime) -> List[Dict[str, Any]]:
        """The bulk actions for one paper, empty when it has nothing to index."""

    def _index_all_papers(self, stamp: datetime) -> IndexRun:
        run = IndexRun()
        for paper in self.papers():
            run.papers_seen += 1
            documents = self.documents(paper, stamp)
            if not documents:
                run.papers_without_documents += 1
                continue
            result = self._index_paper(paper.arxiv_id, documents)
            run.documents_indexed += result.documents_written
            if result.error:
                run.errors.append(result.error)
            else:
                run.papers_indexed += 1
        return run

    def _index_paper(self, arxiv_id: str, documents: List[Dict[str, Any]]) -> SourceResult:
        written, failures = bulk(self.client, documents, raise_on_error=False, raise_on_exception=False)
        if failures:
            return SourceResult(written, f"{arxiv_id}: {len(failures)} of {len(documents)} documents rejected: {failures[0]}")
        return SourceResult(written, None)

    def _delete_documents_older_than(self, stamp: datetime) -> int:
        """Remove documents this pass did not rewrite.

        Superseded documents (the paper was re-parsed into fewer sections) and orphans
        (the paper was purged from the database) both look the same from here: still in
        the index, carrying an older stamp. Only safe after a clean pass, which is why
        the caller checks for errors first — otherwise a paper that failed to index
        would have its previous, good documents deleted.

        Refresh first, or the query still sees this run's documents at their previous
        indexed_at and tries to delete every one of them; each then aborts on a version
        conflict, and the whole cleanup returns deleted=0. conflicts="proceed" covers
        the same case for a document a concurrent run rewrites mid-delete: a conflict
        means the document is current, which is precisely when it must be kept.
        """
        self.client.indices.refresh(index=self.alias)
        response = self.client.delete_by_query(
            index=self.alias,
            body={"query": {"range": {"indexed_at": {"lt": stamp.isoformat()}}}},
            conflicts="proceed",
            refresh=True,
        )
        return int(response.get("deleted", 0))


def strings(value: Any) -> List[str]:
    """The string entries of a JSON list column, dropping anything else.

    papers.authors and papers.categories hold whatever the arXiv API produced; a
    nested object reaching a strict mapping costs the paper every one of its documents.
    """
    if not isinstance(value, (list, tuple)):
        return []
    return [item for item in value if isinstance(item, str)]
