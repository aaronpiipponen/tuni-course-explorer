"""course_embedding_hnsw_index.

Revision ID: 20260917_0008
Revises: 20260915_0007
Create Date: 2026-09-17
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260917_0008"
down_revision: str | Sequence[str] | None = "20260915_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the cosine HNSW index over course embedding vectors.

    The exact-cosine query contract carries no `LIMIT` and scans exactly, so this index serves
    reads that cap nearest neighbors. A fresh or test database builds it empty.
    """
    op.create_index(
        "ix_course_embedding_chunks_embedding_hnsw",
        "course_embedding_chunks",
        ["embedding"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
        postgresql_with={"m": 16, "ef_construction": 64},
    )


def downgrade() -> None:
    """Drop the course embedding HNSW index."""
    op.drop_index(
        "ix_course_embedding_chunks_embedding_hnsw",
        table_name="course_embedding_chunks",
    )
