"""Contracts for the web process environment handoff and the supervisor's worker and router child
wiring."""

from __future__ import annotations

import errno
import os
import signal
import socket
from pathlib import Path

import pytest

from course_explorer import configuration
from course_explorer.config import (
    ENVIRONMENT_ONLY_SETTINGS_SOURCE,
    SETTINGS_SOURCE_MARKER,
    AdmissionSettings,
    DatabaseSettings,
    EmbeddingSettings,
    SearchSettings,
    WebSettings,
)
from course_explorer_web import __main__ as entry_point
from course_explorer_web import launch
from course_explorer_web.dataset import SERVING_GENERATION_ENV
from tests.support import settings_factory, write_example_config_tree

_EMBEDDING_ALIASES = frozenset(
    field.validation_alias
    for field in EmbeddingSettings.model_fields.values()
    if isinstance(field.validation_alias, str)
)


class _Child:
    """One process boundary double that reports an exit code and records its signal.

    A child started with an inherited readiness pipe owns a duplicate of its write end. It writes
    the readiness byte once and releases the duplicate, or releases it when it exits or receives a
    signal, so the supervisor observes the same descriptor lifetime a real process produces.
    """

    def __init__(self, code: int | None, readiness_fd: int | None = None) -> None:
        self.code = code
        self.signal_number: int | None = None
        self._readiness_fd = readiness_fd

    def signal_ready(self) -> None:
        """Write the readiness byte and release the child's copy of the pipe."""
        if self._readiness_fd is not None:
            os.write(self._readiness_fd, b"1")
            self._release_readiness()

    def exit(self, code: int) -> None:
        """Record an exit and release the child's copy of the pipe without reporting readiness."""
        self.code = code
        self._release_readiness()

    def poll(self) -> int | None:
        return self.code

    def terminate(self) -> None:
        self.signal_number = signal.SIGTERM
        if self.code is None:
            self.code = -signal.SIGTERM
        self._release_readiness()

    def kill(self) -> None:
        self.signal_number = signal.SIGKILL
        self.code = -signal.SIGKILL
        self._release_readiness()

    def wait(self, timeout: float | None = None) -> int:
        return -1 if self.code is None else self.code

    def _release_readiness(self) -> None:
        if self._readiness_fd is not None:
            os.close(self._readiness_fd)
            self._readiness_fd = None


@pytest.mark.parametrize("embeddings_enabled", (False, True), ids=("off", "on"))
def test_web_launcher_excludes_operator_credentials(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, embeddings_enabled: bool
) -> None:
    """Hand only the required web aliases and the marker to a file-free child process."""
    root = tmp_path / "checkout"
    write_example_config_tree(root, include_derived=embeddings_enabled)
    local = root / ".env"
    local.write_text("POSTGRES_PASSWORD=synthetic-database-password\n", encoding="utf-8")
    local.chmod(0o600)
    monkeypatch.setattr(configuration, "repository_root", lambda: root)
    configuration.clear_configuration_caches()

    class ExecCaptured(Exception):
        pass

    observed: dict[str, str] = {}

    def capture_exec(_executable: str, _arguments: list[str], environment: dict[str, str]) -> None:
        observed.update(environment)
        raise ExecCaptured

    monkeypatch.setattr(os, "execve", capture_exec)
    monkeypatch.setattr(
        os,
        "environ",
        {
            "HOME": "/home/test",
            "PATH": "/usr/bin",
            "LANG": "C.UTF-8",
            "WEB_EMBEDDINGS_ENABLED": "1" if embeddings_enabled else "0",
            "WEB_INFERENCE_ENABLED": "1",
            "TRANSLATION_CONTROLLER_SSH_TARGET": "synthetic-worker",
            "SSH_AUTH_SOCK": "/tmp/synthetic-agent.sock",
            "UNRELATED_SECRET": "synthetic-unrelated-secret",
        },
    )

    with pytest.raises(ExecCaptured):
        launch.main()

    assert observed["POSTGRES_PASSWORD"] == "synthetic-database-password"
    assert observed["WEB_HOST"] == "127.0.0.1"
    assert observed["WEB_PORT"] == "8037"
    assert observed["WEB_WORKERS"] == "2"
    assert observed["WEB_EMBEDDINGS_ENABLED"] == ("1" if embeddings_enabled else "0")
    assert observed["WEB_INFERENCE_ENABLED"] == "1"
    assert observed["ADMISSION_ENABLED"] == "0"
    assert {"HOME", "PATH", "LANG"} <= observed.keys()
    assert observed[SETTINGS_SOURCE_MARKER] == ENVIRONMENT_ONLY_SETTINGS_SOURCE
    assert (
        not {
            "TRANSLATION_CONTROLLER_SSH_TARGET",
            "SSH_AUTH_SOCK",
            "UNRELATED_SECRET",
        }
        & observed.keys()
    )
    # A site without embedding features hands over no embedding alias at all, so its child can
    # compose no embedding family and needs no hub artifact.
    if embeddings_enabled:
        assert "EMBEDDING_HUB_VECTOR" in observed
    else:
        assert not _EMBEDDING_ALIASES & observed.keys()

    # The captured child environment reconstructs its families without reopening any local file
    # and can never reach a worker or unrelated secret.
    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("the child environment must not read configuration files")

    monkeypatch.setattr(configuration, "read_public_configuration", forbidden)
    monkeypatch.setattr(configuration, "read_local_configuration", forbidden)
    monkeypatch.setattr(os, "environ", observed)
    assert DatabaseSettings().postgres_password.get_secret_value() == (
        "synthetic-database-password"
    )
    assert observed["WEB_RESPAWN_EXIT_LIMIT"] == "3"
    assert observed["WEB_RESPAWN_WINDOW_SECONDS"] == "60"
    assert WebSettings().web_port == 8037
    assert WebSettings().web_workers == 2
    assert WebSettings().web_respawn_exit_limit == 3
    assert WebSettings().web_respawn_window_seconds == 60
    assert WebSettings().embeddings_enabled is embeddings_enabled
    assert WebSettings().inference_enabled is True
    assert AdmissionSettings().admission_enabled is False
    # The handoff carries the search policy for one query embedding request as well.
    assert SearchSettings().search_embedding_request_timeout_seconds == 5
    assert SearchSettings().search_embedding_max_attempts == 1
    if embeddings_enabled:
        assert len(EmbeddingSettings().embedding_hub_vector) == 1024

    # Continue the same handoff through the actual entry point, binding only a temporary test port.
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    monkeypatch.setenv("WEB_PORT", str(port))
    monkeypatch.setenv(SERVING_GENERATION_ENV, "inherited-by-the-parent")
    spawned: list[dict[str, object]] = []
    worker_ports: list[int] = []
    router_ports: list[int] = []
    exiting_fd: list[int] = []
    pending_exit: list[_Child] = []
    router_started = False

    def spawn(command: list[str], **options: object) -> _Child:
        nonlocal router_started
        pass_fds = options["pass_fds"]
        environment = options["env"]
        assert isinstance(environment, dict)
        assert environment[SERVING_GENERATION_ENV] == os.environ[SERVING_GENERATION_ENV]
        assert environment[SERVING_GENERATION_ENV] != "inherited-by-the-parent"
        assert options["close_fds"] is True
        if command[2] == "course_explorer_web.router":
            public_fd = int(command[3])
            assert pass_fds == (public_fd,)
            with socket.fromfd(public_fd, socket.AF_INET, socket.SOCK_STREAM) as listener:
                assert listener.getsockname() == ("127.0.0.1", port)
                assert listener.getsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY) == 1
                assert listener.getsockopt(socket.SOL_SOCKET, socket.SO_ACCEPTCONN) == 1
            router_ports.extend(int(value) for value in command[4:])
            router_started = True
            for pending in pending_exit:
                pending.code = 3
            child = _Child(None)
        else:
            assert command[2] == "course_explorer_web.worker"
            listener_fd = int(command[3])
            readiness_fd = int(command[4])
            assert pass_fds == (listener_fd, readiness_fd)
            with socket.fromfd(listener_fd, socket.AF_INET, socket.SOCK_STREAM) as listener:
                address = listener.getsockname()
                assert address[0] == "127.0.0.1"
                assert address[1] != 0
                worker_ports.append(address[1])
            if not exiting_fd:
                exiting_fd.append(listener_fd)
            child = _Child(None, os.dup(readiness_fd))
            if listener_fd == exiting_fd[0]:
                if router_started:
                    child.code = 3
                else:
                    pending_exit.append(child)
            # The worker reports completed startup before its first exit, which models a process
            # that finished binding and then failed.
            child.signal_ready()
        spawned.append({"command": command, "child": child, **options})
        return child

    monkeypatch.setattr(entry_point.subprocess, "Popen", spawn)
    monkeypatch.setattr(entry_point, "_POLL_SECONDS", 0.0)
    assert entry_point.main() == 3
    commands = [entry["command"] for entry in spawned]
    # Every worker starts first and the router starts only after both report readiness, so the
    # crash loop of one worker begins with a running router.
    assert [command[2] for command in commands] == [
        "course_explorer_web.worker",
        "course_explorer_web.worker",
        "course_explorer_web.router",
        "course_explorer_web.worker",
        "course_explorer_web.worker",
    ]
    # The first worker slot exits three times and is replaced twice on its own descriptor, while
    # the router and the second worker keep their single process until the unit stops.
    worker_fds = [command[3] for command in commands if command[2] != "course_explorer_web.router"]
    first_worker_fd = str(exiting_fd[0])
    assert worker_fds[0] == first_worker_fd
    assert worker_fds[1] != first_worker_fd
    assert worker_fds[2:] == [first_worker_fd, first_worker_fd]
    assert len(set(worker_fds)) == 2
    assert len(worker_ports) == 4
    assert worker_ports[0] == worker_ports[2] == worker_ports[3]
    assert worker_ports[1] != worker_ports[0]
    assert router_ports == worker_ports[:2]
    router = spawned[2]["child"]
    second_worker = spawned[1]["child"]
    assert isinstance(router, _Child)
    assert isinstance(second_worker, _Child)
    assert router.signal_number == signal.SIGTERM
    assert second_worker.signal_number == signal.SIGTERM


def test_web_router_waits_for_all_workers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Start the router only when every worker's own readiness pipe reports completed startup."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    settings = settings_factory(WebSettings, WEB_WORKERS="2", WEB_PORT=str(port))
    monkeypatch.setattr(entry_point, "load_web_settings", lambda: settings)
    monkeypatch.setenv(SERVING_GENERATION_ENV, "inherited-by-the-parent")

    original_listener = entry_point._listener
    public_listeners: list[socket.socket] = []

    def record_listener(host: str, listener_port: int) -> socket.socket:
        listener = original_listener(host, listener_port)
        if listener_port == port:
            public_listeners.append(listener)
        return listener

    monkeypatch.setattr(entry_point, "_listener", record_listener)

    original_pipe = os.pipe
    created_pipes: list[tuple[int, int]] = []

    def record_pipe() -> tuple[int, int]:
        pair = original_pipe()
        created_pipes.append(pair)
        return pair

    monkeypatch.setattr(os, "pipe", record_pipe)

    commands: list[list[str]] = []
    workers: list[_Child] = []

    def spawn(command: list[str], **options: object) -> _Child:
        pass_fds = options["pass_fds"]
        if command[2] == "course_explorer_web.router":
            assert pass_fds == (int(command[3]),)
            child = _Child(None)
        else:
            assert command[2] == "course_explorer_web.worker"
            assert pass_fds == (int(command[3]), int(command[4]))
            child = _Child(None, os.dup(int(command[4])))
            workers.append(child)
        commands.append(command)
        return child

    monkeypatch.setattr(entry_point.subprocess, "Popen", spawn)

    poll_steps = 0

    def poll_once(_seconds: float) -> None:
        nonlocal poll_steps
        poll_steps += 1
        router_commands = [command for command in commands if command[2].endswith(".router")]
        if poll_steps == 1:
            # The public socket accepts from bind, and the router is absent while the second
            # worker has not reported readiness.
            assert len(public_listeners) == 1
            assert public_listeners[0].getsockopt(socket.SOL_SOCKET, socket.SO_ACCEPTCONN) == 1
            assert not router_commands
            workers[0].signal_ready()
            workers[1].exit(3)
        elif poll_steps == 2:
            # The replacement carries a fresh pipe, so the predecessor's readiness is gone.
            assert len(workers) == 3
            assert not router_commands
        elif poll_steps == 3:
            assert len(workers) == 3
            assert not router_commands
            workers[2].signal_ready()
        else:
            assert router_commands
            os.kill(os.getpid(), signal.SIGTERM)

    monkeypatch.setattr(entry_point.time, "sleep", poll_once)
    assert entry_point.main() == 0
    assert len([command for command in commands if command[2].endswith(".router")]) == 1
    # The first worker reported readiness before the exit-before-startup replacement appeared,
    # and every parent pipe descriptor is released when the unit stops.
    assert created_pipes
    for read_fd, write_fd in created_pipes:
        for descriptor in (read_fd, write_fd):
            with pytest.raises(OSError) as closed:
                os.fstat(descriptor)
            assert closed.value.errno == errno.EBADF
