"""Two new explicitly approved arms; both completed old allowances stay read-only."""

import hashlib
import json
import os
import sqlite3
from contextlib import closing
from pathlib import Path

from src.commands.evaluate_retrieval import digest
from src.commands.hf_allowance import ALLOWANCE_PATH, PRIOR_RUN, transaction
from src.commands.hf_clarity_execution import load_execution
from src.commands.hf_prompt_allowance import PROMPT_ALLOWANCE_PATH, original_binding
from src.commands.hf_prompt_allowance import approval_proposal as prompt_proposal

CLARITY_ALLOWANCE_PATH = Path("tests/test_output/hf-clarity-allowance-20261015/allowance.sqlite3")
PROMPT_APPROVAL_PATH = Path("tests/test_output/hf-prompt-execution-20261014-01/approval.json")


def prompt_binding(
    *, original=ALLOWANCE_PATH, prior=PRIOR_RUN, prompt_path=PROMPT_ALLOWANCE_PATH, prompt_approval=PROMPT_APPROVAL_PATH
) -> str:
    path, approval = Path(prompt_path), Path(prompt_approval)
    marker = path.with_suffix(".registered")
    if not path.is_file() or not approval.is_file() or not marker.is_file():
        raise ValueError("Complete retained prompt allowance is required")
    expected = prompt_proposal(original=original, prior=prior)
    expected.update(status="approved", authorization_source="explicit_user_approval")
    receipt = json.loads(approval.read_text(encoding="utf-8"))
    if (
        receipt != expected
        or type(receipt.get("maximum_outbound_attempts")) is not int
        or receipt.get("paper_data_sent") is not False
    ):
        raise ValueError("Retained prompt approval differs")
    signature = digest(receipt)
    if marker.read_text(encoding="utf-8") != signature:
        raise ValueError("Retained prompt registration differs")
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        seeds = db.execute("SELECT signature FROM seed").fetchall()
        rows = db.execute("SELECT arm,run,used FROM arms ORDER BY arm").fetchall()
    if (
        seeds != [(signature,)]
        or len(rows) != 6
        or {row[0] for row in rows} != set(expected["arms"])
        or any(type(row[2]) is not int or row[2] != 1 for row in rows)
    ):
        raise ValueError("Complete exhausted six-arm evidence is required")
    return digest(
        {
            "seed": signature,
            "arms": rows,
            "sqlite_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "receipt_sha256": hashlib.sha256(approval.read_bytes()).hexdigest(),
        }
    )


def approval_proposal(
    *, original=ALLOWANCE_PATH, prior=PRIOR_RUN, prompt_path=PROMPT_ALLOWANCE_PATH, prompt_approval=PROMPT_APPROVAL_PATH
) -> dict:
    profile = load_execution()
    return {
        "kind": "hf_clarity_execution_approval_v1",
        "status": "pending_user_approval",
        "authorization_source": None,
        "manifest_sha256": profile["manifest_sha256"],
        "candidate_manifest_sha256": profile["candidate_manifest_sha256"],
        "measurement_manifest_sha256": profile["measurement_manifest_sha256"],
        "model": profile["model"],
        "endpoint": profile["endpoint"],
        "maximum_outbound_attempts": 2,
        "arms": list(profile["arms"]),
        "scope": profile["approval_scope"],
        "paper_data_sent": False,
        "original_allowance_binding": original_binding(original, prior=prior),
        "prompt_allowance_binding": prompt_binding(
            original=original, prior=prior, prompt_path=prompt_path, prompt_approval=prompt_approval
        ),
    }


class ClarityAllowance:
    def __init__(
        self,
        approval: Path,
        *,
        path=CLARITY_ALLOWANCE_PATH,
        original=ALLOWANCE_PATH,
        prior=PRIOR_RUN,
        prompt_path=PROMPT_ALLOWANCE_PATH,
        prompt_approval=PROMPT_APPROVAL_PATH,
    ):
        self.approval, self.path = Path(approval), Path(path)
        self.parents = {"original": original, "prior": prior, "prompt_path": prompt_path, "prompt_approval": prompt_approval}
        expected = approval_proposal(**self.parents)
        expected.update(status="approved", authorization_source="explicit_user_approval")
        receipt = json.loads(self.approval.read_text(encoding="utf-8"))
        if (
            receipt != expected
            or type(receipt.get("maximum_outbound_attempts")) is not int
            or receipt.get("paper_data_sent") is not False
        ):
            raise ValueError("Explicit approval of the exact two-attempt scope is required")
        self.receipt, self.signature = receipt, digest(receipt)
        self.marker = self.path.with_suffix(".registered")
        bootstrap = not self.path.exists()
        if bootstrap:
            if self.marker.exists():
                raise ValueError("Registered clarity ledger is missing; recovery is required")
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.marker.open("x", encoding="utf-8") as stream:
                stream.write(self.signature)
                stream.flush()
                os.fsync(stream.fileno())
        elif not self.marker.is_file() or self.marker.read_text(encoding="utf-8") != self.signature:
            raise ValueError("Clarity registration differs")
        with transaction(self.path) as db:
            if bootstrap:
                db.execute("CREATE TABLE seed (signature TEXT PRIMARY KEY)")
                db.execute("CREATE TABLE arms (arm TEXT PRIMARY KEY, run TEXT NOT NULL, used INTEGER)")
                db.execute("INSERT INTO seed VALUES (?)", (self.signature,))
            self._rows(db)

    def _rows(self, db) -> list:
        seeds = db.execute("SELECT signature FROM seed").fetchall()
        rows = db.execute("SELECT arm,run,used FROM arms").fetchall()
        if (
            seeds != [(self.signature,)]
            or len(rows) > 2
            or any(
                arm not in self.receipt["arms"]
                or type(run) is not str
                or used is not None
                and (type(used) is not int or used not in {0, 1})
                for arm, run, used in rows
            )
        ):
            raise ValueError("Clarity allowance rows differ")
        return rows

    def _validate(self) -> None:
        if (
            not self.path.is_file()
            or not self.marker.is_file()
            or self.marker.read_text(encoding="utf-8") != self.signature
            or digest(json.loads(self.approval.read_text(encoding="utf-8"))) != self.signature
        ):
            raise ValueError("Retained clarity approval or registration differs")
        expected = approval_proposal(**self.parents)
        expected.update(status="approved", authorization_source="explicit_user_approval")
        if expected != self.receipt:
            raise ValueError("Complete parent evidence differs")

    @property
    def used(self) -> int:
        self._validate()
        with closing(sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
            return sum(1 if used is None else used for _, _, used in self._rows(db))

    def reserve(self, run: str, arm: str) -> None:
        self._validate()
        if type(run) is not str or not run or arm not in self.receipt["arms"]:
            raise ValueError("Unapproved arm or run")
        with transaction(self.path) as db:
            rows = self._rows(db)
            if len(rows) >= 2 or any(row[0] == arm for row in rows):
                raise ValueError("Clarity arm is exhausted or already reserved")
            db.execute("INSERT INTO arms VALUES (?,?,NULL)", (arm, run))

    def settle(self, arm: str, used: int | None) -> None:
        self._validate()
        if used is not None and (type(used) is not int or used not in {0, 1}):
            raise ValueError("Invalid clarity attempt settlement")
        with transaction(self.path) as db:
            self._rows(db)
            row = db.execute("SELECT used FROM arms WHERE arm=?", (arm,)).fetchone()
            if row is None or row[0] is not None:
                raise ValueError("Missing or repeated clarity settlement")
            db.execute("UPDATE arms SET used=? WHERE arm=?", (1 if used is None else used, arm))
