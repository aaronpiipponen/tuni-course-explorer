"""Public-boundary proofs of single-attempt feedback publication over a disposable store."""

from __future__ import annotations

import base64
import json
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import update

from course_explorer.config import FeedbackSenderSettings
from course_explorer.feedback import publication
from course_explorer.feedback.attachments import AttachmentUpload
from course_explorer.feedback.definition import FeedbackDefinition, load_feedback_definition
from course_explorer.feedback.models import FeedbackSubmission
from course_explorer.feedback.publication import create_github_issue
from course_explorer.feedback.service import FeedbackPublicationReport, FeedbackService
from tests.feedback._support import (
    PublisherDouble,
    _image_bytes,
    _row_counts,
)
from tests.feedback.conftest import FeedbackDatabase
from tests.support import settings_factory

pytestmark = [pytest.mark.integration]

_ISSUE_URL = "https://github.com/example-owner/example-repository/issues/17"


def _sender_settings() -> FeedbackSenderSettings:
    """Return the example destination and timeout with one synthetic credential."""
    return settings_factory(FeedbackSenderSettings, FEEDBACK_GITHUB_TOKEN="synthetic-sender-token")


def _service(
    database: FeedbackDatabase, definition: FeedbackDefinition | None = None
) -> FeedbackService:
    """Open the store with the supplied definition or the example one."""
    return FeedbackService(database.factory, definition or database.definition, database.store)


def _publish(service: FeedbackService) -> FeedbackPublicationReport:
    """Publish once through the real adapter and one synthetic credential."""

    def publisher(title: str, body: str, attachments: tuple[tuple[str, Path], ...]):
        return create_github_issue(
            settings=_sender_settings(), title=title, body=body, attachments=attachments
        )

    return service.publish_next(publish=publisher)


def _add_unmapped_definition(root: Path) -> FeedbackDefinition:
    """Copy the definition with one unmapped text field and one unmapped attachment field."""
    path = root / "config" / "feedback-form.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["fields"].insert(
        len(payload["fields"]) - 1,
        {
            "id": "extra_note",
            "kind": "text",
            "label": {"en": "Extra note", "fi": "Lisätieto"},
            "required": False,
            "maxLength": 200,
        },
    )
    payload["fields"].append(
        {
            "id": "extra_files",
            "kind": "attachment",
            "label": {"en": "Extra files", "fi": "Lisätiedostot"},
            "required": False,
            "acceptedMimeTypes": ["image/png", "image/jpeg"],
            "maxFiles": 1,
            "maxBytesPerFile": 5242880,
        }
    )
    path.write_text(json.dumps(payload), encoding="utf-8")
    return load_feedback_definition(root)


def test_feedback_publication_uses_only_the_configured_issue_mapping(
    feedback_database: FeedbackDatabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The real renderer and CLI adapter send only the mapped fields and designated image."""
    definition = _add_unmapped_definition(feedback_database.root)
    service = _service(feedback_database, definition)
    screenshot = _image_bytes("PNG")
    second_screenshot = _image_bytes("PNG", noise=True)
    extra_file = _image_bytes("JPEG", noise=True)
    stored = service.submit(
        answers={
            "type": "bug",
            "title": "Mapping check",
            "message": "First line\nSecond line",
            "affected_feature": "search",
            "role": "student",
            "extra_note": "Unmapped note text",
        },
        attachments=[
            AttachmentUpload(field_id="screenshots", filename="screenshot.png", content=screenshot),
            AttachmentUpload(
                field_id="screenshots", filename="second.png", content=second_screenshot
            ),
            AttachmentUpload(field_id="extra_files", filename="extra-file.jpg", content=extra_file),
        ],
        public_issue=True,
    )
    publisher = PublisherDouble()
    monkeypatch.setattr(publication.subprocess, "run", publisher)

    report = _publish(service)

    assert report.feedback_id == stored.id
    assert report.publication_state == "published"
    assert report.issue_url == _ISSUE_URL
    assert len(publisher.calls) == 1
    call = publisher.calls[0]
    assert call.argv[:4] == ("gh", "issue", "create", "--repo")
    assert call.argv[call.argv.index("--repo") + 1] == "example-owner/example-repository"
    assert call.argv[call.argv.index("--title") + 1] == "[BUG] Mapping check"
    assert call.argv[call.argv.index("--body-file") + 1] == "-"
    attached = [call.argv[index + 1] for index, item in enumerate(call.argv) if item == "--attach"]
    assert [Path(path).name for path in attached] == ["screenshot.png", "second.png"]
    assert call.attached == {
        "screenshot.png": screenshot,
        "second.png": second_screenshot,
    }
    assert "extra-file.jpg" not in call.attached

    body = call.body
    assert body == ("## Message\n\nFirst line\nSecond line\n\n## Affected feature\n\nSearch")
    assert "Unmapped note text" not in body
    assert "student" not in body.lower()
    assert str(feedback_database.store_root) not in body

    assert call.environment["GH_TOKEN"] == "synthetic-sender-token"
    assert call.environment["GH_PROMPT_DISABLED"] == "1"
    assert "HOME" in call.environment
    assert "PATH" in call.environment
    assert set(call.environment) <= {
        "HOME",
        "PATH",
        "LANG",
        "GH_TOKEN",
        "GH_CONFIG_DIR",
        "GH_PROMPT_DISABLED",
    }
    assert not Path(call.environment["GH_CONFIG_DIR"]).exists()
    assert call.timeout == 120.0

    published = service.get(stored.id)
    assert published.publication_state == "published"
    assert published.issue_url == _ISSUE_URL
    assert published.publication_failure is None


def test_feedback_publication_preserves_a_created_issue_on_partial_upload(
    feedback_database: FeedbackDatabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A nonzero attachment upload that printed a canonical link stays partial and never repeats."""
    service = _service(feedback_database)
    content = _image_bytes("PNG")
    stored = service.submit(
        answers={"type": "bug", "title": "Partial upload", "message": "Body text"},
        attachments=[
            AttachmentUpload(field_id="screenshots", filename="screenshot.png", content=content)
        ],
        public_issue=True,
    )
    publisher = PublisherDouble(returncode=1)
    monkeypatch.setattr(publication.subprocess, "run", publisher)

    report = _publish(service)

    assert report.feedback_id == stored.id
    assert report.publication_state == "partial"
    assert report.issue_url == _ISSUE_URL
    assert len(publisher.calls) == 1

    partial = service.get(stored.id)
    assert partial.publication_state == "partial"
    assert partial.issue_url == _ISSUE_URL
    assert partial.publication_failure == "attachment_upload_incomplete"
    assert partial.answers == stored.answers
    attachment = partial.attachments[0]
    read = service.read_attachment(stored.id, attachment.id)
    assert base64.b64decode(read.content_base64) == content

    again = _publish(service)
    assert again == FeedbackPublicationReport()
    assert len(publisher.calls) == 1
    assert service.get(stored.id).publication_state == "partial"


@pytest.mark.parametrize("variant", ["timeout", "unconfirmed", "precommitted"])
def test_feedback_publication_never_retries_an_unconfirmed_creation(
    feedback_database: FeedbackDatabase, monkeypatch: pytest.MonkeyPatch, variant: str
) -> None:
    """A timeout, an unconfirmed failure and an interrupted claim all keep the row and never resend."""
    service = _service(feedback_database)
    content = _image_bytes("PNG")
    stored = service.submit(
        answers={"type": "bug", "title": "Unconfirmed", "message": "Body text"},
        attachments=[
            AttachmentUpload(field_id="screenshots", filename="screenshot.png", content=content)
        ],
        public_issue=True,
    )
    if variant == "precommitted":
        with feedback_database.factory.begin() as session:
            session.execute(
                update(FeedbackSubmission)
                .where(FeedbackSubmission.id == stored.id)
                .values(publication_state="uncertain")
            )
        publisher = PublisherDouble()
    elif variant == "timeout":
        publisher = PublisherDouble(error=subprocess.TimeoutExpired(cmd=("gh",), timeout=1.0))
    else:
        publisher = PublisherDouble(returncode=1, stdout="")
    monkeypatch.setattr(publication.subprocess, "run", publisher)

    report = _publish(service)

    if variant == "precommitted":
        assert report.feedback_id is None
        assert publisher.calls == []
    else:
        assert report.feedback_id == stored.id
        assert report.publication_state == "uncertain"
        assert report.issue_url is None
        assert len(publisher.calls) == 1

    reread = FeedbackService(
        feedback_database.factory, feedback_database.definition, feedback_database.store
    ).get(stored.id)
    assert reread.publication_state == "uncertain"
    assert reread.issue_url is None
    assert reread.answers == stored.answers
    assert (
        base64.b64decode(
            service.read_attachment(stored.id, stored.attachments[0].id).content_base64
        )
        == content
    )

    again = _publish(service)
    assert again.feedback_id is None
    assert len(publisher.calls) == (0 if variant == "precommitted" else 1)
    listed = FeedbackService(
        feedback_database.factory, feedback_database.definition, feedback_database.store
    ).list_submissions()
    assert listed.submissions[0].publication_state == "uncertain"
    assert _row_counts(feedback_database) == (1, 1)
