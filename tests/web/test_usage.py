"""Serving-boundary proofs that every HTTP outcome records one content-free usage line."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from course_explorer.config import AdmissionSettings
from course_explorer.search import lookup_commands
from course_explorer.usage import UsageRecord
from course_explorer_web.app import create_app
from course_explorer_web.router.app import create_router
from tests.support import settings_factory
from tests.web._router_support import WorkerHarness

_USAGE_PATH = Path("data") / "usage" / "requests"
_SENTINELS = ("sentinel-course-code", "?query=sentinel", "sentinel-header")
_LIMITED_COOKIE = "c" * 32


class _UsageCase:
    """One HTTP request, its fixed route label and its observed status."""

    __slots__ = (
        "admission",
        "body",
        "cookie",
        "headers",
        "method",
        "path",
        "pre_admit",
        "route",
        "status",
        "use_embeddings",
    )

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
        admission: dict[str, str] | None = None,
        pre_admit: bool = False,
        cookie: str | None = None,
    ) -> None:
        self.method = method
        self.path = path
        self.route = route
        self.status = status
        self.body = body
        self.headers = headers or {}
        self.use_embeddings = use_embeddings
        self.admission = admission
        self.pre_admit = pre_admit
        self.cookie = cookie


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
        "/api/catalogue",
        "/api/catalogue",
        500,
        body={},
    ),
    _UsageCase(
        "POST",
        "/api/catalogue",
        "/api/catalogue",
        429,
        body={},
        admission={
            "ADMISSION_ENABLED": "1",
            "ADMISSION_LIGHT_BURST": "1",
            "ADMISSION_LIGHT_OPERATIONS_PER_MINUTE": "1",
        },
        pre_admit=True,
        cookie=_LIMITED_COOKIE,
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
    "limited",
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

        def failing_catalogue(**_kwargs: object) -> None:
            raise RuntimeError("handler-payload-value")

        monkeypatch.setattr(lookup_commands, "run_catalogue_command", failing_catalogue)
    harness = WorkerHarness(
        (create_app(frontend_directory=dist), create_app(frontend_directory=dist))
    )
    settings = settings_factory(AdmissionSettings, WEB_WORKERS="2", **(case.admission or {}))

    async def exercise() -> httpx.Response:
        application = create_router(
            workers=harness.addresses[:2],
            settings=settings,
            client=harness.client(),
        )
        await application.startup()
        try:
            if case.pre_admit:
                assert application.state is not None
                assert case.cookie is not None
                application.state.admit_light(case.cookie)
            headers = dict(case.headers)
            if case.cookie is not None:
                headers["cookie"] = f"tce_anon={case.cookie}"
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=application), base_url="http://router"
            ) as client:
                return await client.request(case.method, case.path, json=case.body, headers=headers)
        finally:
            await application.shutdown()

    response = asyncio.run(exercise())
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
