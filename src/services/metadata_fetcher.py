import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, NamedTuple, Optional

from dateutil import parser as date_parser
from sqlalchemy.orm import Session
from src.exceptions import PipelineException
from src.repositories.paper import PaperRepository
from src.schemas.arxiv.paper import ArxivPaper, PaperCreate
from src.schemas.pdf_parser.models import ArxivMetadata, ParsedPaper, PdfContent
from src.services.arxiv.client import ArxivClient
from src.services.pdf_parser.parser import PDFParserService

logger = logging.getLogger(__name__)


class PdfOutcome(NamedTuple):
    """Why a paper ended up without parsed content.

    status is "skipped" when the parser declined the file on purpose (size or page
    limits) and "download_error"/"parse_error" when something actually went wrong.
    Carried through to the stored row so the database, not the task log, answers
    "why is this paper unparsed?".
    """

    status: str
    reason: str


class MetadataFetcher:
    """
    Service for fetching arXiv papers with PDF processing and database storage.

    This service orchestrates the complete pipeline:
    1. Fetch paper metadata from arXiv API
    2. Download PDFs with caching
    3. Parse PDFs with Docling
    4. Store complete paper data in PostgreSQL
    """

    def __init__(
        self,
        arxiv_client: ArxivClient,
        pdf_parser: PDFParserService,
        pdf_cache_dir: Optional[Path] = None,
        max_concurrent_downloads: int = 5,
        max_concurrent_parsing: int = 3,
    ):
        """
        Initialize metadata fetcher.

        Args:
            arxiv_client: ArxivClient instance for API calls
            pdf_parser: PDFParserService for parsing PDFs
            pdf_cache_dir: Directory for PDF caching (uses client default if None)
            max_concurrent_downloads: Maximum concurrent PDF downloads
            max_concurrent_parsing: Maximum concurrent PDF parsing operations
        """
        self.arxiv_client = arxiv_client
        self.pdf_parser = pdf_parser
        self.pdf_cache_dir = pdf_cache_dir or self.arxiv_client.pdf_cache_dir
        self.max_concurrent_downloads = max_concurrent_downloads
        self.max_concurrent_parsing = max_concurrent_parsing

    async def fetch_and_process_papers(
        self,
        max_results: Optional[int] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        process_pdfs: bool = True,
        store_to_db: bool = True,
        db_session: Optional[Session] = None,
    ) -> Dict[str, Any]:
        """
        Fetch papers from arXiv, process PDFs, and store to database.

        Args:
            max_results: Maximum papers to fetch
            from_date: Filter papers from this date (YYYYMMDD)
            to_date: Filter papers to this date (YYYYMMDD)
            process_pdfs: Whether to download and parse PDFs
            store_to_db: Whether to store results in database
            db_session: Database session (required if store_to_db=True)

        Returns:
            Dictionary with processing results and statistics
        """

        results = {
            "papers_fetched": 0,
            "pdfs_downloaded": 0,
            "pdfs_parsed": 0,
            "pdfs_skipped": 0,
            "papers_stored": 0,
            "errors": [],
            "processing_time": 0,
        }

        start_time = datetime.now()

        try:
            # Step 1: Fetch paper metadata from arXiv
            papers = await self.arxiv_client.fetch_papers(
                max_results=max_results, from_date=from_date, to_date=to_date, sort_by="submittedDate", sort_order="descending"
            )

            results["papers_fetched"] = len(papers)

            if not papers:
                logger.warning("No papers found")
                return results

            # Step 2: Process PDFs if requested
            pdf_results = {}
            if process_pdfs:
                pdf_results = await self._process_pdfs_batch(papers)
                results["pdfs_downloaded"] = pdf_results["downloaded"]
                results["pdfs_parsed"] = pdf_results["parsed"]
                results["pdfs_skipped"] = len(pdf_results["skipped"])
                results["errors"].extend(pdf_results["errors"])

            # Step 3: Store to database if requested
            if store_to_db and db_session:
                logger.info("Step 3: Storing papers to database...")
                stored_count = self._store_papers_to_db(
                    papers, pdf_results.get("parsed_papers", {}), db_session, pdf_results.get("failure_reasons", {})
                )
                results["papers_stored"] = stored_count
            elif store_to_db:
                logger.warning("Database storage requested but no session provided")
                results["errors"].append("Database session not provided for storage")

            # Calculate total processing time
            processing_time = (datetime.now() - start_time).total_seconds()
            results["processing_time"] = processing_time

            # Simple logging summary
            logger.info(
                f"Pipeline completed in {processing_time:.1f}s: {results['papers_fetched']} papers, "
                f"{results['pdfs_downloaded']} PDFs downloaded, {results['pdfs_parsed']} parsed, "
                f"{results['pdfs_skipped']} skipped, {len(results['errors'])} errors"
            )

            if results["errors"]:
                logger.warning("Errors summary:")
                for i, error in enumerate(results["errors"][:5], 1):  # Show first 5 errors
                    logger.warning(f"  {i}. {error}")
                if len(results["errors"]) > 5:
                    logger.warning(f"  ... and {len(results['errors']) - 5} more errors")

            return results

        except Exception as e:
            logger.error(f"Pipeline error: {e}")
            results["errors"].append(f"Pipeline error: {str(e)}")
            raise PipelineException(f"Pipeline execution failed: {e}") from e

    async def _process_pdfs_batch(self, papers: List[ArxivPaper]) -> Dict[str, Any]:
        """
        Process PDFs for a batch of papers with async concurrency.

        Uses overlapping download+parse pipeline:
        - Downloads happen concurrently (up to max_concurrent_downloads)
        - As each download completes, parsing starts immediately
        - Multiple PDFs can be parsing while others are still downloading

        This is optimal for production workloads like 100 papers/day.

        Args:
            papers: List of ArxivPaper objects

        Returns:
            Dictionary with processing results and statistics
        """
        results = {
            "downloaded": 0,
            "parsed": 0,
            "parsed_papers": {},
            "skipped": [],
            "failure_reasons": {},
            "errors": [],
            "download_failures": [],
            "parse_failures": [],
        }

        logger.info(f"Starting async pipeline for {len(papers)} PDFs...")
        logger.info(f"Concurrent downloads: {self.max_concurrent_downloads}")
        logger.info(f"Concurrent parsing: {self.max_concurrent_parsing}")

        # Create semaphores for controlled concurrency
        download_semaphore = asyncio.Semaphore(self.max_concurrent_downloads)
        parse_semaphore = asyncio.Semaphore(self.max_concurrent_parsing)

        # Start all download+parse pipelines concurrently
        pipeline_tasks = [self._download_and_parse_pipeline(paper, download_semaphore, parse_semaphore) for paper in papers]

        # Wait for all pipelines to complete
        pipeline_results = await asyncio.gather(*pipeline_tasks, return_exceptions=True)

        # Process results with detailed error tracking
        for paper, result in zip(papers, pipeline_results):
            if isinstance(result, Exception):
                # Only genuinely unexpected failures reach here; the pipeline reports
                # download and parse outcomes in its return value instead of raising.
                error_msg = f"Pipeline error for {paper.arxiv_id}: {result}"
                logger.error(error_msg)
                results["errors"].append(error_msg)
                results["failure_reasons"][paper.arxiv_id] = PdfOutcome(status="parse_error", reason=str(result))
                continue

            download_success, parsed_paper, outcome = result

            if download_success:
                # Counted on download success regardless of what parsing did next.
                results["downloaded"] += 1
            else:
                results["download_failures"].append(paper.arxiv_id)

            if parsed_paper:
                results["parsed"] += 1
                results["parsed_papers"][paper.arxiv_id] = parsed_paper
                continue

            results["failure_reasons"][paper.arxiv_id] = outcome
            if outcome.status == "skipped":
                # A deliberate skip (size/page limits) is not an incident.
                results["skipped"].append(paper.arxiv_id)
                logger.info(f"Skipped PDF for {paper.arxiv_id}: {outcome.reason}")
            else:
                if outcome.status == "parse_error":
                    results["parse_failures"].append(paper.arxiv_id)
                error_msg = f"{paper.arxiv_id}: {outcome.reason}"
                logger.error(f"PDF processing failed for {error_msg}")
                results["errors"].append(error_msg)

        # Simple processing summary. Each failure is already in results["errors"] with its
        # reason attached, so it is not appended a second time as a bare arxiv_id.
        logger.info(
            f"PDF processing: {results['downloaded']}/{len(papers)} downloaded, "
            f"{results['parsed']} parsed, {len(results['skipped'])} skipped"
        )

        if results["download_failures"]:
            logger.warning(f"Download failures: {len(results['download_failures'])}")

        if results["parse_failures"]:
            logger.warning(f"Parse failures: {len(results['parse_failures'])}")

        return results

    async def _download_and_parse_pipeline(
        self, paper: ArxivPaper, download_semaphore: asyncio.Semaphore, parse_semaphore: asyncio.Semaphore
    ) -> tuple:
        """
        Complete download+parse pipeline for a single paper with true parallelism.
        Downloads PDF, then immediately starts parsing while other downloads continue.

        A parse failure does not discard the download that already succeeded, and it does
        not raise: both facts are returned so the caller can count and report them.

        Returns:
            Tuple of (download_success: bool, parsed_paper: Optional[ParsedPaper], outcome: Optional[PdfOutcome])
            outcome is None when parsing succeeded.
        """
        # Step 1: Download PDF with download concurrency control
        try:
            async with download_semaphore:
                logger.debug(f"Starting download: {paper.arxiv_id}")
                pdf_path = await self.arxiv_client.download_pdf(paper, False)
        except Exception as e:
            logger.error(f"Download error for {paper.arxiv_id}: {e}")
            return (False, None, PdfOutcome(status="download_error", reason=str(e)))

        if not pdf_path:
            logger.error(f"Download failed: {paper.arxiv_id}")
            return (False, None, PdfOutcome(status="download_error", reason="PDF download returned no file"))

        logger.debug(f"Download complete: {paper.arxiv_id}")

        # Step 2: Parse PDF with parse concurrency control (happens AFTER download completes)
        # This allows other downloads to continue while this PDF is being parsed
        try:
            async with parse_semaphore:
                logger.debug(f"Starting parse: {paper.arxiv_id}")
                pdf_content = await self.pdf_parser.parse_pdf(pdf_path)
        except Exception as e:
            logger.error(f"Parse error for {paper.arxiv_id}: {e}")
            return (True, None, PdfOutcome(status="parse_error", reason=str(e)))

        if not pdf_content:
            # The parser declined the file on purpose (size or page limits).
            return (True, None, PdfOutcome(status="skipped", reason="outside configured size or page limits"))

        arxiv_metadata = ArxivMetadata(
            title=paper.title,
            authors=paper.authors,
            abstract=paper.abstract,
            arxiv_id=paper.arxiv_id,
            categories=paper.categories,
            published_date=paper.published_date,
            pdf_url=paper.pdf_url,
        )
        parsed_paper = ParsedPaper(arxiv_metadata=arxiv_metadata, pdf_content=pdf_content)
        logger.debug(f"Parse complete: {paper.arxiv_id} - {len(pdf_content.raw_text)} chars extracted")

        return (True, parsed_paper, None)

    def _serialize_parsed_content(self, parsed_paper: ParsedPaper) -> Dict[str, Any]:
        """
        Serialize ParsedPaper content for database storage.

        Args:
            parsed_paper: ParsedPaper object with PDF content

        Returns:
            Dictionary with serialized content for database storage
        """
        try:
            pdf_content = parsed_paper.pdf_content

            # Serialize sections
            sections = [{"title": section.title, "content": section.content} for section in pdf_content.sections]

            # Serialize references
            references = list(pdf_content.references)  #

            return {
                "raw_text": pdf_content.raw_text,
                "sections": sections,
                "references": references,
                "parser_used": pdf_content.parser_used.value if pdf_content.parser_used else None,
                "parser_metadata": pdf_content.metadata or {},
                "pdf_processed": True,
                "pdf_processing_date": datetime.now(),
            }
        except Exception as e:
            logger.error(f"Failed to serialize parsed content: {e}")
            return {"pdf_processed": False, "parser_metadata": {"error": str(e)}}

    def _store_papers_to_db(
        self,
        papers: List[ArxivPaper],
        parsed_papers: Dict[str, ParsedPaper],
        db_session: Session,
        failure_reasons: Optional[Dict[str, PdfOutcome]] = None,
    ) -> int:
        """
        Store papers and parsed content to database with comprehensive content storage.

        Args:
            papers: List of ArxivPaper metadata
            parsed_papers: Dictionary of parsed PDF content by arxiv_id
            db_session: Database session
            failure_reasons: Why a paper has no parsed content, by arxiv_id

        Returns:
            Number of papers stored successfully
        """
        paper_repo = PaperRepository(db_session)
        failure_reasons = failure_reasons or {}
        stored_count = 0

        for paper in papers:
            try:
                # Get parsed content if available
                parsed_paper = parsed_papers.get(paper.arxiv_id)

                # Base paper data
                published_date = (
                    date_parser.parse(paper.published_date) if isinstance(paper.published_date, str) else paper.published_date
                )
                paper_data = {
                    "arxiv_id": paper.arxiv_id,
                    "title": paper.title,
                    "authors": paper.authors,
                    "abstract": paper.abstract,
                    "categories": paper.categories,
                    "published_date": published_date,
                    "pdf_url": paper.pdf_url,
                }

                # Add parsed content if available
                if parsed_paper:
                    parsed_content = self._serialize_parsed_content(parsed_paper)
                    paper_data.update(parsed_content)
                    logger.debug(
                        f"Storing paper {paper.arxiv_id} with parsed content ({len(parsed_content.get('raw_text', '')) if parsed_content.get('raw_text') else 0} chars)"
                    )
                else:
                    # No parsed content - store metadata plus why, so the row is diagnosable.
                    outcome = failure_reasons.get(paper.arxiv_id)
                    paper_data.update(
                        {
                            "pdf_processed": False,
                            "parser_metadata": {
                                "parser": "docling",
                                "status": outcome.status if outcome else "not_processed",
                                "reason": outcome.reason if outcome else "PDF processing was not run for this paper",
                            },
                        }
                    )
                    logger.debug(f"Storing paper {paper.arxiv_id} with metadata only")

                paper_create = PaperCreate(**paper_data)
                stored_paper = paper_repo.upsert(paper_create)

                if stored_paper:
                    stored_count += 1
                    content_info = "with parsed content" if parsed_paper else "metadata only"
                    logger.debug(f"Stored paper {paper.arxiv_id} to database ({content_info})")

            except Exception as e:
                logger.error(f"Failed to store paper {paper.arxiv_id}: {e}")

        # Commit all changes
        try:
            db_session.commit()
            logger.info(f"Committed {stored_count} papers to database with full content storage")
        except Exception as e:
            logger.error(f"Failed to commit papers to database: {e}")
            db_session.rollback()
            stored_count = 0

        return stored_count


def make_metadata_fetcher(
    arxiv_client: ArxivClient,
    pdf_parser: PDFParserService,
    pdf_cache_dir: Optional[Path] = None,
) -> MetadataFetcher:
    """
    Factory function to create MetadataFetcher instance optimized for production.

    Configured for typical production workloads (100 papers/day):
    - 5 concurrent downloads (I/O bound, can handle more)
    - 3 concurrent parsing operations (CPU intensive, use fewer)
    - Async pipeline for optimal resource utilization

    Args:
        arxiv_client: Configured ArxivClient
        pdf_parser: Configured PDFParserService (singleton with model caching)
        pdf_cache_dir: Optional PDF cache directory

    Returns:
        MetadataFetcher instance optimized for production
    """
    return MetadataFetcher(
        arxiv_client=arxiv_client,
        pdf_parser=pdf_parser,
        pdf_cache_dir=pdf_cache_dir,
        max_concurrent_downloads=5,
        max_concurrent_parsing=1,
    )
