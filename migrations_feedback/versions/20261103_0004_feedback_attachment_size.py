"""Drop the unread stored byte size of every feedback attachment."""

from collections.abc import Sequence

from alembic import op

revision: str = "20261103_feedback_0004"
down_revision: str | Sequence[str] | None = "20261103_feedback_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Drop the size check and the size column."""
    op.drop_constraint(
        op.f("ck_feedback_attachments_byte_size_positive"),
        "feedback_attachments",
        type_="check",
    )
    op.drop_column("feedback_attachments", "byte_size")


def downgrade() -> None:
    """Refuse the destructive rollback of unretained attachment sizes."""
    raise RuntimeError("the attachment byte sizes are not retained; restore a dump instead")
