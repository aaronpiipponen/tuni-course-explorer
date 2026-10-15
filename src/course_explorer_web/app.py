"""Compose the fixed read-only feature API."""

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from course_explorer_web.frontend import register_frontend
from course_explorer_web.routes import (
    comparison,
    course_lookup,
    course_summaries,
    minimum_route,
    module_lookup,
    next_courses,
    prerequisites,
    recommendations,
    search,
    study_structure,
)


def create_app(*, frontend_directory: Path | None = None) -> FastAPI:
    """Create the fixed API surface and translate only caller errors to safe 422 responses."""
    application = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    for route in (
        search.router,
        course_lookup.router,
        module_lookup.router,
        comparison.router,
        prerequisites.router,
        minimum_route.router,
        next_courses.router,
        recommendations.router,
        study_structure.router,
        course_summaries.router,
    ):
        application.include_router(route)

    @application.exception_handler(ValueError)
    async def command_error(_request: Request, exc: ValueError) -> JSONResponse:
        if isinstance(exc, ValidationError):
            raise exc
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @application.exception_handler(RequestValidationError)
    async def invalid_request(_request: Request, _exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": "Invalid request"})

    register_frontend(
        application,
        dist_directory=frontend_directory or Path(__file__).resolve().parents[2] / "web" / "dist",
    )
    return application


app = create_app()
