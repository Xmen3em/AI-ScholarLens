"""Public request and response contracts for grounded answers."""

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator
from src.policies.ai_scope import AI_CATEGORY_ALLOWLIST


class AskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(..., min_length=1, max_length=500)
    top_k: int = Field(default=3, ge=1, le=10, description="Number of paper groups to retrieve")
    use_hybrid: bool = True
    model: Optional[str] = None
    categories: Optional[list[str]] = None

    @field_validator("query")
    @classmethod
    def query_must_contain_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("query must contain text")
        return value

    @field_validator("categories")
    @classmethod
    def categories_must_be_in_scope(cls, value: Optional[list[str]]) -> Optional[list[str]]:
        if value is None:
            return value
        unknown = sorted(set(value) - AI_CATEGORY_ALLOWLIST)
        if unknown:
            raise ValueError(f"outside the ingested AI scope: {', '.join(unknown)}")
        return value


class Citation(BaseModel):
    marker: str
    arxiv_id: str
    title: str
    section_title: str
    section_index: int
    chunk_index: int
    evidence: str


class AskResponse(BaseModel):
    query: str
    answer: str
    sources: list[str]
    citations: list[Citation]
    chunks_used: int
    search_mode: Literal["hybrid", "bm25"]
    model: str


class SourcesEvent(BaseModel):
    query: str
    sources: list[str]
    citations: list[Citation]
    chunks_used: int
    search_mode: Literal["hybrid", "bm25"]
    model: str


class DeltaEvent(BaseModel):
    delta: str


class DoneEvent(BaseModel):
    answer: str


class ErrorEvent(BaseModel):
    error: str


class GeneratedAnswer(BaseModel):
    """Internal evidence selection; public answer text is rendered by the server."""

    model_config = ConfigDict(extra="forbid", strict=True)
    answer: list[str] = Field(..., max_length=3)
