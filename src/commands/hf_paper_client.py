"""Source-bound, persistently funded model client for isolated paper evaluation."""

import math
from pathlib import Path

from src.commands.evaluate_agent import free_memory_mib
from src.commands.evaluate_hf_agent import source_hashes
from src.commands.evaluate_retrieval import digest
from src.commands.hf_evaluation import MeasuredHF, validate_structured
from src.commands.hf_paper_allowance import TaskAllowance
from src.commands.hf_paper_profile import CEREBRAS_TASK_SHA256, load_profile
from src.commands.hf_schema_execution import load_cerebras, load_selectors
from src.config import Settings
from src.operations import request_context
from src.schemas.api.rag import GeneratedAnswer
from src.services.hf.client import HFGenerationError
from src.services.hf.tokenizer import CerebrasInputAdmission, verify_vocabulary
from src.services.rag.service import _selection_pattern


class FundedHF(CerebrasInputAdmission, MeasuredHF):
    def __init__(self, settings: Settings, *, grant: TaskAllowance, output: Path, source: dict,
                 outbound_budget: int, memory=free_memory_mib):
        profile, controller, selectors = load_profile(), load_cerebras(), load_selectors()
        expected = {"rag_sentence_candidates_per_passage": "candidates_per_passage", "agent_deadline_seconds": "deadline_seconds",
                    "agent_node_timeout_seconds": "node_timeout_seconds", "hf_timeout_seconds": "hf_timeout_seconds",
                    "api_generations_per_minute": "generations_per_minute", "ollama_embedding_model": "embedding_model"}
        if (settings.hf_models != [controller["model"]] or settings.hf_default_model != controller["model"]
                or not settings.agent_enabled or settings.answer_cache_enabled or settings.local_tracing_enabled
                or settings.monitoring_directory is not None or not settings.api_key
                or any(getattr(settings, key) != profile[value] for key, value in expected.items())
                or type(outbound_budget) is not int or outbound_budget != grant.receipt["maximum_outbound_attempts"]
                or grant.receipt["hosted_manifest_sha256"] != CEREBRAS_TASK_SHA256
                or grant.receipt["model"] != controller["model"] or grant.receipt["source_sha256"] != digest(source)
                or source_hashes() != source or grant.started):
            raise ValueError("Funded evaluation requires the unchanged approved source, pair and policy")
        verify_vocabulary()
        self.source, self.grant, self.output, self.memory = dict(source), grant, output.resolve(), memory
        self.qualification = controller["cases"] + selectors["cases"]
        self.payloads = controller["payloads"] + selectors["payloads"]
        self.schemas = {digest(case["schema"]): 256 for case in controller["cases"]}
        for count in range(31):
            schema = GeneratedAnswer.model_json_schema()
            schema["properties"]["answer"] = {"type": "string", "pattern": _selection_pattern(count)}
            self.schemas[digest(schema)] = 512
        self.halted = False
        self.request_calls: dict[str, int] = {}
        super().__init__(settings, outbound_budget=outbound_budget)

    async def generate_result(self, model, prompt, **kwargs):
        if self.halted:
            raise HFGenerationError("Hosted evaluation has stopped")
        if self._busy:
            raise HFGenerationError("Hosted generation capacity is occupied")
        before = self.attempts
        request_id = (request_context.get() or {}).get("request_id") or "administrative"
        reserved = False
        try:
            profile = load_profile()
            free_mib = self.memory()
            if (source_hashes() != self.source or not math.isfinite(free_mib) or free_mib < profile["live_margin_mib"]
                    or before >= self.outbound_budget or self.request_calls.get(request_id, 0) >= 6):
                raise HFGenerationError("Hosted evaluation source, resource or work limit failed")
            payload = self._payload(model, prompt, kwargs.get("system"), kwargs.get("response_format"), kwargs.get("options"))
            if (self.schemas.get(digest(kwargs.get("response_format"))) != payload["max_tokens"]
                    or before < len(self.payloads) and digest(payload) != digest(self.payloads[before])):
                raise ValueError("Request differs from the approved canonical contracts")
            self.grant.reserve(str(self.output), before + 1, request_id)
            reserved = True
            self.request_calls[request_id] = self.request_calls.get(request_id, 0) + 1
            result = await super().generate_result(model, prompt, **kwargs)
            if result.input_tokens is None or result.output_tokens is None:
                self.halted = True
            try:
                raw = validate_structured(result.content, kwargs["response_format"])
                if before < len(self.qualification):
                    expected = self.qualification[before]["expected"]
                    if expected is not None and raw != expected:
                        self.halted = True
            except (ValueError, TypeError, KeyError):
                self.halted = True
            # MeasuredHF records known usage/schema validity before the collector
            # stops. No further wire attempt is admitted after a failed check.
            return result
        except BaseException:
            self.halted = True
            raise
        finally:
            if reserved:
                used = self.attempts - before
                try:
                    self.grant.settle(before + 1, used if used in {0, 1} else None)
                except BaseException:
                    self.halted = True
                    raise
