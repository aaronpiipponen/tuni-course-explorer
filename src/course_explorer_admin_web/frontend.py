"""The console's built shell and built assets of the administration backend.

``/`` answers the built ``index.html``, which names the hashed files of one frontend build, and
``/assets`` is a mount over the build's assets directory. Admission admits these read-only
addresses without a session. A build that is absent fails when it is requested.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from starlette.responses import FileResponse
from starlette.staticfiles import StaticFiles

from course_explorer_admin_web.routes.auth import NO_STORE_HEADERS

# The one shell document and the build-owned assets directory of a console build.
SHELL_FILENAME = "index.html"
ASSETS_DIRNAME = "assets"

SHELL_PATH = "/"
ASSETS_MOUNT = "/assets"


def register_frontend(application: FastAPI, *, dist_directory: Path) -> None:
    """Register the console shell and its assets directory from one built output directory.

    The shell answers GET and HEAD with the build's ``index.html`` and no-store caching. The assets
    mount serves the built files beneath ``assets`` and refuses symlinked entries, so a file miss
    reaches the mount's own 404. Both register with the same admission rules as every other address.
    """

    async def shell() -> FileResponse:
        """Return the built console shell with no-store caching."""
        return FileResponse(
            dist_directory / SHELL_FILENAME, media_type="text/html", headers=NO_STORE_HEADERS
        )

    application.add_api_route(SHELL_PATH, shell, methods=["GET", "HEAD"], include_in_schema=False)
    application.mount(
        ASSETS_MOUNT, StaticFiles(directory=dist_directory / ASSETS_DIRNAME, check_dir=False)
    )
