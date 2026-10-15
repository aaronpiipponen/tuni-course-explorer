"""Shared opt-in PostgreSQL fixtures for the exact-cosine semantic-search contracts.

The seed helpers build a stored chunk graph so the real pgvector read and the current
official-summary mapping can be exercised against a disposable database.
"""

from __future__ import annotations

import math
import uuid
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Engine

from course_explorer.config import EmbeddingSettings, SearchSettings
from course_explorer.constants import COURSE_EMBEDDING_DIMENSION
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
from course_explorer.embeddings.generation import embedding_configuration_sha256
from course_explorer.enums import (
    CourseEmbeddingStatus,
    IngestionRunStatus,
    SourceObjectType,
    TeachingTextField,
    TeachingTextLanguage,
    TeachingTextOrigin,
    TranslationMethod,
)
from tests.support import settings_factory

GENERATED_AT = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
OTHER_CONFIGURATION_HASH = "f" * 64
CURRENT_YEAR = 2026
WINDOW_YEARS = 3


def embedding_settings() -> EmbeddingSettings:
    """Build the full required embedding configuration used to derive the compatible hash."""
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
        EMBEDDING_HUB_VECTOR=[0.0] * COURSE_EMBEDDING_DIMENSION,
    )


def search_settings(min_score: float) -> SearchSettings:
    return settings_factory(
        SearchSettings,
        SEMANTIC_SEARCH_MIN_SCORE=str(min_score),
    )


def cosine_vector(cosine: float) -> tuple[float, ...]:
    """Return one 1024-dimensional unit vector with the requested exact cosine to the query."""
    sine = math.sqrt(1.0 - cosine * cosine)
    return (cosine, sine) + (0.0,) * (COURSE_EMBEDDING_DIMENSION - 2)


QUERY_VECTOR = (1.0,) + (0.0,) * (COURSE_EMBEDDING_DIMENSION - 1)


class FakeQueryProvider:
    """Records the query and returns the fixed unit query vector."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    def embed(self, texts):
        self.calls.append(tuple(texts))
        return tuple(QUERY_VECTOR for _ in texts)


def _add_course(session, group_id: str, *, is_active: bool) -> UUID:
    course_id = uuid.uuid4()
    session.add(
        Course(
            id=course_id,
            group_id=group_id,
            is_active=is_active,
            activity_as_of_academic_year_start=CURRENT_YEAR,
            activity_window_years=WINDOW_YEARS,
        )
    )
    return course_id


def _add_version(
    session,
    *,
    course_id: UUID,
    source_id: str,
    index: int,
    source_hash: str,
    code: str,
    name_fi: str | None,
    name_en: str | None,
    membership_year: int,
    content_fi: str | None = None,
) -> UUID:
    version_id = uuid.uuid4()
    run_id = uuid.uuid4()
    session.add(
        IngestionRun(
            id=run_id,
            status=IngestionRunStatus.COMPLETED,
            raw_root_path=f"data/raw/{index}",
            manifest_path=f"data/raw/{index}/manifest.json",
        )
    )
    snapshot_id = uuid.uuid4()
    session.add(
        SourceSnapshot(
            id=snapshot_id,
            ingestion_run_id=run_id,
            object_type=SourceObjectType.COURSE_UNIT,
            source_object_id=source_id,
            source_group_id=None,
            response_path=f"courses/{index}.json",
            response_item_index=0,
            source_hash=source_hash,
        )
    )
    session.flush()
    session.add(
        CourseVersion(
            id=version_id,
            course_id=course_id,
            sisu_course_unit_id=source_id,
            code=code,
            name_fi=name_fi,
            name_en=name_en,
            credits_min=5,
            credits_max=5,
            official_url=f"https://example.test/{source_id}",
            document_state="ACTIVE",
            source_snapshot_id=snapshot_id,
        )
    )
    session.flush()
    if content_fi is not None:
        session.add(CourseText(course_version_id=version_id, content_fi=content_fi))
    session.add(
        CourseVersionCurriculumPeriod(
            course_version_id=version_id, curriculum_period_id=f"period-{membership_year}"
        )
    )
    return version_id


def _add_chunk(
    session,
    *,
    version_id: UUID,
    source_hash: str,
    field: TeachingTextField,
    language: TeachingTextLanguage,
    chunk_index: int,
    text: str,
    cosine: float,
    origin: TeachingTextOrigin = TeachingTextOrigin.OFFICIAL,
    status: CourseEmbeddingStatus = CourseEmbeddingStatus.COMPLETED,
    configuration_hash: str | None = None,
) -> None:
    is_completed = status is CourseEmbeddingStatus.COMPLETED
    session.add(
        CourseEmbeddingChunk(
            course_version_id=version_id,
            field=field,
            language=language,
            chunk_index=chunk_index,
            text_origin=origin,
            text=text,
            representative_source_hash=source_hash,
            effective_text_hash="d" * 64,
            source_text_hash="d" * 64,
            chunk_text_hash="e" * 64,
            embedding_model="BAAI/bge-m3",
            embedding_artifact_sha256="a" * 64,
            embedding_configuration_hash=(
                configuration_hash or embedding_configuration_sha256(embedding_settings())
            ),
            translation_method=(
                TranslationMethod.MANUAL if origin is TeachingTextOrigin.DERIVED else None
            ),
            translation_generated_at=(
                GENERATED_AT if origin is TeachingTextOrigin.DERIVED else None
            ),
            status=status,
            embedding=(list(cosine_vector(cosine)) if is_completed else None),
        )
    )


def _seed_semantic_courses(database: tuple[Engine, object]) -> dict[str, UUID]:
    """Seed the active/inactive, multi-chunk, incompatible, pending, and sub-threshold rows."""
    _, factory = database
    result: dict[str, UUID] = {}
    with session_scope(factory) as session:
        session.add(CurriculumPeriod(id="period-2026", academic_year_start=CURRENT_YEAR))
        session.add(CurriculumPeriod(id="period-2020", academic_year_start=2020))
        session.flush()

        course_a = _add_course(session, "group-a", is_active=True)
        version_a = _add_version(
            session,
            course_id=course_a,
            source_id="source-a",
            index=1,
            source_hash="1" * 64,
            code="A.1",
            name_fi="Kurssi A",
            name_en=None,
            membership_year=2026,
            content_fi="Sisalto A",
        )
        _add_chunk(
            session,
            version_id=version_a,
            source_hash="1" * 64,
            field=TeachingTextField.CONTENT,
            language=TeachingTextLanguage.FI,
            chunk_index=0,
            text="chunk a0",
            cosine=0.6,
        )
        _add_chunk(
            session,
            version_id=version_a,
            source_hash="1" * 64,
            field=TeachingTextField.CONTENT,
            language=TeachingTextLanguage.EN,
            chunk_index=1,
            text="chunk a1",
            cosine=0.8,
        )

        course_b = _add_course(session, "group-b", is_active=False)
        version_b = _add_version(
            session,
            course_id=course_b,
            source_id="source-b",
            index=2,
            source_hash="2" * 64,
            code="B.1",
            name_fi=None,
            name_en="Course B",
            membership_year=2020,
        )
        _add_chunk(
            session,
            version_id=version_b,
            source_hash="2" * 64,
            field=TeachingTextField.CONTENT,
            language=TeachingTextLanguage.EN,
            chunk_index=0,
            text="chunk b0",
            cosine=0.9,
        )

        course_c = _add_course(session, "group-c", is_active=True)
        version_c = _add_version(
            session,
            course_id=course_c,
            source_id="source-c",
            index=3,
            source_hash="3" * 64,
            code="C.1",
            name_fi=None,
            name_en="Course C",
            membership_year=2026,
        )
        _add_chunk(
            session,
            version_id=version_c,
            source_hash="3" * 64,
            field=TeachingTextField.CONTENT,
            language=TeachingTextLanguage.EN,
            chunk_index=0,
            text="chunk c0",
            cosine=0.95,
            configuration_hash=OTHER_CONFIGURATION_HASH,
        )

        course_d = _add_course(session, "group-d", is_active=True)
        version_d = _add_version(
            session,
            course_id=course_d,
            source_id="source-d",
            index=4,
            source_hash="4" * 64,
            code="D.1",
            name_fi=None,
            name_en="Course D",
            membership_year=2026,
        )
        _add_chunk(
            session,
            version_id=version_d,
            source_hash="4" * 64,
            field=TeachingTextField.CONTENT,
            language=TeachingTextLanguage.EN,
            chunk_index=0,
            text="chunk d0",
            cosine=0.99,
            status=CourseEmbeddingStatus.PENDING,
        )

        course_e = _add_course(session, "group-e", is_active=True)
        version_e = _add_version(
            session,
            course_id=course_e,
            source_id="source-e",
            index=5,
            source_hash="5" * 64,
            code="E.1",
            name_fi=None,
            name_en="Course E",
            membership_year=2026,
        )
        _add_chunk(
            session,
            version_id=version_e,
            source_hash="5" * 64,
            field=TeachingTextField.CONTENT,
            language=TeachingTextLanguage.EN,
            chunk_index=0,
            text="chunk e0",
            cosine=0.4,
        )
        result.update(
            group_a_version=version_a,
            group_b_version=version_b,
            group_c_version=version_c,
            group_d_version=version_d,
            group_e_version=version_e,
        )
    return result


def _seed_derived_and_obsolete(database: tuple[Engine, object]) -> dict[str, UUID]:
    """Seed one canonical course whose current representative has a derived-only English chunk."""
    _, factory = database
    result: dict[str, UUID] = {}
    with session_scope(factory) as session:
        session.add(CurriculumPeriod(id="period-2026", academic_year_start=CURRENT_YEAR))
        session.add(CurriculumPeriod(id="period-2020", academic_year_start=2020))
        session.flush()

        course = _add_course(session, "group-current", is_active=True)
        current = _add_version(
            session,
            course_id=course,
            source_id="source-current",
            index=6,
            source_hash="1" * 64,
            code="CUR.1",
            name_fi="Nykyinen kurssi",
            name_en=None,
            membership_year=2026,
            content_fi="Sisalto",
        )
        _add_chunk(
            session,
            version_id=current,
            source_hash="1" * 64,
            field=TeachingTextField.CONTENT,
            language=TeachingTextLanguage.EN,
            chunk_index=0,
            text="Derived english chunk",
            cosine=0.6,
            origin=TeachingTextOrigin.DERIVED,
        )
        # A current-version chunk whose stored representative source hash is stale must never be
        # paired with the current summary, exactly like a chunk on an obsolete version.
        _add_chunk(
            session,
            version_id=current,
            source_hash="3" * 64,
            field=TeachingTextField.CONTENT,
            language=TeachingTextLanguage.EN,
            chunk_index=1,
            text="Stale source hash chunk",
            cosine=0.99,
        )
        obsolete = _add_version(
            session,
            course_id=course,
            source_id="source-obsolete",
            index=7,
            source_hash="2" * 64,
            code="OBS.1",
            name_fi=None,
            name_en="Obsolete english name",
            membership_year=2020,
        )
        _add_chunk(
            session,
            version_id=obsolete,
            source_hash="2" * 64,
            field=TeachingTextField.CONTENT,
            language=TeachingTextLanguage.EN,
            chunk_index=0,
            text="Obsolete high score",
            cosine=0.95,
        )
        result.update(current=current, obsolete=obsolete)
    return result
