"""Pure ASGI middleware appending one content-free usage record per HTTP request."""

from __future__ import annotations

import time

from starlette.concurrency import run_in_threadpool
from starlette.staticfiles import StaticFiles
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from course_explorer.administration import utc_now
from course_explorer.usage import append_usage_record, rounded_usage_hour

_ASSET_ROUTE = "/assets"
_UNMATCHED_ROUTE = "unmatched"


class UsageMiddleware:
    """Append one usage record for every HTTP request after the inner application finishes.

    A non-HTTP scope passes through unchanged. The recorded status starts at 500 and is replaced
    by the inner response's own start status, so an unhandled failure records a 500 outcome. The
    append runs in a worker thread, so a report holding the usage file's lock cannot block the
    serving event loop, and application failures keep propagating to the caller.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        hour = rounded_usage_hour(utc_now())
        started = time.perf_counter()
        status = 500

        async def observe_response(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, observe_response)
        finally:
            await run_in_threadpool(
                append_usage_record,
                hour=hour,
                route=_route_label(scope),
                status=status,
                duration_seconds=time.perf_counter() - started,
            )


def _route_label(scope: Scope) -> str:
    """Return one request's fixed route label from its final trusted routing metadata.

    A matched route contributes its own fixed path, so a shell read, an API read and a method
    mismatch all report that path. The mounted asset directory reports one fixed label for a served
    file and a missing one alike. Every other request reports the unmatched label, so no requested
    path, asset name or query is ever part of the label.
    """
    route = scope.get("route")
    if route is not None:
        return route.path
    if isinstance(scope.get("endpoint"), StaticFiles):
        return _ASSET_ROUTE
    return _UNMATCHED_ROUTE
