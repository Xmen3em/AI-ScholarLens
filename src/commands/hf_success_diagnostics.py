"""Fixed flags and bounded counts for validated relevance decisions; no generated text."""

import hashlib
import json
from pathlib import Path

from src.commands.hf_qualification import decision_diagnostics

SUCCESS_DIAGNOSTICS_SHA256 = "48b46935a42a5dd7931c8a36c5b7bcfefe5f405c62791667d14ba251190169b7"
BOOLEAN_FIELDS = ("expected_match", "expected_empty", "returned_empty", "supplied_marker_membership", "duplicate_markers")
COUNT_FIELDS = ("marker_count", "expected_marker_count", "missing_expected_marker_count", "unexpected_marker_count")


def load_success_contract(root=Path("evaluation/week7_hf/success-diagnostics-v1")) -> dict:
    from src.commands.hf_reproduction import PROMPT_COMPARISON_SHA256, load_prompt_comparison

    manifest = root / "manifest.json"
    if hashlib.sha256(manifest.read_bytes()).hexdigest() != SUCCESS_DIAGNOSTICS_SHA256:
        raise ValueError("Success measurement manifest differs")
    binding = json.loads(manifest.read_text(encoding="utf-8"))
    load_prompt_comparison()
    if binding["parent_prompt_manifest_sha256"] != PROMPT_COMPARISON_SHA256 or set(binding["sha256"]) != {
        "PROTOCOL.md",
        "profile.json",
    }:
        raise ValueError("Success measurement parent differs")
    for name, expected in binding["sha256"].items():
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != expected:
            raise ValueError("Success measurement input differs")
    profile = json.loads((root / "profile.json").read_text(encoding="utf-8"))
    if profile != {
        "kind": "bounded_relevance_decision_measurements",
        "boolean_fields": list(BOOLEAN_FIELDS),
        "count_fields": list(COUNT_FIELDS),
        "count_limit": 30,
    }:
        raise ValueError("Success measurement fields differ")
    return {**profile, "manifest_sha256": SUCCESS_DIAGNOSTICS_SHA256}


def _markers(raw) -> list[str]:
    if type(raw) is not dict or set(raw) != {"relevant_markers"}:
        raise ValueError("Invalid relevance diagnostic shape")
    markers = raw["relevant_markers"]
    if type(markers) is not list or len(markers) > 30 or any(type(marker) is not str for marker in markers):
        raise ValueError("Invalid relevance diagnostic markers")
    return markers


def inspect_relevance(raw, case: dict) -> dict:
    markers = _markers(raw)
    expected = _markers(case.get("expected"))
    supplied = _markers({"relevant_markers": case.get("supplied_markers")})
    if len(set(supplied)) != len(supplied) or len(set(expected)) != len(expected) or not set(expected) <= set(supplied):
        raise ValueError("Invalid relevance diagnostic fixture")
    result = decision_diagnostics(raw, case)
    result.update(
        expected_empty=not expected,
        returned_empty=not markers,
        expected_marker_count=len(expected),
        missing_expected_marker_count=len(set(expected) - set(markers)),
        unexpected_marker_count=len(set(markers) - set(expected)),
    )
    return result
