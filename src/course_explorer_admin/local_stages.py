"""Local stage adapters over the shared lifecycle core.

Each adapter implements :class:`~course_explorer_admin.lifecycle.Stage` for one local
administrative stage. It owns the stage-specific product decisions: the coarse work identity,
the prepared-resource check, the database schema-head check, the exact callbacks the product
command needs, and finalization. Every controlled run delegates exactly once to
``run_capture_command`` or ``run_course_embedding_command``. The public adapters are the
operator entry points the scripts and the unified command dispatcher call.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from course_explorer.administration import (
    repository_root,
    sha256_file,
    utc_now,
)
from course_explorer.config import (
    KoriSettings,
    NormalizationSettings,
    load_capture_settings,
    load_database_settings,
    load_embedding_runtime_settings,
    load_kori_settings,
    load_normalization_settings,
)
from course_explorer.datasets import require_database_schema
from course_explorer.db.session import create_database_engine
from course_explorer.embeddings.commands import run_course_embedding_command
from course_explorer.embeddings.generation import (
    CourseEmbeddingProgress,
    CourseEmbeddingRunReport,
    embedding_configuration_sha256,
)
from course_explorer.hashing import json_sha256
from course_explorer.ingestion.commands import run_capture_command
from course_explorer.ingestion.manifest import (
    RawCaptureStore,
    discover_capture_manifests,
    prune_capture_runs,
)
from course_explorer_admin import mechanics
from course_explorer_admin.lifecycle import (
    ControllerAction,
    EmbeddingOptions,
    EmbeddingProgress,
    IngestionOptions,
    IngestionProgress,
    LifecycleContext,
    LifecycleStatus,
    StageName,
    StageOptions,
    StageProgress,
    read_lifecycle_state,
    run_lifecycle_command,
    stage_state_root,
)

_OPERATIONAL_KORI_FIELDS = frozenset(
    {
        "kori_request_timeout_seconds",
        "kori_max_attempts",
        "kori_retry_backoff_seconds",
        "kori_concurrency",
    }
)


def ingestion_configuration_sha256(
    kori_settings: KoriSettings, normalization_settings: NormalizationSettings
) -> str:
    """Hash the source, request-shape, and normalization values that change captured work.

    The payload carries the Kori settings as JSON without the four operational values
    ``kori_request_timeout_seconds``, ``kori_max_attempts``, ``kori_retry_backoff_seconds`` and
    ``kori_concurrency``, and the normalization settings as JSON.
    """
    payload = {
        "kori": kori_settings.model_dump(mode="json", exclude=_OPERATIONAL_KORI_FIELDS),
        "normalization": normalization_settings.model_dump(mode="json"),
    }
    return json_sha256(payload, ensure_ascii=True)


def stage_identity_sha256(
    stage_name: StageName, configuration_sha256: str, options: StageOptions
) -> str:
    """Hash one coarse work identity: stage, configuration, selected database and options."""
    payload = {
        "stage": stage_name,
        "configuration_sha256": configuration_sha256,
        "postgres_db": load_database_settings().postgres_db,
        "options": options.model_dump(mode="json"),
    }
    return json_sha256(payload, ensure_ascii=True)


def require_selected_database_schema() -> None:
    """Require the selected database to be at this checkout's single Alembic head."""
    engine = create_database_engine(load_database_settings())
    try:
        with engine.connect() as connection:
            require_database_schema(connection)
    finally:
        engine.dispose()


class IngestionStage:
    """Local curriculum-ingestion adapter over the ``run_capture_command`` service."""

    name: StageName = "ingestion"
    services: tuple[str, ...] = ("db",)
    temporary_services: tuple[str, ...] = ()
    retains_after_stop: bool = True
    server_worker_module: str = "course_explorer_admin.worker"

    def select_options(self) -> StageOptions:
        """Adopt the sole retained partial manifest for a fresh bare start, else capture fresh."""
        capture_settings = load_capture_settings()
        candidates: list[Path] = []
        for relative_path in discover_capture_manifests(capture_settings.raw_data_root):
            store = RawCaptureStore.open(capture_settings.raw_data_root, relative_path)
            if store.manifest.status.value not in {"running", "failed"}:
                continue
            candidates.append(Path(store.manifest_relative_path))
        if len(candidates) > 1:
            raise ValueError("multiple retained partial ingestion manifests are ambiguous")
        if not candidates:
            return IngestionOptions(kind="ingestion")
        return IngestionOptions(kind="ingestion", manifest_path=str(candidates[0]))

    def identity_sha256(self, options: StageOptions) -> str:
        configuration = ingestion_configuration_sha256(
            load_kori_settings(), load_normalization_settings()
        )
        return stage_identity_sha256(self.name, configuration, options)

    def initial_progress(self, options: StageOptions) -> StageProgress:
        return IngestionProgress(
            kind="ingestion",
            stage="selecting",
            manifest_path=None,
            run_id=None,
            manifest_sha256=None,
            response_count=0,
            verified_response_count=0,
            verification_total=None,
            normalized=False,
        )

    def require_prepared(self) -> None:
        """Do nothing: the core starts the database service."""

    def require_database(self) -> None:
        require_selected_database_schema()

    def release(self, context: LifecycleContext) -> None:
        """Release is a no-op. A local stage's work runs on this host."""

    def run(self, context: LifecycleContext) -> bool:
        """Delegate once to ``run_capture_command`` with the real boundary callbacks."""
        options = context.session.options
        if not isinstance(options, IngestionOptions):
            raise ValueError("ingestion stage requires ingestion options")
        progress = context.read_state().progress
        if not isinstance(progress, IngestionProgress):
            raise ValueError("ingestion stage requires ingestion progress")
        tracker: dict[str, object] = {
            "stage": progress.stage,
            "manifest_path": progress.manifest_path,
            "run_id": progress.run_id,
            "manifest_sha256": progress.manifest_sha256,
            "response_count": progress.response_count,
            "verified_response_count": progress.verified_response_count,
            "verification_total": progress.verification_total,
            "normalized": progress.normalized,
        }
        selected_store: RawCaptureStore | None = None

        def snapshot() -> IngestionProgress:
            return IngestionProgress(
                kind="ingestion",
                stage=tracker["stage"],  # type: ignore[arg-type]
                manifest_path=tracker["manifest_path"],  # type: ignore[arg-type]
                run_id=tracker["run_id"],  # type: ignore[arg-type]
                manifest_sha256=tracker["manifest_sha256"],  # type: ignore[arg-type]
                response_count=int(tracker["response_count"]),
                verified_response_count=int(tracker["verified_response_count"]),
                verification_total=tracker["verification_total"],  # type: ignore[arg-type]
                normalized=bool(tracker["normalized"]),
            )

        def record_manifest(store: RawCaptureStore) -> None:
            digest = store.manifest_sha256
            if tracker["manifest_sha256"] != digest:
                # A different manifest digest invalidates any retained verification prefix.
                tracker["verified_response_count"] = 0
                tracker["verification_total"] = None
            tracker["manifest_path"] = store.manifest_relative_path
            tracker["run_id"] = store.manifest.run_id
            tracker["manifest_sha256"] = digest

        def refresh_manifest_identity() -> None:
            if selected_store is None:
                return
            record_manifest(selected_store)

        def on_store_selected(store: RawCaptureStore) -> None:
            nonlocal selected_store
            selected_store = store
            record_manifest(store)

        def on_boundary(stage: str, completed: int, total: int | None) -> bool:
            tracker["stage"] = stage
            if stage == "verification":
                tracker["verified_response_count"] = completed
                tracker["verification_total"] = total
                if total is not None:
                    tracker["response_count"] = total
            else:
                tracker["response_count"] = completed
                refresh_manifest_identity()
            context.checkpoint(snapshot())
            if not context.admit():
                return False
            if stage == "before_normalization":
                # The indivisible normalization transaction that follows is labelled
                # ``normalization`` until it commits. Nothing polls inside it.
                tracker["stage"] = "normalization"
                context.checkpoint(snapshot())
            return True

        def before_request() -> bool:
            return context.admit()

        retained_manifest = tracker["manifest_path"] or options.manifest_path
        verification_start_index = int(tracker["verified_response_count"])

        try:
            if retained_manifest is not None:
                report = run_capture_command(
                    resume_manifest=Path(retained_manifest),
                    verification_start_index=verification_start_index,
                    on_store_selected=on_store_selected,
                    on_boundary=on_boundary,  # type: ignore[arg-type]
                    before_request=before_request,
                )
            else:
                report = run_capture_command(
                    on_store_selected=on_store_selected,
                    on_boundary=on_boundary,  # type: ignore[arg-type]
                    before_request=before_request,
                )
            if report is not None:
                refresh_manifest_identity()
                context.checkpoint(snapshot())
        except Exception as exc:
            # Capture rewrote the failed manifest bytes before the exception reached here, so the
            # recorded identity must be refreshed before durable failed state is published.
            # Otherwise a subsequent stop would publish a receipt that blocks continuation.
            try:
                refresh_manifest_identity()
                context.checkpoint(snapshot())
            except Exception as refresh_error:
                raise refresh_error from exc
            raise

        if report is None:
            return False
        tracker["normalized"] = True
        response_count = report.capture.response_count
        tracker["response_count"] = response_count
        tracker["verified_response_count"] = response_count
        tracker["verification_total"] = response_count
        tracker["stage"] = "complete"
        context.checkpoint(snapshot())
        return True

    def finalize(self, context: LifecycleContext) -> None:
        """Retain the exact manifest identity a subsequent bare start must continue from."""
        progress = context.read_state().progress
        if not isinstance(progress, IngestionProgress):
            raise ValueError("ingestion stage requires ingestion progress")
        if progress.manifest_path is not None:
            return
        options = context.session.options
        if not isinstance(options, IngestionOptions) or options.manifest_path is None:
            return
        store = RawCaptureStore.open(
            load_capture_settings().raw_data_root, Path(options.manifest_path)
        )
        context.checkpoint(
            progress.model_copy(
                update={
                    "manifest_path": store.manifest_relative_path,
                    "run_id": store.manifest.run_id,
                    "manifest_sha256": store.manifest_sha256,
                }
            )
        )


def _require_prepared_artifact() -> None:
    """Validate that the pinned embedding artifact exists and matches its configured checksum."""
    settings = load_embedding_runtime_settings()
    artifact = settings.embedding_artifact_path
    resolved = artifact if artifact.is_absolute() else repository_root() / artifact
    resolved = resolved.resolve()
    if not resolved.is_file() or resolved.is_symlink():
        raise ValueError("configured embedding artifact must be a regular file before start")
    if sha256_file(resolved) != settings.embedding_artifact_sha256:
        raise ValueError("configured embedding artifact checksum does not match its file")


class EmbeddingStage:
    """Local bulk-embedding adapter over the ``run_course_embedding_command`` service."""

    name: StageName = "embedding"
    services: tuple[str, ...] = ("db", "embedding")
    temporary_services: tuple[str, ...] = ("embedding",)
    retains_after_stop: bool = True
    server_worker_module: str = "course_explorer_admin.worker"

    def select_options(self) -> StageOptions:
        return EmbeddingOptions(kind="embedding")

    def identity_sha256(self, options: StageOptions) -> str:
        configuration = embedding_configuration_sha256(load_embedding_runtime_settings())
        return stage_identity_sha256(self.name, configuration, options)

    def initial_progress(self, options: StageOptions) -> StageProgress:
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
        _require_prepared_artifact()

    def require_database(self) -> None:
        require_selected_database_schema()

    def release(self, context: LifecycleContext) -> None:
        """Release is a no-op. A local stage's work runs on this host."""

    def run(self, context: LifecycleContext) -> bool:
        """Delegate once to ``run_course_embedding_command`` over the sole generation service."""
        options = context.session.options
        if not isinstance(options, EmbeddingOptions):
            raise ValueError("embedding stage requires embedding options")
        progress = context.read_state().progress
        if not isinstance(progress, EmbeddingProgress):
            raise ValueError("embedding stage requires embedding progress")
        process_start_generated = progress.generated_count
        measurement_start: datetime | None = None

        def pace(embedded_count: int) -> float | None:
            """Measure this invocation's successful vectors over the time since reconciliation."""
            if measurement_start is None or embedded_count <= 0:
                return None
            elapsed = (context.clock() - measurement_start).total_seconds()
            if elapsed <= 0:
                return None
            return embedded_count / elapsed

        def convert(
            value: CourseEmbeddingProgress,
            *,
            embedded_count: int,
            items_per_second: float | None,
        ) -> EmbeddingProgress:
            return EmbeddingProgress(
                kind="embedding",
                reconciled=True,
                desired_count=value.desired_chunk_count,
                pending_count=value.coverage.pending_count,
                completed_count=value.coverage.completed_count,
                failed_count=value.coverage.failed_count,
                generated_count=process_start_generated + embedded_count,
                items_per_second=items_per_second,
            )

        def on_checkpoint(value: CourseEmbeddingProgress) -> None:
            nonlocal measurement_start
            if measurement_start is None:
                measurement_start = context.clock()
            context.checkpoint(
                convert(
                    value,
                    embedded_count=value.embedded_count,
                    items_per_second=pace(value.embedded_count),
                )
            )

        report = run_course_embedding_command(
            before_pending_batch=context.admit,
            before_request=context.admit,
            on_checkpoint=on_checkpoint,
            request_scope=mechanics.model_request_scope,
        )
        if report is None:
            return False
        if not isinstance(report, CourseEmbeddingRunReport):
            raise ValueError("detached embedding worker requires a generation report")
        context.checkpoint(
            convert(
                report,
                embedded_count=report.embedded_count,
                items_per_second=pace(report.embedded_count),
            )
        )
        return True

    def finalize(self, context: LifecycleContext) -> None:
        """Vectors are committed when embedding completes, so stop is a no-op."""


def _cleanup_ingestion_raw(root: Path) -> None:
    """Prune every non-retained raw capture run once ingestion has reached idle.

    The per-stage lock is held across survivor selection and deletion so a concurrent
    ``start`` cannot publish a live ingestion session mid-cleanup. It is never held around the
    core stop/wait/finalization. Only an idle state with no live owned process may prune. The
    sole retained incomplete job's bound manifest path selects the whole surviving directory.
    Completed idle work and an absent state select nothing. A non-idle state, a live owned process
    or a non-ingestion progress type fails loudly.
    """
    with mechanics.exclusive_action_lock(root, controller_name="ingestion", blocking=True):
        state = read_lifecycle_state(root)
        if state is not None:
            if state.lifecycle != "idle":
                raise ValueError("ingestion raw cleanup requires an idle lifecycle")
            if state.process is not None and mechanics.owned_process_is_alive(state.process):
                raise ValueError("ingestion raw cleanup requires no live owned process")
        retained_manifest: Path | None = None
        if state is not None and not state.work_complete:
            progress = state.progress
            if not isinstance(progress, IngestionProgress):
                raise ValueError("retained ingestion work requires ingestion progress")
            if progress.manifest_path is not None:
                retained_manifest = Path(progress.manifest_path)
        prune_capture_runs(
            load_capture_settings().raw_data_root, retained_manifest=retained_manifest
        )


def run_ingestion_command(
    action: ControllerAction,
    *,
    runner: mechanics.ProcessRunner | None = None,
    clock: Callable[[], datetime] = utc_now,
    session_id_factory: Callable[[], str] = lambda: uuid.uuid4().hex,
    sleep: Callable[[float], None] = time.sleep,
) -> LifecycleStatus:
    """Run exactly one local ingestion lifecycle action through the shared core.

    After a stop that reaches idle, the raw root is pruned to the sole retained resumable job's
    directory. A failed stop never prunes.
    """
    root = stage_state_root("ingestion")
    status = run_lifecycle_command(
        action,
        stage=IngestionStage(),
        root=root,
        runner=runner,
        clock=clock,
        session_id_factory=session_id_factory,
        sleep=sleep,
    )
    if action == "stop" and status.lifecycle == "idle":
        _cleanup_ingestion_raw(root)
    return status


def run_embedding_command(
    action: ControllerAction,
    *,
    runner: mechanics.ProcessRunner | None = None,
    clock: Callable[[], datetime] = utc_now,
    session_id_factory: Callable[[], str] = lambda: uuid.uuid4().hex,
    sleep: Callable[[float], None] = time.sleep,
) -> LifecycleStatus:
    """Run exactly one local embedding lifecycle action through the shared core."""
    return run_lifecycle_command(
        action,
        stage=EmbeddingStage(),
        root=stage_state_root("embedding"),
        runner=runner,
        clock=clock,
        session_id_factory=session_id_factory,
        sleep=sleep,
    )
