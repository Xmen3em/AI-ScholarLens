"""Grounded retrieval-augmented generation over grouped paper passages."""

import logging
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Literal

import anyio
from pydantic import ValidationError
from src.config import Settings
from src.exceptions import GroundingError, OllamaResponseError, UnsupportedModelError
from src.schemas.api.rag import AskRequest, AskResponse, GeneratedAnswer, SourcesEvent
from src.schemas.api.search import ChunkSearchResponse, HybridSearchResponse
from src.schemas.ollama import OllamaGenerateResponse
from src.services.ollama.client import OllamaClient
from src.services.rag.context import RAGContext, build_context, validate_answer_citations
from src.services.search import SearchService

logger = logging.getLogger(__name__)

EVIDENCE_CHARACTER_BUDGET = 12_000
GENERATION_OPTIONS = {"temperature": 0, "num_predict": 512, "num_ctx": 8192}
INSUFFICIENT_EVIDENCE_ANSWER = "The retrieved evidence is insufficient to answer this question."
SYSTEM_PROMPT_PATH = Path(__file__).parents[1] / "ollama" / "prompts" / "rag_system.txt"


@dataclass(frozen=True)
class PreparedRAG:
    request: AskRequest
    context: RAGContext
    search_mode: Literal["hybrid", "bm25"]
    model: str

    def sources_event(self) -> SourcesEvent:
        return SourcesEvent(
            query=self.request.query,
            sources=self.context.sources,
            citations=self.context.citations,
            chunks_used=len(self.context.citations),
            search_mode=self.search_mode,
            model=self.model,
        )


class RAGService:
    def __init__(self, search: SearchService, ollama: OllamaClient, settings: Settings):
        self.search = search
        self.ollama = ollama
        self.settings = settings
        self.system_prompt = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8").strip()

    async def prepare(self, request: AskRequest) -> PreparedRAG:
        model = self._model_for(request)
        started = time.perf_counter()
        search_call: Callable[[], ChunkSearchResponse | HybridSearchResponse]
        if request.use_hybrid:
            search_call = partial(
                self.search.search_hybrid,
                request.query,
                size=request.top_k,
                offset=0,
                categories=request.categories,
            )
        else:
            search_call = partial(
                self.search.search_chunks,
                request.query,
                size=request.top_k,
                offset=0,
                categories=request.categories,
            )
        result = await anyio.to_thread.run_sync(search_call)
        elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
        mode: Literal["hybrid", "bm25"] = (
            "hybrid" if isinstance(result, HybridSearchResponse) and result.mode == "hybrid" else "bm25"
        )
        logger.info(
            "rag_retrieval duration_ms=%s paper_groups=%s passages=%s mode=%s",
            elapsed_ms,
            len(result.hits),
            sum(len(paper.passages) for paper in result.hits),
            mode,
        )
        context = build_context(result.hits, character_budget=EVIDENCE_CHARACTER_BUDGET)
        return PreparedRAG(request=request, context=context, search_mode=mode, model=model)

    async def ask(self, request: AskRequest) -> AskResponse:
        prepared = await self.prepare(request)
        if not prepared.context.citations:
            return self._response(prepared, INSUFFICIENT_EVIDENCE_ANSWER)

        generated = await self.ollama.generate(
            prepared.model,
            self._prompt(prepared, structured=True),
            system=self.system_prompt,
            response_format=GeneratedAnswer.model_json_schema(),
            options=GENERATION_OPTIONS,
        )
        self._log_generation(generated)
        try:
            answer = GeneratedAnswer.model_validate_json(generated.response).answer.strip()
        except (ValidationError, ValueError) as exc:
            raise OllamaResponseError("Ollama returned invalid structured output") from exc
        self.validate_answer(prepared, answer)
        return self._response(prepared, answer)

    async def generate_stream(self, prepared: PreparedRAG) -> AsyncIterator[OllamaGenerateResponse]:
        async for chunk in self.ollama.generate_stream(
            prepared.model,
            self._prompt(prepared, structured=False),
            system=self.system_prompt,
            options=GENERATION_OPTIONS,
        ):
            if chunk.done:
                self._log_generation(chunk)
            yield chunk

    def validate_answer(self, prepared: PreparedRAG, answer: str) -> None:
        try:
            validate_answer_citations(answer, {citation.marker for citation in prepared.context.citations})
        except ValueError as exc:
            raise GroundingError("Generated answer failed citation validation") from exc

    @staticmethod
    def _prompt(prepared: PreparedRAG, *, structured: bool) -> str:
        output = (
            'Return a JSON object with exactly one field named "answer".'
            if structured
            else "Return only the answer text."
        )
        return (
            f"Question:\n{prepared.request.query}\n\n"
            f"Evidence catalog:\n{prepared.context.prompt_context}\n\n"
            f"{output}"
        )

    @staticmethod
    def _response(prepared: PreparedRAG, answer: str) -> AskResponse:
        return AskResponse(
            query=prepared.request.query,
            answer=answer,
            sources=prepared.context.sources,
            citations=prepared.context.citations,
            chunks_used=len(prepared.context.citations),
            search_mode=prepared.search_mode,
            model=prepared.model,
        )

    def _model_for(self, request: AskRequest) -> str:
        if request.model is not None and request.model not in self.settings.ollama_models:
            raise UnsupportedModelError("Requested model is not configured")
        return request.model or self.settings.ollama_default_model

    @staticmethod
    def _log_generation(result: OllamaGenerateResponse) -> None:
        logger.info(
            "rag_generation load_ns=%s prompt_eval_ns=%s generation_ns=%s prompt_tokens=%s output_tokens=%s",
            result.load_duration,
            result.prompt_eval_duration,
            result.eval_duration,
            result.prompt_eval_count,
            result.eval_count,
        )
