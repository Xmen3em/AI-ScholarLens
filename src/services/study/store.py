"""Durable owner-scoped study state; admission and paid attempts commit first."""

import hashlib
import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable


class StoreConflict(RuntimeError):
    pass


def _json(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    if len(encoded.encode()) > 2_000_000:
        raise StoreConflict("state_too_large")
    return encoded


class StudyStore:
    def __init__(self, path: Path, owner: str, *, now: Callable[[], float] = time.time):
        if not owner or len(owner) > 80 or path.is_symlink():
            raise StoreConflict("invalid_store")
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path, self.owner, self.now = path, owner, now
        with self._db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, owner TEXT NOT NULL, intent TEXT NOT NULL, payload TEXT NOT NULL,
                    status TEXT NOT NULL, result TEXT, max_calls INTEGER NOT NULL, created REAL NOT NULL,
                    delivery INTEGER NOT NULL DEFAULT 0, UNIQUE(owner,intent));
                CREATE TABLE IF NOT EXISTS attempts (
                    job TEXT NOT NULL REFERENCES jobs(id), sequence INTEGER NOT NULL, purpose TEXT NOT NULL,
                    model TEXT NOT NULL, state TEXT NOT NULL, PRIMARY KEY(job,sequence));
                CREATE TABLE IF NOT EXISTS state (
                    owner TEXT NOT NULL, key TEXT NOT NULL, value TEXT NOT NULL, PRIMARY KEY(owner,key));
                CREATE TABLE IF NOT EXISTS papers (
                    owner TEXT NOT NULL, id TEXT NOT NULL, content TEXT NOT NULL, lesson TEXT,
                    PRIMARY KEY(owner,id));
            """)
            if "payload_hash" not in {row[1] for row in db.execute("PRAGMA table_info(jobs)")}:
                db.execute("ALTER TABLE jobs ADD COLUMN payload_hash TEXT")
                for row in db.execute("SELECT id,payload FROM jobs").fetchall():
                    db.execute("UPDATE jobs SET payload_hash=? WHERE id=?", (hashlib.sha256(row["payload"].encode()).hexdigest(), row["id"]))

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def _job(row):
        return {**dict(row), "payload": json.loads(row["payload"]),
                "result": json.loads(row["result"]) if row["result"] else None}

    def create_job(self, intent: str, payload: dict, *, max_calls: int = 4) -> dict:
        if not 1 <= len(intent) <= 120 or not 1 <= max_calls <= 8:
            raise StoreConflict("invalid_admission")
        encoded = _json(payload)
        digest = hashlib.sha256(encoded.encode()).hexdigest()
        with self._db() as db:
            # Keep accounting/idempotency tombstones, but expire old dialogue/results.
            db.execute("UPDATE jobs SET payload='{}',result=NULL,delivery=1 WHERE owner=? AND status!='running' AND created<?",
                       (self.owner, self.now() - 30 * 86400))
            row = db.execute("SELECT * FROM jobs WHERE owner=? AND intent=?", (self.owner, intent)).fetchone()
            if row:
                if row["payload_hash"] != digest:
                    raise StoreConflict("intent_payload_changed")
                return self._job(row)
            if db.execute("SELECT 1 FROM jobs WHERE owner=? AND status='running'", (self.owner,)).fetchone():
                raise StoreConflict("study_busy")
            identity = uuid.uuid4().hex
            db.execute("INSERT INTO jobs(id,owner,intent,payload,status,max_calls,created,payload_hash) VALUES(?,?,?,?,?,?,?,?)",
                       (identity, self.owner, intent, encoded, "running", max_calls, self.now(), digest))
            return self._job(db.execute("SELECT * FROM jobs WHERE id=?", (identity,)).fetchone())

    def get_job(self, job_id: str) -> dict | None:
        with self._db() as db:
            row = db.execute("SELECT * FROM jobs WHERE owner=? AND id=?", (self.owner, job_id)).fetchone()
            return self._job(row) if row else None

    def finish_job(self, job_id: str, result: dict, *, status: str = "ready") -> None:
        if status not in {"ready", "failed"}:
            raise StoreConflict("invalid_status")
        with self._db() as db:
            changed = db.execute("UPDATE jobs SET status=?,result=? WHERE owner=? AND id=? AND status='running'",
                                 (status, _json(result), self.owner, job_id)).rowcount
            if changed != 1:
                raise StoreConflict("job_not_running")

    def recover_interrupted(self) -> None:
        with self._db() as db:
            db.execute("UPDATE attempts SET state='unknown' WHERE state='reserved' AND job IN "
                       "(SELECT id FROM jobs WHERE owner=?)", (self.owner,))
            db.execute("UPDATE jobs SET status='interrupted',result=? WHERE owner=? AND status='running'",
                       (_json({"text": "الطلب اتوقف مع إعادة التشغيل. ابعت طلب جديد لو تحب تكمل؛ مش هيتعاد تلقائيًا."}), self.owner))

    def reserve_attempt(self, job_id: str, purpose: str, model: str) -> int:
        with self._db() as db:
            job = db.execute("SELECT * FROM jobs WHERE owner=? AND id=?", (self.owner, job_id)).fetchone()
            count = db.execute("SELECT COUNT(*) FROM attempts WHERE job=?", (job_id,)).fetchone()[0]
            if not job or job["status"] != "running" or count >= job["max_calls"]:
                raise StoreConflict("attempt_budget_exhausted")
            ceiling = self._get(db, "attempt_ceiling")
            if ceiling is not None:
                total = db.execute("SELECT COUNT(*) FROM attempts a JOIN jobs j ON j.id=a.job WHERE j.owner=?", (self.owner,)).fetchone()[0]
                if total >= ceiling:
                    raise StoreConflict("run_attempt_budget_exhausted")
            db.execute("INSERT INTO attempts VALUES(?,?,?,?,?)", (job_id, count + 1, purpose[:80], model[:160], "reserved"))
            return count + 1

    def settle_attempt(self, job_id: str, sequence: int, state: str) -> None:
        if state not in {"succeeded", "failed", "unknown"}:
            raise StoreConflict("invalid_attempt_state")
        with self._db() as db:
            db.execute("UPDATE attempts SET state=? WHERE job=? AND sequence=? AND state='reserved' AND job IN "
                       "(SELECT id FROM jobs WHERE owner=?)", (state, job_id, sequence, self.owner))

    def attempts(self, job_id: str) -> list[dict]:
        with self._db() as db:
            return [dict(row) for row in db.execute("SELECT a.* FROM attempts a JOIN jobs j ON j.id=a.job "
                    "WHERE j.owner=? AND j.id=? ORDER BY a.sequence", (self.owner, job_id))]

    def pending_deliveries(self) -> list[dict]:
        with self._db() as db:
            return [self._job(row) for row in db.execute("SELECT * FROM jobs WHERE owner=? AND delivery=0 "
                    "AND status!='running' ORDER BY created LIMIT 5", (self.owner,))]

    def claim_delivery(self, job_id: str) -> bool:
        with self._db() as db:
            return db.execute("UPDATE jobs SET delivery=1 WHERE owner=? AND id=? AND delivery=0 AND status!='running'",
                              (self.owner, job_id)).rowcount == 1

    def _get(self, db, key, default=None):
        row = db.execute("SELECT value FROM state WHERE owner=? AND key=?", (self.owner, key)).fetchone()
        return json.loads(row[0]) if row else default

    def _set(self, db, key, value):
        db.execute("INSERT INTO state VALUES(?,?,?) ON CONFLICT(owner,key) DO UPDATE SET value=excluded.value",
                   (self.owner, key, _json(value)))

    def activate(self, paper_id: str, metadata: dict) -> None:
        with self._db() as db:
            self._set(db, "context", {"paper_id": paper_id, "metadata": metadata, "turns": [], "updated": self.now()})

    def context(self) -> dict | None:
        with self._db() as db:
            context = self._get(db, "context")
            if context and self.now() - context["updated"] > 86400:
                context["turns"] = []
                self._set(db, "context", context)
            return context

    def append_turn(self, paper_id: str, question: str, answer: str) -> None:
        with self._db() as db:
            context = self._get(db, "context")
            if not context or context["paper_id"] != paper_id:
                raise StoreConflict("paper_context_changed")
            turns = context["turns"] if self.now() - context["updated"] <= 86400 else []
            context.update(turns=(turns + [{"question": question[:2000], "answer": answer[:12000]}])[-4:], updated=self.now())
            self._set(db, "context", context)

    def preferences(self) -> dict:
        with self._db() as db:
            return self._get(db, "preferences", {"depth": "beginner"})

    def set_total_ceiling(self, ceiling: int) -> None:
        if type(ceiling) is not int or not 1 <= ceiling <= 12:
            raise StoreConflict("invalid_run_budget")
        with self._db() as db:
            current = self._get(db, "attempt_ceiling")
            if current is not None and current != ceiling:
                raise StoreConflict("run_budget_is_immutable")
            self._set(db, "attempt_ceiling", ceiling)

    def total_attempts(self) -> int:
        with self._db() as db:
            return db.execute("SELECT COUNT(*) FROM attempts a JOIN jobs j ON j.id=a.job WHERE j.owner=?", (self.owner,)).fetchone()[0]

    def set_preferences(self, *, depth: str) -> None:
        if depth not in {"beginner", "researcher"}:
            raise StoreConflict("invalid_depth")
        with self._db() as db:
            self._set(db, "preferences", {"depth": depth})

    def selection(self, candidates: list[dict] | None = None) -> list[dict]:
        with self._db() as db:
            if candidates is not None:
                self._set(db, "selection", {"candidates": candidates[:3], "updated": self.now()})
            value = self._get(db, "selection", {"candidates": [], "updated": 0})
            return value["candidates"] if self.now() - value["updated"] <= 3600 else []

    def save_paper(self, paper_id: str, content: dict, lesson: dict | None = None) -> None:
        with self._db() as db:
            db.execute("INSERT INTO papers VALUES(?,?,?,?) ON CONFLICT(owner,id) DO UPDATE "
                       "SET content=excluded.content,lesson=COALESCE(excluded.lesson,papers.lesson)",
                       (self.owner, paper_id, _json(content), _json(lesson) if lesson else None))
            db.execute("DELETE FROM papers WHERE owner=? AND rowid NOT IN "
                       "(SELECT rowid FROM papers WHERE owner=? ORDER BY rowid DESC LIMIT 10)", (self.owner, self.owner))

    def paper(self, paper_id: str) -> dict | None:
        with self._db() as db:
            row = db.execute("SELECT * FROM papers WHERE owner=? AND id=?", (self.owner, paper_id)).fetchone()
            return {"content": json.loads(row["content"]), "lesson": json.loads(row["lesson"]) if row["lesson"] else None} if row else None

    def forget(self) -> None:
        # Admission/attempt records are accounting tombstones and remain durable.
        with self._db() as db:
            db.execute("DELETE FROM state WHERE owner=? AND key!='attempt_ceiling'", (self.owner,))
            db.execute("DELETE FROM papers WHERE owner=?", (self.owner,))
            db.execute("UPDATE jobs SET payload='{}', result=NULL,delivery=1 WHERE owner=? AND status!='running'", (self.owner,))

    def fingerprint(self) -> str:
        return hashlib.sha256(self.owner.encode()).hexdigest()[:12]
