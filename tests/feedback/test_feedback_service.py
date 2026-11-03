"""Public-boundary proofs of validated feedback submission against a disposable store."""

from __future__ import annotations

import base64
import json
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.migration import MigrationContext
from sqlalchemy import inspect, text, update

from course_explorer.db.models import Base
from course_explorer.feedback import FeedbackValidationError
from course_explorer.feedback.attachments import AttachmentUpload
from course_explorer.feedback.definition import (
    FeedbackDefinition,
    SelectField,
    TextField,
    load_feedback_definition,
)
from course_explorer.feedback.models import FeedbackSubmission
from course_explorer.feedback.publication import PublicationResult
from course_explorer.feedback.service import FeedbackService
from tests.feedback._support import _image_bytes, _row_counts, _stored_entries
from tests.feedback.conftest import (
    FEEDBACK_HEAD,
    FEEDBACK_TABLES,
    FeedbackDatabase,
    FeedbackHttpSite,
    feedback_alembic_config,
)
from tests.support.database import scratch_database

pytestmark = [pytest.mark.integration]


def _rewrite_attachment_limits(
    root: Path, *, max_files: int | None = None, max_bytes: int | None = None
) -> FeedbackDefinition:
    """Rewrite only the copied definition's attachment limits and load it again."""
    path = root / "config" / "feedback-form.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    for field in payload["fields"]:
        if field["kind"] == "attachment":
            if max_files is not None:
                field["maxFiles"] = max_files
            if max_bytes is not None:
                field["maxBytesPerFile"] = max_bytes
    path.write_text(json.dumps(payload), encoding="utf-8")
    return load_feedback_definition(root)


def _set_created_at(database: FeedbackDatabase, feedback_id: UUID, created_at: datetime) -> None:
    """Give one stored submission a known creation time so report order is deterministic."""
    with database.factory.begin() as session:
        session.execute(
            update(FeedbackSubmission)
            .where(FeedbackSubmission.id == feedback_id)
            .values(created_at=created_at)
        )


def _unexpected_publish(title: str, body: str, attachments: tuple[Path, ...]) -> PublicationResult:
    """Fail when a private submission reaches the publication callback."""
    raise AssertionError("a private submission must not be published")


def test_feedback_schema_is_independent_of_curriculum() -> None:
    """The feedback chain migrates existing rows to its own head without the curriculum metadata."""
    private_id = uuid4()
    pending_id = uuid4()
    private_answers = json.dumps({"type": "other", "title": "Private", "message": "Kept"})
    pending_answers = json.dumps({"type": "bug", "title": "Pending", "message": "Queued"})
    with scratch_database("course_feedback") as engine:
        with engine.connect() as connection:
            command.upgrade(feedback_alembic_config(connection), "20261027_feedback_0001")
        with engine.begin() as connection:
            for feedback_id, answers, public_issue, state in (
                (private_id, private_answers, False, "private"),
                (pending_id, pending_answers, True, "pending"),
            ):
                connection.execute(
                    text(
                        "INSERT INTO feedback_submissions "
                        "(id, answers, public_issue, publication_state) "
                        "VALUES (:id, CAST(:answers AS jsonb), :public_issue, :state)"
                    ),
                    {
                        "id": feedback_id,
                        "answers": answers,
                        "public_issue": public_issue,
                        "state": state,
                    },
                )
        with engine.connect() as connection:
            command.upgrade(feedback_alembic_config(connection), "head")
        with engine.connect() as connection:
            rows = connection.execute(
                text(
                    "SELECT id, answers, public_issue, publication_state, issue_url, "
                    "publication_failure FROM feedback_submissions ORDER BY id"
                )
            ).all()
            by_id = {row.id: row for row in rows}
            assert set(by_id) == {private_id, pending_id}
            assert by_id[private_id].answers == json.loads(private_answers)
            assert by_id[private_id].public_issue is False
            assert by_id[private_id].publication_state == "private"
            assert by_id[pending_id].answers == json.loads(pending_answers)
            assert by_id[pending_id].public_issue is True
            assert by_id[pending_id].publication_state == "pending"
            for row in rows:
                assert row.issue_url is None
                assert row.publication_failure is None

            assert set(inspect(connection).get_table_names()) == {
                *FEEDBACK_TABLES,
                "alembic_version",
            }
            assert (
                connection.scalar(
                    text("SELECT count(*) FROM pg_extension WHERE extname = 'vector'")
                )
                == 0
            )
            assert MigrationContext.configure(connection).get_current_heads() == (FEEDBACK_HEAD,)
    assert FEEDBACK_TABLES.isdisjoint(Base.metadata.tables)


@pytest.mark.parametrize(
    ("image_format", "public_issue", "type_value"),
    [("PNG", True, "other"), ("JPEG", False, "bug")],
)
def test_feedback_submission_round_trips_answers_attachments_and_publication_choice(
    feedback_database: FeedbackDatabase,
    feedback_http: Callable[..., AbstractContextManager[FeedbackHttpSite]],
    image_format: str,
    public_issue: bool,
    type_value: str,
) -> None:
    """A submission through the HTTP surface stores its answers, choice, bytes and metadata."""
    content = _image_bytes(image_format)
    answers = {
        "type": type_value,
        "title": "Round trip",
        "message": "Message text",
        "affected_feature": "search",
    }
    with feedback_http(database=feedback_database, admission_enabled=False) as site:
        definition_response = site.client.get("/api/feedback/definition")
        assert definition_response.status_code == 200
        assert definition_response.headers["cache-control"] == "no-store"
        cookie = definition_response.headers["set-cookie"]
        assert "tce_anon=" in cookie
        assert "HttpOnly" in cookie
        assert "Secure" in cookie
        assert "SameSite=Lax" in cookie
        report = definition_response.json()
        assert report["repository"] == "example-owner/example-repository"
        assert report["visibility"] == "public"
        assert report["max_request_bytes"] == 25165824
        assert (
            FeedbackDefinition.model_validate(report["definition"]) == feedback_database.definition
        )

        response = site.client.post(
            "/api/feedback",
            json={
                "answers": answers,
                "attachments": [
                    {
                        "field_id": "screenshots",
                        "filename": "screenshot.png",
                        "content_base64": base64.b64encode(content).decode("ascii"),
                    }
                ],
                "public_issue": public_issue,
            },
        )
    assert response.status_code == 201
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "accepted": True,
        "publication_state": "pending" if public_issue else "private",
    }

    service = FeedbackService(
        feedback_database.factory, feedback_database.definition, feedback_database.store
    )
    listed = service.list_submissions().submissions
    assert len(listed) == 1
    stored = listed[0]

    assert stored.answers == {
        "type": type_value,
        "title": "Round trip",
        "message": "Message text",
        "affected_feature": "search",
        "role": None,
    }
    assert stored.public_issue is public_issue
    assert stored.publication_state == ("pending" if public_issue else "private")
    assert stored.issue_url is None
    assert stored.publication_failure is None
    assert stored.created_at.tzinfo is not None
    assert len(stored.attachments) == 1
    attachment = stored.attachments[0]
    assert attachment.feedback_id == stored.id
    assert attachment.field_id == "screenshots"
    assert attachment.mime_type == ("image/png" if image_format == "PNG" else "image/jpeg")

    suffix = ".png" if image_format == "PNG" else ".jpg"
    path = feedback_database.store.path_for(attachment)
    assert path == (
        feedback_database.store_root
        / "screenshots"
        / str(stored.id)
        / f"{attachment.id.hex}{suffix}"
    )
    assert path.read_bytes() == content
    assert path.stat().st_mode & 0o777 == 0o600
    assert path.parent.stat().st_mode & 0o777 == 0o700
    assert path.parent.parent.stat().st_mode & 0o777 == 0o700
    assert feedback_database.store_root.stat().st_mode & 0o777 == 0o700

    reread = FeedbackService(
        feedback_database.factory, feedback_database.definition, feedback_database.store
    ).get(stored.id)
    assert reread == stored

    if not public_issue:
        unpublished = FeedbackService(
            feedback_database.factory, feedback_database.definition, feedback_database.store
        ).publish_next(publish=_unexpected_publish)
        assert unpublished.feedback_id is None
        assert service.get(stored.id).publication_state == "private"


@pytest.mark.parametrize(
    "answers",
    [
        {"type": "bug", "title": "Missing message"},
        {"type": "invalid", "title": "Unknown option", "message": "Body text"},
    ],
)
def test_feedback_submission_rejects_invalid_answers_without_writes(
    feedback_database: FeedbackDatabase, answers: dict[str, object]
) -> None:
    """An invalid answer refuses the whole submission and writes no row or file."""
    service = FeedbackService(
        feedback_database.factory, feedback_database.definition, feedback_database.store
    )

    with pytest.raises(FeedbackValidationError):
        service.submit(
            answers=answers,
            attachments=[
                AttachmentUpload(
                    field_id="screenshots", filename="screenshot.png", content=_image_bytes("PNG")
                )
            ],
            public_issue=True,
        )

    assert _row_counts(feedback_database) == (0, 0)
    assert _stored_entries(feedback_database.store_root) == []


@pytest.mark.parametrize("variant", ["malformed", "truncated", "oversized", "too_many"])
def test_feedback_submission_rejects_invalid_uploads_without_writes(
    feedback_database: FeedbackDatabase, variant: str
) -> None:
    """An invalid upload preflight refuses the submission and writes no row or file."""
    definition = feedback_database.definition
    valid = _image_bytes("PNG")
    uploads = [
        AttachmentUpload(field_id="screenshots", filename="screenshot.png", content=valid),
        AttachmentUpload(
            field_id="screenshots", filename="screenshot.png", content=b"not an image"
        ),
    ]
    if variant == "truncated":
        uploads[1] = AttachmentUpload(
            field_id="screenshots",
            filename="screenshot.png",
            content=_image_bytes("PNG", size=(8, 8))[:30],
        )
    elif variant == "oversized":
        definition = _rewrite_attachment_limits(feedback_database.root, max_bytes=1000)
        uploads[1] = AttachmentUpload(
            field_id="screenshots",
            filename="screenshot.png",
            content=_image_bytes("PNG", size=(64, 64), noise=True),
        )
    elif variant == "too_many":
        definition = _rewrite_attachment_limits(feedback_database.root, max_files=3)
        uploads = [
            AttachmentUpload(field_id="screenshots", filename="screenshot.png", content=valid)
            for _ in range(4)
        ]

    service = FeedbackService(feedback_database.factory, definition, feedback_database.store)
    with pytest.raises(FeedbackValidationError):
        service.submit(
            answers={"type": "bug", "title": "Upload check", "message": "Body text"},
            attachments=uploads,
            public_issue=False,
        )

    assert _row_counts(feedback_database) == (0, 0)
    assert _stored_entries(feedback_database.store_root) == []


def _submit_text(
    service: FeedbackService, *, title: str, message: str, extra: dict[str, str] | None = None
):
    """Submit one attachment-free feedback response with the supplied text answers."""
    answers: dict[str, object] = {"type": "bug", "title": title, "message": message}
    answers.update(extra or {})
    return service.submit(answers=answers, attachments=[], public_issue=False)


def test_feedback_search_uses_configured_text_order_without_duplicates(
    feedback_database: FeedbackDatabase,
) -> None:
    """JSON text order groups literal matches once, and swapping it swaps search priority."""
    service = FeedbackService(
        feedback_database.factory, feedback_database.definition, feedback_database.store
    )
    title_only = _submit_text(service, title="Needle in title", message="plain body")
    message_only = _submit_text(service, title="Plain title", message="needle in message")
    both = _submit_text(service, title="Needle title", message="Needle message")
    wildcard = _submit_text(service, title="Wild 100%_card", message="literal marker")
    decoy = _submit_text(service, title="Wild 100xxcard", message="literal marker")

    base = datetime(2026, 1, 1, tzinfo=UTC)
    for offset, submission in enumerate((title_only, message_only, both, wildcard, decoy), start=1):
        _set_created_at(feedback_database, submission.id, base.replace(minute=offset))

    text_order = [
        field.id for field in feedback_database.definition.fields if isinstance(field, TextField)
    ]
    assert text_order == ["title", "message"]

    found = service.list_submissions(query="nEeDlE")
    assert [submission.id for submission in found.submissions] == [
        both.id,
        title_only.id,
        message_only.id,
    ]
    assert len({submission.id for submission in found.submissions}) == 3
    assert found.definition == feedback_database.definition

    assert [
        submission.id for submission in service.list_submissions(query="100%_card").submissions
    ] == [wildcard.id]

    newest_first = [decoy.id, wildcard.id, both.id, message_only.id, title_only.id]
    assert [submission.id for submission in service.list_submissions().submissions] == newest_first
    assert [
        submission.id for submission in service.list_submissions(query="   ").submissions
    ] == newest_first

    path = feedback_database.root / "config" / "feedback-form.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    fields = payload["fields"]
    title_index = next(index for index, field in enumerate(fields) if field["id"] == "title")
    message_index = next(index for index, field in enumerate(fields) if field["id"] == "message")
    fields[title_index], fields[message_index] = fields[message_index], fields[title_index]
    path.write_text(json.dumps(payload), encoding="utf-8")
    swapped = load_feedback_definition(feedback_database.root)
    swapped_service = FeedbackService(feedback_database.factory, swapped, feedback_database.store)

    assert [field.id for field in swapped.fields if isinstance(field, TextField)] == [
        "message",
        "title",
    ]
    assert [
        submission.id for submission in swapped_service.list_submissions(query="needle").submissions
    ] == [
        both.id,
        message_only.id,
        title_only.id,
    ]
    assert swapped_service.get(both.id).answers == both.answers


def test_feedback_filters_combine_every_configured_select(
    feedback_database: FeedbackDatabase,
) -> None:
    """Every configured select contributes one AND filter derived from the loaded definition."""
    path = feedback_database.root / "config" / "feedback-form.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["fields"].insert(
        len(payload["fields"]) - 1,
        {
            "id": "platform",
            "kind": "select",
            "label": {"en": "Platform", "fi": "Alusta"},
            "required": False,
            "options": [
                {"value": "desktop", "label": {"en": "Desktop", "fi": "Työpöytä"}},
                {"value": "mobile", "label": {"en": "Mobile", "fi": "Mobiili"}},
            ],
        },
    )
    path.write_text(json.dumps(payload), encoding="utf-8")
    definition = load_feedback_definition(feedback_database.root)
    service = FeedbackService(feedback_database.factory, definition, feedback_database.store)

    select_fields = [field for field in definition.fields if isinstance(field, SelectField)]
    assert [field.id for field in select_fields] == [
        "type",
        "affected_feature",
        "role",
        "platform",
    ]
    filters = {field.id: field.options[0].value for field in select_fields}
    matching_answers = {
        "type": "bug",
        "title": "Combined filters",
        "message": "Every select matches",
        "affected_feature": "search",
        "role": "student",
        "platform": "desktop",
    }
    matching = service.submit(answers=matching_answers, attachments=[], public_issue=False)
    for field in select_fields:
        near_miss = dict(matching_answers)
        near_miss[field.id] = field.options[1].value
        service.submit(answers=near_miss, attachments=[], public_issue=False)

    found = service.list_submissions(filters=filters)
    assert [submission.id for submission in found.submissions] == [matching.id]


def test_feedback_deletion_removes_only_the_named_submission_and_attachments(
    feedback_database: FeedbackDatabase,
) -> None:
    """A named deletion removes its row, metadata and files while the other submission survives."""
    target_content = _image_bytes("PNG")
    other_content = _image_bytes("JPEG")
    service = FeedbackService(
        feedback_database.factory, feedback_database.definition, feedback_database.store
    )
    target = service.submit(
        answers={"type": "bug", "title": "Delete target", "message": "Target body"},
        attachments=[
            AttachmentUpload(
                field_id="screenshots", filename="screenshot.png", content=target_content
            )
        ],
        public_issue=True,
    )
    other = service.submit(
        answers={"type": "other", "title": "Keep this", "message": "Other body"},
        attachments=[
            AttachmentUpload(
                field_id="screenshots", filename="screenshot.png", content=other_content
            )
        ],
        public_issue=False,
    )
    target_attachment = target.attachments[0]
    other_attachment = other.attachments[0]
    target_path = feedback_database.store.path_for(target_attachment)
    other_path = feedback_database.store.path_for(other_attachment)

    read = service.read_attachment(target.id, target_attachment.id)
    assert read.attachment == target_attachment
    assert base64.b64decode(read.content_base64) == target_content
    assert str(feedback_database.store_root) not in read.model_dump_json()
    assert str(target_path) not in read.model_dump_json()

    with pytest.raises(LookupError):
        service.read_attachment(target.id, other_attachment.id)

    deleted = service.delete(target.id)
    assert deleted.feedback_id == target.id

    with pytest.raises(LookupError):
        service.get(target.id)
    with pytest.raises(LookupError):
        service.read_attachment(target.id, target_attachment.id)
    assert _row_counts(feedback_database) == (1, 1)
    assert not target_path.exists()
    assert not target_path.parent.exists()
    assert feedback_database.store_root.is_dir()
    assert (feedback_database.store_root / "screenshots").is_dir()

    assert other_path.read_bytes() == other_content
    assert service.get(other.id) == other
    survived = service.read_attachment(other.id, other_attachment.id)
    assert survived.attachment == other_attachment
    assert base64.b64decode(survived.content_base64) == other_content

    unsent = service.publish_next(publish=_unexpected_publish)
    assert unsent.feedback_id is None
