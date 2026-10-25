"""Contracts for the shared loaded-GPU checkpoint clock and Windows handshake.

These contracts drive the real ``course_explorer_admin.reboot`` owners over a virtual monotonic
clock and a synthetic process runner, proving the native command shapes, the boot-change
requirement, and the clock arithmetic.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from uuid import uuid4

import pytest

from course_explorer.administration import administrative_json, atomic_write_private_text
from course_explorer.config import WorkerConnectionSettings, WorkerGpuRebootSettings
from course_explorer_admin import mechanics
from course_explorer_admin.reboot import (
    WorkerGpuCheckpoint,
    WorkerGpuClock,
    reboot_windows_worker,
    worker_gpu_reboot_due,
)
from course_explorer_admin.transport import SshWslTransport, WorkerConnectionLost

SESSION_ID = "0123456789abcdef0123456789abcdef"


class VirtualMonotonic:
    """A monotonic clock whose value only moves when the test advances or sleeps it."""

    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def reboot_settings(*, minutes: int = 1) -> WorkerGpuRebootSettings:
    return WorkerGpuRebootSettings(WORKER_GPU_REBOOT_INTERVAL_MINUTES=minutes)


def connection(tmp_path: Path, *, stop_timeout: float = 60.0) -> WorkerConnectionSettings:
    return WorkerConnectionSettings(
        TRANSLATION_CONTROLLER_SSH_TARGET="test-worker",
        TRANSLATION_CONTROLLER_SSH_CONNECT_TIMEOUT_SECONDS=10,
        TRANSLATION_CONTROLLER_WSL_DISTRIBUTION="Ubuntu-24.04",
        TRANSLATION_CONTROLLER_WORKER_PROJECT_ROOT=str(tmp_path / "worker"),
        TRANSLATION_CONTROLLER_HEALTH_INTERVAL_SECONDS=0.01,
        TRANSLATION_CONTROLLER_STOP_TIMEOUT_SECONDS=stop_timeout,
    )


def read_checkpoint(directory: Path) -> WorkerGpuCheckpoint:
    return WorkerGpuCheckpoint.model_validate_json(
        (directory / "gpu-clock.json").read_text(encoding="utf-8")
    )


def test_gpu_clock_counts_only_loaded_checkpoint_time_and_survives_same_boot_resume(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The clock excludes unloaded dwell, samples only at checkpoints, and keeps same-boot time."""
    directory = tmp_path / "session"
    directory.mkdir()
    clock = VirtualMonotonic()
    subject = WorkerGpuClock(
        directory,
        session_id=SESSION_ID,
        settings=reboot_settings(),
        monotonic=clock,
    )
    assert subject.due is False

    # Two loaded() calls do not open a second segment. 30 loaded seconds stay below the interval.
    subject.loaded()
    subject.loaded()
    clock.advance(30)
    subject.checkpoint()
    assert read_checkpoint(directory).loaded_seconds == 30
    assert (
        worker_gpu_reboot_due(directory, session_id=SESSION_ID, settings=reboot_settings()) is False
    )
    # A repeated checkpoint at the same instant never double-counts.
    subject.checkpoint()
    assert read_checkpoint(directory).loaded_seconds == 30

    # Unloaded dwell is excluded and repeated unloaded calls are no-ops.
    subject.unloaded()
    subject.unloaded()
    clock.advance(1000)
    subject.checkpoint()
    assert read_checkpoint(directory).loaded_seconds == 30

    # Reloading accumulates only the reload's loaded segment and crosses the interval.
    subject.loaded()
    clock.advance(40)
    subject.checkpoint()
    assert subject.due is True
    assert read_checkpoint(directory).loaded_seconds == 70
    assert (
        worker_gpu_reboot_due(directory, session_id=SESSION_ID, settings=reboot_settings()) is True
    )

    # A fresh same-boot invocation reuses saved seconds but latches due only after a checkpoint.
    retained = WorkerGpuClock(
        directory,
        session_id=SESSION_ID,
        settings=reboot_settings(),
        monotonic=clock,
    )
    assert retained.due is False
    retained.loaded()
    clock.advance(1)
    retained.checkpoint()
    assert retained.due is True
    assert read_checkpoint(directory).loaded_seconds == 71

    # The due read is read-only and writes nothing.
    before = (directory / "gpu-clock.json").read_bytes()
    assert (
        worker_gpu_reboot_due(directory, session_id=SESSION_ID, settings=reboot_settings()) is True
    )
    assert (directory / "gpu-clock.json").read_bytes() == before

    # A different worker boot starts a fresh budget without rewriting the saved record.
    monkeypatch.setattr(mechanics, "current_boot_id", lambda: uuid4())
    assert (
        worker_gpu_reboot_due(directory, session_id=SESSION_ID, settings=reboot_settings()) is False
    )
    assert (directory / "gpu-clock.json").read_bytes() == before
    fresh = WorkerGpuClock(
        directory,
        session_id=SESSION_ID,
        settings=reboot_settings(),
        monotonic=clock,
    )
    assert fresh.due is False

    # A foreign session record refuses in both the read and the constructor.
    foreign = WorkerGpuCheckpoint(
        schema_version=1,
        session_id="f" * 32,
        boot_id=mechanics.current_boot_id(),
        loaded_seconds=120,
    )
    atomic_write_private_text(directory / "gpu-clock.json", administrative_json(foreign))
    foreign_before = (directory / "gpu-clock.json").read_bytes()
    with pytest.raises(ValueError):
        worker_gpu_reboot_due(directory, session_id=SESSION_ID, settings=reboot_settings())
    with pytest.raises(ValueError):
        WorkerGpuClock(
            directory,
            session_id=SESSION_ID,
            settings=reboot_settings(),
            monotonic=clock,
        )
    assert (directory / "gpu-clock.json").read_bytes() == foreign_before


class ScriptedBootRunner:
    """Synthetic process runner for the native Windows and WSL boot probes.

    Native boot/reboot commands run through the reported-wrapper-free native path. The WSL boot-id
    probe is a reported wrapper, so a healthy read supplies the transport completion record on
    stderr and an unavailable WSL returns a nonzero result with no record.
    """

    def __init__(
        self,
        *,
        windows_boot: str = "111",
        wsl_boot: str | None = "00000000-0000-4000-8000-000000000001",
        change_windows_boot: bool = True,
        native_timeouts: int = 0,
        wsl_failures: int = 0,
    ) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.envs: list[object] = []
        self.windows_boot = windows_boot
        self.wsl_boot = wsl_boot
        self.change_windows_boot = change_windows_boot
        self.native_timeouts = native_timeouts
        self.wsl_failures = wsl_failures
        self.reboot_requests = 0

    def run(self, argv, *, cwd=None, env=None, stdin_path=None, stdout_path=None, timeout=None):
        command = tuple(argv)
        self.calls.append(command)
        self.envs.append(env)
        last = command[-1]
        if last.startswith("powershell.exe"):
            if self.native_timeouts > 0:
                self.native_timeouts -= 1
                raise subprocess.TimeoutExpired(list(command), timeout)
            return subprocess.CompletedProcess(
                list(command), 0, stdout=(self.windows_boot + "\n").encode(), stderr=b""
            )
        if last == "shutdown.exe /r /t 0":
            self.reboot_requests += 1
            if self.change_windows_boot:
                self.windows_boot = "222"
            return subprocess.CompletedProcess(list(command), 0, stdout=b"", stderr=b"")
        if self.wsl_boot is None or self.wsl_failures > 0:
            if self.wsl_failures > 0:
                self.wsl_failures -= 1
            # A pre-shell WSL failure: nonzero with no transport completion record.
            return subprocess.CompletedProcess(list(command), 1, stdout=b"", stderr=b"")
        return subprocess.CompletedProcess(
            list(command),
            0,
            stdout=(self.wsl_boot + "\n").encode(),
            stderr=b"COURSE_EXPLORER_TRANSPORT_RESULT command 0\n",
        )


def test_windows_reboot_requires_changed_boot_and_healthy_wsl(tmp_path: Path) -> None:
    """The native request proves a different Windows boot plus a parsed UUID WSL boot id."""
    settings = connection(tmp_path)
    runner = ScriptedBootRunner()
    transport = SshWslTransport(runner, settings)

    assert (
        reboot_windows_worker(transport, settings, run_allowed=lambda: True, sleep=lambda _s: None)
        is True
    )
    assert runner.reboot_requests == 1

    # The boot query is one fixed native command with no sourced environment.
    assert all(env is None for env in runner.envs)

    # The restart is exactly one native request without the forced-shutdown flag.
    shutdown = [call for call in runner.calls if call[-1] == "shutdown.exe /r /t 0"]
    assert len(shutdown) == 1
    assert "/f" not in shutdown[0][-1]

    # A transient native timeout on the old-boot read is retried within the same shared deadline.
    timed = ScriptedBootRunner(native_timeouts=1)
    timed_transport = SshWslTransport(timed, settings)
    assert (
        reboot_windows_worker(
            timed_transport, settings, run_allowed=lambda: True, sleep=lambda _s: None
        )
        is True
    )
    assert timed.reboot_requests == 1

    # An initial native timeout whose bounded sleep consumes the whole episode raises and
    # issues zero restarts: an expired budget is never replayed into the irreversible request.
    clock = VirtualMonotonic()
    exhausted_settings = connection(tmp_path, stop_timeout=0.01)
    exhausted = ScriptedBootRunner(native_timeouts=1)
    exhausted_transport = SshWslTransport(exhausted, exhausted_settings)
    with pytest.raises(WorkerConnectionLost):
        reboot_windows_worker(
            exhausted_transport,
            exhausted_settings,
            run_allowed=lambda: True,
            sleep=clock.advance,
            monotonic=clock,
        )
    assert exhausted.reboot_requests == 0

    # Control withdrawn during the initial retry sleep returns False and issues zero restarts.
    clock = VirtualMonotonic()
    allowed = {"value": True}
    withdrawn = ScriptedBootRunner(native_timeouts=1)
    withdrawn_transport = SshWslTransport(withdrawn, settings)

    def withdraw(seconds: float) -> None:
        allowed["value"] = False
        clock.advance(seconds)

    assert (
        reboot_windows_worker(
            withdrawn_transport,
            settings,
            run_allowed=lambda: allowed["value"],
            sleep=withdraw,
            monotonic=clock,
        )
        is False
    )
    assert withdrawn.reboot_requests == 0
    # Admission was rechecked before the retry read: only the initial old-boot probe ran.
    assert sum(1 for call in withdrawn.calls if call[-1].startswith("powershell.exe")) == 1

    # Transient non-255 WSL unavailability is an expected not-ready observation, then healthy.
    flaky = ScriptedBootRunner(wsl_failures=1)
    flaky_transport = SshWslTransport(flaky, settings)
    clock = VirtualMonotonic()
    assert (
        reboot_windows_worker(
            flaky_transport,
            settings,
            run_allowed=lambda: True,
            sleep=clock.advance,
            monotonic=clock,
        )
        is True
    )
    assert flaky.reboot_requests == 1

    # An identical Windows boot expires the bounded recovery without claiming success.
    clock = VirtualMonotonic()
    stuck = ScriptedBootRunner(change_windows_boot=False)
    stuck_transport = SshWslTransport(stuck, settings)
    with pytest.raises(WorkerConnectionLost):
        reboot_windows_worker(
            stuck_transport,
            settings,
            run_allowed=lambda: True,
            sleep=clock.advance,
            monotonic=clock,
        )
    assert stuck.reboot_requests == 1

    # A changed boot with WSL not ready also expires.
    clock = VirtualMonotonic()
    unhealthy = ScriptedBootRunner(wsl_boot=None)
    unhealthy_transport = SshWslTransport(unhealthy, settings)
    with pytest.raises(WorkerConnectionLost):
        reboot_windows_worker(
            unhealthy_transport,
            settings,
            run_allowed=lambda: True,
            sleep=clock.advance,
            monotonic=clock,
        )

    # A denied control issues zero restarts.
    denied = ScriptedBootRunner()
    denied_transport = SshWslTransport(denied, settings)
    assert (
        reboot_windows_worker(
            denied_transport, settings, run_allowed=lambda: False, sleep=lambda _s: None
        )
        is False
    )
    assert denied.reboot_requests == 0
