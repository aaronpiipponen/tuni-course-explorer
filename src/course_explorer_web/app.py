"""Compose the plain read-only feature application that one worker process serves."""

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.middleware.gzip import GZipMiddleware

from course_explorer_web.frontend import register_frontend
from course_explorer_web.routes import (
    catalogue,
    comparison,
    course_summaries,
    features,
    next_courses,
    prerequisites,
    recommendations,
    search,
    study_structure,
)


def create_app(*, frontend_directory: Path | None = None) -> FastAPI:
    """Create the fixed API surface, register compression and translate caller errors to 422."""
    application = FastAPI(
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    for route in (
        search.router,
        catalogue.router,
        comparison.router,
        prerequisites.router,
        next_courses.router,
        recommendations.router,
        study_structure.router,
        course_summaries.router,
        features.router,
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
    application.add_middleware(GZipMiddleware, minimum_size=500, compresslevel=6)
    return application


app = create_app()
