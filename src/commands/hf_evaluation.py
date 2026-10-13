"""Frozen hosted profile, private metadata measurements and schema qualification."""

import asyncio
import hashlib
import json
import math
import re
import time
from pathlib import Path

from pydantic import BaseModel
from src.commands.agent_collection import create_evaluation_app
from src.commands.evaluate_agent import MANIFEST_SHA256, _count, free_memory_mib, memory_watch
from src.commands.evaluate_retrieval import digest
from src.commands.hf_qualification import decision_diagnostics
from src.config import Settings
from src.middlewares import RateLimiter
from src.operations import request_context
from src.schemas.api.agent import RelevanceDecision, RewriteDecision, ScopeDecision
from src.schemas.api.rag import GeneratedAnswer
from src.services.agent import AgentService
from src.services.hf.client import HFClient, HFGenerationError
from src.services.hf.rag import HostedRAGService
from src.services.rag.service import _selection_pattern, _unique_object

HF_MANIFEST_SHA256 = "3b42fccb34bc542e91ccdd3df0d8acb85c0bc86f7237eebdb214e6e9dbfc37a1"


def load_protocol(root=Path("evaluation/week7_hf")) -> dict:
    manifest_path = root / "manifest.json"
    if hashlib.sha256(manifest_path.read_bytes()).hexdigest() != HF_MANIFEST_SHA256:
        raise ValueError("Hosted manifest differs from frozen version")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest["local_manifest_sha256"] != MANIFEST_SHA256 or set(manifest["sha256"]) != {"PROTOCOL.md", "profile.json"}:
        raise ValueError("Hosted source reference differs")
    for name, expected in manifest["sha256"].items():
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != expected:
            raise ValueError("Hosted protocol fingerprint differs")
    catalog = Path("docs/research/hf-inference-models-20261013.json")
    if hashlib.sha256(catalog.read_bytes()).hexdigest() != manifest["research_catalog_sha256"]:
        raise ValueError("Research provenance differs")
    return json.loads((root / "profile.json").read_text(encoding="utf-8"))


def hosted_admission(settings: Settings, jobs: list, free_mib: float, profile: dict) -> str | None:
    if not settings.api_key or not settings.hf_token:
        return "missing_credentials"
    expected = {"rag_sentence_candidates_per_passage": "candidates_per_passage", "agent_deadline_seconds": "deadline_seconds",
                "agent_node_timeout_seconds": "node_timeout_seconds", "hf_timeout_seconds": "hf_timeout_seconds",
                "api_generations_per_minute": "generations_per_minute", "ollama_embedding_model": "embedding_model"}
    if any(getattr(settings, field) != profile[key] for field, key in expected.items()):
        return "policy_changed"
    if not math.isfinite(free_mib) or free_mib < max(profile["admission_mib"][job["mode"]] for job in jobs or [{"mode": "bm25"}]):
        return "insufficient_memory"
    return None


def create_hosted_app(settings: Settings, search, generation):
    local = create_evaluation_app(settings, search, generation)
    local.state.rag = HostedRAGService(search, generation, settings)
    local.state.agent = AgentService(local.state.rag, settings)
    return local


def validate_structured(content: str, schema: dict) -> dict:
    raw = json.loads(content, object_pairs_hook=_unique_object)
    keys = set(schema.get("properties") or {})
    contracts: dict[frozenset[str], type[BaseModel]] = {
        frozenset({"in_scope"}): ScopeDecision, frozenset({"relevant_markers"}): RelevanceDecision,
        frozenset({"query"}): RewriteDecision, frozenset({"answer"}): GeneratedAnswer}
    contract = contracts.get(frozenset(keys))
    if contract is None:
        raise ValueError("Unknown canonical structured contract")
    contract.model_validate(raw, strict=True)
    if keys == {"answer"} and re.fullmatch(schema["properties"]["answer"]["pattern"], raw["answer"]) is None:
        raise ValueError("Selection violates original pattern")
    return raw


class MeasuredHF(HFClient):
    def __init__(self, settings: Settings, *, outbound_budget: int):
        super().__init__(settings)
        if type(outbound_budget) is not int or not 1 <= outbound_budget <= 773:
            raise ValueError("Invalid hosted attempt budget")
        self.outbound_budget = outbound_budget
        self.ledger: dict[str, list[dict]] = {}

    async def generate(self, model, prompt, **kwargs):
        _count("generation_calls")
        request_id = (request_context.get() or {}).get("request_id") or "administrative"
        rows = self.ledger.setdefault(request_id, [])
        if len(rows) >= 6:
            raise HFGenerationError("Hosted evaluation stage budget exhausted")
        before, started = self.attempts, time.perf_counter()
        schema = kwargs.get("response_format")
        row = {"ordinal": len(rows) + 1, "model": model, "outcome": "failed", "schema_valid": None,
               "input_tokens": None, "output_tokens": None, "reasoning_tokens": None,
               "output_limit": (kwargs.get("options") or {}).get("num_predict", 512)}
        if schema is not None:
            row["schema_sha256"] = digest(schema)
        try:
            if self.attempts >= self.outbound_budget:
                raise HFGenerationError("Hosted evaluation outbound budget exhausted")
            result = await self.generate_result(model, prompt, **kwargs)
            row.update(outcome="completed", input_tokens=result.input_tokens, output_tokens=result.output_tokens,
                       reasoning_tokens=result.reasoning_tokens)
            if schema is not None:
                row["schema_sha256"] = digest(schema)
                try:
                    validate_structured(result.content, schema)
                    row["schema_valid"] = True
                except (ValueError, TypeError, KeyError):
                    row["schema_valid"] = False
            return result.as_legacy_response()
        except asyncio.CancelledError:
            row.update(outcome="interrupted", error_class="CancelledError")
            raise
        except Exception as exc:
            row["error_class"] = type(exc).__name__
            if isinstance(exc, HFGenerationError):
                row["provider_status"] = exc.status_code
                if exc.error_code is not None:
                    row["provider_error_code"] = exc.error_code
                if exc.error_type is not None:
                    row["provider_error_type"] = exc.error_type
            raise
        finally:
            row.update(outbound_attempts=self.attempts - before, duration_ms=round((time.perf_counter() - started) * 1000, 2))
            rows.append(row)


def hosted_work(calls: list[dict], profile: dict, model: str) -> dict:
    rates = profile["prices_per_million"][model]
    outbound = unknown = violations = 0
    known_cost = 0.0
    for ordinal, call in enumerate(calls, 1):
        if (type(call.get("ordinal")) is not int or call["ordinal"] != ordinal or call.get("model") != model
                or type(call.get("outbound_attempts")) is not int or call["outbound_attempts"] not in {0, 1}
                or call.get("outcome") not in {"completed", "failed", "interrupted"}
                or call.get("outcome") == "completed" and call["outbound_attempts"] != 1
                or call.get("schema_valid") is not None and type(call["schema_valid"]) is not bool
                or type(call.get("duration_ms")) not in {int, float}
                or not math.isfinite(call["duration_ms"]) or call["duration_ms"] < 0
                or type(call.get("output_limit")) is not int or call["output_limit"] not in {256, 512}):
            raise ValueError("Invalid hosted work ledger")
        outbound += call["outbound_attempts"]
        violations += int(call["schema_valid"] is False or call["outcome"] == "completed" and call["schema_valid"] is not True)
        inputs, outputs = call.get("input_tokens"), call.get("output_tokens")
        if call["outbound_attempts"]:
            if (call["outcome"] != "completed" or type(inputs) is not int or type(outputs) is not int):
                unknown += 1
            else:
                if not 0 <= inputs <= 8192 - call["output_limit"] or not 0 <= outputs <= call["output_limit"]:
                    raise ValueError("Invalid hosted token ledger")
                known_cost += (inputs * rates["input"] + outputs * rates["output"]) / 1_000_000
    return {"outbound_attempts": outbound, "unknown_usage_attempts": unknown, "schema_violations": violations,
            "usage_complete": unknown == 0, "known_usage_cost_usd": round(known_cost, 10)}


def qualification_cases() -> list[dict]:
    cases: list[dict] = [
        {"id": "scope", "schema": ScopeDecision.model_json_schema(), "prompt": "The question concerns neural AI retrieval. Return in_scope true.", "expected": {"in_scope": True}},
        {"id": "relevance", "schema": RelevanceDecision.model_json_schema(), "prompt": "Question: neural AI retrieval. Evidence [1.1]: Neural AI retrieval selects indexed passages. Return relevant_markers containing only [1.1].", "expected": {"relevant_markers": ["[1.1]"]}},
        {"id": "rewrite", "schema": RewriteDecision.model_json_schema(), "prompt": "Rewrite neural AI retrieval evidence into a concise nonempty search query. Return query.", "expected": None},
    ]
    for count, answer in ((1, "E1"), (10, "E1 E10")):
        schema = GeneratedAnswer.model_json_schema()
        schema["properties"]["answer"] = {"type": "string", "pattern": _selection_pattern(count)}
        cases.append({"id": f"selector-{count}", "schema": schema,
                      "prompt": f"For this synthetic schema check, return exactly answer={answer!r}. Known IDs range from E1 to E{count}.",
                      "expected": {"answer": answer}})
    return cases


async def qualify(client: MeasuredHF, profile: dict, *, limiter: RateLimiter, memory=free_memory_mib, revision=None) -> dict:
    checks: list[dict] = []
    binding = {"fixture_manifest_sha256": revision["manifest_sha256"]} if revision else {}
    model = client.settings.hf_default_model
    schema = GeneratedAnswer.model_json_schema()
    schema["properties"]["answer"] = {"type": "string", "pattern": _selection_pattern(30)}
    before = client.attempts
    rejected = False
    try:
        client._payload(model, "Synthetic large-schema admission check", None, schema,
                        {"temperature": 0, "num_predict": 512, "num_ctx": 8192})
    except HFGenerationError:
        rejected = client.attempts == before
    if not rejected:
        return {**binding, "qualified": False, "checks": checks, "large_schema_preflight_rejected": False}
    for case in revision["cases"] if revision else qualification_cases():
        check = {"id": case["id"], "schema_sha256": digest(case["schema"]), "ok": False}
        if revision:
            check["fixture_sha256"] = digest(case)
        request_id = hashlib.sha256(case["id"].encode()).hexdigest()[:32]
        token = request_context.set({"request_id": request_id})
        finished = asyncio.Event()
        samples: list[dict] = []
        task = watcher = None
        try:
            if memory() < profile["live_margin_mib"]:
                raise ValueError("Qualification resource margin failed")
            if limiter.reserve(generation=True):
                raise ValueError("Qualification quota rejected")
            output_limit = 512 if case["id"].startswith("selector") else 256
            system = {"system": case["system"]} if revision else {}
            task = asyncio.create_task(client.generate(model, case["prompt"], **system, response_format=case["schema"],
                options={"temperature": 0, "num_predict": output_limit, "num_ctx": 8192}))
            watcher = asyncio.create_task(memory_watch(task, finished, samples, memory))
            generated = await task
            raw = validate_structured(generated.response, case["schema"])
            if revision:
                check["diagnostics"] = decision_diagnostics(raw, case)
            if case["expected"] is not None and raw != case["expected"]:
                raise ValueError("Synthetic qualification answer differs")
            check["ok"] = True
        except asyncio.CancelledError:
            if not samples or all("free_mib" in sample and sample["free_mib"] >= 384 for sample in samples):
                raise
            check["error_class"] = "QualificationResourceStop"
        except Exception as exc:
            check["error_class"] = type(exc).__name__
        finally:
            finished.set()
            if watcher is not None:
                await watcher
            request_context.reset(token)
            ledger = client.ledger.pop(request_id, [])
            check.update(calls=ledger, work=hosted_work(ledger, profile, model))
            values = [sample["free_mib"] for sample in samples if "free_mib" in sample]
            check["minimum_free_mib"] = min(values) if values else None
            if check["ok"] and (not values or min(values) < 600 or not check["work"]["usage_complete"] or check["work"]["schema_violations"]):
                check["ok"] = False
                check["error_class"] = "QualificationMeasurementsIncomplete"
            checks.append(check)
            if revision:
                print(json.dumps({"qualification": case["id"], "ok": check["ok"],
                    "diagnostics": check.get("diagnostics"), "outbound_attempts": check["work"]["outbound_attempts"],
                    "error_class": check.get("error_class")}), flush=True)
        if not check["ok"]:
            break
    return {**binding, "qualified": len(checks) == profile["qualification_calls"] and all(check["ok"] for check in checks),
            "checks": checks, "large_schema_preflight_rejected": rejected}
