"""Explicit, resumable PDF repair with one fresh Docling process per page batch.

Run inside the Airflow image: python -m src.commands.repair_pdf ARXIV_ID --apply
Without --apply, only the stored row is inspected. Scheduled ingestion is unchanged.
"""

import argparse
import asyncio
import hashlib
import logging
import subprocess
import sys
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

from src.models.paper import Paper
from src.policies.ai_scope import matches_ai_scope
from src.policies.chunking import chunk_sections
from src.schemas.arxiv.paper import ArxivPaper
from src.schemas.pdf_parser.models import PaperSection, ParserType, PdfContent


def merge_batches(batches: list[PdfContent]) -> PdfContent:
    sections: list[PaperSection] = []
    for batch in batches:
        for section in batch.sections:
            # A batch starting mid-section has no heading. Carry the previous heading
            # forward, including References, so bibliography continuations stay excluded.
            if sections and section.title == "Content":
                sections[-1].content += "\n" + section.content
            else:
                sections.append(section.model_copy(deep=True))
    return PdfContent(
        raw_text="\n".join(batch.raw_text for batch in batches),
        sections=sections,
        parser_used=ParserType.DOCLING,
        metadata={"source": "docling", "mode": "page-batches", "page_count": sum(b.metadata["page_count"] for b in batches)},
    )


def parse_in_batches(
    pdf_path: Path, cache_dir: Path, *, pages_per_batch: int = 1, max_pages: int = 60, max_file_size_mb: int = 50,
) -> PdfContent:
    import pypdfium2 as pdfium

    if pages_per_batch < 1 or max_pages < 1 or max_file_size_mb < 1:
        raise ValueError("Page and file limits must be positive")
    if pdf_path.stat().st_size > max_file_size_mb * 1024 * 1024:
        raise ValueError(f"PDF exceeds the explicit repair limit of {max_file_size_mb} MB")
    with pdf_path.open("rb") as source:
        source_hash = hashlib.file_digest(source, "sha256").hexdigest()
    # Version the checkpoints by source bytes, Docling version and batch policy.
    identity = f"repair-v1:{source_hash}:{version('docling')}:{pages_per_batch}"
    work_dir = cache_dir / hashlib.sha256(identity.encode()).hexdigest()
    work_dir.mkdir(parents=True, exist_ok=True)
    batches = []
    with pdfium.PdfDocument(str(pdf_path)) as document:
        page_count = len(document)
        if not 1 <= page_count <= max_pages:
            raise ValueError(f"PDF has {page_count} pages; explicit repair limit is {max_pages}")
        for start in range(0, page_count, pages_per_batch):
            end = min(start + pages_per_batch, page_count)
            batch_path = work_dir / f"pages-{start + 1:04d}-{end:04d}.pdf"
            checkpoint = batch_path.with_suffix(".json")
            if not checkpoint.exists():
                with pdfium.PdfDocument.new() as part:
                    part.import_pages(document, pages=list(range(start, end)))
                    part.save(str(batch_path))
                print(f"Parsing pages {start + 1}-{end} of {page_count}", flush=True)
                result = subprocess.run(
                    [sys.executable, "-u", "-m", "src.commands.repair_pdf", "--worker", str(batch_path), str(checkpoint)],
                    check=False,
                )
                if result.returncode != 0:
                    raise RuntimeError(
                        f"pages {start + 1}-{end} worker exited {result.returncode}; "
                        f"completed batches remain in {work_dir}. Stored paper was not updated."
                    )
            parsed = PdfContent.model_validate_json(checkpoint.read_text(encoding="utf-8"))
            if parsed.metadata.get("page_count") != end - start:
                raise RuntimeError(f"Checkpoint page count is wrong: {checkpoint}")
            batches.append(parsed)
            batch_path.unlink(missing_ok=True)
            print(f"Completed pages {start + 1}-{end} of {page_count}", flush=True)
    merged = merge_batches(batches)
    merged.metadata.update(source_sha256=source_hash, pages_per_batch=pages_per_batch)
    return merged


def parse_worker(pdf_path: Path, output: Path) -> None:
    """Heavy libraries are imported only in this short-lived child process."""
    import pypdfium2 as pdfium
    from docling.datamodel.base_models import ConversionStatus, InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    with pdfium.PdfDocument(str(pdf_path)) as document:
        expected_pages = len(document)
    options = PdfPipelineOptions(
        do_ocr=False, do_table_structure=False, generate_page_images=False, generate_picture_images=False,
    )
    converter = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)})
    result = converter.convert(str(pdf_path))
    if result.status != ConversionStatus.SUCCESS or len(result.document.pages) != expected_pages:
        raise RuntimeError(f"Docling did not complete every page: status={result.status}")

    sections: list[PaperSection] = []
    title = "Content"
    text: list[str] = []
    for element in result.document.texts:
        if element.label in {"title", "section_header"}:
            if text:
                sections.append(PaperSection(title=title, content="\n".join(text)))
            title, text = element.text.strip(), []
        elif element.text.strip():
            text.append(element.text.strip())
    if text:
        sections.append(PaperSection(title=title, content="\n".join(text)))
    content = PdfContent(
        raw_text=result.document.export_to_text(), sections=sections, parser_used=ParserType.DOCLING,
        metadata={"page_count": expected_pages},
    )
    temporary = output.with_suffix(".tmp")
    temporary.write_text(content.model_dump_json(), encoding="utf-8")
    temporary.replace(output)


def download(metadata: ArxivPaper) -> Path:
    from src.services.arxiv.factory import make_arxiv_client

    path = asyncio.run(make_arxiv_client().download_pdf(metadata))
    if path is None:
        raise RuntimeError("PDF download returned no file")
    return path


def repair_one(database, arxiv_id: str, cache_dir: Path, *, apply: bool, **limits) -> None:
    with database.get_session() as session:
        paper = session.query(Paper).filter_by(arxiv_id=arxiv_id).one_or_none()
        if paper is None:
            raise ValueError(f"No stored paper with exact ID {arxiv_id}")
        if not matches_ai_scope(paper.categories):
            raise ValueError(f"Paper is outside the AI scope: {arxiv_id}")
        if chunk_sections(paper.sections):
            print(f"Already has usable chunks: {arxiv_id}", flush=True)
            return
        print(f"Chunkless: {arxiv_id}; parser metadata: {getattr(paper, 'parser_metadata', None)}", flush=True)
        if not apply:
            return
        original_updated_at = paper.updated_at
        metadata = ArxivPaper(
            arxiv_id=paper.arxiv_id, title=paper.title, authors=paper.authors, abstract=paper.abstract,
            categories=paper.categories, published_date=paper.published_date.isoformat(), pdf_url=paper.pdf_url,
        )

    content = parse_in_batches(download(metadata), cache_dir, **limits)
    sections = [{"title": section.title, "content": section.content} for section in content.sections]
    chunks = chunk_sections(sections)
    if not content.raw_text.strip() or not chunks:
        raise RuntimeError("Complete parse produced no usable evidence; stored paper was not updated")
    with database.get_session() as session:
        paper = session.query(Paper).filter_by(arxiv_id=arxiv_id).with_for_update().one_or_none()
        if paper is None or paper.updated_at != original_updated_at:
            raise RuntimeError("Paper changed during parsing; stored content was not overwritten")
        paper.raw_text, paper.sections, paper.references = content.raw_text, sections, content.references
        paper.parser_used, paper.parser_metadata = content.parser_used.value, content.metadata
        paper.pdf_processed = True
        paper.pdf_processing_date = datetime.now(timezone.utc)
        session.commit()
    print(f"REPAIRED {arxiv_id}: {len(chunks)} chunks", flush=True)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("arxiv_ids", nargs="*", help="Exact stored IDs, including version")
    parser.add_argument("--apply", action="store_true", help="Parse and update; otherwise inspect only")
    parser.add_argument("--pages-per-batch", type=int, default=1)
    parser.add_argument("--max-pages", type=int, default=60)
    parser.add_argument("--max-file-size-mb", type=int, default=50)
    parser.add_argument("--worker", nargs=2, metavar=("PDF", "JSON"), help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.worker:
        parse_worker(*map(Path, args.worker))
        return 0
    if not args.arxiv_ids:
        parser.error("Provide at least one exact arXiv ID")
    if min(args.pages_per_batch, args.max_pages, args.max_file_size_mb) < 1:
        parser.error("Page and file limits must be positive")

    from src.config import get_settings
    from src.db.factory import make_database

    database = make_database()
    failed = False
    try:
        for arxiv_id in args.arxiv_ids:
            try:
                repair_one(
                    database, arxiv_id, Path(get_settings().arxiv.pdf_cache_dir) / ".repair",
                    apply=args.apply, pages_per_batch=args.pages_per_batch, max_pages=args.max_pages,
                    max_file_size_mb=args.max_file_size_mb,
                )
            except Exception:
                logging.exception("FAILED %s", arxiv_id)
                failed = True
    finally:
        database.teardown()
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
