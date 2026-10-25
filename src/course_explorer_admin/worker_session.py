"""One shared worker-side lifecycle shell for every remote stage.

This module is the one owner of the worker-host process observation and cooperative-control
mechanics shared by the translation and inference worker helpers, and also of their shared
lifecycle shell. A stage injects a :class:`WorkerStage`
implementation with its own state/policy records and its genuinely different prepare/run/finalize
bodies, while every shared decision (identity/quiescence refusals, owned-runtime retirement,
control publication, status projection, main subcommands) lives here once. The single
``await_worker_quiescence`` owner bounds every wait with the shared stop timeout and accepts only a
real recorded exit (plus an optional stage predicate) on each re-validated read.
"""

from __future__ import annotations

import argparse
import math
import os
import sys
import time
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel

from course_explorer.administration import (
    administrative_json,
    atomic_write_private_text,
    load_private_model,
    utc_now,
)
from course_explorer.config import WorkerConnectionSettings, load_raw_database_settings
from course_explorer.datasets import (
    DatasetReceipt,
    require_database_schema,
    require_selected_dataset_root,
)
from course_explorer.db.session import create_database_engine
from course_explorer_admin import mechanics, remote
from course_explorer_admin.remote import WorkerControl, WorkerControllerStatus, WorkerDatasetSession
from course_explorer_admin.runtime import OwnedWorkerRuntime

_TERMINAL_LIFECYCLES = {"stopped", "completed", "failed"}


class WorkerState(Protocol):
    """The neutral subset of one stage worker's durable state used for observation."""

    schema_version: int
    session_id: str
    lifecycle: str
    runner_pid: int | None
    runtime_pid: int | None


class WorkerStage[StateT: WorkerState, PolicyT: BaseModel](Protocol):
    """The two-stage worker seam the shared shell drives.

    A stage exposes only its own identity/loaders and the genuinely stage-specific bodies. The
    shell owns every shared refusal, wait, control publication, status projection and subcommand.
    """

    name: Literal["translation", "inference"]
    controller_name: str
    cleanup_artifacts: tuple[str, ...]

    def connection(self) -> WorkerConnectionSettings: ...

    def load_session(self, session_id: str) -> tuple[WorkerDatasetSession, PolicyT, Path]: ...

    def load_state(self, path: Path) -> StateT: ...

    def require_policy(self, session: WorkerDatasetSession, policy: PolicyT) -> None: ...

    def publish_prepared(
        self, session: WorkerDatasetSession, directory: Path
    ) -> WorkerControllerStatus: ...

    def run(
        self,
        session: WorkerDatasetSession,
        directory: Path,
        state: StateT,
        *,
        runner: mechanics.ProcessRunner,
        sleep: Callable[[float], None],
        clock: Callable[[], datetime],
        monotonic: Callable[[], float],
    ) -> int: ...

    def read_import_receipt(
        self, session: WorkerDatasetSession, state: StateT, directory: Path
    ) -> BaseModel | None: ...

    def finalize(self, session: WorkerDatasetSession, state: StateT, directory: Path) -> None: ...

    def status(
        self,
        session: WorkerDatasetSession,
        state: StateT,
        directory: Path,
        *,
        clock: Callable[[], datetime],
        lifecycle: str | None,
    ) -> WorkerControllerStatus: ...

    def stop_updates(self, state: StateT, directory: Path) -> dict[str, object]: ...

    def require_cleanup_evidence(
        self, session: WorkerDatasetSession, receipt: BaseModel, directory: Path
    ) -> None: ...


def worker_runner_is_alive(state: WorkerState, directory: Path) -> bool:
    """Observe whether the session's runner is the exact owned runner process.

    A present ``runner.json`` is loaded strictly and observed through the shared boot/argv
    check FIRST. A proven dead, other-boot, or empty-command record reports not-live without
    comparing a stale display PID, which recovers the interrupted publication window between
    the runner-record write and the starting-state write. A live record whose nonempty argv
    differs from the recorded argv raises through that observer. Only a proven live record is
    compared against a non-null display ``runner_pid``, and a mismatch raises the
    fixed error. A symlinked or malformed record fails loudly. A missing record is not
    live.
    """
    path = directory / "runner.json"
    if path.is_symlink():
        raise ValueError("runner ownership record must not be a symlink")
    if not path.exists():
        return False
    record = load_private_model(path, mechanics.OwnedProcessRecord)
    if not mechanics.owned_process_is_alive(record):
        return False
    if state.runner_pid is not None and state.runner_pid != record.pid:
        raise ValueError("runner ownership record does not match the recorded runner")
    return True


def worker_runtime_is_alive(state: WorkerState, directory: Path) -> bool:
    """Observe whether the session's model runtime is the exact owned runtime.

    A present ``runtime.json`` is loaded strictly and observed through the shared boot/argv
    check. A symlinked or malformed record fails loudly. When no record exists the observation
    reports not-live.
    """
    path = directory / "runtime.json"
    if path.is_symlink():
        raise ValueError("runtime ownership record must not be a symlink")
    if path.exists():
        record = load_private_model(path, mechanics.OwnedProcessRecord)
        return mechanics.owned_process_is_alive(record)
    return False


def require_worker_quiescence(state: WorkerState, directory: Path) -> None:
    """Refuse a locked decision while either owned process record is live.

    The pre-lock bounded wait is not authoritative: a fast intervening run can release the
    instance lock with terminal state while its runner is exiting. Under that lock this
    re-observes only the runner/runtime records, writing no signal, file, or wait and loading no
    other record, and raises the fixed safe error instead of acting on stale quiescence.
    """
    if worker_runner_is_alive(state, directory) or worker_runtime_is_alive(state, directory):
        raise ValueError("worker session is not quiescent")


def require_worker_database_schema(session: WorkerDatasetSession) -> None:
    """Require the received worker database to match this worker code's Alembic head.

    The raw database settings are copied with the session's exact derived database name, one engine
    is opened through the shared owner, and the single factored schema check runs once before the
    engine is disposed. A mismatch raises the schema error before any work.
    """
    settings = load_raw_database_settings().model_copy(
        update={"postgres_db": session.database_name}
    )
    engine = create_database_engine(settings)
    try:
        with engine.connect() as connection:
            require_database_schema(connection)
    finally:
        engine.dispose()


def write_runner_record(directory: Path, record: mechanics.OwnedProcessRecord) -> None:
    """Atomically publish the worker invocation's own boot/argv runner ownership record."""
    atomic_write_private_text(directory / "runner.json", administrative_json(record))


def read_control(directory: Path, session: WorkerDatasetSession) -> WorkerControl:
    """Read live control and require it to describe exactly the requested session."""
    current = load_private_model(directory / "control.json", WorkerControl)
    if current.session_id != session.session_id:
        raise ValueError("control file identity does not match the session")
    return current


def write_worker_control(directory: Path, control: WorkerControl) -> None:
    """Atomically publish one cooperative worker control at mode 0600."""
    atomic_write_private_text(directory / "control.json", administrative_json(control))


def publish_worker_control(
    directory: Path,
    session: WorkerDatasetSession,
    action: Literal["run", "pause", "stop"],
    *,
    rearm: bool = False,
) -> None:
    """Publish one cooperative control under the disjoint per-session controls lock.

    ``directory`` always means the canonical session directory and the control file is
    ``directory/control.json``. The disjoint ``controls`` lock is not ``directory/controller.lock``
    and is released before any wait or worker instance lock. Stop always writes stop. Pause
    preserves a stop. Run refuses a pause/stop unless ``rearm=True``, which is
    used only by a locked retained resume.
    """
    lock_root = directory / "controls"
    require_selected_dataset_root(lock_root)
    with mechanics.exclusive_action_lock(lock_root, controller_name="worker control", create=True):
        current = read_control(directory, session)
        if action == "stop":
            requested: Literal["run", "pause", "stop"] = "stop"
        elif action == "pause":
            requested = "stop" if current.requested_action == "stop" else "pause"
        elif current.requested_action in {"pause", "stop"} and not rearm:
            raise ValueError("cannot clear a pending pause or stop without re-arming")
        else:
            requested = "run"
        write_worker_control(
            directory,
            WorkerControl(
                schema_version=1,
                session_id=session.session_id,
                requested_action=requested,
            ),
        )


def await_worker_quiescence(
    connection: WorkerConnectionSettings,
    *,
    directory: Path,
    read_state: Callable[[], WorkerState],
    runner_only: bool = False,
    accepted: Callable[[WorkerState], bool] | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Wait boundedly until the owned processes observe a real exit and any predicate holds.

    Acceptance combines the actual recorded runner/runtime observations with the optional stage
    predicate on the same re-validated read, so a null display PID or a state label alone is never
    exit proof. The bound is the stop timeout measured with a monotonic deadline, never
    the health attempt count.
    """
    deadline = time.monotonic() + connection.stop_timeout_seconds
    attempts = max(
        1, math.ceil(connection.stop_timeout_seconds / connection.poll_interval_seconds) + 1
    )

    def accept(current: WorkerState) -> bool:
        if worker_runner_is_alive(current, directory):
            return False
        if not runner_only and worker_runtime_is_alive(current, directory):
            return False
        return accepted is None or accepted(current)

    mechanics.await_state(
        read_state,
        accept,
        attempts=attempts,
        interval=connection.poll_interval_seconds,
        sleep=sleep,
        expired=lambda: time.monotonic() >= deadline,
    )


def write_worker_state(directory: Path, state: BaseModel) -> None:
    """Atomically publish one stage worker state record at mode 0600.

    It is a publication primitive: callers hold the instance lock and
    preserve live intent themselves.
    """
    atomic_write_private_text(directory / "state.json", administrative_json(state))


def _load_worker_control_state[StateT: WorkerState](
    stage: WorkerStage[StateT, BaseModel], session: WorkerDatasetSession, directory: Path
) -> tuple[WorkerControl, StateT]:
    """Load control/state and require them to describe this already-loaded session."""
    control = load_private_model(directory / "control.json", WorkerControl)
    state = stage.load_state(directory / "state.json")
    if control.session_id != session.session_id or state.session_id != session.session_id:
        raise ValueError("control or state file identity does not match the requested session")
    return control, state


def _quiescence_read[StateT: WorkerState](
    stage: WorkerStage[StateT, BaseModel], session: WorkerDatasetSession, directory: Path
) -> Callable[[], StateT]:
    """Return an identity-revalidating state read for the shared quiescence owner."""

    def read() -> StateT:
        current = stage.load_state(directory / "state.json")
        if current.session_id != session.session_id:
            raise ValueError("worker state identity does not match the session")
        return current

    return read


def _require_canonical_run_environment[StateT: WorkerState, PolicyT: BaseModel](
    stage: WorkerStage[StateT, PolicyT],
    session: WorkerDatasetSession,
    policy: PolicyT,
) -> None:
    """Require the current policy and raw session-database environment before any write."""
    stage.require_policy(session, policy)
    raw = load_raw_database_settings()
    if raw.selected_dataset_enabled or raw.postgres_db != session.database_name:
        raise ValueError("canonical worker run requires the session database environment")


def prepare_worker_session[StateT: WorkerState, PolicyT: BaseModel](
    stage: WorkerStage[StateT, PolicyT],
    session: WorkerDatasetSession,
    *,
    runner: mechanics.ProcessRunner,
) -> WorkerControllerStatus:
    """Prepare or acknowledge one canonical shared-dataset session.

    The shared canonical loader supplies the session, policy, and directory under the same worker
    instance lock. An already-prepared acknowledgement is reused without restore or selection.
    """
    recorded, policy, directory = stage.load_session(session.session_id)
    if recorded != session:
        raise ValueError("uploaded canonical session does not match the requested session")
    stage.require_policy(session, policy)

    with mechanics.exclusive_action_lock(directory, controller_name=stage.controller_name):
        for name in ("import-receipt.json", "return.json"):
            path = directory / name
            if path.exists() or path.is_symlink():
                raise ValueError("canonical session already has import or return evidence")
        control_path = directory / "control.json"
        state_path = directory / "state.json"
        control_present = control_path.exists() or control_path.is_symlink()
        state_present = state_path.exists() or state_path.is_symlink()
        if control_present != state_present:
            raise ValueError("canonical control and state must both be present or both absent")
        if control_present:
            _control, state = _load_worker_control_state(stage, session, directory)
            if state.lifecycle != "prepared":
                raise ValueError("canonical prepared acknowledgement requires prepared state")
            require_worker_quiescence(state, directory)
            require_worker_database_schema(session)
            return stage.status(
                session, state, directory=directory, clock=utc_now, lifecycle="prepared"
            )
        for name in ("runner.json", "runtime.json"):
            path = directory / name
            if path.exists() or path.is_symlink():
                raise ValueError("canonical session has process evidence without prepared state")
        remote.prepare_worker_database(session, runner=runner)
        return stage.publish_prepared(session, directory)


def run_worker_session[StateT: WorkerState, PolicyT: BaseModel](
    stage: WorkerStage[StateT, PolicyT],
    session_id: str,
    *,
    runner: mechanics.ProcessRunner,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], datetime] = utc_now,
    monotonic: Callable[[], float] = time.monotonic,
) -> int:
    """Run one prepared or retained session to completion or cooperative stop.

    The whole invocation holds the session instance lock, so two launches can never race over
    the same state or ownership record. A retained nonterminal session whose recorded
    runner disappeared after a worker host shutdown is resumed here through the stage body's
    durable checkpoints. A live duplicate runner and completed/cleaned work are rejected before
    any model or command work.
    """
    settings = stage.connection()
    session, policy, directory = stage.load_session(session_id)
    with mechanics.exclusive_action_lock(directory, controller_name=stage.controller_name):
        return _run_worker_session(
            stage,
            session,
            directory,
            settings,
            policy=policy,
            runner=runner,
            sleep=sleep,
            clock=clock,
            monotonic=monotonic,
        )


def _run_worker_session[StateT: WorkerState, PolicyT: BaseModel](
    stage: WorkerStage[StateT, PolicyT],
    session: WorkerDatasetSession,
    directory: Path,
    settings: WorkerConnectionSettings,
    *,
    policy: PolicyT,
    runner: mechanics.ProcessRunner,
    sleep: Callable[[float], None],
    clock: Callable[[], datetime],
    monotonic: Callable[[], float],
) -> int:
    """Run one session under the already-held instance lock."""
    _control, state = _load_worker_control_state(stage, session, directory)
    _require_canonical_run_environment(stage, session, policy)
    if stage.read_import_receipt(session, state, directory) is not None:
        raise ValueError("canonical worker session is already imported")
    return_path = directory / "return.json"
    if return_path.exists() or return_path.is_symlink():
        raise ValueError("canonical worker session already has return evidence")
    if state.lifecycle in {"completed", "cleaned"}:
        raise ValueError("worker session has no outstanding work to run")
    if state.lifecycle not in {"prepared", "starting", "running", "paused", "stopped", "failed"}:
        raise ValueError("worker session has no resumable lifecycle")
    if worker_runner_is_alive(state, directory):
        raise ValueError("worker session already has a live runner process")

    # Precondition before any runtime owner/clock construction, runtime stop/start, runner-record,
    # selection, provider or job call: a received worker database that matches this worker code's
    # Alembic head. A mismatch fails here and changes no state.
    worker_root = settings.worker_project_root
    require_worker_database_schema(session)

    # Retire any runtime this session owns from a stopped invocation through the shared
    # owner before this invocation publishes its own ownership or starts a model.
    OwnedWorkerRuntime(runner, root=worker_root, directory=directory, sleep=sleep).stop(
        timeout=settings.stop_timeout_seconds, interval=settings.poll_interval_seconds
    )
    runner_pid = os.getpid()
    runner_argv = mechanics.read_process_command_line(runner_pid)
    if not runner_argv:
        raise ValueError("worker run requires its own readable command line")
    write_runner_record(
        directory,
        mechanics.OwnedProcessRecord(
            schema_version=1,
            pid=runner_pid,
            argv=runner_argv,
            boot_id=mechanics.current_boot_id(),
        ),
    )
    return stage.run(
        session,
        directory,
        state,
        runner=runner,
        sleep=sleep,
        clock=clock,
        monotonic=monotonic,
    )


def _await_runner_exit[StateT: WorkerState](
    stage: WorkerStage[StateT, BaseModel],
    settings: WorkerConnectionSettings,
    session: WorkerDatasetSession,
    *,
    directory: Path,
    sleep: Callable[[float], None],
) -> None:
    """Wait boundedly for an exiting runner record to disappear, ignoring the orphan runtime."""
    await_worker_quiescence(
        settings,
        directory=directory,
        read_state=_quiescence_read(stage, session, directory),
        runner_only=True,
        sleep=sleep,
    )


def _await_worker_quiescence[StateT: WorkerState](
    stage: WorkerStage[StateT, BaseModel],
    settings: WorkerConnectionSettings,
    session: WorkerDatasetSession,
    *,
    directory: Path,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Wait boundedly until both the runner and runtime records observe a real exit."""
    await_worker_quiescence(
        settings,
        directory=directory,
        read_state=_quiescence_read(stage, session, directory),
        sleep=sleep,
    )


def _await_live_action[StateT: WorkerState](
    stage: WorkerStage[StateT, BaseModel],
    settings: WorkerConnectionSettings,
    session: WorkerDatasetSession,
    directory: Path,
    targets: set[str],
    *,
    sleep: Callable[[float], None],
) -> None:
    """Wait boundedly for a live action's projected lifecycle plus real quiescence.

    Acceptance combines the projected lifecycle target with both the runner and runtime
    observations, so acceptance requires a matching projected lifecycle and live runner and
    runtime processes.
    """
    await_worker_quiescence(
        settings,
        directory=directory,
        read_state=_quiescence_read(stage, session, directory),
        accepted=lambda current: project_worker_lifecycle(current, directory=directory) in targets,
        sleep=sleep,
    )


def _stop_unloaded_session[StateT: WorkerState](
    stage: WorkerStage[StateT, BaseModel],
    session: WorkerDatasetSession,
    directory: Path,
    settings: WorkerConnectionSettings,
    *,
    runner: mechanics.ProcessRunner,
    sleep: Callable[[float], None],
    clock: Callable[[], datetime],
) -> WorkerControllerStatus:
    """Stop prepared, interrupted, or paused work without any provider call.

    Stop control is published first, then an exiting paused runner record is waited out with the
    runner observer alone. The orphan runtime may be live. Under the instance lock the state
    is re-read, a cleaned session or a live runner is refused before any runtime stop, and a
    natural terminal race is returned once quiescence is re-proved. Otherwise the owned
    runtime is stopped through the shared owner and the stage reconciles any retained count.
    Failure preserves evidence.
    """
    initial_state = stage.load_state(directory / "state.json")
    publish_worker_control(directory, session, "stop")
    if worker_runner_is_alive(initial_state, directory):
        _await_runner_exit(stage, settings, session, directory=directory, sleep=sleep)
    with mechanics.exclusive_action_lock(
        directory, controller_name=stage.controller_name, blocking=True
    ):
        state = stage.load_state(directory / "state.json")
        if state.session_id != session.session_id:
            raise ValueError("worker state identity does not match the session")
        if state.lifecycle == "cleaned":
            raise ValueError("worker session is already cleaned")
        if worker_runner_is_alive(state, directory):
            raise ValueError("worker session already has a live runner process")
        if state.lifecycle in _TERMINAL_LIFECYCLES:
            # A natural terminal race is returned after re-proving quiescence. It is
            # never cleared, relabelled, or counted again.
            require_worker_quiescence(state, directory)
            return stage.status(
                session, state, directory=directory, clock=clock, lifecycle=state.lifecycle
            )
        OwnedWorkerRuntime(
            runner, root=settings.worker_project_root, directory=directory, sleep=sleep
        ).stop(timeout=settings.stop_timeout_seconds, interval=settings.poll_interval_seconds)
        updated = state.model_copy(
            update={
                "lifecycle": "stopped",
                "runner_pid": None,
                "runtime_pid": None,
                "error_type": None,
                **stage.stop_updates(state, directory),
            }
        )
        write_worker_state(directory, updated)
    return read_worker_status(stage, session.session_id, clock=clock)


def _rearm_retained_session[StateT: WorkerState](
    stage: WorkerStage[StateT, BaseModel],
    session: WorkerDatasetSession,
    directory: Path,
    settings: WorkerConnectionSettings,
    *,
    runner: mechanics.ProcessRunner,
    sleep: Callable[[float], None],
    clock: Callable[[], datetime],
) -> WorkerControllerStatus:
    """Re-arm retained work to ``run`` without launching anything.

    The retained runner record is waited out, then under the instance lock the state is re-read, a
    cleaned session or a live runner is refused, and a natural completed race is returned
    once quiescence is re-proved, before any runtime stop or control publication.
    Otherwise the retained owned runtime is stopped, both records are proved quiescent, and
    ``run`` is published. It never relabels a paused session as running.
    """
    _await_runner_exit(stage, settings, session, directory=directory, sleep=sleep)
    with mechanics.exclusive_action_lock(
        directory, controller_name=stage.controller_name, blocking=True
    ):
        state = stage.load_state(directory / "state.json")
        if state.session_id != session.session_id:
            raise ValueError("worker state identity does not match the session")
        if state.lifecycle == "cleaned":
            raise ValueError("worker session is already cleaned")
        if worker_runner_is_alive(state, directory):
            raise ValueError("worker session already has a live runner process")
        # An intervening finalize/return that arrived while waiting is never re-armed.
        if stage.read_import_receipt(session, state, directory) is not None:
            raise ValueError("canonical worker session is already imported")
        return_path = directory / "return.json"
        if return_path.exists() or return_path.is_symlink():
            raise ValueError("canonical worker session already has return evidence")
        if state.lifecycle == "completed":
            # A completed race is returned after re-proving quiescence, before any
            # runtime stop or ``run`` publication, so the completed control record is reused.
            require_worker_quiescence(state, directory)
            return stage.status(
                session, state, directory=directory, clock=clock, lifecycle=state.lifecycle
            )
        require_worker_database_schema(session)
        OwnedWorkerRuntime(
            runner, root=settings.worker_project_root, directory=directory, sleep=sleep
        ).stop(timeout=settings.stop_timeout_seconds, interval=settings.poll_interval_seconds)
        _await_worker_quiescence(stage, settings, session, directory=directory, sleep=sleep)
        publish_worker_control(directory, session, "run", rearm=True)
    return read_worker_status(stage, session.session_id, clock=clock)


def request_worker_action[StateT: WorkerState](
    stage: WorkerStage[StateT, BaseModel],
    session_id: str,
    action: str,
    *,
    runner: mechanics.ProcessRunner,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], datetime] = utc_now,
) -> WorkerControllerStatus:
    """Atomically change only the control request and acknowledge the real lifecycle.

    Resume re-arms retained work and launches nothing. Pause and stop publish their control
    request and wait for the projected lifecycle plus actual runner/runtime quiescence. Stop
    also handles prepared, interrupted, or unloaded paused work without any provider call,
    and a natural terminal race is returned as its real status. An unacknowledged action
    raises for a lifecycle the worker never reached. A valid terminal import
    receipt is never re-armed or relaunched: resume waits for quiescence and returns the imported
    status, and return evidence without an import refuses resume.
    """
    if action not in {"pause", "resume", "stop"}:
        raise ValueError("action must be pause, resume, or stop")
    settings = stage.connection()
    session, _policy, directory = stage.load_session(session_id)
    _control, state = _load_worker_control_state(stage, session, directory)
    if state.lifecycle == "cleaned":
        raise ValueError("worker session is already cleaned")
    terminal = _TERMINAL_LIFECYCLES
    projected = project_worker_lifecycle(state, directory=directory)

    if action == "resume":
        if stage.read_import_receipt(session, state, directory) is not None:
            # Finalized work is never re-armed. The real imported status is returned instead.
            _await_worker_quiescence(stage, settings, session, directory=directory, sleep=sleep)
            return read_worker_status(stage, session_id, clock=clock)
        return_path = directory / "return.json"
        if return_path.exists() or return_path.is_symlink():
            raise ValueError("canonical worker session has return evidence without import")

    if action == "stop" and projected in {"prepared", "interrupted", "paused"}:
        return _stop_unloaded_session(
            stage, session, directory, settings, runner=runner, sleep=sleep, clock=clock
        )

    if action == "resume":
        if projected in {"starting", "running"}:
            return read_worker_status(stage, session_id, clock=clock)
        if projected == "completed":
            # A completed race is returned after quiescence without changing control.
            _await_worker_quiescence(stage, settings, session, directory=directory, sleep=sleep)
            return read_worker_status(stage, session_id, clock=clock)
        if projected in {"prepared", "paused", "interrupted", "stopped", "failed"}:
            return _rearm_retained_session(
                stage, session, directory, settings, runner=runner, sleep=sleep, clock=clock
            )
        raise ValueError("resume requires a retained or live worker session")

    if action == "pause":
        if projected == "paused" or projected in terminal:
            _await_worker_quiescence(stage, settings, session, directory=directory, sleep=sleep)
            return read_worker_status(stage, session_id, clock=clock)
        if projected not in {"starting", "running"}:
            raise ValueError("pause requires a live running or starting worker session")
        publish_worker_control(directory, session, "pause")
        _await_live_action(stage, settings, session, directory, {"paused"} | terminal, sleep=sleep)
        return read_worker_status(stage, session_id, clock=clock)

    if projected not in {"starting", "running", "paused"}:
        raise ValueError("stop requires a live running, starting, or paused worker session")
    publish_worker_control(directory, session, "stop")
    _await_live_action(stage, settings, session, directory, terminal, sleep=sleep)
    return read_worker_status(stage, session_id, clock=clock)


def project_worker_lifecycle(state: WorkerState, *, directory: Path) -> str:
    """Project durable state, reporting a vanished live runner as ``interrupted``.

    Paused/terminal states are unloaded and project their durable lifecycle. A starting/running state
    projects ``interrupted`` when the shared runner observation is false. No state is rewritten
    here: status is a read-only read.
    """
    if state.lifecycle in {"starting", "running"} and not worker_runner_is_alive(state, directory):
        return "interrupted"
    return state.lifecycle


def read_worker_status[StateT: WorkerState](
    stage: WorkerStage[StateT, BaseModel],
    session_id: str,
    *,
    clock: Callable[[], datetime] = utc_now,
) -> WorkerControllerStatus:
    """Read strict worker state and derive one text-free operator status."""
    session, _policy, directory = stage.load_session(session_id)
    state = stage.load_state(directory / "state.json")
    if state.session_id != session_id:
        raise ValueError("worker state identity does not match the session")
    return stage.status(
        session,
        state,
        directory=directory,
        clock=clock,
        lifecycle=project_worker_lifecycle(state, directory=directory),
    )


def finalize_worker_session[StateT: WorkerState](
    stage: WorkerStage[StateT, BaseModel],
    session_id: str,
    *,
    runner: mechanics.ProcessRunner,
) -> WorkerControllerStatus:
    """Finalize one canonical terminal session exactly once through the stage body.

    After waiting for real quiescence it takes the worker instance lock, re-reads the terminal
    identity/state, re-proves quiescence, and lets the stage import/publish only when no retained
    receipt exists. It never launches a model or fabricates a report.
    """
    settings = stage.connection()
    session, _policy, directory = stage.load_session(session_id)
    state = stage.load_state(directory / "state.json")
    if state.session_id != session_id:
        raise ValueError("worker state identity does not match the session")
    if state.lifecycle not in _TERMINAL_LIFECYCLES:
        raise ValueError("finalize requires a stopped, completed, or failed worker session")
    _await_worker_quiescence(stage, settings, session, directory=directory)

    with mechanics.exclusive_action_lock(
        directory, controller_name=stage.controller_name, blocking=True
    ):
        state = stage.load_state(directory / "state.json")
        if state.session_id != session_id:
            raise ValueError("worker state identity does not match the session")
        if state.lifecycle not in _TERMINAL_LIFECYCLES:
            raise ValueError("finalize requires a stopped, completed, or failed worker session")
        require_worker_quiescence(state, directory)
        if stage.read_import_receipt(session, state, directory) is None:
            # A fresh finalize does derived/publication work. The received worker database must
            # match this worker code's own Alembic head before that work. A receipt-only retry
            # is usable after a drop.
            require_worker_database_schema(session)
            stage.finalize(session, state, directory)
    return stage.status(session, state, directory=directory, clock=utc_now, lifecycle=None)


def cleanup_worker_session[StateT: WorkerState](
    stage: WorkerStage[StateT, BaseModel],
    session_id: str,
    *,
    runner: mechanics.ProcessRunner,
) -> WorkerControllerStatus:
    """Drop only the exact derived database and remove transferred/generated evidence.

    Cleanup requires its terminal lifecycles, waits for real runner/runtime quiescence,
    then takes the session instance lock and re-reads identity/state before the receipt-gated drop
    and evidence removal. The shared quiescence guard re-proves ownership under the lock, so a
    concurrently restarted run can never be cleaned out from under itself and ``runner.json`` is
    removed only after that proof. Cleanup requires the stage import receipt, the stage's own
    retained-output proof, and the verified server-return proof before the exact database drop,
    and retains the canonical evidence a subsequent cleanup retry needs.
    """
    settings = stage.connection()
    session, _policy, directory = stage.load_session(session_id)
    state = stage.load_state(directory / "state.json")
    if state.session_id != session_id:
        raise ValueError("worker state identity does not match the session")
    if state.lifecycle in {"running", "paused", "starting", "prepared"}:
        raise ValueError("cleanup requires a terminal worker session")
    _await_worker_quiescence(stage, settings, session, directory=directory)

    with mechanics.exclusive_action_lock(
        directory, controller_name=stage.controller_name, blocking=True
    ):
        state = stage.load_state(directory / "state.json")
        if state.session_id != session_id:
            raise ValueError("worker state identity does not match the session")
        if state.lifecycle in {"running", "paused", "starting", "prepared"}:
            raise ValueError("cleanup requires a terminal worker session")
        require_worker_quiescence(state, directory)
        receipt = stage.read_import_receipt(session, state, directory)
        if receipt is None:
            raise ValueError("canonical cleanup requires an import receipt")
        stage.require_cleanup_evidence(session, receipt, directory)
        dataset_receipt = load_private_model(directory / "dataset-receipt.json", DatasetReceipt)
        remote.cleanup_returned_worker_database(session, dataset_receipt, runner=runner)
        for name in stage.cleanup_artifacts:
            (directory / name).unlink(missing_ok=True)
        cleaned = state.model_copy(
            update={
                "lifecycle": "cleaned",
                "runner_pid": None,
                "runtime_pid": None,
                "error_type": None,
            }
        )
        write_worker_state(directory, cleaned)
    return stage.status(session, cleaned, directory=directory, clock=utc_now, lifecycle="cleaned")


def worker_main[StateT: WorkerState](
    stage: WorkerStage[StateT, BaseModel], argv: Sequence[str] | None = None
) -> int:
    """Expose the prepare/run/pause/resume/status/finalize/cleanup/stop subcommands."""
    parser = argparse.ArgumentParser(description=stage.name)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("prepare", "run", "pause", "resume", "status", "finalize", "cleanup", "stop"):
        subparsers.add_parser(name).add_argument("session_id")
    args = parser.parse_args(argv)
    session_id = args.session_id
    runner = mechanics.SubprocessRunner()
    try:
        if args.command == "prepare":
            session, _policy, _directory = stage.load_session(session_id)
            status = prepare_worker_session(stage, session, runner=runner)
            print(administrative_json(status), end="")
            return 0
        if args.command == "finalize":
            status = finalize_worker_session(stage, session_id, runner=runner)
            print(administrative_json(status), end="")
            return 0
        if args.command == "run":
            code = run_worker_session(stage, session_id, runner=runner)
            if code != 0:
                status = read_worker_status(stage, session_id)
                print(status.error_type or "RuntimeError", file=sys.stderr)
                return code
            if stage.name != "inference":
                # The inference stage prints no final success status. Its failure emission is the
                # job's own exhausted-failure line.
                print(administrative_json(read_worker_status(stage, session_id)), end="")
            return code
        if args.command == "status":
            print(administrative_json(read_worker_status(stage, session_id)), end="")
            return 0
        if args.command == "cleanup":
            print(
                administrative_json(cleanup_worker_session(stage, session_id, runner=runner)),
                end="",
            )
            return 0
        status = request_worker_action(stage, session_id, args.command, runner=runner)
        print(administrative_json(status), end="")
        return 0
    except Exception as exc:
        # Never print a raw traceback, untrusted text, or settings. Only the safe class name.
        print(type(exc).__name__, file=sys.stderr)
        return 1
