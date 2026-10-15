"""Separate explicitly approved extension; exhausted original allowance stays read-only."""

import hashlib
import json
import sqlite3
from contextlib import closing
from pathlib import Path

from src.commands.evaluate_retrieval import digest
from src.commands.hf_allowance import ALLOWANCE_PATH, PILOT_MODEL, PRIOR_RUN, transaction, validate_pilot_scope
from src.commands.hf_reproduction import PROMPT_COMPARISON_SHA256, load_prompt_comparison
from src.services.hf.registry import HF_ROUTER_URL

PROMPT_ALLOWANCE_PATH = Path("tests/test_output/hf-prompt-comparison-allowance-20261014/allowance.sqlite3")


def original_binding(path=ALLOWANCE_PATH, *, prior=PRIOR_RUN) -> str:
    path = Path(path)
    if not path.is_file():
        raise ValueError("Retained original allowance is missing")
    hashes = {name: hashlib.sha256((prior / name).read_bytes()).hexdigest()
              for name in ("metadata.json", "completion.json", "qualification.json", "records.jsonl")}
    signature = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    validate_pilot_scope(json.loads((prior / "metadata.json").read_text(encoding="utf-8")))
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        seeds = db.execute("SELECT signature FROM seed").fetchall()
        rows = db.execute("SELECT run,budget,used FROM reservations ORDER BY run").fetchall()
    if (seeds != [(signature,)] or any(type(budget) is not int or type(used) is not int
            or not 0 <= used <= budget for _, budget, used in rows) or 2 + sum(row[2] for row in rows) != 13):
        raise ValueError("Complete exhausted original evidence is required")
    return digest({"seed": signature, "reservations": rows, "sqlite_sha256": hashlib.sha256(path.read_bytes()).hexdigest()})


def approval_proposal(*, original=ALLOWANCE_PATH, prior=PRIOR_RUN) -> dict:
    profile = load_prompt_comparison()
    return {"kind": "hf_prompt_comparison_approval_v1", "status": "pending_user_approval",
            "authorization_source": None, "manifest_sha256": PROMPT_COMPARISON_SHA256,
            "model": PILOT_MODEL, "endpoint": HF_ROUTER_URL, "maximum_outbound_attempts": 6,
            "arms": list(profile["arms"]), "scope": profile["approval_scope"], "paper_data_sent": False,
            "original_allowance_binding": original_binding(original, prior=prior)}


class PromptAllowance:
    def __init__(self, approval: Path, *, path=PROMPT_ALLOWANCE_PATH, original=ALLOWANCE_PATH, prior=PRIOR_RUN):
        self.approval, self.path, self.original, self.prior = Path(approval), Path(path), Path(original), Path(prior)
        expected = approval_proposal(original=self.original, prior=self.prior)
        expected.update(status="approved", authorization_source="explicit_user_approval")
        receipt = json.loads(self.approval.read_text(encoding="utf-8"))
        if (receipt != expected or type(receipt.get("maximum_outbound_attempts")) is not int
                or receipt.get("paper_data_sent") is not False):
            raise ValueError("Explicit approval of this exact additional scope is required")
        self.receipt, self.signature = receipt, digest(receipt)
        self.marker = self.path.with_suffix(".registered")
        bootstrap = not self.path.exists()
        if bootstrap:
            if self.marker.exists():
                raise ValueError("Registered extension ledger is missing; recovery is required")
            self.path.parent.mkdir(parents=True, exist_ok=True)
            # Exclusive registration is retained even if initialization is interrupted.
            # A missing ledger after registration requires recovery, never reseeding.
            with self.marker.open("x", encoding="utf-8") as stream:
                stream.write(self.signature)
        elif not self.marker.is_file() or self.marker.read_text(encoding="utf-8") != self.signature:
            raise ValueError("Extension registration differs")
        with transaction(self.path) as db:
            if bootstrap:
                db.execute("CREATE TABLE seed (signature TEXT PRIMARY KEY)")
                db.execute("CREATE TABLE arms (arm TEXT PRIMARY KEY, run TEXT NOT NULL, used INTEGER)")
                db.execute("INSERT INTO seed VALUES (?)", (self.signature,))
            seeds = db.execute("SELECT signature FROM seed").fetchall()
            if seeds != [(self.signature,)]:
                raise ValueError("Extension approval differs")
            db.execute("SELECT arm,run,used FROM arms").fetchall()

    def _validate(self) -> None:
        if (not self.path.is_file() or not self.marker.is_file()
                or self.marker.read_text(encoding="utf-8") != self.signature
                or json.loads(self.approval.read_text(encoding="utf-8")) != self.receipt
                or original_binding(self.original, prior=self.prior) != self.receipt["original_allowance_binding"]):
            raise ValueError("Retained extension/original evidence differs")

    @property
    def used(self) -> int:
        self._validate()
        with closing(sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
            return db.execute("SELECT COALESCE(SUM(COALESCE(used,1)),0) FROM arms").fetchone()[0]

    def reserve(self, run: str, arm: str) -> None:
        self._validate()
        if arm not in self.receipt["arms"]:
            raise ValueError("Unapproved arm")
        with transaction(self.path) as db:
            seeds = db.execute("SELECT signature FROM seed").fetchall()
            count = db.execute("SELECT COUNT(*) FROM arms").fetchone()[0]
            if seeds != [(self.signature,)] or count >= 6 or db.execute("SELECT 1 FROM arms WHERE arm=?", (arm,)).fetchone():
                raise ValueError("Arm is exhausted or already reserved")
            db.execute("INSERT INTO arms VALUES (?,?,NULL)", (arm, run))

    def settle(self, arm: str, used: int | None) -> None:
        self._validate()
        if used is not None and (type(used) is not int or used not in {0, 1}):
            raise ValueError("Invalid attempt settlement")
        with transaction(self.path) as db:
            row = db.execute("SELECT used FROM arms WHERE arm=?", (arm,)).fetchone()
            if row is None or row[0] is not None:
                raise ValueError("Missing or repeated settlement")
            db.execute("UPDATE arms SET used=? WHERE arm=?", (1 if used is None else used, arm))
