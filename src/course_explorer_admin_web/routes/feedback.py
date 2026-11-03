"""The Feedback routes: the protected listing, attachment read and named deletion.

Each route maps one authenticated request to exactly one fixed command and returns that command's
transient outcome. The listing serves the console's automatic panel read and the attachment read is an
explicit action. The listing and the attachment read forward the console's automatic-read marker,
and the deletion records its own outcome. The command's owning service validates the search, filters
and identities, and this layer validates shape alone. Every answer is non-cacheable, and an
attachment report exists only in the transient outcome.
"""

from __future__ import annotations

from fastapi import APIRouter, Request, Response

from course_explorer_admin_web.routes.auth import NO_STORE_HEADERS
from course_explorer_admin_web.routes.read_mode import automatic_read
from course_explorer_admin_web.runner import (
    CommandResult,
    FeedbackAttachmentCommand,
    FeedbackAttachmentInput,
    FeedbackDeleteCommand,
    FeedbackDeleteInput,
    FeedbackListCommand,
    FeedbackListInput,
)

router = APIRouter()


class FeedbackListRequest(FeedbackListInput):
    """One requested feedback listing with its optional search and select filters."""


class FeedbackAttachmentRequest(FeedbackAttachmentInput):
    """One requested transient attachment read keyed by both stored identities."""


class FeedbackDeleteRequest(FeedbackDeleteInput):
    """One requested deletion of one named feedback submission."""


@router.post("/api/feedback/list")
def listing(request: Request, response: Response, body: FeedbackListRequest) -> CommandResult:
    """Run the fixed feedback listing once and return its transient outcome."""
    response.headers.update(NO_STORE_HEADERS)
    return request.app.state.commands.run(
        FeedbackListCommand(kind="feedback-list", query=body.query, filters=body.filters),
        automatic=automatic_read(request),
    )


@router.post("/api/feedback/attachment")
def attachment(
    request: Request, response: Response, body: FeedbackAttachmentRequest
) -> CommandResult:
    """Run the fixed attachment read once and return its transient outcome."""
    response.headers.update(NO_STORE_HEADERS)
    return request.app.state.commands.run(
        FeedbackAttachmentCommand(
            kind="feedback-attachment",
            feedback_id=body.feedback_id,
            attachment_id=body.attachment_id,
        ),
        automatic=automatic_read(request),
    )


@router.post("/api/feedback/delete")
def delete(request: Request, response: Response, body: FeedbackDeleteRequest) -> CommandResult:
    """Run the fixed named deletion once and return its transient outcome."""
    response.headers.update(NO_STORE_HEADERS)
    return request.app.state.commands.run(
        FeedbackDeleteCommand(kind="feedback-delete", feedback_id=body.feedback_id)
    )
