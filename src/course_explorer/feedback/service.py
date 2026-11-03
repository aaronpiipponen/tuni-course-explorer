"""Validate and store feedback submissions and serve the operator's reads and deletion of the
saved store.

Every answer and upload is validated against the definition in force before a write. The validated
submission, its attachment metadata and its explicit publication choice are then stored in one
transaction, and only a committed transaction reports success. The saved publication state is the
state that the operator and the sender read and update. The operator listing, attachment read and
named deletion read the same definition and stored rows, and the transient reports they return are
not saved anywhere.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict
from sqlalchemy import case, func, or_, select, update
from sqlalchemy.orm import Session, sessionmaker

from course_explorer import administration
from course_explorer.config import FeedbackSettings, load_feedback_settings
from course_explorer.db.session import database_context, session_scope
from course_explorer.feedback import FeedbackValidationError
from course_explorer.feedback.attachments import (
    AttachmentStore,
    AttachmentUpload,
    StoredAttachment,
)
from course_explorer.feedback.definition import (
    AttachmentField,
    FeedbackDefinition,
    SelectField,
    TextField,
    load_feedback_definition,
)
from course_explorer.feedback.models import FeedbackAttachment, FeedbackSubmission
from course_explorer.feedback.publication import (
    PublicationInputError,
    PublicationResult,
    render_publication,
)
from course_explorer.feedback.schema import require_feedback_schema

PublicationState = Literal["private", "pending", "uncertain", "published", "partial", "failed"]
AttemptedPublicationState = Literal["published", "partial", "failed", "uncertain"]


class StoredFeedback(BaseModel):
    """One saved submission with its answers, publication choice and current outcome."""

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    id: UUID
    created_at: datetime
    answers: dict[str, str | None]
    public_issue: bool
    publication_state: PublicationState
    issue_url: str | None
    publication_failure: str | None
    attachments: tuple[StoredAttachment, ...]


class FeedbackListReport(BaseModel):
    """The current definition and every selected submission in reported order."""

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    definition: FeedbackDefinition
    submissions: tuple[StoredFeedback, ...]


class FeedbackAttachmentReport(BaseModel):
    """One stored attachment's metadata and its transient base64 content carrier."""

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    attachment: StoredAttachment
    content_base64: str


class FeedbackDeletionReport(BaseModel):
    """The identity of the one submission a deletion removed."""

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    feedback_id: UUID


class FeedbackPublicationReport(BaseModel):
    """The one selected record's identity and current publication outcome, when there was one."""

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    feedback_id: UUID | None = None
    publication_state: AttemptedPublicationState | None = None
    issue_url: str | None = None


def _stored_attachment(row: FeedbackAttachment) -> StoredAttachment:
    """Return one attachment's metadata from its row."""
    return StoredAttachment(
        id=row.id,
        feedback_id=row.feedback_id,
        field_id=row.field_id,
        filename=row.filename,
        mime_type=row.mime_type,
    )


def _stored_feedback(
    submission: FeedbackSubmission, attachment_rows: Sequence[FeedbackAttachment]
) -> StoredFeedback:
    """Assemble one stored submission from its row and attachment metadata rows."""
    return StoredFeedback(
        id=submission.id,
        created_at=submission.created_at,
        answers=dict(submission.answers),
        public_issue=submission.public_issue,
        publication_state=submission.publication_state,
        issue_url=submission.issue_url,
        publication_failure=submission.publication_failure,
        attachments=tuple(_stored_attachment(row) for row in attachment_rows),
    )


def _escape_like_literal(value: str) -> str:
    """Escape the wildcard and escape characters so a search stays literal."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def parse_feedback_filters(value: str) -> dict[str, str]:
    """Decode one JSON filter transport value into string field IDs and option values."""
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError as error:
        raise FeedbackValidationError("feedback filters must be one JSON object") from error
    if not isinstance(decoded, dict):
        raise FeedbackValidationError("feedback filters must be one JSON object")
    for field_id, option in decoded.items():
        if not isinstance(field_id, str) or not isinstance(option, str):
            raise FeedbackValidationError(
                "feedback filters must map field IDs to option values as text"
            )
    return decoded


def _validate_answers(
    definition: FeedbackDefinition, answers: Mapping[str, object]
) -> dict[str, str | None]:
    """Normalize the raw answer mapping against the definition in force or refuse it."""
    configured = {field.id for field in definition.fields}
    if set(answers) - configured:
        raise FeedbackValidationError("an answer names no configured feedback field")
    attachment_fields = {
        field.id for field in definition.fields if isinstance(field, AttachmentField)
    }
    if set(answers) & attachment_fields:
        raise FeedbackValidationError("attachment answers belong to the upload collection")

    validated: dict[str, str | None] = {}
    for field in definition.fields:
        if isinstance(field, AttachmentField):
            continue
        value = answers.get(field.id)
        if value is None or (isinstance(value, str) and not value.strip()):
            if field.required:
                raise FeedbackValidationError("a required feedback answer is missing")
            validated[field.id] = None
            continue
        if not isinstance(value, str):
            raise FeedbackValidationError("a feedback answer must be text or null")
        if isinstance(field, TextField):
            if len(value) > field.maxLength:
                raise FeedbackValidationError("a feedback answer exceeds its length limit")
        elif isinstance(field, SelectField):
            if value not in {option.value for option in field.options}:
                raise FeedbackValidationError("a select answer names no configured option")
        else:
            raise FeedbackValidationError("an answer names no configured feedback field")
        validated[field.id] = value
    return validated


class FeedbackService:
    """Validate and persist feedback submissions in the separate application store."""

    def __init__(
        self,
        factory: sessionmaker[Session],
        definition: FeedbackDefinition,
        attachments: AttachmentStore,
    ) -> None:
        self._factory = factory
        self._definition = definition
        self._attachments = attachments
        with factory() as session:
            require_feedback_schema(session.connection())

    def submit(
        self,
        *,
        answers: Mapping[str, object],
        attachments: Sequence[AttachmentUpload],
        public_issue: bool,
    ) -> StoredFeedback:
        """Validate and save one submission, returning it only after its commit."""
        if not isinstance(public_issue, bool):
            raise FeedbackValidationError("the publication choice must be true or false")
        normalized_answers = _validate_answers(self._definition, answers)
        validated_uploads = self._attachments.validate_uploads(self._definition, attachments)

        feedback_id = uuid4()
        stored_attachments = self._attachments.write_submission(feedback_id, validated_uploads)
        try:
            with session_scope(self._factory) as session:
                session.add(
                    FeedbackSubmission(
                        id=feedback_id,
                        answers=normalized_answers,
                        public_issue=public_issue,
                        publication_state="pending" if public_issue else "private",
                    )
                )
                session.flush()
                for attachment in stored_attachments:
                    session.add(
                        FeedbackAttachment(
                            id=attachment.id,
                            feedback_id=feedback_id,
                            field_id=attachment.field_id,
                            filename=attachment.filename,
                            mime_type=attachment.mime_type,
                        )
                    )
        except Exception:
            self._attachments.discard_submission(stored_attachments)
            raise
        return self.get(feedback_id)

    def publish_next(
        self,
        *,
        publish: Callable[[str, str, tuple[tuple[str, Path], ...]], PublicationResult],
    ) -> FeedbackPublicationReport:
        """Publish at most one opted-in pending submission through the supplied creator.

        The oldest pending row is claimed alone and committed as ``uncertain`` before the external
        call, so an interrupted attempt can never become pending again. The same row is then locked
        through one bounded external attempt and its result update. A deletion that already removed
        it leaves nothing to send. The callback receives the rendered title, body and designated
        attachment filenames and paths, and its result is the row's current outcome.
        """
        with session_scope(self._factory) as session:
            selected_id = session.scalar(
                select(FeedbackSubmission.id)
                .where(
                    FeedbackSubmission.publication_state == "pending",
                    FeedbackSubmission.public_issue.is_(True),
                )
                .order_by(FeedbackSubmission.created_at, FeedbackSubmission.id)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            if selected_id is None:
                return FeedbackPublicationReport()
            session.execute(
                update(FeedbackSubmission)
                .where(FeedbackSubmission.id == selected_id)
                .values(publication_state="uncertain")
            )

        with session_scope(self._factory) as session:
            submission = session.scalar(
                select(FeedbackSubmission)
                .where(FeedbackSubmission.id == selected_id)
                .with_for_update()
            )
            if submission is None:
                return FeedbackPublicationReport()
            attachment_rows = session.scalars(
                select(FeedbackAttachment)
                .where(FeedbackAttachment.feedback_id == selected_id)
                .order_by(FeedbackAttachment.field_id, FeedbackAttachment.id)
            ).all()
            attachments = [_stored_attachment(row) for row in attachment_rows]
            try:
                rendered = render_publication(
                    self._definition,
                    dict(submission.answers),
                    [
                        (
                            attachment.field_id,
                            attachment.filename,
                            self._attachments.path_for(attachment),
                        )
                        for attachment in attachments
                    ],
                )
            except PublicationInputError:
                submission.publication_state = "failed"
                submission.publication_failure = "publication_input_invalid"
                submission.issue_url = None
                session.flush()
                return FeedbackPublicationReport(
                    feedback_id=selected_id,
                    publication_state="failed",
                    issue_url=None,
                )
            result = publish(rendered.title, rendered.body, rendered.attachments)
            submission.publication_state = result.state
            submission.issue_url = result.issue_url
            submission.publication_failure = result.failure
            session.flush()
            return FeedbackPublicationReport(
                feedback_id=selected_id,
                publication_state=result.state,
                issue_url=result.issue_url,
            )

    def get(self, feedback_id: UUID) -> StoredFeedback:
        """Return one submission by its identity, or raise ``LookupError`` when it is absent."""
        with session_scope(self._factory) as session:
            submission = session.scalar(
                select(FeedbackSubmission).where(FeedbackSubmission.id == feedback_id)
            )
            if submission is None:
                raise LookupError("feedback submission not found")
            attachment_rows = session.scalars(
                select(FeedbackAttachment)
                .where(FeedbackAttachment.feedback_id == feedback_id)
                .order_by(FeedbackAttachment.field_id, FeedbackAttachment.id)
            ).all()
            return _stored_feedback(submission, attachment_rows)

    def list_submissions(
        self, *, query: str | None = None, filters: Mapping[str, str] | None = None
    ) -> FeedbackListReport:
        """List stored submissions under the configured search, filters and order.

        An absent or whitespace-only query applies no text filter. A query is a literal
        case-insensitive substring of every current text and textarea answer, with no wildcard
        meaning for ``%`` or ``_``. Results are grouped by the earliest matching text field in
        definition order, then newest first. Filters name a current select field and one of its
        options, and combine with AND. Invalid filter names or values raise
        :class:`FeedbackValidationError`.
        """
        normalized_filters = self._validate_filters(filters)
        text_field_ids = [
            field.id for field in self._definition.fields if isinstance(field, TextField)
        ]
        search = query if query is not None and query.strip() else None
        with session_scope(self._factory) as session:
            statement = select(FeedbackSubmission)
            for field_id, option in normalized_filters.items():
                statement = statement.where(FeedbackSubmission.answers[field_id].astext == option)
            if search is not None:
                if not text_field_ids:
                    return FeedbackListReport(definition=self._definition, submissions=())
                pattern = f"%{_escape_like_literal(search.lower())}%"
                matches = [
                    func.lower(FeedbackSubmission.answers[field_id].astext).like(
                        pattern, escape="\\"
                    )
                    for field_id in text_field_ids
                ]
                statement = statement.where(or_(*matches)).order_by(
                    case(
                        *((match, rank) for rank, match in enumerate(matches)), else_=len(matches)
                    ),
                    FeedbackSubmission.created_at.desc(),
                    FeedbackSubmission.id.desc(),
                )
            else:
                statement = statement.order_by(
                    FeedbackSubmission.created_at.desc(), FeedbackSubmission.id.desc()
                )
            submissions = session.scalars(statement).all()
            if not submissions:
                return FeedbackListReport(definition=self._definition, submissions=())
            attachment_rows = session.scalars(
                select(FeedbackAttachment)
                .where(
                    FeedbackAttachment.feedback_id.in_(
                        [submission.id for submission in submissions]
                    )
                )
                .order_by(FeedbackAttachment.field_id, FeedbackAttachment.id)
            ).all()
            attachments_by_submission: dict[UUID, list[FeedbackAttachment]] = {}
            for row in attachment_rows:
                attachments_by_submission.setdefault(row.feedback_id, []).append(row)
            return FeedbackListReport(
                definition=self._definition,
                submissions=tuple(
                    _stored_feedback(submission, attachments_by_submission.get(submission.id, ()))
                    for submission in submissions
                ),
            )

    def _validate_filters(self, filters: Mapping[str, str] | None) -> dict[str, str]:
        """Return the supplied filters after checking them against the current definition."""
        if filters is None:
            return {}
        select_fields = {
            field.id: field for field in self._definition.fields if isinstance(field, SelectField)
        }
        validated: dict[str, str] = {}
        for field_id, option in filters.items():
            field = select_fields.get(field_id)
            if field is None:
                raise FeedbackValidationError("a feedback filter names no configured select field")
            if not isinstance(option, str) or option not in {
                candidate.value for candidate in field.options
            }:
                raise FeedbackValidationError("a feedback filter names no configured option")
            validated[field_id] = option
        return validated

    def read_attachment(self, feedback_id: UUID, attachment_id: UUID) -> FeedbackAttachmentReport:
        """Return one attachment of one submission with its bytes as a base64 carrier.

        Both identities must name the same stored attachment, otherwise the read raises
        ``LookupError``. The bytes are transient command output and no filesystem path is returned.
        """
        with session_scope(self._factory) as session:
            row = session.scalar(
                select(FeedbackAttachment).where(
                    FeedbackAttachment.id == attachment_id,
                    FeedbackAttachment.feedback_id == feedback_id,
                )
            )
            if row is None:
                raise LookupError("feedback attachment not found")
            attachment = _stored_attachment(row)
        content = self._attachments.path_for(attachment).read_bytes()
        return FeedbackAttachmentReport(
            attachment=attachment,
            content_base64=base64.b64encode(content).decode("ascii"),
        )

    def delete(self, feedback_id: UUID) -> FeedbackDeletionReport:
        """Delete exactly one submission with its attachment metadata and stored files.

        A missing identity raises ``LookupError``. The row lock is held before the stored files are
        removed, so a deletion either wins before a publication attempt or waits for one already
        under way. The files are removed before the transaction commits, so a file failure can leave
        a partial removal, and a database failure after the file removal can leave the stored row in
        place. Both failures propagate rather than reporting success.
        """
        with session_scope(self._factory) as session:
            submission = session.scalar(
                select(FeedbackSubmission)
                .where(FeedbackSubmission.id == feedback_id)
                .with_for_update()
            )
            if submission is None:
                raise LookupError("feedback submission not found")
            attachment_rows = session.scalars(
                select(FeedbackAttachment).where(FeedbackAttachment.feedback_id == feedback_id)
            ).all()
            self._attachments.discard_submission(
                [_stored_attachment(row) for row in attachment_rows]
            )
            session.delete(submission)
        return FeedbackDeletionReport(feedback_id=feedback_id)


@contextmanager
def feedback_context(*, settings: FeedbackSettings | None = None) -> Iterator[FeedbackService]:
    """Open the feedback store with one definition and dispose its engine on exit."""
    resolved = settings if settings is not None else load_feedback_settings()
    definition = load_feedback_definition(administration.repository_root())
    with database_context(resolved) as factory:
        store = AttachmentStore(resolved.feedback_attachments_root)
        yield FeedbackService(factory, definition, store)


__all__ = [
    "FeedbackAttachmentReport",
    "FeedbackDeletionReport",
    "FeedbackListReport",
    "FeedbackPublicationReport",
    "FeedbackService",
    "FeedbackValidationError",
    "StoredAttachment",
    "StoredFeedback",
    "feedback_context",
    "parse_feedback_filters",
]
