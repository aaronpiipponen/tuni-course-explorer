"""The front router: one loopback listener that admits each request and forwards it to one worker.

The router owns the anonymous cookie, the request classification, the light and heavy limits, the
heavy queue and placement, the load score meter, the graph elapsed cost and the one usage
record. It has one forwarding path with no retry and no fallback: a worker connection failure raises
and answers a server error. The supervisor replaces an exited router or worker on its own socket.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from dataclasses import dataclass

import httpx
from fastapi.responses import JSONResponse
from starlette.types import Message, Receive, Scope, Send

from course_explorer.config import AdmissionSettings, load_admission_settings
from course_explorer_web.admission import host_cpu
from course_explorer_web.admission.classify import AdmissionClass, Classification, classify
from course_explorer_web.admission.graph_cost import graph_cost_field
from course_explorer_web.admission.identity import identify, set_cookie_value
from course_explorer_web.admission.state import AdmissionRefused, AdmissionState
from course_explorer_web.dataset import ServingDataset, resolve_serving_dataset
from course_explorer_web.router.usage import UsageMiddleware
from course_explorer_web.router.workers import WorkerPool
from course_explorer_web.serving import MEASURE_GRAPH_HEADER, Route, route_of

logger = logging.getLogger(__name__)

_SAMPLE_SECONDS = 1.0
_HOP_BY_HOP_HEADERS = frozenset(
    {
        b"connection",
        b"keep-alive",
        b"proxy-authenticate",
        b"proxy-authorization",
        b"te",
        b"trailer",
        b"transfer-encoding",
        b"upgrade",
    }
)
_MEASURED_HEADER = MEASURE_GRAPH_HEADER.encode("latin-1")


@dataclass(frozen=True)
class _Admission:
    """One admitted request: its cookie identity, its heavy flag, its heavy ticket, its serving
    dataset, its graph-cost key and its response channel."""

    cookie: str
    heavy: bool
    ticket: str | None
    serving: ServingDataset | None
    field: str | None
    response_send: Send


class RouterApplication:
    """The pure ASGI front router over a fixed set of loopback worker addresses.

    ``state`` is the admission state after startup, and it stays ``None`` while admission is off.
    The application owns one sampler task and one HTTP client for its lifetime.
    """

    def __init__(
        self,
        *,
        workers: tuple[tuple[str, int], ...],
        settings: AdmissionSettings | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._workers = WorkerPool(workers)
        self._settings = settings
        self._client = client
        self._sampler: asyncio.Task[None] | None = None
        self._usage = UsageMiddleware(self._handle_http)
        self.state: AdmissionState | None = None

    async def startup(self) -> None:
        """Load the policy, build the admission state and start the load sampler.

        Admission off reads no core count and starts no sampler. A host that reports no core count
        raises, so a site cannot admit requests against an unknown capacity.
        """
        settings = self._settings or load_admission_settings()
        self._settings = settings
        if settings.admission_enabled:
            self.state = AdmissionState(settings, host_cpu.core_count())
            self._sampler = asyncio.create_task(self._sample_loop())
        if self._client is None:
            # A worker's uvicorn expires an idle connection at five seconds while the pool would
            # hold one, so every forwarded request opens a fresh loopback connection and the router
            # never reuses one a worker has closed.
            self._client = httpx.AsyncClient(
                timeout=None, limits=httpx.Limits(max_keepalive_connections=0)
            )

    async def shutdown(self) -> None:
        """Stop the sampler and close the HTTP client."""
        if self._sampler is not None:
            self._sampler.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._sampler
            self._sampler = None
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def sample_once(self) -> None:
        """Sample the host's busy CPU once, or treat an unreadable counter as unloaded.

        The sample adds one host CPU interval and refreshes the score position from the host CPU and
        the light and heavy activity in the window. An unreadable counter logs one content-free
        error and resets the meter to its unloaded state, so the next good sample stores zero
        instead of the outage and counts the activity already admitted.
        """
        if self.state is None:
            return
        try:
            busy = host_cpu.busy_cpu_seconds()
        except OSError:
            logger.error("the host CPU counter could not be read; treating the site as unloaded")
            self.state.reset_meter()
            return
        self.state.sample(busy, int(time.time()))

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Serve one ASGI call: the lifespan, a refused websocket or one recorded HTTP request."""
        if scope["type"] == "lifespan":
            await self._lifespan(receive, send)
            return
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return
        if scope["type"] != "http":
            return
        await self._usage(scope, receive, send)

    async def _lifespan(self, receive: Receive, send: Send) -> None:
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                try:
                    await self.startup()
                except Exception as error:
                    await send({"type": "lifespan.startup.failed", "message": str(error)})
                    return
                await send({"type": "lifespan.startup.complete"})
            elif message["type"] == "lifespan.shutdown":
                await self.shutdown()
                await send({"type": "lifespan.shutdown.complete"})
                return

    async def _sample_loop(self) -> None:
        """Sample once a second and expire idle identities once per identity lifetime."""
        next_expiry = time.time() + self._settings.admission_identity_ttl_seconds
        while True:
            await asyncio.sleep(_SAMPLE_SECONDS)
            await self.sample_once()
            now = time.time()
            if now >= next_expiry:
                self.state.expire(int(now))
                next_expiry = now + self._settings.admission_identity_ttl_seconds

    async def _handle_http(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Read one request body, admit the request and forward it to one worker."""
        if self._settings is None:
            raise RuntimeError("the front router is not started")
        if self._client is None:
            raise RuntimeError("the front router is not started")
        body = await _read_body(receive)
        admission = await self._admit(scope, receive, body, send)
        if admission is None:
            return
        await self._forward(scope, body, admission)

    async def _admit(
        self, scope: Scope, receive: Receive, body: bytes, send: Send
    ) -> _Admission | None:
        """Take the request's ticket and graph cost, or send the fixed refusal and return ``None``.

        A refused request is answered through the cookie-wrapped channel, so the refusal carries the
        same identity headers as a served response.
        """
        settings = self._settings
        enabled = settings.admission_enabled
        cookie = ""
        response_send = send
        if enabled and scope["path"].startswith("/api/"):
            cookie = identify(scope)
            response_send = _cookie_send(
                send, set_cookie_value(cookie, settings.admission_cookie_max_age_seconds)
            )
        classification: Classification | None = None
        serving: ServingDataset | None = None
        field: str | None = None
        route = route_of(scope["path"]) if scope["method"] == "POST" else None
        if enabled and route is not None:
            parsed = _request_body(body)
            if route is Route.PREREQUISITES:
                serving = await asyncio.to_thread(resolve_serving_dataset)
                field = graph_cost_field(parsed)
                classification = classify(
                    route,
                    parsed,
                    settings,
                    graph_cost=self.state.graph_cost(serving.identity, field),
                )
            else:
                classification = classify(route, parsed, settings)
        heavy = (
            classification is not None and classification.admission_class is AdmissionClass.HEAVY
        )
        ticket: str | None = None
        if classification is not None and classification.admission_class is not AdmissionClass.FREE:
            try:
                if heavy:
                    ticket = await self.state.admit_heavy(cookie, classification)
                else:
                    ticket = self.state.admit_light(cookie)
            except AdmissionRefused:
                await _too_much_traffic(settings)(scope, receive, response_send)
                return None
        return _Admission(cookie, heavy, ticket, serving, field, response_send)

    async def _forward(self, scope: Scope, body: bytes, admission: _Admission) -> None:
        """Forward one admitted request to one worker, record its graph cost and release its ticket.

        The handler has checked that the router is started, so the client is present. The admission
        state is present for an admission that carries a ticket or a graph cost.
        """
        address = self._workers.choose(heavy=admission.heavy)
        try:
            async with self._workers.occupy(address, heavy=admission.heavy):
                started = time.monotonic()
                response = await self._client.send(
                    _worker_request(address, scope, body), stream=True
                )
                try:
                    measured = (
                        admission.serving is not None
                        and admission.field is not None
                        and response.headers.get(MEASURE_GRAPH_HEADER) == "1"
                    )
                    await admission.response_send(
                        {
                            "type": "http.response.start",
                            "status": response.status_code,
                            "headers": _response_headers(response),
                        }
                    )
                    async for chunk in response.aiter_raw():
                        await admission.response_send(
                            {"type": "http.response.body", "body": chunk, "more_body": True}
                        )
                    await admission.response_send(
                        {"type": "http.response.body", "body": b"", "more_body": False}
                    )
                finally:
                    await response.aclose()
                if measured:
                    self.state.record_graph_cost(
                        admission.serving.identity,
                        admission.field,
                        time.monotonic() - started,
                    )
        finally:
            if admission.ticket is not None:
                if admission.heavy:
                    await self.state.release_heavy(admission.ticket)
                else:
                    self.state.release_light(admission.cookie, admission.ticket)


def create_router(
    *,
    workers: tuple[tuple[str, int], ...],
    settings: AdmissionSettings | None = None,
    client: httpx.AsyncClient | None = None,
) -> RouterApplication:
    """Build the one front router over the given loopback worker addresses."""
    return RouterApplication(workers=workers, settings=settings, client=client)


def _worker_request(address: tuple[str, int], scope: Scope, body: bytes) -> httpx.Request:
    """Build one buffered request for a worker from the router's scope."""
    host, port = address
    target = f"http://{host}:{port}{scope['raw_path'].decode('latin-1')}"
    query = scope["query_string"].decode("latin-1")
    if query:
        target = f"{target}?{query}"
    headers = [
        (name, value) for name, value in scope["headers"] if name.lower() not in _HOP_BY_HOP_HEADERS
    ]
    return httpx.Request(scope["method"], target, headers=headers, content=body)


def _response_headers(response: httpx.Response) -> list[tuple[bytes, bytes]]:
    """Return the worker's response headers without the hop-by-hop set or the graph marker."""
    return [
        (name, value)
        for name, value in response.headers.raw
        if name.lower() not in _HOP_BY_HOP_HEADERS and name.lower() != _MEASURED_HEADER
    ]


async def _read_body(receive: Receive) -> bytes:
    """Read the whole buffered request body from the receive channel."""
    chunks: list[bytes] = []
    while True:
        message = await receive()
        chunks.append(message.get("body", b""))
        if not message.get("more_body", False):
            return b"".join(chunks)


def _request_body(raw: bytes) -> dict[str, object]:
    """Return a JSON object body, or an empty mapping for any other payload.

    A non-object or unparseable body takes the route's request defaults, so an unparseable search
    body reads inactive courses and is charged heavy while the route's own validation answers it.
    """
    try:
        parsed = json.loads(raw)
    except UnicodeDecodeError, json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _cookie_send(send: Send, cookie: bytes) -> Send:
    """Return a send channel that adds one ``set-cookie`` header to every response start."""

    async def send_with_cookie(message: Message) -> None:
        if message["type"] == "http.response.start":
            message = {
                **message,
                "headers": [*message.get("headers", []), (b"set-cookie", cookie)],
            }
        await send(message)

    return send_with_cookie


def _too_much_traffic(settings: AdmissionSettings) -> JSONResponse:
    """Return the fixed refusal response with its retry delay."""
    return JSONResponse(
        {"detail": "Too much traffic"},
        status_code=429,
        headers={"Retry-After": str(settings.admission_retry_after_seconds)},
    )
