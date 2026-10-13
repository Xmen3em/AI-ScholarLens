"""Atomic reservation of the explicitly approved, cumulative HF pilot allowance."""

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from src.commands.hf_evaluation import HF_MANIFEST_SHA256, hosted_work, load_protocol

PILOT_MODEL = "openai/gpt-oss-120b:groq"
PILOT_CASE = "week7-development-narrative-rubrics-literal"
ALLOWANCE_PATH = Path("tests/test_output/hf-approved-pilot-20261013/allowance.sqlite3")
PRIOR_RUN = Path("tests/test_output/hf-development-pilot-20261013-04")


def validate_pilot_scope(metadata: dict) -> None:
    jobs = metadata["jobs"]
    if (metadata["split"] != "development" or metadata["configuration"]["model"] != PILOT_MODEL
            or len(jobs) != 2 or [job["path"] for job in jobs] != ["baseline", "agent"]
            or any(job["case_id"] != PILOT_CASE or job["mode"] != "bm25" or job["transport"] != "json"
                   or job["key"] != f"{PILOT_CASE}:bm25:{job['path']}:json" for job in jobs)):
        raise ValueError("Run exceeds the approved pilot scope")


@contextmanager
def transaction(path: Path):
    db = sqlite3.connect(path, timeout=5, isolation_level=None)
    try:
        db.execute("BEGIN IMMEDIATE")
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


class PilotAllowance:
    def __init__(self, path=ALLOWANCE_PATH, *, prior=PRIOR_RUN):
        self.path = Path(path)
        names = ("metadata.json", "completion.json", "qualification.json", "records.jsonl")
        hashes = {name: hashlib.sha256((prior / name).read_bytes()).hexdigest() for name in names}
        self.signature = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
        read = lambda name: json.loads((prior / name).read_text(encoding="utf-8"))
        metadata, completion, qualification = read("metadata.json"), read("completion.json"), read("qualification.json")
        validate_pilot_scope(metadata)
        if metadata["hosted_manifest_sha256"] != HF_MANIFEST_SHA256 or (prior / "records.jsonl").read_text().strip():
            raise ValueError("Prior approved trial differs")
        work = [hosted_work(check["calls"], load_protocol(), PILOT_MODEL) for check in qualification["checks"]]
        if sum(row["outbound_attempts"] for row in work) != 2 or completion.get("outbound_attempts") != 2:
            raise ValueError("Prior approved attempts cannot be verified")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with transaction(self.path) as db:
            db.execute("CREATE TABLE IF NOT EXISTS seed (signature TEXT PRIMARY KEY)")
            db.execute("CREATE TABLE IF NOT EXISTS reservations (run TEXT PRIMARY KEY, budget INTEGER NOT NULL, used INTEGER)")
            existing = db.execute("SELECT signature FROM seed").fetchall()
            if existing and existing != [(self.signature,)]:
                raise ValueError("Prior allowance evidence changed")
            if not existing:
                db.execute("INSERT INTO seed VALUES (?)", (self.signature,))

    def reserve(self, run: str, planned: int) -> int:
        if type(planned) is not int or not 1 <= planned <= 773:
            raise ValueError("Invalid planned allowance")
        with transaction(self.path) as db:
            spent = db.execute("SELECT COALESCE(SUM(COALESCE(used, budget)), 0) FROM reservations").fetchone()[0]
            budget = min(planned, 13 - 2 - spent)
            if budget <= 0 or db.execute("SELECT 1 FROM reservations WHERE run=?", (run,)).fetchone():
                raise ValueError("Approved pilot allowance is exhausted or already reserved")
            db.execute("INSERT INTO reservations VALUES (?, ?, NULL)", (run, budget))
        return budget

    def settle(self, run: str, used: int | None) -> None:
        with transaction(self.path) as db:
            row = db.execute("SELECT budget, used FROM reservations WHERE run=?", (run,)).fetchone()
            if row is None or row[1] is not None or used is not None and (type(used) is not int or not 0 <= used <= row[0]):
                raise ValueError("Invalid or repeated allowance settlement")
            db.execute("UPDATE reservations SET used=? WHERE run=?", (row[0] if used is None else used, run))
