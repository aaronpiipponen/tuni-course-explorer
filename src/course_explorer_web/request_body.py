"""Read one buffered request body at the front router under its byte bound.

The reader serves both the ordinary request path and the feedback submission path. A crossing chunk
raises 413 before it is appended or another chunk is read, so a declared length and a chunked body
reach the same byte ceiling. A client disconnect inside the read raises 400 and forwards no partial
body.
"""

from __future__ import annotations

from starlette.types import Receive


class RequestRefused(Exception):
    """One refused front request with the status it answers and its optional retry delay.

    The error carries no request input, body or identity, so a handler can answer it without
    rendering any part of the request.
    """

    def __init__(self, status_code: int, *, retry_after_seconds: int | None = None) -> None:
        super().__init__(f"request refused with status {status_code}")
        self.status_code = status_code
        self.retry_after_seconds = retry_after_seconds


async def read_body(receive: Receive, *, max_bytes: int) -> bytes:
    """Read the whole buffered request body from the receive channel under its byte bound."""
    chunks: list[bytes] = []
    total = 0
    while True:
        message = await receive()
        if message["type"] == "http.disconnect":
            raise RequestRefused(400)
        chunk = message.get("body", b"")
        total += len(chunk)
        if total > max_bytes:
            raise RequestRefused(413)
        chunks.append(chunk)
        if not message.get("more_body", False):
            return b"".join(chunks)
