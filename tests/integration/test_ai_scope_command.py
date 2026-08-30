"""The audit/purge command against a real PostgreSQL schema.

Purge hard-deletes rows, so the parts worth proving are the ones a mocked session
cannot: that the expected-count guard actually blocks a delete, that the delete is
committed, and that it removes only the papers the audit named.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import Session
from src.commands.ai_scope import EXIT_COUNT_MISMATCH, EXIT_OK, EXIT_VIOLATIONS_FOUND, main, run_audit, run_purge, scan
from src.models.paper import Paper
from src.repositories.paper import PaperRepository

from tests.integration.test_paper_repository import make_paper


@pytest.fixture
def repository(db_session) -> PaperRepository:
    return PaperRepository(db_session)


def stub_get_db_session(session, opened=None):
    """Stand in for the command's session accessor, recording each time it is opened."""

    @contextmanager
    def factory():
        if opened is not None:
            opened.append(True)
        yield session

    return factory


def store_raw(db_session, arxiv_id: str, categories) -> None:
    """Insert a row through the model, bypassing Pydantic.

    Rows already in the corpus predate this validation, so the audit has to cope with
    category values that ``PaperCreate`` would reject outright.
    """
    db_session.add(
        Paper(
            id=uuid.uuid4(),
            arxiv_id=arxiv_id,
            title=f"Paper {arxiv_id}",
            authors=["Ada Lovelace"],
            abstract="An abstract.",
            categories=categories,
            published_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
            pdf_url=f"https://arxiv.org/pdf/{arxiv_id}",
        )
    )
    db_session.commit()


def seed(repository, *specs) -> None:
    """Insert papers and commit, as a completed ingestion run would have left them."""
    for arxiv_id, categories in specs:
        repository.upsert(make_paper(arxiv_id, categories=categories))
    repository.session.commit()


def test_audit_reports_scanned_compliant_and_non_compliant_rows(repository):
    seed(
        repository,
        ("2401.00001", ["cs.AI"]),
        ("2401.00002", ["cs.CL", "cs.LG"]),
        ("2401.00003", ["hep-th"]),
        ("2401.00004", ["cs.IR", "cs.DL"]),
    )

    report = scan(repository)

    assert report.scanned == 4
    assert report.compliant == 2
    assert [row.arxiv_id for row in report.violations] == ["2401.00003", "2401.00004"]
    assert [row.categories for row in report.violations] == [["hep-th"], ["cs.IR", "cs.DL"]]


def test_cross_listed_ai_papers_are_compliant(repository):
    seed(
        repository,
        ("2401.00001", ["quant-ph", "cs.LG"]),
        ("2401.00002", ["math.CO", "stat.ML"]),
    )

    assert scan(repository).violations == []


def test_malformed_categories_are_reported_not_crashed(db_session, repository):
    store_raw(db_session, "2401.00001", [])
    store_raw(db_session, "2401.00002", [123, None])
    store_raw(db_session, "2401.00003", None)

    report = scan(repository)

    assert report.scanned == 3
    assert [row.arxiv_id for row in report.violations] == ["2401.00001", "2401.00002", "2401.00003"]


def test_dry_run_purge_deletes_nothing(repository):
    seed(repository, ("2401.00001", ["cs.AI"]), ("2401.00002", ["hep-th"]), ("2401.00003", ["cs.IR"]))

    assert run_purge(repository, expected_count=None, apply=False).exit_code == EXIT_OK
    assert repository.get_count() == 3


def test_expected_count_mismatch_aborts_without_deleting(repository):
    seed(repository, ("2401.00001", ["cs.AI"]), ("2401.00002", ["hep-th"]))

    assert run_purge(repository, expected_count=5, apply=True).exit_code == EXIT_COUNT_MISMATCH
    assert repository.get_count() == 2, "a stale expected count must never authorise a delete"


def test_purge_with_a_matching_count_removes_only_the_violations(repository):
    seed(
        repository,
        ("2401.00001", ["cs.AI"]),
        ("2401.00002", ["quant-ph", "cs.RO"]),
        ("2401.00003", ["stat.ML"]),
        ("2401.00004", ["hep-th"]),
        ("2401.00005", ["cs.IR"]),
    )

    assert run_purge(repository, expected_count=2, apply=True).exit_code == EXIT_OK

    survivors = sorted(paper.arxiv_id for paper in repository.get_all())
    assert survivors == ["2401.00001", "2401.00002", "2401.00003"]


def test_purge_is_committed_and_visible_to_a_new_session(postgres_engine, repository):
    seed(repository, ("2401.00001", ["cs.AI"]), ("2401.00002", ["hep-th"]))

    run_purge(repository, expected_count=1, apply=True)

    with Session(postgres_engine) as other_session:
        assert PaperRepository(other_session).get_count() == 1


def test_rerunning_purge_is_idempotent(repository):
    seed(repository, ("2401.00001", ["cs.AI"]), ("2401.00002", ["hep-th"]))
    run_purge(repository, expected_count=1, apply=True)

    assert run_purge(repository, expected_count=0, apply=True).exit_code == EXIT_OK
    assert repository.get_count() == 1


def test_purge_on_an_all_compliant_corpus_is_a_no_op(repository):
    # Guards the empty-id early return: `IN ()` is a SQL syntax error.
    seed(repository, ("2401.00001", ["cs.AI"]), ("2401.00002", ["cs.NE"]))

    assert run_purge(repository, expected_count=0, apply=True).exit_code == EXIT_OK
    assert repository.get_count() == 2


def test_audit_exit_code_only_signals_violations_when_asked(repository):
    seed(repository, ("2401.00001", ["hep-th"]))

    assert run_audit(repository).exit_code == EXIT_OK
    assert run_audit(repository, fail_on_violation=True).exit_code == EXIT_VIOLATIONS_FOUND


def test_main_audit_reports_through_the_cli(monkeypatch, db_session, repository):
    seed(repository, ("2401.00001", ["cs.AI"]), ("2401.00002", ["hep-th"]))
    monkeypatch.setattr("src.commands.ai_scope.get_db_session", stub_get_db_session(db_session))

    assert main(["audit"]) == EXIT_OK
    assert main(["audit", "--fail-on-violation"]) == EXIT_VIOLATIONS_FOUND


def test_main_purge_applies_the_deletion_end_to_end(monkeypatch, db_session, repository):
    seed(repository, ("2401.00001", ["cs.AI"]), ("2401.00002", ["hep-th"]))
    monkeypatch.setattr("src.commands.ai_scope.get_db_session", stub_get_db_session(db_session))

    assert main(["purge", "--expected-count", "1", "--apply"]) == EXIT_OK
    assert [paper.arxiv_id for paper in repository.get_all()] == ["2401.00001"]


def test_main_purge_apply_without_expected_count_is_a_usage_error(monkeypatch):
    opened = []
    monkeypatch.setattr("src.commands.ai_scope.get_db_session", stub_get_db_session(None, opened))

    with pytest.raises(SystemExit) as excinfo:
        main(["purge", "--apply"])

    assert excinfo.value.code == 2
    assert opened == [], "the usage error must land before any database work"
