"""PaperRepository against a real PostgreSQL schema.

The ingestion DAG re-runs the same date routinely, so `upsert` is the method the whole
pipeline's safety rests on: it must update in place and must not blank content it was
not given. Nothing else in the suite exercises real SQL.
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError
from src.repositories.paper import PaperRepository
from src.schemas.arxiv.paper import PaperCreate


def make_paper(arxiv_id: str = "2401.00001", *, day: int = 1, **overrides) -> PaperCreate:
    """A valid paper payload; `day` varies published_date so ordering is deterministic."""
    fields = {
        "arxiv_id": arxiv_id,
        "title": f"Paper {arxiv_id}",
        "authors": ["Ada Lovelace"],
        "abstract": "An abstract.",
        "categories": ["cs.AI"],
        "published_date": datetime(2024, 1, day, tzinfo=timezone.utc),
        "pdf_url": f"https://arxiv.org/pdf/{arxiv_id}",
    }
    fields.update(overrides)
    return PaperCreate(**fields)


@pytest.fixture
def repository(db_session) -> PaperRepository:
    return PaperRepository(db_session)


def test_upsert_updates_the_existing_row_instead_of_duplicating_it(repository):
    # The DAG re-runs the same date; a second ingestion must not create a second row.
    repository.upsert(make_paper(title="First title"))
    repository.upsert(make_paper(title="Corrected title"))

    assert repository.get_count() == 1
    assert repository.get_by_arxiv_id("2401.00001").title == "Corrected title"


def test_upsert_keeps_parsed_content_when_a_later_run_supplies_none(repository):
    # A re-run whose PDF failed sends metadata only. Without exclude_unset that would
    # blank raw_text on a paper that had already been parsed successfully.
    repository.upsert(make_paper(raw_text="Extracted text", parser_used="docling", pdf_processed=True))

    repository.upsert(make_paper(title="Metadata-only re-run"))

    stored = repository.get_by_arxiv_id("2401.00001")
    assert stored.title == "Metadata-only re-run"
    assert stored.raw_text == "Extracted text"
    assert stored.pdf_processed is True


def test_duplicate_arxiv_id_is_rejected_by_the_schema(repository):
    repository.create(make_paper())

    with pytest.raises(IntegrityError):
        repository.create(make_paper())


def test_papers_are_listed_newest_first_and_paginated(repository):
    for index, day in enumerate([1, 3, 2], start=1):
        repository.upsert(make_paper(f"2401.0000{index}", day=day))

    first_page = repository.get_all(limit=2, offset=0)
    second_page = repository.get_all(limit=2, offset=2)

    assert [paper.arxiv_id for paper in first_page] == ["2401.00002", "2401.00003"]
    assert [paper.arxiv_id for paper in second_page] == ["2401.00001"]
    assert repository.get_count() == 3


def test_unprocessed_query_excludes_papers_that_were_parsed(repository):
    repository.upsert(make_paper("2401.00001", raw_text="Extracted", pdf_processed=True))
    repository.upsert(make_paper("2401.00002"))

    unprocessed = repository.get_unprocessed_papers()
    processed = repository.get_processed_papers()

    assert [paper.arxiv_id for paper in unprocessed] == ["2401.00002"]
    assert [paper.arxiv_id for paper in processed] == ["2401.00001"]


def test_processing_stats_report_rates_over_stored_papers(repository):
    repository.upsert(make_paper("2401.00001", raw_text="Extracted", pdf_processed=True))
    repository.upsert(make_paper("2401.00002", pdf_processed=True))
    repository.upsert(make_paper("2401.00003"))

    stats = repository.get_processing_stats()

    assert stats["total_papers"] == 3
    assert stats["processed_papers"] == 2
    assert stats["papers_with_text"] == 1
    assert stats["processing_rate"] == pytest.approx(66.67, abs=0.01)
    assert stats["text_extraction_rate"] == pytest.approx(50.0)


def test_processing_stats_on_an_empty_table_do_not_divide_by_zero(repository):
    stats = repository.get_processing_stats()

    assert stats["total_papers"] == 0
    assert stats["processing_rate"] == 0
    assert stats["text_extraction_rate"] == 0
