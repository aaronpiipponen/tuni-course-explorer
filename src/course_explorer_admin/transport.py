"""Neutral SSH/WSL command, file, and keepalive transport for administrative worker sessions.

This module owns the one SSH-over-WSL command and file transport used by the translation and
inference controllers and their worker-side helpers. It receives only a validated
:class:`WorkerConnectionSettings` base and a process runner, and it validates every session id
through the shared dataset-id type. Environment overrides are restricted to a closed allowlist of
worker keys.
"""

from __future__ import annotations

import base64
import os
import re
import shlex
import signal
import subprocess
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import TypeAdapter

from course_explorer.administration import sha256_file
from course_explorer.config import WorkerConnectionSettings
from course_explorer.datasets import DatasetId
from course_explorer_admin.mechanics import ProcessRunner

_ENVIRONMENT_KEY_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_CMD_METACHARACTERS = frozenset('&|<>^()"')
_SESSION_ID = TypeAdapter(DatasetId)

# The closed set of environment keys a caller may override on a worker helper invocation: the stage
# state roots, the derived database name, the selected-dataset switch, the one GPU detection flag,
# and the one validated checkpoint-reboot interval.
_WORKER_ENVIRONMENT_ALLOWLIST = frozenset(
    {
        "POSTGRES_DB",
        "SELECTED_DATASET_ENABLED",
        "ADMIN_STATE_ROOT",
        "TRANSLATION_CONTROLLER_STATE_ROOT",
        "INFERENCE_CONTROLLER_STATE_ROOT",
        "HSA_ENABLE_DXG_DETECTION",
        "WORKER_GPU_REBOOT_INTERVAL_MINUTES",
    }
)

# The one closed control record every reported wrapper emits exactly once on its stderr. The
# payload is a fixed phase word and a decimal exit status.
_TRANSPORT_RESULT_PATTERN = re.compile(
    rb"^COURSE_EXPLORER_TRANSPORT_RESULT (bootstrap|command) ([0-9]+)$"
)


class WorkerCommandError(subprocess.CalledProcessError):
    """A remote invocation reached the shell and reported a terminal failure.

    It retains only the decimal exit status the remote shell observed and the closed phase
    (``bootstrap`` before the payload starts, ``command`` once it has), so it is safe to log across
    the administrative boundary.
    """

    def __init__(self, returncode: int, *, phase: Literal["bootstrap", "command"]) -> None:
        super().__init__(returncode, [])
        self.phase = phase


class WorkerAvailabilityError(RuntimeError):
    """A remote invocation did not reach a reportable completion: connection or WSL unavailable.

    ``returncode`` is the observed SSH/WSL exit status when one was available, otherwise ``None``
    (for example a transport timeout).
    """

    def __init__(self, returncode: int | None) -> None:
        super().__init__("worker transport did not complete the remote invocation")
        self.returncode = returncode


class WorkerConnectionLost(WorkerAvailabilityError):
    """A bounded recovery episode expired without restoring the worker connection."""


class WorkerRecoveryCancelled(RuntimeError):
    """A recovery episode was cancelled because live run intent was withdrawn."""


class WorkerRecovery:
    """One shared in-memory retry-admission budget for a single recovery episode.

    The budget is the configured stop timeout, initialized once on the first availability failure.
    It admits retries only for transient availability loss, and only while the optional live
    run-intent callback allows starting work. Every sequential step gets one ordinary first
    invocation even after a long transfer uses up this budget. Only that step's retries consult the
    shared deadline.
    """

    last_returncode: int | None

    def __init__(
        self,
        connection: WorkerConnectionSettings,
        *,
        run_allowed: Callable[[], bool] | None = None,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._connection = connection
        self._run_allowed = run_allowed
        self._sleep = sleep
        self._monotonic = monotonic
        self._deadline: float | None = None
        self.last_returncode = None

    def begin(self) -> float:
        """Initialize the one shared deadline once and return it."""
        if self._deadline is None:
            self._deadline = self._monotonic() + self._connection.stop_timeout_seconds
        return self._deadline

    def remaining(self) -> float:
        """Return seconds left in the one shared deadline, or infinity before it is initialized."""
        if self._deadline is None:
            return float("inf")
        return self._deadline - self._monotonic()

    def _require_admission(self) -> None:
        if self._run_allowed is not None and not self._run_allowed():
            raise WorkerRecoveryCancelled()

    def call[ResultT](self, operation: Callable[[], ResultT]) -> ResultT:
        """Invoke one operation, retrying only transient availability loss within the budget."""
        self._require_admission()
        while True:
            try:
                return operation()
            except WorkerConnectionLost:
                raise
            except WorkerAvailabilityError as exc:
                self.last_returncode = exc.returncode
                deadline = self.begin()
                self._require_admission()
                remaining = deadline - self._monotonic()
                if remaining > 0:
                    self._sleep(min(self._connection.poll_interval_seconds, remaining))
                    self._require_admission()
                    remaining = deadline - self._monotonic()
                if remaining <= 0:
                    raise WorkerConnectionLost(self.last_returncode) from None


class SshWslTransport:
    """One SSH/WSL command and file transport for controller sessions."""

    def __init__(self, runner: ProcessRunner, settings: WorkerConnectionSettings) -> None:
        self._runner = runner
        self._settings = settings
        self._keepalive: subprocess.Popen[bytes] | None = None

    def _remote_command(self, script: str) -> str:
        distribution = self._settings.wsl_distribution
        command = f"wsl.exe -d {distribution} -- bash -lc {shlex.quote(script)}"
        # Windows OpenSSH hands the remote command to cmd.exe before wsl.exe sees it, so cmd
        # metacharacters must be caret-escaped or they are consumed before bash -lc runs.
        return "".join(
            f"^{character}" if character in _CMD_METACHARACTERS else character
            for character in command
        )

    def _ssh_argv(self, script: str) -> tuple[str, ...]:
        return self._host_ssh_argv(self._remote_command(script))

    def _host_ssh_argv(self, command: str) -> tuple[str, ...]:
        """Return one SSH argv carrying a native host command under the configured target.

        This is the shared SSH prefix every WSL wrapper and the two native Windows methods
        build on.
        """
        return (
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            f"ConnectTimeout={self._settings.ssh_connect_timeout_seconds}",
            self._settings.ssh_target,
            command,
        )

    def read_windows_boot_id(self, *, timeout: float) -> str:
        """Read the native Windows last-boot identity over the SSH target.

        The fixed PowerShell script is sent as one UTF-16LE/base64 ``-EncodedCommand``, and its
        stripped stdout is returned as a canonical positive decimal
        integer. Missing, non-ASCII-decimal, or nonpositive output fails with a fixed safe error.
        The read is the method's only transport action.
        """
        script = (
            "$ErrorActionPreference='Stop'; "
            "(Get-CimInstance Win32_OperatingSystem).LastBootUpTime.ToUniversalTime().Ticks"
        )
        encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
        argv = self._host_ssh_argv(
            "powershell.exe -NoLogo -NoProfile -NonInteractive -EncodedCommand " + encoded
        )
        stdout = self._runner.run(argv, timeout=timeout).stdout
        try:
            text = stdout.decode("ascii", errors="strict").strip()
        except UnicodeDecodeError as exc:
            raise RuntimeError("Windows boot identity is not a positive decimal integer") from exc
        if not text or not text.isdigit():
            raise RuntimeError("Windows boot identity is not a positive decimal integer")
        value = int(text, 10)
        if value <= 0:
            raise RuntimeError("Windows boot identity is not a positive decimal integer")
        return str(value)

    def request_windows_reboot(self, *, timeout: float) -> None:
        """Issue exactly one native Windows restart without forcing and without WSL detachment."""
        argv = self._host_ssh_argv("shutdown.exe /r /t 0")
        self._runner.run(argv, timeout=timeout)

    def _wrapper(
        self,
        argv: Sequence[str],
        cwd: PurePosixPath,
        env: Mapping[str, str] | None,
        *,
        detached: bool,
        output_path: PurePosixPath | None,
    ) -> str:
        # Install the result trap before cwd so a bootstrap failure is reported too. The payload
        # runs in a subshell, so its own EXIT traps/exit/exec cannot replace this outer trap, and
        # the parent's exit status is the payload's. A leading newline frames the record
        # independently of arbitrary payload stderr, which may lack a final newline. The marker is
        # never parsed out of that stderr. The worker's own Python and Compose read its checkout
        # TOML and ignored .env automatically, so the wrapper sources no configuration.
        lines: list[str] = [
            "__ce_phase=bootstrap",
            (
                "trap '__ce_status=$?; printf "
                '"\\nCOURSE_EXPLORER_TRANSPORT_RESULT %s %d\\n" '
                '"$__ce_phase" "$__ce_status" >&2\' EXIT'
            ),
            "set -euo pipefail",
            f"cd {shlex.quote(str(cwd))}",
            'export PATH="$HOME/.local/bin:$PATH"',
        ]
        for key, value in (env or {}).items():
            if _ENVIRONMENT_KEY_PATTERN.fullmatch(key) is None or (
                key not in _WORKER_ENVIRONMENT_ALLOWLIST
            ):
                # Content-free: the error omits the key and value.
                raise ValueError("worker environment overrides must be allowlisted identifiers")
            lines.append(f"export {key}={shlex.quote(value)}")
        inline_script = (
            argv[2] if len(argv) == 3 and argv[0] == "bash" and argv[1] == "-c" else None
        )
        if detached:
            if output_path is None:
                raise ValueError("detached commands require an output path")
            # `wsl.exe` tears down the launching process group when its launcher exits, so the
            # launching shell briefly outlives the detach to let the child re-parent over a fixed
            # short hold.
            payload = (
                f"umask 077; nohup {shlex.join(argv)} > {shlex.quote(str(output_path))} "
                "2>&1 </dev/null & sleep 1"
            )
        elif inline_script is not None:
            # Inline a wrapper-owned `bash -c` script, so Windows `cmd.exe` mangling cannot break
            # two layers of single-quote escaping.
            payload = inline_script
        else:
            payload = f"exec {shlex.join(argv)}"
        lines.append("__ce_phase=command")
        lines.append(f"( {payload} )")
        # `wsl.exe -d <distro> -- bash -lc <script>` on Windows corrupts embedded newlines,
        # so every wrapper is emitted as one semicolon-joined line before it is shell-quoted.
        return "; ".join(lines)

    def _keepalive_argv(self, session_id: str) -> tuple[str, ...]:
        """Derive the exact local SSH argv of one session's own keepalive process."""
        # Validate the id alone. No confined directory is derived or created here.
        _SESSION_ID.validate_python(session_id)
        script = f"exec -a {shlex.quote(self._keepalive_process_name(session_id))} sleep infinity"
        return self._ssh_argv(script)

    @staticmethod
    def _keepalive_process_name(session_id: str) -> str:
        return f"course-explorer-worker-{session_id}-keepalive"

    def start_keepalive(self, session_id: str, *, stdout_path: Path, stderr_path: Path) -> int:
        """Launch one detached local keepalive that holds the configured WSL distribution open.

        The child is its own session leader with no terminal streams, so it outlives the
        invoking shell and needs no operator terminal. Only the local SSH process is
        recorded. It owns the remote ``sleep infinity`` for the lifetime of the session. The
        exact ``Popen`` handle is retained so liveness and stop reads observe this child
        directly without re-deriving ownership from a numeric PID.
        """
        argv = self._keepalive_argv(session_id)
        process = self._runner.popen(
            argv,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            start_new_session=True,
        )
        if process.pid <= 0:
            raise RuntimeError("detached keepalive did not report a process identifier")
        self._keepalive = process
        return process.pid

    def _retained_keepalive(self, pid: int | None) -> subprocess.Popen[bytes] | None:
        """Return the retained keepalive handle only when it is exactly the recorded PID."""
        if pid is None or self._keepalive is None or self._keepalive.pid != pid:
            return None
        return self._keepalive

    def keepalive_is_alive(self, session_id: str, pid: int | None) -> bool:
        """Report whether a recorded PID is the exact owned keepalive process.

        When this transport holds the started child's handle, its actual exit
        observation (including an unreaped child) decides liveness and the handle is reaped.
        Only a retained orphan call yields ``False`` for a null or dead PID. A live PID whose
        command line differs from this session's keepalive is a reused PID, so this fails loudly
        like ``stop_keepalive``.
        """
        handle = self._retained_keepalive(pid)
        if handle is not None:
            if handle.poll() is not None:
                handle.wait()
                self._keepalive = None
                return False
            return True
        if pid is None:
            return False
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            pass
        if not self._cmdline_matches(pid, self._keepalive_argv(session_id)):
            raise ValueError("recorded keepalive process identifier is not owned by this session")
        return True

    def stop_keepalive(
        self,
        session_id: str,
        pid: int | None,
        *,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        """Terminate only the exact recorded keepalive process and wait for it to exit.

        A retained handle is terminated and waited, reaping an already-exited child. An absent
        orphan process is already stopped. A live orphan whose command line differs from this
        session's keepalive has a reused PID: the caller fails loudly.
        """
        if pid is None or not self.keepalive_is_alive(session_id, pid):
            return
        handle = self._retained_keepalive(pid)
        if handle is not None:
            if handle.poll() is None:
                handle.terminate()
                try:
                    handle.wait(timeout=self._settings.stop_timeout_seconds)
                except subprocess.TimeoutExpired:
                    # The child is the exact owned process: retain its handle so an ordinary retry
                    # observes and reaps it.
                    raise RuntimeError(
                        "owned keepalive process did not exit within the stop timeout"
                    ) from None
            else:
                handle.wait()
            self._keepalive = None
            return
        os.kill(pid, signal.SIGTERM)
        deadline = time.monotonic() + self._settings.stop_timeout_seconds
        interval = self._settings.poll_interval_seconds
        while time.monotonic() < deadline:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return
            except PermissionError:
                return
            sleep(interval)
        raise RuntimeError("owned keepalive process did not exit within the stop timeout")

    def terminate_remote_keepalive(self, session_id: str, *, timeout: float | None = None) -> None:
        """Terminate the exact named remote keepalive process, tolerating an absent one.

        Terminating the local SSH client alone leaves the remote ``sleep infinity`` running on the
        worker, so the one keepalive owner also kills the exact process by its anchored name. The
        anchored pattern matches only the ``exec -a`` argv of that session's keepalive. An absent
        process is a successful no-op.
        """
        _SESSION_ID.validate_python(session_id)
        name = self._keepalive_process_name(session_id)
        # ``pkill`` exits 1 when no process matched (a valid absent keepalive) and >1 on a real
        # error, which must fail loudly. The ``||`` stops the wrapper's
        # ``set -e`` from aborting on the valid no-match exit.
        script = f"pkill -f {shlex.quote('^' + name + ' ')} || test $? -le 1"
        self.run(
            ("bash", "-c", script),
            cwd=PurePosixPath(str(self._settings.worker_project_root)),
            timeout=timeout,
        )

    @staticmethod
    def _cmdline_matches(pid: int, expected: Sequence[str]) -> bool:
        """Return whether ``/proc/<pid>/cmdline`` is exactly the expected argv."""
        try:
            raw = Path(f"/proc/{pid}/cmdline").read_bytes()
        except OSError as exc:
            raise ValueError("owned process command line is not readable") from exc
        actual = raw.decode("utf-8", errors="surrogateescape").split("\0")
        if actual and actual[-1] == "":
            actual.pop()
        return tuple(actual) == tuple(expected)

    @staticmethod
    def _completion_markers(stderr: bytes) -> list[tuple[str, int]]:
        """Return every valid completion control record in captured stderr, in order."""
        markers: list[tuple[str, int]] = []
        for line in stderr.splitlines():
            match = _TRANSPORT_RESULT_PATTERN.fullmatch(line.strip())
            if match is not None:
                markers.append((match.group(1).decode("ascii"), int(match.group(2))))
        return markers

    @classmethod
    def _classify(cls, returncode: int, stderr: bytes) -> None:
        """Classify one reported wrapper result as success, executed failure, or availability loss.

        A completed helper failure (including a helper that itself exits 255) carries a valid
        nonzero terminal record and raises :class:`WorkerCommandError`. A checked nonzero subprocess
        result *without* a valid terminal record is an availability observation carrying the
        available SSH/WSL status. A successful subprocess must carry exactly one zero ``command``
        record. Any other protocol shape is a loud :class:`ValueError`.
        """
        markers = cls._completion_markers(stderr)
        if returncode == 0:
            if markers != [("command", 0)]:
                raise ValueError("worker transport completed without a valid result record")
            return
        if len(markers) > 1:
            raise ValueError("worker transport produced more than one result record")
        if markers:
            phase, status = markers[0]
            if status == 0:
                raise ValueError("worker transport exit status contradicts its result record")
            raise WorkerCommandError(status, phase=phase) from None  # type: ignore[arg-type]
        raise WorkerAvailabilityError(returncode) from None

    def _classify_call(self, completed: subprocess.CompletedProcess[bytes]) -> bytes:
        self._classify(completed.returncode, completed.stderr or b"")
        return completed.stdout

    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: PurePosixPath,
        env: Mapping[str, str] | None = None,
        stdin_path: Path | None = None,
        timeout: float | None = None,
    ) -> bytes:
        """Run one remote command and return its captured UTF-8/bytes stdout."""
        script = self._wrapper(
            argv,
            cwd,
            env,
            detached=False,
            output_path=None,
        )
        try:
            completed = self._runner.run(
                self._ssh_argv(script), stdin_path=stdin_path, timeout=timeout
            )
        except subprocess.TimeoutExpired:
            raise WorkerAvailabilityError(None) from None
        except subprocess.CalledProcessError as exc:
            self._classify(exc.returncode, exc.stderr or b"")
            raise
        return self._classify_call(completed)

    def start_detached(
        self,
        argv: Sequence[str],
        *,
        cwd: PurePosixPath,
        env: Mapping[str, str],
        output_path: PurePosixPath,
        timeout: float | None = None,
    ) -> None:
        """Start one remote command under nohup and wait only for the launcher to exit."""
        script = self._wrapper(
            argv,
            cwd,
            env,
            detached=True,
            output_path=output_path,
        )
        try:
            completed = self._runner.run(self._ssh_argv(script), timeout=timeout)
        except subprocess.TimeoutExpired:
            raise WorkerAvailabilityError(None) from None
        except subprocess.CalledProcessError as exc:
            self._classify(exc.returncode, exc.stderr or b"")
            raise
        self._classify(completed.returncode, completed.stderr or b"")

    def upload(
        self,
        source: Path,
        destination: PurePosixPath,
        *,
        reuse_matching: bool = False,
        timeout: float | None = None,
    ) -> None:
        """Stream one local file to a remote path under a remove-on-failure trap.

        With ``reuse_matching=True`` a regular non-symlink destination whose digest equals the
        local file is reused. Any other present destination is rejected. ``timeout`` bounds each
        transfer subprocess independently.
        """
        parent = destination.parent
        part = parent / (destination.name + ".part")
        if reuse_matching:
            preflight_script = (
                f"test -d {shlex.quote(str(parent))}; "
                f"test ! -e {shlex.quote(str(part))}; "
                f"if test -e {shlex.quote(str(destination))}; then "
                f"test -f {shlex.quote(str(destination))}; "
                f"test ! -L {shlex.quote(str(destination))}; "
                'test "$(sha256sum -- '
                f"{shlex.quote(str(destination))} | cut -d ' ' -f 1)\" = "
                f"{shlex.quote(sha256_file(source))}; "
                "printf 'matching\\n'; "
                "fi"
            )
        else:
            preflight_script = (
                f"test -d {shlex.quote(str(parent))} && "
                f"test ! -e {shlex.quote(str(destination))} && "
                f"test ! -e {shlex.quote(str(part))}"
            )
        stdout = self.run(
            ("bash", "-c", preflight_script),
            cwd=self._settings.worker_project_root,
            timeout=timeout,
        )
        if reuse_matching:
            if stdout == b"matching\n":
                return
            if stdout != b"":
                raise ValueError("remote upload destination has unexpected preflight output")
        upload_script = (
            "set -euo pipefail; "
            f"trap 'rm -f -- {shlex.quote(str(part))}' EXIT; "
            f"cat > {shlex.quote(str(part))}; "
            f"chmod 0600 {shlex.quote(str(part))}; "
            "python3 -c 'import os,sys; fd=os.open(sys.argv[1], os.O_RDONLY); "
            f"os.fsync(fd); os.close(fd)' {shlex.quote(str(part))}; "
            f"mv -- {shlex.quote(str(part))} {shlex.quote(str(destination))}; "
            "trap - EXIT"
        )
        self.run(
            ("bash", "-c", upload_script),
            cwd=self._settings.worker_project_root,
            stdin_path=source,
            timeout=timeout,
        )

    def download(
        self, source: PurePosixPath, destination: Path, *, timeout: float | None = None
    ) -> None:
        """Stream one remote file to a local atomic mode-0600 destination.

        ``timeout`` bounds the preflight and the streaming subprocess independently. On a
        transfer timeout only this call's own local process is killed and waited, its temporary
        is removed, and the timeout re-raises, leaving any destination that is already present
        intact.
        """
        self.run(
            (
                "bash",
                "-c",
                "test -f {source} && test ! -L {source}".format(source=shlex.quote(str(source))),
            ),
            cwd=self._settings.worker_project_root,
            timeout=timeout,
        )
        if not destination.parent.is_dir():
            raise ValueError("download destination directory must already exist")
        descriptor, temporary_name = tempfile.mkstemp(
            dir=destination.parent, prefix=f".{destination.name}-", suffix=".part"
        )
        os.close(descriptor)
        part = Path(temporary_name)
        log = destination.with_name(destination.name + ".download.log")
        script = self._wrapper(
            ("cat", "--", str(source)),
            self._settings.worker_project_root,
            None,
            detached=False,
            output_path=None,
        )
        # The runner appends to the log. Another attempt's marker must not classify this attempt,
        # so truncate the invocation's log before the stream starts.
        log.unlink(missing_ok=True)
        try:
            process = self._runner.popen(self._ssh_argv(script), stdout_path=part, stderr_path=log)
            try:
                return_code = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
                raise WorkerAvailabilityError(None) from None
            self._classify(return_code, log.read_bytes() if log.exists() else b"")
            with os.fdopen(os.open(part, os.O_RDONLY), "rb") as stream:
                os.fsync(stream.fileno())
            os.chmod(part, 0o600)
            os.replace(part, destination)
        except Exception:
            part.unlink(missing_ok=True)
            raise
        finally:
            log.unlink(missing_ok=True)
