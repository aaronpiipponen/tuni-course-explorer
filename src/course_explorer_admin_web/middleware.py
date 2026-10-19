"""Pure ASGI admission middleware of the administration backend.

Every HTTP request passes one fixed order: the durable lock, the exact Host and Origin boundary, the
session requirement of its address, the server-wide budget of a fresh anonymous session, the CSRF
token of every state-changing method, and the refresh of the admitted session's own idle clock. An
admitted request carries that refreshed session in ``scope["state"]["admin_session"]``.

The built console shell and its built assets are the one address that needs no session: a GET or
HEAD of ``/`` or of a path beneath ``/assets/`` is admitted after the lock and site checks and before
any cookie is read, so it creates no session, executes no command and records nothing. Every other
address, a POST of a static path included, uses the ordinary session and CSRF flow.

The middleware holds no route table of its own: a refusal answers before any handler runs, and an
admitted unknown address reaches the router's ordinary 404 or 405.
"""

from __future__ import annotations

import json
import secrets
from collections.abc import Iterable
from urllib.parse import urlsplit

from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from starlette.requests import cookie_parser
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from course_explorer.config import AdminWebSettings
from course_explorer_admin.commands import format_operator_error
from course_explorer_admin_web.security import (
    SESSION_COOKIE_NAME,
    AdminSecurity,
    AnonymousSessionRateLimited,
)

# The session address, which reuses or creates the session of its cookie, and the login address, which
# needs one live session of any kind because it carries that session's CSRF token.
SESSION_PATH = "/auth/session"
LOGIN_PATH = "/auth/login"

# Methods that change no state, so they need no CSRF token.
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

# The one static admission exception: the built console shell and the built assets beneath its
# assets directory. A mounted-file miss keeps the mount's own 404 rather than falling back to
# another directory or to the shell.
SHELL_PATH = "/"
ASSETS_PREFIX = "/assets/"

# Methods the static exception admits. A state-changing method of the same path keeps its session.
STATIC_METHODS = frozenset({"GET", "HEAD"})

_CSRF_HEADER = b"x-csrf-token"
_WEBSOCKET_POLICY_VIOLATION = 1008


class AdminAdmissionMiddleware:
    """Admit one administration request before any handler, or answer a fixed refusal.

    The lock refusal is a bare empty 403. A site-boundary refusal is 403, and a missing authenticated
    session is 401. A fresh anonymous session beyond the server-wide budget is an empty 429 with
    ``Cache-Control: no-store`` and an integer ``Retry-After`` in seconds. No refusal names a reason,
    a file or a header. An operational failure answers one content-free JSON 500 naming the exception
    class, and a failure after the response started raises a content-free ``RuntimeError`` instead of
    exposing a payload.
    """

    def __init__(
        self, app: ASGIApp, *, security: AdminSecurity, settings: AdminWebSettings
    ) -> None:
        self.app = app
        self._security = security
        self._settings = settings
        # The proxy connects to this backend by plain HTTP, so the request's own transport scheme is
        # not compared to the configured HTTPS origin. The Host header is.
        self._netloc = urlsplit(settings.admin_web_origin).netloc

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "lifespan":
            await self.app(scope, receive, send)
            return
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": _WEBSOCKET_POLICY_VIOLATION})
            return
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = False

        async def observe(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            refusal = await self._refusal(scope)
            if refusal is not None:
                await refusal(scope, receive, send)
                return
            await self.app(scope, receive, observe)
        except Exception as exc:
            if started:
                raise RuntimeError("administration response failed") from None
            await _failure_response(exc)(scope, receive, send)

    async def _refusal(self, scope: Scope) -> Response | None:
        """Return one fixed refusal for this request, or admit it and return ``None``.

        The admission order is the lock, the exact Host and Origin, the static shell and asset
        exception of a read-only method, the session requirement of the address, the CSRF boundary
        of a state-changing method, and the idle-clock refresh of the admitted session alone.

        The session address takes one slot of the server-wide fresh anonymous session budget only
        when it must create a grant. A live cookie takes none, and a refusal at the spent budget
        takes none. A static shell or asset request is admitted before its cookie is read, so it
        neither creates nor touches a session and executes no command.
        """
        if await run_in_threadpool(self._security.is_locked):
            return Response(status_code=403)
        headers = scope.get("headers", ())
        hosts = _header_values(headers, b"host")
        if len(hosts) != 1 or hosts[0].decode("latin-1").strip() != self._netloc:
            return Response(status_code=403)
        origins = _header_values(headers, b"origin")
        if len(origins) > 1:
            return Response(status_code=403)
        supplied_origin = origins[0].decode("latin-1") if origins else None
        if supplied_origin is not None and supplied_origin != self._settings.admin_web_origin:
            return Response(status_code=403)
        method = scope.get("method", "GET").upper()
        state_changing = method not in SAFE_METHODS
        if state_changing and supplied_origin is None:
            return Response(status_code=403)
        path = scope.get("path", "")
        if _static_shell_request(method, path):
            return None
        cookie = _session_cookie(headers)
        if method == "GET" and path == SESSION_PATH:
            try:
                grant = await run_in_threadpool(self._security.bootstrap, cookie)
            except AnonymousSessionRateLimited as exc:
                return Response(
                    status_code=429,
                    headers={
                        "Cache-Control": "no-store",
                        "Retry-After": str(exc.retry_after_seconds),
                    },
                )
        else:
            grant = await run_in_threadpool(self._security.resolve, cookie)
            login_request = method == "POST" and path == LOGIN_PATH
            if grant is None:
                # A login carries its CSRF token on the live session it already holds, so a login
                # without one is refused at the site boundary like the missing-token case.
                return Response(status_code=403 if login_request else 401)
            if not grant.authenticated and not login_request:
                return Response(status_code=401)
            if state_changing and not _csrf_matches(headers, grant.csrf_token):
                return Response(status_code=403)
        admitted = await run_in_threadpool(self._security.touch, grant.token)
        if admitted is None:
            return Response(status_code=401)
        scope.setdefault("state", {})["admin_session"] = admitted
        return None


def _header_values(headers: Iterable[tuple[bytes, bytes]], name: bytes) -> list[bytes]:
    """Return every value of one request header, preserving duplicates and their order."""
    return [value for key, value in headers if key.lower() == name]


def _static_shell_request(method: str, path: str) -> bool:
    """Report whether one request is a read-only console shell or built-asset request."""
    if method not in STATIC_METHODS:
        return False
    return path == SHELL_PATH or path.startswith(ASSETS_PREFIX)


def _session_cookie(headers: Iterable[tuple[bytes, bytes]]) -> str | None:
    """Return this site's session cookie of the request, or ``None`` when it carries none."""
    raw = _header_values(headers, b"cookie")
    if not raw:
        return None
    cookies = cookie_parser(raw[0].decode("latin-1"))
    return cookies.get(SESSION_COOKIE_NAME)


def _csrf_matches(headers: Iterable[tuple[bytes, bytes]], expected: str) -> bool:
    """Report whether the request carries exactly one matching CSRF token header.

    The supplied header bytes compare directly with the ASCII token, so a non-ASCII value is a
    mismatch rather than a decoding failure.
    """
    supplied = _header_values(headers, _CSRF_HEADER)
    if len(supplied) != 1:
        return False
    return secrets.compare_digest(supplied[0], expected.encode("ascii"))


def _failure_response(exc: Exception) -> JSONResponse:
    """Return one content-free non-cacheable JSON 500 naming the exception class alone.

    The no-store header matches the authentication answers, so a proxy and a browser store no part
    of an operational failure while serving authentication.
    """
    payload = json.loads(format_operator_error(exc))
    return JSONResponse(
        status_code=500,
        content={"error": payload["error"]},
        headers={"Cache-Control": "no-store"},
    )
