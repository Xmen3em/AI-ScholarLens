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

CEREBRAS_TASK_SHA256 = "e871096c69e83dc6d1a29cdf100a4505e613ab8014e22727c8be13e613d855f5"
CEREBRAS_PROFILE = "hosted-cerebras-v1"


def load_profile(root=Path("evaluation/week7_hf/cerebras-evaluation-v1")) -> dict:
    manifest_path = root / "manifest.json"
    if hashlib.sha256(manifest_path.read_bytes()).hexdigest() != CEREBRAS_TASK_SHA256:
        raise ValueError("Cerebras task profile manifest differs")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    original, controller, selectors = load_protocol(), load_cerebras(), load_selectors()
    if (manifest["version"] != CEREBRAS_PROFILE or manifest["parent_hosted_manifest_sha256"] != HF_MANIFEST_SHA256
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
    expected = {**original, "version": CEREBRAS_PROFILE, "model_pairs": [controller["model"]],
                "prices_per_million": {controller["model"]: controller["prices_per_million"]}}
    if digest(profile) != digest(expected):
        raise ValueError("Cerebras task profile changes an inherited gate")
    return profile


def get_profile(name="hosted-agent-v1") -> tuple[dict, str]:
    if name == "hosted-agent-v1":
        return load_protocol(), HF_MANIFEST_SHA256
    if name == CEREBRAS_PROFILE:
        return load_profile(), CEREBRAS_TASK_SHA256
    raise ValueError("Unknown frozen hosted profile")


def plan_collection(snapshot: Path, *, split="development") -> dict:
    if split not in {"development", "holdout"}:
        raise ValueError("Unknown Cerebras task split")
    profile = load_profile()
    _, labels, _, _ = load_labels(Path("evaluation/week7_agent"), snapshot)
    jobs = build_jobs(labels[split]["cases"])
    if len(jobs) != profile[f"{split}_jobs"]:
        raise ValueError("Complete frozen comparison matrix is required")
    budget = profile["qualification_calls"] + sum(6 if job["path"] == "agent" else 2 for job in jobs)
    controller = load_cerebras()
    return {"status": "offline_plan", "inference_started": False, "created_unix": time.time(),
            "manifest_sha256": MANIFEST_SHA256, "hosted_manifest_sha256": CEREBRAS_TASK_SHA256,
            "parent_hosted_manifest_sha256": HF_MANIFEST_SHA256,
            "fixture_manifest_sha256": controller["qualification_manifest_sha256"],
            "source_snapshot_sha256": hashlib.sha256((snapshot / "state.json").read_bytes()).hexdigest(),
            "split": split, "configuration": {"model": controller["model"], "policy": CEREBRAS_PROFILE},
            "jobs": [{key: value for key, value in job.items() if key != "query"} for job in jobs],
            "source_sha256": source_hashes(), "outbound_budget": 0, "approved_outbound_budget": 0,
            "planned_outbound_budget": budget, "proposed_outbound_budget": budget,
            "paper_collection_planned": True, "app_accepted": False}
