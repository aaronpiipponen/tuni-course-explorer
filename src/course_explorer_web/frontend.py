"""Serve the built web application's two shell documents and compiled assets."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


def register_frontend(application: FastAPI, *, dist_directory: Path) -> None:
    """Register fixed document routes and the build's sole public asset directory."""

    async def frontend_document() -> FileResponse:
        return FileResponse(dist_directory / "index.html", media_type="text/html")

    application.add_api_route("/", frontend_document, methods=["GET"], include_in_schema=False)
    application.add_api_route("/docs", frontend_document, methods=["GET"], include_in_schema=False)
    application.mount(
        "/assets",
        StaticFiles(directory=dist_directory / "assets", check_dir=False),
        name="frontend-assets",
    )
