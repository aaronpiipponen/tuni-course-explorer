"""Create the derived course embedding neighbour table.

Revision ID: 20261028_0021
Revises: 20261027_0020

The table `course_embedding_neighbors` holds the nearest descriptive-chunk targets of every query
chunk. Its primary key on `(query_chunk_id, rank)` orders the stored rows of one query chunk, and
both chunk references cascade with their chunk rows. The table holds derived data, and the serving
artifact build replaces every row.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "20261028_0021"
down_revision: str | Sequence[str] | None = "20261027_0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the derived neighbour table."""
    op.create_table(
        "course_embedding_neighbors",
        sa.Column("query_chunk_id", UUID(as_uuid=True), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("target_chunk_id", UUID(as_uuid=True), nullable=False),
        sa.Column("score", sa.Double(), nullable=False),
        sa.CheckConstraint(
            "rank > 0",
            name="ck_course_embedding_neighbors_rank_positive",
        ),
        sa.CheckConstraint(
            "score >= -1 AND score <= 1",
            name="ck_course_embedding_neighbors_score_cosine_range",
        ),
        sa.ForeignKeyConstraint(
            ["query_chunk_id"],
            ["course_embedding_chunks.id"],
            name="fk_course_embedding_neighbors_query_chunk",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["target_chunk_id"],
            ["course_embedding_chunks.id"],
            name="fk_course_embedding_neighbors_target_chunk",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("query_chunk_id", "rank", name="pk_course_embedding_neighbors"),
    )


def downgrade() -> None:
    """Drop the derived neighbour table."""
    op.drop_table("course_embedding_neighbors")
