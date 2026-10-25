"""Serve the front router on the public file descriptor the supervisor passes it."""

from __future__ import annotations

import sys

import uvicorn

from course_explorer.config import load_web_settings
from course_explorer_web.router import ROUTER_SHUTDOWN_SECONDS
from course_explorer_web.router.app import create_router


def main() -> None:
    """Build the router over the worker ports and serve the inherited public socket."""
    public_fd = int(sys.argv[1])
    ports = sys.argv[2:]
    settings = load_web_settings()
    application = create_router(workers=tuple((settings.web_host, int(port)) for port in ports))
    uvicorn.run(
        application,
        fd=public_fd,
        access_log=False,
        timeout_graceful_shutdown=ROUTER_SHUTDOWN_SECONDS,
    )


if __name__ == "__main__":
    main()
