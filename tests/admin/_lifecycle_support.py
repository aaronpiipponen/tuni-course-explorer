"""Support fixtures for the shared local lifecycle core contracts.

This module owns the one synthetic local stage that writes real temporary unit files, the one
local process/Compose boundary double that delegates real subprocess creation to
``SubprocessRunner`` and answers only prepared-service observations, and the test-only worker main
that calls ``run_lifecycle_worker`` with that stage.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from collections.abc import Mapping, Sequence
from pathlib import Path

from course_explorer.administration import administrative_json, atomic_write_private_text
from course_explorer.hashing import json_sha256
from course_explorer_admin import lifecycle, mechanics
from course_explorer_admin.lifecycle import (
    EmbeddingOptions,
    EmbeddingProgress,
    IngestionOptions,
    IngestionProgress,
    LifecycleContext,
    StageName,
    StageOptions,
    StageProgress,
)

IDENTITY_ALIAS = "LIFECYCLE_TEST_IDENTITY"
UNITS_ALIAS = "LIFECYCLE_TEST_UNITS"
DELAY_ALIAS = "LIFECYCLE_TEST_UNIT_DELAY"
FAIL_DATABASE_ALIAS = "LIFECYCLE_TEST_FAIL_DATABASE"
INITIAL_ACTION_ALIAS = "LIFECYCLE_TEST_INITIAL_ACTION"


class SupportStage:
    """One local stage that writes real unit files and honours live run intent."""

    retains_after_stop = True
    server_worker_module = "course_explorer_admin.worker"

    def __init__(self, name: StageName) -> None:
        self.name = name
        if name == "ingestion":
            self.services: tuple[str, ...] = ("db",)
            self.temporary_services: tuple[str, ...] = ()
        else:
            self.services = ("db", "embedding")
            self.temporary_services = ("embedding",)

    def select_options(self) -> StageOptions:
        if self.name == "ingestion":
            return IngestionOptions(kind="ingestion")
        return EmbeddingOptions(kind="embedding")

    def identity_sha256(self, options: StageOptions) -> str:
        token = os.environ.get(IDENTITY_ALIAS, "default")
        payload = {
            "stage": self.name,
            "token": token,
            "options": options.model_dump(mode="json"),
        }
        return json_sha256(payload, ensure_ascii=True)

    def initial_progress(self, options: StageOptions) -> StageProgress:
        if self.name == "ingestion":
            return IngestionProgress(
                kind="ingestion",
                stage="selecting",
                response_count=0,
                verified_response_count=0,
                normalized=False,
            )
        return EmbeddingProgress(
            kind="embedding",
            reconciled=False,
            desired_count=0,
            pending_count=0,
            completed_count=0,
            failed_count=0,
            generated_count=0,
        )

    def require_prepared(self) -> None:
        return None

    def require_database(self) -> None:
        if os.environ.get(FAIL_DATABASE_ALIAS) == "1":
            raise RuntimeError("synthetic database preparation failure")

    def run(self, context: LifecycleContext) -> bool:
        total = int(os.environ.get(UNITS_ALIAS, "4"))
        delay = float(os.environ.get(DELAY_ALIAS, "0.1"))
        units_dir = context.root / context.session.session_id / "units"
        units_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        start = len(list(units_dir.glob("unit-*.txt")))
        for index in range(start, total):
            if not context.admit():
                return False
            (units_dir / f"unit-{index}.txt").write_text(f"unit {index}\n", encoding="utf-8")
            context.checkpoint(self._progress(index + 1, total))
            if delay > 0:
                time.sleep(delay)
        return True

    def release(self, context: LifecycleContext) -> None:
        return None

    def finalize(self, context: LifecycleContext) -> None:
        return None

    def _progress(self, completed: int, total: int) -> StageProgress:
        if self.name == "ingestion":
            return IngestionProgress(
                kind="ingestion",
                stage="capture",
                response_count=completed,
                verified_response_count=0,
                verification_total=total,
                normalized=False,
            )
        return EmbeddingProgress(
            kind="embedding",
            reconciled=True,
            desired_count=total,
            pending_count=total - completed,
            completed_count=completed,
            failed_count=0,
            generated_count=completed,
        )


class LocalLifecycleRunner:
    """One local process/Compose double that answers only prepared-service observations/actions."""

    def __init__(
        self,
        *,
        root: Path,
        revision: str = "a" * 40,
        running: set[str] | None = None,
        fail_up: bool = False,
        fail_release: bool = False,
    ) -> None:
        self.root = root
        self.revision = revision
        self.running = set(running or ())
        self.fail_up = fail_up
        self.fail_release = fail_release
        self.calls: list[tuple[str, ...]] = []
        self.launches: list[tuple[str, ...]] = []
        self.started: list[str] = []
        self.stopped: list[str] = []
        self.children: list[subprocess.Popen[bytes]] = []
        self._real = mechanics.SubprocessRunner()

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
        command = tuple(argv)
        self.calls.append(command)
        if command[:3] == ("git", "rev-parse", "HEAD"):
            return subprocess.CompletedProcess(
                list(command), 0, stdout=(self.revision + "\n").encode(), stderr=b""
            )
        if command[: len(mechanics.compose_prefix())] == mechanics.compose_prefix():
            return self._compose(command)
        return self._real.run(
            command,
            cwd=cwd,
            env=env,
            stdin_path=stdin_path,
            stdout_path=stdout_path,
            timeout=timeout,
        )

    def _compose(self, command: tuple[str, ...]) -> subprocess.CompletedProcess[bytes]:
        if "ps" in command and "--services" in command:
            output = ("\n".join(sorted(self.running)) + "\n").encode()
            return subprocess.CompletedProcess(list(command), 0, stdout=output, stderr=b"")
        if "up" in command and "--wait" in command:
            if self.fail_up:
                raise subprocess.CalledProcessError(1, list(command))
            services = command[command.index("never") + 1 :]
            for service in services:
                self.running.add(service)
                self.started.append(service)
            return subprocess.CompletedProcess(list(command), 0, stdout=b"", stderr=b"")
        if self.fail_release and ("stop" in command or "rm" in command):
            sentinel = b"synthetic-secret-sentinel"
            raise subprocess.CalledProcessError(
                255, list(command), output=sentinel, stderr=sentinel
            )
        if "stop" in command:
            service = command[-1]
            self.running.discard(service)
            self.stopped.append(service)
            return subprocess.CompletedProcess(list(command), 0, stdout=b"", stderr=b"")
        if "rm" in command:
            self.running.discard(command[-1])
            return subprocess.CompletedProcess(list(command), 0, stdout=b"", stderr=b"")
        return subprocess.CompletedProcess(list(command), 0, stdout=b"", stderr=b"")

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
        command = tuple(argv)
        self.launches.append(command)
        rewritten = (
            sys.executable,
            "-m",
            "tests.admin._lifecycle_support",
            str(self.root),
            command[3],
            command[4],
        )
        child = self._real.popen(
            rewritten,
            cwd=cwd,
            env=env,
            stdin_path=stdin_path,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            start_new_session=start_new_session,
            inherit_environment=inherit_environment,
        )
        self.children.append(child)
        return child

    def close(self) -> None:
        """Reap this runner's recorded synthetic children, killing only those alive."""
        for child in self.children:
            if child.poll() is None:
                child.kill()
            child.wait()


def configure_environment(monkeypatch, *, startup_attempts: int = 100) -> None:
    """Set the one shared local-lifecycle policy to deterministic test bounds."""
    monkeypatch.setenv("INGESTION_CONTROLLER_STATE_ROOT", "data/tests/lifecycle/ingestion")
    monkeypatch.setenv("EMBEDDING_CONTROLLER_STATE_ROOT", "data/tests/lifecycle/embedding")
    monkeypatch.setenv("ADMIN_STARTUP_ATTEMPTS", str(startup_attempts))
    monkeypatch.setenv("ADMIN_POLL_INTERVAL_SECONDS", "0.02")
    monkeypatch.setenv("ADMIN_STOP_TIMEOUT_SECONDS", "10")
    monkeypatch.setenv(INITIAL_ACTION_ALIAS, "run")


def units_directory(root: Path, session_id: str) -> Path:
    return root / session_id / "units"


def unit_count(root: Path, session_id: str) -> int:
    directory = units_directory(root, session_id)
    if not directory.is_dir():
        return 0
    return len(list(directory.glob("unit-*.txt")))


def wait_for_units(root: Path, session_id: str, minimum: int, *, timeout: float = 10.0) -> int:
    """Block until at least ``minimum`` durable unit files exist. Fail loudly on timeout."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        count = unit_count(root, session_id)
        if count >= minimum:
            return count
        time.sleep(0.01)
    raise AssertionError("synthetic lifecycle worker did not reach the requested unit count")


def session_id_from_state(root: Path) -> str:
    from course_explorer_admin.lifecycle import read_lifecycle_state

    state = read_lifecycle_state(root)
    assert state is not None
    return state.session_id


def wait_for_stable_state(root: Path, *, timeout: float = 10.0, quiet: float = 0.03) -> bytes:
    """Return state bytes once two reads ``quiet`` apart agree, i.e. the worker is between units."""
    path = root / "state.json"
    deadline = time.monotonic() + timeout
    previous = path.read_bytes()
    while time.monotonic() < deadline:
        time.sleep(quiet)
        current = path.read_bytes()
        if current == previous:
            return current
        previous = current
    raise AssertionError("synthetic lifecycle state never stabilized")


def wait_for_lifecycle(root: Path, targets: set[str], *, timeout: float = 20.0):
    """Block until the current state reaches one of ``targets``. Fail loudly on timeout."""
    from course_explorer_admin.lifecycle import read_lifecycle_state

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = read_lifecycle_state(root)
        if state is not None and state.lifecycle in targets:
            return state
        time.sleep(0.01)
    raise AssertionError("synthetic lifecycle did not reach the requested lifecycle")


def main(argv: Sequence[str] | None = None) -> int:
    """Test-only worker main: run one synthetic session through the real lifecycle worker."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root")
    parser.add_argument("stage", choices=("ingestion", "embedding"))
    parser.add_argument("session_id")
    args = parser.parse_args(argv)
    from course_explorer_admin.worker import run_lifecycle_worker

    stage = SupportStage(args.stage)
    root = Path(args.root)
    if os.environ.get(INITIAL_ACTION_ALIAS) == "pause":
        # Fixture control intent at the public worker boundary: seed the parent's published
        # current state with a pending pause so the real worker takes its refused-intent path.
        with mechanics.exclusive_action_lock(root, controller_name=stage.name, blocking=True):
            state = lifecycle.read_lifecycle_state(root)
            if state is not None:
                atomic_write_private_text(
                    root / "state.json",
                    administrative_json(state.model_copy(update={"requested_action": "pause"})),
                )
    status = run_lifecycle_worker(stage, root, args.session_id)
    print(status.model_dump_json())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
