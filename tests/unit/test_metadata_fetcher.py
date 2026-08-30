"""Pipeline accounting: what happens to a paper whose PDF never becomes parsed content.

Regression cover for the 2026-08-27 ingestion run, which stored 10 papers with
`pdfs_downloaded: 0` and an identical "PDF processing not available or failed" note,
leaving the failure reason only in the task log.
"""

from pathlib import Path

import pytest
from src.schemas.arxiv.paper import ArxivPaper
from src.schemas.pdf_parser.models import ParserType, PdfContent
from src.services.metadata_fetcher import MetadataFetcher


class FakeArxivClient:
    """Stands in for the arXiv HTTP boundary: returns metadata and cached PDF paths."""

    def __init__(self, papers, download_result=Path("/cache/2401.00001.pdf")):
        self.papers = papers
        self.download_result = download_result
        self.pdf_cache_dir = Path("/cache")
        self.downloaded = []

    async def fetch_papers(self, **kwargs):
        return self.papers

    async def download_pdf(self, paper, force_download=False):
        self.downloaded.append(paper.arxiv_id)
        if isinstance(self.download_result, Exception):
            raise self.download_result
        return self.download_result


class FakePdfParser:
    """Stands in for Docling: returns content, declines the file, or fails."""

    def __init__(self, result):
        self.result = result
        self.parsed = []

    async def parse_pdf(self, pdf_path):
        self.parsed.append(pdf_path)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class RecordingSession:
    """Captures what the repository would have written, without a database."""

    def __init__(self):
        self.stored = {}
        self.committed = False
        self.rolled_back = False

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


class RecordingRepository:
    def __init__(self, session):
        self._session = session

    def upsert(self, paper_create):
        self._session.stored[paper_create.arxiv_id] = paper_create
        return paper_create


@pytest.fixture
def paper() -> ArxivPaper:
    return ArxivPaper(
        arxiv_id="2401.00001",
        title="Test paper",
        authors=["Ada Lovelace"],
        abstract="A test abstract.",
        categories=["cs.AI"],
        published_date="2024-01-01T00:00:00Z",
        pdf_url="https://arxiv.org/pdf/2401.00001",
    )


@pytest.fixture
def recording_session(monkeypatch) -> RecordingSession:
    monkeypatch.setattr("src.services.metadata_fetcher.PaperRepository", RecordingRepository)
    return RecordingSession()


def parsed_content() -> PdfContent:
    return PdfContent(raw_text="Extracted text", parser_used=ParserType.DOCLING)


async def run_pipeline(paper, parser_result, session):
    fetcher = MetadataFetcher(arxiv_client=FakeArxivClient([paper]), pdf_parser=FakePdfParser(parser_result))
    return await fetcher.fetch_and_process_papers(max_results=1, db_session=session)


@pytest.mark.anyio
async def test_declined_pdf_is_reported_as_skip_not_error(paper, recording_session):
    # A parser returning None means "outside the configured size or page limits".
    results = await run_pipeline(paper, None, recording_session)

    assert results["pdfs_skipped"] == 1
    assert results["errors"] == []
    assert results["papers_stored"] == 1

    stored = recording_session.stored["2401.00001"]
    assert stored.pdf_processed is False
    assert stored.parser_metadata["status"] == "skipped"


@pytest.mark.anyio
async def test_parse_failure_is_reported_as_error(paper, recording_session):
    results = await run_pipeline(paper, RuntimeError("libGL.so.1: cannot open shared object file"), recording_session)

    assert results["pdfs_skipped"] == 0
    assert len(results["errors"]) == 1
    assert results["papers_stored"] == 1


@pytest.mark.parametrize(
    ("parser_result", "expected_status", "expected_reason_fragment"),
    [
        pytest.param(None, "skipped", "size or page limits", id="declined-by-parser"),
        pytest.param(RuntimeError("libGL.so.1 missing"), "parse_error", "libGL.so.1", id="parser-raised"),
    ],
)
@pytest.mark.anyio
async def test_stored_row_records_why_the_pdf_has_no_content(
    paper, recording_session, parser_result, expected_status, expected_reason_fragment
):
    await run_pipeline(paper, parser_result, recording_session)

    stored = recording_session.stored["2401.00001"]
    assert stored.raw_text is None
    assert stored.parser_metadata["status"] == expected_status
    assert expected_reason_fragment in stored.parser_metadata["reason"]


@pytest.mark.parametrize(
    ("parser_result", "expected_parsed"),
    [
        pytest.param(parsed_content(), 1, id="parse-succeeded"),
        pytest.param(None, 0, id="parse-declined"),
        pytest.param(RuntimeError("boom"), 0, id="parse-raised"),
    ],
)
@pytest.mark.anyio
async def test_successful_download_is_counted_whatever_parsing_does(paper, recording_session, parser_result, expected_parsed):
    results = await run_pipeline(paper, parser_result, recording_session)

    assert results["pdfs_downloaded"] == 1
    assert results["pdfs_parsed"] == expected_parsed


@pytest.mark.anyio
async def test_failed_download_is_not_counted_as_downloaded(paper, recording_session):
    fetcher = MetadataFetcher(
        arxiv_client=FakeArxivClient([paper], download_result=None), pdf_parser=FakePdfParser(parsed_content())
    )

    results = await fetcher.fetch_and_process_papers(max_results=1, db_session=recording_session)

    assert results["pdfs_downloaded"] == 0
    assert len(results["errors"]) == 1
    assert recording_session.stored["2401.00001"].parser_metadata["status"] == "download_error"


def make_paper(arxiv_id: str, categories: list) -> ArxivPaper:
    return ArxivPaper(
        arxiv_id=arxiv_id,
        title=f"Paper {arxiv_id}",
        authors=["Ada Lovelace"],
        abstract="A test abstract.",
        categories=categories,
        published_date="2024-01-01T00:00:00Z",
        pdf_url=f"https://arxiv.org/pdf/{arxiv_id}",
    )


@pytest.mark.anyio
async def test_non_ai_papers_are_counted_but_never_downloaded_parsed_or_stored(recording_session):
    """The scope guard has to sit ahead of every side effect, not just ahead of storage."""
    papers = [
        make_paper("2401.00001", ["cs.LG"]),
        make_paper("2401.00002", ["hep-th", "math.CO"]),
        make_paper("2401.00003", ["quant-ph", "cs.CV"]),  # cross-listed into scope
        make_paper("2401.00004", ["cs.IR"]),
    ]
    arxiv_client = FakeArxivClient(papers)
    pdf_parser = FakePdfParser(parsed_content())
    fetcher = MetadataFetcher(arxiv_client=arxiv_client, pdf_parser=pdf_parser)

    results = await fetcher.fetch_and_process_papers(max_results=4, db_session=recording_session)

    assert results["papers_fetched"] == 4, "the raw arXiv count must keep its meaning"
    assert results["papers_filtered_non_ai"] == 2
    assert sorted(arxiv_client.downloaded) == ["2401.00001", "2401.00003"]
    assert len(pdf_parser.parsed) == 2
    assert sorted(recording_session.stored) == ["2401.00001", "2401.00003"]


@pytest.mark.anyio
async def test_an_all_non_ai_batch_stores_nothing(recording_session):
    arxiv_client = FakeArxivClient([make_paper("2401.00002", ["hep-th"])])
    pdf_parser = FakePdfParser(parsed_content())
    fetcher = MetadataFetcher(arxiv_client=arxiv_client, pdf_parser=pdf_parser)

    results = await fetcher.fetch_and_process_papers(max_results=1, db_session=recording_session)

    assert results["papers_fetched"] == 1
    assert results["papers_filtered_non_ai"] == 1
    assert results["papers_stored"] == 0
    assert arxiv_client.downloaded == []
    assert recording_session.stored == {}


@pytest.mark.anyio
async def test_filtered_count_is_zero_when_every_paper_is_in_scope(paper, recording_session):
    results = await run_pipeline(paper, parsed_content(), recording_session)

    assert results["papers_filtered_non_ai"] == 0


class StubParsedPaper:
    """Only ``pdf_content`` is read, so a duck type is enough to drive serialization."""

    def __init__(self, pdf_content):
        self.pdf_content = pdf_content


class ExplodingContent:
    """Parsed content whose access raises whatever the test wants."""

    def __init__(self, error):
        self._error = error

    def __getattr__(self, name):
        raise self._error


def serialize(pdf_content):
    fetcher = MetadataFetcher(arxiv_client=FakeArxivClient([]), pdf_parser=FakePdfParser(None))
    return fetcher._serialize_parsed_content(StubParsedPaper(pdf_content))


def test_missing_pdf_content_is_recorded_rather_than_raised():
    result = serialize(None)

    assert result["pdf_processed"] is False
    assert "pdf_content" in result["parser_metadata"]["error"]


@pytest.mark.parametrize("error", [AttributeError("no sections"), TypeError("not iterable"), ValueError("bad value")])
def test_malformed_parser_output_degrades_to_an_unprocessed_row(error):
    """Bad data from the parser must not take down the rest of the batch."""
    result = serialize(ExplodingContent(error))

    assert result["pdf_processed"] is False
    assert result["parser_metadata"]["error"] == str(error)


@pytest.mark.parametrize("error", [KeyError("bug"), RuntimeError("bug"), ZeroDivisionError("bug")])
def test_a_defect_in_serialization_surfaces_instead_of_being_filed_as_unprocessed(error):
    """The old bare `except Exception` recorded our own bugs as "PDF not processed"."""
    with pytest.raises(type(error)):
        serialize(ExplodingContent(error))
