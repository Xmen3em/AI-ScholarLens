import logging
from pathlib import Path
from typing import Optional

from src.exceptions import PDFParsingException, PDFSkippedError, PDFValidationError
from src.schemas.pdf_parser.models import PdfContent

logger = logging.getLogger(__name__)


class PDFParserService:
    """Main PDF parsing service using Docling only."""

    def __init__(self, max_pages: int = 20, max_file_size_mb: int = 20, do_ocr: bool = False, do_table_structure: bool = False):
        """
        Initialize PDF parser service with configurable limits.

        Args:
            max_pages: Maximum number of pages to process (default: 20)
            max_file_size_mb: Maximum file size in MB (default: 20MB)
            do_ocr: Enable OCR for scanned PDFs (default: False, very slow)
            do_table_structure: Extract table structures (default: False; the parser discards tables)
        """
        # Imported here rather than at module scope: docling and pypdfium2 exist only in
        # the Airflow image, and importing them eagerly would make this module — and every
        # module that imports it — unimportable in the API image and the test suite.
        from .docling import DoclingParser

        self.docling_parser = DoclingParser(
            max_pages=max_pages, max_file_size_mb=max_file_size_mb, do_ocr=do_ocr, do_table_structure=do_table_structure
        )

    async def parse_pdf(self, pdf_path: Path) -> PdfContent:
        """
        Parse PDF using Docling parser only.

        Args:
            pdf_path: Path to PDF file

        Returns:
            PdfContent extracted from the document.

        Raises:
            PDFSkippedError: the file exceeds a configured page or size limit. A skip is a
                policy decision, not a failure, and the message names the limit that tripped.
            PDFValidationError: the file is missing or not a readable PDF.
            PDFParsingException: parsing was attempted and failed.
        """
        if not pdf_path.exists():
            logger.error(f"PDF file not found: {pdf_path}")
            raise PDFValidationError(f"PDF file not found: {pdf_path}")

        try:
            result = await self.docling_parser.parse_pdf(pdf_path)
            logger.info(f"Parsed {pdf_path.name}")
            return result

        except (PDFSkippedError, PDFValidationError, PDFParsingException):
            raise
        except Exception as e:
            logger.error(f"Docling parsing error for {pdf_path.name}: {e}")
            raise PDFParsingException(f"Docling parsing error for {pdf_path.name}: {e}")
