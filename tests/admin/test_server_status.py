"""Contracts for the one server-only status report behind the operator's Dashboard read.

The proof binds one temporary checkout whose configuration, environment file and migration tree
are links to this checkout, plus a temporary selected-dataset receipt in a case that enrolls one
and an embedding artifact directory with both hub files. One small process-boundary double answers
the fixed systemd, git, Compose and directory-total reads, while the host facts are real and the
database read runs against the disposable ``course_explorer_test`` database. Every parameter runs
the single public report once and asserts only that invocation's outcome.
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic.config import Config as AlembicConfig
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, text

from course_explorer import administration
from course_explorer.administration import administrative_json, atomic_write_private_text
from course_explorer.config import load_database_settings, load_embedding_runtime_settings
from course_explorer.constants import COURSE_EMBEDDING_DIMENSION
from course_explorer.datasets import DatasetPointer
from course_explorer.embeddings.generation import embedding_configuration_sha256
from course_explorer.serving_artifacts import (
    embedding_directory,
    serving_artifact_root,
    serving_key,
)
from course_explorer.serving_build import write_hub_pair
from course_explorer_admin import datasets as datasets_admin
from course_explorer_admin import mechanics, server
from tests.datasets._support import INITIAL_ID, REVISION, sample_receipt
from tests.support.repository import scratch_repository

pytestmark = [pytest.mark.integration]

_DISPOSABLE_DATABASE = "course_explorer_test"
_UNUSED_DATABASE = "course_explorer_status_unused"
_STATE_ROOT = "data/admin-site-test"
_UNIT = "synthetic-site-web.service"
_WEB_HOST = "127.0.0.1"
_WEB_PORT = 18026
_WEB_WORKERS = 3
_MAIN_PID = 4242
_SHARED_MEMORY_BYTES = 1073741824
_DIRECTORY_TOTALS = {"data": 1024, "models": 2048}
_SITE_PROPERTIES = (
    "LoadState",
    "ActiveState",
    "SubState",
    "MainPID",
    "ActiveEnterTimestampMonotonic",
    "WorkingDirectory",
    "ExecStart",
)


def _bind_proof_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    selection_enabled: bool,
    embeddings_enabled: bool,
) -> Path:
    """Build one temporary checkout and bind every owner root and setting the report reads.

    The configuration, migrations and environment file are links to this checkout, so the database
    settings compose from the checkout's own values and the other settings take the example values
    the integration fixture places in the process environment. The report's state root and
    artifact build resolve to the temporary tree.
    """
    root = scratch_repository(tmp_path / "checkout")
    (root / "data").mkdir()
    (root / "models").mkdir()
    state = root / _STATE_ROOT
    if selection_enabled:
        receipt_directory = state / "datasets" / INITIAL_ID
        receipt_directory.mkdir(mode=0o700, parents=True)
        atomic_write_private_text(
            receipt_directory / "receipt.json",
            administrative_json(sample_receipt(database_name=_DISPOSABLE_DATABASE)),
        )
        atomic_write_private_text(
            state / "selected-dataset.json",
            administrative_json(DatasetPointer(schema_version=1, dataset_id=INITIAL_ID)),
        )
    # One hub file is older than any web start and one is newer, so the comparison is decided by the
    # file times rather than by how long this host has been up.
    ancient = datetime(2001, 1, 1, tzinfo=UTC).timestamp()
    tomorrow = (datetime.now(UTC) + timedelta(days=1)).timestamp()

    def _write_embedding_directory() -> Path:
        family = serving_artifact_root(root / _STATE_ROOT, serving_key(load_database_settings()))
        directory = embedding_directory(
            family, embedding_configuration_sha256(load_embedding_runtime_settings())
        )
        directory.mkdir(parents=True)
        write_hub_pair(
            directory,
            (0.0,) * COURSE_EMBEDDING_DIMENSION,
            (0.0,) * COURSE_EMBEDDING_DIMENSION,
        )
        return directory

    monkeypatch.setenv("ADMIN_SITE_WEB_SERVICE_UNIT", _UNIT)
    monkeypatch.setenv("ADMIN_SITE_ADMIN_SERVICE_UNIT", "synthetic-site-admin.service")
    monkeypatch.setenv("ADMIN_STATE_ROOT", _STATE_ROOT)
    monkeypatch.setenv("WEB_EMBEDDINGS_ENABLED", "1" if embeddings_enabled else "0")
    monkeypatch.setenv(
        "POSTGRES_DB", _DISPOSABLE_DATABASE if not selection_enabled else _UNUSED_DATABASE
    )
    monkeypatch.setenv("WEB_HOST", _WEB_HOST)
    monkeypatch.setenv("WEB_PORT", str(_WEB_PORT))
    monkeypatch.setenv("WEB_WORKERS", str(_WEB_WORKERS))
    # The settings composition and the selected-dataset resolution both read this one owner.
    monkeypatch.setattr(administration, "repository_root", lambda: root)
    if not embeddings_enabled:
        return root
    directory = _write_embedding_directory()
    os.utime(directory / "embedding-hub.json", (ancient, ancient))
    os.utime(directory / "embedding-outcomes-hub.json", (tomorrow, tomorrow))
    return root


class _ServerProcessBoundary:
    """Answer the fixed server process reads without running any real command."""

    def __init__(self, *, root: Path, unit: str, running: bool) -> None:
        self.root = root
        self.unit = unit
        self.running = running
        self.calls: list[tuple[str, ...]] = []
        self.directory_paths: list[str] = []

    def run(
        self,
        argv,
        *,
        cwd: Path | None = None,
        env: object = None,
        stdin_path: Path | None = None,
        stdout_path: Path | None = None,
        timeout: float | None = None,
    ) -> subprocess.CompletedProcess[bytes]:
        command = tuple(argv)
        self.calls.append(command)
        prefix = mechanics.compose_prefix(non_interactive=True, interpreter=True)
        if command[0] == "systemctl":
            output = self._unit_properties()
        elif command[:2] == ("git", "branch"):
            output = b"synthetic-branch\n"
        elif command[:2] == ("git", "rev-parse"):
            output = f"{REVISION}\n".encode()
        elif command[: len(prefix)] == prefix:
            output = self._container_listing()
        elif command[0] == "sudo":
            output = f"{_SHARED_MEMORY_BYTES}\n".encode()
        elif command[0] == "du":
            output = self._directory_total(command[-1])
        else:
            raise AssertionError(f"the report ran an unexpected process command: {command[0]}")
        return subprocess.CompletedProcess(list(command), 0, stdout=output, stderr=b"")

    def _unit_properties(self) -> bytes:
        return "".join(
            f"{name}={value}\n"
            for name, value in (
                ("LoadState", "loaded"),
                ("ActiveState", "active"),
                ("SubState", "running"),
                ("MainPID", str(_MAIN_PID)),
                # One second of this host's monotonic clock, so the derived uptime is measurable.
                ("ActiveEnterTimestampMonotonic", "1000000"),
                ("WorkingDirectory", str(self.root)),
                (
                    "ExecStart",
                    "{ path=/usr/bin/bash ; argv[]=/usr/bin/bash "
                    f"{self.root / 'scripts' / 'run_web.sh'} ; ignore_errors=no ; "
                    "start_time=[n/a] ; stop_time=[n/a] }",
                ),
            )
        ).encode()

    def _container_listing(self) -> bytes:
        database = {
            "ID": "synthetic-db-container",
            "Service": "db",
            "State": "running" if self.running else "exited",
            "Health": "healthy" if self.running else "",
            "Image": "pgvector/pgvector:0.8.6-pg18-trixie",
        }
        embedding = {
            "ID": "synthetic-embedding-container",
            "Service": "embedding",
            "State": "running",
            "Health": "healthy",
            "Image": "synthetic-embedding-image",
        }
        return ("\n".join(json.dumps(entry) for entry in (database, embedding)) + "\n").encode()

    def _directory_total(self, path: str) -> bytes:
        relative = Path(path).relative_to(self.root).as_posix()
        self.directory_paths.append(relative)
        return f"{_DIRECTORY_TOTALS[relative]}\t{path}\n".encode()


def _tree_state(root: Path) -> dict[str, tuple[int, int, bytes]]:
    """Return one (mode, modification time, bytes) projection per file under the proof root.

    The interpreter's own bytecode cache is not product state, so it is left out of the projection.
    """
    state: dict[str, tuple[int, int, bytes]] = {}
    for path in sorted(root.rglob("*")):
        if "__pycache__" in path.parts:
            continue
        if path.is_file() and not path.is_symlink():
            stat = path.stat()
            state[path.relative_to(root).as_posix()] = (
                stat.st_mode,
                stat.st_mtime_ns,
                path.read_bytes(),
            )
    return state


@pytest.mark.parametrize(
    ("case", "selection_enabled", "running", "embeddings_enabled"),
    [
        ("selected-and-running", True, True, True),
        ("selected-and-stopped", True, False, True),
        ("configured-and-running", False, True, True),
        ("configured-and-stopped", False, False, True),
        ("redirected-data-reads-unavailable-and-stopped", True, False, True),
        ("selected-and-embeddings-off", True, True, False),
    ],
)
def test_server_status_reports_server_owned_facts(
    database: tuple[Engine, object],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    case: str,
    selection_enabled: bool,
    running: bool,
    embeddings_enabled: bool,
) -> None:
    """One report states the measured, configured, receipt and checkout facts it owns."""
    root = _bind_proof_root(
        monkeypatch,
        tmp_path,
        selection_enabled=selection_enabled,
        embeddings_enabled=embeddings_enabled,
    )
    if case == "redirected-data-reads-unavailable-and-stopped":
        # The data directory is a redirect at the checkout root and the dataset state lives under
        # it, so both read-only reports state that the dataset state is unavailable instead of
        # reading through the link.
        outside_data = tmp_path / "outside-data"
        (root / "data").rename(outside_data)
        (root / "data").symlink_to(outside_data)
    boundary = _ServerProcessBoundary(root=root, unit=_UNIT, running=running)
    engines: list[str] = []
    real_engine_factory = server.create_database_engine

    def spy_engine_factory(settings):
        engines.append(settings.postgres_db)
        return real_engine_factory(settings)

    monkeypatch.setattr(server, "create_database_engine", spy_engine_factory)
    before = _tree_state(root)

    if case == "redirected-data-reads-unavailable-and-stopped":
        report = server.read_server_status(runner=boundary)
        assert report.serving.selection_enabled is None
        assert report.serving.dataset_id is None
        assert report.serving.kind is None
        assert report.serving.predecessor_id is None
        assert report.serving.pointer is None
        assert report.serving.receipt_schema_revision is None
        listing = datasets_admin.list_retained_datasets(runner=boundary)
        assert listing.mode == "unavailable"
        assert listing.datasets == ()
        assert _tree_state(root) == before
        return

    report = server.read_server_status(runner=boundary)

    # Nothing under the proof root changed, and no status record was retained.
    assert _tree_state(root) == before

    website = report.website
    assert website.unit == _UNIT
    assert website.state == "active" and website.substate == "running"
    assert website.main_pid == _MAIN_PID
    assert (website.host, website.port, website.configured_workers) == (
        _WEB_HOST,
        _WEB_PORT,
        _WEB_WORKERS,
    )
    assert website.entry_point == "scripts/run_web.sh"
    assert website.checkout_branch == "synthetic-branch"
    assert website.checkout_revision == REVISION
    assert website.started_at is not None and website.uptime_seconds is not None
    assert website.uptime_seconds > 0
    elapsed = (datetime.now(UTC) - website.started_at).total_seconds()
    assert abs(elapsed - website.uptime_seconds) < 5

    host = report.host
    assert host.uptime_seconds > 0
    assert 0 <= host.cpu_usage_percent <= 100
    assert 0 < host.memory_used_bytes < host.memory_total_bytes
    assert host.disk_free_bytes < host.disk_total_bytes
    assert (host.data_bytes, host.models_bytes) == (1024, 2048)
    assert host.backups_bytes is None
    assert boundary.directory_paths == ["data", "models"]

    assert report.embedding.container.state == "running"
    assert report.embedding.container.health == "healthy"
    assert report.embedding.host == "127.0.0.1"
    assert report.embedding.model and report.embedding.artifact

    assert report.serving.embeddings_enabled is embeddings_enabled
    if embeddings_enabled:
        catalogue, outcomes = report.hubs
        assert [hub.name for hub in report.hubs] == ["catalogue", "outcomes"]
        assert catalogue.path.endswith("/embedding-hub.json")
        assert outcomes.path.endswith("/embedding-outcomes-hub.json")
        assert catalogue.path.startswith(f"{_STATE_ROOT}/serving/")
        assert catalogue.modified_at == datetime.fromtimestamp(
            (root / catalogue.path).stat().st_mtime, tz=UTC
        )
        assert catalogue.newer_than_web_start is False
        assert outcomes.newer_than_web_start is True
    else:
        assert report.hubs == ()

    expected_head = ScriptDirectory.from_config(
        AlembicConfig(str(root / "alembic.ini"))
    ).get_heads()[0]
    assert report.database.expected_schema_revision == expected_head
    assert report.database.host == "127.0.0.1"
    assert report.database.shared_memory_bytes == _SHARED_MEMORY_BYTES

    if not selection_enabled:
        assert report.serving == server.ServingStatus(
            selection_enabled=False, embeddings_enabled=embeddings_enabled
        )
        assert report.database.name == _DISPOSABLE_DATABASE
    else:
        assert report.serving.selection_enabled is True
        assert report.serving.dataset_id == INITIAL_ID
        assert report.serving.kind == "initial"
        assert report.serving.predecessor_id is None
        assert report.serving.pointer == f"{_STATE_ROOT}/selected-dataset.json"
        # The database schema revision the receipt recorded, apart from the document format version
        # and the database's own head.
        assert report.serving.receipt_schema_revision == "fixture-schema"
        # The report takes the database name from the receipt.
        assert report.database.name == _DISPOSABLE_DATABASE

    if not running:
        assert report.database.container.state == "exited"
        assert report.database.container.health is None
        assert report.database.schema_revision is None
        assert report.database.at_head is None
        assert report.database.size_bytes is None
        assert report.database.connections is None
        assert engines == []
    else:
        assert report.database.container.state == "running"
        assert report.database.container.image == "pgvector/pgvector:0.8.6-pg18-trixie"
        assert report.database.schema_revision == expected_head
        assert report.database.at_head is True
        assert report.database.connections is not None and report.database.connections >= 1
        assert report.database.size_bytes is not None and report.database.size_bytes > 0
        assert engines == [_DISPOSABLE_DATABASE]
        engine, _ = database
        with engine.connect() as connection:
            live_size = connection.execute(
                text("SELECT pg_database_size(current_database())")
            ).scalar_one()
        assert report.database.size_bytes == live_size

    # The configured unit, one Compose listing, and no other read of the server.
    systemctl = next(command for command in boundary.calls if command[0] == "systemctl")
    requested = tuple(systemctl[index + 1] for index, part in enumerate(systemctl) if part == "-p")
    assert requested == _SITE_PROPERTIES
    assert systemctl[3] == _UNIT
    compose = next(
        command
        for command in boundary.calls
        if command[: len(mechanics.compose_prefix(non_interactive=True, interpreter=True))]
        == mechanics.compose_prefix(non_interactive=True, interpreter=True)
    )
    assert compose[-4:] == ("ps", "--all", "--format", "{{json .}}")
