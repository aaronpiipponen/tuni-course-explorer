"""Local worker transport and shared external-observation boundary for the remote lifecycle tests.

The one :class:`LocalWorkerTransport` maps a requested remote path relative to the configured
``worker_project_root`` into a separate temporary worker-data root and runs the ACTUAL worker helper
subprocesses through the test-only bootstrap in ``_real_worker_support``. Only the external machine
boundary (Compose service observations, the keepalive, the native Windows boot, the model-response
gate and the status-delivery delay) is canned. Those observations, injected faults and call counts
live in one JSON file under the shared lock so the parent test process, the detached server
child and the worker helper subprocesses observe the same state. The real owners keep the lifecycle,
session, status, count and reboot-due authority. ``main`` runs the export-only child mode
used by the export serialization test.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import Any

from course_explorer.administration import administrative_json, sha256_file
from course_explorer_admin import mechanics
from course_explorer_admin.transport import WorkerAvailabilityError, WorkerCommandError
from tests.datasets._support import sample_verification

_FAKE_NAME = "real-worker-boundary.json"
_WSL_BOOT = "00000000-0000-4000-8000-000000000001"
_DUMP_STARTED = "dump-started"
_DUMP_RELEASE = "dump-release"
_DUMP_DONE = "dump-done"

# Captured before the bootstrap patches the synthetic boot identity, so a recorded worker-child
# ownership record always carries the real local boot the parent can observe through ``/proc``.
_LOCAL_BOOT_ID = mechanics.current_boot_id()


def fake_state_path(root: Path) -> Path:
    return root / _FAKE_NAME


def read_fake(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_fake(path: Path, state: dict[str, Any]) -> None:
    # Each writer uses its own temporary so concurrent writers can never interleave bytes in one
    # shared temporary before the atomic replace.
    descriptor, name = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(state, stream)
    os.replace(name, path)


@contextmanager
def state_lock(path: Path):
    """Serialize one read-modify-write across every boundary observer process."""
    lock_path = path.with_name(path.name + ".lock")
    descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        os.close(descriptor)


def seed_fake(path: Path) -> None:
    """Reset the one external-observation boundary. No lifecycle or work state is stored here."""
    with state_lock(path):
        write_fake(
            path,
            {
                "keepalive_pid": 777,
                "keepalive_alive": False,
                "keepalive_starts": 0,
                "services": [],
                "windows_boot": "111",
                "wsl_boot": _WSL_BOOT,
                "monotonic_seconds": 0.0,
                "reboot_requests": 0,
                "status_delay_seconds": 0.0,
                "calls": [],
                "uploads": [],
                "detached": [],
                "downloads": [],
                "remote_terminated": [],
                "faults": [],
                "fault_consumed": 0,
                "model_response_released": False,
                "worker_children": [],
            },
        )


def release_model_response(path: Path) -> None:
    """Open the one test-only external model-response gate under the shared lock."""
    with state_lock(path):
        state = read_fake(path)
        state["model_response_released"] = True
        write_fake(path, state)


def model_response_released(path: Path) -> bool:
    return bool(read_fake(path).get("model_response_released"))


def set_monotonic_seconds(path: Path, seconds: float) -> None:
    """Set the worker bootstrap's external monotonic seconds under the shared lock."""
    with state_lock(path):
        state = read_fake(path)
        state["monotonic_seconds"] = float(seconds)
        write_fake(path, state)


def set_status_delay(path: Path, seconds: float) -> None:
    """Set an external status-response delivery delay under the shared lock."""
    with state_lock(path):
        state = read_fake(path)
        state["status_delay_seconds"] = float(seconds)
        write_fake(path, state)


def add_fault(
    path: Path,
    *,
    method: str | None = None,
    token: str | None = None,
    fault_type: str = "availability",
    rc: int | None = 1,
    remaining: int = 1,
    position: str = "before",
    kill_keepalive: bool = False,
) -> None:
    """Append one shared external fault matched by transport method or command token.

    ``remaining`` counts invocations (a negative value is persistent). ``position`` selects whether
    the fault fires before the call's effect or after it (a lost response following the real effect).
    """
    with state_lock(path):
        state = read_fake(path)
        state.setdefault("faults", []).append(
            {
                "method": method,
                "token": token,
                "type": fault_type,
                "rc": rc,
                "remaining": remaining,
                "position": position,
                "kill_keepalive": kill_keepalive,
            }
        )
        write_fake(path, state)


def _matching_fault(state: dict[str, Any], *, method: str, token: str) -> dict[str, Any] | None:
    for fault in state.get("faults", []):
        if int(fault.get("remaining", 0)) == 0:
            continue
        if fault.get("method") is not None and fault["method"] != method:
            continue
        if fault.get("token") is not None and fault["token"] not in token:
            continue
        return fault
    return None


def _consume_fault(state: dict[str, Any], fault: dict[str, Any]) -> None:
    if int(fault.get("remaining", 0)) > 0:
        fault["remaining"] = int(fault["remaining"]) - 1
    state["fault_consumed"] = int(state.get("fault_consumed", 0)) + 1


def _raise_fault(fault: dict[str, Any]) -> None:
    fault_type = fault.get("type", "availability")
    rc = fault.get("rc")
    if fault_type == "timeout":
        raise WorkerAvailabilityError(None)
    if fault_type == "command":
        raise WorkerCommandError(int(rc if rc is not None else 1), phase="command")
    raise WorkerAvailabilityError(None if rc is None else int(rc))


def _child_alive(record: dict[str, Any]) -> bool:
    """Observe one recorded worker child through real ``/proc`` ownership, not the fake boot."""
    pid = int(record["pid"])
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError:
        return False
    actual = raw.decode("utf-8", errors="surrogateescape").split("\0")
    if actual and actual[-1] == "":
        actual.pop()
    return tuple(actual) == tuple(record["argv"])


def reap_record(record: dict[str, Any]) -> None:
    """Signal one recorded test worker child only after proving real ``/proc`` ownership."""
    if not _child_alive(record):
        return
    pid = int(record["pid"])
    os.kill(pid, signal.SIGTERM)
    deadline = time.monotonic() + 5.0
    while _child_alive(record):
        if time.monotonic() >= deadline:
            os.kill(pid, signal.SIGKILL)
            break
        time.sleep(0.02)
    try:
        os.waitpid(pid, os.WNOHANG)
    except ChildProcessError:
        pass


class LocalWorkerTransport:
    """Real local SSH/WSL transport double mapping remote paths into a worker-data root."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._root = self.path.parent
        self._checkout = Path(os.environ["TRANSLATION_CONTROLLER_WORKER_PROJECT_ROOT"])
        self._data_root = Path(os.environ["S7D_WORKER_DATA_ROOT"])
        self._runner = mechanics.SubprocessRunner()

    def _map(self, remote: PurePosixPath) -> Path:
        relative = PurePosixPath(str(remote)).relative_to(PurePosixPath(str(self._checkout)))
        return self._data_root / Path(str(relative))

    def _rewrite(self, text: str) -> str:
        return text.replace(str(self._checkout), str(self._data_root))

    def _fault(self, method: str, token: str, effect: Callable[[], Any]) -> Any:
        """Select/consume one fault under the lock, release it, then invoke the effect.

        The shared boundary lock is never held across a worker helper, subprocess or response gate,
        because those processes consume the same boundary file.
        """
        with state_lock(self.path):
            state = read_fake(self.path)
            fault = _matching_fault(state, method=method, token=token)
            if fault is not None:
                _consume_fault(state, fault)
                if fault.get("kill_keepalive"):
                    state["keepalive_alive"] = False
                write_fake(self.path, state)
        if fault is None:
            return effect()
        if fault.get("position", "before") == "after":
            result = effect()
            _raise_fault(fault)
            return result
        _raise_fault(fault)
        return None  # unreachable, and _raise_fault always raises

    def _bootstrap_argv(
        self, mode: str, stage: str, subcommand: str, session_id: str
    ) -> tuple[str, ...]:
        return (
            sys.executable,
            "-m",
            os.environ.get("S7D_BOOTSTRAP_MODULE", "tests.admin._real_worker_support"),
            str(self._root),
            mode,
            stage,
            subcommand,
            session_id,
        )

    def _run_bootstrap(
        self, mode: str, stage: str, subcommand: str, session_id: str, env: dict[str, str] | None
    ) -> bytes:
        argv = self._bootstrap_argv(mode, stage, subcommand, session_id)
        merged = {**os.environ, **(env or {})}
        merged.setdefault("PYTHONPATH", str(self._checkout))
        try:
            completed = self._runner.run(argv, cwd=self._checkout, env=merged)
        except subprocess.CalledProcessError as exc:
            # A completed helper that exits nonzero is a command failure, not availability loss.
            raise WorkerCommandError(exc.returncode, phase="command") from None
        return completed.stdout

    def run(
        self,
        argv,
        *,
        cwd=None,
        env=None,
        stdin_path=None,
        timeout=None,
    ):
        command = tuple(argv)
        return self._fault(
            "run",
            " ".join(str(part) for part in command),
            lambda: self._run(command, env=env, timeout=timeout),
        )

    def _run(self, command: tuple[str, ...], *, env: dict[str, str] | None, timeout: float | None):
        if command == ("printf", "ready"):
            return b"ready"
        if command == ("cat", "/proc/sys/kernel/random/boot_id"):
            return str(read_fake(self.path).get("wsl_boot", _WSL_BOOT)).encode()
        if command[: len(mechanics.compose_prefix())] == mechanics.compose_prefix():
            return self._compose(command)
        if command[:2] == ("bash", "-c"):
            script = self._rewrite(command[2])
            completed = subprocess.run(
                ["bash", "-c", script],
                cwd=self._checkout,
                capture_output=True,
                check=True,
                timeout=timeout,
            )
            return completed.stdout
        if command[:2] == ("uv", "sync"):
            return b""
        worker = self._worker_helper(command)
        if worker is not None:
            _mode, stage, subcommand, session_id = worker
            if subcommand != "status":
                with state_lock(self.path):
                    state = read_fake(self.path)
                    state.setdefault("calls", []).append(list(command))
                    write_fake(self.path, state)
            if subcommand == "status":
                delay = float(read_fake(self.path).get("status_delay_seconds", 0.0))
                if delay > 0:
                    time.sleep(delay)
            return self._run_bootstrap("worker", stage, subcommand, session_id, env)
        remote = self._remote_helper(command)
        if remote is not None:
            subcommand, session_id = remote
            return self._run_bootstrap("remote", "inference", subcommand, session_id, env)
        return b""

    @staticmethod
    def _worker_helper(command: tuple[str, ...]) -> tuple[str, str, str, str] | None:
        for part in command:
            if part.endswith("controller_worker"):
                stage = "translation" if "translation" in part else "inference"
                return ("worker", stage, command[-2], command[-1])
        return None

    @staticmethod
    def _remote_helper(command: tuple[str, ...]) -> tuple[str, str] | None:
        if "course_explorer_admin.remote" in command:
            return (command[-2], command[-1])
        return None

    def _compose(self, command: tuple[str, ...]) -> bytes:
        with state_lock(self.path):
            state = read_fake(self.path)
            state.setdefault("calls", []).append(list(command))
            if "ps" in command and "--services" in command:
                output = ("\n".join(state.get("services", [])) + "\n").encode()
            elif "up" in command and "--wait" in command:
                services = list(state.get("services", []))
                if "db" not in services:
                    services.append("db")
                state["services"] = services
                output = b""
            elif "stop" in command or "rm" in command:
                state["services"] = [item for item in state.get("services", []) if item != "db"]
                output = b""
            else:
                output = b""
            write_fake(self.path, state)
            return output

    def upload(self, source: Path, destination, *, reuse_matching=False, timeout=None) -> None:
        mapped = self._map(PurePosixPath(str(destination)))

        def effect() -> None:
            with state_lock(self.path):
                state = read_fake(self.path)
                state.setdefault("uploads", []).append(
                    [Path(source).name, str(destination), bool(reuse_matching)]
                )
                write_fake(self.path, state)
            if mapped.exists():
                if not reuse_matching:
                    raise ValueError("remote upload destination already exists")
                if sha256_file(mapped) != sha256_file(Path(source)):
                    raise ValueError("remote upload destination does not match")
                return
            mapped.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            mapped.write_bytes(Path(source).read_bytes())
            os.chmod(mapped, 0o600)

        self._fault("upload", str(destination), effect)

    def download(self, source, destination: Path, *, timeout=None) -> None:
        mapped = self._map(PurePosixPath(str(source)))

        def effect() -> None:
            with state_lock(self.path):
                state = read_fake(self.path)
                state.setdefault("downloads", []).append(str(source))
                write_fake(self.path, state)
            Path(destination).write_bytes(mapped.read_bytes())

        self._fault("download", str(source), effect)

    def start_detached(self, argv, *, cwd=None, env=None, output_path=None, timeout=None) -> None:
        command = tuple(argv)

        def effect() -> None:
            worker = self._worker_helper(command)
            assert worker is not None
            _mode, stage, subcommand, session_id = worker
            assert subcommand == "run"
            mapped_output = self._map(PurePosixPath(str(output_path)))
            mapped_output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            bootstrap = self._bootstrap_argv("worker", stage, "run", session_id)
            merged = {**os.environ, **(env or {})}
            merged.setdefault("PYTHONPATH", str(self._checkout))
            process = self._runner.popen(
                bootstrap,
                cwd=self._checkout,
                env=merged,
                stdout_path=mapped_output,
                stderr_path=mapped_output,
                start_new_session=True,
            )
            record = mechanics.OwnedProcessRecord(
                schema_version=1,
                pid=process.pid,
                argv=tuple(process.args),
                boot_id=_LOCAL_BOOT_ID,
            )
            with state_lock(self.path):
                state = read_fake(self.path)
                state.setdefault("detached", []).append(list(command))
                state.setdefault("worker_children", []).append(record.model_dump(mode="json"))
                write_fake(self.path, state)
            # The real detached wrapper briefly outlives the launcher to let the child re-parent. The
            # hold also lets the worker publish its starting/running state before the first poll.
            time.sleep(2.0)

        self._fault("start_detached", str(output_path), effect)

    def start_keepalive(self, session_id: str, *, stdout_path: Path, stderr_path: Path) -> int:
        with state_lock(self.path):
            state = read_fake(self.path)
            state["keepalive_alive"] = True
            state["keepalive_starts"] = int(state.get("keepalive_starts", 0)) + 1
            write_fake(self.path, state)
            return int(state.get("keepalive_pid", 777))

    def keepalive_is_alive(self, session_id: str, pid: int | None) -> bool:
        state = read_fake(self.path)
        return bool(state.get("keepalive_alive")) and pid == state.get("keepalive_pid", 777)

    def stop_keepalive(self, session_id: str, pid: int | None, *, sleep=None) -> None:
        with state_lock(self.path):
            state = read_fake(self.path)
            state["keepalive_alive"] = False
            write_fake(self.path, state)

    def terminate_remote_keepalive(self, session_id: str, *, timeout=None) -> None:
        def effect() -> None:
            with state_lock(self.path):
                state = read_fake(self.path)
                state.setdefault("remote_terminated", []).append(session_id)
                state["keepalive_alive"] = False
                write_fake(self.path, state)

        self._fault("terminate_remote_keepalive", session_id, effect)

    def read_windows_boot_id(self, *, timeout: float) -> str:
        return str(read_fake(self.path).get("windows_boot", "111"))

    def request_windows_reboot(self, *, timeout: float) -> None:
        with state_lock(self.path):
            state = read_fake(self.path)
            state["reboot_requests"] = int(state.get("reboot_requests", 0)) + 1
            records = list(state.get("worker_children", []))
            write_fake(self.path, state)
        # Boundedly observe the recorded test worker processes' actual exit through real ``/proc``
        # ownership before changing any boot observation. Never make a live runner look dead early.
        deadline = time.monotonic() + max(float(timeout), 20.0)
        for record in records:
            while _child_alive(record):
                if time.monotonic() >= deadline:
                    raise RuntimeError("recorded worker child did not exit before reboot")
                time.sleep(0.02)
        with state_lock(self.path):
            state = read_fake(self.path)
            state["windows_boot"] = "222"
            state["wsl_boot"] = str(uuid.uuid4())
            state["monotonic_seconds"] = 0.0
            write_fake(self.path, state)


def _fake_dump(*, runner, root, settings, destination, include_embeddings, timeout=None) -> str:
    Path(destination).write_bytes(b"dump-bytes")
    return sha256_file(Path(destination))


def _export_fake_dump(
    *, runner, root, settings, destination, include_embeddings, timeout=None
) -> str:
    """External dump boundary for the export-child mode, gated by test markers.

    It records a per-invocation dump marker, waits for the parent's release file, then reuses the
    normal fake dump publication. It scripts only external dump latency, never locking or artifact
    reuse.
    """
    directory = Path(destination).parent
    with (directory / "dump-invocations").open("a", encoding="utf-8") as stream:
        stream.write("dump\n")
    (directory / _DUMP_STARTED).write_text("1", encoding="utf-8")
    release = directory / _DUMP_RELEASE
    while not release.exists():
        time.sleep(0.01)
    digest = _fake_dump(
        runner=runner,
        root=root,
        settings=settings,
        destination=destination,
        include_embeddings=include_embeddings,
        timeout=timeout,
    )
    (directory / _DUMP_DONE).write_text("1", encoding="utf-8")
    return digest


def main(argv: list[str] | None = None) -> int:
    """Run the export-only ``_remote_support`` child mode."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root")
    parser.add_argument("stage")
    parser.add_argument("session_id")
    args = parser.parse_args(argv)
    if args.stage != "export":
        raise SystemExit("only the export child mode remains")

    import course_explorer_admin.remote as remote

    root = Path(args.root)
    _redirect_repository_root(root)
    remote.dump_database = _export_fake_dump
    remote.read_dataset_verification = lambda settings: sample_verification()
    session = remote.load_worker_dataset_session(args.session_id)
    directory = remote.worker_dataset_session_directory(args.session_id)
    (directory / f"export-entry-{os.getpid()}").write_text(str(os.getpid()), encoding="utf-8")
    snapshot = remote.export_worker_database(session, runner=mechanics.SubprocessRunner())
    print(administrative_json(snapshot), end="")
    return 0


def _redirect_repository_root(root: Path) -> None:
    import course_explorer.administration as administration
    import course_explorer_admin.datasets as datasets_module
    import course_explorer_admin.lifecycle as lifecycle
    import course_explorer_admin.remote as remote

    administration.repository_root = lambda: root
    datasets_module.repository_root = lambda: root
    lifecycle.repository_root = lambda: root
    remote.repository_root = lambda: root


if __name__ == "__main__":
    raise SystemExit(main())
