"""Search over the paper and passage indices: keyword, vector, and the two fused."""

import logging
from typing import Any, Dict, List, Optional, Sequence, Tuple

from opensearchpy import OpenSearch
from opensearchpy.exceptions import NotFoundError
from src.exceptions import OllamaException
from src.schemas.api.search import (
    ChunkSearchResponse,
    HybridSearchResponse,
    PaperPassages,
    PassageHit,
    SearchHit,
    SearchResponse,
)
from src.search.fusion import fused_scores, reciprocal_rank_fusion
from src.search.query import (
    CHUNK_CANDIDATE_PROFILE,
    CHUNK_PROFILE,
    MAX_PASSAGES_PER_PAPER,
    PAPER_PROFILE,
    QueryProfile,
    SearchQuery,
    vector_query,
)
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
        """Find the passages that say something about the query, not the papers that mention it.

        ``size`` counts papers: OpenSearch collapses the hits by paper and returns each
        one's best passages, so a paper matching two hundred times cannot fill the page.
        """
        total, hits, took_ms = self._run(CHUNK_PROFILE, query, size=size, offset=offset, categories=categories)
        return ChunkSearchResponse(query=query, total=total, took_ms=took_ms, hits=[_collapsed_group(hit) for hit in hits])

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
        keyword = self._execute(
            CHUNK_PROFILE.alias, SearchQuery(CHUNK_CANDIDATE_PROFILE, query, size=depth, categories=categories).build()
        )
        # The real match count, not the size of the candidate pool. Reporting the pool
        # made `total` cap out at the retrieval depth -- a query matching 172 passages
        # reported 80, which is the one number a caller cannot sanity-check for itself.
        matches = keyword["hits"]["total"]["value"]

        try:
            vector = self.embedder.embed_query(query)
        except OllamaException as e:
            logger.warning("Falling back to keyword search: %s", e)
            found = keyword["hits"]["hits"]
            grouped = _group_by_paper([hit["_id"] for hit in found], {hit["_id"]: hit for hit in found})
            return HybridSearchResponse(
                query=query,
                total=matches,
                took_ms=keyword["took"],
                hits=grouped[offset : offset + size],
                mode="keyword",
                # BM25, not RRF: nothing was fused, so the scores are the keyword
                # half's own and are on a completely different scale.
                score_kind="bm25",
                fallback_reason=str(e),
            )

        semantic = self._execute(CHUNK_PROFILE.alias, vector_query(CHUNK_PROFILE, vector, size=depth, categories=categories))
        return self._fuse(
            query,
            keyword["hits"]["hits"],
            semantic["hits"]["hits"],
            size=size,
            offset=offset,
            total=matches,
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
        total: int,
        took_ms: int,
    ) -> HybridSearchResponse:
        by_id = {hit["_id"]: hit for hit in [*semantic, *keyword]}
        rankings = [[hit["_id"] for hit in keyword], [hit["_id"] for hit in semantic]]
        order = reciprocal_rank_fusion(rankings)
        # The fused score, not BM25: rank positions are all RRF sees, so the two scales
        # never have to be reconciled. Values sit near 1/RRF_K.
        grouped = _group_by_paper(order, by_id, scores=fused_scores(rankings))
        hits = grouped[offset : offset + size]

        return HybridSearchResponse(
            query=query,
            total=total,
            took_ms=took_ms,
            hits=hits,
            mode="hybrid",
            score_kind="rrf",
            fallback_reason=None,
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


def _collapsed_group(hit: Dict[str, Any]) -> PaperPassages:
    """One paper and its passages, from a collapsed hit and its inner hits."""
    source = hit["_source"]
    inner = hit["inner_hits"]["passages"]["hits"]
    return PaperPassages(
        arxiv_id=source["arxiv_id"],
        title=source["title"],
        categories=source["categories"],
        published_date=source.get("published_date"),
        score=_score(hit),
        matching_passages=inner["total"]["value"],
        passages=[_passage(passage) for passage in inner["hits"]],
    )


def _group_by_paper(
    order: Sequence[str], by_id: Dict[str, Dict[str, Any]], scores: Optional[Dict[str, float]] = None
) -> List[PaperPassages]:
    """Group an already-ranked list of passages into papers, capped, keeping the order.

    A paper takes the position of its best passage, so the ranking survives the grouping.
    Dict insertion order does the work: the first passage seen for a paper is its best.

    ``matching_passages`` is left unset, unlike the collapsed path — this only ever sees
    a bounded candidate pool, so a count from it would understate the truth.
    """
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for document_id in order:
        passages = grouped.setdefault(by_id[document_id]["_source"]["arxiv_id"], [])
        if len(passages) < MAX_PASSAGES_PER_PAPER:
            passages.append(by_id[document_id])

    papers = []
    for arxiv_id, hits in grouped.items():
        source = hits[0]["_source"]
        papers.append(
            PaperPassages(
                arxiv_id=arxiv_id,
                title=source["title"],
                categories=source["categories"],
                published_date=source.get("published_date"),
                score=_ranked_score(hits[0], scores),
                passages=[_passage(hit, scores) for hit in hits],
            )
        )
    return papers


def _passage(hit: Dict[str, Any], scores: Optional[Dict[str, float]] = None) -> PassageHit:
    source = hit["_source"]
    return PassageHit(
        section_title=source["section_title"],
        section_index=source["section_index"],
        chunk_index=source["chunk_index"],
        content=source["content"],
        score=_ranked_score(hit, scores),
        highlights=_highlights(hit),
    )


def _ranked_score(hit: Dict[str, Any], scores: Optional[Dict[str, float]]) -> float:
    """The fused score when fusing, otherwise the backend's own."""
    if scores is None:
        return _score(hit)
    return scores[hit["_id"]]


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
