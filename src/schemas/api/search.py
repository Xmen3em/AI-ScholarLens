from typing import Dict, List, Optional

from pydantic import BaseModel, Field, field_validator
from src.policies.ai_scope import AI_CATEGORY_ALLOWLIST


class SearchRequest(BaseModel):
    """A BM25 search over the paper index."""

    # Empty is allowed and means "browse": the filters and the newest-first sort still
    # apply, which is how "the latest cs.CL papers" is asked for.
    query: str = Field(default="", max_length=500, description="Text to search for in titles, abstracts, and authors")
    size: int = Field(default=10, ge=1, le=50, description="Number of results to return")
    offset: int = Field(default=0, ge=0, le=1000, description="Results to skip, for pagination")
    categories: Optional[List[str]] = Field(default=None, description="Restrict to these arXiv categories")
    newest_first: bool = Field(default=False, description="Sort by publication date instead of relevance")

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


class SearchResponse(BaseModel):
    """Search results, with the total available behind them."""

    query: str
    total: int = Field(..., description="Papers matching the query, not the number returned")
    hits: List[SearchHit]
    took_ms: int = Field(..., description="Time OpenSearch spent on the query")
