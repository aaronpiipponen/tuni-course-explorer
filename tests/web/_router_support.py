"""One recording worker boundary and the shared request bodies and wait helper."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable
from dataclasses import dataclass

import httpx
from starlette.types import ASGIApp, Receive, Scope, Send

_PORT_BASE = 19001
_WORKERS = 4


def search_body(*, include_inactive: bool = False) -> dict[str, object]:
    """Return one unified-search request body for the given inactive-courses flag."""
    return {"query": "analysis", "display_language": "en", "include_inactive": include_inactive}


def recommendation_body(count: int, *, active_only: bool = True) -> dict[str, object]:
    """Return one completed-basis recommendation body over the given number of courses."""
    return {
        "active_only": active_only,
        "basis": "completed",
        "completed_courses": [f"c{index}" for index in range(count)],
        "display_language": "en",
        "include_inferred": False,
        "mode": "all",
        "selected_courses": [],
    }


async def wait_for(predicate: Callable[[], bool]) -> None:
    """Wait for one router state predicate to hold, and fail when it does not arrive."""
    for _ in range(500):
        if predicate():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("the expected router state did not arrive")


@dataclass
class RecordedCall:
    """One forwarded worker call: its worker, its path and its start and end."""

    worker: int
    path: str
    started: float
    finished: float | None = None


class WorkerHarness:
    """Route a router's forwarded requests to four recording worker applications.

    ``apps`` supplies one ASGI application per worker, and a worker without one answers ``200``
    with its own index. Every call records the worker, the path and its start and end. ``hold``
    keeps every reply waiting until ``release``.
    """

    def __init__(self, apps: tuple[ASGIApp | None, ...] = ()) -> None:
        self.ports = tuple(_PORT_BASE + index for index in range(_WORKERS))
        self._apps = {
            index: (
                apps[index]
                if index < len(apps) and apps[index] is not None
                else _default_worker(index)
            )
            for index in range(_WORKERS)
        }
        self._hold: asyncio.Event | None = None
        self.calls: list[RecordedCall] = []
        self._transports = {
            index: httpx.ASGITransport(app=_HeldApp(self, index), raise_app_exceptions=False)
            for index in range(_WORKERS)
        }

    @property
    def addresses(self) -> tuple[tuple[str, int], ...]:
        """Return the four worker addresses in index order."""
        return tuple(("127.0.0.1", port) for port in self.ports)

    def hold(self) -> None:
        """Make every reply wait until ``release``."""
        self._hold = asyncio.Event()

    def release(self) -> None:
        """Release every reply held on the current event."""
        if self._hold is None:
            raise RuntimeError("no reply is held")
        self._hold.set()

    def client(self, base_url: str = "http://router") -> httpx.AsyncClient:
        """Return one client whose transport routes a request by its port."""
        return httpx.AsyncClient(transport=_RoutingTransport(self), base_url=base_url)

    def worker(self, request: httpx.Request) -> int:
        """Return the worker index of one request's port, or raise a connection error."""
        try:
            return self.ports.index(request.url.port)
        except ValueError:
            raise httpx.ConnectError(f"no worker listens on port {request.url.port}") from None

    async def serve(self, index: int, scope: Scope, receive: Receive, send: Send) -> None:
        """Serve one worker call after the current hold, when one is set."""
        if self._hold is not None:
            await self._hold.wait()
        await self._apps[index](scope, receive, send)


class _HeldApp:
    """Pass one worker's calls through the harness hold."""

    def __init__(self, harness: WorkerHarness, index: int) -> None:
        self._harness = harness
        self._index = index

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await self._harness.serve(self._index, scope, receive, send)


class _RoutingTransport(httpx.AsyncBaseTransport):
    """Route one client call to the worker of its URL port and record it."""

    def __init__(self, harness: WorkerHarness) -> None:
        self._harness = harness

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        index = self._harness.worker(request)
        call = RecordedCall(index, request.url.path, time.monotonic())
        self._harness.calls.append(call)
        try:
            return await self._harness._transports[index].handle_async_request(request)
        finally:
            call.finished = time.monotonic()


def _default_worker(index: int) -> ASGIApp:
    """Return one worker application that reports its own index."""

    async def worker(scope: Scope, receive: Receive, send: Send) -> None:
        body = json.dumps({"worker": index}).encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode("ascii")),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})

    return worker
