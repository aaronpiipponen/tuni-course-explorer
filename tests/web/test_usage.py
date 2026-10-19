"""Serving-boundary proofs that every HTTP outcome records one content-free usage line."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from course_explorer.search import lookup_commands
from course_explorer.usage import UsageRecord
from course_explorer_web.app import create_app

_USAGE_PATH = Path("data") / "usage" / "requests"
_SENTINELS = ("sentinel-course-code", "?query=sentinel", "sentinel-header")


class _UsageCase:
    """One HTTP request, its fixed route label and its observed status."""

    __slots__ = ("body", "headers", "method", "path", "route", "status", "use_embeddings")

    def __init__(
        self,
        method: str,
        path: str,
        route: str,
        status: int,
        *,
        body: dict[str, object] | None = None,
        headers: dict[str, str] | None = None,
        use_embeddings: bool = True,
    ) -> None:
        self.method = method
        self.path = path
        self.route = route
        self.status = status
        self.body = body
        self.headers = headers or {}
        self.use_embeddings = use_embeddings


_CASES = (
    _UsageCase("POST", "/api/features", "/api/features", 200, body={}),
    _UsageCase(
        "POST",
        "/api/features",
        "/api/features",
        422,
        body={"unexpected": "sentinel-course-code"},
    ),
    _UsageCase(
        "POST",
        "/api/comparison",
        "/api/comparison",
        403,
        body={"course_a": "COMP.CS.100", "course_b": "COMP.CS.200"},
        use_embeddings=False,
    ),
    _UsageCase(
        "GET",
        "/unknown/sentinel-course-code?query=sentinel",
        "unmatched",
        404,
        headers={"x-sentinel": "sentinel-header"},
    ),
    _UsageCase("GET", "/api/features", "/api/features", 405),
    _UsageCase("GET", "/", "/", 200),
    _UsageCase("GET", "/assets/app.js", "/assets", 200),
    _UsageCase("GET", "/assets/absent.js", "/assets", 404),
    _UsageCase(
        "POST",
        "/api/course-lookup",
        "/api/course-lookup",
        500,
        body={"query": "COMP.CS", "display_language": "en"},
    ),
)
_CASE_IDS = (
    "feature-read",
    "validation",
    "disabled-feature",
    "unknown-path",
    "method-mismatch",
    "shell",
    "asset",
    "missing-asset",
    "handler-failure",
)


@pytest.mark.parametrize("case", _CASES, ids=_CASE_IDS)
def test_http_requests_record_only_safe_route_usage(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, case: _UsageCase
) -> None:
    """One request per invocation records one line with its own route, status and duration."""
    dist = tmp_path / "dist"
    assets = dist / "assets"
    assets.mkdir(parents=True)
    (dist / "index.html").write_text("<main>built shell</main>", encoding="utf-8")
    (assets / "app.js").write_text("console.log('built asset')", encoding="utf-8")
    monkeypatch.setenv("WEB_EMBEDDINGS_ENABLED", "1" if case.use_embeddings else "0")
    if case.status == 500:

        def failing_lookup(**_kwargs: object) -> None:
            raise RuntimeError("handler-payload-value")

        monkeypatch.setattr(lookup_commands, "run_course_lookup_command", failing_lookup)

    client = TestClient(create_app(frontend_directory=dist), raise_server_exceptions=False)
    response = client.request(case.method, case.path, json=case.body, headers=case.headers)
    assert response.status_code == case.status

    lines = (tmp_path / _USAGE_PATH).read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    record = UsageRecord.model_validate_json(lines[0])
    assert set(json.loads(lines[0])) == {"hour", "route", "status", "duration_seconds"}
    assert record.route == case.route
    assert record.status == case.status
    assert record.hour.tzinfo is not None
    assert record.hour.utcoffset() == timedelta(0)
    assert record.hour == record.hour.replace(minute=0, second=0, microsecond=0)
    assert record.hour <= datetime.now(UTC)
    assert record.duration_seconds >= 0
    assert not any(sentinel in lines[0] for sentinel in _SENTINELS)
