"""The front router's feedback submission gate: exact site, media type, length and allowance.

The gate answers a refusal before any identity exists, charges an admitted attempt to the router's
transient allowance, reads the body under the configured byte bound, and returns the cookie, body and
cookie-wrapped response channel of an admitted submission. The router forwards that submission.
"""

from __future__ import annotations

from starlette.responses import JSONResponse
from starlette.types import Receive, Scope, Send

from course_explorer.config import FeedbackIntakeSettings
from course_explorer.http_headers import header_values
from course_explorer_web.admission.identity import cookie_send, identify, set_cookie_value
from course_explorer_web.feedback_intake import FeedbackIntake, require_feedback_site
from course_explorer_web.request_body import RequestRefused, read_body


def feedback_refusal(refusal: RequestRefused) -> JSONResponse:
    """Return the fixed non-cacheable feedback refusal with its retry delay."""
    headers = {"Cache-Control": "no-store"}
    if refusal.retry_after_seconds is not None:
        headers["Retry-After"] = str(refusal.retry_after_seconds)
    return JSONResponse(
        {"detail": "Feedback request refused"},
        status_code=refusal.status_code,
        headers=headers,
    )


def require_content_type(scope: Scope) -> None:
    """Require one JSON media type with any parameters, or refuse the request with 415."""
    values = header_values(scope.get("headers", ()), b"content-type")
    if len(values) != 1:
        raise RequestRefused(415)
    media_type = values[0].decode("latin-1").split(";", 1)[0].strip().lower()
    if media_type != "application/json":
        raise RequestRefused(415)


def require_declared_length(scope: Scope, *, max_bytes: int) -> None:
    """Refuse a malformed or repeated declared length with 400 and one over the bound with 413."""
    values = header_values(scope.get("headers", ()), b"content-length")
    if not values:
        return
    if len(values) != 1:
        raise RequestRefused(400)
    declared = values[0].decode("latin-1").strip()
    if not declared.isascii() or not declared.isdigit():
        raise RequestRefused(400)
    if int(declared) > max_bytes:
        raise RequestRefused(413)


async def read_submission(
    scope: Scope,
    receive: Receive,
    send: Send,
    *,
    settings: FeedbackIntakeSettings,
    intake: FeedbackIntake,
    cookie_max_age_seconds: int,
) -> tuple[str, bytes, Send] | None:
    """Return one admitted submission's cookie, body and channel, or answer its refusal.

    A site, media-type or declared-length refusal answers before any identity exists. The request
    body is read under the configured byte bound after the attempt is charged to the feedback
    allowance, so a refused or failed body spends its charge.
    """
    try:
        require_feedback_site(scope, settings)
        require_content_type(scope)
        require_declared_length(scope, max_bytes=settings.feedback_max_request_bytes)
    except RequestRefused as refusal:
        await feedback_refusal(refusal)(scope, receive, send)
        return None
    cookie = identify(scope)
    response_send = cookie_send(send, set_cookie_value(cookie, cookie_max_age_seconds))
    try:
        intake.admit(cookie)
        body = await read_body(receive, max_bytes=settings.feedback_max_request_bytes)
    except RequestRefused as refusal:
        await feedback_refusal(refusal)(scope, receive, response_send)
        return None
    return cookie, body, response_send
