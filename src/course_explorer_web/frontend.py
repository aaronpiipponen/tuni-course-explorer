"""Serve the built web application's three shell documents and compiled assets."""

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.datastructures import Headers
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import Scope

from course_explorer_web.accept_encoding import accepts_encoding
from course_explorer_web.serving import SHELL_ROUTES

_IMMUTABLE = "public, max-age=31536000, immutable"


class ImmutableAssetFiles(StaticFiles):
    """Serve a hashed build asset with immutable caching and its precompressed variant.

    A file beside the asset with a ``.br`` or ``.gz`` suffix is returned when the request admits
    that encoding, with the asset's content type and ``Vary: Accept-Encoding``. A request that
    admits neither coding receives the plain file.
    """

    def file_response(
        self,
        full_path: str | Path,
        stat_result: os.stat_result,
        scope: Scope,
        status_code: int = 200,
    ) -> Response:
        """Return the asset response with immutable caching and its precompressed variant."""
        response = super().file_response(full_path, stat_result, scope, status_code)
        response.headers["Cache-Control"] = _IMMUTABLE
        if response.status_code != 200:
            return response
        accepted = Headers(scope=scope).get("accept-encoding", "")
        for suffix, encoding in ((".br", "br"), (".gz", "gzip")):
            variant = Path(f"{full_path}{suffix}")
            if not accepts_encoding(accepted, encoding) or not variant.is_file():
                continue
            encoded = FileResponse(variant, status_code=status_code, media_type=response.media_type)
            encoded.headers["Content-Encoding"] = encoding
            encoded.headers["Vary"] = "Accept-Encoding"
            encoded.headers["Cache-Control"] = _IMMUTABLE
            return encoded
        return response


def register_frontend(application: FastAPI, *, dist_directory: Path) -> None:
    """Register fixed document routes and the build's sole asset directory.

    The app shell, the docs shell and the feedback shell all serve the same built index document
    with ``Cache-Control: no-cache``, so a rebuilt build reaches a browser. The asset directory is
    the only mounted path and carries immutable caching, and an unknown document path reaches the
    application's ordinary 404 rather than a shell fallback.
    """

    async def frontend_document(_request: Request) -> FileResponse:
        return FileResponse(
            dist_directory / "index.html",
            media_type="text/html",
            headers={"Cache-Control": "no-cache"},
        )

    for path in SHELL_ROUTES:
        application.add_api_route(path, frontend_document, methods=["GET"], include_in_schema=False)
    application.mount(
        "/assets",
        ImmutableAssetFiles(directory=dist_directory / "assets", check_dir=False),
        name="frontend-assets",
    )
