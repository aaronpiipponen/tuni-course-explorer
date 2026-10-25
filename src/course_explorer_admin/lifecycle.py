"""One shared lifecycle core for the ingestion, embedding, translation and inference stages.

This module owns the single detached lifecycle every stage uses: one mutable ``state.json``
per stage root that names the sole current session and carries control intent, the exact owned
process record, resource ownership and progress. One immutable ``session.json`` execution
receipt per session, and one short-held per-stage flock that serializes the real CLI and worker
writers of that one file. The public five-action algorithm (``start``/``pause``/``resume``/
``status``/``stop``) lives here exactly once. Each stage adapter delegates work selection, source
access, envelope verification, provenance, vector generation and product database access to its
product command.

The generic core loads only the neutral ``LocalLifecycleSettings``. A stage's
``require_prepared``/``require_database``/``run``/``finalize`` methods own every stage-specific
resource and product decision.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import uuid
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from course_explorer.administration import (
    administrative_json,
    atomic_write_private_text,
    load_private_model,
    repository_root,
    session_directory,
    sha256_file,
    utc_now,
)
from course_explorer.config import (
    LocalLifecycleSettings,
    load_inference_controller_settings,
    load_local_lifecycle_settings,
    load_translation_controller_settings,
)
from course_explorer.datasets import DatasetId, DatasetRevision, require_selected_dataset_root
from course_explorer.validation import (
    require_aware,
    require_error_type,
    require_finite_nonnegative,
    require_nonblank_text,
    require_sha256,
)
from course_explorer_admin import mechanics
from course_explorer_admin.inference.controller import InferenceControllerStatus
from course_explorer_admin.mechanics import ControllerAction
from course_explorer_admin.translation.controller import TranslationControllerStatus
from course_explorer_admin.transport import WorkerAvailabilityError

type StageName = Literal["ingestion", "embedding", "translation", "inference"]

_ACTIONS = ("start", "pause", "resume", "status", "stop")

_IngestionStage = Literal[
    "selecting",
    "verification",
    "capture",
    "before_normalization",
    "normalization",
    "complete",
]


class _LifecycleModel(BaseModel):
    """Frozen, closed DTO base for the text-free local-lifecycle contract."""

    model_config = ConfigDict(extra="forbid", frozen=True)


def _require_nonblank(value: str | None) -> str | None:
    if value is None:
        return value
    return require_nonblank_text(value, message="text identity values must not be blank")


type FailureStep = Literal[
    "session",
    "intent",
    "await_exit",
    "transport",
    "capture",
    "bring_up",
    "launch",
    "status",
    "release",
    "reboot",
    "finalize",
    "worker_finalize",
    "return",
    "worker_cleanup",
    "local_cleanup",
    "services",
    "idle",
]


class LifecycleFailure(_LifecycleModel):
    """One content-free durable failure breadcrumb.

    It retains only the closed step that was executing, the safe exception class name, and an
    available integer subprocess/availability status. No message, stream, argv, path, payload or
    cause chain is ever stored.
    """

    step: FailureStep | None = None
    error_type: str
    returncode: int | None = None

    @field_validator("error_type")
    @classmethod
    def validate_error_type(cls, value: str) -> str:
        return require_error_type(value, max_length=64)


def lifecycle_failure(step: FailureStep | None, exc: Exception) -> LifecycleFailure:
    """Extract only the safe step, class and available status from one failure."""
    if isinstance(exc, subprocess.CalledProcessError):
        returncode: int | None = exc.returncode
    elif isinstance(exc, WorkerAvailabilityError):
        returncode = exc.returncode
    else:
        returncode = None
    return LifecycleFailure(step=step, error_type=type(exc).__name__, returncode=returncode)


class IngestionOptions(_LifecycleModel):
    """The one ingestion operation a fresh session runs: full capture or a retained manifest."""

    kind: Literal["ingestion"]
    manifest_path: str | None = None

    @field_validator("manifest_path")
    @classmethod
    def validate_manifest_path(cls, value: str | None) -> str | None:
        return _require_nonblank(value)


class EmbeddingOptions(_LifecycleModel):
    """The one embedding operation a fresh session runs."""

    kind: Literal["embedding"]


class TranslationOptions(_LifecycleModel):
    """The one translation operation a fresh session runs."""

    kind: Literal["translation"]


class InferenceOptions(_LifecycleModel):
    """The one inference operation a fresh session runs."""

    kind: Literal["inference"]


StageOptions = Annotated[
    IngestionOptions | EmbeddingOptions | TranslationOptions | InferenceOptions,
    Field(discriminator="kind"),
]


class IngestionProgress(_LifecycleModel):
    """Observation of one ingestion session's durable capture/verification position."""

    kind: Literal["ingestion"]
    stage: _IngestionStage
    manifest_path: str | None = None
    run_id: uuid.UUID | None = None
    manifest_sha256: str | None = None
    response_count: int = Field(ge=0)
    verified_response_count: int = Field(ge=0)
    verification_total: int | None = Field(default=None, ge=0)
    normalized: bool

    @field_validator("manifest_path")
    @classmethod
    def validate_manifest_path(cls, value: str | None) -> str | None:
        return _require_nonblank(value)

    @field_validator("manifest_sha256")
    @classmethod
    def validate_manifest_sha256(cls, value: str | None) -> str | None:
        return None if value is None else require_sha256(value, "manifest_sha256")


class EmbeddingProgress(_LifecycleModel):
    """Observation of one embedding session's reconciled and generated coverage.

    ``items_per_second`` is the last measured current-invocation successful-work pace. It is
    ``None`` while unmeasured (before reconciliation, before the first committed vector, or after
    a restart clears it) and is never derived from cumulative generation over session time.
    """

    kind: Literal["embedding"]
    reconciled: bool
    desired_count: int = Field(ge=0)
    pending_count: int = Field(ge=0)
    completed_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    generated_count: int = Field(ge=0)
    items_per_second: float | None = Field(default=None, gt=0, allow_inf_nan=False)


class TranslationProgress(_LifecycleModel):
    """The last mirrored translation worker status, or unknown before the first read."""

    kind: Literal["translation"]
    worker: TranslationControllerStatus | None = None


class InferenceProgress(_LifecycleModel):
    """The last mirrored inference worker status, or unknown before the first read.

    ``preparation`` names the server-side preparation step (snapshot/transfer/restore) or the job
    phase while the remote worker has not yet reported running. It is ``None`` once real running work
    is observed, so no stale or synthetic pace is shown before current measured work.
    """

    kind: Literal["inference"]
    worker: InferenceControllerStatus | None = None
    preparation: Literal["snapshot", "transfer", "restore", "job"] | None = None


StageProgress = Annotated[
    IngestionProgress | EmbeddingProgress | TranslationProgress | InferenceProgress,
    Field(discriminator="kind"),
]


class WorkerResources(_LifecycleModel):
    """Local ownership evidence of the remote worker resources one session created.

    It records only what this controller created or started itself, so release never guesses from
    machine-wide state and never touches a resource that predated the session. Each bit is
    monotonic, so an ordinary retry never re-starts or re-uploads anything.
    """

    keepalive_pid: int | None = Field(default=None, gt=0)
    keepalive_boot_id: UUID | None = None
    worker_database_started: bool = False
    worker_database_start_attempted: bool = False
    remote_session_created: bool = False
    worker_prepared: bool = False

    @model_validator(mode="after")
    def validate_prepared_consistency(self) -> WorkerResources:
        if self.worker_prepared and not self.remote_session_created:
            raise ValueError("a prepared worker requires a created remote session")
        return self


class LifecycleSession(_LifecycleModel):
    """The ONE immutable execution receipt binding a session to its work identity and options."""

    schema_version: Literal[1] = 1
    session_id: DatasetId
    stage: StageName
    revision: DatasetRevision
    identity_sha256: str
    options: StageOptions
    created_at: datetime

    @field_validator("identity_sha256")
    @classmethod
    def validate_identity(cls, value: str) -> str:
        return require_sha256(value, "identity_sha256")

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, value: datetime) -> datetime:
        return require_aware(value, "created_at")


class LifecycleState(_LifecycleModel):
    """The ONE mutable current state: control intent, owned process, resources and progress."""

    schema_version: Literal[1] = 1
    session_id: DatasetId
    lifecycle: Literal["idle", "starting", "running", "paused", "stopped", "completed", "failed"]
    requested_action: Literal["run", "pause", "stop"]
    process: mechanics.OwnedProcessRecord | None = None
    progress: StageProgress
    work_complete: bool
    owned_services: tuple[Literal["embedding"], ...] = ()
    worker: WorkerResources | None = None
    active_seconds: float
    running_since: datetime | None = None
    error_type: str | None = None
    failure: LifecycleFailure | None = None
    stop_failure: LifecycleFailure | None = None

    @field_validator("running_since")
    @classmethod
    def validate_running_since(cls, value: datetime | None) -> datetime | None:
        return None if value is None else require_aware(value, "running_since")

    @field_validator("active_seconds")
    @classmethod
    def validate_active_seconds(cls, value: float) -> float:
        return require_finite_nonnegative(value, "active_seconds")

    @field_validator("error_type")
    @classmethod
    def validate_error_type(cls, value: str | None) -> str | None:
        return None if value is None else require_error_type(value, max_length=64)


class LifecycleStatus(_LifecycleModel):
    """Text-free operator status. Idle carries retained progress but no session identity."""

    stage: StageName
    lifecycle: Literal[
        "idle",
        "starting",
        "running",
        "paused",
        "interrupted",
        "stopped",
        "completed",
        "failed",
    ]
    session_id: str | None = None
    revision: str | None = None
    options: StageOptions | None = None
    progress: StageProgress | None = None
    active_seconds: float
    error_type: str | None = None
    failure: LifecycleFailure | None = None
    stop_failure: LifecycleFailure | None = None
    items_per_second: float | None = None
    eta_seconds: float | None = None

    @field_validator("active_seconds")
    @classmethod
    def validate_active_seconds(cls, value: float) -> float:
        return require_finite_nonnegative(value, "active_seconds")

    @field_validator("error_type")
    @classmethod
    def validate_error_type(cls, value: str | None) -> str | None:
        return None if value is None else require_error_type(value, max_length=64)


class Stage(Protocol):
    """One stage's product-owned decisions behind the shared lifecycle algorithm.

    ``server_worker_module`` names the server-side lifecycle worker module this stage's detached
    child is launched as, so a caller that owns an additional explicit route supplies the same
    lifecycle entry with its own module.
    """

    name: StageName
    services: tuple[str, ...]
    temporary_services: tuple[str, ...]
    retains_after_stop: bool
    server_worker_module: str

    def select_options(self) -> StageOptions: ...

    def identity_sha256(self, options: StageOptions) -> str: ...

    def initial_progress(self, options: StageOptions) -> StageProgress: ...

    def require_prepared(self) -> None: ...

    def require_database(self) -> None: ...

    def run(self, context: LifecycleContext) -> bool: ...

    def release(self, context: LifecycleContext) -> None: ...

    def finalize(self, context: LifecycleContext) -> None: ...


def stage_state_root(stage: StageName, *, base: Path | None = None) -> Path:
    """Return the configured stage root's ``current`` directory, the one supported layout."""
    root = repository_root() if base is None else base
    if stage == "ingestion":
        configured = load_local_lifecycle_settings().ingestion_state_root
    elif stage == "embedding":
        configured = load_local_lifecycle_settings().embedding_state_root
    elif stage == "translation":
        configured = load_translation_controller_settings().translation_controller_state_root
    else:
        configured = load_inference_controller_settings().inference_controller_state_root
    return root / configured / "current"


def _state_path(root: Path) -> Path:
    return root / "state.json"


def read_lifecycle_state(root: Path) -> LifecycleState | None:
    """Strictly read the one current state. An absent state is a fresh root, not completeness."""
    path = _state_path(root)
    if not path.exists() and not path.is_symlink():
        return None
    return load_private_model(path, LifecycleState)


def write_lifecycle_state(root: Path, state: LifecycleState) -> None:
    """Atomically publish the one mutable current state at mode 0600.

    It is a publication primitive: callers hold the short per-stage
    lock and preserve live intent themselves.
    """
    atomic_write_private_text(_state_path(root), administrative_json(state))


def _read_session(root: Path, session_id: str) -> LifecycleSession:
    directory = session_directory(root, session_id)
    if not directory.is_dir():
        raise ValueError("lifecycle session directory is absent")
    return load_private_model(directory / "session.json", LifecycleSession)


def _self_process_record() -> mechanics.OwnedProcessRecord:
    """Record the invoking command process as the preparation owner of one start."""
    argv = mechanics.read_process_command_line(os.getpid())
    if argv is None or not argv:
        raise ValueError("current command process has no readable command line")
    return mechanics.OwnedProcessRecord(
        schema_version=1, pid=os.getpid(), argv=argv, boot_id=mechanics.current_boot_id()
    )


def _process_live(state: LifecycleState) -> bool:
    if state.process is None:
        return False
    return mechanics.owned_process_is_alive(state.process)


def _project_lifecycle(state: LifecycleState, live: bool) -> str:
    if state.lifecycle in {"starting", "running"} and not live:
        return "interrupted"
    return state.lifecycle


def _fresh_idle_status(stage: Stage) -> LifecycleStatus:
    return LifecycleStatus(stage=stage.name, lifecycle="idle", active_seconds=0.0)


def _rate_eta(
    progress: StageProgress, active_seconds: float, lifecycle: str
) -> tuple[float | None, float | None]:
    if isinstance(progress, IngestionProgress):
        measured = (
            progress.verified_response_count
            if progress.stage == "verification"
            else progress.response_count
        )
        rate = measured / active_seconds if measured > 0 and active_seconds > 0 else None
        if lifecycle == "completed":
            return rate, 0.0
        if progress.stage != "verification" or progress.verification_total is None or rate is None:
            return rate, None
        remaining = max(progress.verification_total - progress.verified_response_count, 0)
        return rate, remaining / rate
    if isinstance(progress, EmbeddingProgress):
        rate = progress.items_per_second
        if lifecycle == "completed":
            return rate, 0.0
        if rate is None:
            return rate, None
        return rate, (progress.pending_count + progress.failed_count) / rate
    if isinstance(progress, InferenceProgress):
        worker = progress.worker
        if (
            lifecycle != "running"
            or worker is None
            or worker.lifecycle != "running"
            or progress.preparation is not None
        ):
            return None, None
        return worker.items_per_second, worker.projected_remaining_seconds
    if progress.worker is None:
        return None, None
    return progress.worker.items_per_second, progress.worker.projected_remaining_seconds


def _status_from_state(
    stage: Stage, state: LifecycleState, session: LifecycleSession, *, clock: Callable[[], datetime]
) -> LifecycleStatus:
    live = _process_live(state)
    lifecycle = _project_lifecycle(state, live)
    if isinstance(state.progress, InferenceProgress):
        worker = state.progress.worker
        active = (
            0.0
            if worker is None or state.progress.preparation is not None
            else worker.active_seconds
        )
    else:
        active = mechanics.active_seconds(
            state.active_seconds, state.running_since, running=lifecycle == "running", now=clock()
        )
    rate, eta = _rate_eta(state.progress, active, lifecycle)
    if lifecycle == "idle":
        session_id = None
        revision = None
        options = None
    else:
        session_id = session.session_id
        revision = session.revision
        options = session.options
    return LifecycleStatus(
        stage=stage.name,
        lifecycle=lifecycle,  # type: ignore[arg-type]
        session_id=session_id,
        revision=revision,
        options=options,
        progress=state.progress,
        active_seconds=active,
        error_type=state.error_type,
        failure=state.failure,
        stop_failure=state.stop_failure,
        items_per_second=rate,
        eta_seconds=eta,
    )


def read_lifecycle_status(
    stage: Stage, root: Path, *, clock: Callable[[], datetime] = utc_now
) -> LifecycleStatus:
    """Read state, its sole named receipt and exact-owned-process liveness. Write nothing."""
    state = read_lifecycle_state(root)
    if state is None:
        return _fresh_idle_status(stage)
    session = _read_session(root, state.session_id)
    return _status_from_state(stage, state, session, clock=clock)


class LifecycleContext:
    """The worker-side handle a stage uses to read state, admit work and checkpoint progress."""

    def __init__(
        self,
        root: Path,
        session: LifecycleSession,
        *,
        runner: mechanics.ProcessRunner,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self.root = root
        self.session = session
        self.runner = runner
        self.clock = clock
        self.failure_step: FailureStep | None = None

    def read_state(self) -> LifecycleState:
        state = read_lifecycle_state(self.root)
        if state is None or state.session_id != self.session.session_id:
            raise ValueError("lifecycle state does not name the current session")
        return state

    def admit(self) -> bool:
        """Read-only live run-intent read. Pause and stop refuse the next retry or unit."""
        state = read_lifecycle_state(self.root)
        return state is not None and state.requested_action == "run"

    def checkpoint(self, progress: StageProgress) -> None:
        """Replace progress/running time and, for inference, the mirrored worker lifecycle."""
        with mechanics.exclusive_action_lock(
            self.root, controller_name=self.session.stage, blocking=True
        ):
            state = self.read_state()
            now = self.clock()
            active = mechanics.active_seconds(
                state.active_seconds,
                state.running_since,
                running=state.lifecycle == "running",
                now=now,
            )
            update: dict[str, object] = {
                "progress": progress,
                "active_seconds": active,
                "running_since": now if state.lifecycle == "running" else None,
            }
            if isinstance(progress, InferenceProgress) and state.lifecycle in {
                "starting",
                "running",
            }:
                worker = progress.worker
                if worker is not None and worker.lifecycle == "running":
                    update["lifecycle"] = "running"
                    update["running_since"] = now
                else:
                    update["lifecycle"] = "starting"
                    update["running_since"] = None
            write_lifecycle_state(self.root, state.model_copy(update=update))

    def record_worker(self, resources: WorkerResources) -> None:
        """Replace only the worker ownership record under the short lock, preserving intent."""
        with mechanics.exclusive_action_lock(
            self.root, controller_name=self.session.stage, blocking=True
        ):
            state = self.read_state()
            write_lifecycle_state(self.root, state.model_copy(update={"worker": resources}))


def _publish_starting(
    root: Path,
    state: LifecycleState,
    *,
    expected_state: LifecycleState | None,
    fresh_session: LifecycleSession | None = None,
) -> None:
    """Reserve the one current writer under the short lock, then publish ``starting``.

    The lock is the blocking per-stage flock. The current state is read once and must
    equal ``expected_state`` exactly. ``None`` means the current state must be absent, never a
    skipped expectation. A different snapshot refuses once, before any receipt/state publication
    or preparation, without retry, merge, intent override or follow-up recovery. A fresh session's
    confined directory and immutable receipt are created inside this same critical section.
    """
    with mechanics.exclusive_action_lock(root, controller_name=state.progress.kind, blocking=True):
        current = read_lifecycle_state(root)
        if current != expected_state:
            raise RuntimeError("lifecycle start reservation changed")
        if fresh_session is not None:
            directory = session_directory(root, fresh_session.session_id)
            directory.mkdir(mode=0o700, parents=False, exist_ok=False)
            atomic_write_private_text(
                directory / "session.json", administrative_json(fresh_session)
            )
        update: dict[str, object] = {
            "lifecycle": "starting",
            "requested_action": "run",
            "process": _self_process_record(),
            "running_since": None,
            "error_type": None,
            "failure": None,
        }
        if isinstance(state.progress, InferenceProgress):
            # Drop a preceding session's rate so it is never shown as this preparation's pace.
            update["progress"] = InferenceProgress(kind="inference")
        elif isinstance(state.progress, EmbeddingProgress):
            # Clear the preceding invocation's measured pace.
            update["progress"] = state.progress.model_copy(update={"items_per_second": None})
        write_lifecycle_state(root, state.model_copy(update=update))


def _publish_failed(
    stage: Stage, root: Path, error_type: str, clock: Callable[[], datetime]
) -> None:
    with mechanics.exclusive_action_lock(root, controller_name=stage.name, blocking=True):
        current = read_lifecycle_state(root)
        if current is None:
            return
        now = clock()
        active = mechanics.active_seconds(
            current.active_seconds,
            current.running_since,
            running=current.lifecycle == "running",
            now=now,
        )
        write_lifecycle_state(
            root,
            current.model_copy(
                update={
                    "lifecycle": "failed",
                    "process": None,
                    "running_since": None,
                    "active_seconds": active,
                    "error_type": error_type,
                }
            ),
        )


def _publish_stop_failed(stage: Stage, root: Path, failure: LifecycleFailure) -> None:
    """Record one content-free stop failure while preserving the recorded outcome and ownership."""
    with mechanics.exclusive_action_lock(root, controller_name=stage.name, blocking=True):
        current = read_lifecycle_state(root)
        if current is None:
            return
        write_lifecycle_state(root, current.model_copy(update={"stop_failure": failure}))


def _prepare(
    stage: Stage, root: Path, runner: mechanics.ProcessRunner, settings: LocalLifecycleSettings
) -> None:
    """Start only already-installed prepared services and record session-temporary ownership."""
    stage.require_prepared()

    def on_starting(requested_absent: set[str]) -> None:
        temporary = tuple(sorted(set(requested_absent) & set(stage.temporary_services)))
        if not temporary:
            return
        with mechanics.exclusive_action_lock(root, controller_name=stage.name, blocking=True):
            current = read_lifecycle_state(root)
            if current is None:
                return
            merged = tuple(sorted(set(current.owned_services) | set(temporary)))
            write_lifecycle_state(root, current.model_copy(update={"owned_services": merged}))

    mechanics.ensure_prepared_services(
        lambda argv: (
            runner.run(argv, cwd=repository_root(), timeout=settings.stop_timeout_seconds).stdout
        ),
        stage.services,
        on_starting=on_starting,
    )
    stage.require_database()


def require_retained_ingestion_manifest(path_text: str, expected_sha256: str | None) -> None:
    """Require the retained ingestion manifest to be a regular non-symlink file with exact bytes.

    This is the one continuation check that compares the retained manifest bytes with the recorded
    identity before a resumed lifecycle action.
    """
    path = Path(path_text)
    if not path.is_file() or path.is_symlink():
        raise ValueError("retained ingestion manifest is missing or not a regular file")
    if expected_sha256 is not None and sha256_file(path) != expected_sha256:
        raise ValueError("retained ingestion manifest bytes do not match recorded evidence")


def _require_compatible(stage: Stage, session: LifecycleSession, state: LifecycleState) -> None:
    """One coarse compatibility pair: the receipt identity and the retained ingestion hash."""
    if session.identity_sha256 != stage.identity_sha256(session.options):
        raise ValueError("retained lifecycle work configuration does not match this device")
    progress = state.progress
    if isinstance(progress, IngestionProgress) and progress.manifest_path is not None:
        require_retained_ingestion_manifest(progress.manifest_path, progress.manifest_sha256)


def _await_process_exit(
    stage: Stage,
    root: Path,
    settings: LocalLifecycleSettings,
    *,
    sleep: Callable[[float], None],
    clock: Callable[[], datetime],
) -> LifecycleState:
    """Wait boundedly for the owned process to actually exit. In-flight work is never signalled."""
    interval = settings.poll_interval_seconds
    attempts = max(1, int(settings.stop_timeout_seconds / interval) + 1)
    deadline = clock().timestamp() + settings.stop_timeout_seconds
    return mechanics.await_state(
        lambda: read_lifecycle_state(root),
        lambda state: state is not None and not _process_live(state),
        attempts=attempts,
        interval=interval,
        sleep=sleep,
        expired=lambda: clock().timestamp() >= deadline,
    )


def _launch_acknowledged(stage: Stage, state: LifecycleState | None) -> bool:
    """Return whether one launched session may acknowledge startup without waiting for full prep.

    A running live process, or any terminal/unloaded state, always acknowledges. Inference also
    acknowledges an acknowledged live detached process that is ``starting`` once its exact live child
    has published a nonnull preparation marker, so a bare start returns within configured bounds
    without waiting for the whole transfer/prepare window.
    """
    if state is None:
        return False
    if state.lifecycle in {"paused", "stopped", "completed", "failed", "idle"}:
        return True
    if state.lifecycle == "running" and _process_live(state):
        return True
    return (
        stage.name == "inference"
        and state.lifecycle == "starting"
        and _process_live(state)
        and isinstance(state.progress, InferenceProgress)
        and state.progress.preparation is not None
    )


def _launch_and_wait(
    stage: Stage,
    root: Path,
    session: LifecycleSession,
    runner: mechanics.ProcessRunner,
    settings: LocalLifecycleSettings,
    *,
    sleep: Callable[[float], None],
) -> None:
    directory = session_directory(root, session.session_id)
    argv = (
        sys.executable,
        "-m",
        stage.server_worker_module,
        stage.name,
        session.session_id,
    )
    with mechanics.exclusive_action_lock(root, controller_name=stage.name, blocking=True):
        current = read_lifecycle_state(root)
        if current is None or current.session_id != session.session_id:
            raise ValueError("lifecycle state does not name the current session before launch")
        if current.requested_action != "run":
            target = "stopped" if current.requested_action == "stop" else "paused"
            write_lifecycle_state(root, current.model_copy(update={"lifecycle": target}))
            return
        if stage.name == "inference":
            stdout_path = Path(os.devnull)
            stderr_path = Path(os.devnull)
        else:
            stdout_path = directory / "runner.out"
            stderr_path = directory / "runner.err"
        process = runner.popen(
            argv,
            cwd=repository_root(),
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            start_new_session=True,
        )
        # The launched handle owns the exact argv. Reading /proc immediately after spawn can
        # race the kernel's fork/exec window and see an empty command line.
        child_argv = tuple(process.args)
        if not child_argv:
            raise ValueError("launched lifecycle worker has no readable command line")
        record = mechanics.OwnedProcessRecord(
            schema_version=1,
            pid=process.pid,
            argv=child_argv,
            boot_id=mechanics.current_boot_id(),
        )
        write_lifecycle_state(root, current.model_copy(update={"process": record}))
    mechanics.await_state(
        lambda: read_lifecycle_state(root),
        lambda state: _launch_acknowledged(stage, state),
        attempts=settings.startup_attempts,
        interval=settings.poll_interval_seconds,
        sleep=sleep,
    )


def _run_start(
    stage: Stage,
    root: Path,
    session: LifecycleSession,
    state: LifecycleState,
    runner: mechanics.ProcessRunner,
    settings: LocalLifecycleSettings,
    *,
    clock: Callable[[], datetime],
    sleep: Callable[[float], None],
    expected_state: LifecycleState | None,
    fresh: bool = False,
) -> LifecycleStatus:
    _publish_starting(
        root,
        state,
        expected_state=expected_state,
        fresh_session=session if fresh else None,
    )
    try:
        _prepare(stage, root, runner, settings)
    except Exception as exc:
        _publish_failed(stage, root, type(exc).__name__, clock)
        raise
    try:
        _launch_and_wait(stage, root, session, runner, settings, sleep=sleep)
    except Exception as exc:
        current = read_lifecycle_state(root)
        if current is None or not _process_live(current):
            _publish_failed(stage, root, type(exc).__name__, clock)
        raise
    return read_lifecycle_status(stage, root, clock=clock)


def _create_fresh_session(
    stage: Stage,
    root: Path,
    runner: mechanics.ProcessRunner,
    settings: LocalLifecycleSettings,
    *,
    clock: Callable[[], datetime],
    session_id_factory: Callable[[], str],
    sleep: Callable[[float], None],
    expected_state: LifecycleState | None,
) -> LifecycleStatus:
    options = stage.select_options()
    identity = stage.identity_sha256(options)
    revision = mechanics.current_revision(runner, repository_root())
    session = LifecycleSession(
        schema_version=1,
        session_id=session_id_factory(),
        stage=stage.name,
        revision=revision,
        identity_sha256=identity,
        options=options,
        created_at=clock(),
    )
    state = LifecycleState(
        schema_version=1,
        session_id=session.session_id,
        lifecycle="starting",
        requested_action="run",
        process=None,
        progress=stage.initial_progress(options),
        work_complete=False,
        owned_services=(),
        active_seconds=0.0,
        running_since=None,
        error_type=None,
    )
    return _run_start(
        stage,
        root,
        session,
        state,
        runner,
        settings,
        clock=clock,
        sleep=sleep,
        expected_state=expected_state,
        fresh=True,
    )


def _resume_retained(
    stage: Stage,
    root: Path,
    session: LifecycleSession,
    state: LifecycleState,
    runner: mechanics.ProcessRunner,
    settings: LocalLifecycleSettings,
    *,
    clock: Callable[[], datetime],
    sleep: Callable[[float], None],
) -> LifecycleStatus:
    return _run_start(
        stage,
        root,
        session,
        state,
        runner,
        settings,
        clock=clock,
        sleep=sleep,
        expected_state=state,
    )


def _start_action(
    stage: Stage,
    root: Path,
    runner: mechanics.ProcessRunner,
    settings: LocalLifecycleSettings,
    *,
    clock: Callable[[], datetime],
    session_id_factory: Callable[[], str],
    sleep: Callable[[float], None],
) -> LifecycleStatus:
    state = read_lifecycle_state(root)
    if state is None:
        return _create_fresh_session(
            stage,
            root,
            runner,
            settings,
            clock=clock,
            session_id_factory=session_id_factory,
            sleep=sleep,
            expected_state=None,
        )
    session = _read_session(root, state.session_id)
    if _process_live(state):
        return _status_from_state(stage, state, session, clock=clock)
    if state.lifecycle == "completed":
        return _status_from_state(stage, state, session, clock=clock)
    if state.lifecycle == "idle" and (state.work_complete or not stage.retains_after_stop):
        return _create_fresh_session(
            stage,
            root,
            runner,
            settings,
            clock=clock,
            session_id_factory=session_id_factory,
            sleep=sleep,
            expected_state=state,
        )
    _require_compatible(stage, session, state)
    return _resume_retained(stage, root, session, state, runner, settings, clock=clock, sleep=sleep)


def _set_intent(
    stage: Stage,
    root: Path,
    action: Literal["run", "pause", "stop"],
    *,
    preserve_stop: bool = False,
) -> None:
    with mechanics.exclusive_action_lock(root, controller_name=stage.name, blocking=True):
        current = read_lifecycle_state(root)
        if current is None:
            return
        if preserve_stop and current.requested_action == "stop":
            # A pending stop is never overwritten by a subsequent pause or checkpoint.
            return
        write_lifecycle_state(root, current.model_copy(update={"requested_action": action}))


def _release_owned_services(
    runner: mechanics.ProcessRunner, services: tuple[str, ...], *, timeout: float
) -> None:
    """Stop and remove exactly the recorded session-owned temporary Compose services."""
    for service in services:
        runner.run(
            (*mechanics.compose_prefix(), "stop", service),
            cwd=repository_root(),
            timeout=timeout,
        )
        runner.run(
            (*mechanics.compose_prefix(), "rm", "-f", service),
            cwd=repository_root(),
            timeout=timeout,
        )


def _unload_temporary_services(
    stage: Stage,
    root: Path,
    state: LifecycleState,
    runner: mechanics.ProcessRunner,
    *,
    settings: LocalLifecycleSettings,
) -> LifecycleState:
    """Release recorded session-owned services and clear both ownership handles.

    The exact recorded temporary services are stopped/removed first. Only on success are
    ``owned_services`` and the dead process record cleared under the short lock, preserving every
    other field. A release failure leaves ownership and recoverable state intact.
    """
    if state.owned_services:
        _release_owned_services(runner, state.owned_services, timeout=settings.stop_timeout_seconds)
    with mechanics.exclusive_action_lock(root, controller_name=stage.name, blocking=True):
        current = read_lifecycle_state(root)
        if current is None:
            return state
        updated = current.model_copy(update={"owned_services": (), "process": None})
        write_lifecycle_state(root, updated)
    return read_lifecycle_state(root) or state


def _pause_action(
    stage: Stage,
    root: Path,
    state: LifecycleState,
    runner: mechanics.ProcessRunner,
    settings: LocalLifecycleSettings,
    *,
    clock: Callable[[], datetime],
    sleep: Callable[[float], None],
) -> LifecycleStatus:
    session = _read_session(root, state.session_id)
    if state.lifecycle == "idle":
        return _status_from_state(stage, state, session, clock=clock)
    live = _process_live(state)
    if state.lifecycle in {"starting", "running"} and live:
        _set_intent(stage, root, "pause", preserve_stop=True)
    final = _await_process_exit(stage, root, settings, sleep=sleep, clock=clock) if live else state
    stage.release(LifecycleContext(root=root, session=session, runner=runner, clock=clock))
    final = _unload_temporary_services(stage, root, final, runner, settings=settings)
    return _status_from_state(stage, final, session, clock=clock)


def _stop_action(
    stage: Stage,
    root: Path,
    state: LifecycleState,
    runner: mechanics.ProcessRunner,
    settings: LocalLifecycleSettings,
    *,
    clock: Callable[[], datetime],
    sleep: Callable[[float], None],
) -> LifecycleStatus:
    # An idle-only projection creates nothing and cannot record a stop execution failure. It runs
    # outside the catch, so only a real stop path records a stop failure.
    if state.lifecycle == "idle":
        session = _read_session(root, state.session_id)
        return _status_from_state(stage, state, session, clock=clock)
    failure_step: FailureStep = "session"
    context: LifecycleContext | None = None
    try:
        session = _read_session(root, state.session_id)
        failure_step = "intent"
        if state.lifecycle in {"starting", "running"} and _process_live(state):
            _set_intent(stage, root, "stop")
        failure_step = "await_exit"
        final = _await_process_exit(stage, root, settings, sleep=sleep, clock=clock)
        failure_step = "finalize"
        context = LifecycleContext(root=root, session=session, runner=runner, clock=clock)
        stage.finalize(context)
        # A finer breadcrumb supplied by finalize applies only while it executes. After it returns,
        # a subsequent services/local-cleanup/idle failure records its own executing step.
        context.failure_step = None
        failure_step = "services"
        _release_owned_services(runner, final.owned_services, timeout=settings.stop_timeout_seconds)
        failure_step = "local_cleanup"
        directory = session_directory(root, session.session_id)
        (directory / "runner.out").unlink(missing_ok=True)
        (directory / "runner.err").unlink(missing_ok=True)
        failure_step = "idle"
        work_complete = final.lifecycle == "completed"
        with mechanics.exclusive_action_lock(root, controller_name=stage.name, blocking=True):
            current = read_lifecycle_state(root)
            if current is None:
                raise ValueError("lifecycle state vanished during stop")
            updated = current.model_copy(
                update={
                    "lifecycle": "idle",
                    "requested_action": "run",
                    "process": None,
                    "owned_services": (),
                    "work_complete": work_complete,
                    "running_since": None,
                    "error_type": None,
                    "failure": None,
                    "stop_failure": None,
                }
            )
            write_lifecycle_state(root, updated)
    except Exception as exc:
        step = (context.failure_step or failure_step) if context is not None else failure_step
        _publish_stop_failed(stage, root, lifecycle_failure(step, exc))
        raise
    return _status_from_state(stage, updated, session, clock=clock)


def _validate_action(action: ControllerAction) -> None:
    if action not in _ACTIONS:
        raise ValueError("action must be start, pause, resume, status, or stop")


def run_lifecycle_command(
    action: ControllerAction,
    *,
    stage: Stage,
    root: Path,
    runner: mechanics.ProcessRunner | None = None,
    clock: Callable[[], datetime] = utc_now,
    session_id_factory: Callable[[], str] = lambda: uuid.uuid4().hex,
    sleep: Callable[[float], None] = time.sleep,
) -> LifecycleStatus:
    """Run exactly one local lifecycle action and return its status without waiting on work."""
    _validate_action(action)
    process_runner = runner if runner is not None else mechanics.SubprocessRunner()

    if action == "status":
        require_selected_dataset_root(root)
        return read_lifecycle_status(stage, root, clock=clock)

    require_selected_dataset_root(root)
    settings = load_local_lifecycle_settings()

    if action == "start":
        return _start_action(
            stage,
            root,
            process_runner,
            settings,
            clock=clock,
            session_id_factory=session_id_factory,
            sleep=sleep,
        )

    state = read_lifecycle_state(root)
    if state is None:
        if action == "resume":
            raise ValueError("no retained lifecycle session to resume")
        return _fresh_idle_status(stage)
    if action == "pause":
        return _pause_action(stage, root, state, process_runner, settings, clock=clock, sleep=sleep)
    if action == "resume":
        session = _read_session(root, state.session_id)
        if _process_live(state):
            return _status_from_state(stage, state, session, clock=clock)
        if state.lifecycle == "completed":
            return _status_from_state(stage, state, session, clock=clock)
        if state.lifecycle == "idle":
            if state.work_complete:
                return _status_from_state(stage, state, session, clock=clock)
            if not stage.retains_after_stop:
                # A non-retaining stage finalizes and returns at stop, so an idle state has no
                # resumable worker session left. Resume is refused like an absent state.
                raise ValueError("no retained lifecycle session to resume")
        _require_compatible(stage, session, state)
        return _resume_retained(
            stage, root, session, state, process_runner, settings, clock=clock, sleep=sleep
        )
    return _stop_action(stage, root, state, process_runner, settings, clock=clock, sleep=sleep)
