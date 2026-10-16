"""Additive frozen Cerebras task profile and complete offline comparison plans."""

import hashlib
import json
import time
from pathlib import Path

from src.commands.agent_collection import build_jobs
from src.commands.evaluate_agent import MANIFEST_SHA256, load_labels
from src.commands.evaluate_hf_agent import source_hashes
from src.commands.evaluate_retrieval import digest
from src.commands.hf_evaluation import HF_MANIFEST_SHA256, load_protocol
from src.commands.hf_schema_execution import load_cerebras, load_selectors

LEGACY_CEREBRAS_TASK_SHA256 = "e871096c69e83dc6d1a29cdf100a4505e613ab8014e22727c8be13e613d855f5"
CEREBRAS_TASK_SHA256 = "92ec9996534e5a958d4ead38fa9224b83ce6c3a318ca3919d886decaeba2558d"
CEREBRAS_PROFILE = "hosted-cerebras-tokenized-v2"
EVIDENCE_PROFILE = "hosted-cerebras-evidence-v3"
EVIDENCE_TASK_SHA256 = "2dc8ab7bb2dd98c544d06b80d5b41873a7e3399e04af9375d332829719c6c23b"
PAPER_PROFILES = (CEREBRAS_PROFILE, EVIDENCE_PROFILE)


def load_legacy_profile(root=Path("evaluation/week7_hf/cerebras-evaluation-v1")) -> dict:
    manifest_path = root / "manifest.json"
    if hashlib.sha256(manifest_path.read_bytes()).hexdigest() != LEGACY_CEREBRAS_TASK_SHA256:
        raise ValueError("Cerebras task profile manifest differs")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    original, controller, selectors = load_protocol(), load_cerebras(), load_selectors()
    if (manifest["version"] != "hosted-cerebras-v1" or manifest["parent_hosted_manifest_sha256"] != HF_MANIFEST_SHA256
            or manifest["local_manifest_sha256"] != MANIFEST_SHA256
            or manifest["qualification_manifest_sha256"] != controller["qualification_manifest_sha256"]
            or manifest["controller_manifest_sha256"] != controller["manifest_sha256"]
            or manifest["selector_manifest_sha256"] != selectors["manifest_sha256"]
            or set(manifest["sha256"]) != {"PROTOCOL.md", "profile.json"}):
        raise ValueError("Cerebras task profile parent differs")
    for name, expected in manifest["sha256"].items():
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != expected:
            raise ValueError("Frozen Cerebras task input differs")
    profile = json.loads((root / "profile.json").read_text(encoding="utf-8"))
    expected = {**original, "version": "hosted-cerebras-v1", "model_pairs": [controller["model"]],
                "prices_per_million": {controller["model"]: controller["prices_per_million"]}}
    if digest(profile) != digest(expected):
        raise ValueError("Cerebras task profile changes an inherited gate")
    return profile


def load_profile(root=Path("evaluation/week7_hf/cerebras-tokenized-v2")) -> dict:
    manifest_path = root / "manifest.json"
    if hashlib.sha256(manifest_path.read_bytes()).hexdigest() != CEREBRAS_TASK_SHA256:
        raise ValueError("Tokenized Cerebras manifest differs")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (manifest.get("version") != CEREBRAS_PROFILE
            or manifest.get("parent_cerebras_manifest_sha256") != LEGACY_CEREBRAS_TASK_SHA256
            or manifest.get("parent_hosted_manifest_sha256") != HF_MANIFEST_SHA256
            or manifest.get("local_manifest_sha256") != MANIFEST_SHA256
            or manifest.get("qualification_manifest_sha256") != load_cerebras()["qualification_manifest_sha256"]
            or manifest.get("controller_manifest_sha256") != load_cerebras()["manifest_sha256"]
            or manifest.get("selector_manifest_sha256") != load_selectors()["manifest_sha256"]
            or set(manifest.get("sha256", {})) != {"PROTOCOL.md", "profile.json"}):
        raise ValueError("Tokenized Cerebras parent differs")
    for name, expected in manifest["sha256"].items():
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != expected:
            raise ValueError("Frozen tokenized Cerebras input differs")
    profile = json.loads((root / "profile.json").read_text(encoding="utf-8"))
    expected = {**load_legacy_profile(), "version": CEREBRAS_PROFILE, "input_admission": {
        "method": "o200k_ordinary_schema_inclusive_v1", "encoding": "o200k_harmony",
        "vocabulary_sha256": "446a9538cb6c348e3516120d7c08b09f57c36495e2acfffe59a5bf8b0cfb1a2d",
        "maximum_payload_bytes": 65536, "maximum_schema_bytes": 7168}}
    if digest(profile) != digest(expected):
        raise ValueError("Tokenized Cerebras profile changes an inherited gate")
    return profile


def load_evidence_profile(root=Path("evaluation/week7_hf/cerebras-evidence-v3")) -> dict:
    manifest_path = root / "manifest.json"
    if hashlib.sha256(manifest_path.read_bytes()).hexdigest() != EVIDENCE_TASK_SHA256:
        raise ValueError("Evidence catalog manifest differs")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (manifest.get("version") != EVIDENCE_PROFILE
            or manifest.get("parent_tokenized_manifest_sha256") != CEREBRAS_TASK_SHA256
            or set(manifest.get("sha256", {})) != {"PROTOCOL.md", "profile.json"}):
        raise ValueError("Evidence catalog parent differs")
    for name, expected in manifest["sha256"].items():
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != expected:
            raise ValueError("Frozen evidence catalog input differs")
    profile = json.loads((root / "profile.json").read_text(encoding="utf-8"))
    expected = {**load_profile(), "version": EVIDENCE_PROFILE, "candidates_per_passage": 3, "max_sentence_candidates": 10}
    if digest(profile) != digest(expected):
        raise ValueError("Evidence catalog changes an inherited gate")
    return profile


def get_profile(name="hosted-agent-v1") -> tuple[dict, str]:
    if name == "hosted-agent-v1":
        return load_protocol(), HF_MANIFEST_SHA256
    if name == "hosted-cerebras-v1":
        return load_legacy_profile(), LEGACY_CEREBRAS_TASK_SHA256
    if name == CEREBRAS_PROFILE:
        return load_profile(), CEREBRAS_TASK_SHA256
    if name == EVIDENCE_PROFILE:
        return load_evidence_profile(), EVIDENCE_TASK_SHA256
    raise ValueError("Unknown frozen hosted profile")


def get_profile_by_manifest(manifest_sha256: str) -> dict:
    for name in PAPER_PROFILES:
        profile, registered = get_profile(name)
        if registered == manifest_sha256:
            return profile
    raise ValueError("Unknown funded profile manifest")


def plan_collection(snapshot: Path, *, split="development", profile_name=CEREBRAS_PROFILE) -> dict:
    if split not in {"development", "holdout"} or profile_name not in PAPER_PROFILES:
        raise ValueError("Unknown Cerebras task split")
    profile, manifest_sha = get_profile(profile_name)
    _, labels, _, _ = load_labels(Path("evaluation/week7_agent"), snapshot)
    jobs = build_jobs(labels[split]["cases"])
    if len(jobs) != profile[f"{split}_jobs"]:
        raise ValueError("Complete frozen comparison matrix is required")
    budget = profile["qualification_calls"] + sum(6 if job["path"] == "agent" else 2 for job in jobs)
    controller = load_cerebras()
    return {"status": "offline_plan", "inference_started": False, "created_unix": time.time(),
            "manifest_sha256": MANIFEST_SHA256, "hosted_manifest_sha256": manifest_sha,
            "parent_hosted_manifest_sha256": HF_MANIFEST_SHA256,
            "fixture_manifest_sha256": controller["qualification_manifest_sha256"],
            "source_snapshot_sha256": hashlib.sha256((snapshot / "state.json").read_bytes()).hexdigest(),
            "split": split, "configuration": {"model": controller["model"], "policy": profile_name},
            "jobs": [{key: value for key, value in job.items() if key != "query"} for job in jobs],
            "source_sha256": source_hashes(), "outbound_budget": 0, "approved_outbound_budget": 0,
            "planned_outbound_budget": budget, "proposed_outbound_budget": budget,
            "paper_collection_planned": True, "app_accepted": False}
