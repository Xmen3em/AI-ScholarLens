"""Search over the paper and passage indices: keyword, vector, and the two fused."""

import logging
from typing import Any, Dict, List, Optional, Sequence, Tuple

from opensearchpy import OpenSearch
from opensearchpy.exceptions import NotFoundError
from src.exceptions import OllamaException
from src.schemas.api.search import ChunkHit, ChunkSearchResponse, HybridSearchResponse, SearchHit, SearchResponse
from src.search.fusion import fused_scores, reciprocal_rank_fusion
from src.search.query import CHUNK_PROFILE, PAPER_PROFILE, QueryProfile, SearchQuery, vector_query
from src.services.embeddings.ollama import OllamaEmbedder

logger = logging.getLogger(__name__)

# How far past the requested page each half retrieves before fusing. Fusion can only
# reorder what it is given, so a document ranked 8th by one half and 40th by the other
# is invisible unless both lists run deeper than the page being served.
CANDIDATE_DEPTH = 5

# ...and a floor, because the multiplier alone collapses on small pages. At size=3 it
# asked each half for 15 candidates, the two lists did not overlap at all, and every
# fused score came out at exactly 1/(RRF_K + 1) — an expensive way to reproduce the
# keyword ranking. Fusion needs a pool wide enough for the halves to agree inside.
MIN_CANDIDATES = 50


class SearchService:
    """Runs queries against the search indices and shapes the responses.

    Deliberately does no health check before searching: it would double the latency
    of every request to learn what a failed search reports anyway.
    """

    def __init__(self, client: OpenSearch, embedder: OllamaEmbedder):
        self.client = client
        self.embedder = embedder

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

    def search_hybrid(
        self,
        query: str,
        *,
        size: int = 10,
        offset: int = 0,
        categories: Optional[Sequence[str]] = None,
    ) -> HybridSearchResponse:
        """Find passages by meaning and by wording at once, fused with reciprocal rank.

        Falls back to keyword-only when the embedding model is unreachable. Degrading
        to worse results beats returning none: the keyword half is complete on its own,
        and the response says which ranking produced it.
        """
        depth = max((offset + size) * CANDIDATE_DEPTH, MIN_CANDIDATES)
        keyword = self._execute(CHUNK_PROFILE.alias, SearchQuery(CHUNK_PROFILE, query, size=depth, categories=categories).build())

        try:
            vector = self.embedder.embed_query(query)
        except OllamaException as e:
            logger.warning("Falling back to keyword search: %s", e)
            found = keyword["hits"]["hits"]
            return HybridSearchResponse(
                query=query,
                total=len(found),
                took_ms=keyword["took"],
                hits=[_chunk_hit(hit) for hit in found[offset : offset + size]],
                mode="keyword",
                fallback_reason=str(e),
            )

        semantic = self._execute(CHUNK_PROFILE.alias, vector_query(CHUNK_PROFILE, vector, size=depth, categories=categories))
        return self._fuse(
            query,
            keyword["hits"]["hits"],
            semantic["hits"]["hits"],
            size=size,
            offset=offset,
            took_ms=keyword["took"] + semantic["took"],
        )

    def _fuse(
        self,
        query: str,
        keyword: List[Dict[str, Any]],
        semantic: List[Dict[str, Any]],
        *,
        size: int,
        offset: int,
        took_ms: int,
    ) -> HybridSearchResponse:
        by_id = {hit["_id"]: hit for hit in [*semantic, *keyword]}
        rankings = [[hit["_id"] for hit in keyword], [hit["_id"] for hit in semantic]]
        order = reciprocal_rank_fusion(rankings)
        scores = fused_scores(rankings)

        hits = []
        for document_id in order[offset : offset + size]:
            hit = _chunk_hit(by_id[document_id])
            # The fused score, not BM25: rank positions are all RRF sees, so the two
            # scales never have to be reconciled. Values sit near 1/RRF_K.
            hit.score = scores[document_id]
            hits.append(hit)

        return HybridSearchResponse(
            query=query, total=len(order), took_ms=took_ms, hits=hits, mode="hybrid", fallback_reason=None
        )

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
        response = self._execute(profile.alias, body)
        return response["hits"]["total"]["value"], response["hits"]["hits"], response["took"]

    def _execute(self, alias: str, body: Dict[str, Any]) -> Dict[str, Any]:
        """Run a prepared query body, treating a missing index as an empty result.

        A missing index is expected on a stack that has never run the ingestion DAG.
        Anything else is a real fault and propagates to the 503 handler.
        """
        try:
            return self.client.search(index=alias, body=body)
        except NotFoundError:
            logger.warning("Search index %s does not exist yet", alias)
            return {"took": 0, "hits": {"total": {"value": 0}, "hits": []}}


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
