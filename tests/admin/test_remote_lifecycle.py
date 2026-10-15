"""Real-subprocess, real-PostgreSQL contracts for the remote translation/inference lifecycle.

These four proofs drive the real shared lifecycle core, a real detached server child, real worker
helper subprocesses and the real dataset return/rotation owners over real disposable PostgreSQL. Only
the external machine boundary (SSH/WSL, Compose service control, the keepalive, the native Windows
boot, the model endpoint and the clock/boot observations) is substituted. Every SQL/persistence owner,
worker checkout/schema checker, selector, job and publisher run as-is.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest
from sqlalchemy import Engine

from course_explorer import administration
from course_explorer.config import load_embedding_settings, load_raw_database_settings
from course_explorer.datasets import read_dataset_verification
from course_explorer_admin import (
    lifecycle,
    local_stages,
    mechanics,
    remote,
    remote_stages,
)
from course_explorer_admin.datasets import initialize_selected_dataset
from course_explorer_admin.inference.controller import InferenceControllerWorkerState
from course_explorer_admin.lifecycle import read_lifecycle_state
from course_explorer_admin.snapshots import dump_database, restore_database
from course_explorer_admin.translation.controller import TranslationControllerWorkerState
from course_explorer_admin.transport import WorkerCommandError, WorkerConnectionLost
from tests.admin._remote_support import (
    LocalWorkerTransport,
    add_fault,
    fake_state_path,
    read_fake,
    release_model_response,
    seed_fake,
    set_monotonic_seconds,
    set_status_delay,
)
from tests.config._support import (
    ADMIN_DATASET_KEYS,
    EMBEDDING_KEYS,
    INFERENCE_ALL_KEYS,
    INFERENCE_CONTROLLER_KEYS,
    LOCAL_LIFECYCLE_KEYS,
    TRANSLATION_CONTROLLER_KEYS,
    TRANSLATION_KEYS,
)
from tests.inference._job_support import seed_embeddings
from tests.inference._scheduling_support import seed_courses

pytestmark = [
    pytest.mark.integration,
    pytest.mark.slow,
]

_REPO = Path(__file__).resolve().parents[2]

SESSION_ID = "0123456789abcdef0123456789abcdef"
SECOND_ID = "fedcba9876543210fedcba9876543210"
SOURCE_DATABASE = "course_explorer_test"
WORKLOAD = [
    ("remote-t1", "REM.T1", True),
    ("remote-t2", "REM.T2", True),
    ("remote-c1", "REM.C1", False),
    ("remote-c2", "REM.C2", False),
] + [(f"remote-s{index:02d}", f"REM.S{index:02d}", False) for index in range(1, 51)]


def _compose_exec(*argv: str, stdin_path: Path | None = None):
    return mechanics.SubprocessRunner().run(
        (*mechanics.compose_prefix(), "exec", "-T", "db", *argv),
        cwd=_REPO,
        stdin_path=stdin_path,
        timeout=600,
    )


def _drop_database(name: str) -> None:
    user = load_raw_database_settings().postgres_user
    _compose_exec("dropdb", "--if-exists", "--username", user, name)


@pytest.fixture()
def sql_source(
    database: tuple[Engine, object], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> str:
    """Seed the fixture, dump it, and restore one owning ``course_s7d_<hex>_test`` copy."""
    _engine, factory = database
    with monkeypatch.context() as context:
        context.setenv("SELECTED_DATASET_ENABLED", "0")
        context.setenv("POSTGRES_DB", SOURCE_DATABASE)
        seed_courses(factory, WORKLOAD)
        seed_embeddings(factory, load_embedding_settings())
        source = load_raw_database_settings().model_copy(update={"postgres_db": SOURCE_DATABASE})
        scratch = tmp_path / "source.dump"
        digest = dump_database(
            runner=mechanics.SubprocessRunner(),
            root=_REPO,
            settings=source,
            destination=scratch,
            include_embeddings=True,
        )
        verification = read_dataset_verification(source)
        name = f"course_s7d_{uuid.uuid4().hex}_test"
        restore_database(
            runner=mechanics.SubprocessRunner(),
            root=_REPO,
            settings=source,
            dump=scratch,
            database_name=name,
            expected_sha256=digest,
            include_embeddings=True,
            expected_verification=verification,
        )
    try:
        yield name
    finally:
        _drop_database(name)
        scratch.unlink(missing_ok=True)


def configure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *, initial_database: str) -> None:
    """Point every canonical loader at one temporary repository with real PostgreSQL settings."""
    for key, value in {
        **TRANSLATION_CONTROLLER_KEYS,
        **INFERENCE_CONTROLLER_KEYS,
        **ADMIN_DATASET_KEYS,
        **LOCAL_LIFECYCLE_KEYS,
        **TRANSLATION_KEYS,
        **INFERENCE_ALL_KEYS,
        **EMBEDDING_KEYS,
    }.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("ADMIN_STATE_ROOT", "data/admin")
    monkeypatch.setenv("INGESTION_CONTROLLER_STATE_ROOT", "state/ingestion")
    monkeypatch.setenv("EMBEDDING_CONTROLLER_STATE_ROOT", "state/embedding")
    monkeypatch.setenv("TRANSLATION_CONTROLLER_STATE_ROOT", "state/translation")
    monkeypatch.setenv("INFERENCE_CONTROLLER_STATE_ROOT", "state/inference")
    monkeypatch.setenv("TRANSLATION_CONTROLLER_WORKER_PROJECT_ROOT", str(_REPO))
    monkeypatch.setenv("S7D_WORKER_DATA_ROOT", str(tmp_path / "worker-data"))
    monkeypatch.setenv("ADMIN_DATASET_DATABASE_PREFIX", "course_s7d_test")
    monkeypatch.setenv("ADMIN_WORKER_DATABASE_PREFIX", "course_s7d_worker_test")
    monkeypatch.setenv("ADMIN_DATABASE_OPERATION_TIMEOUT_SECONDS", "600")
    monkeypatch.setenv("INFERENCE_SELECTION_POOL_K", "50")
    monkeypatch.setenv("INFERENCE_SELECTION_FINAL_K", "50")
    monkeypatch.setenv("TRANSLATION_CONTROLLER_HEALTH_INTERVAL_SECONDS", "0.02")
    monkeypatch.setenv("TRANSLATION_CONTROLLER_STOP_TIMEOUT_SECONDS", "20")
    monkeypatch.setenv("ADMIN_POLL_INTERVAL_SECONDS", "0.02")
    monkeypatch.setenv("ADMIN_STOP_TIMEOUT_SECONDS", "20")
    monkeypatch.setenv("ADMIN_STARTUP_ATTEMPTS", "400")
    monkeypatch.setenv("POSTGRES_DB", initial_database)
    monkeypatch.setenv("SELECTED_DATASET_ENABLED", "0")
    for module in (administration, lifecycle, local_stages, remote):
        monkeypatch.setattr(module, "repository_root", lambda: tmp_path)
    from course_explorer_admin import datasets as datasets_module

    monkeypatch.setattr(datasets_module, "repository_root", lambda: tmp_path)
    enrollment = RemoteLifecycleRunner(root=tmp_path, running={"db"})
    initialize_selected_dataset(runner=enrollment)
    enrollment.close()
    monkeypatch.setenv("SELECTED_DATASET_ENABLED", "1")


class RemoteLifecycleRunner:
    """Local process double: real subprocess for git/PostgreSQL, canned service-control only."""

    def __init__(self, *, root: Path, running: set[str] | None = None) -> None:
        self.root = root
        self.running = set(running or ())
        self.calls: list[tuple[str, ...]] = []
        self.launches: list[tuple[str, ...]] = []
        self.children: list[subprocess.Popen[bytes]] = []
        self._real = mechanics.SubprocessRunner()

    def run(self, argv, *, cwd=None, env=None, stdin_path=None, stdout_path=None, timeout=None):
        command = tuple(argv)
        self.calls.append(command)
        if command[:3] == ("sudo", "docker", "compose"):
            if "exec" not in command and any(
                part in command for part in ("ps", "up", "stop", "rm")
            ):
                return self._compose(command)
        return self._real.run(
            command,
            cwd=_REPO,
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
            services = command[command.index("never") + 1 :]
            self.running.update(services)
            return subprocess.CompletedProcess(list(command), 0, stdout=b"", stderr=b"")
        if "stop" in command or "rm" in command:
            self.running.discard(command[-1])
            return subprocess.CompletedProcess(list(command), 0, stdout=b"", stderr=b"")
        return subprocess.CompletedProcess(list(command), 0, stdout=b"", stderr=b"")

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
        inherit_environment=True,
    ) -> subprocess.Popen[bytes]:
        command = tuple(argv)
        self.launches.append(command)
        rewritten = (
            sys.executable,
            "-m",
            os.environ.get("S7D_BOOTSTRAP_MODULE", "tests.admin._real_worker_support"),
            str(self.root),
            "server",
            command[3],
            "server",
            command[4],
        )
        launch_env = dict(env or {})
        launch_env["PYTHONPATH"] = str(_REPO)
        child = self._real.popen(
            rewritten,
            cwd=cwd,
            env=launch_env,
            stdin_path=stdin_path,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            start_new_session=start_new_session,
            inherit_environment=inherit_environment,
        )
        self.children.append(child)
        return child

    def close(self) -> None:
        """Reap this runner's server children and every recorded test worker child."""
        for child in self.children:
            if child.poll() is None:
                child.kill()
            child.wait()
        self.children.clear()
        from tests.admin._remote_support import reap_record

        for record in read_fake(fake_state_path(self.root)).get("worker_children", []):
            reap_record(record)


def _wait_for(predicate, *, timeout: float = 60.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("remote lifecycle state did not reach the expected observation")


def _state_root(root: Path, stage: str) -> Path:
    return root / "state" / stage / "current"


def _worker_session_dir(root: Path, session_id: str) -> Path:
    return root / "worker-data" / "data" / "admin" / "sessions" / session_id


def _worker_state(stage: str, root: Path, session_id: str):
    payload = (_worker_session_dir(root, session_id) / "state.json").read_text(encoding="utf-8")
    if stage == "translation":
        return TranslationControllerWorkerState.model_validate_json(payload)
    return InferenceControllerWorkerState.model_validate_json(payload)


def _receipt_path(root: Path, session_id: str) -> Path:
    return root / "data" / "admin" / "datasets" / session_id / "receipt.json"


def _scenario(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    *,
    initial_database: str,
    stop_timeout: str = "3",
    interval: str = "0.02",
):
    root = tmp_path / name
    root.mkdir()
    configure(monkeypatch, root, initial_database=initial_database)
    monkeypatch.setenv("TRANSLATION_CONTROLLER_STOP_TIMEOUT_SECONDS", stop_timeout)
    monkeypatch.setenv("TRANSLATION_CONTROLLER_HEALTH_INTERVAL_SECONDS", interval)
    fake = fake_state_path(root)
    seed_fake(fake)
    transport = LocalWorkerTransport(fake)
    runner = RemoteLifecycleRunner(root=root, running={"db"})
    monkeypatch.setattr(remote_stages, "_transport", lambda _runner, _connection: transport)
    return root, fake, runner


def _clear_faults(fake: Path) -> None:
    state = read_fake(fake)
    state["faults"] = []
    from tests.admin._remote_support import write_fake

    write_fake(fake, state)


def _cleanup_scenario(root: Path, *session_ids: str) -> None:
    """Drop only this scenario's two derived databases and its owned temporary data root."""
    import shutil

    errors: list[Exception] = []
    for session_id in session_ids:
        for prefix in ("course_s7d_test", "course_s7d_worker_test"):
            try:
                _drop_database(f"{prefix}_{session_id}")
            except Exception as exc:
                errors.append(exc)
    if root.exists():
        try:
            shutil.rmtree(root)
        except Exception as exc:
            errors.append(exc)
    if errors:
        raise ExceptionGroup("scenario cleanup failed", errors)


def test_remote_due_checkpoint_reboots_and_continues_same_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, sql_source: str
) -> None:
    """A due checkpoint reboots once and resumes the same session. A pending pause issues none."""
    root, fake, runner = _scenario(
        tmp_path, monkeypatch, "reboot", initial_database=sql_source, stop_timeout="20"
    )
    monkeypatch.setenv("WORKER_GPU_REBOOT_INTERVAL_MINUTES", "1")
    try:
        started = remote_stages.run_translation_lifecycle_command(
            "start", runner=runner, session_id_factory=lambda: SESSION_ID, sleep=time.sleep
        )
        assert started.lifecycle in {"starting", "running"}
        _wait_for(
            lambda: len(read_fake(fake)["detached"]) >= 1 and len(read_fake(fake)["uploads"]) >= 3
        )
        _wait_for(lambda: _worker_state("translation", root, SESSION_ID).lifecycle == "running")
        # The worker is held at its first gated response. Advance the external clock past one minute
        # so the real completed-unit checkpoint publishes a due paused state, then release it.
        set_monotonic_seconds(fake, 61.0)
        release_model_response(fake)
        _wait_for(lambda: read_fake(fake)["reboot_requests"] == 1, timeout=60)
        assert read_fake(fake)["windows_boot"] == "222"
        _wait_for(
            lambda: len(read_fake(fake)["detached"]) >= 2 and len(read_fake(fake)["uploads"]) >= 6,
            timeout=60,
        )
        assert read_lifecycle_state(_state_root(root, "translation")).session_id == SESSION_ID
    finally:
        runner.close()
        _cleanup_scenario(root, SESSION_ID)

    # Pending-pause case: an external status-response delivery delay lets the foreground pause land
    # before the due status is delivered, so the real reboot admission issues zero requests.
    pause_root, pause_fake, pause_runner = _scenario(
        tmp_path, monkeypatch, "reboot-pause", initial_database=sql_source, stop_timeout="20"
    )
    monkeypatch.setenv("WORKER_GPU_REBOOT_INTERVAL_MINUTES", "1")
    try:
        started = remote_stages.run_inference_lifecycle_command(
            "start", runner=pause_runner, session_id_factory=lambda: SECOND_ID, sleep=time.sleep
        )
        assert started.lifecycle in {"starting", "running"}
        _wait_for(lambda: len(read_fake(pause_fake)["detached"]) >= 1)
        set_monotonic_seconds(pause_fake, 61.0)
        set_status_delay(pause_fake, 1.0)
        release_model_response(pause_fake)
        paused = remote_stages.run_inference_lifecycle_command(
            "pause", runner=pause_runner, sleep=time.sleep
        )
        assert paused.lifecycle == "paused"
        assert read_fake(pause_fake)["reboot_requests"] == 0
    finally:
        pause_runner.close()
        _cleanup_scenario(pause_root, SECOND_ID)

    # A lost launcher acknowledgment after the real launch effect is reconciled read-only from
    # status. The detached launch is never repeated.
    lost_root = tmp_path / "lost-launch"
    lost_root.mkdir()
    configure(monkeypatch, lost_root, initial_database=sql_source)
    lost_fake = fake_state_path(lost_root)
    seed_fake(lost_fake)
    lost_transport = LocalWorkerTransport(lost_fake)
    lost_runner = RemoteLifecycleRunner(root=lost_root, running={"db"})
    monkeypatch.setattr(remote_stages, "_transport", lambda _r, _c: lost_transport)
    add_fault(
        lost_fake,
        method="start_detached",
        fault_type="availability",
        rc=None,
        remaining=1,
        position="after",
    )
    try:
        started = remote_stages.run_inference_lifecycle_command(
            "start", runner=lost_runner, session_id_factory=lambda: SESSION_ID, sleep=time.sleep
        )
        assert started.lifecycle in {"starting", "running"}
        _wait_for(lambda: len(read_fake(lost_fake)["detached"]) >= 1)
        assert len(read_fake(lost_fake)["detached"]) == 1
        assert read_fake(lost_fake)["reboot_requests"] == 0
    finally:
        lost_runner.close()
        _cleanup_scenario(lost_root, SESSION_ID)


def test_remote_mirror_failure_is_safe_and_stop_recovers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, sql_source: str
) -> None:
    """Persistent availability exhausts a short bound safely. Failures stay loud. Stop recovers."""
    # Non-255 availability exhaustion: the safe stage/class/status diagnostics are retained and no
    # second launch is attempted.
    root, fake, runner = _scenario(
        tmp_path, monkeypatch, "exhaust-availability", initial_database=sql_source
    )
    try:
        started = remote_stages.run_translation_lifecycle_command(
            "start", runner=runner, session_id_factory=lambda: SESSION_ID, sleep=time.sleep
        )
        assert started.lifecycle in {"starting", "running"}
        _wait_for(lambda: len(read_fake(fake)["detached"]) >= 1)
        add_fault(
            fake, method="run", token=" status ", fault_type="availability", rc=1, remaining=-1
        )
        state_root = _state_root(root, "translation")
        _wait_for(lambda: read_lifecycle_state(state_root).lifecycle == "failed", timeout=40)
        failed = read_lifecycle_state(state_root)
        assert failed is not None and failed.failure is not None
        assert failed.failure.step == "status"
        assert failed.failure.error_type == "WorkerConnectionLost"
        assert failed.failure.returncode == 1
        assert failed.worker is not None and failed.worker.worker_prepared
        assert failed.worker.keepalive_pid is not None
        assert len(read_fake(fake)["detached"]) == 1

        # Clear the fault. An ordinary stop verifies, returns, cleans and clears every diagnostic.
        _clear_faults(fake)
        release_model_response(fake)
        stopped = remote_stages.run_translation_lifecycle_command(
            "stop", runner=runner, sleep=time.sleep
        )
        assert stopped.lifecycle == "idle"
        assert _worker_state("translation", root, SESSION_ID).lifecycle == "cleaned"
        final = read_lifecycle_state(state_root)
        assert final is not None and final.failure is None and final.stop_failure is None
        assert _receipt_path(root, SESSION_ID).is_file()
    finally:
        runner.close()
        _cleanup_scenario(root, SESSION_ID)

    # Timeout exhaustion has the same safe shape with a null available status.
    root, fake, runner = _scenario(
        tmp_path, monkeypatch, "exhaust-timeout", initial_database=sql_source
    )
    try:
        remote_stages.run_translation_lifecycle_command(
            "start", runner=runner, session_id_factory=lambda: SESSION_ID, sleep=time.sleep
        )
        _wait_for(lambda: len(read_fake(fake)["detached"]) >= 1)
        add_fault(fake, method="run", token=" status ", fault_type="timeout", rc=None, remaining=-1)
        state_root = _state_root(root, "translation")
        _wait_for(lambda: read_lifecycle_state(state_root).lifecycle == "failed", timeout=40)
        failed = read_lifecycle_state(state_root)
        assert failed is not None and failed.failure is not None
        assert failed.failure.step == "status"
        assert failed.failure.error_type == "WorkerConnectionLost"
        assert failed.failure.returncode is None
    finally:
        runner.close()
        _cleanup_scenario(root, SESSION_ID)

    # A completed helper that exits 255 fails immediately as a command error, not an availability
    # retry, and never launches work.
    root, fake, runner = _scenario(
        tmp_path, monkeypatch, "command-failure", initial_database=sql_source
    )
    try:
        remote_stages.run_translation_lifecycle_command(
            "start", runner=runner, session_id_factory=lambda: SESSION_ID, sleep=time.sleep
        )
        _wait_for(lambda: len(read_fake(fake)["detached"]) >= 1)
        add_fault(fake, method="run", token=" status ", fault_type="command", rc=255, remaining=-1)
        state_root = _state_root(root, "translation")
        _wait_for(lambda: read_lifecycle_state(state_root).lifecycle == "failed", timeout=40)
        failed = read_lifecycle_state(state_root)
        assert failed is not None and failed.failure is not None
        assert failed.failure.step == "status"
        assert failed.failure.error_type == "WorkerCommandError"
        assert failed.failure.returncode == 255
        assert read_fake(fake)["fault_consumed"] == 1
        assert len(read_fake(fake)["detached"]) == 1
    finally:
        runner.close()
        _cleanup_scenario(root, SESSION_ID)

    # An unproved launch (the launcher response is lost before any effect) fails as a `launch`
    # step after the acknowledgment budget expires, and the detached launch is never repeated.
    root, fake, runner = _scenario(
        tmp_path, monkeypatch, "unproved-launch", initial_database=sql_source
    )
    try:
        add_fault(
            fake,
            method="start_detached",
            fault_type="availability",
            rc=None,
            remaining=-1,
        )
        remote_stages.run_translation_lifecycle_command(
            "start", runner=runner, session_id_factory=lambda: SESSION_ID, sleep=time.sleep
        )
        state_root = _state_root(root, "translation")
        _wait_for(lambda: read_lifecycle_state(state_root).lifecycle == "failed", timeout=40)
        failed = read_lifecycle_state(state_root)
        assert failed is not None and failed.failure is not None
        assert failed.failure.step == "launch"
        assert failed.failure.error_type == "WorkerConnectionLost"
        assert read_fake(fake)["detached"] == []
    finally:
        runner.close()
        _cleanup_scenario(root, SESSION_ID)

    # A lost fresh-prepare acknowledgment is one-shot: the prepare effect may already have run, so
    # the server fails loudly at bring_up without replaying it, never records worker_prepared and
    # never launches the worker.
    root, fake, runner = _scenario(
        tmp_path, monkeypatch, "ambiguous-fresh-prepare", initial_database=sql_source
    )
    try:
        add_fault(
            fake,
            method="run",
            token=" prepare ",
            position="after",
            fault_type="availability",
            rc=1,
            remaining=1,
        )
        remote_stages.run_translation_lifecycle_command(
            "start", runner=runner, session_id_factory=lambda: SESSION_ID, sleep=time.sleep
        )
        state_root = _state_root(root, "translation")
        _wait_for(lambda: read_lifecycle_state(state_root).lifecycle == "failed", timeout=40)
        failed = read_lifecycle_state(state_root)
        assert failed is not None and failed.failure is not None
        assert failed.failure.step == "bring_up"
        assert failed.failure.error_type == "WorkerAvailabilityError"
        assert failed.failure.returncode == 1
        assert failed.worker is not None and failed.worker.worker_prepared is False
        observed = read_fake(fake)
        assert observed["fault_consumed"] == 1
        assert observed["detached"] == []
        prepare_calls = [
            call
            for call in observed["calls"]
            if any(part.endswith("controller_worker") for part in call) and call[-2] == "prepare"
        ]
        assert len(prepare_calls) == 1
    finally:
        runner.close()
        _cleanup_scenario(root, SESSION_ID)

    # A pending stop during a retry cancels admission, publishes the real intent without starting a run
    # attempt, and afterwards the ordinary stop recovers once the external fault is cleared.
    root, fake, runner = _scenario(
        tmp_path, monkeypatch, "pending-control", initial_database=sql_source, stop_timeout="1.5"
    )
    try:
        remote_stages.run_translation_lifecycle_command(
            "start", runner=runner, session_id_factory=lambda: SESSION_ID, sleep=time.sleep
        )
        _wait_for(lambda: len(read_fake(fake)["detached"]) >= 1)
        add_fault(
            fake, method="run", token=" status ", fault_type="availability", rc=1, remaining=-1
        )
        _wait_for(lambda: read_fake(fake)["fault_consumed"] >= 1)
        release_model_response(fake)
        with pytest.raises(WorkerConnectionLost):
            remote_stages.run_translation_lifecycle_command("stop", runner=runner, sleep=time.sleep)
        state_root = _state_root(root, "translation")
        stopped = read_lifecycle_state(state_root)
        assert stopped is not None and stopped.lifecycle == "stopped"
        assert stopped.stop_failure is not None
        assert stopped.stop_failure.step == "worker_finalize"
        assert stopped.stop_failure.error_type == "WorkerConnectionLost"
        assert len(read_fake(fake)["detached"]) == 1

        _clear_faults(fake)
        recovered = remote_stages.run_translation_lifecycle_command(
            "stop", runner=runner, sleep=time.sleep
        )
        assert recovered.lifecycle == "idle"
        final = read_lifecycle_state(state_root)
        assert final is not None and final.stop_failure is None
    finally:
        runner.close()
        _cleanup_scenario(root, SESSION_ID)


def test_failed_return_is_recorded_and_rerun_stop_recovers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, sql_source: str
) -> None:
    """An exhausted availability loss before server retention is recorded safely and a re-run stop
    reuses the completed export, verifies once, cleans and clears the record. A genuine helper error
    is loud. No worker deletion or receipt fabrication happens on the failed stop."""
    root, fake, runner = _scenario(
        tmp_path, monkeypatch, "failed-return", initial_database=sql_source, stop_timeout="3"
    )
    try:
        remote_stages.run_translation_lifecycle_command(
            "start", runner=runner, session_id_factory=lambda: SESSION_ID, sleep=time.sleep
        )
        _wait_for(lambda: len(read_fake(fake)["detached"]) >= 1)
        release_model_response(fake)
        add_fault(fake, method="download", fault_type="availability", rc=3, remaining=-1)
        with pytest.raises(WorkerConnectionLost):
            remote_stages.run_translation_lifecycle_command("stop", runner=runner, sleep=time.sleep)
        state_root = _state_root(root, "translation")
        failed = read_lifecycle_state(state_root)
        assert failed is not None and failed.stop_failure is not None
        assert failed.stop_failure.step == "return"
        assert failed.stop_failure.error_type == "WorkerConnectionLost"
        assert failed.stop_failure.returncode == 3
        assert failed.failure is None
        assert _worker_state("translation", root, SESSION_ID).lifecycle != "cleaned"
        assert not _receipt_path(root, SESSION_ID).exists()

        # Public status exposes the same content-free record, and the worker evidence is retained.
        status = remote_stages.run_translation_lifecycle_command(
            "status", runner=runner, sleep=time.sleep
        )
        assert status.stop_failure == failed.stop_failure

        # Clear the fault: the re-run ordinary stop verifies once, cleans and clears the record.
        _clear_faults(fake)
        stopped = remote_stages.run_translation_lifecycle_command(
            "stop", runner=runner, sleep=time.sleep
        )
        assert stopped.lifecycle == "idle"
        assert _receipt_path(root, SESSION_ID).is_file()
        assert _worker_state("translation", root, SESSION_ID).lifecycle == "cleaned"
        final = read_lifecycle_state(state_root)
        assert final is not None and final.stop_failure is None
    finally:
        runner.close()
        _cleanup_scenario(root, SESSION_ID)

    # A genuine completed helper error is terminal, not an availability retry.
    root, fake, runner = _scenario(
        tmp_path, monkeypatch, "return-helper-error", initial_database=sql_source, stop_timeout="3"
    )
    try:
        remote_stages.run_translation_lifecycle_command(
            "start", runner=runner, session_id_factory=lambda: SESSION_ID, sleep=time.sleep
        )
        _wait_for(lambda: len(read_fake(fake)["detached"]) >= 1)
        release_model_response(fake)
        add_fault(fake, method="run", token=" export ", fault_type="command", rc=255, remaining=-1)
        with pytest.raises(WorkerCommandError):
            remote_stages.run_translation_lifecycle_command("stop", runner=runner, sleep=time.sleep)
        state_root = _state_root(root, "translation")
        failed = read_lifecycle_state(state_root)
        assert failed is not None and failed.stop_failure is not None
        assert failed.stop_failure.step == "return"
        assert failed.stop_failure.error_type == "WorkerCommandError"
        assert failed.stop_failure.returncode == 255
        assert read_fake(fake)["fault_consumed"] == 1
        assert not _receipt_path(root, SESSION_ID).exists()
    finally:
        runner.close()
        _cleanup_scenario(root, SESSION_ID)
