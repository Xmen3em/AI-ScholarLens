"""Validated contracts for Ollama's external API responses."""

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict


class OllamaModel(BaseModel):
    """The stable fields used from one `/api/tags` model entry."""

    model_config = ConfigDict(extra="ignore", strict=True)

    name: Optional[str] = None
    model: Optional[str] = None


class OllamaTagsResponse(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)

    models: list[OllamaModel]


class OllamaGenerateResponse(BaseModel):
    """One normal response or one item from the NDJSON stream."""

    model_config = ConfigDict(extra="ignore", strict=True)

    model: str
    response: str
    done: bool
    done_reason: Optional[str] = None
    total_duration: Optional[int] = None
    load_duration: Optional[int] = None
    prompt_eval_count: Optional[int] = None
    prompt_eval_duration: Optional[int] = None
    eval_count: Optional[int] = None
    eval_duration: Optional[int] = None


class OllamaReadiness(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["healthy", "degraded", "unhealthy"]
    installed: list[str]
    missing_required: list[str]
    missing_optional: list[str]
