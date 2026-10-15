"""Separate Fireworks grant; the stopped Groq counter remains read-only and unspent."""

import hashlib
import json
import sqlite3
from contextlib import closing
from pathlib import Path

from src.commands.evaluate_retrieval import digest
from src.commands.hf_schema_allowance import SCHEMA_ALLOWANCE_PATH, SchemaAllowance
from src.commands.hf_schema_allowance import approval_proposal as schema_proposal
from src.commands.hf_schema_execution import load_alternative, load_execution

ALTERNATIVE_ALLOWANCE_PATH = Path("tests/test_output/hf-fireworks-schema-allowance-20261015/allowance.sqlite3")
STOPPED_APPROVAL = Path("tests/test_output/hf-schema-execution-20261015-01/approval.json")
STOPPED_RUN = Path("tests/test_output/hf-schema-live-20261015-01")


def stopped_binding(*, stopped_path=SCHEMA_ALLOWANCE_PATH, stopped_approval=STOPPED_APPROVAL, stopped_run=STOPPED_RUN,
                    **parents) -> str:
    path, approval, run = Path(stopped_path), Path(stopped_approval), Path(stopped_run)
    marker = path.with_suffix(".registered")
    if not path.is_file() or not approval.is_file() or not marker.is_file():
        raise ValueError("Retained stopped Groq evidence is required")
    expected = schema_proposal(**parents)
    expected.update(status="approved", authorization_source="explicit_user_approval")
    receipt = json.loads(approval.read_text(encoding="utf-8"))
    signature = digest(receipt)
    if signature != digest(expected) or marker.read_text(encoding="utf-8") != signature:
        raise ValueError("Stopped Groq approval or registration differs")
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        seeds = db.execute("SELECT signature FROM seed").fetchall()
        rows = db.execute("SELECT arm,run,used FROM arms ORDER BY arm").fetchall()
    if (seeds != [(signature,)] or [row[0] for row in rows] != ["relevance", "scope"]
            or any(row[1] != str(run.resolve()) or type(row[2]) is not int or row[2] != 1 for row in rows)):
        raise ValueError("Stopped Groq two-attempt accounting differs")
    profile = load_execution()
    metadata = json.loads((run / "metadata.json").read_text(encoding="utf-8"))
    result = json.loads((run / "qualification.json").read_text(encoding="utf-8"))
    qualification, preservation = result.get("qualification", {}), result.get("preservation", {})
    checks = qualification.get("checks", [])
    if (metadata.get("kind") != profile["kind"] or metadata.get("status") != "schema_qualification_completed"
            or metadata.get("approval_sha256") != signature
            or result.get("schema_execution_manifest_sha256") != profile["manifest_sha256"]
            or result.get("schema_qualified") is not False
            or result.get("app_accepted") is not False
            or type(result.get("outbound_attempts")) is not int or result["outbound_attempts"] != 2
            or qualification.get("qualified") is not False
            or qualification.get("fixture_manifest_sha256") != profile["qualification_manifest_sha256"]
            or [check.get("id") for check in checks] != ["scope", "relevance"]
            or checks[0].get("ok") is not True or checks[1].get("ok") is not False
            or len(checks[1].get("calls", [])) != 1
            or type(checks[1]["calls"][0].get("outbound_attempts")) is not int
            or checks[1]["calls"][0]["outbound_attempts"] != 1
            or checks[1]["calls"][0].get("provider_status") != 400
            or checks[1]["calls"][0].get("provider_error_code") != "json_validate_failed"
            or checks[1]["calls"][0].get("provider_error_type") != "invalid_request_error"
            or set(preservation) != {"source_unchanged", "frozen_labels_unchanged", "corpus_unchanged", "models_unchanged"}
            or any(flag is not True for flag in preservation.values())):
        raise ValueError("Complete preserved failed Groq qualification is required")
    return digest({"seed": signature, "arms": rows,
                   "sha256": {str(name): hashlib.sha256(name.read_bytes()).hexdigest()
                              for name in (path, approval, run / "metadata.json", run / "qualification.json")}})


def approval_proposal(*, stopped_path=SCHEMA_ALLOWANCE_PATH, stopped_approval=STOPPED_APPROVAL, stopped_run=STOPPED_RUN,
                      **parents) -> dict:
    profile = load_alternative()
    proposal = schema_proposal(**parents)
    proposal.update(kind="hf_provider_alternative_approval_v1", manifest_sha256=profile["manifest_sha256"],
                    model=profile["model"], scope=profile["approval_scope"],
                    stopped_schema_allowance_binding=stopped_binding(stopped_path=stopped_path,
                        stopped_approval=stopped_approval, stopped_run=stopped_run, **parents))
    return proposal


class AlternativeAllowance(SchemaAllowance):
    def __init__(self, approval: Path, *, path=ALTERNATIVE_ALLOWANCE_PATH, stopped_path=SCHEMA_ALLOWANCE_PATH,
                 stopped_approval=STOPPED_APPROVAL, stopped_run=STOPPED_RUN, **parents):
        self.stopped = {"stopped_path": stopped_path, "stopped_approval": stopped_approval, "stopped_run": stopped_run}
        super().__init__(approval, path=path, **parents)

    def _proposal(self) -> dict:
        return approval_proposal(**self.parents, **self.clarity, **self.stopped)
