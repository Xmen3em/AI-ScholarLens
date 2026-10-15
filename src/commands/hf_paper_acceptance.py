"""Offline acceptance locks bind full reviewed holdout evidence to current source."""

import hashlib
import json
from pathlib import Path

from src.commands.evaluate_hf_agent import source_hashes
from src.commands.evaluate_retrieval import digest
from src.commands.hf_paper_profile import CEREBRAS_PROFILE, CEREBRAS_TASK_SHA256, load_profile
from src.commands.score_hf_agent import score_run

EVIDENCE_NAMES = {"metadata.json", "completion.json", "qualification.json", "records.jsonl", "reviews.json"}


def _local(path: Path) -> Path:
    path = path.resolve()
    workspace = Path.cwd().resolve()
    if not any(path.is_relative_to(workspace / name) and path != workspace / name
               for name in ("test_output", "tests/test_output")):
        raise ValueError("Acceptance evidence must stay in ignored workspace storage")
    return path


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _accepted(report: dict, metadata: dict, source: Path) -> None:
    model = load_profile()["model_pairs"][0]
    if (report.get("holdout_accepted") is not True or report.get("gate_failures") != []
            or type(report.get("attempts")) is not int or report["attempts"] != 192
            or report.get("hosted_manifest_sha256") != CEREBRAS_TASK_SHA256 or report.get("model") != model
            or metadata.get("split") != "holdout" or metadata.get("hosted_manifest_sha256") != CEREBRAS_TASK_SHA256
            or metadata.get("configuration") != {"model": model, "policy": CEREBRAS_PROFILE}
            or metadata.get("source_sha256") != source_hashes()
            or metadata.get("source_snapshot_sha256") != _sha(source / "state.json")):
        raise ValueError("Complete accepted Cerebras holdout on the current source is required")


def create_acceptance_lock(run: Path, source: Path) -> dict:
    run, source = _local(run), _local(source)
    metadata = json.loads((run / "metadata.json").read_text(encoding="utf-8"))
    reviews = json.loads((run / "reviews.json").read_text(encoding="utf-8"))
    report = score_run(run, source, reviews, profile_name=CEREBRAS_PROFILE)
    _accepted(report, metadata, source)
    report_path = run / "acceptance-report.json"
    if report_path.exists():
        raise ValueError("Acceptance report must be fresh")
    hashes = {name: _sha(run / name) for name in sorted(EVIDENCE_NAMES)}
    with report_path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(report, indent=2) + "\n")
    return {"kind": "hf_cerebras_app_acceptance_v1", "hosted_manifest_sha256": CEREBRAS_TASK_SHA256,
            "model": report["model"], "holdout_accepted": True, "holdout_jobs": 192,
            "holdout_run": str(run), "source_snapshot": str(source), "source_snapshot_sha256": _sha(source / "state.json"),
            "source_sha256": digest(metadata["source_sha256"]), "report_sha256": _sha(report_path), "evidence_sha256": hashes}


def validate_acceptance(lock_path: Path) -> dict:
    path = _local(lock_path)
    lock = json.loads(path.read_text(encoding="utf-8"))
    model = load_profile()["model_pairs"][0]
    if (lock.get("kind") != "hf_cerebras_app_acceptance_v1" or lock.get("hosted_manifest_sha256") != CEREBRAS_TASK_SHA256
            or lock.get("model") != model or lock.get("holdout_accepted") is not True
            or type(lock.get("holdout_jobs")) is not int or lock["holdout_jobs"] != 192
            or set(lock.get("evidence_sha256", {})) != EVIDENCE_NAMES):
        raise ValueError("Unaccepted or unreviewed model lock")
    run, source = _local(Path(lock["holdout_run"])), _local(Path(lock["source_snapshot"]))
    report_path = run / "acceptance-report.json"
    if (_sha(report_path) != lock["report_sha256"] or _sha(source / "state.json") != lock["source_snapshot_sha256"]
            or any(_sha(run / name) != value for name, value in lock["evidence_sha256"].items())):
        raise ValueError("Accepted evidence changed")
    metadata = json.loads((run / "metadata.json").read_text(encoding="utf-8"))
    report = json.loads(report_path.read_text(encoding="utf-8"))
    _accepted(report, metadata, source)
    recalculated = score_run(run, source, json.loads((run / "reviews.json").read_text(encoding="utf-8")), profile_name=CEREBRAS_PROFILE)
    if recalculated != report or digest(metadata["source_sha256"]) != lock["source_sha256"]:
        raise ValueError("Acceptance no longer validates")
    return {**lock, "source_files": metadata["source_sha256"]}
