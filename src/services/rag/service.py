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
from src.services.rag.context import INSUFFICIENT_EVIDENCE_ANSWER, RAGContext, build_context, validate_answer_evidence
from src.services.rag.excerpts import build_excerpts, render_selection
from src.services.search import SearchService

logger = logging.getLogger(__name__)

EVIDENCE_CHARACTER_BUDGET = 12_000
GENERATION_OPTIONS = {"temperature": 0, "num_predict": 512, "num_ctx": 8192}
SYSTEM_PROMPT_PATH = Path(__file__).parents[1] / "ollama" / "prompts" / "rag_system.txt"


@dataclass(frozen=True)
class PreparedRAG:
    request: AskRequest
    context: RAGContext
    search_mode: Literal["hybrid", "bm25"]
    model: str
    candidates_per_passage: int = 1

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
        return PreparedRAG(request=request, context=context, search_mode=mode, model=model,
                           candidates_per_passage=self.settings.rag_sentence_candidates_per_passage)

    async def ask(self, request: AskRequest) -> AskResponse:
        prepared = await self.prepare(request)
        answer = await self._generate_answer(prepared)
        return self._response(prepared, answer)

    async def _generate_answer(self, prepared: PreparedRAG) -> str:
        """Use one selection transport and bounded validation policy for both routes."""
        if not build_excerpts(prepared.context.citations, prepared.request.query,
                              candidates_per_passage=prepared.candidates_per_passage):
            return INSUFFICIENT_EVIDENCE_ANSWER

        generated = await self.ollama.generate(
            prepared.model,
            self._prompt(prepared, structured=True),
            system=self.system_prompt,
            response_format=self._selection_schema(prepared),
            options=GENERATION_OPTIONS,
        )
        self._log_generation(generated)
        try:
            answer = self._selected_answer(prepared, generated.response, structured=True)
            self.validate_answer(prepared, answer)
        except (GroundingError, OllamaResponseError):
            # Retry invalid selections once as plain IDs against the same evidence.
            # Never rewrite model claims or invent citations.
            generated = await self.ollama.generate(
                prepared.model,
                self._prompt(prepared, structured=False),
                system=self.system_prompt,
                options=GENERATION_OPTIONS,
            )
            self._log_generation(generated)
            answer = self._selected_answer(prepared, generated.response, structured=False)
            self.validate_answer(prepared, answer)
        return answer

    async def generate_stream(self, prepared: PreparedRAG) -> AsyncIterator[OllamaGenerateResponse]:
        # Selection is already buffered: use the same transport/retry as /ask,
        # then expose only complete validated quotations, never internal IDs.
        answer = await self._generate_answer(prepared)
        for line in answer.splitlines(keepends=True):
            yield OllamaGenerateResponse(model=prepared.model, response=line, done=False)
        yield OllamaGenerateResponse(model=prepared.model, response="", done=True)

    def validate_answer(self, prepared: PreparedRAG, answer: str) -> None:
        try:
            validate_answer_evidence(answer, prepared.context.citations)
        except ValueError as exc:
            logger.warning(
                "rag_answer_validation_failed model=%s mode=%s reason=%s",
                prepared.model,
                prepared.search_mode,
                exc,
            )
            raise GroundingError("Generated answer failed grounding validation") from exc

    @staticmethod
    def _prompt(prepared: PreparedRAG, *, structured: bool) -> str:
        excerpts = build_excerpts(prepared.context.citations, prepared.request.query,
                                  candidates_per_passage=prepared.candidates_per_passage)
        blocks = []
        for citation in prepared.context.citations:
            sentences = [f"{key}: {excerpt.text}" for key, excerpt in excerpts.items() if excerpt.marker == citation.marker]
            blocks.append(f"{citation.marker}\nPaper: {citation.title}\nSection: {citation.section_title}\n" + "\n".join(sentences))
        catalog = "\n\n".join(blocks)
        expansion_guidance = (
            "Never repeat an ID. Do not fill unused slots with background. "
            "Include complementary sentences when a passage contains several requested details. "
            if prepared.candidates_per_passage > 1 else ""
        )
        distinct = "distinct " if prepared.candidates_per_passage > 1 else ""
        output = (
            f'Return a JSON object with exactly one field named "answer", an array of up to three {distinct}selected IDs. '
            'Return {"answer": []} if no sentence answers the question.'
            if structured
            else f"Return only up to three {distinct}IDs separated by spaces, or NONE if no sentence answers the question."
        )
        return (
            f"Question:\n{prepared.request.query}\n\n"
            f"Evidence catalog:\n{catalog}\n\n"
            f"Answer the original question: {prepared.request.query}\n"
            f"Allowed citation markers: {', '.join(c.marker for c in prepared.context.citations)}.\n"
            "Select the sentences that directly answer the question. Prefer different relevant papers. "
            f"{expansion_guidance}"
            "Distinguish background discussion, proposed methods, and comparison baselines. "
            "The server will quote selected sentences and attach their original passage citations. "
            f"{output}\nSelected evidence IDs:"
        )

    @staticmethod
    def _selection_schema(prepared: PreparedRAG) -> dict:
        schema = GeneratedAnswer.model_json_schema()
        ids = list(build_excerpts(prepared.context.citations, prepared.request.query,
                                  candidates_per_passage=prepared.candidates_per_passage))
        schema["properties"]["answer"]["items"]["enum"] = ids
        schema["properties"]["answer"]["uniqueItems"] = True
        return schema

    @staticmethod
    def _selected_answer(prepared: PreparedRAG, raw: str, *, structured: bool) -> str:
        if structured:
            try:
                selection = GeneratedAnswer.model_validate_json(raw).answer
            except (ValidationError, ValueError) as exc:
                raise OllamaResponseError("Ollama returned invalid structured output") from None
        else:
            selection = [] if raw.strip() == "NONE" else raw.split()
        try:
            return render_selection(selection, build_excerpts(prepared.context.citations, prepared.request.query,
                                                             candidates_per_passage=prepared.candidates_per_passage))
        except ValueError as exc:
            logger.warning("rag_selection_validation_failed reason=%s", exc)
            raise GroundingError("Generated answer failed grounding validation") from exc

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
            "rag_generation load_ns=%s prompt_eval_ns=%s generation_ns=%s prompt_tokens=%s output_tokens=%s done_reason=%s",
            result.load_duration,
            result.prompt_eval_duration,
            result.eval_duration,
            result.prompt_eval_count,
            result.eval_count,
            result.done_reason,
        )
