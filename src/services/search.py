"""BM25 search over the paper and passage indices."""

import logging
from typing import Any, Dict, List, Optional, Sequence, Tuple

from opensearchpy import OpenSearch
from opensearchpy.exceptions import NotFoundError
from src.schemas.api.search import ChunkHit, ChunkSearchResponse, SearchHit, SearchResponse
from src.search.query import CHUNK_PROFILE, PAPER_PROFILE, QueryProfile, SearchQuery

logger = logging.getLogger(__name__)


class SearchService:
    """Runs queries against the search indices and shapes the responses.

    Deliberately does no health check before searching: it would double the latency
    of every request to learn what a failed search reports anyway.
    """

    def __init__(self, client: OpenSearch):
        self.client = client

    def search_papers(
        self,
        query: str,
        *,
        size: int = 10,
        offset: int = 0,
        categories: Optional[Sequence[str]] = None,
        newest_first: bool = False,
    ) -> SearchResponse:
        """Find papers about the query, ranked by BM25 over title, abstract, and authors."""
        total, hits, took_ms = self._run(
            PAPER_PROFILE, query, size=size, offset=offset, categories=categories, newest_first=newest_first
        )
        return SearchResponse(query=query, total=total, took_ms=took_ms, hits=[_paper_hit(hit) for hit in hits])

    def search_chunks(
        self,
        query: str,
        *,
        size: int = 10,
        offset: int = 0,
        categories: Optional[Sequence[str]] = None,
    ) -> ChunkSearchResponse:
        """Find the passages that say something about the query, not the papers that mention it."""
        total, hits, took_ms = self._run(CHUNK_PROFILE, query, size=size, offset=offset, categories=categories)
        return ChunkSearchResponse(query=query, total=total, took_ms=took_ms, hits=[_chunk_hit(hit) for hit in hits])

    def _run(
        self,
        profile: QueryProfile,
        query: str,
        *,
        size: int,
        offset: int,
        categories: Optional[Sequence[str]],
        newest_first: bool = False,
    ) -> Tuple[int, List[Dict[str, Any]], int]:
        body = SearchQuery(
            profile, query, size=size, offset=offset, categories=categories, newest_first=newest_first
        ).build()
        try:
            response = self.client.search(index=profile.alias, body=body)
        except NotFoundError:
            # Expected on a stack that has never run the ingestion DAG. An empty result
            # is the honest answer; anything else here is a real fault and propagates.
            logger.warning("Search index %s does not exist yet", profile.alias)
            return 0, [], 0
        return response["hits"]["total"]["value"], response["hits"]["hits"], response["took"]


def _paper_hit(hit: Dict[str, Any]) -> SearchHit:
    source = hit["_source"]
    return SearchHit(
        arxiv_id=source["arxiv_id"],
        title=source["title"],
        authors=source["authors"],
        abstract=source["abstract"],
        categories=source["categories"],
        published_date=source.get("published_date"),
        pdf_url=source.get("pdf_url"),
        score=_score(hit),
        highlights=_highlights(hit),
    )


def _chunk_hit(hit: Dict[str, Any]) -> ChunkHit:
    source = hit["_source"]
    return ChunkHit(
        arxiv_id=source["arxiv_id"],
        title=source["title"],
        section_title=source["section_title"],
        section_index=source["section_index"],
        chunk_index=source["chunk_index"],
        content=source["content"],
        categories=source["categories"],
        published_date=source.get("published_date"),
        score=_score(hit),
        highlights=_highlights(hit),
    )


def _score(hit: Dict[str, Any]) -> float:
    """A date-sorted search returns null scores; the field stays a float so a client
    never has to branch on the sort order to read it."""
    return float(hit.get("_score") or 0.0)


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
