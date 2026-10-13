"""Provider-neutral result with a narrow projection to retained RAG callers."""

from typing import Any, Mapping, Protocol

from pydantic import BaseModel, ConfigDict, Field
from src.schemas.ollama import OllamaGenerateResponse


class GenerationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    model: str
    content: str = Field(min_length=1, max_length=8192)
    elapsed_ms: float = Field(ge=0, allow_inf_nan=False)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    reasoning_tokens: int | None = Field(default=None, ge=0)

    def as_legacy_response(self) -> OllamaGenerateResponse:
        return OllamaGenerateResponse(model=self.model, response=self.content, done=True,
                                      done_reason="stop", prompt_eval_count=self.input_tokens,
                                      eval_count=self.output_tokens)


class GenerationPort(Protocol):
    """Retained caller shape; provider durations remain optional, never invented."""

    async def generate(
        self, model: str, prompt: str, *, system: str | None = None,
        response_format: Mapping[str, Any] | str | None = None,
        options: Mapping[str, Any] | None = None,
    ) -> OllamaGenerateResponse: ...
