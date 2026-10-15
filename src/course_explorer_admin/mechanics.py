"""Neutral administrative process mechanics shared by the detached stage controllers.

This module is the one owner of the process-level mechanics that the
ingestion/embedding/translation controllers and their detached workers share: the request-scoped
elapsed-time timer used by a worker main thread, the production argv subprocess runner and its
protocol, process liveness, the ordered Compose command prefix, a non-blocking action lock, and the
common checkout/Compose/poll/projection/time helpers. Stage controllers own their own closed DTOs,
resource bits and cleanup rules and pass only already-validated settings and callbacks.
"""

from __future__ import annotations

import fcntl
import math
import os
import signal
import subprocess
import threading
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Literal, Protocol
from uuid import UUID

import httpx
from pydantic import BaseModel, ConfigDict, Field

# The one shared runtime pathspec every stage validates before starting a detached session. Its
# breadth prevents one stage from starting against a checkout modified by another stage's runtime file.
_RUNTIME_PATHS = (
    "src/",
    "scripts/",
    "config/",
    "pyproject.toml",
    "uv.lock",
    "migrations/",
    "docker-compose.yml",
    "docker/",
)

# The one shared five-action lifecycle vocabulary every administrative stage accepts. The remote
# controller re-exports this same type, so one literal is declared.
type ControllerAction = Literal["start", "pause", "resume", "status", "stop"]


@contextmanager
def model_request_scope(seconds: float) -> Iterator[None]:
    """Bound one HTTP request by an actual elapsed-time alarm on a worker main thread.

    A scalar HTTP read timeout is an inactivity timeout, so a slow keepalive/body trickle can
    outlive the configured request ceiling. This wraps only the request's HTTP I/O with a real-time
    alarm that raises the same safe transport error the client already handles on expiry. It must run
    on the process main thread, refuses to overlap an active real-time alarm, and always disarms
    and restores the handler before leaving the request so no subsequent database checkpoint, evidence
    write, model process launch or verified return ever runs under an armed timer.
    """
    if threading.current_thread() is not threading.main_thread():
        raise RuntimeError("model request scope must run on the main thread")
    if signal.getitimer(signal.ITIMER_REAL) != (0.0, 0.0):
        raise RuntimeError("model request scope requires no existing real-time alarm")
    if not math.isfinite(seconds) or seconds <= 0:
        raise ValueError("model request scope seconds must be finite and positive")
    previous_handler = signal.getsignal(signal.SIGALRM)

    def _expire(signum: int, frame: object) -> None:
        raise httpx.ReadTimeout("model request exceeded its configured timeout")

    signal.signal(signal.SIGALRM, _expire)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0.0)
        signal.signal(signal.SIGALRM, previous_handler)


def pid_is_alive(pid: int | None) -> bool:
    """Return whether a recorded process identifier exists."""
    if pid is None:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


_BOOT_ID_PATH = Path("/proc/sys/kernel/random/boot_id")


class OwnedProcessRecord(BaseModel):
    """One frozen ownership record binding an owned PID to its boot and exact argv."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal[1] = 1
    pid: int = Field(gt=0)
    argv: tuple[str, ...] = Field(min_length=1)
    boot_id: UUID


def current_boot_id() -> UUID:
    """Read the current kernel boot id, the only ownership proof this module accepts."""
    try:
        raw = _BOOT_ID_PATH.read_text(encoding="ascii").strip()
    except OSError as exc:
        raise RuntimeError("process ownership requires a readable kernel boot id") from exc
    try:
        return UUID(raw)
    except ValueError as exc:
        raise RuntimeError("kernel boot id is not a UUID") from exc


def read_process_command_line(pid: int) -> tuple[str, ...] | None:
    """Read one process's command line from ``/proc``. ``None`` when it has exited."""
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise ValueError("recorded process command line is not readable") from exc
    parts = raw.decode("utf-8", errors="surrogateescape").split("\0")
    if parts and parts[-1] == "":
        parts.pop()
    return tuple(parts)


def owned_process_is_alive(record: OwnedProcessRecord) -> bool:
    """Report whether a recorded process is the exact owned process.

    A record from a previous boot, a dead PID, or an absent/empty command line means the process
    has exited and is not live. A live process whose nonempty argv differs from the recorded argv has
    been reused: it fails loudly rather than being signalled. Only an exact argv match is live.
    This call observes liveness only. Signalling the process is a separate operation.
    """
    if record.boot_id != current_boot_id():
        return False
    command_line = read_process_command_line(record.pid)
    if command_line is None or not command_line:
        return False
    if command_line != record.argv:
        raise ValueError("recorded process is not the owned process")
    return True


def compose_prefix() -> tuple[str, ...]:
    """Return the exact Compose bridge prefix shared by both hosts.

    Every local and remote caller generates its own temporary environment-file bridge through
    ``course_explorer_admin.compose``.
    """
    return (
        "uv",
        "run",
        "--no-sync",
        "--offline",
        "--no-python-downloads",
        "python",
        "-m",
        "course_explorer_admin.compose",
        "--",
    )


@contextmanager
def exclusive_action_lock(
    root: Path, *, controller_name: str, create: bool = True, blocking: bool = False
) -> Iterator[None]:
    """Serialize one controller's actions with a single advisory lock.

    With ``create=True`` (the default for every mutating action) the mode-0700 state root and
    its mode-0600 lock file are created when absent. With ``create=False`` a read-only action takes
    the same lock only when an initialized controller already published it: an absent root or lock
    yields immediately, leaving the filesystem untouched, and a regular lock file is opened and
    flocked directly.
    ``blocking=True`` waits for the lock. ``blocking=False`` fails loudly. Short server-state writers
    (lifecycle read-modify-writes, spawn publication) use it to serialize the one state file. The
    same flag also lets a reconnect retry wait behind an already-running idempotent worker helper
    at the worker export and named worker-action locks, so a temporary busy lock is not mistaken
    for a completed-helper failure.
    """
    lock_path = root / "controller.lock"
    if not create:
        if lock_path.is_symlink() or not lock_path.is_file():
            yield
            return
        descriptor = os.open(lock_path, os.O_RDWR)
    else:
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        try:
            operation = fcntl.LOCK_EX if blocking else fcntl.LOCK_EX | fcntl.LOCK_NB
            fcntl.flock(descriptor, operation)
        except OSError as exc:
            raise RuntimeError(
                f"another {controller_name} controller action is already running"
            ) from exc
        yield
    finally:
        os.close(descriptor)


class ProcessRunner(Protocol):
    """Process boundary used for every local administrative command."""

    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: Path | None = None,
        env: Mapping[str, str] | None = None,
        stdin_path: Path | None = None,
        stdout_path: Path | None = None,
        timeout: float | None = None,
    ) -> subprocess.CompletedProcess[bytes]: ...

    def run_interactive(
        self,
        argv: Sequence[str],
        *,
        cwd: Path | None = None,
        env: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> None: ...

    def popen(
        self,
        argv: Sequence[str],
        *,
        cwd: Path | None = None,
        env: Mapping[str, str] | None = None,
        stdin_path: Path | None = None,
        stdout_path: Path,
        stderr_path: Path,
        start_new_session: bool = False,
        inherit_environment: bool = True,
    ) -> subprocess.Popen[bytes]: ...


class SubprocessRunner:
    """Production process runner over argv lists with no shell and streaming file handles."""

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
        """Run one argv command to completion, checking its status."""
        merged = os.environ if env is None else {**os.environ, **env}
        stdin_handle = None
        stdout_handle = None
        try:
            if stdin_path is not None:
                stdin_handle = stdin_path.open("rb")
            if stdout_path is not None:
                stdout_handle = os.fdopen(
                    os.open(stdout_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "wb"
                )
            return subprocess.run(
                list(argv),
                cwd=None if cwd is None else str(cwd),
                env=merged,
                stdin=stdin_handle,
                stdout=stdout_handle if stdout_handle is not None else subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
                timeout=timeout,
            )
        finally:
            if stdin_handle is not None:
                stdin_handle.close()
            if stdout_handle is not None:
                stdout_handle.close()

    def run_interactive(
        self,
        argv: Sequence[str],
        *,
        cwd: Path | None = None,
        env: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> None:
        """Run one command with inherited terminal streams and a checked status.

        Reserved for explicit setup/update steps that must let sudo, an installer, or a build
        prompt on the real terminal. It captures nothing, merges the process environment, and
        never feeds, logs, or rewrites input.
        """
        merged = os.environ if env is None else {**os.environ, **env}
        subprocess.run(
            list(argv),
            cwd=None if cwd is None else str(cwd),
            env=merged,
            check=True,
            timeout=timeout,
        )

    def popen(
        self,
        argv: Sequence[str],
        *,
        cwd: Path | None = None,
        env: Mapping[str, str] | None = None,
        stdin_path: Path | None = None,
        stdout_path: Path,
        stderr_path: Path,
        start_new_session: bool = False,
        inherit_environment: bool = True,
    ) -> subprocess.Popen[bytes]:
        """Start one argv command detached from terminal streams when requested.

        With ``start_new_session=True`` the child becomes its own session leader so closing
        the invoking shell cannot deliver a hangup to long-running background work. Without
        an input path stdin is ``DEVNULL``. Stdout and stderr are appended to mode-0600
        files. ``inherit_environment=True`` (the default) merges the process
        environment. ``False`` passes exactly the supplied mapping, so a model child launches
        with a closed allowlist.
        """
        merged = os.environ if env is None else {**os.environ, **env}
        if not inherit_environment:
            merged = dict(env or {})
        stdin_handle = stdin_path.open("rb") if stdin_path is not None else subprocess.DEVNULL
        stdout_handle = os.fdopen(
            os.open(stdout_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600), "wb"
        )
        stderr_handle = os.fdopen(
            os.open(stderr_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600), "wb"
        )
        try:
            return subprocess.Popen(
                list(argv),
                cwd=None if cwd is None else str(cwd),
                env=merged,
                stdin=stdin_handle,
                stdout=stdout_handle,
                stderr=stderr_handle,
                start_new_session=start_new_session,
            )
        finally:
            if stdin_path is not None:
                stdin_handle.close()
            stdout_handle.close()
            stderr_handle.close()


# A bytes-returning Compose execution callback: local stages bind a subprocess runner, the remote
# translation stage binds its SSH/WSL helper. It adapts the real bytes-versus-CompletedProcess
# seams without a second transport.
type ComposeCommand = Callable[[Sequence[str]], bytes]


def read_prepared_checkout(
    run: Callable[[Sequence[str]], bytes], *, full_tree: bool = False
) -> tuple[str, str]:
    """Read a non-detached branch, cleanliness, and HEAD from one checkout command runner.

    ``run`` executes one git argv in the checkout and returns captured stdout bytes. With
    ``full_tree=False`` cleanliness is limited to the shared runtime pathspec every stage
    validates before a detached session. With ``full_tree=True`` it covers the whole checkout
    including untracked files, which explicit setup/update requires. Returns ``(branch, HEAD)``.
    """
    branch = run(("git", "branch", "--show-current")).decode().strip()
    if not branch:
        raise ValueError("prepared checkout requires a non-detached Git branch")
    if full_tree:
        dirty = run(("git", "status", "--porcelain", "--untracked-files=normal")).decode()
        if dirty.strip():
            raise ValueError("prepared checkout requires a clean full tree")
    else:
        dirty = run(
            ("git", "status", "--porcelain", "--untracked-files=no", "--", *_RUNTIME_PATHS)
        ).decode()
        if dirty.strip():
            raise ValueError("controller start requires clean runtime paths")
    revision = run(("git", "rev-parse", "HEAD")).decode().strip()
    if len(revision) != 40 or any(character not in "0123456789abcdef" for character in revision):
        raise ValueError("controller start requires a 40-character lowercase revision")
    return branch, revision


def require_prepared_checkout(runner: ProcessRunner, root: Path) -> tuple[str, str]:
    """Require a non-detached branch, a clean shared runtime checkout, and return (branch, HEAD)."""
    return read_prepared_checkout(lambda argv: runner.run(tuple(argv), cwd=root).stdout)


def runtime_checkout_directory(revision: str) -> Path:
    """Return the one convention-owned local llama.cpp checkout directory for a runtime revision."""
    return Path.home() / ".local" / "src" / f"llama.cpp-{revision}"


def running_compose_services(run: ComposeCommand) -> set[str]:
    """Return the Compose services reported running."""
    output = run((*compose_prefix(), "ps", "--services", "--status", "running"))
    return {line.strip() for line in output.decode().splitlines() if line.strip()}


def ensure_prepared_services(
    run: ComposeCommand,
    services: Sequence[str],
    *,
    on_starting: Callable[[set[str]], None] | None = None,
) -> set[str]:
    """Start already-built Compose services and return the requested ones this call started.

    Services that are already running are left untouched. The start uses no build and no pull, so
    it can only reuse an already-provisioned image, and every requested service must be running
    afterwards or the caller fails loudly rather than continuing against a partial stack. When
    supplied, ``on_starting`` is notified once with the requested services absent before startup,
    before ``up`` runs, so a caller can record ownership even if startup then fails.
    """
    requested = set(services)
    before = running_compose_services(run)
    if not requested <= before:
        if on_starting is not None:
            on_starting(requested - before)
        run(
            (
                *compose_prefix(),
                "up",
                "-d",
                "--wait",
                "--no-build",
                "--pull",
                "never",
                *services,
            )
        )
    after = running_compose_services(run)
    missing = requested - after
    if missing:
        raise RuntimeError("prepared Compose services did not become healthy")
    return (after - before) & requested


def await_state[StateT](
    read: Callable[[], StateT],
    accepted: Callable[[StateT], bool],
    *,
    attempts: int,
    interval: float,
    sleep: Callable[[float], None],
    expired: Callable[[], bool] | None = None,
) -> StateT:
    """Read bounded state until ``accepted`` holds, then return it. Otherwise raise loudly.

    At most ``attempts`` reads run. Acceptance is checked first, then an optional expiry predicate.
    ``interval`` is slept only between reads. Exhaustion or expiry raises a fixed safe error rather
    than returning a stale last state, so a vanished or unacknowledged worker can never be reported
    as a successful startup or acknowledgement.
    """
    for attempt in range(attempts):
        state = read()
        if accepted(state):
            return state
        if expired is not None and expired():
            break
        if attempt + 1 < attempts:
            sleep(interval)
    raise RuntimeError("bounded state wait did not reach an accepted state")


def active_seconds(
    seconds: float, running_since: datetime | None, *, running: bool, now: datetime
) -> float:
    """Add the in-flight interval only for a live running process with a recorded start time.

    Offline time between checkpoints does not inflate throughput or ETA, and the durable base
    applies to every non-running lifecycle.
    """
    if running and running_since is not None:
        return seconds + (now - running_since).total_seconds()
    return seconds
