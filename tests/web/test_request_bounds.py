"""Request-model proofs for the configured count, identifier and query bounds."""

from __future__ import annotations

from fastapi.testclient import TestClient

from course_explorer.config import load_web_settings
from course_explorer_web.app import app


def test_feature_routes_refuse_inputs_over_the_configured_bounds() -> None:
    """An over-long course list, identifier and query each answer 422 at the route boundary."""
    client = TestClient(app)
    web = load_web_settings()

    assert (
        client.post(
            "/api/course-summaries",
            json={"identifiers": ["course-group-a"] * (web.web_request_max_course_items + 1)},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/course-summaries",
            json={"identifiers": ["x" * (web.web_request_max_identifier_length + 1)]},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/search",
            json={
                "query": "x" * (web.web_request_max_query_length + 1),
                "display_language": "en",
            },
        ).status_code
        == 422
    )
