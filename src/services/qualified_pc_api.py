"""Private PC generation admitted only by reviewed Cerebras holdout evidence."""

import json
import math
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path

import anyio
from src.commands.evaluate_agent import free_memory_mib
from src.commands.evaluate_hf_agent import live_snapshot
from src.commands.evaluate_retrieval import digest
from src.commands.hf_evaluation import hosted_admission, validate_structured
from src.commands.hf_paper_acceptance import validate_acceptance
from src.commands.hf_paper_profile import load_profile
from src.commands.hf_schema_execution import load_cerebras
from src.config import Settings
from src.operations import request_context
from src.routers import agent, ask
from src.schemas.api.rag import GeneratedAnswer
from src.services.agent import AgentService
from src.services.hf.client import HFClient, HFGenerationError, HFResponseError
from src.services.hf.rag import HostedRAGService
from src.services.pc_api import ReadOnlyDatabase, create_local_app, make_embedder, make_ollama_client, make_search_client
from src.services.rag.service import _selection_pattern
from src.services.search import SearchService


def validate_policy(settings: Settings) -> dict:
    profile = load_profile()
    model = profile["model_pairs"][0]
    if (hosted_admission(settings, [], profile["admission_mib"]["bm25"], profile) is not None
            or not settings.hf_inference_enabled or not settings.agent_enabled
            or settings.hf_models != [model] or settings.hf_default_model != model
            or settings.answer_cache_enabled or settings.local_tracing_enabled or settings.monitoring_directory is not None):
        raise ValueError("Private runtime requires the accepted model and frozen generation policy")
    return profile


class QualifiedHF(HFClient):
    def __init__(self, settings: Settings, acceptance: Path, *, memory=free_memory_mib):
        validate_policy(settings)
        proof = validate_acceptance(acceptance)
        self.acceptance, self.proof, self.memory = acceptance.resolve(), proof, memory
        self.schemas = {digest(case["schema"]): 256 for case in load_cerebras()["cases"]}
        for count in range(31):
            schema = GeneratedAnswer.model_json_schema()
            schema["properties"]["answer"] = {"type": "string", "pattern": _selection_pattern(count)}
            self.schemas[digest(schema)] = 512
        super().__init__(settings)

    async def generate_result(self, model, prompt, **kwargs):
        context = request_context.get()
        if (context is None or not context.get("request_id") or context.get("hf_failed")
                or context.get("hf_calls", 0) >= 6 or self._busy):
            raise HFGenerationError("Private generation request is unavailable or exhausted")
        try:
            profile = validate_policy(self.settings)
            free_mib = self.memory()
            if not math.isfinite(free_mib) or free_mib < profile["live_margin_mib"]:
                raise HFGenerationError("Private generation has insufficient memory")
            proof = await anyio.to_thread.run_sync(validate_acceptance, self.acceptance)
            if proof != self.proof:
                raise HFGenerationError("Accepted private generation evidence changed")
            payload = self._payload(model, prompt, kwargs.get("system"), kwargs.get("response_format"), kwargs.get("options"))
            if self.schemas.get(digest(kwargs.get("response_format"))) != payload["max_tokens"]:
                raise HFGenerationError("Private generation contract differs")
            context["hf_calls"] = context.get("hf_calls", 0) + 1
            result = await super().generate_result(model, prompt, **kwargs)
            if result.input_tokens is None or result.output_tokens is None:
                raise HFResponseError("Private generation usage is incomplete")
            validate_structured(result.content, kwargs["response_format"])
            return result
        except BaseException as exc:
            context["hf_failed"] = True
            if isinstance(exc, (ValueError, OSError, KeyError, TypeError)):
                raise HFGenerationError("Private generation evidence or contract is unavailable") from None
            raise


def verify_live_source(settings: Settings, proof: dict) -> None:
    state, _, _ = live_snapshot(settings)
    expected = json.loads((Path(proof["source_snapshot"]) / "state.json").read_text(encoding="utf-8"))
    if state != expected:
        raise ValueError("Private runtime requires the accepted corpus and installed models")


def create_qualified_app(settings: Settings, acceptance: Path):
    validate_policy(settings)
    proof = validate_acceptance(acceptance)

    @asynccontextmanager
    async def lifespan(app):
        owned = AsyncExitStack()
        try:
            await anyio.to_thread.run_sync(verify_live_source, settings, proof)
            database = ReadOnlyDatabase(settings)
            owned.callback(database.teardown)
            database.startup()
            search_client = make_search_client(settings)
            owned.callback(search_client.close)
            app.state.search = SearchService(search_client, make_embedder(settings))
            ollama = make_ollama_client(settings)
            owned.push_async_callback(ollama.aclose)
            hf = QualifiedHF(settings, acceptance)
            owned.push_async_callback(hf.aclose)
            app.state.database, app.state.ollama, app.state.hf = database, ollama, hf
            app.state.rag = HostedRAGService(app.state.search, hf, settings)
            app.state.agent = AgentService(app.state.rag, settings)
            yield
        finally:
            with anyio.CancelScope(shield=True):
                await owned.aclose()

    app = create_local_app(settings, lifespan)
    app.include_router(ask.router, prefix="/api/v1")
    app.include_router(agent.router, prefix="/api/v1")

    @app.get("/api/v1/qualification")
    async def qualification():
        current = await anyio.to_thread.run_sync(validate_acceptance, acceptance)
        return {"accepted": True, "model": current["model"],
                "hosted_manifest_sha256": current["hosted_manifest_sha256"], "source_sha256": current["source_sha256"]}

    return app
