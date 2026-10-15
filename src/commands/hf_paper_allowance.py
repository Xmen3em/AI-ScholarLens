"""Explicit development funding; historical grants and proofs remain read-only."""

import copy
import hashlib
import json
import os
import re
import sqlite3
from contextlib import closing
from pathlib import Path

from src.commands.evaluate_retrieval import digest
from src.commands.hf_allowance import transaction
from src.commands.hf_cerebras_selectors import CONTROLLER_APPROVAL, CONTROLLER_RUN, SELECTOR_ALLOWANCE_PATH
from src.commands.hf_cerebras_selectors import approval_proposal as selector_proposal
from src.commands.hf_paper_profile import CEREBRAS_PROFILE, CEREBRAS_TASK_SHA256, load_profile, plan_collection
from src.commands.hf_schema_execution import load_cerebras

SCHEMA_REPORT = Path("tests/test_output/hf-cerebras-five-case-summary-20261015-01/report.json")
SCHEMA_REPORT_SHA256 = "3c4e2045f46c4d21ac30f50ffdec4d3da7880068498319dc9f459bd3a0caef0d"
SELECTOR_RUN = Path("tests/test_output/hf-cerebras-selectors-live-20261015-02")
SELECTOR_APPROVAL = Path("tests/test_output/hf-cerebras-selectors-execution-20261015-01/approval.json")
DEVELOPMENT_ALLOWANCE = Path("tests/test_output/hf-cerebras-development-allowance-20261015/allowance.sqlite3")
HOLDOUT_ALLOWANCE = Path("tests/test_output/hf-cerebras-holdout-allowance-20261015/allowance.sqlite3")


def schema_history_binding(*, report_path=SCHEMA_REPORT, selector_path=SELECTOR_ALLOWANCE_PATH,
                           selector_run=SELECTOR_RUN, selector_approval=SELECTOR_APPROVAL,
                           controller_run=CONTROLLER_RUN, controller_approval=CONTROLLER_APPROVAL, **parents) -> str:
    """Verify the pinned historical proof, not a qualification of new source."""
    report_path, path = Path(report_path), Path(selector_path)
    if hashlib.sha256(report_path.read_bytes()).hexdigest() != SCHEMA_REPORT_SHA256:
        raise ValueError("Retained five-case proof differs")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    expected = selector_proposal(controller_run=controller_run, controller_approval=controller_approval, **parents)
    expected.update(status="approved", authorization_source="explicit_user_approval")
    signature = digest(expected)
    approval, run = Path(selector_approval), Path(selector_run)
    if (digest(json.loads(approval.read_text(encoding="utf-8"))) != signature
            or path.with_suffix(".registered").read_text(encoding="utf-8") != signature):
        raise ValueError("Retained selector approval differs")
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        seeds = db.execute("SELECT signature FROM seed").fetchall()
        rows = db.execute("SELECT arm,run,used FROM arms ORDER BY arm").fetchall()
    if (seeds != [(signature,)] or [row[0] for row in rows] != ["selector-1", "selector-10"]
            or any(row[1] != str(run.resolve()) or type(row[2]) is not int or row[2] != 1 for row in rows)):
        raise ValueError("Complete exhausted selector accounting is required")
    accounting = digest({"seed": signature, "arms": rows, "sqlite_sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    evidence_paths = {str(item) for directory, receipt in ((Path(controller_run), Path(controller_approval)), (run, approval))
                      for item in (directory / "metadata.json", directory / "qualification.json", receipt)}
    if (report.get("kind") != "hf_cerebras_five_case_evidence_v1" or report.get("five_schema_cases_verified") is not True
            or report.get("app_accepted") is not False or report.get("task_evaluation_accepted") is not False
            or report.get("model") != load_cerebras()["model"]
            or report.get("cases") != ["scope", "relevance", "rewrite", "selector-1", "selector-10"]
            or type(report.get("outbound_attempts")) is not int or report["outbound_attempts"] != 5
            or report.get("complete_controller_history_binding") != expected["complete_controller_history_binding"]
            or report.get("selector_approval_sha256") != signature or report.get("selector_accounting_sha256") != accounting
            or set(report.get("evidence_sha256", {})) != evidence_paths
            or any(hashlib.sha256(Path(name).read_bytes()).hexdigest() != value
                   for name, value in report["evidence_sha256"].items())):
        raise ValueError("Historical five-case evidence or accounting differs")
    return digest({"report_sha256": SCHEMA_REPORT_SHA256, "selector_accounting": accounting,
                   "controller_history": expected["complete_controller_history_binding"]})


def _scope(metadata: dict) -> dict:
    profile, cases = load_profile(), load_cerebras()
    split = metadata.get("split")
    if split not in {"development", "holdout"}:
        raise ValueError("Unknown paper scope")
    jobs = metadata.get("jobs", [])
    count = profile[f"{split}_jobs"]
    budget = 5 + count // 2 * 8
    if (metadata.get("hosted_manifest_sha256") != CEREBRAS_TASK_SHA256
            or metadata.get("configuration") != {"model": cases["model"], "policy": CEREBRAS_PROFILE}
            or metadata.get("fixture_manifest_sha256") != cases["qualification_manifest_sha256"]
            or len(jobs) != count or len({job["key"] for job in jobs}) != len(jobs)
            or sum(job["path"] == "agent" for job in jobs) != count // 2
            or sum(job["path"] == "baseline" for job in jobs) != count // 2
            or type(metadata.get("planned_outbound_budget")) is not int or metadata["planned_outbound_budget"] != budget):
        raise ValueError("Complete Cerebras task scope is required")
    selection = metadata.get("selection_lock")
    if split == "holdout" and (type(selection) is not dict or metadata.get("selection_sha256") != digest(selection)):
        raise ValueError("Holdout requires a bound development selection")
    return {"hosted_manifest_sha256": CEREBRAS_TASK_SHA256, "model": cases["model"], "split": split,
            "qualification_manifest_sha256": cases["qualification_manifest_sha256"],
            "jobs_sha256": digest(jobs), "source_sha256": digest(metadata["source_sha256"]),
            "source_snapshot_sha256": metadata["source_snapshot_sha256"], "maximum_outbound_attempts": budget,
            **({"selection_sha256": metadata["selection_sha256"]} if split == "holdout" else {})}


def approval_proposal(metadata: dict) -> dict:
    scope = _scope(metadata)
    split, budget = scope["split"], scope["maximum_outbound_attempts"]
    return {"kind": f"hf_cerebras_{split}_approval_v1", "status": "pending_user_approval", "authorization_source": None,
            **scope, "paper_data_planned": True, "exhausted_history_binding": schema_history_binding(),
            "scope": f"At most {budget} HF/Cerebras attempts for five unchanged fresh synthetic qualifications and the complete "
                     f"{len(metadata['jobs'])}-job {split} comparison on the retained public papers. Send only the bounded questions and "
                     "public paper contexts required by these jobs. Failed or uncertain attempts count. Stop on failed "
                     "qualification, schema, attribution, accounting, source, usage or resource checks and uncertain work. "
                     "No retry of a stopped run, provider fallback, spending outside this split or app/Telegram activation."}


def _selection_files(selection: dict) -> None:
    run = Path(selection["development_run"]).resolve()
    roots = [(Path.cwd() / name).resolve() for name in ("test_output", "tests/test_output")]
    names = {"metadata.json", "completion.json", "qualification.json", "records.jsonl", "reviews.json"}
    if (not any(run.is_relative_to(root) and run != root for root in roots)
            or set(selection.get("evidence_sha256", {})) != names):
        raise ValueError("Selection evidence paths differ")
    hashes = {**selection["evidence_sha256"], "selection-report.json": selection["report_sha256"]}
    if any(hashlib.sha256((run / name).read_bytes()).hexdigest() != value for name, value in hashes.items()):
        raise ValueError("Locked development evidence changed")


def validate_task_accounting(metadata: dict, run: Path, completion: dict, *, path=None) -> str:
    """Validate completed grant evidence without constructing or repairing a grant."""
    scope = _scope(metadata)
    details = metadata.get("allowance", {})
    ledger = Path(path) if path is not None else DEVELOPMENT_ALLOWANCE if scope["split"] == "development" else HOLDOUT_ALLOWANCE
    approval = Path(details.get("approval_path", ""))
    marker = ledger.with_suffix(".registered")
    if (Path(details.get("path", "")).resolve() != ledger.resolve()
            or not all(item.is_file() for item in (ledger, marker, approval))):
        raise ValueError("Complete task funding evidence is required")
    expected = approval_proposal(metadata)
    expected.update(status="approved", authorization_source="explicit_user_approval")
    signature = digest(expected)
    if (digest(json.loads(approval.read_text(encoding="utf-8"))) != signature
            or marker.read_text(encoding="utf-8") != signature or details.get("signature") != signature):
        raise ValueError("Task funding approval differs")
    with closing(sqlite3.connect(ledger.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        seeds = db.execute("SELECT signature FROM seed").fetchall()
        rows = db.execute("SELECT ordinal,run,request_id,used FROM calls ORDER BY ordinal").fetchall()
    if (seeds != [(signature,)] or not 5 <= len(rows) <= scope["maximum_outbound_attempts"]
            or [row[0] for row in rows] != list(range(1, len(rows) + 1))
            or any(row[1] != str(run.resolve()) or type(row[3]) is not int or row[3] != 1
                   or type(row[2]) is not str or re.fullmatch(r"[A-Za-z0-9_-]{1,64}", row[2]) is None for row in rows)
            or type(completion.get("outbound_attempts")) is not int or completion["outbound_attempts"] != len(rows)):
        raise ValueError("Complete settled task accounting is required")
    return digest({"signature": signature, "rows": rows, "sqlite_sha256": hashlib.sha256(ledger.read_bytes()).hexdigest()})


class TaskAllowance:
    def __init__(self, approval: Path, metadata: dict, *, snapshot: Path, path=None):
        self.metadata = copy.deepcopy(metadata)
        split = self.metadata["split"]
        fresh = plan_collection(snapshot, split=split)
        if split == "holdout":
            from src.commands.evaluate_hf_agent import validate_selection

            selection = self.metadata.get("selection_lock", {})
            validate_selection(selection, load_cerebras()["model"], snapshot, profile_name=CEREBRAS_PROFILE)
            fresh.update(selection_lock=selection, selection_sha256=digest(selection))
        if _scope(self.metadata) != _scope(fresh):
            raise ValueError("Approval requires the current complete frozen plan")
        expected = approval_proposal(self.metadata)
        expected.update(status="approved", authorization_source="explicit_user_approval")
        self.approval = Path(approval)
        self.path = Path(path) if path is not None else DEVELOPMENT_ALLOWANCE if split == "development" else HOLDOUT_ALLOWANCE
        receipt = json.loads(self.approval.read_text(encoding="utf-8"))
        if digest(receipt) != digest(expected):
            raise ValueError("Explicit approval of this paper scope is required")
        self.receipt, self.signature = receipt, digest(receipt)
        self.ceiling = receipt["maximum_outbound_attempts"]
        self.marker = self.path.with_suffix(".registered")
        bootstrap = not self.path.exists()
        if bootstrap:
            if self.marker.exists():
                raise ValueError("Registered task ledger is missing; recovery is required")
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.marker.open("x", encoding="utf-8") as stream:
                stream.write(self.signature); stream.flush(); os.fsync(stream.fileno())
        elif not self.marker.is_file() or self.marker.read_text(encoding="utf-8") != self.signature:
            raise ValueError("Task registration differs")
        with transaction(self.path) as db:
            if bootstrap:
                db.execute("CREATE TABLE seed (signature TEXT PRIMARY KEY)")
                db.execute("CREATE TABLE calls (ordinal INTEGER PRIMARY KEY, run TEXT NOT NULL, request_id TEXT NOT NULL, used INTEGER)")
                db.execute("INSERT INTO seed VALUES (?)", (self.signature,))
            self._rows(db)

    def _rows(self, db) -> list:
        rows = db.execute("SELECT ordinal,run,request_id,used FROM calls ORDER BY ordinal").fetchall()
        if (db.execute("SELECT signature FROM seed").fetchall() != [(self.signature,)] or len(rows) > self.ceiling
                or [row[0] for row in rows] != list(range(1, len(rows) + 1))
                or len({row[1] for row in rows}) > 1
                or any(type(row[1]) is not str or not row[1] or type(row[2]) is not str
                       or re.fullmatch(r"[A-Za-z0-9_-]{1,64}", row[2]) is None
                       or row[3] is not None and (type(row[3]) is not int or row[3] not in {0, 1}) for row in rows)):
            raise ValueError("Task accounting differs")
        return rows

    def _validate(self) -> None:
        expected = approval_proposal(self.metadata)
        expected.update(status="approved", authorization_source="explicit_user_approval")
        if (not self.path.is_file() or not self.marker.is_file() or self.marker.read_text(encoding="utf-8") != self.signature
                or digest(json.loads(self.approval.read_text(encoding="utf-8"))) != self.signature
                or digest(expected) != self.signature):
            raise ValueError("Task approval or history changed")
        if self.metadata["split"] == "holdout":
            _selection_files(self.metadata["selection_lock"])

    def reserve(self, run: str, ordinal: int, request_id: str) -> None:
        self._validate()
        if (type(ordinal) is not int or not 1 <= ordinal <= self.ceiling or type(run) is not str or not run or type(request_id) is not str
                or re.fullmatch(r"[A-Za-z0-9_-]{1,64}", request_id) is None):
            raise ValueError("Invalid task reservation")
        with transaction(self.path) as db:
            rows = self._rows(db)
            if ordinal != len(rows) + 1 or rows and rows[0][1] != run:
                raise ValueError("Task allowance is exhausted or already reserved")
            db.execute("INSERT INTO calls VALUES (?, ?, ?, NULL)", (ordinal, run, request_id))

    def settle(self, ordinal: int, used: int | None) -> None:
        self._validate()
        if (type(ordinal) is not int or not 1 <= ordinal <= self.ceiling
                or used is not None and (type(used) is not int or used not in {0, 1})):
            raise ValueError("Invalid task settlement")
        with transaction(self.path) as db:
            self._rows(db)
            row = db.execute("SELECT used FROM calls WHERE ordinal=?", (ordinal,)).fetchone()
            if row is None or row[0] is not None:
                raise ValueError("Invalid or repeated task settlement")
            db.execute("UPDATE calls SET used=? WHERE ordinal=?", (1 if used is None else used, ordinal))

    @property
    def used(self) -> int:
        with closing(sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
            return sum(1 if row[3] is None else row[3] for row in self._rows(db))

    @property
    def started(self) -> bool:
        with closing(sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
            return bool(self._rows(db))
