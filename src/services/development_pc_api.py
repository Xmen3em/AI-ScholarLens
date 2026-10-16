"""Explicit owner development runtime; never claims evaluation acceptance."""

import math
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path

import anyio
import httpx
from fastapi import FastAPI, HTTPException
from src.commands.evaluate_agent import free_memory_mib
from src.commands.hf_evaluation import validate_structured
from src.commands.run_pc_api import preview_settings
from src.config import Settings
from src.middlewares import OperationalMiddleware
from src.operations import request_context
from src.routers.agent import ask as ask_agent
from src.schemas.api.agent import AgentResponse
from src.schemas.api.assistant import LearningDecision, LearningResponse
from src.schemas.api.rag import AskRequest
from src.services.development_assistant import DevelopmentAssistant, parse_learning_decision
from src.services.hf.client import HFClient, HFGenerationError, HFResponseError
from src.services.hf.rag import HostedRAGService
from src.services.hf.tokenizer import CerebrasInputAdmission, verify_vocabulary
from src.services.pc_api import make_embedder, make_search_client
from src.services.search import SearchService

MODEL = "openai/gpt-oss-120b:cerebras"
ADMISSION_MIB = 1024
LIVE_MIB = 600


def development_settings(original: Settings, workspace: Path) -> Settings:
    local = preview_settings(original, workspace)
    quota = (workspace.resolve() / "data/pc-app/development-quotas.sqlite3").resolve()
    if not quota.is_relative_to(workspace.resolve() / "data/pc-app"):
        raise ValueError("Development state must stay in the workspace")
    return Settings.model_validate(local.model_copy(update={
        "hf_inference_enabled": True, "agent_enabled": True, "hf_models": [MODEL], "hf_default_model": MODEL,
        "rag_sentence_candidates_per_passage": 3, "rag_max_sentence_candidates": 10,
        "api_rate_limit_path": str(quota),
    }).model_dump())


class DevelopmentHF(CerebrasInputAdmission, HFClient):
    def __init__(self, settings: Settings, *, memory=free_memory_mib):
        verify_vocabulary()
        self.memory = memory
        super().__init__(settings)

    async def generate_result(self, model, prompt, **kwargs):
        context = request_context.get()
        if (context is None or not context.get("request_id") or context.get("hf_failed")
                or context.get("hf_calls", 0) >= 6 or self._busy):
            raise HFGenerationError("Development question is unavailable or exhausted")
        try:
            free = self.memory()
            if not math.isfinite(free) or free < LIVE_MIB:
                raise HFGenerationError("Insufficient memory for development generation")
            if not isinstance(kwargs.get("response_format"), dict):
                raise HFGenerationError("Development generation requires a bounded schema")
            context["hf_calls"] = context.get("hf_calls", 0) + 1
            result = await super().generate_result(model, prompt, **kwargs)
            if result.input_tokens is None or result.output_tokens is None:
                raise HFResponseError("Development generation usage is incomplete")
            try:
                if kwargs["response_format"] == LearningDecision.model_json_schema():
                    parse_learning_decision(result.content)
                else:
                    validate_structured(result.content, kwargs["response_format"])
            except (ValueError, TypeError):
                raise HFResponseError("Development generation schema is invalid") from None
            return result
        except BaseException:
            context["hf_failed"] = True
            raise


def create_development_app(settings: Settings, *, study_owner: int | None = None):
    if (not settings.hf_inference_enabled or not settings.agent_enabled or settings.api_key is None
            or settings.hf_models != [MODEL] or settings.hf_default_model != MODEL
            or settings.answer_cache_enabled or settings.local_tracing_enabled or settings.monitoring_directory is not None):
        raise ValueError("Development requires isolated authenticated HF settings")

    @asynccontextmanager
    async def lifespan(app):
        owned = AsyncExitStack()
        try:
            search_client = make_search_client(settings)
            owned.callback(search_client.close)
            app.state.search = SearchService(search_client, make_embedder(settings))
            hf = DevelopmentHF(settings)
            owned.push_async_callback(hf.aclose)
            app.state.hf = hf
            app.state.rag = HostedRAGService(app.state.search, hf, settings)
            app.state.agent = DevelopmentAssistant(app.state.rag, settings)
            if study_owner is not None:
                from src.services.study.content import PaperContentService
                from src.services.study.intake import ArxivIntake
                from src.services.study.service import StudyService
                from src.services.study.store import StudyStore
                from src.services.study.tutor import StudyModel

                workspace = Path.cwd().resolve()
                root = workspace / "data/study"
                if any(path.is_symlink() for path in (workspace / "data", root)) or not root.resolve().is_relative_to(workspace):
                    raise ValueError("Study state must stay in the workspace")
                public = httpx.AsyncClient(trust_env=False, follow_redirects=False, timeout=30,
                    headers={"User-Agent": "ScholarLens-private-study/0.1"},
                    limits=httpx.Limits(max_connections=1, max_keepalive_connections=1))
                owned.push_async_callback(public.aclose)
                store = StudyStore(root / "sessions.sqlite3", str(study_owner))
                store.recover_interrupted()
                tutor = StudyModel(settings.hf_token, store)
                owned.push_async_callback(tutor.aclose)
                app.state.study = StudyService(store, ArxivIntake(public), PaperContentService(root / "sources", public), tutor)
                owned.push_async_callback(app.state.study.aclose)
            yield
        finally:
            with anyio.CancelScope(shield=True):
                await owned.aclose()

    app = FastAPI(title="ScholarLens private development bot", lifespan=lifespan)
    app.state.settings = settings
    app.state.monitoring = app.state.tracing = None
    app.add_middleware(OperationalMiddleware, settings=settings)
    if study_owner is not None:
        if type(study_owner) is not int or not 0 < study_owner < 2**52:
            raise ValueError("Study requires the paired owner")
        from src.services.study.api import add_study_routes

        add_study_routes(app)

    @app.get("/api/v1/development")
    async def status():
        return {"mode": "development", "accepted": False, "model": MODEL, "search_mode": "bm25",
                "answer_modes": ["general_knowledge", "paper_evidence"],
                "generation_attempts": app.state.hf.attempts}

    @app.post("/api/v1/agent/ask", response_model=AgentResponse | LearningResponse)
    async def ask(request: AskRequest):
        if request.model is not None and request.model != MODEL:
            raise HTTPException(status_code=422, detail="Requested generation model is not configured")
        free = free_memory_mib()
        if not math.isfinite(free) or free < LIVE_MIB:
            raise HTTPException(status_code=503, detail="Insufficient memory; try again after other work finishes.")
        # Keyword retrieval avoids loading a local embedding model. Generation
        # remains remote and the response accurately reports its actual mode.
        return await ask_agent(request.model_copy(update={"use_hybrid": False}), app.state.agent)

    return app
