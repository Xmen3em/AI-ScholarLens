"""Invite-only beta access: members, invites and once-a-day notes (docs/specs/multi-user.md §2).

The tables live beside the study store in the same SQLite file. Invite codes are stored only
as SHA-256; a code is trimmed and upper-cased before it is checked.
"""

import hashlib
import secrets
import sqlite3
import time
from collections.abc import Callable
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from src.services.study.access_settings import AccessSettings

CAIRO = ZoneInfo("Africa/Cairo")
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 10
INVITE_SECONDS = 7 * 86400
Role = Literal["owner", "student"]


def _hash(code: str) -> str:
    return hashlib.sha256(code.strip().upper().encode()).hexdigest()


class AccessGate:
    def __init__(self, path: Path, settings: AccessSettings, owner_id: int, *, now: Callable[[], float] = time.time):
        if path.is_symlink():
            raise ValueError("invalid_access_store")
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path, self.settings, self.owner_id, self.now = path, settings, owner_id, now
        with self._db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS members (
                    user INTEGER PRIMARY KEY, role TEXT NOT NULL, joined REAL NOT NULL, last_active REAL NOT NULL,
                    revoked INTEGER NOT NULL DEFAULT 0, inactive INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS invites (
                    hash TEXT PRIMARY KEY, created REAL NOT NULL, expires REAL NOT NULL, used_by INTEGER);
                CREATE TABLE IF NOT EXISTS notes (
                    user INTEGER NOT NULL, day TEXT NOT NULL, kind TEXT NOT NULL, PRIMARY KEY(user, day, kind));
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
