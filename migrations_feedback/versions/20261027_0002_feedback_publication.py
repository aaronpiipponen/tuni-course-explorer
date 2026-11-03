"""Add the current publication outcome to the feedback application store."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261027_feedback_0002"
down_revision: str | Sequence[str] | None = "20261027_feedback_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the issue link and safe failure, and widen the current-state check."""
    op.add_column("feedback_submissions", sa.Column("issue_url", sa.Text(), nullable=True))
    op.add_column(
        "feedback_submissions",
        sa.Column("publication_failure", sa.Text(), nullable=True),
    )
    op.drop_constraint(
        op.f("ck_feedback_submissions_initial_publication_choice"),
        "feedback_submissions",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_feedback_submissions_current_publication_state"),
        "feedback_submissions",
        "(public_issue AND publication_state IN "
        "('pending', 'uncertain', 'published', 'partial', 'failed')) "
        "OR (NOT public_issue AND publication_state = 'private')",
    )


def downgrade() -> None:
    """Refuse the destructive rollback of retained publication outcomes."""
    raise RuntimeError(
        "the feedback store retains publication outcomes and links; restore a dump instead of "
        "dropping the columns"
    )
