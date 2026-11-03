"""Key the neighbour table by its query and target chunk.

Revision ID: 20261103_0023
Revises: 20261028_0022

The neighbour table's key `(query_chunk_id, target_chunk_id)` drops the stored build rank, and the
rows are derived data that the serving artifact build replaces. The downgrade recomputes the rank
from the stored score order.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261103_0023"
down_revision: str | Sequence[str] | None = "20261028_0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Drop the stored rank and key the table by its query and target chunk."""
    op.drop_constraint(
        "pk_course_embedding_neighbors",
        "course_embedding_neighbors",
        type_="primary",
    )
    # Dropping the column also drops the check constraint that references it.
    op.drop_column("course_embedding_neighbors", "rank")
    op.create_primary_key(
        "pk_course_embedding_neighbors",
        "course_embedding_neighbors",
        ["query_chunk_id", "target_chunk_id"],
    )


def downgrade() -> None:
    """Restore the rank from the stored score order and key the table by it."""
    op.drop_constraint(
        "pk_course_embedding_neighbors",
        "course_embedding_neighbors",
        type_="primary",
    )
    op.add_column(
        "course_embedding_neighbors",
        sa.Column("rank", sa.Integer(), nullable=True),
    )
    op.execute(
        "UPDATE course_embedding_neighbors AS n SET rank = r.position "
        "FROM (SELECT query_chunk_id, target_chunk_id, "
        "row_number() OVER (PARTITION BY query_chunk_id ORDER BY score DESC, target_chunk_id) "
        "AS position FROM course_embedding_neighbors) AS r "
        "WHERE n.query_chunk_id = r.query_chunk_id "
        "AND n.target_chunk_id = r.target_chunk_id"
    )
    op.alter_column("course_embedding_neighbors", "rank", nullable=False)
    op.create_check_constraint(
        op.f("ck_course_embedding_neighbors_rank_positive"),
        "course_embedding_neighbors",
        "rank > 0",
    )
    op.create_primary_key(
        "pk_course_embedding_neighbors",
        "course_embedding_neighbors",
        ["query_chunk_id", "rank"],
    )
