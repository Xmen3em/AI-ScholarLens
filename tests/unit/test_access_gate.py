from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from src.services.study.access import AccessGate
from src.services.study.access_settings import AccessSettings

OWNER = 1001
CAIRO = ZoneInfo("Africa/Cairo")


class Clock:
    def __init__(self):
        self.value = datetime(2026, 11, 4, 12, 0, tzinfo=CAIRO).timestamp()

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds

    def set_cairo(self, text: str) -> None:
        self.value = datetime.strptime(text, "%Y-%m-%d %H:%M:%S").replace(tzinfo=CAIRO).timestamp()


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "sessions.sqlite3"


@pytest.fixture
def gate(db_path, clock):
    return AccessGate(db_path, AccessSettings(_env_file=None), OWNER, now=clock)


def test_owner_is_always_a_member(gate):
    assert gate.role(OWNER) == "owner"


def test_strangers_are_not_members(gate):
    assert gate.role(999) is None


def test_invite_codes_are_single_use_and_normalised(gate):
    [code] = gate.create_invites(1)
    assert len(code) == 10 and set(code) <= set("ABCDEFGHJKMNPQRSTUVWXYZ23456789")
    assert gate.redeem(111, "  " + code.lower() + " ") and gate.role(111) == "student"
    assert not gate.redeem(222, code) and gate.role(222) is None


def test_codes_expire_after_seven_days(gate, clock):
    [code] = gate.create_invites(1)
    clock.advance(7 * 86400 + 1)
    assert not gate.redeem(111, code) and gate.role(111) is None


def test_unknown_codes_are_refused(gate):
    assert not gate.redeem(111, "ABCDEFGHJK")


def test_codes_are_stored_only_as_hashes(gate, db_path):
    codes = gate.create_invites(3)
    data = b"".join(path.read_bytes() for path in db_path.parent.glob(db_path.name + "*"))
    assert all(code.encode() not in data for code in codes)


def test_a_member_redeeming_again_consumes_nothing(gate):
    [first, second] = gate.create_invites(2)
    gate.redeem(111, first)
    assert gate.redeem(111, second) and gate.redeem(222, second) and gate.role(222) == "student"


def test_revoke_blocks_and_a_new_code_readmits(gate):
    [first, second] = gate.create_invites(2)
    gate.redeem(111, first)
    assert gate.revoke(111) and gate.role(111) is None and gate.is_revoked(111)
    assert gate.redeem(111, second) and gate.role(111) == "student" and not gate.is_revoked(111)


def test_owner_cannot_be_revoked(gate):
    assert not gate.revoke(OWNER) and gate.role(OWNER) == "owner"


def test_revoking_a_stranger_does_nothing(gate):
    assert not gate.revoke(999)


def test_notes_are_sent_once_per_cairo_day(gate, clock):
    assert gate.note_once(999, "not_member") and not gate.note_once(999, "not_member")
    assert gate.note_once(999, "revoked")
    clock.set_cairo("2026-11-05 00:00:01")
    assert gate.note_once(999, "not_member")


def test_cairo_day_rolls_over_at_local_midnight(gate, clock):
    clock.set_cairo("2026-11-04 23:59:59")
    assert gate.cairo_day() == "2026-11-04"
    clock.advance(2)
    assert gate.cairo_day() == "2026-11-05"


def test_invite_count_is_bounded(gate):
    with pytest.raises(ValueError):
        gate.create_invites(11)
    with pytest.raises(ValueError):
        gate.create_invites(0)


def test_touch_records_activity_and_clears_inactive(gate, clock):
    [code] = gate.create_invites(1)
    gate.redeem(111, code)
    gate.mark_inactive(111)
    assert gate.is_inactive(111)
    clock.advance(60)
    gate.touch(111)
    assert not gate.is_inactive(111)
    [row] = [member for member in gate.members() if member["user"] == 111]
    assert row["last_active"] == clock() and row["role"] == "student"


def test_members_lists_the_owner_and_students(gate):
    [code] = gate.create_invites(1)
    gate.redeem(111, code)
    assert {(row["user"], row["role"]) for row in gate.members()} == {(OWNER, "owner"), (111, "student")}


def test_the_gate_survives_a_restart(db_path, clock):
    first = AccessGate(db_path, AccessSettings(_env_file=None), OWNER, now=clock)
    [code] = first.create_invites(1)
    first.redeem(111, code)
    second = AccessGate(db_path, AccessSettings(_env_file=None), OWNER, now=clock)
    assert second.role(111) == "student" and second.role(OWNER) == "owner"
