"""Two predeclared, isolated HF/Groq routes over the exact same synthetic contract."""

import hashlib
import json
import math
from pathlib import Path

import httpx
from src.commands.evaluate_agent import free_memory_mib
from src.commands.evaluate_retrieval import digest
from src.commands.hf_allowance import PILOT_MODEL
from src.commands.hf_evaluation import MeasuredHF, load_protocol, qualify
from src.commands.hf_qualification import load_revision
from src.config import Settings
from src.middlewares import RateLimiter

COMPARISON_SHA256 = "d68d2a7e37bead8df18de30dab7033fa3b6fd208bb7187202097bdc6a6ae963c"
RELAY_BASE = "https://router.huggingface.co/groq/openai/v1/"
PROVIDER_MODEL = "openai/gpt-oss-120b"


def load_comparison(root=Path("evaluation/week7_hf/route-comparison-v1")) -> dict:
    manifest_path = root / "manifest.json"
    if hashlib.sha256(manifest_path.read_bytes()).hexdigest() != COMPARISON_SHA256:
        raise ValueError("Route comparison manifest differs")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    revision = load_revision()
    if manifest["parent_fixture_manifest_sha256"] != revision["manifest_sha256"]:
        raise ValueError("Route comparison fixture differs")
    if set(manifest["sha256"]) != {"sources.json", "profile.json", "PROTOCOL.md"}:
        raise ValueError("Route comparison omits provenance")
    for name, expected in manifest["sha256"].items():
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != expected:
            raise ValueError("Frozen route comparison differs")
    profile = json.loads((root / "profile.json").read_text(encoding="utf-8"))
    sources = json.loads((root / "sources.json").read_text(encoding="utf-8"))
    verify_mapping(sources["groq_mapping"])
    return {**profile, "manifest_sha256": COMPARISON_SHA256, "sources": sources}


def verify_mapping(row: dict) -> None:
    if (row.get("providerId") != PROVIDER_MODEL or row.get("status") != "live"
            or row.get("task") != "conversational"):
        raise ValueError("HF/Groq provider mapping changed")


class RouteHF(MeasuredHF):
    def __init__(self, settings: Settings, *, route: str):
        profile = load_comparison()
        if type(route) is not str or route not in profile["route_order"]:
            raise ValueError("Only the two fixed HF routes are permitted")
        if settings.hf_models != [PILOT_MODEL] or settings.hf_default_model != PILOT_MODEL:
            raise ValueError("Route comparison requires the pinned Groq pair")
        super().__init__(settings, outbound_budget=1)
        self.route = route
        if route == "provider-relay":
            # Official HF SDK provider helper, pinned in the comparison sources.
            # Keep the inherited authentication, timeout, TLS and no-redirect/proxy settings.
            self._client.base_url = httpx.URL(RELAY_BASE)

    def _payload(self, model, prompt, system, response_format, options):
        payload = super()._payload(model, prompt, system, response_format, options)
        if self.route == "provider-relay":
            # The verified provider ID is shorter; inherited byte admission remains conservative.
            payload["model"] = PROVIDER_MODEL
        return payload


async def compare_routes(settings: Settings, *, memory=free_memory_mib) -> dict:
    comparison, revision, profile = load_comparison(), load_revision(), load_protocol()
    selected = {**revision, "cases": [revision["cases"][1]]}
    case = selected["cases"][0]
    limiter = RateLimiter(settings)
    arms: list[dict] = []
    outbound = 0
    stop = None

    def inspected_memory():
        value = memory()
        if not math.isfinite(value):
            raise OSError("Memory inspection unavailable")
        return value

    for route in comparison["route_order"]:
        try:
            headroom = inspected_memory()
        except Exception:
            stop = "pre_arm_memory_unavailable"
            break
        if headroom < profile["live_margin_mib"]:
            stop = "pre_arm_resource_floor"
            break
        client = RouteHF(settings, route=route)
        try:
            payload = client._payload(PILOT_MODEL, case["prompt"], case["system"], case["schema"],
                {"temperature": 0, "num_predict": 256, "num_ctx": 8192})
            normalized = {key: value for key, value in payload.items() if key != "model"}
            probe = await qualify(client, profile, limiter=limiter, memory=inspected_memory, revision=selected)
            arms.append({"route": route, "endpoint": str(client._client.base_url) + "chat/completions",
                         "wire_model": payload["model"], "contract_payload_sha256": digest(normalized),
                         "qualification_probe": probe})
            checks = probe["checks"]
            minimum = [check["minimum_free_mib"] for check in checks]
            errors = {check.get("error_class") for check in checks}
            errors.update(call.get("error_class") for check in checks for call in check["calls"])
            transport_unknown = any(call.get("error_class") == "HFGenerationError" and call.get("provider_status") is None
                                    for check in checks for call in check["calls"])
            if (not checks or client.attempts != 1 or any(value is None or value < profile["live_margin_mib"] for value in minimum)
                    or transport_unknown or errors & {"HFTimeoutError", "CancelledError", "QualificationResourceStop"}):
                stop = "uncertain_or_resource_work"
        finally:
            outbound += client.attempts
            await client.aclose()
        if stop:
            break
    return {"kind": "route_comparison_only", "comparison_manifest_sha256": comparison["manifest_sha256"],
            "fixture_manifest_sha256": revision["manifest_sha256"], "qualification_accepted": False,
            "arms": arms, "outbound_attempts": outbound, "stop_reason": stop}
