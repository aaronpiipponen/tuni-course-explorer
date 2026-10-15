"""Configured loopback-only uvicorn entry point for the read-only web API."""

import socket

import uvicorn

from course_explorer.config import load_web_settings


def main() -> None:
    """Serve with configured processes sharing one owned loopback TCP socket."""
    settings = load_web_settings()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP) as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # Uvicorn's inherited-socket path does not enable NODELAY through asyncio here.
        listener.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        listener.bind((settings.web_host, settings.web_port))
        uvicorn.run(
            "course_explorer_web.app:app",
            host=settings.web_host,
            port=settings.web_port,
            fd=listener.fileno(),
            workers=settings.web_workers,
            access_log=False,
        )


if __name__ == "__main__":
    main()
