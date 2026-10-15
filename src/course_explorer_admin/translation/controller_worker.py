"""Translation stage body for the one shared worker lifecycle shell.

Every function here executes on the worker host (invoked through
``python -m course_explorer_admin.translation.controller_worker``) and owns only the translation
stage's genuinely different bodies: the prepared-session selection, the translation run, the
finalize, its status projection and its cleanup evidence. The shared lifecycle shell,
process observation and CLI live once in ``course_explorer_admin.worker_session``. Detached ``run``
delegates exactly once to ``run_translation_command``.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path

from course_explorer.administration import (
    administrative_json,
    atomic_write_private_text,
    sha256_file,
    utc_now,
)
from course_explorer.config import (
    TranslationControllerSettings,
    load_raw_database_settings,
    load_translation_controller_settings,
    load_translation_settings,
    load_worker_gpu_reboot_settings,
)
from course_explorer.curriculum_repository import CurriculumRepository
from course_explorer.db.session import create_database_engine, create_session_factory
from course_explorer.teaching_text.commands import load_translation_file
from course_explorer.teaching_text.repository import DerivedTranslationRepository
from course_explorer.translation.commands import run_translation_command
from course_explorer.translation.service import TranslationRunReport, select_translation_work
from course_explorer_admin import mechanics, worker_session
from course_explorer_admin.reboot import WorkerGpuClock, worker_gpu_reboot_due
from course_explorer_admin.remote import WorkerControl, WorkerDatasetSession
from course_explorer_admin.runtime import OwnedWorkerRuntime, translation_runtime_spec
from course_explorer_admin.translation.controller import (
    TranslationControllerImportReceipt,
    TranslationControllerOutputManifest,
    TranslationControllerPolicy,
    TranslationControllerStatus,
    TranslationControllerWorkerState,
    load_translation_controller_import_receipt,
    load_translation_controller_worker_state,
    load_translation_dataset_session,
)
from course_explorer_admin.worker_session import (
    read_control,
    write_worker_control,
    write_worker_state,
)

_CLEANUP_ARTIFACTS = (
    "input.dump",
    "return.dump",
    "output.json",
    "output.json.failure.json",
    "output-manifest.json",
    "run-report.json",
    "runner.json",
    "runtime.json",
    "runtime.log",
    "runner.log",
)


def _retained_output_count(directory: Path) -> int:
    """Return the strict count of one session's retained atomic output file.

    This is the single owner of retained-output presence and counting: an absent
    ``output.json`` is zero, a symlink or any other non-regular file fails loudly and
    preserves evidence, and a regular file is counted only through the strict output loader.
    """
    output_path = directory / "output.json"
    if output_path.is_symlink():
        raise ValueError("retained output must not be a symlink")
    if not output_path.exists():
        return 0
    if not output_path.is_file():
        raise ValueError("retained output must be a regular file")
    return len(load_translation_file(output_path))


def _read_import_receipt(
    session: WorkerDatasetSession,
    state: TranslationControllerWorkerState,
    directory: Path,
) -> TranslationControllerImportReceipt | None:
    """Strictly load one canonical session's import receipt, or ``None`` when genuinely absent.

    Only a genuinely absent file returns ``None``. A symlinked, nonregular, malformed, foreign, or
    inconsistent receipt fails loudly. The receipt must describe this session and revision, agree
    with the worker state's completed count, carry a hash exactly when its count is positive, and
    report a requested count equal to its output count. The receipt file is its only input.
    """
    path = directory / "import-receipt.json"
    if path.is_symlink():
        raise ValueError("import receipt must not be a symlink")
    if not path.exists():
        return None
    receipt = load_translation_controller_import_receipt(path)
    if receipt.session_id != session.session_id or receipt.revision != session.revision:
        raise ValueError("import receipt identity does not match the session")
    if receipt.output_count != state.completed_count:
        raise ValueError("import receipt output count does not match the worker state")
    if receipt.output_count > 0 and receipt.output_sha256 is None:
        raise ValueError("positive import receipt requires an output hash")
    if receipt.output_count == 0 and receipt.output_sha256 is not None:
        raise ValueError("zero import receipt requires no output hash")
    if receipt.import_report.requested_count != receipt.output_count:
        raise ValueError("import receipt report does not match its output count")
    return receipt


def _status_from_state(
    session: WorkerDatasetSession,
    state: TranslationControllerWorkerState,
    *,
    directory: Path,
    clock: Callable[[], datetime],
    lifecycle: str | None = None,
) -> TranslationControllerStatus:
    receipt = _read_import_receipt(session, state, directory)
    if receipt is not None and state.lifecycle not in {"stopped", "completed", "failed", "cleaned"}:
        raise ValueError("import receipt requires a terminal worker state")
    projected = state.lifecycle if lifecycle is None else lifecycle
    if receipt is not None and projected in {"stopped", "completed", "failed"}:
        projected = "imported"
    active_seconds = mechanics.active_seconds(
        state.active_seconds,
        state.running_since,
        running=projected == "running",
        now=clock(),
    )
    output_path = directory / "output.json"
    output_sha256 = None
    if state.completed_count > 0 and output_path.is_file() and not output_path.is_symlink():
        output_sha256 = sha256_file(output_path)
    import_report = None
    if receipt is not None:
        if output_sha256 is not None and receipt.output_count > 0:
            if output_sha256 != receipt.output_sha256:
                raise ValueError("retained output hash does not match the import receipt")
        if output_sha256 is None:
            output_sha256 = receipt.output_sha256
        import_report = receipt.import_report
    reboot_due = False
    if projected == "paused":
        reboot_due = worker_gpu_reboot_due(
            directory,
            session_id=session.session_id,
            revision=session.revision,
            settings=load_worker_gpu_reboot_settings(),
        )
    return TranslationControllerStatus(
        session_id=session.session_id,
        lifecycle=projected,  # type: ignore[arg-type]
        revision=session.revision,
        course_limit=session.course_limit,
        desired_count=state.desired_count,
        completed_count=state.completed_count,
        active_seconds=active_seconds,
        output_sha256=output_sha256,
        import_report=import_report,
        error_type=state.error_type,
        reboot_due=reboot_due,
    )


def _publish_prepared_session(
    session: WorkerDatasetSession, directory: Path
) -> TranslationControllerStatus:
    """Publish control/state ``prepared`` after one explicit session-database selection.

    This is the one publication owner: it opens an explicit engine on the session's derived
    database, runs the translation selector with the session's course limit, disposes the
    engine, and writes prepared control and state. It writes a prepared acknowledgement once and
    refuses any control/state that is present.
    """
    database_settings = load_raw_database_settings()
    session_settings = database_settings.model_copy(update={"postgres_db": session.database_name})
    engine = create_database_engine(session_settings)
    try:
        factory = create_session_factory(engine)
        selection = select_translation_work(
            CurriculumRepository(factory),
            DerivedTranslationRepository(factory),
            load_translation_settings(),
            course_limit=session.course_limit,
        )
    finally:
        engine.dispose()
    desired_count = len(selection.items)

    control_path = directory / "control.json"
    state_path = directory / "state.json"
    if control_path.exists() or state_path.exists():
        raise ValueError("prepared control and state files must not already exist")
    started_at = utc_now()
    write_worker_control(
        directory,
        WorkerControl(
            schema_version=1,
            session_id=session.session_id,
            revision=session.revision,
            requested_action="run",
        ),
    )
    state = TranslationControllerWorkerState(
        schema_version=2,
        session_id=session.session_id,
        revision=session.revision,
        lifecycle="prepared",
        desired_count=desired_count,
        completed_count=0,
        started_at=started_at,
        active_seconds=0.0,
    )
    write_worker_state(directory, state)
    return _status_from_state(
        session, state, directory=directory, clock=utc_now, lifecycle="prepared"
    )


def _stop_owned_runtime(owner: OwnedWorkerRuntime, settings: TranslationControllerSettings) -> bool:
    """Stop the shared owned runtime and report whether shutdown was proved.

    A failed shutdown is never swallowed into a terminal state: the caller returns nonzero and
    leaves the recorded state and the runtime record intact for interrupted recovery.
    """
    try:
        owner.stop(
            timeout=settings.stop_timeout_seconds,
            interval=settings.poll_interval_seconds,
        )
    except Exception:
        return False
    return True


def _stop_updates(state: TranslationControllerWorkerState, directory: Path) -> dict[str, object]:
    """Reconcile the retained output count into the stopped state, or refuse inconsistency."""
    retained_count = _retained_output_count(directory)
    if state.lifecycle == "prepared":
        if retained_count != 0:
            raise ValueError("prepared worker session must not retain output")
        return {"running_since": None}
    # The worker host may have died between the atomic output publication and its state count
    # write, so the retained file is the authority for completed work.
    if not state.completed_count <= retained_count <= state.desired_count:
        raise ValueError("retained output count is inconsistent with the recorded worker state")
    return {"completed_count": retained_count, "running_since": None}


def _require_cleanup_evidence(receipt: TranslationControllerImportReceipt, directory: Path) -> None:
    """Require the retained output (when present) to match the import receipt before any drop."""
    output_path = directory / "output.json"
    if receipt.output_count > 0:
        if output_path.is_symlink():
            raise ValueError("retained output must not be a symlink")
        if output_path.exists():
            if not output_path.is_file():
                raise ValueError("retained output must be a regular file")
            if sha256_file(output_path) != receipt.output_sha256:
                raise ValueError("import receipt output hash does not match the current output")
    elif output_path.exists() or output_path.is_symlink():
        raise ValueError("zero import receipt requires no output file")


def _export_worker_output_locked(
    session: WorkerDatasetSession,
    state: TranslationControllerWorkerState,
    directory: Path,
) -> TranslationControllerOutputManifest:
    """Count, hash, and publish one terminal output manifest under the held instance lock.

    This is the one output validator for finalize: a positive recorded count requires a regular
    retained output whose strict entry count matches, a zero count requires no output path at all,
    and an optional run report is strictly validated before it is hashed.
    """
    output_path = directory / "output.json"
    output_sha256 = None
    if state.completed_count > 0:
        retained_count = _retained_output_count(directory)
        if retained_count == 0:
            raise ValueError("positive completed count requires a regular output file")
        if retained_count != state.completed_count:
            raise ValueError("output entry count does not match recorded completed count")
        output_sha256 = sha256_file(output_path)
    elif output_path.exists() or output_path.is_symlink():
        raise ValueError("zero completed count requires no output file")

    run_report_path = directory / "run-report.json"
    run_report_sha256 = None
    if run_report_path.is_file() and not run_report_path.is_symlink():
        TranslationRunReport.model_validate_json(run_report_path.read_text(encoding="utf-8"))
        run_report_sha256 = sha256_file(run_report_path)

    manifest = TranslationControllerOutputManifest(
        schema_version=1,
        session_id=session.session_id,
        revision=session.revision,
        output_count=state.completed_count,
        output_sha256=output_sha256,
        run_report_sha256=run_report_sha256,
    )
    atomic_write_private_text(directory / "output-manifest.json", administrative_json(manifest))
    return manifest


def _finalize(
    session: WorkerDatasetSession,
    state: TranslationControllerWorkerState,
    directory: Path,
) -> None:
    """Import one canonical terminal session's retained output exactly once."""
    manifest = _export_worker_output_locked(session, state, directory)
    if manifest.output_count > 0:
        translations = load_translation_file(directory / "output.json")
    else:
        translations = ()
    database_settings = load_raw_database_settings()
    session_settings = database_settings.model_copy(update={"postgres_db": session.database_name})
    engine = create_database_engine(session_settings)
    try:
        factory = create_session_factory(engine)
        report = DerivedTranslationRepository(factory).upsert(translations)
    finally:
        engine.dispose()
    receipt = TranslationControllerImportReceipt(
        schema_version=1,
        session_id=session.session_id,
        revision=session.revision,
        output_count=manifest.output_count,
        output_sha256=manifest.output_sha256,
        import_report=report,
    )
    atomic_write_private_text(directory / "import-receipt.json", administrative_json(receipt))


class TranslationWorkerStage:
    """Translation stage body implementing the shared worker shell's stage seam."""

    name = "translation"
    controller_name = "translation worker"
    cleanup_artifacts = _CLEANUP_ARTIFACTS

    def connection(self):
        return load_translation_controller_settings()

    def load_session(
        self, session_id: str
    ) -> tuple[WorkerDatasetSession, TranslationControllerPolicy, Path]:
        return load_translation_dataset_session(session_id)

    def load_state(self, path: Path) -> TranslationControllerWorkerState:
        return load_translation_controller_worker_state(path)

    def require_policy(
        self, session: WorkerDatasetSession, policy: TranslationControllerPolicy
    ) -> None:
        if policy.translation_model != load_translation_settings().provenance_model:
            raise ValueError(
                "canonical policy model does not match the configured provenance model"
            )

    def publish_prepared(
        self, session: WorkerDatasetSession, directory: Path
    ) -> TranslationControllerStatus:
        return _publish_prepared_session(session, directory)

    def run(
        self,
        session: WorkerDatasetSession,
        directory: Path,
        state: TranslationControllerWorkerState,
        *,
        runner: mechanics.ProcessRunner,
        sleep: Callable[[float], None],
        clock: Callable[[], datetime],
        monotonic: Callable[[], float],
    ) -> int:
        """Run one prepared or retained translation session under the already-held instance lock."""
        settings = self.connection()
        worker_root = settings.worker_project_root
        translation_settings = load_translation_settings()
        owner = OwnedWorkerRuntime(runner, root=worker_root, directory=directory, sleep=sleep)
        gpu_clock = WorkerGpuClock(
            directory,
            session_id=session.session_id,
            revision=session.revision,
            settings=load_worker_gpu_reboot_settings(),
            monotonic=monotonic,
        )
        tracker: dict[str, object] = {
            "active_seconds": state.active_seconds,
            "completed_count": state.completed_count,
            "running_since": None,
            "runtime_pid": None,
        }

        def write(
            lifecycle: str, *, error_type: str | None = None, running_since: object = None
        ) -> None:
            unloaded = lifecycle in {"paused", "stopped", "completed", "failed", "cleaned"}
            write_worker_state(
                directory,
                TranslationControllerWorkerState(
                    schema_version=2,
                    session_id=session.session_id,
                    revision=session.revision,
                    lifecycle=lifecycle,  # type: ignore[arg-type]
                    desired_count=state.desired_count,
                    completed_count=int(tracker["completed_count"]),
                    started_at=state.started_at,
                    active_seconds=float(tracker["active_seconds"]),
                    running_since=running_since,  # type: ignore[arg-type]
                    runner_pid=None if unloaded else os.getpid(),
                    runtime_pid=None if unloaded else tracker["runtime_pid"],  # type: ignore[arg-type]
                    error_type=error_type,
                ),
            )

        def accumulate_active() -> None:
            running_since = tracker["running_since"]
            if running_since is None:
                return
            tracker["active_seconds"] = mechanics.active_seconds(
                float(tracker["active_seconds"]),
                running_since,  # type: ignore[arg-type]
                running=True,
                now=clock(),
            )
            tracker["running_since"] = None

        def begin_running() -> None:
            tracker["running_since"] = clock()
            write("running", running_since=tracker["running_since"])

        def gate() -> bool:
            # Pure live-control admission plus the latched completed-unit checkpoint: never blocks,
            # waits for resume, or mutates state.
            return read_control(directory, session).requested_action == "run" and not gpu_clock.due

        def before_request() -> bool:
            return read_control(directory, session).requested_action == "run"

        def on_checkpoint(count: int) -> None:
            tracker["completed_count"] = count
            accumulate_active()
            # A checkpoint can only follow real provider I/O, so a runtime is always present. Never
            # publish a running state when it is absent.
            if tracker["runtime_pid"] is not None:
                begin_running()
            # Sample the loaded-GPU clock only at a real completed unit. An unloaded checkpoint is
            # a no-op, so stage/CPU/unloaded notifications never invent GPU use.
            gpu_clock.checkpoint()

        try:
            write("starting")
            # A pending pause/stop that arrived before this invocation starts no model at all.
            if state.desired_count > 0 and gate():
                tracker["runtime_pid"] = owner.start(
                    translation_runtime_spec(translation_settings, worker_root),
                    attempts=settings.translation_controller_health_attempts,
                    interval=settings.poll_interval_seconds,
                    timeout=settings.stop_timeout_seconds,
                )
                gpu_clock.loaded()
                begin_running()

            report = run_translation_command(
                output_path=directory / "output.json",
                course_limit=session.course_limit,
                before_pending_item=gate,
                on_checkpoint=on_checkpoint,
                before_request=before_request,
                request_scope=mechanics.model_request_scope,
            )
        except Exception as exc:
            accumulate_active()
            if not _stop_owned_runtime(owner, settings):
                # Shutdown could not be proved. The recorded state and the runtime record are left
                # recoverable.
                return 1
            gpu_clock.unloaded()
            tracker["runtime_pid"] = None
            write("failed", error_type=type(exc).__name__)
            return 1

        accumulate_active()
        if not _stop_owned_runtime(owner, settings):
            return 1
        gpu_clock.unloaded()
        tracker["runtime_pid"] = None
        tracker["completed_count"] = report.output_count
        atomic_write_private_text(directory / "run-report.json", administrative_json(report))
        # A request that arrives between the last durable gate and the provider's own admission
        # ends the run with a partial report. Classify the terminal lifecycle from live control so
        # an interrupted stop or pause publishes stopped or paused. A latched due
        # checkpoint with unfinished selected work yields an unloaded paused checkpoint
        # for the shared restart. A completed workload is terminal.
        requested = read_control(directory, session).requested_action
        if requested == "stop":
            write("stopped")
        elif requested == "pause":
            write("paused")
        elif gpu_clock.due and report.output_count < state.desired_count:
            write("paused")
        else:
            write("completed")
        return 0

    def read_import_receipt(
        self,
        session: WorkerDatasetSession,
        state: TranslationControllerWorkerState,
        directory: Path,
    ) -> TranslationControllerImportReceipt | None:
        return _read_import_receipt(session, state, directory)

    def finalize(
        self,
        session: WorkerDatasetSession,
        state: TranslationControllerWorkerState,
        directory: Path,
    ) -> None:
        _finalize(session, state, directory)

    def status(
        self,
        session: WorkerDatasetSession,
        state: TranslationControllerWorkerState,
        directory: Path,
        *,
        clock: Callable[[], datetime],
        lifecycle: str | None,
    ) -> TranslationControllerStatus:
        return _status_from_state(
            session, state, directory=directory, clock=clock, lifecycle=lifecycle
        )

    def stop_updates(
        self, state: TranslationControllerWorkerState, directory: Path
    ) -> dict[str, object]:
        return _stop_updates(state, directory)

    def require_cleanup_evidence(
        self,
        session: WorkerDatasetSession,
        receipt: TranslationControllerImportReceipt,
        directory: Path,
    ) -> None:
        _require_cleanup_evidence(receipt, directory)


def main(argv: Sequence[str] | None = None) -> int:
    """Expose the worker subcommands through the shared shell."""
    return worker_session.worker_main(TranslationWorkerStage(), argv)


if __name__ == "__main__":
    raise SystemExit(main())
