"""BM25 search over papers and over the passages inside them."""

from fastapi import APIRouter
from src.dependencies import SearchDep
from src.schemas.api.search import ChunkSearchRequest, ChunkSearchResponse, SearchRequest, SearchResponse

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
