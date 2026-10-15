"""Frozen five-case execution of the unchanged synthetic qualification fixtures."""

import hashlib
import json
from pathlib import Path

from src.commands.hf_allowance import PILOT_MODEL
from src.commands.hf_clarity_execution import CLARITY_EXECUTION_SHA256
from src.commands.hf_clarity_execution import load_execution as load_clarity_execution
from src.commands.hf_evaluation import HF_MANIFEST_SHA256, load_protocol
from src.commands.hf_qualification import load_revision
from src.services.hf.registry import HF_ROUTER_URL

SCHEMA_EXECUTION_SHA256 = "51a6c389b97a4668439bfa2ecdf12258ecb866a164c610829d20c03ef11af32c"
ALTERNATIVE_SHA256 = "507ed295c7b59b5bb57e1a4f87569ec129b19c1092c297a992695484d56dc820"
ALTERNATIVE_MODEL = "openai/gpt-oss-120b:fireworks-ai"
CEREBRAS_SHA256 = "7513c590330757c45c023c7c202c94e4b03b7c35af7c1126e0390044b02aeb0a"
CEREBRAS_MODEL = "openai/gpt-oss-120b:cerebras"


def load_execution(root=Path("evaluation/week7_hf/schema-execution-v1")) -> dict:
    manifest = root / "manifest.json"
    if hashlib.sha256(manifest.read_bytes()).hexdigest() != SCHEMA_EXECUTION_SHA256:
        raise ValueError("Schema execution manifest differs")
    binding = json.loads(manifest.read_text(encoding="utf-8"))
    revision = load_revision()
    load_protocol()
    load_clarity_execution()
    if (
        binding["qualification_manifest_sha256"] != revision["manifest_sha256"]
        or binding["hosted_manifest_sha256"] != HF_MANIFEST_SHA256
        or binding["clarity_execution_manifest_sha256"] != CLARITY_EXECUTION_SHA256
        or set(binding["sha256"]) != {"PROTOCOL.md", "requests.json"}
    ):
        raise ValueError("Schema execution parent differs")
    for name, expected in binding["sha256"].items():
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != expected:
            raise ValueError("Frozen schema execution input differs")
    profile = json.loads((root / "requests.json").read_text(encoding="utf-8"))
    if (
        profile["model"] != PILOT_MODEL
        or profile["endpoint"] != HF_ROUTER_URL
        or type(profile["maximum_outbound_attempts"]) is not int
        or profile["maximum_outbound_attempts"] != 5
        or profile["arms"] != [case["id"] for case in revision["cases"]]
        or len(profile["payloads"]) != 5
    ):
        raise ValueError("Schema execution scope differs")
    return {**profile, "cases": revision["cases"], "manifest_sha256": SCHEMA_EXECUTION_SHA256,
            "qualification_manifest_sha256": revision["manifest_sha256"]}


def load_alternative(root=Path("evaluation/week7_hf/provider-alternative-v1")) -> dict:
    manifest = root / "manifest.json"
    if hashlib.sha256(manifest.read_bytes()).hexdigest() != ALTERNATIVE_SHA256:
        raise ValueError("Provider alternative manifest differs")
    binding = json.loads(manifest.read_text(encoding="utf-8"))
    original = load_execution()
    if (binding["parent_schema_execution_sha256"] != original["manifest_sha256"]
            or binding["qualification_manifest_sha256"] != original["qualification_manifest_sha256"]
            or set(binding["sha256"]) != {"PROTOCOL.md", "requests.json"}):
        raise ValueError("Provider alternative parent differs")
    for name, expected in binding["sha256"].items():
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != expected:
            raise ValueError("Frozen provider alternative input differs")
    profile = json.loads((root / "requests.json").read_text(encoding="utf-8"))
    if (profile["model"] != ALTERNATIVE_MODEL or profile["endpoint"] != original["endpoint"]
            or type(profile["maximum_outbound_attempts"]) is not int or profile["maximum_outbound_attempts"] != 5
            or profile["arms"] != original["arms"]
            or profile["payloads"] != [{**payload, "model": ALTERNATIVE_MODEL} for payload in original["payloads"]]):
        raise ValueError("Provider alternative changes more than the frozen provider")
    return {**profile, "cases": original["cases"], "manifest_sha256": ALTERNATIVE_SHA256,
            "qualification_manifest_sha256": original["qualification_manifest_sha256"]}


def load_experiment(experiment: str) -> dict:
    if experiment == "schema-execution-v1":
        return load_execution()
    if experiment == "provider-alternative-v1":
        return load_alternative()
    if experiment == "cerebras-remaining-v1":
        return load_cerebras()
    raise ValueError("Unknown frozen schema experiment")


def load_cerebras(root=Path("evaluation/week7_hf/cerebras-remaining-v1")) -> dict:
    manifest = root / "manifest.json"
    if hashlib.sha256(manifest.read_bytes()).hexdigest() != CEREBRAS_SHA256:
        raise ValueError("Remaining Cerebras manifest differs")
    binding = json.loads(manifest.read_text(encoding="utf-8"))
    original = load_execution()
    if (binding["parent_schema_execution_sha256"] != original["manifest_sha256"]
            or binding["qualification_manifest_sha256"] != original["qualification_manifest_sha256"]
            or set(binding["sha256"]) != {"PROTOCOL.md", "requests.json"}):
        raise ValueError("Remaining Cerebras parent differs")
    for name, expected in binding["sha256"].items():
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != expected:
            raise ValueError("Frozen remaining Cerebras input differs")
    profile = json.loads((root / "requests.json").read_text(encoding="utf-8"))
    if (profile["model"] != CEREBRAS_MODEL or profile["endpoint"] != original["endpoint"]
            or type(profile["maximum_outbound_attempts"]) is not int or profile["maximum_outbound_attempts"] != 3
            or profile["arms"] != original["arms"][:3]
            or profile["payloads"] != [{**payload, "model": CEREBRAS_MODEL} for payload in original["payloads"][:3]]):
        raise ValueError("Remaining Cerebras scope differs")
    return {**profile, "cases": original["cases"][:3], "manifest_sha256": CEREBRAS_SHA256,
            "qualification_manifest_sha256": original["qualification_manifest_sha256"]}


def measurement_profile(experiment: str) -> dict:
    profile = load_protocol()
    if experiment == "cerebras-remaining-v1":
        candidate = load_cerebras()
        profile["prices_per_million"] = {**profile["prices_per_million"], candidate["model"]: candidate["prices_per_million"]}
    return profile
