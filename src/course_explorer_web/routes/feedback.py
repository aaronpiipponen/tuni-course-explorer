"""The feedback HTTP surface: the definition read and the anonymous submission write.

The definition read reports the current ordered definition beside the configured destination
metadata and body bound, and it opens no feedback database. The submission decodes the standard
base64 carriers and calls the feedback service once inside its owning context, so the service keeps
the only answer, upload and image validation. Both answers are non-cacheable, and a failure answer
names no input, stored identity, local path or publication promise.
"""

from __future__ import annotations

import base64
import binascii
from collections.abc import Sequence
from typing import Literal

from fastapi import APIRouter
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictStr

from course_explorer import administration
from course_explorer.config import load_feedback_intake_settings
from course_explorer.feedback import FeedbackValidationError
from course_explorer.feedback.attachments import AttachmentUpload
from course_explorer.feedback.definition import FeedbackDefinition, load_feedback_definition
from course_explorer.feedback.service import feedback_context
from course_explorer_web.feedback_intake import (
    FEEDBACK_DEFINITION_PATH,
    FEEDBACK_SUBMISSION_PATH,
)

router = APIRouter()

_NO_STORE = {"Cache-Control": "no-store"}


class FeedbackUploadRequest(BaseModel):
    """One attachment carrier: its field, its display filename and its standard base64 content."""

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    field_id: StrictStr = Field(repr=False)
    filename: StrictStr = Field(repr=False)
    content_base64: StrictStr = Field(repr=False)


class FeedbackSubmissionRequest(BaseModel):
    """One submission: its text and select answers, attachment carriers and explicit choice."""

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    answers: dict[str, StrictStr | None] = Field(repr=False)
    attachments: tuple[FeedbackUploadRequest, ...] = Field(repr=False)
    public_issue: StrictBool = Field(repr=False)


class FeedbackFormReport(BaseModel):
    """The current ordered definition and the configured presentation metadata."""

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    definition: FeedbackDefinition
    repository: str
    visibility: Literal["public", "private"]
    max_request_bytes: int


class FeedbackAcknowledgment(BaseModel):
    """The narrow committed outcome of one accepted submission."""

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    accepted: Literal[True] = True
    publication_state: Literal["private", "pending"]


def _decode_uploads(
    carriers: Sequence[FeedbackUploadRequest],
) -> tuple[AttachmentUpload, ...]:
    """Decode standard base64 carriers into uploads without echoing their content."""
    uploads: list[AttachmentUpload] = []
    for carrier in carriers:
        try:
            content = base64.b64decode(carrier.content_base64, validate=True)
        except (binascii.Error, ValueError) as error:
            raise FeedbackValidationError(
                "feedback attachment content is not standard base64"
            ) from error
        uploads.append(
            AttachmentUpload(
                field_id=carrier.field_id,
                filename=carrier.filename,
                content=content,
            )
        )
    return tuple(uploads)


def _invalid_feedback() -> Response:
    """Return the fixed non-cacheable refusal of one invalid submission."""
    return JSONResponse(status_code=422, content={"detail": "Invalid feedback"}, headers=_NO_STORE)


def _operation_failed(exc: Exception) -> Response:
    """Return one non-cacheable failure naming the exception class alone."""
    return JSONResponse(status_code=500, content={"error": type(exc).__name__}, headers=_NO_STORE)


@router.get(FEEDBACK_DEFINITION_PATH)
def definition() -> Response:
    """Return the current definition with the configured destination metadata and body bound."""
    try:
        settings = load_feedback_intake_settings()
        report = FeedbackFormReport(
            definition=load_feedback_definition(administration.repository_root()),
            repository=settings.feedback_github_repository,
            visibility=settings.feedback_github_visibility,
            max_request_bytes=settings.feedback_max_request_bytes,
        )
    except Exception as exc:
        return _operation_failed(exc)
    return JSONResponse(report.model_dump(mode="json"), headers=_NO_STORE)


@router.post(FEEDBACK_SUBMISSION_PATH)
def submit(body: FeedbackSubmissionRequest) -> Response:
    """Validate and save one submission through its owning service, then acknowledge it."""
    try:
        uploads = _decode_uploads(body.attachments)
        with feedback_context() as service:
            stored = service.submit(
                answers=body.answers,
                attachments=uploads,
                public_issue=body.public_issue,
            )
    except FeedbackValidationError:
        return _invalid_feedback()
    except Exception as exc:
        return _operation_failed(exc)
    acknowledgment = FeedbackAcknowledgment(
        publication_state="pending" if stored.public_issue else "private"
    )
    return JSONResponse(
        status_code=201, content=acknowledgment.model_dump(mode="json"), headers=_NO_STORE
    )
