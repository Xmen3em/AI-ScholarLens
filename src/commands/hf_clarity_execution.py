"""New approval-bound execution contract for the unchanged offline candidates."""

import hashlib
import json
from pathlib import Path

from src.commands.hf_allowance import PILOT_MODEL
from src.commands.hf_fixture_clarity import CLARITY_SHA256, load_clarity
from src.commands.hf_success_diagnostics import SUCCESS_DIAGNOSTICS_SHA256
from src.commands.hf_validation import memoized_input
from src.services.hf.registry import HF_ROUTER_URL

CLARITY_EXECUTION_SHA256 = "aef8ff44f41dc662dcbe032755d0af014c4c590f98f9b54be79514d206190672"


@memoized_input
def load_execution(root=Path("evaluation/week7_hf/clarity-execution-v1")) -> dict:
    manifest = root / "manifest.json"
    if hashlib.sha256(manifest.read_bytes()).hexdigest() != CLARITY_EXECUTION_SHA256:
        raise ValueError("Clarity execution manifest differs")
    binding = json.loads(manifest.read_text(encoding="utf-8"))
    candidate = load_clarity()
    if (
        binding["candidate_manifest_sha256"] != CLARITY_SHA256
        or binding["measurement_manifest_sha256"] != SUCCESS_DIAGNOSTICS_SHA256
        or set(binding["sha256"]) != {"PROTOCOL.md", "profile.json"}
    ):
        raise ValueError("Clarity execution parent differs")
    for name, expected in binding["sha256"].items():
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != expected:
            raise ValueError("Clarity execution input differs")
    profile = json.loads((root / "profile.json").read_text(encoding="utf-8"))
    if (
        profile["model"] != PILOT_MODEL
        or profile["endpoint"] != HF_ROUTER_URL
        or type(profile["maximum_outbound_attempts"]) is not int
        or profile["maximum_outbound_attempts"] != 2
        or profile["arms"] != ["clarity-positive", "clarity-negative"]
        or list(candidate["arms"]) != profile["arms"]
    ):
        raise ValueError("Clarity execution scope differs")
    return {
        **profile,
        "arms": candidate["arms"],
        "manifest_sha256": CLARITY_EXECUTION_SHA256,
        "candidate_manifest_sha256": CLARITY_SHA256,
        "measurement_manifest_sha256": SUCCESS_DIAGNOSTICS_SHA256,
    }
