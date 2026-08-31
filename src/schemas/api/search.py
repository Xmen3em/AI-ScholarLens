from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator
from src.policies.ai_scope import AI_CATEGORY_ALLOWLIST


class BaseSearchRequest(BaseModel):
    """The paging and filtering every search shares."""

    size: int = Field(default=10, ge=1, le=50, description="Number of results to return")
    # Capped because OpenSearch refuses offset + size past index.max_result_window,
    # which defaults to 10,000; a 422 beats a 500 from the backend.
    offset: int = Field(default=0, ge=0, le=1000, description="Results to skip, for pagination")
    categories: Optional[List[str]] = Field(default=None, description="Restrict to these arXiv categories")

    @field_validator("categories")
    @classmethod
    def categories_must_be_in_scope(cls, value: Optional[List[str]]) -> Optional[List[str]]:
        """Reject categories the corpus never ingests.

        Filtering on `hep-th` can only ever return nothing, and a silent empty result
        reads as "no papers match" rather than "that filter was never going to work".
        """
        if value is None:
            return value
        unknown = sorted(set(value) - AI_CATEGORY_ALLOWLIST)
        if unknown:
            raise ValueError(f"outside the ingested AI scope: {', '.join(unknown)}")
        return value


class SearchRequest(BaseSearchRequest):
    """A BM25 search over whole papers."""

    # Empty is allowed and means "browse": the filters and the newest-first sort still
    # apply, which is how "the latest cs.CL papers" is asked for.
    query: str = Field(default="", max_length=500, description="Text to search for in titles, abstracts, and authors")
    newest_first: bool = Field(default=False, description="Sort by publication date instead of relevance")


class ChunkSearchRequest(BaseSearchRequest):
    """A BM25 search over passages.

    Requires a query. Browsing passages by date has no use: a passage is only
    meaningful as an answer to something.
    """

    query: str = Field(..., min_length=1, max_length=500, description="Text to search for inside paper sections")

    size: int = Field(default=10, ge=1, le=50, description="Number of papers to return, not passages")


class HybridSearchRequest(ChunkSearchRequest):
    """A hybrid search over passages: BM25 and vector similarity, fused."""


class SearchHit(BaseModel):
    """One paper that matched, with the fragments that made it match."""

    arxiv_id: str
    title: str
    authors: str
    abstract: str
    categories: List[str]
    published_date: Optional[str] = None
    pdf_url: Optional[str] = None
    score: float = Field(..., description="BM25 relevance score")
    highlights: Dict[str, List[str]] = Field(default_factory=dict, description="Matched fragments, marked with <mark>")


class PassageHit(BaseModel):
    """One passage that matched, positioned within its paper."""

    section_title: str
    section_index: int
    chunk_index: int
    content: str
    score: float = Field(..., description="Relevance score of this passage; see the response's score_kind")
    highlights: Dict[str, List[str]] = Field(default_factory=dict, description="Matched fragments, marked with <mark>")


class PaperPassages(BaseModel):
    """One paper, with its best matching passages.

    Results are grouped rather than flat so that a strong paper cannot crowd out every
    other source. Capped at three passages a paper: enough to carry a claim and its
    evidence, few enough that ten results still span several papers.
    """

    arxiv_id: str
    title: str
    categories: List[str]
    published_date: Optional[str] = None
    score: float = Field(..., description="Score of this paper's best passage, which is what ranks the paper")
    matching_passages: Optional[int] = Field(
        default=None,
        description=(
            "How many passages in this paper matched, which may exceed the number returned. "
            "Absent from hybrid results, where fusion sees only a bounded candidate pool."
        ),
    )
    passages: List[PassageHit]


class SearchResponse(BaseModel):
    """Matching papers, with the total available behind them."""

    query: str
    total: int = Field(..., description="Papers matching the query, not the number returned")
    hits: List[SearchHit]
    took_ms: int = Field(..., description="Time OpenSearch spent on the query")


class ChunkSearchResponse(BaseModel):
    """Matching passages, grouped by the paper they came from."""

    query: str
    total: int = Field(..., description="Passages matching the query, across every paper")
    hits: List[PaperPassages] = Field(..., description="Papers, best first, each with up to three passages")
    took_ms: int = Field(..., description="Time OpenSearch spent on the query")


class HybridSearchResponse(ChunkSearchResponse):
    """Fused passages, plus which ranking actually produced them."""

    total: int = Field(
        ...,
        description=(
            "Passages matching the keyword half. Fusion reranks a bounded pool of candidates "
            "from each half, so offset cannot reach every one of them."
        ),
    )
    score_kind: Literal["rrf", "bm25"] = Field(
        ..., description="'rrf' for a fused score near 1/60; 'bm25' when mode is 'keyword'"
    )
    mode: Literal["hybrid", "keyword"] = Field(
        ..., description="'keyword' when the embedding model was unreachable and the search fell back to BM25"
    )
    fallback_reason: Optional[str] = Field(
        default=None, description="Why the vector half was skipped, when mode is 'keyword'"
    )
