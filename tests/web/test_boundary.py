"""Security boundary proofs for the fixed read-only web API package."""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Iterator
from typing import Any

from course_explorer_web.app import app


def _walk(routes: Any) -> Iterator[Any]:
    """Yield each route once, descending through an included router's own routes."""
    for route in routes:
        yield route
        nested = getattr(getattr(route, "original_router", None), "routes", None)
        if nested is not None:
            yield from _walk(nested)


def test_web_surface_is_read_only() -> None:
    """Only feature POST and fixed shell GET surfaces exist, without forbidden imports."""
    assert {
        (route.path, frozenset(route.methods or ()))
        for route in _walk(app.routes)
        if hasattr(route, "methods") and route.path != "/openapi.json"
    } == {
        (path, frozenset({"POST"}))
        for path in (
            "/api/search",
            "/api/catalogue",
            "/api/comparison",
            "/api/prerequisites",
            "/api/next-courses",
            "/api/recommendations",
            "/api/study-structure",
            "/api/course-summaries",
            "/api/features",
        )
    } | {("/", frozenset({"GET"})), ("/docs", frozenset({"GET"}))}
    assert any(getattr(route, "path", None) == "/assets" for route in _walk(app.routes))
    subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import course_explorer_web.app; forbidden = "
            "('course_explorer_admin', 'course_explorer_admin_web', 'course_explorer.translation', "
            "'course_explorer.ingestion.commands', 'course_explorer.embeddings.commands'); "
            "assert not any(name == prefix or name.startswith(prefix + '.') "
            "for name in sys.modules for prefix in forbidden)",
        ],
        check=True,
    )
