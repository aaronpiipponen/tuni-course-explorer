"""Opt-in PostgreSQL proofs for the inference exact course-to-course candidate read."""

from __future__ import annotations

import math
import uuid
from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy import Engine, func, select

from course_explorer.constants import COURSE_EMBEDDING_DIMENSION
from course_explorer.db.models import (
    Course,
    CourseEmbeddingChunk,
    CourseText,
    CourseVersion,
    CourseVersionCurriculumPeriod,
    CurriculumPeriod,
    InferenceModelAttempt,
    InferencePipelineRun,
    InferenceTargetWork,
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
from course_explorer.inference.context import InferenceCourseEmbeddingIdentity
from course_explorer.inference.context_repository import InferenceCandidateRepository
from course_explorer.inference.failures import TargetSelectionError
from tests.inference._fixture_support import embedding_settings

pytestmark = [
    pytest.mark.integration,
]

GENERATED_AT = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
OTHER_CONFIGURATION_HASH = "f" * 64
CURRENT_YEAR = 2026
WINDOW_YEARS = 3


def cosine_vector(cosine: float) -> tuple[float, ...]:
    """Return one 1024-dimensional unit vector with the requested exact cosine to the query."""
    sine = math.sqrt(1.0 - cosine * cosine)
    return (cosine, sine) + (0.0,) * (COURSE_EMBEDDING_DIMENSION - 2)


QUERY_VECTOR = (1.0,) + (0.0,) * (COURSE_EMBEDDING_DIMENSION - 1)


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
    membership_year: int,
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
            name_fi="Kurssi",
            name_en=None,
            credits_min=5,
            credits_max=5,
            official_url=f"https://example.test/{source_id}",
            document_state="ACTIVE",
            source_snapshot_id=snapshot_id,
        )
    )
    session.flush()
    session.add(CourseText(course_version_id=version_id, content_fi="Sisalto"))
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
    cosine: float,
    origin: TeachingTextOrigin = TeachingTextOrigin.OFFICIAL,
    status: CourseEmbeddingStatus = CourseEmbeddingStatus.COMPLETED,
    configuration_hash: str | None = None,
    chunk_text_hash: str = "e" * 64,
) -> None:
    is_completed = status is CourseEmbeddingStatus.COMPLETED
    session.add(
        CourseEmbeddingChunk(
            course_version_id=version_id,
            field=field,
            language=language,
            chunk_index=chunk_index,
            text_origin=origin,
            text=f"chunk {chunk_index}",
            representative_source_hash=source_hash,
            effective_text_hash="d" * 64,
            source_text_hash="d" * 64,
            chunk_text_hash=chunk_text_hash,
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


def _seed_candidates(
    database: tuple[Engine, object],
) -> dict[str, InferenceCourseEmbeddingIdentity]:
    """Seed active/inactive versions, multi-chunk candidates, and active/inactive sources."""
    _, factory = database
    result: dict[str, InferenceCourseEmbeddingIdentity] = {}
    with session_scope(factory) as session:
        session.add(CurriculumPeriod(id="period-2026", academic_year_start=CURRENT_YEAR))
        session.add(CurriculumPeriod(id="period-2020", academic_year_start=2020))
        session.flush()

        target_course = _add_course(session, "group-target", is_active=True)
        target_version = _add_version(
            session,
            course_id=target_course,
            source_id="source-target",
            index=1,
            source_hash="1" * 64,
            code="TGT.1",
            membership_year=2026,
        )
        # Target chunks are the query vector itself, so each candidate score is exactly its
        # designed cosine to the target.
        _add_chunk(
            session,
            version_id=target_version,
            source_hash="1" * 64,
            field=TeachingTextField.CONTENT,
            language=TeachingTextLanguage.FI,
            chunk_index=0,
            cosine=1.0,
            chunk_text_hash="1" * 64,
        )
        _add_chunk(
            session,
            version_id=target_version,
            source_hash="1" * 64,
            field=TeachingTextField.OUTCOMES,
            language=TeachingTextLanguage.EN,
            chunk_index=0,
            cosine=1.0,
            chunk_text_hash="2" * 64,
        )
        result["target"] = InferenceCourseEmbeddingIdentity(
            group_id="group-target",
            sisu_course_unit_id="source-target",
            representative_source_sha256="1" * 64,
        )

        # Active candidate with two chunks: best pair must win.
        candidate_a = _add_course(session, "group-a", is_active=True)
        version_a = _add_version(
            session,
            course_id=candidate_a,
            source_id="source-a",
            index=2,
            source_hash="2" * 64,
            code="AAA.1",
            membership_year=2026,
        )
        _add_chunk(
            session,
            version_id=version_a,
            source_hash="2" * 64,
            field=TeachingTextField.CONTENT,
            language=TeachingTextLanguage.FI,
            chunk_index=0,
            cosine=0.6,
            chunk_text_hash="3" * 64,
        )
        _add_chunk(
            session,
            version_id=version_a,
            source_hash="2" * 64,
            field=TeachingTextField.CONTENT,
            language=TeachingTextLanguage.FI,
            chunk_index=1,
            cosine=0.9,
            chunk_text_hash="4" * 64,
        )
        result["a"] = InferenceCourseEmbeddingIdentity(
            group_id="group-a",
            sisu_course_unit_id="source-a",
            representative_source_sha256="2" * 64,
        )

        # An inactive candidate is eligible.
        candidate_b = _add_course(session, "group-b", is_active=False)
        version_b = _add_version(
            session,
            course_id=candidate_b,
            source_id="source-b",
            index=3,
            source_hash="3" * 64,
            code="BBB.1",
            membership_year=2020,
        )
        _add_chunk(
            session,
            version_id=version_b,
            source_hash="3" * 64,
            field=TeachingTextField.CONTENT,
            language=TeachingTextLanguage.EN,
            chunk_index=0,
            cosine=0.95,
            origin=TeachingTextOrigin.DERIVED,
            chunk_text_hash="5" * 64,
        )
        result["b"] = InferenceCourseEmbeddingIdentity(
            group_id="group-b",
            sisu_course_unit_id="source-b",
            representative_source_sha256="3" * 64,
        )

        # Incompatible configuration and pending rows are unmeasurable candidates.
        candidate_c = _add_course(session, "group-c", is_active=True)
        version_c = _add_version(
            session,
            course_id=candidate_c,
            source_id="source-c",
            index=4,
            source_hash="4" * 64,
            code="CCC.1",
            membership_year=2026,
        )
        _add_chunk(
            session,
            version_id=version_c,
            source_hash="4" * 64,
            field=TeachingTextField.CONTENT,
            language=TeachingTextLanguage.EN,
            chunk_index=0,
            cosine=0.99,
            configuration_hash=OTHER_CONFIGURATION_HASH,
        )
        _add_chunk(
            session,
            version_id=version_c,
            source_hash="4" * 64,
            field=TeachingTextField.CONTENT,
            language=TeachingTextLanguage.EN,
            chunk_index=1,
            cosine=0.98,
            status=CourseEmbeddingStatus.PENDING,
        )
        result["c"] = InferenceCourseEmbeddingIdentity(
            group_id="group-c",
            sisu_course_unit_id="source-c",
            representative_source_sha256="4" * 64,
        )

        # An inactive version of the active candidate must never compete with its active version.
        obsolete_version = _add_version(
            session,
            course_id=candidate_a,
            source_id="source-a-obsolete",
            index=5,
            source_hash="9" * 64,
            code="AAA.0",
            membership_year=2020,
        )
        _add_chunk(
            session,
            version_id=obsolete_version,
            source_hash="9" * 64,
            field=TeachingTextField.CONTENT,
            language=TeachingTextLanguage.EN,
            chunk_index=0,
            cosine=0.99,
        )

        # Score tie for deterministic group-id ordering.
        candidate_d = _add_course(session, "group-d", is_active=True)
        version_d = _add_version(
            session,
            course_id=candidate_d,
            source_id="source-d",
            index=6,
            source_hash="6" * 64,
            code="DDD.1",
            membership_year=2026,
        )
        _add_chunk(
            session,
            version_id=version_d,
            source_hash="6" * 64,
            field=TeachingTextField.CONTENT,
            language=TeachingTextLanguage.EN,
            chunk_index=0,
            cosine=0.9,
            chunk_text_hash="6" * 64,
        )
        result["d"] = InferenceCourseEmbeddingIdentity(
            group_id="group-d",
            sisu_course_unit_id="source-d",
            representative_source_sha256="6" * 64,
        )
    return result


def test_exact_candidate_ranking_uses_best_current_compatible_chunk_and_includes_inactive_sources(
    database: tuple[Engine, object],
) -> None:
    """Best-pair scores, deterministic ties, inactive eligibility, and target exclusion all hold."""
    identities = _seed_candidates(database)
    _, factory = database
    repository = InferenceCandidateRepository(factory)
    configuration_hash = embedding_configuration_sha256(embedding_settings())

    ranked = repository.rank_candidates(
        identities["target"],
        represented_courses=(
            identities["target"],
            identities["a"],
            identities["b"],
            identities["c"],
            identities["d"],
        ),
        embedding_configuration_hash=configuration_hash,
    )
    assert [entry.match.course.group_id for entry in ranked] == [
        "group-b",
        "group-a",
        "group-d",
    ]
    assert [entry.rank for entry in ranked] == [1, 2, 3]
    by_group = {entry.match.course.group_id: entry for entry in ranked}
    # 0.95 from the inactive derived candidate, not excluded.
    assert by_group["group-b"].match.score == pytest.approx(0.95)
    assert by_group["group-b"].match.candidate_chunk.text_origin is TeachingTextOrigin.DERIVED
    # Best pair 0.9 from the second chunk, not the 0.6 first chunk nor the inactive 0.99 row.
    assert by_group["group-a"].match.score == pytest.approx(0.9)
    assert by_group["group-a"].match.candidate_chunk.chunk_index == 1
    assert by_group["group-a"].match.candidate_chunk.chunk_text_sha256 == "4" * 64
    assert by_group["group-a"].match.course.sisu_course_unit_id == "source-a"
    assert by_group["group-a"].match.course.representative_source_sha256 == "2" * 64
    # Tie at 0.9 is broken by candidate group id.
    assert by_group["group-d"].match.score == pytest.approx(0.9)
    # group-c has no compatible completed chunk and is therefore omitted, not fabricated.
    assert "group-c" not in by_group
    # The target is never its own candidate.
    assert "group-target" not in by_group
    # No inference evidence or final-store writes occurred.
    with factory() as session:
        for table in (InferencePipelineRun, InferenceTargetWork, InferenceModelAttempt):
            assert session.scalar(select(func.count()).select_from(table)) == 0

    represented = (
        identities["target"],
        identities["a"],
        identities["b"],
        identities["c"],
        identities["d"],
    )

    def field_view(field: TeachingTextField) -> tuple:
        return repository.rank_candidates(
            identities["target"],
            represented_courses=represented,
            embedding_configuration_hash=configuration_hash,
            target_field=field,
        )

    # The exact target has no NAME chunk, so its NAME field view is empty, not fabricated.
    assert field_view(TeachingTextField.NAME) == ()
    # Add a target NAME chunk whose unit vector differs from the CONTENT/OUTCOMES query vector, so
    # its field view ranks candidates by NAME similarity while the unfiltered best-pair ranking
    # (whose best pairs are at 0.9+).
    with session_scope(factory) as session:
        target_version_id = session.scalar(
            select(CourseVersion.id)
            .join(Course, Course.id == CourseVersion.course_id)
            .where(Course.group_id == "group-target")
        )
        assert target_version_id is not None
        _add_chunk(
            session,
            version_id=target_version_id,
            source_hash="1" * 64,
            field=TeachingTextField.NAME,
            language=TeachingTextLanguage.FI,
            chunk_index=0,
            cosine=0.5,
            chunk_text_hash="a" * 64,
        )
    name_view = field_view(TeachingTextField.NAME)
    name_by_group = {entry.match.course.group_id: entry for entry in name_view}
    # The field view is restricted to the target NAME chunk while candidate chunks are free.
    for entry in name_view:
        assert entry.match.target_chunk.field is TeachingTextField.NAME
        assert isinstance(entry.match.candidate_chunk.field, TeachingTextField)
    # Scores are the NAME-view cosine, distinct from the unfiltered best-pair scores.
    assert name_by_group["group-b"].match.score != by_group["group-b"].match.score
    assert [entry.rank for entry in name_view] == [1, 2, 3]
    assert [entry.match.course.group_id for entry in name_view] == [
        "group-a",
        "group-d",
        "group-b",
    ]
    # A field-view call never mutates the all-field path.
    unfiltered_after = repository.rank_candidates(
        identities["target"],
        represented_courses=represented,
        embedding_configuration_hash=configuration_hash,
    )
    # The unfiltered ranking never restricts the target chunk to a single field. The added NAME
    # chunk participates, so the all-field best-pair search spans more than one field.
    assert len({entry.match.target_chunk.field for entry in unfiltered_after}) > 1


def test_candidate_ranking_rejects_stale_identity_missing_target_and_bad_scope_without_search_writes(
    database: tuple[Engine, object],
) -> None:
    """Identity, target, hash, and scope validation fail clearly before any result is returned."""
    identities = _seed_candidates(database)
    _, factory = database
    repository = InferenceCandidateRepository(factory)
    configuration_hash = embedding_configuration_sha256(embedding_settings())

    represented = (identities["target"], identities["a"])
    with pytest.raises(ValueError):
        repository.rank_candidates(
            identities["b"],
            represented_courses=represented,
            embedding_configuration_hash=configuration_hash,
        )
    # A target with no compatible chunk fails before any ranking query.
    unknown = InferenceCourseEmbeddingIdentity(
        group_id="group-c",
        sisu_course_unit_id="source-c",
        representative_source_sha256="4" * 64,
    )
    with pytest.raises(TargetSelectionError) as missing_chunk:
        repository.rank_candidates(
            unknown,
            represented_courses=(unknown, identities["target"]),
            embedding_configuration_hash=configuration_hash,
        )
    assert missing_chunk.value.reason == "missing_target_chunks"
    # The exact target with only an incompatible-configuration chunk is unmeasurable.
    incompatible = InferenceCourseEmbeddingIdentity(
        group_id="group-target",
        sisu_course_unit_id="source-target",
        representative_source_sha256="1" * 64,
    )
    ranked = repository.rank_candidates(
        incompatible,
        represented_courses=(incompatible, identities["c"]),
        embedding_configuration_hash=configuration_hash,
    )
    assert ranked == ()


def test_embedding_state_digest_tracks_scoped_current_chunk_changes(
    database: tuple[Engine, object],
) -> None:
    """The embedding-state digest is scoped, order-stable and lifecycle-inclusive."""
    identities = _seed_candidates(database)
    _, factory = database
    repository = InferenceCandidateRepository(factory)
    configuration_hash = embedding_configuration_sha256(embedding_settings())
    represented = (identities["target"], identities["a"], identities["b"])
    digest = repository.embedding_state_sha256(
        represented, embedding_configuration_hash=configuration_hash
    )
    assert len(digest) == 64
    # Reordering the supplied pairs does not change the digest.
    assert (
        repository.embedding_state_sha256(
            tuple(reversed(represented)), embedding_configuration_hash=configuration_hash
        )
        == digest
    )
    # A different embedding configuration or empty scope yields a different real digest.
    assert (
        repository.embedding_state_sha256(
            represented, embedding_configuration_hash=OTHER_CONFIGURATION_HASH
        )
        != digest
    )
    assert (
        repository.embedding_state_sha256((), embedding_configuration_hash=configuration_hash)
        != digest
    )

    with factory() as session:
        chunk_ids = session.scalars(
            select(CourseEmbeddingChunk.id)
            .join(CourseVersion, CourseVersion.id == CourseEmbeddingChunk.course_version_id)
            .join(Course, Course.id == CourseVersion.course_id)
            .where(
                Course.group_id == "group-a",
                CourseVersion.sisu_course_unit_id == "source-a",
            )
            .order_by(CourseEmbeddingChunk.chunk_index)
        ).all()
        assert len(chunk_ids) == 2

    # A status/vector-presence change on a supplied version changes the digest.
    with session_scope(factory) as session:
        row = session.get(CourseEmbeddingChunk, chunk_ids[0])
        assert row is not None
        row.status = CourseEmbeddingStatus.PENDING
        row.embedding = None
    changed_status = repository.embedding_state_sha256(
        represented, embedding_configuration_hash=configuration_hash
    )
    assert changed_status != digest

    # A stale-source chunk on the supplied version participates (no source-hash filter).
    with session_scope(factory) as session:
        row = session.get(CourseEmbeddingChunk, chunk_ids[0])
        assert row is not None
        row.status = CourseEmbeddingStatus.COMPLETED
        row.embedding = list(cosine_vector(0.6))
        row.representative_source_hash = "9" * 64
    after_stale = repository.embedding_state_sha256(
        represented, embedding_configuration_hash=configuration_hash
    )
    assert after_stale != digest

    # A different source version of the same course is excluded from the supplied-pair scope.
    with session_scope(factory) as session:
        obsolete_version_id = session.scalar(
            select(CourseVersion.id)
            .join(Course, Course.id == CourseVersion.course_id)
            .where(
                Course.group_id == "group-a",
                CourseVersion.sisu_course_unit_id == "source-a-obsolete",
            )
        )
        assert obsolete_version_id is not None
        session.add(
            CourseEmbeddingChunk(
                course_version_id=obsolete_version_id,
                field=TeachingTextField.CONTENT,
                language=TeachingTextLanguage.EN,
                chunk_index=7,
                text_origin=TeachingTextOrigin.OFFICIAL,
                text="obsolete",
                representative_source_hash="9" * 64,
                effective_text_hash="d" * 64,
                source_text_hash="d" * 64,
                chunk_text_hash="d" * 64,
                embedding_model="BAAI/bge-m3",
                embedding_artifact_sha256="a" * 64,
                embedding_configuration_hash=configuration_hash,
                status=CourseEmbeddingStatus.COMPLETED,
                embedding=list(cosine_vector(0.1)),
            )
        )
    assert (
        repository.embedding_state_sha256(
            represented, embedding_configuration_hash=configuration_hash
        )
        == after_stale
    )
