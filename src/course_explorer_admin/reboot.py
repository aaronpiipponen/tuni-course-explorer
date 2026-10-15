"""One shared checkpoint clock and native Windows reboot handshake for worker GPU modes.

This module owns the two worker-lifecycle mechanics that the translation and inference remote
modes share but that no single stage may duplicate: the loaded-GPU checkpoint clock and the
Windows worker restart. The clock measures only elapsed time while an owned local GPU
runtime is loaded, including its between-unit dwell, accumulates across runtime switches and
same-WSL-boot pauses, and persists at completed atomic-unit checkpoints as well as at committed
failed-generation-attempt checkpoints (so repeated local rejections cannot starve the reboot
interval). The handshake reads the
native Windows boot identity, issues exactly one restart through the SSH/WSL transport,
and proves a changed Windows boot plus a healthy configured WSL before returning.

Both owners work from one per-session ``gpu-clock.json`` schema-1 record and the
transport/connection settings. The clock measures loaded-GPU dwell alone, and a restart is
claimed only after an observed boot change. It is worker-side: the persisted record is written
by whichever worker host runs the GPU mode.
"""

from __future__ import annotations

import subprocess
import time
from collections.abc import Callable
from pathlib import Path, PurePosixPath
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

from course_explorer.administration import (
    administrative_json,
    atomic_write_private_text,
    load_private_model,
)
from course_explorer.config import WorkerConnectionSettings, WorkerGpuRebootSettings
from course_explorer.datasets import DatasetId, DatasetRevision
from course_explorer.validation import require_finite_nonnegative
from course_explorer_admin import mechanics
from course_explorer_admin.transport import (
    SshWslTransport,
    WorkerAvailabilityError,
    WorkerConnectionLost,
    WorkerRecovery,
)

_CHECKPOINT_NAME = "gpu-clock.json"

# The fixed WSL kernel boot-id read.
_WSL_BOOT_ID_ARGV = ("cat", "/proc/sys/kernel/random/boot_id")


class WorkerGpuCheckpoint(BaseModel):
    """One frozen per-session sample of accumulated loaded-GPU seconds.

    It carries only the session/revision
    identity, the worker kernel boot the seconds belong to, and the finite nonnegative accumulated
    loaded-GPU seconds. The kernel boot id proves same-boot continuity. A different worker boot
    starts a fresh budget without rewriting this record until a real checkpoint.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    session_id: DatasetId
    revision: DatasetRevision
    boot_id: UUID
    loaded_seconds: float

    @field_validator("loaded_seconds")
    @classmethod
    def validate_loaded_seconds(cls, value: float) -> float:
        return require_finite_nonnegative(value, "loaded_seconds")


def _read_checkpoint(
    directory: Path, *, session_id: str, revision: str
) -> WorkerGpuCheckpoint | None:
    """Strictly load the one gpu-clock record, or ``None`` when absent.

    After the strict load it compares the record's session/revision identity once and refuses a
    foreign record. It writes nothing.
    """
    path = directory / _CHECKPOINT_NAME
    if path.is_symlink():
        raise ValueError("gpu clock record must not be a symlink")
    if not path.exists():
        return None
    checkpoint = load_private_model(path, WorkerGpuCheckpoint)
    if checkpoint.session_id != session_id or checkpoint.revision != revision:
        raise ValueError("gpu clock record identity does not match the session")
    return checkpoint


def worker_gpu_reboot_due(
    directory: Path,
    *,
    session_id: str,
    revision: str,
    settings: WorkerGpuRebootSettings,
) -> bool:
    """Report whether the saved sample proves this worker boot has reached the interval.

    The read writes nothing. An absent record means no loaded work and raises no error. A symlinked,
    malformed, or foreign-identity record refuses. A record from another worker boot
    reports not-due (its stored kernel boot id differs) without rewriting it.
    """
    checkpoint = _read_checkpoint(directory, session_id=session_id, revision=revision)
    if checkpoint is None:
        return False
    if checkpoint.boot_id != mechanics.current_boot_id():
        return False
    return checkpoint.loaded_seconds >= settings.worker_gpu_reboot_interval_minutes * 60


class WorkerGpuClock:
    """The one in-memory loaded-GPU clock that persists only at checkpoint samples.

    The constructor reuses same-boot saved seconds so a paused-then-resumed session resumes from them.
    A record from another boot supplies zero to this invocation and is not rewritten until a
    real GPU checkpoint. ``loaded``/``unloaded`` open and close one loaded segment, ``checkpoint``
    samples it and publishes the accumulated seconds at a completed atomic unit or a committed failed
    generation attempt, and ``due`` is latched only from the last published sample, never a running
    wall-clock test.
    """

    def __init__(
        self,
        directory: Path,
        *,
        session_id: str,
        revision: str,
        settings: WorkerGpuRebootSettings,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._directory = directory
        self._session_id = session_id
        self._revision = revision
        self._settings = settings
        self._monotonic = monotonic
        self._seconds = 0.0
        self._segment_start: float | None = None
        self._due = False
        checkpoint = _read_checkpoint(directory, session_id=session_id, revision=revision)
        if checkpoint is not None and checkpoint.boot_id == mechanics.current_boot_id():
            self._seconds = checkpoint.loaded_seconds

    def loaded(self) -> None:
        """Open one loaded segment at now, only when none is already open."""
        if self._segment_start is None:
            self._segment_start = self._monotonic()

    def unloaded(self) -> None:
        """Close the open loaded segment once and publish nothing.

        Repeated calls with no open segment are no-ops, so neither a repeated runtime stop nor an
        unloaded/CPU/external-route dwell ever double-counts or publishes a checkpoint.
        """
        if self._segment_start is None:
            return
        self._seconds += max(0.0, self._monotonic() - self._segment_start)
        self._segment_start = None

    def checkpoint(self) -> None:
        """Sample the open loaded segment and publish the accumulated seconds.

        A checkpoint with no open loaded segment returns without publishing. When loaded, it adds
        the segment delta and reopens the segment at the same sample instant, so consecutive
        checkpoints never double-count. Callers invoke it at a completed atomic unit and after a
        committed failed generation attempt.
        """
        if self._segment_start is None:
            return
        now = self._monotonic()
        self._seconds += max(0.0, now - self._segment_start)
        self._segment_start = now
        self._publish()
        self._due = self._seconds >= self._settings.worker_gpu_reboot_interval_minutes * 60

    @property
    def due(self) -> bool:
        """Report whether the last published checkpoint sample reached the interval."""
        return self._due

    def _publish(self) -> None:
        checkpoint = WorkerGpuCheckpoint(
            schema_version=1,
            session_id=self._session_id,
            revision=self._revision,
            boot_id=mechanics.current_boot_id(),
            loaded_seconds=self._seconds,
        )
        atomic_write_private_text(
            self._directory / _CHECKPOINT_NAME, administrative_json(checkpoint)
        )


def _bounded_timeout(
    deadline: float, monotonic: Callable[[], float], connect_timeout: int
) -> float:
    """Return the smaller of the connect bound and the remaining recovery budget."""
    remaining = deadline - monotonic()
    if remaining <= 0:
        return 0.0
    return min(float(connect_timeout), remaining)


def _native_transient(exc: Exception) -> bool:
    """Report whether a native command failure is an expected severed-connection observation."""
    if isinstance(exc, subprocess.TimeoutExpired):
        return True
    return isinstance(exc, subprocess.CalledProcessError) and exc.returncode == 255


def _wsl_healthy(
    transport: SshWslTransport,
    connection: WorkerConnectionSettings,
    *,
    timeout: float,
    recovery: WorkerRecovery,
) -> bool:
    """Prove a healthy configured WSL by reading and parsing its kernel boot id.

    Only a classified availability loss (the shell never reported a completed command) is an
    expected not-ready observation within the bounded recovery. A completed command failure,
    protocol error, or malformed boot id is a real output error and propagates. A valid parsed UUID
    boot id is the health proof.
    """
    try:
        raw = transport.run(
            _WSL_BOOT_ID_ARGV,
            cwd=PurePosixPath(str(connection.worker_project_root)),
            timeout=timeout,
        )
    except WorkerAvailabilityError as exc:
        recovery.last_returncode = exc.returncode
        return False
    try:
        UUID(raw.decode("ascii").strip())
    except (UnicodeDecodeError, ValueError) as exc:
        raise RuntimeError("worker WSL boot id is not a UUID") from exc
    return True


def reboot_windows_worker(
    transport: SshWslTransport,
    connection: WorkerConnectionSettings,
    *,
    run_allowed: Callable[[], bool],
    recovery: WorkerRecovery | None = None,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> bool:
    """Read the Windows boot before the restart, issue one restart, and prove a different boot plus healthy WSL.

    The boot before the restart is read first, then ``run_allowed`` is rechecked immediately before
    the single irreversible request. A denied control returns ``False`` without issuing anything.
    After the request, the one shared recovery deadline (the configured stop timeout) bounds every
    probe: a different Windows boot and a parsed UUID WSL boot id must both be observed, or a fixed
    :class:`WorkerConnectionLost` is raised. A request that severs its SSH connection (exit 255 or
    timeout) continues only to this mandatory boot proof. Once the request is issued the bounded
    health observation finishes even if a pause/stop arrives. This owner does not re-arm or launch
    work for that pending control.
    """
    if recovery is None:
        recovery = WorkerRecovery(
            connection, run_allowed=run_allowed, sleep=sleep, monotonic=monotonic
        )
    deadline = recovery.begin()
    connect_timeout = connection.ssh_connect_timeout_seconds

    while True:
        if not run_allowed():
            return False
        attempt_timeout = _bounded_timeout(deadline, monotonic, connect_timeout)
        if attempt_timeout <= 0:
            raise WorkerConnectionLost(recovery.last_returncode) from None
        try:
            old_boot = transport.read_windows_boot_id(timeout=attempt_timeout)
            break
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError) as exc:
            if not _native_transient(exc):
                raise
            recovery.last_returncode = _native_returncode(exc)
            remaining = deadline - monotonic()
            if remaining <= 0:
                raise WorkerConnectionLost(recovery.last_returncode) from None
            sleep(min(connection.poll_interval_seconds, remaining))
    if not run_allowed():
        return False
    reboot_timeout = _bounded_timeout(deadline, monotonic, connect_timeout)
    if reboot_timeout <= 0:
        raise WorkerConnectionLost(recovery.last_returncode) from None
    try:
        transport.request_windows_reboot(timeout=reboot_timeout)
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError) as exc:
        if not _native_transient(exc):
            raise
        recovery.last_returncode = _native_returncode(exc)
        # The reboot may have severed its own connection. Only the boot proof may claim success.
    interval = connection.poll_interval_seconds
    while True:
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise WorkerConnectionLost(recovery.last_returncode) from None
        probe_timeout = min(float(connect_timeout), remaining)
        try:
            new_boot = transport.read_windows_boot_id(timeout=probe_timeout)
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError) as exc:
            if not _native_transient(exc):
                raise
            recovery.last_returncode = _native_returncode(exc)
            new_boot = None
        if new_boot is not None and new_boot != old_boot:
            remaining = deadline - monotonic()
            if remaining > 0 and _wsl_healthy(
                transport,
                connection,
                timeout=min(float(connect_timeout), remaining),
                recovery=recovery,
            ):
                return True
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise WorkerConnectionLost(recovery.last_returncode) from None
        sleep(min(interval, remaining))


def _native_returncode(exc: Exception) -> int | None:
    """Return the available native subprocess status, or ``None`` for a timeout."""
    if isinstance(exc, subprocess.CalledProcessError):
        return exc.returncode
    return None
