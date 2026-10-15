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
