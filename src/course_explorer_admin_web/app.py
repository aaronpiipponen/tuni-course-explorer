"""Compose the authenticated administration application over the fixed security owners.

The application serves the authentication routes, the built console shell and its assets, and the
five feature routers of the console. It registers the admission middleware outside every route, so
the lock, the exact-site boundary, the CSRF boundary and the session requirement apply to every
address, an unknown one included. The built shell and its assets are the one read-only exception.
Construction reads the configured settings, builds one security owner and one fixed-command runner,
and creates no file.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from course_explorer.administration import repository_root, utc_now
from course_explorer.config import AdminWebSettings, load_admin_web_settings
from course_explorer_admin.mechanics import ProcessRunner
from course_explorer_admin_web.frontend import register_frontend
from course_explorer_admin_web.middleware import AdminAdmissionMiddleware
from course_explorer_admin_web.routes import (
    auth,
    dashboard,
    inference,
    logs,
    preparation,
)
from course_explorer_admin_web.routes import (
    settings as settings_routes,
)
from course_explorer_admin_web.routes.auth import NO_STORE_HEADERS
from course_explorer_admin_web.runner import FixedCommandRunner
from course_explorer_admin_web.security import AdminSecurity

# The administration console build output directory beneath the checkout root.
DIST_DIRECTORY_NAME = Path("admin-web") / "dist"


def create_app(
    *,
    settings: AdminWebSettings | None = None,
    root: Path | None = None,
    clock: Callable[[], datetime] = utc_now,
    dist_directory: Path | None = None,
    process_runner: ProcessRunner | None = None,
) -> FastAPI:
    """Create the administration application over one settings family and checkout root.

    Omitted settings and root resolve through their owning loaders, and an omitted dist directory
    resolves beneath the checkout root. ``clock`` supplies the session and
    entry clock, so an expiry boundary is provable without waiting. ``process_runner`` supplies the
    process boundary the fixed-command runner executes over. The application serves the
    administration console, and the usage file counts course-exploration site requests.
    """
    resolved_settings = load_admin_web_settings() if settings is None else settings
    resolved_root = repository_root() if root is None else root
    resolved_dist = (
        resolved_root / DIST_DIRECTORY_NAME if dist_directory is None else dist_directory
    )
    application = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, debug=False)
    security = AdminSecurity(resolved_root, resolved_settings, clock=clock)
    application.state.settings = resolved_settings
    application.state.security = security
    application.state.commands = FixedCommandRunner(
        resolved_root, security.log, runner=process_runner
    )
    application.include_router(auth.router)
    application.include_router(dashboard.router)
    application.include_router(preparation.router)
    application.include_router(inference.router)
    application.include_router(logs.router)
    application.include_router(settings_routes.router)
    register_frontend(application, dist_directory=resolved_dist)

    @application.exception_handler(RequestValidationError)
    async def invalid_request(_request: Request, _exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422, content={"detail": "Invalid request"}, headers=NO_STORE_HEADERS
        )

    application.add_middleware(
        AdminAdmissionMiddleware,
        security=security,
        settings=resolved_settings,
    )
    return application
