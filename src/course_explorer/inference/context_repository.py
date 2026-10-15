"""Exact inference-owned course-to-course read over current compatible teaching chunks.

This is the sole inference reader for `course_embedding_chunks`. It computes exact best-chunk
cosine scores between one target's completed chunks and every supplied current represented
course's completed chunks, chooses one deterministic best chunk pair per candidate, and ranks the
complete measurable non-target candidate set by canonical score descending then candidate group id.
It uses only stored vectors: it never embeds text, never accepts official labels, never touches the
user-search path, and never adds a vector store, ANN approximation, or SQL result cap. The
complete ranking is bounded to one target. Callers retain only the configured top-K provenance.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import Text, and_, column, func, select, tuple_, values
from sqlalchemy.orm import Session, aliased, sessionmaker

from course_explorer.db.models import (
    Course,
    CourseEmbeddingChunk,
    CourseVersion,
)
from course_explorer.enums import (
    CourseEmbeddingStatus,
    TeachingTextField,
)
from course_explorer.hashing import canonical_json_sha256
from course_explorer.inference.context import (
    InferenceCandidateMatch,
    InferenceCourseEmbeddingIdentity,
    InferenceMatchedChunk,
    InferenceRankedCandidate,
)
from course_explorer.inference.failures import TargetSelectionError
from course_explorer.validation import require_sha256 as _require_sha256

_REPRESENTED_IDENTITIES_CTE = "represented_current_identities"
# The embedding-state digest reads one bounded pair batch per statement: a single IN list over
# every represented course exceeds PostgreSQL's statement-complexity limit at real catalogue size.
_EMBEDDING_STATE_BATCH_SIZE = 1000


def _require_identity(identity: InferenceCourseEmbeddingIdentity) -> None:
    if not isinstance(identity, InferenceCourseEmbeddingIdentity):
        raise ValueError("represented identities must be InferenceCourseEmbeddingIdentity values")


def _utc_iso(value: datetime | None) -> str | None:
    """Render one aware timestamp as a UTC ISO string, preserving an absent value as None."""
    return None if value is None else value.astimezone(UTC).isoformat()


class InferenceCandidateRepository:
    """Rank every measurable non-target candidate for one exact target by cosine similarity."""

    def __init__(self, factory: sessionmaker[Session]) -> None:
        self._factory = factory

    def rank_candidates(
        self,
        target: InferenceCourseEmbeddingIdentity,
        *,
        represented_courses: Sequence[InferenceCourseEmbeddingIdentity],
        embedding_configuration_hash: str,
        target_field: TeachingTextField | None = None,
    ) -> tuple[InferenceRankedCandidate, ...]:
        """Return the complete score-descending best-pair ranking of measurable candidates.

        ``represented_courses`` is the caller's exact current represented-course universe. The
        target identity must belong to it, all identities must be unique, and inactive candidates
        remain eligible. Candidates without a completed, non-null vector under the requested
        configuration hash are unmeasurable and are omitted here rather than fabricated into the
        ranking.

        ``target_field`` is an optional target-chunk field view: when supplied, the target side of
        the exact query is restricted to completed chunks of that field while every candidate
        chunk is unrestricted. ``None`` selects the identical all-field path, so the
        all-field ranking behavior is preserved. The target identity
        is validated unfiltered, so a target without a compatible chunk for one field yields an
        empty field view rather than a fabricated match.
        """
        _require_sha256(embedding_configuration_hash, "embedding_configuration_hash")
        if not isinstance(target, InferenceCourseEmbeddingIdentity):
            raise ValueError("target must be an InferenceCourseEmbeddingIdentity value")
        if target_field is not None and not isinstance(target_field, TeachingTextField):
            raise ValueError("target_field must be a TeachingTextField value or None")
        identities = tuple(represented_courses)
        for identity in identities:
            _require_identity(identity)
        keys = tuple(
            (identity.group_id, identity.sisu_course_unit_id, identity.representative_source_sha256)
            for identity in identities
        )
        if len(keys) != len(set(keys)):
            raise ValueError("represented course identities must be unique")
        if target not in identities:
            raise ValueError("the target identity must be in the supplied represented courses")
        self._require_compatible_target_chunk(target, embedding_configuration_hash)

        candidate_rows = tuple(
            (
                identity.group_id,
                identity.sisu_course_unit_id,
                identity.representative_source_sha256,
            )
            for identity in identities
            if identity.group_id != target.group_id
        )
        with self._factory() as session:
            rows = (
                ()
                if not candidate_rows
                else tuple(
                    session.execute(
                        self._ranked_statement(
                            target,
                            candidate_rows,
                            embedding_configuration_hash,
                            target_field=target_field,
                        )
                    )
                )
            )
        return tuple(
            InferenceRankedCandidate(
                rank=rank,
                match=InferenceCandidateMatch(
                    course=InferenceCourseEmbeddingIdentity(
                        group_id=candidate_group_id,
                        sisu_course_unit_id=candidate_source_id,
                        representative_source_sha256=candidate_source_hash,
                    ),
                    score=float(score),
                    target_chunk=InferenceMatchedChunk(
                        field=target_field,
                        language=target_language,
                        chunk_index=target_chunk_index,
                        text_origin=target_origin,
                        chunk_text_sha256=target_chunk_text_hash,
                    ),
                    candidate_chunk=InferenceMatchedChunk(
                        field=candidate_field,
                        language=candidate_language,
                        chunk_index=candidate_chunk_index,
                        text_origin=candidate_origin,
                        chunk_text_sha256=candidate_chunk_text_hash,
                    ),
                ),
            )
            for (
                candidate_group_id,
                candidate_source_id,
                candidate_source_hash,
                score,
                target_field,
                target_language,
                target_chunk_index,
                target_origin,
                target_chunk_text_hash,
                candidate_field,
                candidate_language,
                candidate_chunk_index,
                candidate_origin,
                candidate_chunk_text_hash,
                rank,
            ) in rows
        )

    def embedding_state_sha256(
        self,
        represented_courses: Sequence[InferenceCourseEmbeddingIdentity],
        *,
        embedding_configuration_hash: str,
    ) -> str:
        """Hash the current stored embedding state over the supplied exact course pairs.

        One scoped projection reads only identity/provenance/status columns for chunks on the
        supplied exact ``(Course.group_id, CourseVersion.sisu_course_unit_id)`` pairs under the
        requested embedding configuration hash. It reads every chunk source
        hash, lifecycle, or vector presence, so a stale-source, pending, or failed chunk on a
        supplied current version participates and changes the digest. A different source
        version, a course outside the supplied pairs, or a different embedding configuration is
        excluded. Never vectors, text, or ORM entities are read.
        """
        _require_sha256(embedding_configuration_hash, "embedding_configuration_hash")
        identities = tuple(represented_courses)
        for identity in identities:
            _require_identity(identity)
        keys = tuple((identity.group_id, identity.sisu_course_unit_id) for identity in identities)
        if len(keys) != len(set(keys)):
            raise ValueError("represented course identities must be unique")
        records: list[dict[str, object]] = []
        if keys:
            pairs = sorted(set(keys))
            for start in range(0, len(pairs), _EMBEDDING_STATE_BATCH_SIZE):
                batch = pairs[start : start + _EMBEDDING_STATE_BATCH_SIZE]
                with self._factory() as session:
                    rows = tuple(
                        session.execute(
                            select(
                                Course.group_id,
                                CourseVersion.sisu_course_unit_id,
                                CourseEmbeddingChunk.id,
                                CourseEmbeddingChunk.field,
                                CourseEmbeddingChunk.language,
                                CourseEmbeddingChunk.chunk_index,
                                CourseEmbeddingChunk.representative_source_hash,
                                CourseEmbeddingChunk.effective_text_hash,
                                CourseEmbeddingChunk.source_text_hash,
                                CourseEmbeddingChunk.chunk_text_hash,
                                CourseEmbeddingChunk.text_origin,
                                CourseEmbeddingChunk.translation_method,
                                CourseEmbeddingChunk.translation_model,
                                CourseEmbeddingChunk.translation_generated_at,
                                CourseEmbeddingChunk.embedding_model,
                                CourseEmbeddingChunk.embedding_artifact_sha256,
                                CourseEmbeddingChunk.embedding_configuration_hash,
                                CourseEmbeddingChunk.status,
                                CourseEmbeddingChunk.embedding.is_not(None).label("vector_present"),
                                CourseEmbeddingChunk.updated_at,
                            )
                            .join(
                                CourseVersion,
                                CourseVersion.id == CourseEmbeddingChunk.course_version_id,
                            )
                            .join(Course, Course.id == CourseVersion.course_id)
                            .where(
                                tuple_(Course.group_id, CourseVersion.sisu_course_unit_id).in_(
                                    batch
                                ),
                                CourseEmbeddingChunk.embedding_configuration_hash
                                == embedding_configuration_hash,
                            )
                        )
                    )
                records.extend(
                    [
                        {
                            "group_id": row.group_id,
                            "sisu_course_unit_id": row.sisu_course_unit_id,
                            "id": str(row.id),
                            "field": row.field.value,
                            "language": row.language.value,
                            "chunk_index": row.chunk_index,
                            "representative_source_hash": row.representative_source_hash,
                            "effective_text_hash": row.effective_text_hash,
                            "source_text_hash": row.source_text_hash,
                            "chunk_text_hash": row.chunk_text_hash,
                            "text_origin": row.text_origin.value,
                            "translation_method": (
                                None
                                if row.translation_method is None
                                else row.translation_method.value
                            ),
                            "translation_model": row.translation_model,
                            "translation_generated_at": _utc_iso(row.translation_generated_at),
                            "embedding_model": row.embedding_model,
                            "embedding_artifact_sha256": row.embedding_artifact_sha256,
                            "embedding_configuration_hash": row.embedding_configuration_hash,
                            "status": row.status.value,
                            "vector_present": bool(row.vector_present),
                            "updated_at": _utc_iso(row.updated_at),
                        }
                        for row in rows
                    ]
                )
        records.sort(
            key=lambda record: (
                record["group_id"],
                record["sisu_course_unit_id"],
                record["field"],
                record["language"],
                record["chunk_index"],
                record["id"],
            )
        )
        return canonical_json_sha256(
            {
                "embedding_configuration_hash": embedding_configuration_hash,
                "chunks": records,
            }
        )

    def _require_compatible_target_chunk(
        self,
        target: InferenceCourseEmbeddingIdentity,
        embedding_configuration_hash: str,
    ) -> None:
        """Fail clearly when the exact target has no completed compatible chunk."""
        with self._factory() as session:
            count = session.scalar(
                select(func.count())
                .select_from(CourseEmbeddingChunk)
                .join(CourseVersion, CourseVersion.id == CourseEmbeddingChunk.course_version_id)
                .join(Course, Course.id == CourseVersion.course_id)
                .where(
                    Course.group_id == target.group_id,
                    CourseVersion.sisu_course_unit_id == target.sisu_course_unit_id,
                    CourseEmbeddingChunk.representative_source_hash
                    == target.representative_source_sha256,
                    CourseEmbeddingChunk.status == CourseEmbeddingStatus.COMPLETED,
                    CourseEmbeddingChunk.embedding.is_not(None),
                    CourseEmbeddingChunk.embedding_configuration_hash
                    == embedding_configuration_hash,
                )
            )
        if not count:
            raise TargetSelectionError("missing_target_chunks")

    @staticmethod
    def _ranked_statement(
        target: InferenceCourseEmbeddingIdentity,
        candidate_rows: tuple[tuple[str, str, str], ...],
        embedding_configuration_hash: str,
        *,
        target_field: TeachingTextField | None = None,
    ):
        """Build the exact best-pair-then-ranked statement without loading vector/text columns."""
        identities = values(
            column("group_id", Text),
            column("sisu_course_unit_id", Text),
            column("representative_source_hash", Text),
            name=_REPRESENTED_IDENTITIES_CTE,
        ).data(list(candidate_rows))
        target_course = aliased(Course, name="target_course")
        target_version = aliased(CourseVersion, name="target_version")
        target_chunk = aliased(CourseEmbeddingChunk, name="target_chunk")
        candidate_course = aliased(Course, name="candidate_course")
        candidate_version = aliased(CourseVersion, name="candidate_version")
        candidate_chunk = aliased(CourseEmbeddingChunk, name="candidate_chunk")
        distance = target_chunk.embedding.cosine_distance(candidate_chunk.embedding)
        target_chunk_conditions = [
            target_chunk.course_version_id == target_version.id,
            target_chunk.representative_source_hash == target.representative_source_sha256,
            target_chunk.status == CourseEmbeddingStatus.COMPLETED,
            target_chunk.embedding.is_not(None),
            target_chunk.embedding_configuration_hash == embedding_configuration_hash,
        ]
        if target_field is not None:
            target_chunk_conditions.append(target_chunk.field == target_field)
        best_pairs = (
            select(
                candidate_course.group_id.label("candidate_group_id"),
                candidate_version.sisu_course_unit_id.label("candidate_source_id"),
                candidate_chunk.representative_source_hash.label("candidate_source_hash"),
                (1 - distance).label("score"),
                target_chunk.field.label("target_field"),
                target_chunk.language.label("target_language"),
                target_chunk.chunk_index.label("target_chunk_index"),
                target_chunk.text_origin.label("target_origin"),
                target_chunk.chunk_text_hash.label("target_chunk_text_hash"),
                candidate_chunk.field.label("candidate_field"),
                candidate_chunk.language.label("candidate_language"),
                candidate_chunk.chunk_index.label("candidate_chunk_index"),
                candidate_chunk.text_origin.label("candidate_origin"),
                candidate_chunk.chunk_text_hash.label("candidate_chunk_text_hash"),
                func.row_number()
                .over(
                    partition_by=[
                        candidate_course.group_id,
                        candidate_version.sisu_course_unit_id,
                        candidate_chunk.representative_source_hash,
                    ],
                    order_by=[
                        distance,
                        target_chunk.field,
                        target_chunk.language,
                        target_chunk.chunk_index,
                        target_chunk.id,
                        candidate_chunk.field,
                        candidate_chunk.language,
                        candidate_chunk.chunk_index,
                        candidate_chunk.id,
                    ],
                )
                .label("pair_rank"),
            )
            .select_from(identities)
            .join(candidate_course, candidate_course.group_id == identities.c.group_id)
            .join(
                candidate_version,
                and_(
                    candidate_version.course_id == candidate_course.id,
                    candidate_version.sisu_course_unit_id == identities.c.sisu_course_unit_id,
                ),
            )
            .join(
                candidate_chunk,
                and_(
                    candidate_chunk.course_version_id == candidate_version.id,
                    candidate_chunk.representative_source_hash
                    == identities.c.representative_source_hash,
                    candidate_chunk.status == CourseEmbeddingStatus.COMPLETED,
                    candidate_chunk.embedding.is_not(None),
                    candidate_chunk.embedding_configuration_hash == embedding_configuration_hash,
                ),
            )
            .join(target_course, target_course.group_id == target.group_id)
            .join(
                target_version,
                and_(
                    target_version.course_id == target_course.id,
                    target_version.sisu_course_unit_id == target.sisu_course_unit_id,
                ),
            )
            .join(
                target_chunk,
                and_(*target_chunk_conditions),
            )
            .where(candidate_course.id != target_course.id)
            .subquery("best_pairs")
        )
        return (
            select(
                best_pairs.c.candidate_group_id,
                best_pairs.c.candidate_source_id,
                best_pairs.c.candidate_source_hash,
                best_pairs.c.score,
                best_pairs.c.target_field,
                best_pairs.c.target_language,
                best_pairs.c.target_chunk_index,
                best_pairs.c.target_origin,
                best_pairs.c.target_chunk_text_hash,
                best_pairs.c.candidate_field,
                best_pairs.c.candidate_language,
                best_pairs.c.candidate_chunk_index,
                best_pairs.c.candidate_origin,
                best_pairs.c.candidate_chunk_text_hash,
                func.row_number()
                .over(
                    order_by=[
                        best_pairs.c.score.desc(),
                        best_pairs.c.candidate_group_id,
                    ]
                )
                .label("rank"),
            )
            .where(best_pairs.c.pair_rank == 1)
            .order_by(best_pairs.c.score.desc(), best_pairs.c.candidate_group_id)
        )
