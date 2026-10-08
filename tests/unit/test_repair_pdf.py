"""A killed page worker must never turn a partial parse into a repaired paper."""

import json
import sys
from contextlib import nullcontext
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from src.commands import repair_pdf
from src.schemas.pdf_parser.models import PaperSection, ParserType, PdfContent


def content(text="Evidence " * 25, title="Methods", pages=1):
    return PdfContent(
        raw_text=text,
        sections=[PaperSection(title=title, content=text)] if text else [],
        parser_used=ParserType.DOCLING,
        metadata={"page_count": pages},
    )


@pytest.fixture
def pdf_workers(monkeypatch, tmp_path):
    """Fake only PDFium and the subprocess boundary; exercise real checkpoints."""
    class Document:
        def __init__(self, *_):
            self.pages = [0, 1, 2]

        def __len__(self):
            return len(self.pages)

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        @classmethod
        def new(cls):
            return cls()

        def import_pages(self, source, pages):
            self.pages = pages

        def save(self, path):
            Path(path).write_text(json.dumps(self.pages))

    monkeypatch.setitem(sys.modules, "pypdfium2", SimpleNamespace(PdfDocument=Document))
    monkeypatch.setattr(repair_pdf, "version", lambda _: "test")
    source = tmp_path / "source.pdf"
    source.write_bytes(b"%PDF-test")
    calls = []

    def run(command, **kwargs):
        assert kwargs == {"check": False}
        input_path, output_path = map(Path, command[-2:])
        pages = json.loads(input_path.read_text())
        calls.append(pages)
        output_path.write_text(content(str(pages) + " evidence " * 25, pages=len(pages)).model_dump_json())
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(repair_pdf.subprocess, "run", run)
    return source, tmp_path / "checkpoints", calls, run


def test_every_page_runs_in_a_separate_worker_and_completed_batches_are_reused(pdf_workers):
    source, cache, calls, _ = pdf_workers
    result = repair_pdf.parse_in_batches(source, cache, pages_per_batch=1)
    assert calls == [[0], [1], [2]]
    assert result.metadata["page_count"] == 3
    assert result.raw_text.index("[0]") < result.raw_text.index("[1]") < result.raw_text.index("[2]")
    repair_pdf.parse_in_batches(source, cache, pages_per_batch=1)
    assert calls == [[0], [1], [2]]


def test_worker_kill_preserves_completed_checkpoint_and_retry_resumes(pdf_workers, monkeypatch):
    source, cache, calls, run = pdf_workers

    def kill_second(command, **kwargs):
        if len(calls) == 1:
            return SimpleNamespace(returncode=-9)
        return run(command, **kwargs)

    monkeypatch.setattr(repair_pdf.subprocess, "run", kill_second)
    with pytest.raises(RuntimeError, match="pages 2-2.*-9"):
        repair_pdf.parse_in_batches(source, cache)
    assert len(list(cache.rglob("*.json"))) == 1
    monkeypatch.setattr(repair_pdf.subprocess, "run", run)
    repair_pdf.parse_in_batches(source, cache)
    assert calls == [[0], [1], [2]]


def test_changed_pdf_does_not_reuse_old_checkpoints(pdf_workers):
    source, cache, calls, _ = pdf_workers
    repair_pdf.parse_in_batches(source, cache)
    source.write_bytes(b"%PDF-changed")
    repair_pdf.parse_in_batches(source, cache)
    assert calls == [[0], [1], [2], [0], [1], [2]]


def test_wrong_page_count_is_rejected(pdf_workers, monkeypatch):
    source, cache, _, _ = pdf_workers

    def incomplete(command, **kwargs):
        Path(command[-1]).write_text(content(pages=0).model_dump_json())
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(repair_pdf.subprocess, "run", incomplete)
    with pytest.raises(RuntimeError, match="page count"):
        repair_pdf.parse_in_batches(source, cache)


def test_continued_reference_section_stays_excluded_from_chunks():
    result = repair_pdf.merge_batches([content(title="References"), content(title="Content")])
    assert [section.title for section in result.sections] == ["References"]
    assert repair_pdf.chunk_sections([s.model_dump() for s in result.sections]) == []


@pytest.fixture
def paper_database():
    paper = SimpleNamespace(
        arxiv_id="2608.27456v1", title="UrbanGround", authors=["Author"], abstract="Abstract",
        categories=["cs.AI"], published_date=datetime(2026, 8, 1), pdf_url="https://arxiv.org/pdf/2608.27456v1",
        sections=None, raw_text=None, updated_at=datetime(2026, 9, 1), pdf_processed=False,
    )
    session = Mock()
    query = session.query.return_value.filter_by.return_value
    query.one_or_none.return_value = paper
    query.with_for_update.return_value.one_or_none.return_value = paper
    database = Mock()
    database.get_session.side_effect = lambda: nullcontext(session)
    return database, session, paper


def test_failed_parse_never_updates_paper_or_commits(paper_database, monkeypatch, tmp_path):
    database, session, paper = paper_database
    monkeypatch.setattr(repair_pdf, "download", lambda _: tmp_path / "cached.pdf")
    monkeypatch.setattr(repair_pdf, "parse_in_batches", Mock(side_effect=RuntimeError("worker killed")))
    with pytest.raises(RuntimeError, match="worker killed"):
        repair_pdf.repair_one(database, paper.arxiv_id, tmp_path, apply=True)
    session.commit.assert_not_called()
    assert paper.sections is None and paper.raw_text is None and paper.pdf_processed is False


def test_successful_complete_parse_commits_once(paper_database, monkeypatch, tmp_path):
    database, session, paper = paper_database
    monkeypatch.setattr(repair_pdf, "download", lambda _: tmp_path / "cached.pdf")
    monkeypatch.setattr(repair_pdf, "parse_in_batches", lambda *args, **kwargs: content())
    repair_pdf.repair_one(database, paper.arxiv_id, tmp_path, apply=True)
    session.commit.assert_called_once()
    assert paper.pdf_processed is True and repair_pdf.chunk_sections(paper.sections)


def test_audit_does_not_download_parse_or_write(paper_database, monkeypatch, tmp_path):
    database, session, paper = paper_database
    downloader = Mock(side_effect=AssertionError("audit must not download"))
    monkeypatch.setattr(repair_pdf, "download", downloader)
    repair_pdf.repair_one(database, paper.arxiv_id, tmp_path, apply=False)
    downloader.assert_not_called()
    session.commit.assert_not_called()


def test_empty_evidence_does_not_mark_the_paper_processed(paper_database, monkeypatch, tmp_path):
    database, session, paper = paper_database
    monkeypatch.setattr(repair_pdf, "download", lambda _: tmp_path / "cached.pdf")
    monkeypatch.setattr(repair_pdf, "parse_in_batches", lambda *args, **kwargs: content(text=""))
    with pytest.raises(RuntimeError, match="no usable evidence"):
        repair_pdf.repair_one(database, paper.arxiv_id, tmp_path, apply=True)
    session.commit.assert_not_called()
    assert paper.pdf_processed is False


def test_concurrent_change_prevents_overwriting_paper(paper_database, monkeypatch, tmp_path):
    database, session, paper = paper_database
    monkeypatch.setattr(repair_pdf, "download", lambda _: tmp_path / "cached.pdf")

    def parse(*args, **kwargs):
        paper.updated_at = datetime(2026, 10, 1)
        return content()

    monkeypatch.setattr(repair_pdf, "parse_in_batches", parse)
    with pytest.raises(RuntimeError, match="changed during parsing"):
        repair_pdf.repair_one(database, paper.arxiv_id, tmp_path, apply=True)
    session.commit.assert_not_called()
    assert paper.pdf_processed is False


@pytest.mark.parametrize("status, pages", [("partial", 3), ("success", 2)])
def test_worker_refuses_partial_conversion(pdf_workers, monkeypatch, tmp_path, status, pages):
    source, _, _, _ = pdf_workers
    result = SimpleNamespace(status=status, document=SimpleNamespace(pages=dict.fromkeys(range(pages))))
    converter = Mock()
    converter.convert.return_value = result
    monkeypatch.setitem(sys.modules, "docling.datamodel.base_models", SimpleNamespace(
        ConversionStatus=SimpleNamespace(SUCCESS="success"), InputFormat=SimpleNamespace(PDF="pdf"),
    ))
    monkeypatch.setitem(sys.modules, "docling.datamodel.pipeline_options", SimpleNamespace(PdfPipelineOptions=Mock()))
    monkeypatch.setitem(sys.modules, "docling.document_converter", SimpleNamespace(
        DocumentConverter=Mock(return_value=converter), PdfFormatOption=Mock(),
    ))
    output = tmp_path / "partial.json"
    with pytest.raises(RuntimeError, match="did not complete every page"):
        repair_pdf.parse_worker(source, output)
    assert not output.exists()
