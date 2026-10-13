"""Diagnostic-only structural observations; no provider content is retained."""

import hashlib
import json
import math
from pathlib import Path

import httpx
from src.commands.evaluate_agent import free_memory_mib
from src.commands.evaluate_retrieval import digest
from src.commands.hf_evaluation import MeasuredHF, load_protocol, qualify, validate_structured
from src.commands.hf_qualification import load_revision
from src.commands.hf_route_comparison import COMPARISON_SHA256, load_comparison
from src.config import Settings
from src.middlewares import RateLimiter
from src.services.hf.client import _unique_object

MAX_ERROR_BYTES = 8192
COUNT_CAP = 31
STRUCTURE_SHA256 = "18119b207cec1a74781361c3b2666d542806763e92f496c6c7b52637b5b2dff7"
DIAGNOSTIC_FIELDS = (
    "body_complete", "body_json_valid", "error_object",
    "failed_generation_present", "failed_generation_string",
    "generated_char_count", "starts_object", "ends_object",
    "code_fence_prefix", "reasoning_prefix", "generation_json_valid",
    "generation_object", "property_count", "required_fields_present",
    "additional_fields_present", "markers_array", "markers_strings",
    "marker_count", "schema_valid", "expected_match",
    "supplied_marker_membership", "duplicate_markers",
)


def reject_constant(value: str) -> None:
    raise ValueError("Nonfinite JSON constant")


def strict_json(content: str):
    return json.loads(content, object_pairs_hook=_unique_object, parse_constant=reject_constant)


def inspect_error(body: bytes, case: dict, *, body_complete: bool = True) -> dict:
    result: dict[str, bool | int | None] = dict.fromkeys(DIAGNOSTIC_FIELDS)
    result["body_complete"] = body_complete and len(body) <= MAX_ERROR_BYTES
    if not result["body_complete"]:
        return result
    try:
        raw = strict_json(body.decode("utf-8"))
    except (ValueError, TypeError, RecursionError):
        result["body_json_valid"] = False
        return result
    result["body_json_valid"] = True
    error = raw.get("error") if type(raw) is dict else None
    result["error_object"] = type(error) is dict
    if type(error) is not dict:
        return result
    result["failed_generation_present"] = "failed_generation" in error
    if not result["failed_generation_present"]:
        return result
    generation = error["failed_generation"]
    result["failed_generation_string"] = type(generation) is str
    if type(generation) is not str:
        return result
    stripped = generation.strip()
    result.update(generated_char_count=min(len(generation), MAX_ERROR_BYTES),
                  starts_object=stripped.startswith("{"), ends_object=stripped.endswith("}"),
                  code_fence_prefix=stripped.startswith("```"),
                  reasoning_prefix=stripped.startswith(("<think>", "<|channel|>analysis", "analysis", "<|start|>assistant")))
    try:
        generated = strict_json(generation)
    except (ValueError, TypeError, RecursionError):
        result["generation_json_valid"] = False
        return result
    result.update(generation_json_valid=True, generation_object=type(generated) is dict,
                  expected_match=generated == case["expected"])
    try:
        validate_structured(generation, case["schema"])
        result["schema_valid"] = True
    except (ValueError, TypeError, KeyError, RecursionError):
        result["schema_valid"] = False
    if type(generated) is not dict:
        return result
    result.update(property_count=min(len(generated), COUNT_CAP),
                  required_fields_present=set(case["schema"]["required"]) <= set(generated),
                  additional_fields_present=bool(set(generated) - set(case["schema"]["properties"])))
    markers = generated.get("relevant_markers")
    result["markers_array"] = type(markers) is list
    if type(markers) is list:
        result.update(marker_count=min(len(markers), COUNT_CAP), markers_strings=all(type(marker) is str for marker in markers))
        if len(markers) <= 30 and result["markers_strings"]:
            result.update(supplied_marker_membership=all(marker in case["supplied_markers"] for marker in markers),
                          duplicate_markers=len(markers) != len(set(markers)))
    return result


def load_structure_protocol(root=Path("evaluation/week7_hf/structure-diagnostic-v1")) -> dict:
    manifest_path = root / "manifest.json"
    if hashlib.sha256(manifest_path.read_bytes()).hexdigest() != STRUCTURE_SHA256:
        raise ValueError("Structural diagnostic manifest differs")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    revision = load_revision()
    load_comparison()
    if (manifest["parent_fixture_manifest_sha256"] != revision["manifest_sha256"]
            or manifest["prior_route_manifest_sha256"] != COMPARISON_SHA256
            or set(manifest["sha256"]) != {"PROTOCOL.md", "profile.json"}):
        raise ValueError("Structural diagnostic parent differs")
    for name, expected in manifest["sha256"].items():
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != expected:
            raise ValueError("Structural diagnostic input differs")
    profile = json.loads((root / "profile.json").read_text(encoding="utf-8"))
    if tuple(profile["diagnostic_fields"]) != DIAGNOSTIC_FIELDS or httpx.__version__ != "0.28.1":
        raise ValueError("Unsupported diagnostic contract or HTTPX version")
    return profile


class BoundedErrorTransport(httpx.AsyncBaseTransport):
    def __init__(self, upstream: httpx.AsyncBaseTransport, case: dict):
        self.upstream, self.case = upstream, case
        self.diagnostics: dict | None = None

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        response = await self.upstream.handle_async_request(request)
        if response.status_code != 400:
            return response
        body = bytearray()
        complete = True
        try:
            async for chunk in response.aiter_bytes(chunk_size=4096):
                if len(body) + len(chunk) > MAX_ERROR_BYTES:
                    complete = False
                    body.clear()
                    break
                body.extend(chunk)
        finally:
            await response.aclose()
        self.diagnostics = inspect_error(bytes(body), self.case, body_complete=complete)
        # Replayed bytes are decoded already; upstream content-encoding/length
        # headers must not be copied. Original error-label handling stays intact.
        return httpx.Response(400, content=bytes(body))

    async def aclose(self) -> None:
        await self.upstream.aclose()


class StructuralHF(MeasuredHF):
    def __init__(self, settings: Settings):
        profile = load_structure_protocol()
        if settings.hf_models != [profile["model"]] or settings.hf_default_model != profile["model"]:
            raise ValueError("Diagnostic requires the approved model/provider")
        super().__init__(settings, outbound_budget=1)
        self.observer = BoundedErrorTransport(self._client._transport, load_revision()["cases"][1])
        # This isolated observer is tied to HTTPX 0.28.1. Delegating the existing
        # transport preserves its TLS, proxy, retry and connection configuration.
        self._client._transport = self.observer


async def diagnose_structure(settings: Settings, *, memory=free_memory_mib) -> dict:
    profile = load_structure_protocol()
    revision = load_revision()
    case = revision["cases"][1]
    hf = StructuralHF(settings)

    def checked_memory():
        value = memory()
        if not math.isfinite(value):
            raise ValueError("Diagnostic memory unavailable")
        return value

    try:
        payload = hf._payload(profile["model"], case["prompt"], case["system"], case["schema"],
                              {"temperature": 0, "num_predict": 256, "num_ctx": 8192})
        del payload["model"]
        qualification = await qualify(hf, load_protocol(), limiter=RateLimiter(settings), memory=checked_memory,
                                      revision={**revision, "cases": [case]})
        return {"kind": profile["kind"], "qualification_accepted": False,
                "diagnostic_manifest_sha256": STRUCTURE_SHA256, "contract_payload_sha256": digest(payload),
                "qualification": qualification, "error_structure": hf.observer.diagnostics,
                "outbound_attempts": hf.attempts}
    finally:
        await hf.aclose()
