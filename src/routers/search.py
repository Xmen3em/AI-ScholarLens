"""BM25 paper search."""

import logging

from fastapi import APIRouter, HTTPException
from opensearchpy.exceptions import OpenSearchException
from src.dependencies import PaperSearchDep
from src.schemas.api.search import SearchRequest, SearchResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/search", tags=["search"])


@router.post("/", response_model=SearchResponse)
def search_papers(request: SearchRequest, paper_search: PaperSearchDep) -> SearchResponse:
    """Search papers by relevance, scored with BM25.

    Matches are scored across the title (3x), the abstract (2x), and the authors (1x),
    so a paper whose *title* is about the query outranks one that merely mentions it.
    An empty query browses instead: filters and the newest-first sort still apply.
    """
    try:
        return paper_search.search(
            request.query,
            size=request.size,
            offset=request.offset,
            categories=request.categories,
            newest_first=request.newest_first,
        )
    # Only the search backend being unreachable or refusing the query. Anything else
    # is a defect here, and turning it into a 500 with a message would hide it.
    except OpenSearchException as e:
        logger.error("Search backend failed for %r: %s", request.query, e)
        raise HTTPException(status_code=503, detail="Search is unavailable") from e
