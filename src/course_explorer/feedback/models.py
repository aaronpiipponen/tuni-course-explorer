"""SQLAlchemy metadata for the feedback application store.

These tables live in a separate application database from the curriculum store and carry their own
metadata and migration head. A submission holds the answers by configured field ID, the explicit
publication choice and its outcome. Its attachments record the owning submission, the generated
identity, field, filename and detected image type, and the image bytes live on disk.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    MetaData,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Naming templates for the generated index, unique, check, foreign key and primary key names of the
# store.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class FeedbackBase(DeclarativeBase):
    """Declarative root carrying this store's own metadata and naming conventions."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class FeedbackSubmission(FeedbackBase):
    """One stored anonymous submission with its answers and publication choice."""

    __tablename__ = "feedback_submissions"
    __table_args__ = (
        CheckConstraint(
            "(public_issue AND publication_state IN "
            "('pending', 'uncertain', 'published', 'partial', 'failed')) "
            "OR (NOT public_issue AND publication_state = 'private')",
            name="current_publication_state",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    answers: Mapped[dict] = mapped_column(JSONB(none_as_null=True))
    public_issue: Mapped[bool] = mapped_column(Boolean)
    publication_state: Mapped[str] = mapped_column(Text)
    issue_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    publication_failure: Mapped[str | None] = mapped_column(Text, nullable=True)


class FeedbackAttachment(FeedbackBase):
    """The metadata of one stored image file that belongs to a submission."""

    __tablename__ = "feedback_attachments"
    __table_args__ = (
        CheckConstraint("mime_type IN ('image/png', 'image/jpeg')", name="mime_type_valid"),
        CheckConstraint("length(filename) > 0", name="filename_present"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    feedback_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("feedback_submissions.id", ondelete="CASCADE")
    )
    field_id: Mapped[str] = mapped_column(Text)
    filename: Mapped[str] = mapped_column(Text)
    mime_type: Mapped[str] = mapped_column(Text)


__all__ = ["FeedbackAttachment", "FeedbackBase", "FeedbackSubmission"]
