"""Configured loopback-only single-process uvicorn entry point for the administration backend."""

import uvicorn

from course_explorer.config import load_admin_web_settings
from course_explorer_admin_web.app import create_app


def main() -> None:
    """Serve the administration application on its configured loopback bind.

    One process is fixed, because it owns the in-memory sessions. The process starts one thread's
    event loop and one uvicorn worker, logs no access line and trusts no proxy header.
    """
    settings = load_admin_web_settings()
    uvicorn.run(
        create_app(settings=settings),
        host=settings.admin_web_host,
        port=settings.admin_web_port,
        workers=1,
        access_log=False,
        proxy_headers=False,
    )


if __name__ == "__main__":
    main()
