"""Security boundary proofs for the fixed read-only web API package."""

from __future__ import annotations

import subprocess
import sys

from course_explorer_web.app import app


def test_web_surface_is_read_only() -> None:
    """Only feature POST and fixed shell GET surfaces exist, without forbidden imports."""
    assert {
        (route.path, frozenset(route.methods or ()))
        for route in app.routes
        if hasattr(route, "methods") and route.path != "/openapi.json"
    } == {
        (path, frozenset({"POST"}))
        for path in (
            "/api/search",
            "/api/course-lookup",
            "/api/module-lookup",
            "/api/comparison",
            "/api/prerequisites",
            "/api/minimum-route",
            "/api/next-courses",
            "/api/recommendations",
            "/api/study-structure",
            "/api/course-summaries",
        )
    } | {("/", frozenset({"GET"})), ("/docs", frozenset({"GET"}))}
    assert any(route.path == "/assets" for route in app.routes)
    subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import course_explorer_web.app; forbidden = "
            "('course_explorer_admin', 'course_explorer.translation', "
            "'course_explorer.ingestion.commands', 'course_explorer.embeddings.commands'); "
            "assert not any(name == prefix or name.startswith(prefix + '.') "
            "for name in sys.modules for prefix in forbidden)",
        ],
        check=True,
    )
