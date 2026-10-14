"""Frozen synthetic reproduction; experimental schemas never change application guards."""

import asyncio
import copy
import hashlib
import json
import math
from pathlib import Path

from src.commands.evaluate_agent import free_memory_mib, memory_watch
from src.commands.evaluate_retrieval import digest
from src.commands.hf_allowance import PILOT_MODEL
from src.commands.hf_error_structure import STRUCTURE_SHA256, BoundedErrorTransport, load_structure_protocol, strict_json
from src.commands.hf_evaluation import MeasuredHF, hosted_work, load_protocol, validate_structured
from src.commands.hf_qualification import load_revision
from src.commands.hf_success_diagnostics import inspect_relevance, load_success_contract
from src.config import Settings
from src.middlewares import RateLimiter
from src.operations import request_context
from src.schemas.api.rag import GeneratedAnswer
from src.services.hf.client import HFGenerationError, HFTimeoutError
from src.services.rag.service import _selection_pattern

REPRODUCTION_SHA256 = "7e5768ae0713b9d91d19d5faf0f5a62c6941ac25deef55b43ae014c31566a4cf"
ARRAY_PROMPT_SHA256 = "d445f845434f469a39e3e06715ae7fc4d92333f08b691293ccfab4ba64b6e7d9"
PROMPT_COMPARISON_SHA256 = "9dd2a1e2ad2c9cb678c683a4285208b6857fd07bce1a763be5bb36f371fbd3dd"


def load_reproduction(root=Path("evaluation/week7_hf/reproduction-v1")) -> dict:
    manifest = root / "manifest.json"
    if hashlib.sha256(manifest.read_bytes()).hexdigest() != REPRODUCTION_SHA256:
        raise ValueError("Reproduction manifest differs")
    binding = json.loads(manifest.read_text(encoding="utf-8"))
    if (binding["parent_fixture_manifest_sha256"] != load_revision()["manifest_sha256"]
            or binding["prior_structure_manifest_sha256"] != STRUCTURE_SHA256
            or set(binding["sha256"]) != {"PROTOCOL.md", "requests.json"}):
        raise ValueError("Reproduction parent differs")
    load_structure_protocol()
    for name, expected in binding["sha256"].items():
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != expected:
            raise ValueError("Reproduction input differs")
    return json.loads((root / "requests.json").read_text(encoding="utf-8"))


def load_array_prompt(root=Path("evaluation/week7_hf/array-prompt-v1")) -> dict:
    manifest = root / "manifest.json"
    if hashlib.sha256(manifest.read_bytes()).hexdigest() != ARRAY_PROMPT_SHA256:
        raise ValueError("Array prompt manifest differs")
    binding = json.loads(manifest.read_text(encoding="utf-8"))
    load_reproduction()
    if (binding["parent_fixture_manifest_sha256"] != load_revision()["manifest_sha256"]
            or binding["parent_reproduction_manifest_sha256"] != REPRODUCTION_SHA256
            or set(binding["sha256"]) != {"PROTOCOL.md", "requests.json"}):
        raise ValueError("Array prompt parent differs")
    for name, expected in binding["sha256"].items():
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != expected:
            raise ValueError("Array prompt input differs")
    return json.loads((root / "requests.json").read_text(encoding="utf-8"))


def load_prompt_comparison(root=Path("evaluation/week7_hf/prompt-comparison-v1")) -> dict:
    manifest = root / "manifest.json"
    if hashlib.sha256(manifest.read_bytes()).hexdigest() != PROMPT_COMPARISON_SHA256:
        raise ValueError("Prompt comparison manifest differs")
    binding = json.loads(manifest.read_text(encoding="utf-8"))
    load_array_prompt()
    if (binding["parent_fixture_manifest_sha256"] != load_revision()["manifest_sha256"]
            or binding["parent_array_manifest_sha256"] != ARRAY_PROMPT_SHA256
            or set(binding["sha256"]) != {"PROTOCOL.md", "requests.json"}):
        raise ValueError("Prompt comparison parent differs")
    for name, expected in binding["sha256"].items():
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != expected:
            raise ValueError("Prompt comparison input differs")
    return json.loads((root / "requests.json").read_text(encoding="utf-8"))


def load_experiment(experiment: str) -> dict:
    if experiment == "reproduction-v1":
        return {**load_reproduction(), "manifest_sha256": REPRODUCTION_SHA256}
    if experiment == "array-prompt-v1":
        return {**load_array_prompt(), "manifest_sha256": ARRAY_PROMPT_SHA256}
    if experiment == "prompt-comparison-v1":
        return {**load_prompt_comparison(), "manifest_sha256": PROMPT_COMPARISON_SHA256}
    raise ValueError("Unknown frozen experiment")


class ReproductionHF(MeasuredHF):
    def __init__(self, settings: Settings, arm: str, *, experiment="reproduction-v1"):
        arms = load_experiment(experiment)["arms"]
        if arm not in arms or settings.hf_models != [PILOT_MODEL] or settings.hf_default_model != PILOT_MODEL:
            raise ValueError("Reproduction requires a frozen approved arm")
        self.arm = arms[arm]
        super().__init__(settings, outbound_budget=1)
        self.observer = BoundedErrorTransport(self._client._transport, self.arm["case"])
        self._client._transport = self.observer

    def _payload(self, model, prompt, system, response_format, options):
        payload = super()._payload(model, prompt, system, response_format, options)
        if payload != self.arm["payload"]:
            raise ValueError("Request differs from frozen reproduction")
        return payload


async def reproduce(settings: Settings, arm: str, *, memory=free_memory_mib, experiment="reproduction-v1") -> dict:
    profile = load_protocol()
    experiment_profile = load_experiment(experiment)
    measurement = load_success_contract()
    hf = ReproductionHF(settings, arm, experiment=experiment)
    case = hf.arm["case"]
    limit = hf.arm["payload"]["max_tokens"]
    options = {"temperature": 0, "num_predict": limit, "num_ctx": 8192}
    finished = asyncio.Event()
    samples: list[dict] = []
    watcher = None
    token = request_context.set({"request_id": hashlib.sha256(arm.encode()).hexdigest()[:32]})
    result = {"kind": experiment_profile["kind"], "arm": arm,
              "qualification_accepted": False, "reproduction_manifest_sha256": experiment_profile["manifest_sha256"],
              "payload_sha256": digest(hf.arm["payload"]), "schema_valid": None, "expected_match": None,
              "success_diagnostic_manifest_sha256": measurement["manifest_sha256"], "decision_diagnostics": None}

    def checked_memory():
        value = memory()
        if not math.isfinite(value):
            raise ValueError("Memory unavailable")
        return value

    try:
        # Exercise the unchanged application's large-schema admission independently
        # of the frozen-arm equality gate, without any outbound attempt.
        schema = copy.deepcopy(GeneratedAnswer.model_json_schema())
        schema["properties"]["answer"] = {"type": "string", "pattern": _selection_pattern(30)}
        rejected = False
        try:
            super(ReproductionHF, hf)._payload(PILOT_MODEL, "Synthetic large-schema admission check", None, schema,
                                               {"temperature": 0, "num_predict": 512, "num_ctx": 8192})
        except HFGenerationError:
            rejected = hf.attempts == 0
        if not rejected:
            raise ValueError("Large-schema admission differs")
        result["large_schema_preflight_rejected"] = True
        value = checked_memory()
        result["pre_request_free_mib"] = value
        if value < profile["live_margin_mib"]:
            result["category"] = "resource_stop"
        elif RateLimiter(settings).reserve(generation=True):
            result["category"] = "quota_rejected"
        else:
            task = asyncio.create_task(hf.generate(PILOT_MODEL, case["prompt"], system=case["system"],
                                                 response_format=case["schema"], options=options))
            watcher = asyncio.create_task(memory_watch(task, finished, samples, checked_memory))
            generated = await task
            try:
                raw = strict_json(generated.response)
                # Even arms omitting outbound maxItems retain original local checks.
                validate_structured(generated.response, case["schema"])
                if set(case["schema"]["properties"]) == {"relevant_markers"}:
                    result["decision_diagnostics"] = inspect_relevance(raw, case)
                result.update(schema_valid=True, expected_match=raw == case["expected"])
                result["category"] = "passed" if result["expected_match"] else "expected_mismatch"
            except (ValueError, TypeError, KeyError, RecursionError):
                result.update(schema_valid=False, category="schema_invalid")
    except HFTimeoutError:
        result["category"] = "timeout"
    except HFGenerationError as exc:
        result["category"] = ("provider_json_validation" if exc.error_code == "json_validate_failed" else
                              "provider_error" if exc.status_code is not None else "transport_or_response_error")
    except asyncio.CancelledError:
        if not samples or all(sample.get("free_mib", 0) >= 384 for sample in samples):
            raise
        result["category"] = "resource_stop"
    except Exception:
        result["category"] = "transport_or_response_error"
    finally:
        finished.set()
        try:
            if watcher is not None:
                await watcher
        finally:
            request_context.reset(token)
            await hf.aclose()
    calls = [row for rows in hf.ledger.values() for row in rows]
    result.update(outbound_attempts=hf.attempts, calls=calls, work=hosted_work(calls, profile, PILOT_MODEL),
                  error_structure=hf.observer.diagnostics,
                  minimum_free_mib=min((sample["free_mib"] for sample in samples if "free_mib" in sample), default=None))
    return result
