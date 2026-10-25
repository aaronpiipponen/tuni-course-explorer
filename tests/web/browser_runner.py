"""Serve the built app over one disposable example-data database for the browser journeys.

The runner owns one fresh ``_test`` database, its Alembic head, the committed example import, one
loopback uvicorn process and one Node test invocation, and removes each in reverse order. It selects
the listed browser test basenames and rejects any other name.
"""

from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from collections.abc import Sequence
from pathlib import Path

from alembic import command
from alembic.config import Config

from course_explorer.config import (
    ENVIRONMENT_ONLY_SETTINGS_SOURCE,
    SETTINGS_SOURCE_MARKER,
    DatabaseSettings,
    load_raw_database_settings,
)
from course_explorer.db.session import create_database_engine
from course_explorer.mock_data import run_mock_data_command
from tests.support import public_environment

APPROVED_TESTS = (
    "browser-route.test.mjs",
    "browser-phone.test.mjs",
    "browser-lookup-guard.test.mjs",
    "browser-docs.test.mjs",
    "browser-docs-search.test.mjs",
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_FRONTEND_INDEX = _REPOSITORY_ROOT / "web" / "dist" / "index.html"
_READY_TIMEOUT_SECONDS = 60.0
_SHUTDOWN_TIMEOUT_SECONDS = 10.0


class _StopSignal(Exception):
    """Unwind the owned server, test process and database after a termination signal."""

    def __init__(self, signum: int) -> None:
        super().__init__(signum)
        self.signum = signum


def _handle_stop(signum: int, _frame: object) -> None:
    """Raise the unwinding exception a termination signal requests."""
    raise _StopSignal(signum)


def _selected_tests(arguments: Sequence[str]) -> tuple[str, ...]:
    """Return the listed basenames to run, defaulting to all five."""
    if not arguments:
        return APPROVED_TESTS
    unknown = [name for name in arguments if name not in APPROVED_TESTS]
    if unknown:
        raise ValueError(
            "unknown browser test basename: "
            f"{', '.join(unknown)}; the listed names are {', '.join(APPROVED_TESTS)}"
        )
    return tuple(arguments)


def _executable_environment() -> dict[str, str]:
    """Return the ordinary executable-discovery environment without product settings."""
    preserved = (
        "PATH",
        "HOME",
        "TMPDIR",
        "TMP",
        "TEMP",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "LD_LIBRARY_PATH",
        "XDG_CACHE_HOME",
        "XDG_CONFIG_HOME",
    )
    environment = {key: os.environ[key] for key in preserved if key in os.environ}
    environment.update(
        {key: value for key, value in os.environ.items() if key.startswith("PLAYWRIGHT_")}
    )
    return environment


def _closed_environment(connection: DatabaseSettings, database_name: str) -> dict[str, str]:
    """Build the example-only settings map for this run's database and serving generation."""
    environment = dict(public_environment())
    environment.update(
        {
            "POSTGRES_HOST": connection.postgres_host,
            "POSTGRES_PORT": str(connection.postgres_port),
            "POSTGRES_USER": connection.postgres_user,
            "POSTGRES_PASSWORD": connection.postgres_password.get_secret_value(),
            "POSTGRES_DB": database_name,
            "SELECTED_DATASET_ENABLED": "0",
            SETTINGS_SOURCE_MARKER: ENVIRONMENT_ONLY_SETTINGS_SOURCE,
            "COURSE_EXPLORER_WEB_GENERATION": uuid.uuid4().hex,
        }
    )
    return environment


def _create_database(connection: DatabaseSettings, database_name: str) -> None:
    """Create one fresh database on the configured instance without touching any other."""
    if not database_name.endswith("_test"):
        raise ValueError("the browser database name must end with _test")
    engine = create_database_engine(connection.model_copy(update={"postgres_db": "postgres"}))
    try:
        with engine.connect() as opened:
            autocommit = opened.execution_options(isolation_level="AUTOCOMMIT")
            quoted = autocommit.dialect.identifier_preparer.quote(database_name)
            autocommit.exec_driver_sql(f"CREATE DATABASE {quoted}")
    finally:
        engine.dispose()


def _drop_database(connection: DatabaseSettings, database_name: str) -> None:
    """Drop exactly the database this run created, failing loudly if it is absent."""
    engine = create_database_engine(connection.model_copy(update={"postgres_db": "postgres"}))
    try:
        with engine.connect() as opened:
            autocommit = opened.execution_options(isolation_level="AUTOCOMMIT")
            quoted = autocommit.dialect.identifier_preparer.quote(database_name)
            autocommit.exec_driver_sql(f"DROP DATABASE {quoted}")
    finally:
        engine.dispose()


def _migrate(database: DatabaseSettings) -> None:
    """Apply the Alembic head to the fresh database through one caller-owned connection."""
    config = Config(str(_REPOSITORY_ROOT / "alembic.ini"))
    engine = create_database_engine(database)
    try:
        with engine.connect() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
    finally:
        engine.dispose()


def _available_port() -> int:
    """Reserve and release one loopback port for the serving process."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _await_ready(process: subprocess.Popen[bytes], base_url: str) -> None:
    """Poll the feature read until it reports both example switches and a dataset identity."""
    deadline = time.monotonic() + _READY_TIMEOUT_SECONDS
    request = urllib.request.Request(
        f"{base_url}/api/features",
        data=b"{}",
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"the web server exited with status {process.returncode}")
        try:
            with urllib.request.urlopen(request, timeout=1.0) as response:
                payload = json.loads(response.read())
        except urllib.error.HTTPError as error:
            raise RuntimeError(f"the feature check answered HTTP {error.code}") from error
        except urllib.error.URLError, OSError:
            time.sleep(0.2)
            continue
        if not isinstance(payload, dict):
            raise RuntimeError("the feature check returned no report")
        if (
            payload.get("embeddings_enabled") is not True
            or payload.get("inference_enabled") is not True
        ):
            raise RuntimeError("the feature check did not report the example switches")
        identity = payload.get("dataset_identity")
        if not isinstance(identity, str) or not identity:
            raise RuntimeError("the feature check reported no dataset identity")
        return
    raise RuntimeError("the web server did not answer the feature check in 60 seconds")


def _terminate(process: subprocess.Popen[bytes] | None, timeout: float) -> None:
    """Terminate one owned process, then kill and reap it past the shutdown deadline."""
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def _run_tests(
    selected: tuple[str, ...],
    base_url: str,
    environment: dict[str, str],
) -> int:
    """Run the selected Node journeys against the loopback origin once."""
    paths = tuple(str((_REPOSITORY_ROOT / "web" / "tools" / name).resolve()) for name in selected)
    node_environment = dict(environment)
    node_environment["BROWSER_BASE_URL"] = base_url
    process = subprocess.Popen(
        ["node", "--test", "--test-concurrency=1", *paths],
        cwd=_REPOSITORY_ROOT,
        env=node_environment,
    )
    try:
        return process.wait()
    finally:
        _terminate(process, _SHUTDOWN_TIMEOUT_SECONDS)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the selected browser journeys and return the Node exit status."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    try:
        selected = _selected_tests(arguments)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 2
    if not _FRONTEND_INDEX.is_file():
        print(
            f"the built frontend is missing: {_FRONTEND_INDEX}",
            file=sys.stderr,
        )
        return 2
    connection = load_raw_database_settings()
    database_name = f"course_explorer_browser_{uuid.uuid4().hex}_test"
    environment = _closed_environment(connection, database_name)
    os.environ.update(environment)
    serving = connection.model_copy(update={"postgres_db": database_name})
    created = False
    server: subprocess.Popen[bytes] | None = None
    exit_code = 0
    stop_code = 0
    previous_handlers = {
        signum: signal.signal(signum, _handle_stop) for signum in (signal.SIGTERM, signal.SIGINT)
    }
    try:
        with tempfile.TemporaryDirectory(prefix="course-explorer-browser-") as scratch:
            scratch_root = Path(scratch)
            try:
                _create_database(connection, database_name)
                created = True
                _migrate(serving)
                run_mock_data_command(
                    "load",
                    fixture_dir=_REPOSITORY_ROOT / "data" / "mock",
                    raw_root=scratch_root / "raw",
                    hubs_dir=scratch_root / "hubs",
                )
                port = _available_port()
                base_url = f"http://127.0.0.1:{port}"
                server = subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "uvicorn",
                        "course_explorer_web.app:app",
                        "--host",
                        "127.0.0.1",
                        "--port",
                        str(port),
                        "--log-level",
                        "warning",
                    ],
                    cwd=_REPOSITORY_ROOT,
                    env=_executable_environment() | environment,
                )
                _await_ready(server, base_url)
                exit_code = _run_tests(selected, base_url, _executable_environment())
            except _StopSignal as stop:
                stop_code = 128 + stop.signum
            finally:
                _terminate(server, _SHUTDOWN_TIMEOUT_SECONDS)
                if created:
                    _drop_database(connection, database_name)
    finally:
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)
    return stop_code or exit_code


if __name__ == "__main__":
    raise SystemExit(main())
