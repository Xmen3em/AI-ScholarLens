"""Two new selector slots require explicit funding and complete read-only C3 evidence."""

import hashlib
import json
import sqlite3
from contextlib import closing
from pathlib import Path

from src.commands.evaluate_retrieval import digest
from src.commands.hf_cerebras_allowance import AUTHORITY, CEREBRAS_ALLOWANCE_PATH, allocation_proposal
from src.commands.hf_cerebras_allowance import approval_proposal as controller_proposal
from src.commands.hf_clarity_allowance import ClarityAllowance
from src.commands.hf_schema_allowance import REALLOCATION_PATH
from src.commands.hf_schema_execution import load_cerebras, load_selectors

SELECTOR_ALLOWANCE_PATH = Path("tests/test_output/hf-cerebras-selectors-allowance-20261015/allowance.sqlite3")
CONTROLLER_APPROVAL = Path("tests/test_output/hf-cerebras-execution-20261015-01/approval.json")
CONTROLLER_RUN = Path("tests/test_output/hf-cerebras-live-20261015-01")


def controller_binding(*, controller_path=CEREBRAS_ALLOWANCE_PATH, controller_approval=CONTROLLER_APPROVAL,
                       controller_run=CONTROLLER_RUN, allocation=REALLOCATION_PATH, **parents) -> str:
    path, approval, run, allocation = Path(controller_path), Path(controller_approval), Path(controller_run), Path(allocation)
    marker = path.with_suffix(".registered")
    if not path.is_file() or not approval.is_file() or not marker.is_file():
        raise ValueError("Complete retained Cerebras controller evidence is required")
    expected = controller_proposal(**parents)
    expected.update(status="approved", authorization_source=AUTHORITY)
    receipt = json.loads(approval.read_text(encoding="utf-8"))
    signature = digest(receipt)
    if (signature != digest(expected) or marker.read_text(encoding="utf-8") != signature
            or digest(json.loads(allocation.read_text(encoding="utf-8"))) != digest(allocation_proposal(**parents))):
        raise ValueError("Retained Cerebras controller approval/allocation differs")
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        seeds = db.execute("SELECT signature FROM seed").fetchall()
        rows = db.execute("SELECT arm,run,used FROM arms ORDER BY arm").fetchall()
    if (seeds != [(signature,)] or [row[0] for row in rows] != ["relevance", "rewrite", "scope"]
            or any(row[1] != str(run.resolve()) or type(row[2]) is not int or row[2] != 1 for row in rows)):
        raise ValueError("Complete exhausted three-arm controller accounting is required")
    profile = load_cerebras()
    metadata = json.loads((run / "metadata.json").read_text(encoding="utf-8"))
    result = json.loads((run / "qualification.json").read_text(encoding="utf-8"))
    checks = result.get("qualification", {}).get("checks", [])
    preservation = result.get("preservation", {})
    if (metadata.get("kind") != profile["kind"] or metadata.get("status") != "schema_qualification_completed"
            or metadata.get("approval_sha256") != signature
            or result.get("diagnostic_passed") is not True or result.get("app_accepted") is not False
            or result.get("schema_qualified") is not False
            or type(result.get("outbound_attempts")) is not int or result["outbound_attempts"] != 3
            or result.get("schema_execution_manifest_sha256") != profile["manifest_sha256"]
            or result.get("qualification", {}).get("fixture_manifest_sha256") != profile["qualification_manifest_sha256"]
            or [check.get("id") for check in checks] != profile["arms"]
            or set(preservation) != {"source_unchanged", "frozen_labels_unchanged", "corpus_unchanged", "models_unchanged"}
            or any(flag is not True for flag in preservation.values())):
        raise ValueError("Complete successful preserved controller result is required")
    for check, case in zip(checks, profile["cases"], strict=True):
        calls = check.get("calls", [])
        if (check.get("ok") is not True or check.get("schema_sha256") != digest(case["schema"])
                or check.get("fixture_sha256") != digest(case) or check.get("work", {}).get("usage_complete") is not True
                or check.get("work", {}).get("schema_violations") != 0 or len(calls) != 1
                or calls[0].get("model") != profile["model"] or calls[0].get("outbound_attempts") != 1
                or calls[0].get("schema_valid") is not True):
            raise ValueError("Controller schema/work evidence differs")
    return digest({"seed": signature, "arms": rows,
                   "sha256": {str(name): hashlib.sha256(name.read_bytes()).hexdigest()
                              for name in (path, approval, allocation, run / "metadata.json", run / "qualification.json")}})


def approval_proposal(**parents) -> dict:
    profile = load_selectors()
    binding = controller_binding(**parents)
    return {"kind": "hf_cerebras_selectors_approval_v1", "status": "pending_user_approval", "authorization_source": None,
            "manifest_sha256": profile["manifest_sha256"], "qualification_manifest_sha256": profile["qualification_manifest_sha256"],
            "model": profile["model"], "endpoint": profile["endpoint"], "maximum_outbound_attempts": 2,
            "arms": profile["arms"], "scope": profile["approval_scope"], "paper_data_sent": False,
            "complete_controller_history_binding": binding}


class SelectorAllowance(ClarityAllowance):
    def __init__(self, approval: Path, *, path=SELECTOR_ALLOWANCE_PATH, **parents):
        self.controller = parents
        super().__init__(approval, path=path)

    def _proposal(self) -> dict:
        return approval_proposal(**self.controller)
