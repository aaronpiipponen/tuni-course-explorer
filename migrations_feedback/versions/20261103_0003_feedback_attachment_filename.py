"""Add the filename, name every stored row by its generated identity, and require it."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261103_feedback_0003"
down_revision: str | Sequence[str] | None = "20261027_feedback_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the filename, name every stored row by its generated identity, and require it."""
    op.add_column(
        "feedback_attachments",
        sa.Column("filename", sa.Text(), nullable=True),
    )
    op.execute(
        "UPDATE feedback_attachments SET filename = id::text || "
        "CASE mime_type WHEN 'image/png' THEN '.png' ELSE '.jpg' END"
    )
    op.alter_column("feedback_attachments", "filename", nullable=False)
    op.create_check_constraint(
        op.f("ck_feedback_attachments_filename_present"),
        "feedback_attachments",
        "length(filename) > 0",
    )


def downgrade() -> None:
    """Refuse the destructive rollback of retained attachment names."""
    raise RuntimeError(
        "the feedback store retains attachment filenames; restore a dump instead of dropping them"
    )
