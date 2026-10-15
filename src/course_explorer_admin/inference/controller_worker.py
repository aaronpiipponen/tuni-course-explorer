"""Inference stage body for the one shared worker lifecycle shell.

Every function here executes on the worker host (invoked through
``python -m course_explorer_admin.inference.controller_worker``) and owns the inference stage's
bodies: the prepared-session acknowledgement, the incremental job run, the one-time cohort
publication, its status projection and its cleanup artifacts. The shared lifecycle shell, process
observation and CLI live in ``course_explorer_admin.worker_session``. Detached ``run`` delegates once
to the incremental ``run_inference_job`` over the real ``WorkerInferenceRuntime``, and finalize
publishes the retained cohort through the product publisher.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path

from course_explorer.administration import (
    administrative_json,
    atomic_write_private_text,
    utc_now,
)
from course_explorer.config import (
    InferenceControllerSettings,
    load_inference_controller_settings,
    load_inference_rerank_settings,
    load_inference_selection_settings,
    load_inference_settings,
    load_raw_database_settings,
    load_worker_gpu_reboot_settings,
)
from course_explorer.db.session import create_database_engine, create_session_factory
from course_explorer.inference.failures import InferenceTargetsFailed
from course_explorer.inference.job import InferenceJobProgress, run_inference_job
from course_explorer.inference.publication import publish_current_cohort
from course_explorer.inference.routing import OversizeRouteFactory
from course_explorer.inference.scheduling_repository import InferenceSchedulingRepository
from course_explorer_admin import mechanics, worker_session
from course_explorer_admin.inference.controller import (
    InferenceControllerPolicy,
    InferenceControllerStatus,
    InferenceControllerWorkerState,
    inference_configuration_sha256,
    load_inference_controller_status,
    load_inference_controller_worker_state,
    load_inference_dataset_session,
)
from course_explorer_admin.reboot import WorkerGpuClock, worker_gpu_reboot_due
from course_explorer_admin.remote import WorkerControl, WorkerDatasetSession
from course_explorer_admin.runtime import WorkerInferenceRuntime
from course_explorer_admin.worker_session import (
    read_control,
    write_worker_control,
    write_worker_state,
)

_CLEANUP_ARTIFACTS = (
    "input.dump",
    "return.dump",
    "runner.json",
    "runtime.json",
    "runtime.log",
    "runner.log",
)


def _read_import_receipt(
    session: WorkerDatasetSession,
    state: InferenceControllerWorkerState,
    directory: Path,
) -> InferenceControllerStatus | None:
    """Strictly load one session's import status, or ``None`` when genuinely absent.

    Only a genuinely absent file returns ``None``. A symlinked, nonregular, malformed, foreign, or
    inconsistent receipt fails loudly. The receipt must describe this session and revision, report
    the imported lifecycle, be unbounded, require a terminal worker state, and carry known counts
    and real coverage whose published targets equal its retained complete targets (an explicit
    operator DONE target contributes retained coverage once its inference-owned output is withdrawn).
    """
    path = directory / "import-receipt.json"
    if path.is_symlink():
        raise ValueError("import receipt must not be a symlink")
    if not path.exists():
        return None
    receipt = load_inference_controller_status(path)
    if receipt.session_id != session.session_id or receipt.revision != session.revision:
        raise ValueError("import receipt identity does not match the session")
    if receipt.lifecycle != "imported":
        raise ValueError("import receipt must report the imported lifecycle")
    if receipt.course_limit is not None:
        raise ValueError("import receipt must not be bounded")
    if state.lifecycle not in {"stopped", "completed", "failed", "cleaned"}:
        raise ValueError("import receipt requires a terminal worker state")
    if receipt.desired_count is None or receipt.completed_count is None:
        raise ValueError("import receipt requires known counts")
    if receipt.coverage is None:
        raise ValueError("import receipt requires real coverage")
    if receipt.coverage.published_targets != receipt.coverage.retained_complete_targets:
        raise ValueError("import receipt coverage is not fully published")
    if receipt.desired_count != receipt.coverage.eligible_targets:
        raise ValueError("import receipt desired count does not match its coverage")
    if receipt.completed_count != receipt.coverage.retained_complete_targets:
        raise ValueError("import receipt completed count does not match its coverage")
    return receipt


def _status_from_state(
    session: WorkerDatasetSession,
    state: InferenceControllerWorkerState,
    *,
    directory: Path,
    clock: Callable[[], datetime],
    lifecycle: str | None = None,
) -> InferenceControllerStatus:
    receipt = _read_import_receipt(session, state, directory)
    projected = state.lifecycle if lifecycle is None else lifecycle
    if receipt is not None:
        if state.lifecycle == "cleaned":
            return receipt.model_copy(update={"lifecycle": "cleaned"})
        return receipt
    reboot_due = False
    if projected == "paused":
        reboot_due = worker_gpu_reboot_due(
            directory,
            session_id=session.session_id,
            revision=session.revision,
            settings=load_worker_gpu_reboot_settings(),
        )
    return InferenceControllerStatus.model_validate(
        {
            **state.model_dump(
                mode="python",
                exclude={"schema_version", "runner_pid", "runtime_pid", "reboot_due"},
            ),
            "lifecycle": projected,
            "reboot_due": reboot_due,
        }
    )


def _publish_prepared_session(
    session: WorkerDatasetSession, directory: Path
) -> InferenceControllerStatus:
    """Publish run control and prepared unknown progress without any selection or model work."""
    control_path = directory / "control.json"
    state_path = directory / "state.json"
    if control_path.exists() or state_path.exists():
        raise ValueError("prepared control and state files must not already exist")
    write_worker_control(
        directory,
        WorkerControl(
            schema_version=1,
            session_id=session.session_id,
            revision=session.revision,
            requested_action="run",
        ),
    )
    state = InferenceControllerWorkerState(
        schema_version=2,
        session_id=session.session_id,
        revision=session.revision,
        lifecycle="prepared",
        desired_count=None,
        completed_count=None,
        active_seconds=0.0,
        progress=None,
        coverage=None,
        stage_processed_count=0,
    )
    write_worker_state(directory, state)
    return _status_from_state(
        session, state, directory=directory, clock=utc_now, lifecycle="prepared"
    )


def _session_database_settings(session: WorkerDatasetSession):
    return load_raw_database_settings().model_copy(update={"postgres_db": session.database_name})


def _stop_runtime(runtime: WorkerInferenceRuntime, settings: InferenceControllerSettings) -> bool:
    """Stop the shared runtime and report whether unload was proved."""
    try:
        runtime.stop()
    except Exception:
        return False
    return True


def _finalize(
    session: WorkerDatasetSession,
    state: InferenceControllerWorkerState,
    directory: Path,
) -> None:
    """Publish one canonical terminal session's retained cohort exactly once.

    The retained cohort includes explicit operator DONE targets, which are absent from selected
    publication and contribute complete coverage with no inferred output. The publisher withdraws
    their stale predecessor output, so published coverage equals retained coverage.
    """
    engine = create_database_engine(_session_database_settings(session))
    try:
        factory = create_session_factory(engine)
        repository = InferenceSchedulingRepository(factory)
        cohort = repository.read_publication_cohort()
        publish_current_cohort(
            factory,
            cohort,
            load_inference_settings(),
            load_inference_selection_settings(),
        )
        repository.prune_retained_state()
        coverage = repository.read_coverage()
        if coverage.published_targets != coverage.retained_complete_targets:
            raise ValueError("published targets do not match retained complete targets")
        receipt = InferenceControllerStatus(
            session_id=session.session_id,
            revision=session.revision,
            lifecycle="imported",
            course_limit=None,
            desired_count=coverage.eligible_targets,
            completed_count=coverage.retained_complete_targets,
            active_seconds=0.0,
            progress=state.progress,
            coverage=coverage,
            stage_processed_count=0,
        )
        atomic_write_private_text(directory / "import-receipt.json", administrative_json(receipt))
    finally:
        engine.dispose()


class InferenceWorkerStage:
    """Inference stage body implementing the shared worker shell's stage seam.

    ``oversize_route`` is the caller's explicit alternative route for a packet fitting neither local
    key. It is retained transiently and forwarded to the one job entry, while the default is the
    local-only capacity failure. Finalize, status, control and reboot own no route.
    """

    name = "inference"
    controller_name = "inference worker"
    cleanup_artifacts = _CLEANUP_ARTIFACTS

    def __init__(self, *, oversize_route: OversizeRouteFactory | None = None) -> None:
        self._oversize_route = oversize_route

    def connection(self):
        return load_inference_controller_settings()

    def load_session(
        self, session_id: str
    ) -> tuple[WorkerDatasetSession, InferenceControllerPolicy, Path]:
        return load_inference_dataset_session(session_id)

    def load_state(self, path: Path) -> InferenceControllerWorkerState:
        return load_inference_controller_worker_state(path)

    def require_policy(
        self, session: WorkerDatasetSession, policy: InferenceControllerPolicy
    ) -> None:
        if policy.configuration_sha256 != inference_configuration_sha256():
            raise ValueError("canonical policy configuration does not match current settings")

    def publish_prepared(
        self, session: WorkerDatasetSession, directory: Path
    ) -> InferenceControllerStatus:
        return _publish_prepared_session(session, directory)

    def run(
        self,
        session: WorkerDatasetSession,
        directory: Path,
        state: InferenceControllerWorkerState,
        *,
        runner: mechanics.ProcessRunner,
        sleep: Callable[[float], None],
        clock: Callable[[], datetime],
        monotonic: Callable[[], float],
    ) -> int:
        """Run one prepared or retained inference session under the already-held instance lock."""
        settings = self.connection()
        tracker: dict[str, object] = {
            "desired_count": state.desired_count,
            "completed_count": state.completed_count,
            "active_seconds": 0.0,
            "progress": state.progress,
            "coverage": state.coverage,
            "stage_processed_count": 0,
        }

        def write(lifecycle: str, *, error_type: str | None = None) -> None:
            unloaded = lifecycle in {
                "prepared",
                "paused",
                "stopped",
                "completed",
                "failed",
                "cleaned",
            }
            write_worker_state(
                directory,
                InferenceControllerWorkerState(
                    schema_version=2,
                    session_id=session.session_id,
                    revision=session.revision,
                    lifecycle=lifecycle,  # type: ignore[arg-type]
                    desired_count=tracker["desired_count"],  # type: ignore[arg-type]
                    completed_count=tracker["completed_count"],  # type: ignore[arg-type]
                    active_seconds=float(tracker["active_seconds"]),  # type: ignore[arg-type]
                    runner_pid=None if unloaded else os.getpid(),
                    runtime_pid=None,
                    progress=tracker["progress"],  # type: ignore[arg-type]
                    coverage=tracker["coverage"],  # type: ignore[arg-type]
                    stage_processed_count=int(tracker["stage_processed_count"]),  # type: ignore[arg-type]
                    error_type=error_type,
                ),
            )

        def before_unit() -> bool:
            return read_control(directory, session).requested_action == "run" and not gpu_clock.due

        def before_request() -> bool:
            # Request admission requires control run and no latched due checkpoint. Due is latched
            # only by a completed unit or a committed failed-attempt callback, never by running
            # wall-clock time, so an in-flight action is not interrupted for elapsed time.
            # A due checkpoint refuses the next request until the shared reboot resumes the session.
            return read_control(directory, session).requested_action == "run" and not gpu_clock.due

        gpu_clock = WorkerGpuClock(
            directory,
            session_id=session.session_id,
            revision=session.revision,
            settings=load_worker_gpu_reboot_settings(),
            monotonic=monotonic,
        )

        engine = create_database_engine(_session_database_settings(session))
        try:
            factory = create_session_factory(engine)
            repository = InferenceSchedulingRepository(factory)
            initial_coverage = repository.read_coverage()
            runtime = WorkerInferenceRuntime(
                runner,
                root=settings.worker_project_root,
                directory=directory,
                settings=load_inference_settings(),
                rerank_settings=load_inference_rerank_settings(),
                health_attempts=settings.inference_controller_health_attempts,
                interval=settings.poll_interval_seconds,
                stop_timeout_seconds=settings.stop_timeout_seconds,
                sleep=sleep,
                gpu_clock=gpu_clock,
            )
            observed_cycle_id = initial_coverage.cycle_id
            observed_rerank = initial_coverage.rerank_completed
            observed_inference = initial_coverage.inference_completed

            def on_checkpoint(progress: InferenceJobProgress) -> None:
                nonlocal observed_cycle_id, observed_rerank, observed_inference
                tracker["desired_count"] = progress.desired_targets
                tracker["completed_count"] = progress.retained_complete_targets
                tracker["active_seconds"] = progress.active_stage_seconds
                tracker["progress"] = progress
                tracker["stage_processed_count"] = progress.measured_stage_completed
                # Sample the loaded-GPU clock only when a CE/generation completed count actually
                # increased for the observed cycle. A stage-only/skip/failure/recovered
                # notification with no loaded segment is a clock no-op and never invents GPU use.
                if observed_cycle_id != progress.cycle_id:
                    observed_rerank = 0
                    observed_inference = 0
                if (
                    progress.rerank_completed > observed_rerank
                    or progress.inference_completed > observed_inference
                ):
                    gpu_clock.checkpoint()
                observed_cycle_id = progress.cycle_id
                observed_rerank = progress.rerank_completed
                observed_inference = progress.inference_completed
                write("running")

            write("starting")
            if not before_unit():
                # A pause/stop that arrived before this invocation starts no job at all.
                requested = read_control(directory, session).requested_action
                write("stopped" if requested == "stop" else "paused")
                return 0

            try:
                cycle = run_inference_job(
                    factory,
                    runtime=runtime,
                    before_unit=before_unit,
                    before_request=before_request,
                    on_checkpoint=on_checkpoint,
                    on_generation_attempt_checkpoint=gpu_clock.checkpoint,
                    oversize_route=self._oversize_route,
                    clock=clock,
                )
            except InferenceTargetsFailed:
                # Useful targets were published. The job already unloaded in its finally. Publish the
                # unloaded failed state so an ordinary start retries the failures.
                tracker["coverage"] = repository.read_coverage()
                write("failed", error_type="InferenceTargetsFailed")
                return 1
            except Exception as exc:
                if not _stop_runtime(runtime, settings):
                    return 1
                write("failed", error_type=type(exc).__name__)
                return 1

            # Re-prove the runtime actually unloaded before publishing any terminal state.
            fresh_state = load_inference_controller_worker_state(directory / "state.json")
            if worker_session.worker_runtime_is_alive(fresh_state, directory):
                return 1
            requested = read_control(directory, session).requested_action
            if cycle.stage == "complete":
                write("completed")
            elif requested == "stop":
                write("stopped")
            elif requested == "pause":
                write("paused")
            elif gpu_clock.due:
                # A latched due checkpoint with a genuinely unfinished cycle yields an unloaded
                # paused state for the shared restart. A real complete or pending control takes
                # precedence.
                write("paused")
            else:
                raise RuntimeError("inference job returned without completing or a pending control")
            return 0
        finally:
            engine.dispose()

    def read_import_receipt(
        self,
        session: WorkerDatasetSession,
        state: InferenceControllerWorkerState,
        directory: Path,
    ) -> InferenceControllerStatus | None:
        return _read_import_receipt(session, state, directory)

    def finalize(
        self,
        session: WorkerDatasetSession,
        state: InferenceControllerWorkerState,
        directory: Path,
    ) -> None:
        _finalize(session, state, directory)

    def status(
        self,
        session: WorkerDatasetSession,
        state: InferenceControllerWorkerState,
        directory: Path,
        *,
        clock: Callable[[], datetime],
        lifecycle: str | None,
    ) -> InferenceControllerStatus:
        return _status_from_state(
            session, state, directory=directory, clock=clock, lifecycle=lifecycle
        )

    def stop_updates(
        self, state: InferenceControllerWorkerState, directory: Path
    ) -> dict[str, object]:
        return {}

    def require_cleanup_evidence(
        self,
        session: WorkerDatasetSession,
        receipt: InferenceControllerStatus,
        directory: Path,
    ) -> None:
        """Inference cleanup needs no extra retained-output proof beyond the import receipt."""
        return None


def main(argv: Sequence[str] | None = None) -> int:
    """Expose the worker subcommands through the shared shell."""
    return worker_session.worker_main(InferenceWorkerStage(), argv)


if __name__ == "__main__":
    raise SystemExit(main())
