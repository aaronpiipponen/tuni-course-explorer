"""Shared opt-in PostgreSQL fixtures for the course-embedding repository contracts.

The fixtures compose the real generation service and repository over real curricula and a
recording fake provider, so each SQL proof exercises the actual persistence path.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Engine, select

from course_explorer.config import EmbeddingSettings
from course_explorer.constants import COURSE_EMBEDDING_DIMENSION
from course_explorer.curriculum_repository import CurriculumRepository
from course_explorer.db.models import (
    Course,
    CourseEmbeddingChunk,
    CourseText,
    CourseVersion,
    CourseVersionCurriculumPeriod,
    CurriculumPeriod,
    IngestionRun,
    SourceSnapshot,
)
from course_explorer.db.session import session_scope
from course_explorer.embeddings.generation import CourseEmbeddingService
from course_explorer.embeddings.repository import CourseEmbeddingRepository
from course_explorer.enums import (
    IngestionRunStatus,
    SourceObjectType,
    TeachingTextField,
    TeachingTextLanguage,
    TranslationMethod,
)
from course_explorer.teaching_text.repository import DerivedTranslationRepository
from course_explorer.teaching_text.service import (
    DerivedTranslationInput,
    TeachingTextService,
)
from tests.support import settings_factory

GENERATED_AT = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


class FakeProvider:
    """Records batches and returns a deterministic vector or raises one configured error."""

    def __init__(self, *, error: Exception | None = None) -> None:
        self.calls: list[tuple[str, ...]] = []
        self._error = error

    def embed(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        self.calls.append(tuple(texts))
        if self._error is not None:
            raise self._error
        return tuple(
            tuple(0.5 if index == 0 else 0.0 for index in range(COURSE_EMBEDDING_DIMENSION))
            for _ in texts
        )


def embedding_settings() -> EmbeddingSettings:
    """Build the full required embedding configuration with a generation batch."""
    return settings_factory(
        EmbeddingSettings,
        EMBEDDING_CONTEXT_SIZE=1024,
        EMBEDDING_REQUEST_TIMEOUT_SECONDS=30,
        EMBEDDING_GENERATION_BATCH_SIZE=16,
        EMBEDDING_ARTIFACT_URL="https://example.test/model.gguf",
        EMBEDDING_ARTIFACT_PATH="models/model.gguf",
        EMBEDDING_ARTIFACT_SHA256="a" * 64,
        EMBEDDING_SERVER_IMAGE="ghcr.io/ggml-org/llama.cpp:server@sha256:" + "b" * 64,
        EMBEDDING_RUNTIME_REVISION="c" * 40,
    )


def compose(
    database: tuple[Engine, object],
) -> tuple[
    CourseEmbeddingService,
    CourseEmbeddingRepository,
    FakeProvider,
    TeachingTextService,
    EmbeddingSettings,
]:
    """Build the real generation service over real curricula and a recording fake provider."""
    _, factory = database
    teaching_text = TeachingTextService(
        CurriculumRepository(factory), DerivedTranslationRepository(factory)
    )
    repository = CourseEmbeddingRepository(factory)
    provider = FakeProvider()
    config = embedding_settings()
    service = CourseEmbeddingService(teaching_text, repository, provider, config)
    return service, repository, provider, teaching_text, config


def seed_representatives(database: tuple[Engine, object]) -> dict[str, UUID]:
    """Seed a current-year representative and an archived version for one canonical course."""
    _, factory = database
    run_id = uuid.uuid4()
    snapshot_direct = uuid.uuid4()
    snapshot_alt = uuid.uuid4()
    course_id = uuid.uuid4()
    direct_version = uuid.uuid4()
    alt_version = uuid.uuid4()

    with session_scope(factory) as session:
        session.add(
            IngestionRun(
                id=run_id,
                status=IngestionRunStatus.COMPLETED,
                raw_root_path="data/raw/run",
                manifest_path="data/raw/run/manifest.json",
            )
        )
        session.add(CurriculumPeriod(id="period-2026", academic_year_start=2026))
        session.add_all(
            [
                SourceSnapshot(
                    id=snapshot_direct,
                    ingestion_run_id=run_id,
                    object_type=SourceObjectType.COURSE_UNIT,
                    source_object_id="course-a-2026",
                    source_group_id="course-a",
                    response_path="courses/embedding.json",
                    response_item_index=0,
                    source_hash="a" * 64,
                ),
                SourceSnapshot(
                    id=snapshot_alt,
                    ingestion_run_id=run_id,
                    object_type=SourceObjectType.COURSE_UNIT,
                    source_object_id="course-a-2020",
                    source_group_id="course-a",
                    response_path="courses/embedding.json",
                    response_item_index=1,
                    source_hash="b" * 64,
                ),
            ]
        )
        session.flush()
        session.add(
            Course(
                id=course_id,
                group_id="course-a",
                is_active=True,
                activity_as_of_academic_year_start=2026,
                activity_window_years=3,
            )
        )
        session.flush()
        session.add_all(
            [
                CourseVersion(
                    id=direct_version,
                    course_id=course_id,
                    sisu_course_unit_id="course-a-2026",
                    code="A.1",
                    name_fi="Lineaarialgebra",
                    credits_min=5,
                    credits_max=5,
                    official_url="https://example.test/a",
                    document_state="ACTIVE",
                    source_snapshot_id=snapshot_direct,
                ),
                CourseVersion(
                    id=alt_version,
                    course_id=course_id,
                    sisu_course_unit_id="course-a-2020",
                    code="A.1",
                    name_fi="Vanha lineaaralgebra",
                    credits_min=5,
                    credits_max=5,
                    official_url="https://example.test/a-old",
                    document_state="ARCHIVED",
                    source_snapshot_id=snapshot_alt,
                ),
            ]
        )
        session.flush()
        session.add(
            CourseVersionCurriculumPeriod(
                course_version_id=direct_version, curriculum_period_id="period-2026"
            )
        )
        session.add(
            CourseText(
                course_version_id=direct_version,
                content_fi="Matriisit",
                content_en="Matrices",
            )
        )
    return {
        "run_id": run_id,
        "course_id": course_id,
        "direct_version": direct_version,
        "alt_version": alt_version,
    }


def upsert_translation(database: tuple[Engine, object], text: str) -> None:
    """Write one manual NAME/EN derived translation for the seeded representative."""
    _, factory = database
    DerivedTranslationRepository(factory).upsert(
        (
            DerivedTranslationInput(
                sisu_course_unit_id="course-a-2026",
                field=TeachingTextField.NAME,
                language=TeachingTextLanguage.EN,
                source_language=TeachingTextLanguage.FI,
                source_text="Lineaarialgebra",
                text=text,
                translation_method=TranslationMethod.MANUAL,
                generated_at=GENERATED_AT,
            ),
        )
    )


def _chunk_state(
    database: tuple[Engine, object], course_version_id: UUID
) -> dict[tuple[TeachingTextField, TeachingTextLanguage], tuple[UUID, bool, str]]:
    """Capture per-cell row identity, vector presence, and text hash for comparison."""
    _, factory = database
    with session_scope(factory) as session:
        rows = list(
            session.scalars(
                select(CourseEmbeddingChunk).where(
                    CourseEmbeddingChunk.course_version_id == course_version_id
                )
            )
        )
    return {
        (row.field, row.language): (row.id, row.embedding is not None, row.effective_text_hash)
        for row in rows
    }
