"""Five new approved arms bound to all three exhausted read-only allowances."""

import hashlib
import json
import sqlite3
from contextlib import closing
from pathlib import Path

from src.commands.evaluate_retrieval import digest
from src.commands.hf_allowance import ALLOWANCE_PATH, PRIOR_RUN
from src.commands.hf_clarity_allowance import CLARITY_ALLOWANCE_PATH, PROMPT_APPROVAL_PATH, ClarityAllowance
from src.commands.hf_clarity_allowance import approval_proposal as clarity_proposal
from src.commands.hf_clarity_execution import load_execution as load_clarity_execution
from src.commands.hf_prompt_allowance import PROMPT_ALLOWANCE_PATH
from src.commands.hf_schema_execution import load_execution

SCHEMA_ALLOWANCE_PATH = Path("tests/test_output/hf-schema-allowance-20261015/allowance.sqlite3")
CLARITY_APPROVAL_PATH = Path("tests/test_output/hf-clarity-execution-20261015-01/approval.json")
CLARITY_RUN = Path("tests/test_output/hf-clarity-live-20261015-02")
REALLOCATION_PATH = Path("tests/test_output/hf-cerebras-execution-20261015-01/reallocation.json")


def clarity_binding(
    *, original=ALLOWANCE_PATH, prior=PRIOR_RUN, prompt_path=PROMPT_ALLOWANCE_PATH, prompt_approval=PROMPT_APPROVAL_PATH,
    clarity_path=CLARITY_ALLOWANCE_PATH, clarity_approval=CLARITY_APPROVAL_PATH, clarity_run=CLARITY_RUN,
) -> str:
    path, approval, run = Path(clarity_path), Path(clarity_approval), Path(clarity_run)
    marker = path.with_suffix(".registered")
    if not path.is_file() or not approval.is_file() or not marker.is_file():
        raise ValueError("Retained completed clarity allowance is required")
    expected = clarity_proposal(original=original, prior=prior, prompt_path=prompt_path, prompt_approval=prompt_approval)
    expected.update(status="approved", authorization_source="explicit_user_approval")
    receipt = json.loads(approval.read_text(encoding="utf-8"))
    if (digest(receipt) != digest(expected) or type(receipt.get("maximum_outbound_attempts")) is not int
            or receipt.get("paper_data_sent") is not False):
        raise ValueError("Retained clarity approval differs")
    signature = digest(receipt)
    if marker.read_text(encoding="utf-8") != signature:
        raise ValueError("Retained clarity registration differs")
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        seeds = db.execute("SELECT signature FROM seed").fetchall()
        rows = db.execute("SELECT arm,run,used FROM arms ORDER BY arm").fetchall()
    if (seeds != [(signature,)] or len(rows) != 2 or {row[0] for row in rows} != set(expected["arms"])
            or any(type(row[1]) is not str or not row[1] or type(row[2]) is not int or row[2] != 1 for row in rows)):
        raise ValueError("Exhausted two-arm clarity allowance is required")
    metadata = json.loads((run / "metadata.json").read_text(encoding="utf-8"))
    result = json.loads((run / "comparison.json").read_text(encoding="utf-8"))
    profile = load_clarity_execution()
    preservation = result.get("preservation", {})
    records = result.get("records", [])
    if (
        metadata.get("kind") != profile["kind"] or metadata.get("status") != "diagnostic_completed"
        or metadata.get("approval_sha256") != signature
        or metadata.get("reproduction_manifest_sha256") != profile["manifest_sha256"]
        or metadata.get("paper_collection_planned") is not False
        or result.get("pair_passed") is not True or result.get("qualification_accepted") is not False
        or type(result.get("outbound_attempts")) is not int or result["outbound_attempts"] != 2
        or result.get("reproduction_manifest_sha256") != profile["manifest_sha256"]
        or set(preservation) != {"source_unchanged", "frozen_labels_unchanged", "corpus_unchanged", "models_unchanged"}
        or any(flag is not True for flag in preservation.values())
        or [record.get("arm") for record in records] != list(profile["arms"])
        or any(record.get("category") != "passed" or record.get("schema_valid") is not True
               or record.get("expected_match") is not True or record.get("work", {}).get("usage_complete") is not True
               or record.get("work", {}).get("schema_violations") != 0 for record in records)
    ):
        raise ValueError("Preserved successful clarity pair is required")
    return digest({"seed": signature, "arms": rows,
                   "sha256": {str(name): hashlib.sha256(name.read_bytes()).hexdigest()
                              for name in (path, approval, run / "metadata.json", run / "comparison.json")}})


def approval_proposal(
    *, original=ALLOWANCE_PATH, prior=PRIOR_RUN, prompt_path=PROMPT_ALLOWANCE_PATH, prompt_approval=PROMPT_APPROVAL_PATH,
    clarity_path=CLARITY_ALLOWANCE_PATH, clarity_approval=CLARITY_APPROVAL_PATH, clarity_run=CLARITY_RUN,
) -> dict:
    profile = load_execution()
    parent = clarity_proposal(original=original, prior=prior, prompt_path=prompt_path, prompt_approval=prompt_approval)
    return {"kind": "hf_schema_execution_approval_v1", "status": "pending_user_approval", "authorization_source": None,
            "manifest_sha256": profile["manifest_sha256"],
            "qualification_manifest_sha256": profile["qualification_manifest_sha256"],
            "model": profile["model"], "endpoint": profile["endpoint"], "maximum_outbound_attempts": 5,
            "arms": profile["arms"], "scope": profile["approval_scope"], "paper_data_sent": False,
            "original_allowance_binding": parent["original_allowance_binding"],
            "prompt_allowance_binding": parent["prompt_allowance_binding"],
            "clarity_allowance_binding": clarity_binding(original=original, prior=prior, prompt_path=prompt_path,
                prompt_approval=prompt_approval, clarity_path=clarity_path, clarity_approval=clarity_approval, clarity_run=clarity_run)}


class SchemaAllowance(ClarityAllowance):
    maximum_arms = 5

    def __init__(
        self, approval: Path, *, path=SCHEMA_ALLOWANCE_PATH, original=ALLOWANCE_PATH, prior=PRIOR_RUN,
        prompt_path=PROMPT_ALLOWANCE_PATH, prompt_approval=PROMPT_APPROVAL_PATH, clarity_path=CLARITY_ALLOWANCE_PATH,
        clarity_approval=CLARITY_APPROVAL_PATH, clarity_run=CLARITY_RUN,
    ):
        self.clarity = {"clarity_path": clarity_path, "clarity_approval": clarity_approval, "clarity_run": clarity_run}
        super().__init__(approval, path=path, original=original, prior=prior,
                         prompt_path=prompt_path, prompt_approval=prompt_approval)

    def _proposal(self) -> dict:
        return approval_proposal(**self.parents, **self.clarity)

    def reserve(self, run: str, arm: str) -> None:
        if (self.receipt["kind"] == "hf_schema_execution_approval_v1"
                and self.path.resolve() == SCHEMA_ALLOWANCE_PATH.resolve() and REALLOCATION_PATH.exists()):
            raise ValueError("The stopped Groq remainder was reassigned; duplicate spending is blocked")
        super().reserve(run, arm)
