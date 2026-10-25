"""The front router's worker selection and its per-worker in-flight accounting."""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator


class WorkerPool:
    """The in-flight requests of every worker and the choice of one worker for each request.

    Selection and increment run in one event-loop turn, so the counts need no lock. A heavy request
    is placed only on a worker that carries no other heavy request.
    """

    def __init__(self, addresses: tuple[tuple[str, int], ...]) -> None:
        self._addresses = addresses
        self._in_flight = {address: 0 for address in addresses}
        self._heavy = {address: 0 for address in addresses}

    def choose(self, *, heavy: bool) -> tuple[str, int]:
        """Return the index-stable least-busy worker that may carry the request.

        A heavy request excludes a worker with a heavy request in flight. Equal counts pick the
        lower index. A heavy request with no eligible worker raises ``RuntimeError``.
        """
        candidates = [
            address for address in self._addresses if not heavy or self._heavy[address] == 0
        ]
        if not candidates:
            raise RuntimeError("no worker is free of heavy requests")
        return candidates[
            min(range(len(candidates)), key=lambda index: self._in_flight[candidates[index]])
        ]

    @contextlib.asynccontextmanager
    async def occupy(self, address: tuple[str, int], *, heavy: bool) -> AsyncIterator[None]:
        """Count one request against a worker for the duration of the forwarding."""
        self._in_flight[address] += 1
        if heavy:
            self._heavy[address] += 1
        try:
            yield
        finally:
            self._in_flight[address] -= 1
            if heavy:
                self._heavy[address] -= 1
