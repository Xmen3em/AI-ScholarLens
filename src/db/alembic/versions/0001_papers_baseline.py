"""Baseline: the papers table as it stood before migrations existed.

Databases created by the previous ``Base.metadata.create_all`` already match this
revision, so src/db/migrations.py stamps them here rather than re-running it.

Revision ID: 0001_papers_baseline
Revises:
Create Date: 2026-08-30
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# postgresql.UUID, not sa.UUID: the Airflow image runs SQLAlchemy 1.4, where
# sa.UUID does not exist. This mirrors src/models/paper.py.
from sqlalchemy.dialects import postgresql

revision: str = "0001_papers_baseline"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "papers",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("arxiv_id", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("authors", sa.JSON(), nullable=False),
        sa.Column("abstract", sa.Text(), nullable=False),
        sa.Column("categories", sa.JSON(), nullable=False),
        sa.Column("published_date", sa.DateTime(), nullable=False),
        sa.Column("pdf_url", sa.String(), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=True),
        sa.Column("sections", sa.JSON(), nullable=True),
        sa.Column("references", sa.JSON(), nullable=True),
        sa.Column("parser_used", sa.String(), nullable=True),
        sa.Column("parser_metadata", sa.JSON(), nullable=True),
        sa.Column("pdf_processed", sa.Boolean(), nullable=False),
        sa.Column("pdf_processing_date", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_papers_arxiv_id"), "papers", ["arxiv_id"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_papers_arxiv_id"), table_name="papers")
    op.drop_table("papers")
