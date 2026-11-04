"""Invite-only beta access: members, invites, notes, daily limits and the dollar ledger (docs/specs/multi-user.md §2–3).

The tables live beside the study store in the same SQLite file. Invite codes are stored only
as SHA-256; a code is trimmed and upper-cased before it is checked.
"""

import hashlib
import secrets
import sqlite3
import time
from collections import deque
from collections.abc import Callable
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from src.services.study import access_text
from src.services.study.access_settings import AccessSettings
from src.services.study.models import DEFAULT_PROFILE, call_cost_usd

CAIRO = ZoneInfo("Africa/Cairo")
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 10
INVITE_SECONDS = 7 * 86400
WORST_INPUT_TOKENS = 20000
Role = Literal["owner", "student"]
Kind = Literal["paper", "question", "other"]


def _hash(code: str) -> str:
    return hashlib.sha256(code.strip().upper().encode()).hexdigest()


class AccessGate:
    def __init__(self, path: Path, settings: AccessSettings, owner_id: int, *, now: Callable[[], float] = time.time):
        if path.is_symlink():
            raise ValueError("invalid_access_store")
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path, self.settings, self.owner_id, self.now = path, settings, owner_id, now
        self._messages: dict[int, deque[float]] = {}
        with self._db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS members (
                    user INTEGER PRIMARY KEY, role TEXT NOT NULL, joined REAL NOT NULL, last_active REAL NOT NULL,
                    revoked INTEGER NOT NULL DEFAULT 0, inactive INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS invites (
                    hash TEXT PRIMARY KEY, created REAL NOT NULL, expires REAL NOT NULL, used_by INTEGER);
                CREATE TABLE IF NOT EXISTS notes (
                    user INTEGER NOT NULL, day TEXT NOT NULL, kind TEXT NOT NULL, PRIMARY KEY(user, day, kind));
                CREATE TABLE IF NOT EXISTS usage_day (
                    user INTEGER NOT NULL, day TEXT NOT NULL, papers INTEGER NOT NULL DEFAULT 0,
                    questions INTEGER NOT NULL DEFAULT 0, usd REAL NOT NULL DEFAULT 0, PRIMARY KEY(user, day));
                -- A reservation exists before its job does: it is keyed by the request and bound to the job later.
                CREATE TABLE IF NOT EXISTS reservations (
                    key TEXT PRIMARY KEY, job TEXT UNIQUE, user INTEGER NOT NULL, day TEXT NOT NULL,
                    kind TEXT NOT NULL, reserved REAL NOT NULL);
            """)
            db.execute("INSERT INTO members(user, role, joined, last_active) VALUES(?, 'owner', ?, ?) "
                       "ON CONFLICT(user) DO UPDATE SET role='owner', revoked=0", (owner_id, self.now(), self.now()))

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def cairo_day(self, ts: float | None = None) -> str:
        return datetime.fromtimestamp(self.now() if ts is None else ts, CAIRO).strftime("%Y-%m-%d")

    def create_invites(self, count: int) -> list[str]:
        if type(count) is not int or not 1 <= count <= 10:
            raise ValueError("invite_count")
        codes = ["".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH)) for _ in range(count)]
        with self._db() as db:
            for code in codes:
                db.execute("INSERT INTO invites(hash, created, expires) VALUES(?, ?, ?)",
                           (_hash(code), self.now(), self.now() + INVITE_SECONDS))
        return codes

    def redeem(self, user: int, code: str) -> bool:
        """True when the sender is (now) a member; an existing member consumes nothing."""
        with self._db() as db:
            member = db.execute("SELECT revoked FROM members WHERE user=?", (user,)).fetchone()
            if member is not None and not member["revoked"]:
                return True
            used = db.execute("UPDATE invites SET used_by=? WHERE hash=? AND used_by IS NULL AND expires>?",
                              (user, _hash(code), self.now())).rowcount
            if used != 1:
                return False
            db.execute("INSERT INTO members(user, role, joined, last_active) VALUES(?, 'student', ?, ?) "
                       "ON CONFLICT(user) DO UPDATE SET revoked=0, inactive=0, last_active=excluded.last_active",
                       (user, self.now(), self.now()))
            return True

    def role(self, user: int) -> Role | None:
        with self._db() as db:
            row = db.execute("SELECT role, revoked FROM members WHERE user=?", (user,)).fetchone()
        return None if row is None or row["revoked"] else row["role"]

    def is_revoked(self, user: int) -> bool:
        with self._db() as db:
            row = db.execute("SELECT revoked FROM members WHERE user=?", (user,)).fetchone()
        return bool(row and row["revoked"])

    def revoke(self, user: int) -> bool:
        if user == self.owner_id:
            return False
        with self._db() as db:
            return db.execute("UPDATE members SET revoked=1 WHERE user=? AND role='student' AND revoked=0",
                              (user,)).rowcount == 1

    def touch(self, user: int) -> None:
        with self._db() as db:
            db.execute("UPDATE members SET last_active=?, inactive=0 WHERE user=?", (self.now(), user))

    def mark_inactive(self, user: int) -> None:
        with self._db() as db:
            db.execute("UPDATE members SET inactive=1 WHERE user=?", (user,))

    def is_inactive(self, user: int) -> bool:
        with self._db() as db:
            row = db.execute("SELECT inactive FROM members WHERE user=?", (user,)).fetchone()
        return bool(row and row["inactive"])

    def note_once(self, user: int, kind: str) -> bool:
        with self._db() as db:
            return db.execute("INSERT OR IGNORE INTO notes(user, day, kind) VALUES(?, ?, ?)",
                              (user, self.cairo_day(), kind)).rowcount == 1

    def members(self) -> list[dict]:
        with self._db() as db:
            return [dict(row) for row in db.execute(
                "SELECT user, role, joined, last_active, revoked, inactive FROM members ORDER BY joined")]

    # Limits and the dollar ledger (spec §3).

    def worst_call_usd(self) -> float:
        return call_cost_usd(DEFAULT_PROFILE, None, estimate=WORST_INPUT_TOKENS)

    def allow_message(self, user: int) -> bool:
        window = self._messages.setdefault(user, deque())
        while window and window[0] <= self.now() - 60:
            window.popleft()
        if len(window) >= self.settings.messages_per_minute:
            return False
        window.append(self.now())
        return True

    def _day_row(self, db, user: int, day: str) -> sqlite3.Row:
        db.execute("INSERT OR IGNORE INTO usage_day(user, day) VALUES(?, ?)", (user, day))
        return db.execute("SELECT * FROM usage_day WHERE user=? AND day=?", (user, day)).fetchone()

    @staticmethod
    def _day_totals(db, day: str) -> tuple[float, float]:
        spent = db.execute("SELECT COALESCE(SUM(usd), 0) FROM usage_day WHERE day=?", (day,)).fetchone()[0]
        reserved = db.execute("SELECT COALESCE(SUM(reserved), 0) FROM reservations WHERE day=?", (day,)).fetchone()[0]
        return spent, reserved

    def admit(self, user: int, kind: Kind, key: str, max_calls: int) -> str | None:
        """None when admitted (a reservation is recorded under key), else the refusal text."""
        day, amount = self.cairo_day(), max_calls * self.worst_call_usd()
        with self._db() as db:
            role = db.execute("SELECT role FROM members WHERE user=? AND revoked=0", (user,)).fetchone()
            if role is not None and role["role"] == "student":
                row = self._day_row(db, user, day)
                if kind == "paper" and row["papers"] >= self.settings.daily_papers:
                    return access_text.PAPERS_USED.format(P=self.settings.daily_papers)
                if kind == "question" and row["questions"] >= self.settings.daily_questions:
                    return access_text.QUESTIONS_USED.format(Q=self.settings.daily_questions)
            spent, reserved = self._day_totals(db, day)
            if amount > 0 and spent + reserved + amount > self.settings.daily_usd_ceiling + 1e-9:
                return access_text.CEILING
            db.execute("INSERT INTO reservations(key, user, day, kind, reserved) VALUES(?, ?, ?, ?, ?)",
                       (key, user, day, kind, amount))
        return None

    @staticmethod
    def _reservation(db, ref: str) -> sqlite3.Row | None:
        return db.execute("SELECT * FROM reservations WHERE key=? OR job=?", (ref, ref)).fetchone()

    def bind(self, key: str, job: str) -> None:
        with self._db() as db:
            db.execute("UPDATE reservations SET job=? WHERE key=?", (job, key))

    def charge(self, ref: str, usd: float) -> None:
        with self._db() as db:
            reservation = self._reservation(db, ref)
            if reservation is None:
                return
            self._day_row(db, reservation["user"], reservation["day"])
            db.execute("UPDATE usage_day SET usd=usd+? WHERE user=? AND day=?",
                       (usd, reservation["user"], reservation["day"]))
            db.execute("UPDATE reservations SET reserved=MAX(0, reserved-?) WHERE key=?", (usd, reservation["key"]))

    def settle(self, ref: str, *, delivered_kind: Literal["paper", "question"] | None) -> None:
        with self._db() as db:
            reservation = self._reservation(db, ref)
            if reservation is None:
                return
            role = db.execute("SELECT role FROM members WHERE user=?", (reservation["user"],)).fetchone()
            if delivered_kind in ("paper", "question") and role is not None and role["role"] == "student":
                self._day_row(db, reservation["user"], reservation["day"])
                column = "papers" if delivered_kind == "paper" else "questions"
                db.execute(f"UPDATE usage_day SET {column}={column}+1 WHERE user=? AND day=?",
                           (reservation["user"], reservation["day"]))
            db.execute("DELETE FROM reservations WHERE key=?", (reservation["key"],))

    def release(self, ref: str) -> None:
        with self._db() as db:
            db.execute("DELETE FROM reservations WHERE key=? OR job=?", (ref, ref))

    def open_reservations(self) -> list[dict]:
        with self._db() as db:
            return [dict(row) for row in db.execute("SELECT * FROM reservations")]

    def usage(self, user: int) -> dict:
        with self._db() as db:
            row = self._day_row(db, user, self.cairo_day())
        return {"papers_left": max(0, self.settings.daily_papers - row["papers"]),
                "questions_left": max(0, self.settings.daily_questions - row["questions"])}

    def day_usage(self, user: int) -> dict:
        with self._db() as db:
            row = self._day_row(db, user, self.cairo_day())
        return {"papers": row["papers"], "questions": row["questions"], "usd": row["usd"]}

    def owner_usage(self) -> dict:
        day = self.cairo_day()
        with self._db() as db:
            spent, reserved = self._day_totals(db, day)
            top = [{"user": row["user"], "usd": row["usd"], "papers": row["papers"], "questions": row["questions"]}
                   for row in db.execute("SELECT u.* FROM usage_day u JOIN members m ON m.user=u.user "
                                         "WHERE u.day=? AND m.role='student' ORDER BY u.usd DESC LIMIT 5", (day,))]
        return {"spent": spent, "reserved": reserved, "ceiling": self.settings.daily_usd_ceiling, "top": top}
