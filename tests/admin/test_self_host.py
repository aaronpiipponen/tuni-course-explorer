"""Contracts for the two self-host setup workflows and the absent-template copy.

Each test drives the workflow owner. The process runner, the HTTP reads, the pinned artifact check,
the native-library check, the artifact builder, the unit-directory, table-name and feedback-store
helpers, the migration and verification helpers and the readiness sleep are substituted. Template
copy, the exact-file edits and credential creation run as product code.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr

from course_explorer import administration, configuration
from course_explorer.config import SETTINGS_SOURCE_MARKER, load_raw_database_settings
from course_explorer.datasets import read_dataset_role, resolve_dataset_role
from course_explorer.serving_artifacts import (
    CATALOGUE_FILE,
    catalogue_body,
    serving_artifact_root,
    serving_key,
)
from course_explorer_admin import configuration as editor
from course_explorer_admin import datasets as dataset_owner
from course_explorer_admin import self_host
from course_explorer_admin.self_host import (
    ExampleSetupInput,
    RealDatabaseSetupInput,
    setup_example,
    setup_real_database,
)
from tests.config._support import set_administrative_controller_environment
from tests.datasets._support import sample_verification
from tests.support import REPO_ROOT

_ADMIN_PORT = 18039
_WEB_PORT = 18037


def _checkout(tmp_path: Path, name: str = "checkout") -> Path:
    """Materialize one temporary checkout with the tracked example assets alone."""
    root = tmp_path / name
    shutil.copytree(REPO_ROOT / "examples", root / "examples")
    return root


def _prepare_environment(monkeypatch: pytest.MonkeyPatch, root: Path) -> None:
    """Bind the product owners to a temporary checkout and free loopback ports."""
    set_administrative_controller_environment(
        monkeypatch,
        POSTGRES_PORT="15433",
        FEEDBACK_POSTGRES_PORT="15433",
        EMBEDDING_PORT="18081",
        WEB_PORT=str(_WEB_PORT),
        ADMIN_WEB_PORT=str(_ADMIN_PORT),
    )
    monkeypatch.setattr(administration, "repository_root", lambda: root)
    monkeypatch.delenv(SETTINGS_SOURCE_MARKER, raising=False)
    configuration.clear_configuration_caches()


def _prepare_host_files(root: Path) -> None:
    """Create the prepared interpreter and frontend packages a host preflight requires."""
    interpreter = root / ".venv" / "bin" / "python"
    interpreter.parent.mkdir(parents=True, exist_ok=True)
    interpreter.write_text("#!/usr/bin/env python\n", encoding="utf-8")
    interpreter.chmod(0o700)
    for frontend in ("web", "admin-web"):
        (root / frontend / "node_modules").mkdir(parents=True, exist_ok=True)


def _write_shells(root: Path) -> tuple[bytes, bytes]:
    """Write both built shells and return their bytes."""
    web = b"<!doctype html><title>feature</title>\n"
    admin = b"<!doctype html><title>console</title>\n"
    (root / "web" / "dist").mkdir(parents=True, exist_ok=True)
    (root / "admin-web" / "dist").mkdir(parents=True, exist_ok=True)
    (root / "web" / "dist" / "index.html").write_bytes(web)
    (root / "admin-web" / "dist" / "index.html").write_bytes(admin)
    return web, admin


def _write_catalogue(root: Path, settings, payload: bytes) -> None:
    """Write one fixed catalogue artifact for the supplied database settings."""
    family = serving_artifact_root(root / settings.admin_state_root, serving_key(settings))
    current = family / "current"
    current.mkdir(parents=True, exist_ok=True)
    (current / CATALOGUE_FILE).write_bytes(payload)


class _Child:
    """One owned foreground child recorded by the scripted runner."""

    def __init__(self) -> None:
        self.terminated = False
        self.killed = False
        self.waited = False

    def poll(self) -> int | None:
        return 0 if self.waited else None

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.killed = True

    def wait(self, timeout: float | None = None) -> int:
        self.waited = True
        return 0


class _Runner:
    """Scripted local process boundary over the workflow's exact commands."""

    def __init__(self, *, services: tuple[str, ...] = ("db", "embedding")) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.interactive_calls: list[tuple[str, ...]] = []
        self.services = set(services)
        self.created: set[str] = set()
        self.dropped: set[str] = set()
        self.children: list[_Child] = []

    def run(self, argv, *, cwd=None, env=None, stdin_path=None, stdout_path=None, timeout=None):
        command = tuple(argv)
        self.calls.append(command)
        output = b""
        if "ps" in command and "--services" in command and "--status" in command:
            output = "".join(f"{service}\n" for service in sorted(self.services)).encode()
        elif "psql" in command:
            query = command[-1]
            output = "".join(
                f"{name}\n" for name in sorted(self.created) if f"'{name}'" in query
            ).encode()
        elif "createdb" in command:
            self.created.add(command[-1])
        elif "dropdb" in command:
            self.dropped.add(command[-1])
        elif command[:1] == ("node",):
            output = b"v22.0.0\n"
        elif command[:2] == ("docker", "compose") or command[-1:] == ("version",):
            output = b"1.0.0\n"
        elif command[:1] == ("loginctl",):
            output = b"Linger=yes\n"
        return subprocess.CompletedProcess(list(command), 0, stdout=output, stderr=b"")

    def run_interactive(self, argv, *, cwd=None, env=None, timeout=None):
        command = tuple(argv)
        self.interactive_calls.append(command)
        self.run(command, cwd=cwd, env=env, timeout=timeout)

    def popen(
        self,
        argv,
        *,
        cwd=None,
        env=None,
        stdin_path=None,
        stdout_path=None,
        stderr_path=None,
        start_new_session=False,
        inherit_environment=True,
    ):
        self.calls.append(tuple(argv))
        child = _Child()
        self.children.append(child)
        return child


class _IncapableInterpreterRunner(_Runner):
    """Answer the interpreter capability probe with the failure of an incapable interpreter."""

    def run(
        self,
        argv,
        *,
        cwd=None,
        env=None,
        stdin_path=None,
        stdout_path=None,
        timeout=None,
    ):
        command = tuple(argv)
        if len(command) > 2 and command[1] == "-c":
            self.calls.append(command)
            raise subprocess.CalledProcessError(1, command, output=b"", stderr=b"")
        return super().run(
            command,
            cwd=cwd,
            env=env,
            stdin_path=stdin_path,
            stdout_path=stdout_path,
            timeout=timeout,
        )


def _bind_http(
    monkeypatch: pytest.MonkeyPatch,
    *,
    web_shell: bytes,
    admin_shell: bytes,
    artifact: list[bytes],
    identities: list[str],
    events: list[str],
) -> None:
    """Route both workflow proofs through one fixed HTTP boundary and record each read."""

    def handler(request: httpx.Request) -> httpx.Response:
        events.append("http")
        if request.url.path == "/" and request.url.port == _WEB_PORT:
            return httpx.Response(200, content=web_shell)
        if request.url.path == "/" and request.url.port == _ADMIN_PORT:
            return httpx.Response(200, content=admin_shell)
        if request.url.path == "/api/features":
            identity = identities[0]
            events.append(f"identity:{identity}")
            return httpx.Response(
                200,
                json={
                    "embeddings_enabled": False,
                    "inference_enabled": False,
                    "dataset_identity": identity,
                },
            )
        if request.url.path == "/api/catalogue":
            return httpx.Response(
                200, content=catalogue_body(artifact[0], identities[0]), headers={}
            )
        raise AssertionError(f"unexpected serving read: {request.url}")

    real_client = httpx.Client

    def factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "Client", factory)


def test_example_files_are_copied_only_when_absent(tmp_path: Path) -> None:
    """Absent templates are created, present working files keep their bytes, and links refuse."""
    first = _checkout(tmp_path, "first")
    (first / "config").mkdir()
    present = {
        "config/web.toml": b"# present web settings\n",
        ".env": b"CUSTOM_SECRET=kept\n",
        "docker-compose.yml": b"name: kept\n",
        "deploy/Caddyfile": b"# present proxy\n",
    }
    for relative, payload in present.items():
        path = first / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)

    assert self_host._copy_example_files(first) is False
    for relative, payload in present.items():
        assert (first / relative).read_bytes() == payload
    assert (first / "config" / "database.toml").read_bytes() == (
        first / "examples" / "config" / "database.toml"
    ).read_bytes()
    assert (first / "config" / "wiki.json").is_file()
    assert (first / "config" / "feedback-form.json").is_file()
    for unit in self_host._UNIT_TEMPLATES:
        assert (first / "deploy" / unit).read_bytes() == (
            first / "examples" / "deploy" / "systemd" / unit
        ).read_bytes()

    second = _checkout(tmp_path, "second")
    assert self_host._copy_example_files(second) is True
    environment = second / ".env"
    assert environment.read_bytes() == (second / "examples" / ".env.example").read_bytes()
    assert environment.stat().st_mode & 0o777 == 0o600

    third = _checkout(tmp_path, "third")
    (third / "config").mkdir()
    target = tmp_path / "outside.toml"
    target.write_text("outside\n", encoding="utf-8")
    (third / "config" / "curriculum.toml").symlink_to(target)
    with pytest.raises(ValueError):
        self_host._copy_example_files(third)
    assert target.read_text(encoding="utf-8") == "outside\n"


def test_example_workflow_refuses_an_incapable_interpreter_before_any_download(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A checkout whose interpreter lacks the shared-memory call stops before any host step."""
    root = _checkout(tmp_path, "incapable")
    _prepare_environment(monkeypatch, root)
    _prepare_host_files(root)
    runner = _IncapableInterpreterRunner()

    with pytest.raises(ValueError, match="os.memfd_create"):
        setup_example(
            ExampleSetupInput(
                username="synthetic-operator",
                password=SecretStr("synthetic-password"),
                mode="foreground",
            ),
            runner=runner,
            write=lambda _message: None,
        )

    # The capability probe is the workflow's only command, so no download, build or container
    # command ran.
    interpreter = str(root / ".venv" / "bin" / "python")
    assert [(command[0], command[1]) for command in runner.calls] == [(interpreter, "-c")]


@pytest.mark.parametrize("mode", ["foreground", "user"])
def test_example_workflow_reaches_bootstrap_serving(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, mode: str
) -> None:
    """The same example workflow reaches both shells and bootstrap serving in either mode."""
    root = _checkout(tmp_path, f"checkout-{mode}")
    _prepare_environment(monkeypatch, root)
    _prepare_host_files(root)
    web_shell, admin_shell = _write_shells(root)
    runner = _Runner()
    events: list[str] = []
    artifact = [b'{"courses":[]}']
    identities = ["bootstrap"]
    _bind_http(
        monkeypatch,
        web_shell=web_shell,
        admin_shell=admin_shell,
        artifact=artifact,
        identities=identities,
        events=events,
    )

    monkeypatch.setattr(self_host.artifacts, "artifact_present", lambda path, digest: True)
    monkeypatch.setattr(self_host, "_require_native_libraries", lambda: None)
    monkeypatch.setattr(self_host, "_existing_table_names", lambda settings: ())
    unit_directory = tmp_path / "user-units"
    monkeypatch.setattr(self_host, "_user_unit_directory", lambda: unit_directory)

    def prepare_feedback(*, runner) -> None:
        events.append("feedback")

    monkeypatch.setattr(self_host, "_prepare_feedback_store", prepare_feedback)

    def write_artifact(*_args, **_kwargs) -> None:
        events.append("artifact")
        _write_catalogue(root, load_raw_database_settings(), artifact[0])

    monkeypatch.setattr(
        dataset_owner,
        "migrate_configured_database",
        lambda *, runner: events.append("migrate") or sample_verification(),
    )

    # The fake runner writes the bundle artifact when the bundle writer action runs.
    original_run = runner.run

    def run(argv, **kwargs):
        if tuple(argv)[-2:] == ("scripts/mock_data.py", "write-artifacts"):
            write_artifact()
        return original_run(argv, **kwargs)

    runner.run = run

    def stop_after_readiness(_seconds: float) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(self_host.time, "sleep", stop_after_readiness)

    report = setup_example(
        ExampleSetupInput(
            app_url=f"http://localhost:{_WEB_PORT}/",
            username="synthetic-operator",
            password=SecretStr("synthetic-password"),
            mode=mode,
            confirm_download=False,
        ),
        runner=runner,
        write=events.append,
    )

    assert report.app_url == f"http://localhost:{_WEB_PORT}/"
    assert report.dataset_id is None
    assert read_dataset_role(root / "data" / "admin", "selected") is None
    assert "identity:bootstrap" in events

    commands = runner.calls
    interpreter = str(root / ".venv" / "bin" / "python")
    probe_index = next(
        index for index, command in enumerate(commands) if command[:2] == (interpreter, "-c")
    )
    model_index = next(
        index
        for index, command in enumerate(commands)
        if command[-2:] == ("scripts/mock_data.py", "load")
    )
    build_index = next(
        index
        for index, command in enumerate(commands)
        if command[-3:] == ("build", "db", "embedding")
    )
    assert probe_index < model_index
    assert probe_index < build_index
    assert any(command[-2:] == ("scripts/mock_data.py", "load") for command in commands)
    assert any(command[-2:] == ("scripts/mock_data.py", "write-artifacts") for command in commands)
    assert any("scripts/build_native.py" in command for command in commands)
    assert ("npm", "--prefix", "web", "run", "build") in commands
    assert ("npm", "--prefix", "web", "run", "solver:build") in commands
    assert ("npm", "--prefix", "admin-web", "run", "build") in commands
    assert commands.index(("npm", "--prefix", "web", "run", "build")) < commands.index(
        ("npm", "--prefix", "admin-web", "run", "build")
    )
    assert events.index("migrate") < events.index("artifact")
    assert events.index("artifact") < events.index("feedback")
    assert events.index("feedback") < events.index("http")

    if mode == "user":
        assert sorted(path.name for path in unit_directory.iterdir()) == sorted(
            (
                "course-explorer-checkout-user-web.service",
                "course-explorer-checkout-user-admin-web.service",
                "course-explorer-checkout-user-feedback-sender.service",
                "course-explorer-checkout-user-feedback-sender.timer",
            )
        )
        enabled = [
            command for command in commands if command[:3] == ("systemctl", "--user", "enable")
        ]
        site = editor.read_configuration_file("config/admin_web.toml").values
        assert site["ADMIN_SITE_WEB_SERVICE_UNIT"] == ("course-explorer-checkout-user-web.service")
        assert site["ADMIN_SITE_ADMIN_SERVICE_UNIT"] == (
            "course-explorer-checkout-user-admin-web.service"
        )
        assert site["ADMIN_SITE_WEB_SERVICE_SCOPE"] == "user"
        assert [command[-1] for command in enabled] == [
            "course-explorer-checkout-user-web.service",
            "course-explorer-checkout-user-admin-web.service",
        ]
    else:
        assert len(runner.children) == 2
        assert all(child.terminated and child.waited for child in runner.children)


def test_real_database_workflow_serves_an_empty_initial_selection(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The named owner creates and enrolls one empty database, builds before serving, and refuses a
    repeat."""
    root = _checkout(tmp_path, "checkout-real")
    _prepare_environment(monkeypatch, root)
    _prepare_host_files(root)
    self_host._copy_example_files(root)
    web_shell, admin_shell = _write_shells(root)
    runner = _Runner()
    events: list[str] = []
    artifact = [b'{"courses":[]}']
    identities = ["selected"]
    _bind_http(
        monkeypatch,
        web_shell=web_shell,
        admin_shell=admin_shell,
        artifact=artifact,
        identities=identities,
        events=events,
    )
    monkeypatch.setattr(self_host, "_require_native_libraries", lambda: None)
    # The artifact builder, the migration upgrade and the verification read are the substituted
    # boundaries.
    monkeypatch.setattr(
        self_host,
        "build_serving_artifacts",
        lambda settings, *, embedding: _build(settings),
    )
    monkeypatch.setattr(
        dataset_owner, "_run_migration_upgrade", lambda name: events.append("migrate")
    )
    monkeypatch.setattr(
        dataset_owner, "read_dataset_verification", lambda settings: sample_verification()
    )

    def _build(settings) -> None:
        events.append("build")
        _write_catalogue(root, settings, artifact[0])
        return None

    def stop_after_readiness(_seconds: float) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(self_host.time, "sleep", stop_after_readiness)

    name = "course_explorer_real_proof"
    report = setup_real_database(
        RealDatabaseSetupInput(database_name=name, mode="foreground"),
        runner=runner,
        write=events.append,
    )

    assert report.dataset_id == "0" * 32
    assert load_raw_database_settings().postgres_db == "course_explorer"
    assert name in runner.created
    assert runner.dropped == set()
    selected = resolve_dataset_role(root / "data" / "admin", "selected")
    assert selected.dataset_id == "0" * 32
    assert selected.database_name == name
    assert read_dataset_role(root / "data" / "admin", "working") is None
    assert events.index("build") < events.index("http")
    assert "identity:selected" in events

    created = len(runner.created)
    builds = events.count("build")
    requests = events.count("http")
    with pytest.raises(ValueError):
        setup_real_database(
            RealDatabaseSetupInput(database_name=name, mode="foreground"),
            runner=runner,
            write=events.append,
        )
    assert len(runner.created) == created
    assert events.count("build") == builds
    assert events.count("http") == requests
