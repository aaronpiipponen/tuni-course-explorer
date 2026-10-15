"""Contracts for controller status, paths, and SSH/WSL transport."""

from __future__ import annotations

import hashlib
import shlex
import subprocess
from pathlib import Path, PurePosixPath

import pytest

from course_explorer.administration import sha256_file
from course_explorer.config import WorkerConnectionSettings
from course_explorer_admin import mechanics
from course_explorer_admin.transport import (
    SshWslTransport,
    WorkerAvailabilityError,
    WorkerCommandError,
)

SESSION_ID = "0123456789abcdef0123456789abcdef"
_SUCCESS_MARKER = b"COURSE_EXPLORER_TRANSPORT_RESULT command 0\n"


def controller_settings(
    worker_project_root: str = "/home/test-user/tuni-course-explorer",
) -> WorkerConnectionSettings:
    return WorkerConnectionSettings(
        TRANSLATION_CONTROLLER_SSH_TARGET="test-worker",
        TRANSLATION_CONTROLLER_SSH_CONNECT_TIMEOUT_SECONDS=10,
        TRANSLATION_CONTROLLER_WSL_DISTRIBUTION="Ubuntu-24.04",
        TRANSLATION_CONTROLLER_WORKER_PROJECT_ROOT=worker_project_root,
        TRANSLATION_CONTROLLER_HEALTH_INTERVAL_SECONDS=2,
        TRANSLATION_CONTROLLER_STOP_TIMEOUT_SECONDS=660,
    )


class RecordingRunner:
    """Records every argv and returns scripted stdout or executes the real local wrapper.

    In the default mode each reported command returns a valid zero completion record. With
    ``execute_local_wrapper`` the wrapper's cmd caret escaping stands in for the external
    Windows/SSH envelope: the escaping is reversed, its generated bash script is extracted, and the
    script runs through the real local ``SubprocessRunner`` so the actual completion protocol is
    exercised end to end.
    """

    def __init__(
        self, outputs: list[bytes] | None = None, *, execute_local_wrapper: bool = False
    ) -> None:
        self.calls: list[tuple[tuple[str, ...], dict]] = []
        self.outputs = list(outputs or [])
        self.popen_writes: list[tuple[Path, bytes]] = []
        self.execute_local_wrapper = execute_local_wrapper
        self._real = mechanics.SubprocessRunner()

    def _execute_wrapper(self, command: tuple[str, ...]):
        window = command[-1].replace("^", "")
        marker = "bash -lc "
        index = window.index(marker) + len(marker)
        script = shlex.split(window[index:])[0]
        return self._real.run(("bash", "-lc", script))

    def run(self, argv, *, cwd=None, env=None, stdin_path=None, stdout_path=None, timeout=None):
        command = tuple(argv)
        self.calls.append((command, {"cwd": cwd, "env": env, "stdin_path": stdin_path}))
        if self.execute_local_wrapper:
            return self._execute_wrapper(command)
        output = self.outputs.pop(0) if self.outputs else b""
        if stdout_path is not None:
            Path(stdout_path).write_bytes(output)
        return subprocess.CompletedProcess(list(argv), 0, stdout=output, stderr=_SUCCESS_MARKER)

    def popen(
        self,
        argv,
        *,
        cwd=None,
        env=None,
        stdin_path=None,
        stdout_path,
        stderr_path,
        start_new_session=False,
    ):
        self.calls.append(
            (
                tuple(argv),
                {
                    "cwd": cwd,
                    "env": env,
                    "stdin_path": stdin_path,
                    "stdout_path": stdout_path,
                    "stderr_path": stderr_path,
                    "start_new_session": start_new_session,
                },
            )
        )

        class Process:
            pid = 4321

            def poll(self):
                return None

            def wait(self, timeout=None):
                return 0

            def terminate(self):
                return None

        return Process()


def test_upload_reuses_only_exact_matching_remote_file(tmp_path: Path) -> None:
    """Default upload rejects a destination that exists. Reuse matches only exact digest."""
    source = tmp_path / "import-receipt.json"
    source.write_bytes(b"receipt-bytes")
    destination = PurePosixPath("/home/test-user/state/s/import-receipt.json")

    default_runner = RecordingRunner([b""])
    default_transport = SshWslTransport(default_runner, controller_settings())
    default_transport.upload(source, destination)
    assert len(default_runner.calls) == 2
    assert default_runner.calls[1][1]["stdin_path"] == source

    matching_runner = RecordingRunner([b"matching\n"])
    matching_transport = SshWslTransport(matching_runner, controller_settings())
    matching_transport.upload(source, destination, reuse_matching=True)
    assert len(matching_runner.calls) == 1
    preflight_script = matching_runner.calls[0][0][-1]
    assert f"= {sha256_file(source)}" in preflight_script
    assert str(destination) not in " ".join(matching_runner.calls[0][0][:-1])

    mismatch_runner = RecordingRunner([b"foreign\n"])
    mismatch_transport = SshWslTransport(mismatch_runner, controller_settings())
    with pytest.raises(ValueError):
        mismatch_transport.upload(source, destination, reuse_matching=True)
    assert len(mismatch_runner.calls) == 1

    # Every remote command is a quoted argv over SSH BatchMode with validated config values.
    runner = RecordingRunner([b"ok"])
    transport = SshWslTransport(runner, controller_settings())
    output = transport.run(
        (
            "uv",
            "run",
            "python",
            "-m",
            "course_explorer_admin.translation.controller_worker",
            "status",
        ),
        cwd=PurePosixPath("/home/test-user/tuni-course-explorer"),
        env={"POSTGRES_DB": "course_translation_worker_" + SESSION_ID},
    )
    assert output == b"ok"
    argv, _ = runner.calls[0]
    assert "BatchMode=yes" in argv
    assert "ConnectTimeout=10" in argv
    assert "test-worker" in argv
    script = argv[6]
    assert "course-search" not in script
    assert "uv run python -m course_explorer_admin.translation.controller_worker status" in script
    assert "POSTGRES_DB=course_translation_worker_" + SESSION_ID in script

    # The generated wrapper preserves payload stdout and reports exit classification.
    transport = SshWslTransport(
        RecordingRunner(execute_local_wrapper=True), controller_settings(str(tmp_path))
    )
    assert (
        transport.run(
            ("printf", "payload-out"),
            cwd=PurePosixPath(str(tmp_path)),
        )
        == b"payload-out"
    )

    # Synthetic payload stderr without a trailing newline cannot swallow the completion record:
    # a successful payload returns its stdout and is classified as success.
    assert (
        transport.run(
            ("bash", "-c", "printf 'warn' >&2; printf payload-out"),
            cwd=PurePosixPath(str(tmp_path)),
        )
        == b"payload-out"
    )

    # A completed helper that exits 255 with unterminated stderr (as a real helper would) is a
    # command failure, not availability loss.
    with pytest.raises(WorkerCommandError) as failure:
        transport.run(
            ("bash", "-c", "printf 'bad' >&2; exit 255"),
            cwd=PurePosixPath(str(tmp_path)),
        )
    assert failure.value.returncode == 255
    assert failure.value.phase == "command"

    # A missing working directory fails during bootstrap, before the payload runs.
    missing_root = tmp_path / "missing"
    missing = SshWslTransport(
        RecordingRunner(execute_local_wrapper=True), controller_settings(str(missing_root))
    )
    with pytest.raises(WorkerCommandError) as bootstrap:
        missing.run(
            ("printf", "x"),
            cwd=PurePosixPath(str(missing_root)),
        )
    assert bootstrap.value.phase == "bootstrap"

    # A nonzero result with no completion record is availability loss, not a completed failure.
    class UnavailableRunner:
        def run(self, argv, **kwargs):
            return subprocess.CompletedProcess(list(argv), 1, stdout=b"", stderr=b"")

    with pytest.raises(WorkerAvailabilityError) as unavailable:
        SshWslTransport(UnavailableRunner(), controller_settings(str(tmp_path))).run(
            ("printf", "x"),
            cwd=PurePosixPath(str(tmp_path)),
        )
    assert unavailable.value.returncode == 1


def test_streamed_transfer_preserves_hash_and_never_captures_payload(tmp_path: Path) -> None:
    """Uploads flow through stdin and downloads through files without payload in argv."""
    runner = RecordingRunner([b"", b"ok"])
    transport = SshWslTransport(runner, controller_settings())
    source = tmp_path / "code.bundle"
    payload = b"binary-payload-" + b"x" * 32
    source.write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()

    transport.upload(
        source, PurePosixPath("/home/test-user/tuni-course-explorer/state/s/code.bundle")
    )
    upload_call = runner.calls[-1]
    assert upload_call[1]["stdin_path"] == source
    joined = " ".join(upload_call[0])
    assert payload.decode() not in joined

    destination = tmp_path / "downloaded.bin"
    destination.parent.mkdir(exist_ok=True)

    class Process:
        pid = 1

        def __init__(self, path: Path, content: bytes, returncode: int) -> None:
            self._path = path
            self._content = content
            self._returncode = returncode

        def wait(self, timeout=None):
            self._path.write_bytes(self._content)
            return self._returncode

    def popen(argv, *, cwd=None, env=None, stdin_path=None, stdout_path, stderr_path):
        runner.calls.append((tuple(argv), {"cwd": cwd, "env": env, "stdin_path": stdin_path}))
        # A completed stream always carries the transport completion record on its mode-0600 stderr.
        Path(stderr_path).write_bytes(b"COURSE_EXPLORER_TRANSPORT_RESULT command 0\n")
        return Process(Path(stdout_path), payload, 0)

    runner.popen = popen  # type: ignore[method-assign]
    runner.outputs = [b"ok"]
    transport.download(PurePosixPath("/remote/output.json"), destination)
    assert destination.read_bytes() == payload
    assert sha256_file(destination) == digest
    assert oct(destination.stat().st_mode & 0o777) == "0o600"

    # A failed stream preserves the destination, removes its temporary, and raises availability
    # with the available subprocess status instead of a completed-helper failure.
    existing = tmp_path / "existing.bin"
    existing.write_bytes(b"prior-bytes")

    def failing_popen(argv, *, cwd=None, env=None, stdin_path=None, stdout_path, stderr_path):
        runner.calls.append((tuple(argv), {"cwd": cwd, "env": env, "stdin_path": stdin_path}))
        Path(stderr_path).write_bytes(b"ssh: connect to host test-worker: connection reset\n")
        return Process(Path(stdout_path), b"partial-bytes", 255)

    runner.popen = failing_popen  # type: ignore[method-assign]
    runner.outputs = [b"ok"]
    with pytest.raises(WorkerAvailabilityError) as failure:
        transport.download(PurePosixPath("/remote/output.json"), existing)
    assert failure.value.returncode == 255
    assert existing.read_bytes() == b"prior-bytes"
    assert not any(path.name.endswith(".part") for path in tmp_path.iterdir())
    # The transient download protocol log is consumed once by classification and then removed.
    assert not any(path.name.endswith(".download.log") for path in tmp_path.iterdir())


def test_keepalive_detaches_with_configured_identity_and_mode_0600_streams(tmp_path: Path) -> None:
    """The keepalive launches the owned SSH argv detached with mode-0600 log streams."""
    runner = RecordingRunner([b"ready\n"])
    transport = SshWslTransport(runner, controller_settings())
    stdout_path = tmp_path / "keepalive.log"
    stderr_path = tmp_path / "keepalive.log"

    pid = transport.start_keepalive(SESSION_ID, stdout_path=stdout_path, stderr_path=stderr_path)

    assert pid == 4321
    argv, options = runner.calls[0]
    assert "BatchMode=yes" in argv
    assert "test-worker" in argv
    script = argv[6]
    assert f"exec -a course-explorer-worker-{SESSION_ID}-keepalive sleep infinity" in script
    assert options["stdout_path"] == stdout_path
    assert options["stderr_path"] == stderr_path
    assert options["start_new_session"] is True
    assert options["stdin_path"] is None


def test_keepalive_stop_signals_only_the_exact_owned_process(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Liveness/stop match the exact recorded argv. Dead and reused PIDs are never signalled."""
    # Derive the expected owned argv from a real launch over a throwaway transport, so the
    # transport under test holds no retained handle and exercises the command-line ownership path.
    helper_runner = RecordingRunner()
    helper = SshWslTransport(helper_runner, controller_settings())
    log_path = tmp_path / "keepalive.log"
    helper.start_keepalive(SESSION_ID, stdout_path=log_path, stderr_path=log_path)
    expected = helper_runner.calls[-1][0]

    runner = RecordingRunner()
    transport = SshWslTransport(runner, controller_settings())
    cmdline = "\0".join(expected).encode() + b"\0"
    signals: list[int] = []

    assert transport.keepalive_is_alive(SESSION_ID, None) is False

    monkeypatch.setattr("os.kill", lambda pid, sig: signals.append(sig) if sig else None)
    monkeypatch.setattr(Path, "read_bytes", lambda self: cmdline)
    assert transport.keepalive_is_alive(SESSION_ID, 4321) is True

    # A live mismatched PID raises and is never signalled.
    monkeypatch.setattr(Path, "read_bytes", lambda self: b"other\0argv\0")
    with pytest.raises(ValueError):
        transport.keepalive_is_alive(SESSION_ID, 4321)
    assert signals == []

    # A dead process is already stopped and is never signalled.
    received: list[tuple[int, int]] = []

    def dead_kill(pid: int, sig: int) -> None:
        received.append((pid, sig))
        raise ProcessLookupError

    monkeypatch.setattr("os.kill", dead_kill)
    transport.stop_keepalive(SESSION_ID, 4321, sleep=lambda seconds: None)
    assert received and all(sig == 0 for _pid, sig in received)

    # A live reused PID fails loudly instead of being signalled.
    monkeypatch.setattr("os.kill", lambda pid, sig: None)
    monkeypatch.setattr(Path, "read_bytes", lambda self: b"foreign\0process\0")
    with pytest.raises(ValueError):
        transport.stop_keepalive(SESSION_ID, 4321, sleep=lambda seconds: None)

    # A matching live keepalive receives SIGTERM and is boundedly waited for.
    monkeypatch.setattr(Path, "read_bytes", lambda self: cmdline)
    alive = {"count": 0}

    def kill(pid: int, sig: int) -> None:
        if sig != 0:
            signals.append(sig)
        else:
            alive["count"] += 1
            if alive["count"] > 1:
                raise ProcessLookupError

    monkeypatch.setattr("os.kill", kill)
    transport.stop_keepalive(SESSION_ID, 4321, sleep=lambda seconds: None)
    assert signals == [15]


class ScriptedKeepaliveProcess:
    """A retained keepalive handle whose first bounded wait times out and then exits."""

    pid = 4321

    def __init__(self) -> None:
        self.terminated = 0
        self.waits = 0
        self.kills = 0

    def poll(self):
        return None

    def terminate(self) -> None:
        self.terminated += 1

    def kill(self) -> None:
        self.kills += 1

    def wait(self, timeout=None) -> int:
        self.waits += 1
        if self.waits == 1:
            raise subprocess.TimeoutExpired(cmd="ssh", timeout=timeout)
        return 0


def test_keepalive_handle_timeout_preserves_owned_child_for_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed owned keepalive stop retains the handle. An ordinary retry reaps it."""
    runner = RecordingRunner()
    process = ScriptedKeepaliveProcess()
    runner.popen = lambda argv, **kwargs: process  # type: ignore[method-assign]
    transport = SshWslTransport(runner, controller_settings())
    stdout_path = tmp_path / "keepalive.log"
    pid = transport.start_keepalive(SESSION_ID, stdout_path=stdout_path, stderr_path=stdout_path)

    with pytest.raises(RuntimeError):
        transport.stop_keepalive(SESSION_ID, pid, sleep=lambda seconds: None)

    # No force-kill and no lost ownership: the exact handle is observed as live.
    assert process.kills == 0
    assert process.terminated == 1
    assert transport.keepalive_is_alive(SESSION_ID, pid) is True

    transport.stop_keepalive(SESSION_ID, pid, sleep=lambda seconds: None)
    assert process.kills == 0

    # The public observation proves the retained handle was released.
    def gone(pid: int, sig: int) -> None:
        raise ProcessLookupError

    monkeypatch.setattr("os.kill", gone)
    assert transport.keepalive_is_alive(SESSION_ID, pid) is False
    assert process.waits == 2
    assert process.terminated == 2


def test_transport_rejects_unapproved_environment_before_io() -> None:
    """An unallowlisted environment key is refused before any process action, content-free."""
    runner = RecordingRunner()
    transport = SshWslTransport(runner, controller_settings())
    secret_value = "synthetic-secret-value"
    environment = {"UNLISTED_SECRET_KEY": secret_value}

    with pytest.raises(ValueError) as excinfo:
        transport.run(
            ("printf", "ready"),
            cwd=PurePosixPath("/home/test-user/tuni-course-explorer"),
            env=environment,
        )
    assert runner.calls == []
    assert secret_value not in str(excinfo.value)
    assert "UNLISTED_SECRET_KEY" not in str(excinfo.value)
