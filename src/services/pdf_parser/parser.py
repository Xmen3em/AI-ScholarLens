import logging
from pathlib import Path
from typing import Optional

from src.exceptions import PDFParsingException, PDFValidationError
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

    async def parse_pdf(self, pdf_path: Path) -> Optional[PdfContent]:
        """
        Parse PDF using Docling parser only.

        Args:
            pdf_path: Path to PDF file

        Returns:
            PdfContent, or None if the parser declined the file (size or page limits).

        Raises:
            PDFValidationError: the file is missing or not a readable PDF.
            PDFParsingException: parsing was attempted and failed.
        """
        if not pdf_path.exists():
            logger.error(f"PDF file not found: {pdf_path}")
            raise PDFValidationError(f"PDF file not found: {pdf_path}")

        try:
            result = await self.docling_parser.parse_pdf(pdf_path)
            if result:
                logger.info(f"Parsed {pdf_path.name}")
                return result

            # None means the parser declined the file on purpose (size or page limits).
            # That is a skip, not a failure, so let it through instead of raising.
            logger.info(f"Skipped {pdf_path.name}: outside configured size or page limits")
            return None

        except (PDFValidationError, PDFParsingException):
            raise
        except Exception as e:
            logger.error(f"Docling parsing error for {pdf_path.name}: {e}")
            raise PDFParsingException(f"Docling parsing error for {pdf_path.name}: {e}")
