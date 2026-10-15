"""allow unbounded official course credit maxima.

Revision ID: 20260911_0002
Revises: 20260910_0001
Create Date: 2026-09-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260911_0002"
down_revision: str | Sequence[str] | None = "20260910_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Permit source-unbounded course credit maxima as NULL."""
    op.alter_column(
        "course_versions",
        "credits_max",
        existing_type=sa.Numeric(precision=6, scale=2),
        nullable=True,
    )


def downgrade() -> None:
    """Set credit maxima non-null, raising when an unbounded NULL value exists."""
    connection = op.get_bind()
    unbounded_count = connection.scalar(
        sa.text("SELECT count(*) FROM course_versions WHERE credits_max IS NULL")
    )
    if unbounded_count:
        raise RuntimeError(
            "cannot restore non-null course credit maximum while unbounded values exist"
        )
    op.alter_column(
        "course_versions",
        "credits_max",
        existing_type=sa.Numeric(precision=6, scale=2),
        nullable=False,
    )
