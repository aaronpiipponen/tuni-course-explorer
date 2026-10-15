"""Embedding and source records.

Revision ID: 20261008_0015
Revises: 20261008_0014
Create Date: 2026-10-08

Drops the embedding-chunk attempt telemetry and the source snapshot capture time: the per-attempt
count/time/error/creation columns serve only their own validation, retry and reconciliation consume
the lifecycle status, and source snapshot provenance is its immutable position/hash pair. Upgrade
performs explicit DDL drops plus one re-created lifecycle check.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20261008_0015"
down_revision: str | Sequence[str] | None = "20261008_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Drop the embedding/source telemetry and re-create the lifecycle check."""
    op.drop_constraint(
        op.f("ck_course_embedding_chunks_attempt_count_nonnegative"),
        "course_embedding_chunks",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_course_embedding_chunks_lifecycle_consistent"),
        "course_embedding_chunks",
        type_="check",
    )
    for column in ("attempt_count", "last_attempted_at", "last_error", "created_at"):
        op.drop_column("course_embedding_chunks", column)
    op.create_check_constraint(
        op.f("ck_course_embedding_chunks_lifecycle_consistent"),
        "course_embedding_chunks",
        "(status = 'completed' AND embedding IS NOT NULL) "
        "OR (status IN ('pending', 'failed') AND embedding IS NULL)",
    )
    op.drop_column("source_snapshots", "captured_at")


def downgrade() -> None:
    """Refuse the irreversible metadata deletion."""
    raise RuntimeError(
        "20261008_0015 is an irreversible deletion of unused embedding/source telemetry; "
        "restore from the pre-migration backup instead of downgrading"
    )
