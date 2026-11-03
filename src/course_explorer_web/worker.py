"""Serve the worker application on the loopback socket and readiness pipe the supervisor passes it."""

from __future__ import annotations

import os
import socket

import uvicorn


class _ReadyServer(uvicorn.Server):
    """Report a completed Uvicorn startup to the supervisor over an inherited pipe."""

    def __init__(self, config: uvicorn.Config, readiness_fd: int) -> None:
        super().__init__(config)
        self._readiness_fd = readiness_fd

    async def startup(self, sockets: list[socket.socket] | None = None) -> None:
        """Complete startup, then write one readiness byte and release the pipe.

        Uvicorn exits or raises on a failed startup, so a returning call has completed startup.
        """
        await super().startup(sockets=sockets)
        # One byte on the inherited pipe is the supervisor's completed-startup protocol.
        os.write(self._readiness_fd, b"1")
        os.close(self._readiness_fd)


def main(*, listener_fd: int, readiness_fd: int) -> None:
    """Serve the worker application on one inherited loopback socket."""
    server = _ReadyServer(
        uvicorn.Config("course_explorer_web.app:app", fd=listener_fd, access_log=False),
        readiness_fd,
    )
    server.run()
