"""Purge control flow, without a database.

The integration suite proves the SQL; these prove the guards around it, which are what
stand between a stale expected count and a hard delete. They run without Docker, so the
destructive path stays covered on hosts where the container suite only skips.
"""

import uuid

import pytest
from src.commands.ai_scope import EXIT_COUNT_MISMATCH, EXIT_OK, EXIT_VIOLATIONS_FOUND, build_parser, run_audit, run_purge, scan
from src.repositories.paper import CategoryRow


class StubSession:
    def __init__(self):
        self.committed = False
        self.rolled_back = False

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


class StubRepository:
    """Records how the command asked for rows and what it asked to delete."""

    def __init__(self, rows):
        self.session = StubSession()
        self._rows = rows
        self.locked = None
        self.deleted = None

    def list_all_categories(self, *, for_update=False):
        self.locked = for_update
        return list(self._rows)

    def delete_by_ids(self, paper_ids):
        self.deleted = list(paper_ids)
        return len(self.deleted)


def row(arxiv_id, categories) -> CategoryRow:
    return CategoryRow(id=uuid.uuid4(), arxiv_id=arxiv_id, categories=categories)


@pytest.fixture
def mixed() -> StubRepository:
    return StubRepository(
        [
            row("2401.00001", ["cs.AI"]),
            row("2401.00002", ["hep-th"]),
            row("2401.00003", ["quant-ph", "cs.LG"]),
            row("2401.00004", ["cs.IR"]),
        ]
    )


def test_scan_splits_the_corpus_by_the_shared_predicate(mixed):
    report = scan(mixed)

    assert report.scanned == 4
    assert report.compliant == 2
    assert [violation.arxiv_id for violation in report.violations] == ["2401.00002", "2401.00004"]


def test_audit_never_locks_rows_and_never_deletes(mixed):
    assert run_audit(mixed).exit_code == EXIT_OK

    assert mixed.locked is False
    assert mixed.deleted is None
    assert mixed.session.committed is False


def test_audit_signals_violations_only_when_asked(mixed):
    assert run_audit(mixed).exit_code == EXIT_OK
    assert run_audit(mixed, fail_on_violation=True).exit_code == EXIT_VIOLATIONS_FOUND


def test_audit_on_a_clean_corpus_is_quiet_even_when_told_to_fail():
    clean = StubRepository([row("2401.00001", ["cs.NE"])])

    assert run_audit(clean, fail_on_violation=True).exit_code == EXIT_OK


def test_dry_run_never_reaches_the_delete(mixed):
    assert run_purge(mixed, expected_count=None, apply=False).exit_code == EXIT_OK

    assert mixed.deleted is None
    assert mixed.locked is False, "a read-only rehearsal must not hold row locks"
    assert mixed.session.committed is False


def test_dry_run_still_honours_a_mismatched_expected_count(mixed):
    """So the exact command can be rehearsed before --apply is added to it."""
    assert run_purge(mixed, expected_count=99, apply=False).exit_code == EXIT_COUNT_MISMATCH
    assert mixed.deleted is None


def test_mismatched_expected_count_aborts_and_releases_locks(mixed):
    assert run_purge(mixed, expected_count=99, apply=True).exit_code == EXIT_COUNT_MISMATCH

    assert mixed.deleted is None
    assert mixed.session.committed is False
    assert mixed.session.rolled_back is True


def test_apply_deletes_exactly_the_violations_it_counted(mixed):
    violations = [violation.id for violation in scan(mixed).violations]

    outcome = run_purge(mixed, expected_count=2, apply=True)

    assert outcome.exit_code == EXIT_OK
    assert mixed.deleted == violations
    assert outcome.deleted == 2
    assert outcome.applied is True
    assert mixed.session.committed is True


def test_apply_locks_rows_for_the_duration_of_the_delete(mixed):
    run_purge(mixed, expected_count=2, apply=True)

    assert mixed.locked is True, "the count that authorises a delete has to hold row locks"


def test_apply_on_a_clean_corpus_deletes_nothing():
    clean = StubRepository([row("2401.00001", ["stat.ML"])])

    assert run_purge(clean, expected_count=0, apply=True).exit_code == EXIT_OK
    assert clean.deleted == []


def test_malformed_categories_are_violations_rather_than_crashes():
    broken = StubRepository([row("2401.00001", None), row("2401.00002", []), row("2401.00003", [123, None])])

    assert len(scan(broken).violations) == 3


def test_apply_requires_an_expected_count():
    args = build_parser().parse_args(["purge", "--apply"])

    assert args.expected_count is None, "main() must reject this combination before any database work"


def test_purge_defaults_to_a_dry_run():
    assert build_parser().parse_args(["purge"]).apply is False


def test_a_subcommand_is_required():
    with pytest.raises(SystemExit):
        build_parser().parse_args([])
