"""BM25 search over papers and over the passages inside them."""

from fastapi import APIRouter
from src.dependencies import SearchDep
from src.schemas.api.search import (
    ChunkSearchRequest,
    ChunkSearchResponse,
    HybridSearchRequest,
    HybridSearchResponse,
    SearchRequest,
    SearchResponse,
)

router = APIRouter(prefix="/search", tags=["search"])


@router.post("/", response_model=SearchResponse)
def search_papers(request: SearchRequest, search: SearchDep) -> SearchResponse:
    """Find papers about the query, scored with BM25.

    Matches are scored across the title (3x), the abstract (2x), and the authors (1x),
    so a paper whose *title* is about the query outranks one that merely mentions it.
    An empty query browses instead: filters and the newest-first sort still apply.
    """
    return search.search_papers(
        request.query,
        size=request.size,
        offset=request.offset,
        categories=request.categories,
        newest_first=request.newest_first,
    )


@router.post("/chunks", response_model=ChunkSearchResponse)
def search_chunks(request: ChunkSearchRequest, search: SearchDep) -> ChunkSearchResponse:
    """Find the passages that answer the query, rather than the papers that mention it.

    Scored over the passage text (3x) and its section heading (2x). The paper title is
    deliberately not scored: every passage of a paper carries the same one, so boosting
    it returns forty pieces of a single paper instead of the best passage from each.
    """
    return search.search_chunks(
        request.query,
        size=request.size,
        offset=request.offset,
        categories=request.categories,
    )


@router.post("/hybrid", response_model=HybridSearchResponse)
def search_hybrid(request: HybridSearchRequest, search: SearchDep) -> HybridSearchResponse:
    """Find passages by meaning and by wording at once.

    Runs the BM25 passage query and a vector similarity query over the same index,
    then fuses them with reciprocal rank fusion — only the rank positions are used, so
    BM25 scores and cosine similarities never have to be put on one scale.

    Falls back to keyword-only if the embedding model is unreachable, and says so in
    `mode`. Worse results beat no results, and the keyword half is complete on its own.

    `score` therefore lives on two different scales, and `score_kind` says which: `rrf`
    for a fused score near 1/60, or `bm25` for the keyword half's own score, in the
    tens. `total` counts the passages matching the keyword query; fusion only reranks a
    bounded pool of candidates, so `offset` cannot walk all the way through them.
    """
    return search.search_hybrid(
        request.query,
        size=request.size,
        offset=request.offset,
        categories=request.categories,
    )
