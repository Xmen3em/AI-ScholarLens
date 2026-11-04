import pytest
from src.services.study import access_text
from src.services.study.access import AccessGate
from src.services.study.access_settings import AccessSettings

from tests.unit.test_access_gate import OWNER, Clock


@pytest.fixture
def clock():
    return Clock()


def make_gate(tmp_path, clock, **settings):
    return AccessGate(tmp_path / "sessions.sqlite3", AccessSettings(_env_file=None, **settings), OWNER, now=clock)


def join(gate, *users):
    for user, code in zip(users, gate.create_invites(len(users))):
        assert gate.redeem(user, code)
    return users


@pytest.fixture
def gate(tmp_path, clock):
    return make_gate(tmp_path, clock)


@pytest.fixture
def student(gate):
    return join(gate, 111)[0]


def test_worst_call_is_the_profiles_worst_case(gate):
    # GLM-5.3: 20,000 input tokens at $0.90/M plus 3,000 output tokens at $4.00/M.
    assert gate.worst_call_usd() == pytest.approx(0.030)


def test_only_delivered_answers_count(gate, student):
    assert gate.admit(student, "paper", "k1", 2) is None
    gate.settle("k1", delivered_kind=None)
    assert gate.usage(student)["papers_left"] == 3


def test_papers_run_out(gate, student):
    for i in range(3):
        assert gate.admit(student, "paper", f"k{i}", 2) is None
        gate.settle(f"k{i}", delivered_kind="paper")
    assert gate.admit(student, "paper", "k9", 2) == access_text.PAPERS_USED.format(P=3)
    assert gate.admit(student, "question", "k10", 2) is None


def test_questions_run_out(tmp_path, clock):
    gate = make_gate(tmp_path, clock, daily_questions=1)
    [student] = join(gate, 111)
    gate.admit(student, "question", "k1", 2)
    gate.settle("k1", delivered_kind="question")
    assert gate.admit(student, "question", "k2", 2) == access_text.QUESTIONS_USED.format(Q=1)


def test_other_requests_need_no_count(tmp_path, clock):
    gate = make_gate(tmp_path, clock, daily_papers=1)
    [student] = join(gate, 111)
    gate.admit(student, "paper", "k1", 2)
    gate.settle("k1", delivered_kind="paper")
    assert gate.admit(student, "other", "k2", 2) is None


def test_owner_is_exempt_from_counts_not_the_ceiling(tmp_path, clock):
    gate = make_gate(tmp_path, clock, daily_papers=1, daily_usd_ceiling=0.10)
    assert gate.admit(OWNER, "paper", "k1", 2) is None
    gate.settle("k1", delivered_kind="paper")
    assert gate.admit(OWNER, "paper", "k2", 2) is None  # over the count, still under the ceiling
    assert gate.admit(OWNER, "paper", "k3", 2) == access_text.CEILING  # 0.06 + 0.06 > 0.10


def test_parallel_reservations_never_exceed_the_ceiling(tmp_path, clock):
    gate = make_gate(tmp_path, clock, daily_usd_ceiling=0.15)
    students = join(gate, 111, 222, 333)
    refusals = [gate.admit(user, "question", f"k{user}", 2) for user in students]
    assert refusals.count(None) == 2 and refusals[2] == access_text.CEILING


def test_charge_replaces_the_reservation(gate, student):
    gate.admit(student, "question", "k1", 2)
    gate.bind("k1", "job1")
    gate.charge("job1", 0.01)
    usage = gate.owner_usage()
    assert usage["spent"] == pytest.approx(0.01) and usage["reserved"] == pytest.approx(0.05)
    gate.settle("job1", delivered_kind="question")
    usage = gate.owner_usage()
    assert usage["spent"] == pytest.approx(0.01) and usage["reserved"] == 0
    assert gate.usage(student)["questions_left"] == 29


def test_a_charge_beyond_the_reservation_is_still_recorded(gate, student):
    gate.admit(student, "question", "k1", 1)
    gate.charge("k1", 0.05)
    assert gate.owner_usage()["spent"] == pytest.approx(0.05) and gate.owner_usage()["reserved"] == 0


def test_a_job_admitted_before_midnight_counts_that_day(gate, student, clock):
    clock.set_cairo("2026-11-04 23:59:00")
    gate.admit(student, "paper", "k1", 2)
    clock.set_cairo("2026-11-05 00:01:00")
    gate.settle("k1", delivered_kind="paper")
    assert gate.usage(student)["papers_left"] == 3
    clock.set_cairo("2026-11-04 23:59:30")
    assert gate.usage(student)["papers_left"] == 2


def test_release_frees_a_reservation_without_counting(gate, student):
    gate.admit(student, "question", "k1", 2)
    gate.release("k1")
    assert gate.owner_usage()["reserved"] == 0 and gate.usage(student)["questions_left"] == 30


def test_unknown_jobs_are_ignored(gate):
    gate.charge("missing", 0.01)
    gate.settle("missing", delivered_kind="paper")
    gate.release("missing")
    assert gate.owner_usage()["spent"] == 0


def test_owner_usage_lists_top_students(gate):
    students = join(gate, 111, 222)
    for user, cost in zip(students, (0.02, 0.04)):
        gate.admit(user, "question", f"k{user}", 2)
        gate.charge(f"k{user}", cost)
        gate.settle(f"k{user}", delivered_kind="question")
    usage = gate.owner_usage()
    assert usage["ceiling"] == 2.00 and [row["user"] for row in usage["top"]] == [222, 111]
    assert usage["top"][0] == {"user": 222, "usd": pytest.approx(0.04), "papers": 0, "questions": 1}


def test_rate_window(gate, student, clock):
    assert all(gate.allow_message(student) for _ in range(6)) and not gate.allow_message(student)
    clock.advance(61)
    assert gate.allow_message(student)


def test_ledger_survives_a_restart(tmp_path, clock):
    first = make_gate(tmp_path, clock)
    [student] = join(first, 111)
    first.admit(student, "paper", "k1", 2)
    first.charge("k1", 0.02)
    second = make_gate(tmp_path, clock)
    assert second.owner_usage()["spent"] == pytest.approx(0.02) and second.owner_usage()["reserved"] == pytest.approx(0.04)


def test_requests_without_model_calls_pass_a_reached_ceiling(tmp_path, clock):
    # Final review, Important 2: /forget and /study reserve nothing, so the ceiling cannot refuse them.
    gate = make_gate(tmp_path, clock, daily_usd_ceiling=0.10)
    [student] = join(gate, 111)
    gate.admit(student, "question", "k1", 2)
    gate.charge("k1", 0.12)  # real cost can exceed a reservation; spend is now over the ceiling
    gate.settle("k1", delivered_kind="question")
    assert gate.admit(student, "other", "k2", 0) is None
    assert gate.admit(student, "question", "k3", 2) == access_text.CEILING
