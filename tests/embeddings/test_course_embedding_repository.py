"""Opt-in PostgreSQL proofs for course embedding reconciliation, invalidation, and retries."""

from __future__ import annotations

import contextlib
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import Engine, func, select

from course_explorer.administration import (
    administrative_json,
    atomic_write_private_text,
    session_directory,
    utc_now,
)
from course_explorer.constants import COURSE_EMBEDDING_DIMENSION
from course_explorer.db.models import (
    CourseEmbeddingChunk,
    CourseVersionCurriculumPeriod,
)
from course_explorer.db.session import session_scope
from course_explorer.embeddings import commands as embeddings_commands
from course_explorer.embeddings.generation import CourseEmbeddingService
from course_explorer.embeddings.provider import EmbeddingRequestError
from course_explorer.embeddings.repository import CourseEmbeddingRepository
from course_explorer.enums import (
    CourseEmbeddingStatus,
    TeachingTextField,
    TeachingTextLanguage,
    TeachingTextOrigin,
)
from course_explorer.http_retry import RequestNotStarted
from course_explorer.teaching_text.service import TeachingTextService
from course_explorer_admin import lifecycle, mechanics
from course_explorer_admin.lifecycle import (
    EmbeddingOptions,
    EmbeddingProgress,
    LifecycleContext,
    LifecycleSession,
    LifecycleState,
    read_lifecycle_state,
)
from course_explorer_admin.local_stages import EmbeddingStage
from course_explorer_admin.worker import run_lifecycle_worker
from tests.embeddings._repository_support import (
    FakeProvider,
    _chunk_state,
    compose,
    embedding_settings,
    seed_representatives,
    upsert_translation,
)

pytestmark = [
    pytest.mark.integration,
]


def _seed_embedding_session(
    root: Path, session_id: str, *, options: EmbeddingOptions
) -> LifecycleSession:
    """Publish one current receipt/state naming this test process as the owned worker."""
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    directory = session_directory(root, session_id)
    directory.mkdir(mode=0o700, parents=False, exist_ok=False)
    session = LifecycleSession(
        schema_version=1,
        session_id=session_id,
        stage="embedding",
        revision="a" * 40,
        identity_sha256="b" * 64,
        options=options,
        created_at=utc_now(),
    )
    atomic_write_private_text(directory / "session.json", administrative_json(session))
    lifecycle.write_lifecycle_state(root, _embedding_state(session_id))
    return session


def _embedding_state(session_id: str) -> LifecycleState:
    process = mechanics.OwnedProcessRecord(
        schema_version=1,
        pid=os.getpid(),
        argv=mechanics.read_process_command_line(os.getpid()) or ("pytest",),
        boot_id=mechanics.current_boot_id(),
    )
    return LifecycleState(
        schema_version=1,
        session_id=session_id,
        lifecycle="paused",
        requested_action="run",
        process=process,
        progress=EmbeddingProgress(
            kind="embedding",
            reconciled=False,
            desired_count=0,
            pending_count=0,
            completed_count=0,
            failed_count=0,
            generated_count=0,
        ),
        work_complete=False,
        owned_services=(),
        active_seconds=0.0,
        running_since=None,
        error_type=None,
    )


def _reseed_embedding_owner(root: Path, session_id: str) -> None:
    """Re-arm the retained state with a fresh process owner for one direct worker invocation."""
    current = read_lifecycle_state(root)
    assert current is not None
    fresh = _embedding_state(session_id)
    lifecycle.write_lifecycle_state(
        root,
        current.model_copy(
            update={"requested_action": "run", "process": fresh.process, "lifecycle": "paused"}
        ),
    )


class _VirtualClock:
    """A datetime clock whose value only moves when the test advances it."""

    def __init__(self, start: datetime) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


def test_reconcile_embeds_and_reuses_matching_chunks(
    database: tuple[Engine, object],
) -> None:
    """Real reconciliation embeds in bounded batches, completes them, then reuses on rerun."""
    ids = seed_representatives(database)
    _, factory = database
    service, repository, provider, text_service, base_config = compose(database)
    config = base_config.model_copy(update={"embedding_generation_batch_size": 2})
    service = CourseEmbeddingService(text_service, repository, provider, config)

    report = service.run()
    assert report.canonical_course_count == 1
    assert report.desired_chunk_count > 0
    assert report.inserted_count == report.desired_chunk_count
    assert report.embedded_count == report.desired_chunk_count
    assert report.coverage.pending_count == 0
    assert report.coverage.failed_count == 0
    assert report.coverage.completed_count == report.desired_chunk_count
    assert provider.calls
    # Batches stay bounded and cover every desired chunk exactly once.
    assert all(len(call) <= 2 for call in provider.calls)
    assert sum(len(call) for call in provider.calls) == report.desired_chunk_count

    with session_scope(factory) as session:
        rows = list(
            session.scalars(
                select(CourseEmbeddingChunk).where(
                    CourseEmbeddingChunk.course_version_id == ids["direct_version"]
                )
            )
        )
        identity = {row.field: row.id for row in rows}
        assert len(rows) == report.desired_chunk_count
        assert all(row.status is CourseEmbeddingStatus.COMPLETED for row in rows)
        assert all(row.embedding is not None for row in rows)
        assert all(row.text_origin is TeachingTextOrigin.OFFICIAL for row in rows)

    provider.calls.clear()
    rerun = service.run()
    assert rerun.embedded_count == 0
    assert rerun.reused_count == rerun.desired_chunk_count
    assert rerun.deleted_count == 0
    assert provider.calls == []

    with session_scope(factory) as session:
        rows = list(
            session.scalars(
                select(CourseEmbeddingChunk).where(
                    CourseEmbeddingChunk.course_version_id == ids["direct_version"]
                )
            )
        )
        assert {row.field: row.id for row in rows} == identity

    coverage = repository.coverage(("course-a",))
    assert coverage.completed_count == report.desired_chunk_count
    assert coverage.total_chunk_count == report.desired_chunk_count
    # The full-catalogue diagnostic equals the single seeded canonical scope.
    assert repository.coverage() == coverage
    # An unrelated or explicit empty scope is an all-zero report rather than the global total.
    assert repository.coverage(("course-absent",)).total_chunk_count == 0
    assert repository.coverage(()).total_chunk_count == 0


def test_reconcile_invalidates_translation_and_removes_inactive_representative_chunks(
    database: tuple[Engine, object],
) -> None:
    """A translation change resets its own chunk. A representative change removes the inactive representative's chunks."""
    ids = seed_representatives(database)
    _, factory = database
    service, _, provider, _, _ = compose(database)

    baseline = service.run()
    assert baseline.desired_chunk_count > 0
    provider.calls.clear()

    upsert_translation(database, "Linear algebra")
    inserted = service.run()
    # The inserted chunk is the derived NAME/EN chunk.
    assert inserted.inserted_count == 1
    assert inserted.reused_count == baseline.desired_chunk_count

    before = _chunk_state(database, ids["direct_version"])

    upsert_translation(database, "Linear algebra revisited")
    provider.calls.clear()
    invalidated = service.run()
    after = _chunk_state(database, ids["direct_version"])

    assert invalidated.invalidated_count == 1
    assert invalidated.reused_count == invalidated.desired_chunk_count - 1
    content_key = (TeachingTextField.CONTENT, TeachingTextLanguage.FI)
    name_en_key = (TeachingTextField.NAME, TeachingTextLanguage.EN)
    # Matching chunk text holds its identity and vector.
    assert after[content_key] == before[content_key]
    # The changed translation's chunk is the only reset row.
    assert after[name_en_key] != before[name_en_key]

    # Move the representative: switch current-year membership to the archived version and prove
    # the outgoing representative's rows are deleted.
    with session_scope(factory) as session:
        session.execute(
            CourseVersionCurriculumPeriod.__table__.delete().where(
                CourseVersionCurriculumPeriod.course_version_id == ids["direct_version"]
            )
        )
        session.add(
            CourseVersionCurriculumPeriod(
                course_version_id=ids["alt_version"], curriculum_period_id="period-2026"
            )
        )
    moved = service.run()
    assert moved.deleted_count > 0
    with session_scope(factory) as session:
        old_rows = session.scalar(
            select(func.count())
            .select_from(CourseEmbeddingChunk)
            .where(CourseEmbeddingChunk.course_version_id == ids["direct_version"])
        )
        new_rows = session.scalar(
            select(func.count())
            .select_from(CourseEmbeddingChunk)
            .where(CourseEmbeddingChunk.course_version_id == ids["alt_version"])
        )
    assert old_rows == 0
    assert new_rows == moved.desired_chunk_count


def test_batch_checkpoint_pause_and_restart_preserve_completed_vectors(
    database: tuple[Engine, object],
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The real worker pauses at a batch checkpoint. A re-armed worker retries only pending rows.

    A controlled clock proves the public rate/ETA measure only this invocation's successful
    vectors over post-reconciliation time: a long catalogue setup and the paused interval never
    inflate them.
    """
    ids = seed_representatives(database)
    _, factory = database
    config = embedding_settings().model_copy(update={"embedding_generation_batch_size": 1})

    monkeypatch.setattr(
        embeddings_commands,
        "_database_context",
        lambda settings: contextlib.nullcontext(factory),
    )
    monkeypatch.setattr(embeddings_commands, "load_embedding_runtime_settings", lambda: config)

    options = EmbeddingOptions(kind="embedding")
    root = tmp_path / "lifecycle"
    session_id = "1" * 32
    _seed_embedding_session(root, session_id, options=options)

    clock = _VirtualClock(datetime(2026, 1, 1, 12, 0, tzinfo=UTC))
    setup_seconds = iter((5000.0, 9000.0))
    real_build = TeachingTextService.build_catalogue

    def build_with_setup(self, **kwargs):
        clock.advance(next(setup_seconds))
        return real_build(self, **kwargs)

    monkeypatch.setattr(TeachingTextService, "build_catalogue", build_with_setup)

    def advancing_provider() -> FakeProvider:
        provider = FakeProvider()
        original = provider.embed

        def embed(texts):
            clock.advance(10.0)
            return original(texts)

        monkeypatch.setattr(provider, "embed", embed)
        return provider

    recording = advancing_provider()
    monkeypatch.setattr(
        embeddings_commands,
        "EmbeddingProvider",
        lambda *args, **kwargs: contextlib.nullcontext(recording),
    )

    real_checkpoint = LifecycleContext.checkpoint
    requested = {"enabled": True, "done": False}
    observed: list[tuple[int, lifecycle.LifecycleStatus]] = []

    def checkpoint_with_pause(self, progress) -> None:
        real_checkpoint(self, progress)
        if isinstance(progress, EmbeddingProgress):
            state_bytes = (self.root / "state.json").read_bytes()
            observed.append(
                (
                    progress.completed_count,
                    lifecycle.read_lifecycle_status(EmbeddingStage(), self.root, clock=clock),
                )
            )
            assert (self.root / "state.json").read_bytes() == state_bytes
        if (
            requested["enabled"]
            and not requested["done"]
            and isinstance(progress, EmbeddingProgress)
            and progress.completed_count >= 1
        ):
            requested["done"] = True
            with mechanics.exclusive_action_lock(
                self.root, controller_name=self.session.stage, blocking=True
            ):
                current = read_lifecycle_state(self.root)
                assert current is not None
                lifecycle.write_lifecycle_state(
                    self.root, current.model_copy(update={"requested_action": "pause"})
                )

    monkeypatch.setattr(LifecycleContext, "checkpoint", checkpoint_with_pause)

    paused = run_lifecycle_worker(EmbeddingStage(), root, session_id, clock=clock)
    assert paused.lifecycle == "paused"
    assert len(recording.calls) == 1
    # Reconciliation reports no pace/ETA. The first committed batch measures 0.1 vectors/s and
    # an ETA from the real remaining count, never the 5000 s catalogue setup.
    initial_count, initial_status = observed[0]
    assert initial_count == 0
    assert initial_status.items_per_second is None
    assert initial_status.eta_seconds is None
    measured_count, measured_status = observed[1]
    assert measured_count == 1
    assert measured_status.items_per_second == pytest.approx(0.1)
    # The first committed batch keeps its exact row identity and vector.
    with session_scope(factory) as session:
        completed_rows = list(
            session.scalars(
                select(CourseEmbeddingChunk).where(
                    CourseEmbeddingChunk.course_version_id == ids["direct_version"],
                    CourseEmbeddingChunk.status == CourseEmbeddingStatus.COMPLETED,
                )
            )
        )
        pending_rows = list(
            session.scalars(
                select(CourseEmbeddingChunk).where(
                    CourseEmbeddingChunk.course_version_id == ids["direct_version"],
                    CourseEmbeddingChunk.status == CourseEmbeddingStatus.PENDING,
                )
            )
        )
    assert len(completed_rows) == 1
    state = read_lifecycle_state(root)
    assert state is not None and isinstance(state.progress, EmbeddingProgress)
    assert len(pending_rows) == state.progress.desired_count - 1
    assert measured_status.eta_seconds == pytest.approx(
        (state.progress.pending_count + state.progress.failed_count) / 0.1
    )
    before = {row.id: list(row.embedding) for row in completed_rows}
    assert all(row.embedding is not None for row in completed_rows)

    # A re-armed worker with a fresh provider process-equivalent retries only the pending rows.
    requested["enabled"] = False
    resume_observation_start = len(observed)
    resumed_provider = advancing_provider()
    monkeypatch.setattr(
        embeddings_commands,
        "EmbeddingProvider",
        lambda *args, **kwargs: contextlib.nullcontext(resumed_provider),
    )
    _reseed_embedding_owner(root, session_id)
    completed = run_lifecycle_worker(EmbeddingStage(), root, session_id, clock=clock)
    assert completed.lifecycle == "completed"
    assert len(resumed_provider.calls) == len(pending_rows)
    # A fresh invocation's first zero-work checkpoint clears the preceding invocation's measurement.
    _, resumed_first_status = observed[resume_observation_start]
    assert resumed_first_status.items_per_second is None
    # The resumed invocation measures its own successful work again at 0.1 vectors/s. Cumulative
    # generated count keeps the whole session's writes.
    assert completed.items_per_second == pytest.approx(0.1)
    assert completed.progress is not None
    assert completed.progress.generated_count == state.progress.desired_count
    with session_scope(factory) as session:
        for row_id, vector in before.items():
            row = session.get(CourseEmbeddingChunk, row_id)
            assert row is not None
            assert list(row.embedding) == vector
            assert row.status is CourseEmbeddingStatus.COMPLETED
    coverage = CourseEmbeddingRepository(factory).coverage(("course-a",))
    assert coverage.completed_count == state.progress.desired_count
    assert coverage.pending_count == 0


@pytest.mark.parametrize(
    "error",
    [
        EmbeddingRequestError("POST /v1/embeddings: HTTP 503"),
        RuntimeError("unexpected private sentinel"),
        RequestNotStarted("declined"),
    ],
    ids=["known-error", "unexpected-error", "declined-request"],
)
def test_failed_and_interrupted_chunks_are_retryable(
    database: tuple[Engine, object], error: Exception
) -> None:
    """A real-service failure persists failed state and re-raises. A fresh run retries the work."""
    ids = seed_representatives(database)
    _, factory = database
    _, repository, _, text_service, base_config = compose(database)
    config = base_config.model_copy(update={"embedding_generation_batch_size": 1})
    checkpoints: list[object] = []
    declined = isinstance(error, RequestNotStarted)
    provider = FakeProvider(error=error)

    if declined:
        result = CourseEmbeddingService(text_service, repository, provider, config).run(
            on_checkpoint=checkpoints.append
        )
        assert result is None
    else:
        with pytest.raises(type(error)):
            CourseEmbeddingService(text_service, repository, provider, config).run(
                on_checkpoint=checkpoints.append
            )
    # Batch size one: exactly one provider call was recorded for the first row.
    assert len(provider.calls) == 1
    assert len(provider.calls[0]) == 1

    with session_scope(factory) as session:
        rows = list(
            session.scalars(
                select(CourseEmbeddingChunk).where(
                    CourseEmbeddingChunk.course_version_id == ids["direct_version"]
                )
            )
        )
    assert checkpoints[-1].coverage.completed_count == 0
    if declined:
        assert all(row.status is CourseEmbeddingStatus.PENDING for row in rows)
        assert all(row.embedding is None for row in rows)
        assert checkpoints[-1].coverage.pending_count == len(rows)
        assert checkpoints[-1].coverage.failed_count == 0
    else:
        failed_rows = [row for row in rows if row.status is CourseEmbeddingStatus.FAILED]
        assert len(failed_rows) == 1
        assert failed_rows[0].embedding is None
        assert checkpoints[-1].coverage.pending_count == len(rows) - 1
        assert checkpoints[-1].coverage.failed_count == 1

    # A fresh process-equivalent service retries only the unfinished work and completes it.
    resumed_provider = FakeProvider()
    resumed = CourseEmbeddingService(
        text_service, CourseEmbeddingRepository(factory), resumed_provider, config
    )
    report = resumed.run()

    assert report.retry_count == len(rows)
    assert report.embedded_count == len(rows)
    assert len(resumed_provider.calls) == len(rows)
    assert report.coverage.completed_count == len(rows)
    assert report.coverage.pending_count == 0
    assert report.coverage.failed_count == 0


def test_require_current_chunks_is_projected_read_only_and_refuses_stale_work(
    database: tuple[Engine, object],
) -> None:
    """Readiness accepts exact completed vectors, refuses stale/missing work, and mutates nothing."""
    from course_explorer.db.models import CourseEmbeddingChunk
    from course_explorer.embeddings.generation import build_course_embedding_chunks

    seed_representatives(database)
    _, factory = database
    service, repository, _, text_service, config = compose(database)
    report = service.run()
    assert report is not None
    chunks = build_course_embedding_chunks(text_service.build_catalogue(), config)
    assert chunks
    repository.require_current_chunks(chunks)
    repository.require_current_chunks(())

    with session_scope(factory) as session:
        before = [
            (row.id, row.status, row.embedding is not None, row.effective_text_hash)
            for row in session.scalars(
                select(CourseEmbeddingChunk).order_by(CourseEmbeddingChunk.id)
            )
        ]

    # Duplicate desired identities and a missing requested chunk both fail loudly.
    with pytest.raises(ValueError):
        repository.require_current_chunks((chunks[0], chunks[0]))
    with pytest.raises(ValueError):
        repository.require_current_chunks((chunks[0].model_copy(update={"chunk_index": 99}),))

    # Readiness never mutated the rows (identical identity, status, vector presence, text hash).
    with session_scope(factory) as session:
        after = [
            (row.id, row.status, row.embedding is not None, row.effective_text_hash)
            for row in session.scalars(
                select(CourseEmbeddingChunk).order_by(CourseEmbeddingChunk.id)
            )
        ]
    assert after == before

    # A pending desired row makes readiness fail without writing anything.
    with session_scope(factory) as session:
        pending_row = session.get(CourseEmbeddingChunk, before[0][0])
        assert pending_row is not None
        pending_row.status = CourseEmbeddingStatus.PENDING
        pending_row.embedding = None
    with pytest.raises(ValueError):
        repository.require_current_chunks(chunks)
    # Restore that exact row to its real completed vector so the following stale contrast has no
    # pending confounder. Readiness accepts the complete set before the hash changes.
    with session_scope(factory) as session:
        restored_row = session.get(CourseEmbeddingChunk, before[0][0])
        assert restored_row is not None
        restored_row.status = CourseEmbeddingStatus.COMPLETED
        restored_row.embedding = [0.5] + [0.0] * (COURSE_EMBEDDING_DIMENSION - 1)
    repository.require_current_chunks(chunks)
    with session_scope(factory) as session:
        stale_row = session.get(CourseEmbeddingChunk, before[1][0])
        assert stale_row is not None
        stale_row.effective_text_hash = "f" * 64
        stale_row.source_text_hash = "f" * 64
    with pytest.raises(ValueError):
        repository.require_current_chunks(chunks)
