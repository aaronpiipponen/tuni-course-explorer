"""Shared administration-backend test support: a temporary site root and one real argon2id account.

Every helper points the credential owner at a caller-supplied temporary checkout, stores one synthetic
account through the real password owner, builds the administration settings from explicit values so no
configuration file is read, and serves one application over a controlled UTC clock and a temporary
console build. No helper creates or inspects the real ``data/admin-web/`` state of a checkout.
"""

from __future__ import annotations

import subprocess
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from starlette.staticfiles import StaticFiles

from course_explorer.config import AdminWebSettings
from course_explorer_admin import credentials
from course_explorer_admin.mechanics import ProcessRunner
from course_explorer_admin_web.app import create_app
from course_explorer_admin_web.security import SESSION_COOKIE_NAME

ORIGIN = "https://localhost:8039"
APP_URL = "http://localhost:8037/"
REPOSITORY_URL = "https://github.com/aaronpiipponen/tuni-course-explorer"
OPERATOR_NAME = "synthetic-operator"
OPERATOR_PASSWORD = "synthetic-password"
REPLACEMENT_PASSWORD = "synthetic-replacement-password"

ADMIN_STATE_PATH = Path("data") / "admin-web"
PASSWORD_PATH = ADMIN_STATE_PATH / "password"
FAILED_LOGINS_PATH = ADMIN_STATE_PATH / "failed-logins"
COMMAND_LOG_PATH = ADMIN_STATE_PATH / "command-log"
LOCK_PATH = ADMIN_STATE_PATH / "lock"

# The test-only static mount the admission boundary must cover like any other address.
STATIC_PROBE_PATH = "/test-assets/probe.txt"

# A temporary build output for the console shell and its assets directory, so static admission and
# static serving are provable without the product console build.
DIST_DIRECTORY_NAME = "test-dist"
SHELL_TEXT = "administration console shell\n"
ASSET_PROBE_NAME = "probe.txt"
ASSET_PROBE_TEXT = "administration console asset\n"
ASSET_PROBE_PATH = f"/assets/{ASSET_PROBE_NAME}"

# A sentinel no admitted command's own input ever carries, so a retained log line can be checked for
# the capture of an argument or a value.
VALUE_SENTINEL = "synthetic-value-sentinel"
OUTPUT_SENTINEL = "synthetic-output-sentinel"
# A distinctive admitted argument: its text must never reach the log.
ARGUMENT_SENTINEL = 987654


class ControlledClock:
    """A settable timezone-aware UTC clock shared by one application and its test."""

    def __init__(self, now: datetime | None = None) -> None:
        self.now = now if now is not None else datetime(2026, 10, 18, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        """Return the clock's current value."""
        return self.now

    def advance(self, delta: timedelta) -> None:
        """Move the clock forward by one exact interval."""
        self.now = self.now + delta


class ScriptedProcessBoundary:
    """A recording process boundary returning one prepared outcome per call.

    Each ``outcomes`` entry is the stdout bytes of one successful call or a
    ``subprocess.CalledProcessError`` to raise for that call. The last entry repeats once the queue is
    exhausted, so one double serves both a uniform outcome and a mixed sequence. It implements only
    the ``run`` call the runner makes, so it re-implements no product behavior.
    """

    def __init__(self, outcomes: Sequence[bytes | BaseException] = (b"{}",)) -> None:
        self._outcomes: list[bytes | BaseException] = list(outcomes) or [b"{}"]
        self.calls: list[dict[str, object]] = []

    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: Path | None = None,
        env: Mapping[str, str] | None = None,
        stdin_path: Path | None = None,
        stdout_path: Path | None = None,
        timeout: float | None = None,
    ) -> subprocess.CompletedProcess[bytes]:
        """Record one call and return the next prepared result or raise the next failure."""
        self.calls.append({"argv": tuple(argv), "cwd": cwd})
        outcome = self._outcomes.pop(0) if len(self._outcomes) > 1 else self._outcomes[0]
        if isinstance(outcome, BaseException):
            raise outcome
        return subprocess.CompletedProcess(
            args=list(argv), returncode=0, stdout=outcome, stderr=b""
        )


def site_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *, password: str = OPERATOR_PASSWORD
) -> Path:
    """Create one temporary checkout root and store its account through the real password owner."""
    root = tmp_path / "checkout"
    root.mkdir()
    monkeypatch.setattr(credentials, "repository_root", lambda: root)
    credentials.set_admin_password(username=OPERATOR_NAME, password=SecretStr(password))
    return root


def set_account_password(
    monkeypatch: pytest.MonkeyPatch, root: Path, *, password: str = REPLACEMENT_PASSWORD
) -> None:
    """Replace one temporary site's stored account through the same real password owner."""
    monkeypatch.setattr(credentials, "repository_root", lambda: root)
    credentials.set_admin_password(username=OPERATOR_NAME, password=SecretStr(password))


def admin_web_settings(**overrides: object) -> AdminWebSettings:
    """Build administration settings from explicit values in place of any configuration file."""
    values: dict[str, object] = {
        "ADMIN_WEB_HOST": "127.0.0.1",
        "ADMIN_WEB_PORT": 8039,
        "ADMIN_WEB_ORIGIN": ORIGIN,
        "ADMIN_WEB_SESSION_IDLE_MINUTES": 30,
        "ADMIN_WEB_SESSION_MAX_HOURS": 12,
        "ADMIN_WEB_ANONYMOUS_SESSION_LIMIT": 10,
        "ADMIN_WEB_ANONYMOUS_SESSION_WINDOW_SECONDS": 60,
        "ADMIN_WEB_COMMAND_LOG_LIMIT": 200,
        "ADMIN_WEB_POLL_SECONDS": 10,
        "ADMIN_WEB_APP_URL": APP_URL,
        "ADMIN_WEB_REPOSITORY_URL": REPOSITORY_URL,
    }
    values.update(overrides)
    return AdminWebSettings(**values)


def admin_web_app(
    root: Path,
    settings: AdminWebSettings,
    *,
    clock: ControlledClock,
    process_runner: ProcessRunner | None = None,
) -> FastAPI:
    """Build one administration application with a temporary build and the test-only static mount.

    The temporary build holds one shell document and one asset, so static admission and static
    serving are provable without the product console build. ``process_runner`` is forwarded into the
    application's fixed-command runner, so a caller supplies the one shared process double.
    """
    dist = root / DIST_DIRECTORY_NAME
    assets = dist / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    (dist / "index.html").write_text(SHELL_TEXT, encoding="utf-8")
    (assets / ASSET_PROBE_NAME).write_text(ASSET_PROBE_TEXT, encoding="utf-8")
    application = create_app(
        settings=settings,
        root=root,
        clock=clock,
        dist_directory=dist,
        process_runner=process_runner,
    )
    probe = root / "test-assets"
    probe.mkdir(exist_ok=True)
    (probe / "probe.txt").write_text("administration static probe\n", encoding="utf-8")
    application.mount("/test-assets", StaticFiles(directory=probe, check_dir=False))
    return application


def site_client(application: FastAPI) -> TestClient:
    """Return one HTTPS-base client of one application, which carries its own cookie jar."""
    return TestClient(application, base_url=ORIGIN)


def site(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, **overrides: object
) -> tuple[Path, AdminWebSettings, ControlledClock, FastAPI]:
    """Create one temporary site: its root, its settings, its clock and its application."""
    root = site_root(monkeypatch, tmp_path)
    settings = admin_web_settings(**overrides)
    clock = ControlledClock()
    return root, settings, clock, admin_web_app(root, settings, clock=clock)


def session_cookie(client: TestClient) -> str:
    """Return the site session cookie value the client carries."""
    value = client.cookies.get(SESSION_COOKIE_NAME)
    assert value is not None
    return value


def bootstrap(client: TestClient) -> str:
    """Start one real anonymous session and return its CSRF token."""
    response = client.get("/auth/session")
    assert response.status_code == 200
    return response.json()["csrf_token"]


def login(
    client: TestClient,
    *,
    csrf_token: str,
    username: str = OPERATOR_NAME,
    password: str = OPERATOR_PASSWORD,
) -> object:
    """Send one exact-site login request carrying the session cookie and CSRF token."""
    return client.post(
        "/auth/login",
        json={"username": username, "password": password},
        headers={"Origin": ORIGIN, "X-CSRF-Token": csrf_token},
    )


def authenticated_client(application: FastAPI) -> TestClient:
    """Return one client of one application holding a real authenticated server-side session."""
    client = site_client(application)
    assert login(client, csrf_token=bootstrap(client)).status_code == 200
    return client
