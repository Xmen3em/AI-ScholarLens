"""Writing stored papers into the OpenSearch paper index, one document per paper."""

from datetime import datetime
from typing import Any, Dict, List, Sequence

from opensearchpy import OpenSearch
from src.repositories.paper import PaperRepository, SearchableRow
from src.search.indices import PAPER_ALIAS, PAPER_INDEX, ensure_paper_index
from src.services.reindex import CorpusReindexer, strings


class PaperIndexer(CorpusReindexer):
    """Turns stored papers into searchable paper documents in OpenSearch.

    Every paper is indexed, parsed or not: title, abstract, authors, and categories
    all come from the arXiv metadata, so a paper whose PDF was too large to parse is
    still findable — it just has no passages in the chunk index.
    """

    def __init__(self, client: OpenSearch, repository: PaperRepository, index: str = PAPER_INDEX, alias: str = PAPER_ALIAS):
        super().__init__(client, index, alias)
        self.repository = repository

    def ensure_index(self) -> None:
        ensure_paper_index(self.client)

    def papers(self) -> Sequence[SearchableRow]:
        return self.repository.list_searchable()

    def documents(self, paper: SearchableRow, stamp: datetime) -> List[Dict[str, Any]]:
        return [
            {
                "_index": self.index,
                "_id": paper.arxiv_id,
                "_source": {
                    "arxiv_id": paper.arxiv_id,
                    "title": paper.title,
                    # Joined rather than kept as a list: the field is analyzed text so a
                    # query can match one name out of thirty, and a highlight over a
                    # joined string returns something a result card can print.
                    "authors": ", ".join(strings(paper.authors)),
                    "abstract": paper.abstract,
                    "categories": strings(paper.categories),
                    "published_date": paper.published_date.isoformat(),
                    "pdf_url": paper.pdf_url,
                    "indexed_at": stamp.isoformat(),
                },
            }
        ]
