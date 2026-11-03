"""Create the feedback application store."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261027_feedback_0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the submission and attachment tables with their publication and attachment checks."""
    op.create_table(
        "feedback_submissions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "answers",
            postgresql.JSONB(astext_type=sa.Text(), none_as_null=True),
            nullable=False,
        ),
        sa.Column("public_issue", sa.Boolean(), nullable=False),
        sa.Column("publication_state", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "(public_issue AND publication_state = 'pending') "
            "OR (NOT public_issue AND publication_state = 'private')",
            name=op.f("ck_feedback_submissions_initial_publication_choice"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_feedback_submissions")),
    )
    op.create_table(
        "feedback_attachments",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("feedback_id", sa.UUID(), nullable=False),
        sa.Column("field_id", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.Text(), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.CheckConstraint(
            "mime_type IN ('image/png', 'image/jpeg')",
            name=op.f("ck_feedback_attachments_mime_type_valid"),
        ),
        sa.CheckConstraint(
            "byte_size > 0",
            name=op.f("ck_feedback_attachments_byte_size_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["feedback_id"],
            ["feedback_submissions.id"],
            name=op.f("fk_feedback_attachments_feedback_id_feedback_submissions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_feedback_attachments")),
    )


def downgrade() -> None:
    """Refuse the destructive drop of retained feedback."""
    raise RuntimeError(
        "the feedback store retains submitted answers, attachments and publication state; "
        "restore a dump instead of dropping the tables"
    )
