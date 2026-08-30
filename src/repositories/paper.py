from datetime import datetime
from typing import Any, List, NamedTuple, Optional, Sequence, cast
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session
from src.models.paper import Paper
from src.schemas.arxiv.paper import PaperCreate


class CategoryRow(NamedTuple):
    """Just enough of a paper to judge its category scope."""

    id: UUID
    arxiv_id: str
    # Whatever the JSON column round-tripped. A corpus audit has to be able to
    # report a row whose categories are null or malformed, not choke on it.
    categories: Any


class PaperRepository:
    """Queries and writes over the papers table.

    No method here commits. The caller owns the transaction, so it can group several
    writes into one unit and roll the whole thing back; committing per write would take
    that choice away and leave rollback responsibility split between two layers.
    """

    def __init__(self, session: Session):
        self.session = session

    def create(self, paper: PaperCreate) -> Paper:
        """Insert a paper. Flushes so constraints fire here, but does not commit."""
        db_paper = Paper(**paper.model_dump())
        self.session.add(db_paper)
        self.session.flush()
        self.session.refresh(db_paper)
        return db_paper

    def get_by_arxiv_id(self, arxiv_id: str) -> Optional[Paper]:
        stmt = select(Paper).where(Paper.arxiv_id == arxiv_id)
        return self.session.scalar(stmt)

    def get_by_id(self, paper_id: UUID) -> Optional[Paper]:
        stmt = select(Paper).where(Paper.id == paper_id)
        return self.session.scalar(stmt)

    def get_all(self, limit: int = 100, offset: int = 0) -> List[Paper]:
        stmt = select(Paper).order_by(Paper.published_date.desc()).limit(limit).offset(offset)
        return list(self.session.scalars(stmt))

    def get_count(self) -> int:
        stmt = select(func.count(Paper.id))
        return self.session.scalar(stmt) or 0

    def get_processed_papers(self, limit: int = 100, offset: int = 0) -> List[Paper]:
        """Get papers that have been successfully processed with PDF content."""
        stmt = (
            select(Paper)
            .where(Paper.pdf_processed == True)
            .order_by(Paper.pdf_processing_date.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(self.session.scalars(stmt))

    def get_unprocessed_papers(self, limit: int = 100, offset: int = 0) -> List[Paper]:
        """Get papers that haven't been processed for PDF content yet."""
        stmt = select(Paper).where(Paper.pdf_processed == False).order_by(Paper.published_date.desc()).limit(limit).offset(offset)
        return list(self.session.scalars(stmt))

    def get_papers_with_raw_text(self, limit: int = 100, offset: int = 0) -> List[Paper]:
        """Get papers that have raw text content stored."""
        stmt = select(Paper).where(Paper.raw_text != None).order_by(Paper.pdf_processing_date.desc()).limit(limit).offset(offset)
        return list(self.session.scalars(stmt))

    def get_processing_stats(self) -> dict:
        """Get statistics about PDF processing status."""
        total_papers = self.get_count()

        # Count processed papers
        processed_stmt = select(func.count(Paper.id)).where(Paper.pdf_processed == True)
        processed_papers = self.session.scalar(processed_stmt) or 0

        # Count papers with text
        text_stmt = select(func.count(Paper.id)).where(Paper.raw_text != None)
        papers_with_text = self.session.scalar(text_stmt) or 0

        return {
            "total_papers": total_papers,
            "processed_papers": processed_papers,
            "papers_with_text": papers_with_text,
            "processing_rate": (processed_papers / total_papers * 100) if total_papers > 0 else 0,
            "text_extraction_rate": (papers_with_text / processed_papers * 100) if processed_papers > 0 else 0,
        }

    def update(self, paper: Paper) -> Paper:
        """Persist changes to a paper. Flushes but does not commit."""
        self.session.add(paper)
        self.session.flush()
        self.session.refresh(paper)
        return paper

    def upsert(self, paper_create: PaperCreate) -> Paper:
        # Check if paper already exists
        existing_paper = self.get_by_arxiv_id(paper_create.arxiv_id)
        if existing_paper:
            # Update existing paper with new content
            for key, value in paper_create.model_dump(exclude_unset=True).items():
                setattr(existing_paper, key, value)
            return self.update(existing_paper)
        else:
            # Create new paper
            return self.create(paper_create)

    def list_all_categories(self, *, for_update: bool = False) -> List[CategoryRow]:
        """Every paper's identity and categories, for scope auditing.

        Selects three columns rather than whole ``Paper`` rows: a full-corpus scan must
        not drag ``raw_text``, ``sections`` and ``references`` into memory with it.

        Args:
            for_update: Take row locks, so a caller can count and then delete atomically.
        """
        stmt = select(Paper.id, Paper.arxiv_id, Paper.categories).order_by(Paper.arxiv_id)
        if for_update:
            stmt = stmt.with_for_update()
        return [CategoryRow(*row) for row in self.session.execute(stmt)]

    def delete_by_ids(self, paper_ids: Sequence[UUID]) -> int:
        """Delete the given papers and return how many rows went.

        Like every write here, this does not commit: a count check and the delete it
        authorises have to stay one atomic unit, and committing would release the locks
        that hold that guarantee.
        """
        if not paper_ids:
            return 0  # `IN ()` is a syntax error, and there is nothing to do anyway.
        # synchronize_session is stated rather than defaulted: SQLAlchemy 1.4 (the Airflow
        # image) and 2.0 (the API image) disagree on the default, and the caller commits
        # and exits, so there is no identity map left to keep in step.
        result = cast(
            CursorResult,
            self.session.execute(delete(Paper).where(Paper.id.in_(paper_ids)), execution_options={"synchronize_session": False}),
        )
        return result.rowcount
