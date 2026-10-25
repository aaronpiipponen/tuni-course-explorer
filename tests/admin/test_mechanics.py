"""Tests for the administrative request timer and shared process owners."""

from __future__ import annotations

import signal
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

from course_explorer_admin.mechanics import (
    SubprocessRunner,
    exclusive_action_lock,
    model_request_scope,
)


def test_model_request_scope_expires_and_restores_the_alarm() -> None:
    """A stalled body raises the safe transport timeout and leaves no armed timer behind."""
    with pytest.raises(httpx.ReadTimeout):
        with model_request_scope(0.05):
            time.sleep(1.0)
    assert signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0)

    # A normal request block disarms the timer before further work runs.
    with model_request_scope(1.0):
        pass
    assert signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0)


def test_exclusive_action_lock_rejects_concurrent_action(tmp_path: Path) -> None:
    """A second concurrent action fails. ``create=False`` never initializes state but contends."""
    root = tmp_path / "state"
    with exclusive_action_lock(root, controller_name="embedding"):
        assert root.is_dir()
        assert oct(root.stat().st_mode & 0o777) == "0o700"
        assert (root / "controller.lock").is_file()
        with pytest.raises(RuntimeError):
            with exclusive_action_lock(root, controller_name="embedding"):
                pytest.fail("second lock must not be acquired")

    with exclusive_action_lock(root, controller_name="embedding"):
        pass

    absent = tmp_path / "absent"
    with exclusive_action_lock(absent, controller_name="embedding", create=False):
        pass
    assert not absent.exists()

    before = (root / "controller.lock").stat()
    assert oct(before.st_mode & 0o777) == "0o600"
    with exclusive_action_lock(root, controller_name="embedding", create=False):
        with pytest.raises(RuntimeError):
            with exclusive_action_lock(root, controller_name="embedding", create=False):
                pytest.fail("read-only lock must still contend on an existing lock")
    after = (root / "controller.lock").stat()
    assert (before.st_ino, before.st_size, oct(after.st_mode & 0o777)) == (
        after.st_ino,
        after.st_size,
        oct(before.st_mode & 0o777),
    )


def test_subprocess_runner_popen_uses_devnull_mode_0600_logs_and_its_own_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A detached child gets DEVNULL stdin, mode-0600 append logs, and its own session."""
    stdout_path = tmp_path / "runner.out"
    stderr_path = tmp_path / "runner.err"
    script = "import os, sys; print(os.getsid(0) == os.getpid()); print(sys.stdin.read())"
    process = SubprocessRunner().popen(
        (sys.executable, "-c", script),
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        start_new_session=True,
    )
    assert process.wait() == 0
    assert stdout_path.read_text(encoding="utf-8").splitlines() == ["True", ""]
    assert stderr_path.read_text(encoding="utf-8") == ""
    assert oct(stdout_path.stat().st_mode & 0o777) == "0o600"
    assert oct(stderr_path.stat().st_mode & 0o777) == "0o600"

    # A repeated launch appends to the same mode-0600 log rather than truncating it.
    SubprocessRunner().popen(
        (sys.executable, "-c", "print('line')"),
        stdout_path=stdout_path,
        stderr_path=stderr_path,
    ).wait()
    assert stdout_path.read_text(encoding="utf-8") == "True\n\nline\n"

    # A model-style launch with ``inherit_environment=False`` receives only the explicit mapping.
    monkeypatch.setenv("SYNTHETIC_PARENT_ONLY", "parent-value")
    env_stdout = tmp_path / "env.out"
    env_stderr = tmp_path / "env.err"
    env_script = (
        "import os; "
        "print(os.environ.get('SYNTHETIC_EXPLICIT', 'missing')); "
        "print(os.environ.get('SYNTHETIC_PARENT_ONLY', 'absent'))"
    )
    env_process = SubprocessRunner().popen(
        (sys.executable, "-c", env_script),
        env={"SYNTHETIC_EXPLICIT": "explicit-value"},
        stdout_path=env_stdout,
        stderr_path=env_stderr,
        inherit_environment=False,
    )
    assert env_process.wait() == 0
    assert env_stdout.read_text(encoding="utf-8").splitlines() == ["explicit-value", "absent"]
    assert oct(env_stdout.stat().st_mode & 0o777) == "0o600"


def test_subprocess_runner_run_captures_output_and_honors_files(tmp_path: Path) -> None:
    """The foreground runner captures stdout and redirects it to a mode-0600 file on request."""
    completed = SubprocessRunner().run((sys.executable, "-c", "print('hello')"))
    assert completed.stdout == b"hello\n"

    destination = tmp_path / "captured.txt"
    SubprocessRunner().run((sys.executable, "-c", "print('redirected')"), stdout_path=destination)
    assert destination.read_text(encoding="utf-8") == "redirected\n"
    assert oct(destination.stat().st_mode & 0o777) == "0o600"

    with pytest.raises(subprocess.CalledProcessError):
        SubprocessRunner().run((sys.executable, "-c", "raise SystemExit(3)"))
