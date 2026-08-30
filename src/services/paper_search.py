"""BM25 search over the paper index."""

import logging
from typing import Any, Dict, List, Optional, Sequence

from opensearchpy import OpenSearch
from opensearchpy.exceptions import NotFoundError
from src.schemas.api.search import SearchHit, SearchResponse
from src.search.indices import PAPER_ALIAS
from src.search.query import PaperQuery

logger = logging.getLogger(__name__)


class PaperSearchService:
    """Runs paper queries and shapes the response.

    Deliberately does no health check before searching: it would double the latency
    of every request to learn what a failed search reports anyway.
    """

    def __init__(self, client: OpenSearch, alias: str = PAPER_ALIAS):
        self.client = client
        self.alias = alias

    def search(
        self,
        query: str,
        *,
        size: int = 10,
        offset: int = 0,
        categories: Optional[Sequence[str]] = None,
        newest_first: bool = False,
    ) -> SearchResponse:
        body = PaperQuery(query, size=size, offset=offset, categories=categories, newest_first=newest_first).build()
        try:
            response = self.client.search(index=self.alias, body=body)
        except NotFoundError:
            # Expected on a stack that has never run the ingestion DAG. An empty result
            # is the honest answer; anything else here is a real fault and propagates.
            logger.warning("Search index %s does not exist yet", self.alias)
            return SearchResponse(query=query, total=0, hits=[], took_ms=0)

        return SearchResponse(
            query=query,
            total=response["hits"]["total"]["value"],
            hits=[_to_hit(hit) for hit in response["hits"]["hits"]],
            took_ms=response["took"],
        )


def _to_hit(hit: Dict[str, Any]) -> SearchHit:
    source = hit["_source"]
    return SearchHit(
        arxiv_id=source["arxiv_id"],
        title=source["title"],
        authors=source["authors"],
        abstract=source["abstract"],
        categories=source["categories"],
        published_date=source.get("published_date"),
        pdf_url=source.get("pdf_url"),
        # A date-sorted search returns null scores; the field stays a float so a client
        # never has to branch on the sort order to read it.
        score=hit.get("_score") or 0.0,
        highlights=_highlights(hit),
    )


def _highlights(hit: Dict[str, Any]) -> Dict[str, List[str]]:
    """Matched fragments, dropped unless every entry is the list of strings the schema promises."""
    highlight = hit.get("highlight")
    if not isinstance(highlight, dict):
        return {}
    return {
        field: fragments
        for field, fragments in highlight.items()
        if isinstance(fragments, list) and all(isinstance(fragment, str) for fragment in fragments)
    }
