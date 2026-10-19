"""The three authentication routes of the administration backend.

They report the site's session state, verify one login credential, and end one session on the server.
The session route reports the session admitted into the request state. Login and logout delegate
to the security owner. Every answer carries ``Cache-Control: no-store``.
"""

from __future__ import annotations

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, SecretStr

from course_explorer.config import AdminWebSettings
from course_explorer_admin_web.security import SESSION_COOKIE_NAME, AdminSecurity, SessionGrant

router = APIRouter()

# The protected cookie attributes: this exact site, secure transport, no script access, strict
# same-site policy and no persistent max-age, because the server enforces the session lifetime.
_COOKIE_ATTRIBUTES: dict[str, object] = {
    "path": "/",
    "secure": True,
    "httponly": True,
    "samesite": "strict",
}

# Every answer of the authentication surface is non-cacheable, the fixed request-validation failure
# included, so a proxy and a browser store no part of it.
NO_STORE_HEADERS: dict[str, str] = {"Cache-Control": "no-store"}


class LoginRequest(BaseModel):
    """One login attempt: the site's username and the password it presents."""

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    username: str
    password: SecretStr


class LogoutRequest(BaseModel):
    """The empty body of one logout request, so a body with any field is refused."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class SessionReport(BaseModel):
    """The public facts of one session and the console presentation metadata.

    ``poll_seconds`` is the interval the console waits between completed panel reads, ``app_url`` is
    the address its App link points at, and ``repository_url`` is the address its GitHub link opens.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    authenticated: bool
    csrf_token: str
    username: str | None
    poll_seconds: int
    app_url: str
    repository_url: str


def _security(request: Request) -> AdminSecurity:
    """Return the one security owner of the running application."""
    return request.app.state.security


def _report(grant: SessionGrant, settings: AdminWebSettings) -> SessionReport:
    """Return one session grant's public report with the site's presentation metadata."""
    return SessionReport(
        authenticated=grant.authenticated,
        csrf_token=grant.csrf_token,
        username=grant.username,
        poll_seconds=settings.admin_web_poll_seconds,
        app_url=settings.admin_web_app_url,
        repository_url=settings.admin_web_repository_url,
    )


@router.get("/auth/session")
def session(request: Request, response: Response) -> SessionReport:
    """Report the request's own session, issuing the cookie of a session it creates."""
    grant: SessionGrant = request.state.admin_session
    if request.cookies.get(SESSION_COOKIE_NAME) != grant.token:
        response.set_cookie(SESSION_COOKIE_NAME, grant.token, **_COOKIE_ATTRIBUTES)
    response.headers.update(NO_STORE_HEADERS)
    return _report(grant, request.app.state.settings)


@router.post("/auth/login")
def login(request: Request, response: Response, body: LoginRequest) -> Response:
    """Verify one credential attempt and answer with the session report or a fixed refusal.

    A failed credential answers a safe 401. The attempt that creates the site's lock answers an empty
    403 immediately, because the site is locked rather than the credential being wrong. A granted
    session rotates the cookie to its fresh server-side token.
    """
    security = _security(request)
    grant = security.login(
        request.cookies.get(SESSION_COOKIE_NAME), username=body.username, password=body.password
    )
    if grant is None:
        if security.is_locked():
            return Response(status_code=403, headers=NO_STORE_HEADERS)
        return JSONResponse(
            status_code=401, content={"detail": "Authentication failed"}, headers=NO_STORE_HEADERS
        )
    response.set_cookie(SESSION_COOKIE_NAME, grant.token, **_COOKIE_ATTRIBUTES)
    response.headers.update(NO_STORE_HEADERS)
    return _report(grant, request.app.state.settings)


@router.post("/auth/logout")
def logout(request: Request, response: Response, body: LogoutRequest) -> Response:
    """End the request's own session on the server and delete its cookie."""
    grant: SessionGrant = request.state.admin_session
    _security(request).logout(grant.token)
    response.delete_cookie(SESSION_COOKIE_NAME, **_COOKIE_ATTRIBUTES)
    response.status_code = 204
    response.headers.update(NO_STORE_HEADERS)
    return response
