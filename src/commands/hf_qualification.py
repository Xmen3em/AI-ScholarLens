"""Frozen synthetic qualification inputs and content-free mismatch diagnostics."""

import hashlib
import json
from pathlib import Path

from src.services.agent import CONTROLLER_SYSTEM

REVISION_SHA256 = "762bbc82e159bd873d41185059bcb838a641b4fa81d8636805b1eec1417a6464"


def load_revision(root=Path("evaluation/week7_hf/qualification-v2")) -> dict:
    from src.commands.hf_evaluation import HF_MANIFEST_SHA256, qualification_cases

    manifest_path = root / "manifest.json"
    if hashlib.sha256(manifest_path.read_bytes()).hexdigest() != REVISION_SHA256:
        raise ValueError("Qualification manifest differs")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest["parent_manifest_sha256"] != HF_MANIFEST_SHA256 or set(manifest["sha256"]) != {"fixtures.json", "PROTOCOL.md"}:
        raise ValueError("Qualification parent differs")
    for name, expected in manifest["sha256"].items():
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != expected:
            raise ValueError("Frozen qualification input differs")
    revision = json.loads((root / "fixtures.json").read_text(encoding="utf-8"))
    original = qualification_cases()
    if len(revision["cases"]) != len(original):
        raise ValueError("Qualification count differs")
    for case, expected in zip(revision["cases"], original, strict=True):
        if any(case[key] != expected[key] for key in ("id", "schema", "expected")):
            raise ValueError("Canonical qualification contract differs")
    if any(case["system"] != CONTROLLER_SYSTEM for case in revision["cases"][:3]):
        raise ValueError("Controller system differs")
    return {**revision, "manifest_sha256": REVISION_SHA256}


def decision_diagnostics(raw: dict, case: dict) -> dict:
    result: dict[str, bool | int] = {"expected_match": case["expected"] is None or raw == case["expected"]}
    if "relevant_markers" in raw:
        markers = raw["relevant_markers"]
        if type(markers) is not list or len(markers) > 30 or any(type(marker) is not str for marker in markers):
            raise ValueError("Invalid diagnostic input")
        result.update(supplied_marker_membership=all(marker in case["supplied_markers"] for marker in markers),
                      duplicate_markers=len(set(markers)) != len(markers), marker_count=len(markers))
    return result
