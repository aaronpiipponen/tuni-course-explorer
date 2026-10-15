"""Persistence and lifecycle seam for provenance-marked course embedding chunks.

This is the sole writer and reader for `course_embedding_chunks`. It reconciles desired chunk
identity `(course_version_id, field, language, chunk_index)` against persisted rows in one
transaction, inserts pending work, invalidates only changed work, deletes obsolete scoped rows,
and exposes coverage. It never fabricates vectors, keys work by row position, or touches official
and derived source tables outside the effective-text catalogue the generation service hands it.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from datetime import datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy import delete, func, select, tuple_
from sqlalchemy.orm import Session, sessionmaker

from course_explorer.db.models import (
    Course,
    CourseEmbeddingChunk,
    CourseVersion,
)
from course_explorer.db.session import session_scope
from course_explorer.embeddings.generation import (
    CourseEmbeddingChunkInput,
    CourseEmbeddingCoverageCount,
    CourseEmbeddingCoverageReport,
    CourseEmbeddingResult,
    EmbeddingReconciliation,
    PendingCourseEmbeddingChunk,
)
from course_explorer.enums import (
    CourseEmbeddingStatus,
    TeachingTextField,
    TeachingTextLanguage,
    TeachingTextOrigin,
    TranslationMethod,
)

# Readiness checks one bounded identity batch per statement: a single IN list over the whole
# catalogue exceeds the driver's parameter ceiling and PostgreSQL's statement-complexity limit.
_READINESS_BATCH_SIZE = 1000

EmbeddingRowKey = tuple[UUID, TeachingTextField, TeachingTextLanguage, int]


class CourseEmbeddingRepository:
    """Reconcile desired chunks and record their current lifecycle state and vectors."""

    def __init__(self, factory: sessionmaker[Session]) -> None:
        self._factory = factory

    def reconcile(
        self,
        canonical_group_ids: Collection[str],
        chunks: Sequence[CourseEmbeddingChunkInput],
    ) -> EmbeddingReconciliation:
        """Reconcile desired chunks against scoped persisted rows in one transaction."""
        scope = tuple(canonical_group_ids)
        inputs = tuple(chunks)
        _validate_reconciliation_inputs(scope, inputs)

        with session_scope(self._factory) as session:
            course_rows = tuple(
                session.execute(
                    select(Course.group_id, CourseVersion.id, CourseVersion.sisu_course_unit_id)
                    .join(CourseVersion, CourseVersion.course_id == Course.id)
                    .where(Course.group_id.in_(scope))
                )
            )
            groups_to_versions: dict[str, dict[str, UUID]] = {}
            for group_id, version_id, source_id in course_rows:
                groups_to_versions.setdefault(group_id, {})[source_id] = version_id
            missing = set(scope) - set(groups_to_versions)
            if missing:
                raise ValueError(f"canonical group IDs are missing: {sorted(missing)}")
            if not scope:
                return EmbeddingReconciliation(
                    desired_count=0,
                    inserted_count=0,
                    invalidated_count=0,
                    reused_count=0,
                    retry_count=0,
                    deleted_count=0,
                    pending=(),
                )

            scoped_version_ids = tuple(
                version_id
                for versions in groups_to_versions.values()
                for version_id in versions.values()
            )
            existing = {
                (row.course_version_id, row.field, row.language, row.chunk_index): row
                for row in session.scalars(
                    select(CourseEmbeddingChunk).where(
                        CourseEmbeddingChunk.course_version_id.in_(scoped_version_ids)
                    )
                )
            }
            desired = _desired_chunks(inputs, groups_to_versions)

            obsolete = set(existing) - set(desired)
            deleted_count = len(obsolete)
            if obsolete:
                session.execute(
                    delete(CourseEmbeddingChunk).where(
                        CourseEmbeddingChunk.id.in_(tuple(existing[key].id for key in obsolete))
                    )
                )

            (
                inserted_count,
                invalidated_count,
                reused_count,
                retry_count,
                pending_rows,
            ) = _reconcile_desired_rows(session, desired, existing)

            session.flush()
            version_order = {
                version_id: (group_id, source_id)
                for group_id, versions in groups_to_versions.items()
                for source_id, version_id in versions.items()
            }
            pending = tuple(
                PendingCourseEmbeddingChunk(row_id=row.id, text=row.text)
                for row in sorted(
                    pending_rows,
                    key=lambda item: (
                        version_order[item.course_version_id],
                        item.field.value,
                        item.language.value,
                        item.chunk_index,
                    ),
                )
            )
        return EmbeddingReconciliation(
            desired_count=len(desired),
            inserted_count=inserted_count,
            invalidated_count=invalidated_count,
            reused_count=reused_count,
            retry_count=retry_count,
            deleted_count=deleted_count,
            pending=pending,
        )

    def begin_attempt(self, row_ids: Sequence[UUID]) -> None:
        """Reset exact pending rows to pending with no vector before their provider call."""
        ids = _unique_ids(row_ids)
        with session_scope(self._factory) as session:
            rows = _load_rows(session, ids)
            for row in rows:
                row.status = CourseEmbeddingStatus.PENDING
                row.embedding = None

    def complete(self, results: Sequence[CourseEmbeddingResult]) -> None:
        """Store exact completed vectors for the matching rows."""
        items = tuple(results)
        ids = _unique_ids(tuple(item.row_id for item in items))
        with session_scope(self._factory) as session:
            rows = {row.id: row for row in _load_rows(session, ids)}
            for item in items:
                row = rows[item.row_id]
                row.embedding = list(item.embedding)
                row.status = CourseEmbeddingStatus.COMPLETED

    def fail(self, row_ids: Sequence[UUID]) -> None:
        """Mark exact rows failed and clear any vector."""
        ids = _unique_ids(row_ids)
        with session_scope(self._factory) as session:
            rows = _load_rows(session, ids)
            for row in rows:
                row.status = CourseEmbeddingStatus.FAILED
                row.embedding = None

    def coverage(
        self, canonical_group_ids: Collection[str] | None = None
    ) -> CourseEmbeddingCoverageReport:
        """Count lifecycle status per field/language/origin for diagnostic or scoped courses.

        One aggregate `GROUP BY` counts rows in the database. No chunk entity is materialized,
        because a coverage number never needs the stored text or vector. `None` counts every
        canonical course for the full-catalogue diagnostic. An explicit collection scopes the
        read to those courses, including an empty collection's all-zero report.
        """
        if canonical_group_ids is None:
            scope: tuple[str, ...] | None = None
        else:
            scope = tuple(dict.fromkeys(canonical_group_ids))
            if any(not group_id.strip() for group_id in scope):
                raise ValueError("canonical group IDs must not be blank")
        statement = (
            select(
                CourseEmbeddingChunk.field,
                CourseEmbeddingChunk.language,
                CourseEmbeddingChunk.text_origin,
                CourseEmbeddingChunk.status,
                func.count(),
            )
            .join(CourseVersion, CourseVersion.id == CourseEmbeddingChunk.course_version_id)
            .join(Course, Course.id == CourseVersion.course_id)
        )
        if scope is not None:
            statement = statement.where(Course.group_id.in_(scope))
        statement = statement.group_by(
            CourseEmbeddingChunk.field,
            CourseEmbeddingChunk.language,
            CourseEmbeddingChunk.text_origin,
            CourseEmbeddingChunk.status,
        )
        with self._factory() as session:
            buckets = tuple(session.execute(statement))
        counts: dict[
            tuple[TeachingTextField, TeachingTextLanguage, TeachingTextOrigin], dict[str, int]
        ] = {
            (field, language, origin): {"pending": 0, "completed": 0, "failed": 0}
            for field in TeachingTextField
            for language in TeachingTextLanguage
            for origin in TeachingTextOrigin
        }
        total_chunk_count = 0
        for field, language, origin, status, bucket_count in buckets:
            counts[(field, language, origin)][status.value] += bucket_count
            total_chunk_count += bucket_count
        pending_count = sum(cell["pending"] for cell in counts.values())
        completed_count = sum(cell["completed"] for cell in counts.values())
        failed_count = sum(cell["failed"] for cell in counts.values())
        return CourseEmbeddingCoverageReport(
            total_chunk_count=total_chunk_count,
            pending_count=pending_count,
            completed_count=completed_count,
            failed_count=failed_count,
            fields=tuple(
                CourseEmbeddingCoverageCount(
                    field=field,
                    language=language,
                    origin=origin,
                    pending_count=counts[(field, language, origin)]["pending"],
                    completed_count=counts[(field, language, origin)]["completed"],
                    failed_count=counts[(field, language, origin)]["failed"],
                )
                for field in TeachingTextField
                for language in TeachingTextLanguage
                for origin in TeachingTextOrigin
            ),
        )

    def read_chunk_keys(
        self, row_ids: Sequence[UUID]
    ) -> dict[UUID, tuple[str, TeachingTextField, TeachingTextLanguage, int]]:
        """Return each supplied row's projected identity key without hydrating chunk entities.

        The sole caller supplies IDs it reconciled in the same operation, so this read neither
        revalidates their existence/status nor reads text or vectors. It maps one row ID to the
        ``(group_id, field, language, chunk_index)`` key an artifact can name. An empty request
        returns ``{}`` before opening a session.
        """
        ids = tuple(row_ids)
        if not ids:
            return {}
        statement = (
            select(
                CourseEmbeddingChunk.id,
                Course.group_id,
                CourseEmbeddingChunk.field,
                CourseEmbeddingChunk.language,
                CourseEmbeddingChunk.chunk_index,
            )
            .join(CourseVersion, CourseVersion.id == CourseEmbeddingChunk.course_version_id)
            .join(Course, Course.id == CourseVersion.course_id)
            .where(CourseEmbeddingChunk.id.in_(ids))
        )
        with self._factory() as session:
            return {
                row_id: (group_id, field, language, chunk_index)
                for row_id, group_id, field, language, chunk_index in session.execute(statement)
            }

    def require_current_chunks(self, chunks: Sequence[CourseEmbeddingChunkInput]) -> None:
        """Require every desired embeddable chunk to be current, completed, and vector-backed.

        This is a projected, non-mutating readiness read: it selects only the exact requested rows'
        identity/provenance columns, lifecycle status, and a SQL ``embedding IS NOT NULL`` boolean -
        never text or vector data, and it never reconciles, generates, repairs, or deletes. An empty
        desired tuple succeeds. A duplicated desired identity fails. Missing, stale, pending, or
        failed desired work raises a safe ``ValueError`` saying the embedding stage is required.
        """
        items = tuple(chunks)
        keys: set[tuple[str, str, TeachingTextField, TeachingTextLanguage, int]] = set()
        for chunk in items:
            key = (
                chunk.group_id,
                chunk.sisu_course_unit_id,
                chunk.field,
                chunk.language,
                chunk.chunk_index,
            )
            if key in keys:
                raise ValueError(
                    "duplicate desired embedding chunk identity for "
                    f"{chunk.group_id}/{chunk.field}/{chunk.language}/{chunk.chunk_index}"
                )
            keys.add(key)
        if not items:
            return
        identities = sorted(keys)
        by_key: dict[tuple[str, str, TeachingTextField, TeachingTextLanguage, int], object] = {}
        for start in range(0, len(identities), _READINESS_BATCH_SIZE):
            batch = identities[start : start + _READINESS_BATCH_SIZE]
            with self._factory() as session:
                rows = tuple(
                    session.execute(
                        select(
                            Course.group_id,
                            CourseVersion.sisu_course_unit_id,
                            CourseEmbeddingChunk.field,
                            CourseEmbeddingChunk.language,
                            CourseEmbeddingChunk.chunk_index,
                            CourseEmbeddingChunk.status,
                            CourseEmbeddingChunk.embedding.is_not(None).label("vector_present"),
                            CourseEmbeddingChunk.text_origin,
                            CourseEmbeddingChunk.representative_source_hash,
                            CourseEmbeddingChunk.effective_text_hash,
                            CourseEmbeddingChunk.source_text_hash,
                            CourseEmbeddingChunk.chunk_text_hash,
                            CourseEmbeddingChunk.embedding_model,
                            CourseEmbeddingChunk.embedding_artifact_sha256,
                            CourseEmbeddingChunk.embedding_configuration_hash,
                            CourseEmbeddingChunk.translation_method,
                            CourseEmbeddingChunk.translation_model,
                            CourseEmbeddingChunk.translation_generated_at,
                        )
                        .join(
                            CourseVersion,
                            CourseVersion.id == CourseEmbeddingChunk.course_version_id,
                        )
                        .join(Course, Course.id == CourseVersion.course_id)
                        .where(
                            tuple_(
                                Course.group_id,
                                CourseVersion.sisu_course_unit_id,
                                CourseEmbeddingChunk.field,
                                CourseEmbeddingChunk.language,
                                CourseEmbeddingChunk.chunk_index,
                            ).in_(batch),
                        )
                    )
                )
            by_key.update(
                {
                    (
                        row.group_id,
                        row.sisu_course_unit_id,
                        row.field,
                        row.language,
                        row.chunk_index,
                    ): row
                    for row in rows
                }
            )
        for chunk in items:
            row = by_key.get(
                (
                    chunk.group_id,
                    chunk.sisu_course_unit_id,
                    chunk.field,
                    chunk.language,
                    chunk.chunk_index,
                )
            )
            if (
                row is None
                or row.status is not CourseEmbeddingStatus.COMPLETED
                or not row.vector_present
                or not _matches_identity(row, chunk)
            ):
                raise ValueError(
                    "embedding stage is required: "
                    f"{chunk.group_id}/{chunk.field.value}/{chunk.language.value} "
                    f"chunk {chunk.chunk_index} has no current completed embedding"
                )


def _validate_reconciliation_inputs(
    scope: tuple[str, ...], inputs: tuple[CourseEmbeddingChunkInput, ...]
) -> None:
    """Reject an ambiguous scope or an out-of-scope or duplicated desired chunk."""
    if len(scope) != len(set(scope)):
        raise ValueError("canonical group IDs must be unique")
    if any(not group_id.strip() for group_id in scope):
        raise ValueError("canonical group IDs must not be blank")
    scope_set = set(scope)
    keys: set[tuple[str, TeachingTextField, TeachingTextLanguage, int]] = set()
    for chunk in inputs:
        key = (chunk.group_id, chunk.field, chunk.language, chunk.chunk_index)
        if key in keys:
            raise ValueError(
                "duplicate desired chunk key for "
                f"{chunk.group_id}/{chunk.field}/{chunk.language}/{chunk.chunk_index}"
            )
        keys.add(key)
    if any(chunk.group_id not in scope_set for chunk in inputs):
        raise ValueError("desired chunks must belong to the supplied canonical scope")


def _desired_chunks(
    inputs: tuple[CourseEmbeddingChunkInput, ...],
    groups_to_versions: dict[str, dict[str, UUID]],
) -> dict[EmbeddingRowKey, CourseEmbeddingChunkInput]:
    """Map each desired chunk to its persisted row key, preserving insertion order."""
    desired: dict[EmbeddingRowKey, CourseEmbeddingChunkInput] = {}
    for chunk in inputs:
        version_id = groups_to_versions[chunk.group_id].get(chunk.sisu_course_unit_id)
        if version_id is None:
            raise ValueError(
                f"{chunk.sisu_course_unit_id} does not belong to group {chunk.group_id}"
            )
        desired[(version_id, chunk.field, chunk.language, chunk.chunk_index)] = chunk
    return desired


def _reconcile_desired_rows(
    session: Session,
    desired: dict[EmbeddingRowKey, CourseEmbeddingChunkInput],
    existing: dict[EmbeddingRowKey, CourseEmbeddingChunk],
) -> tuple[int, int, int, int, tuple[CourseEmbeddingChunk, ...]]:
    """Insert, reuse, retry, or invalidate each desired chunk in place.

    Returns inserted/invalidated/reused/retry counts and the pending rows in desired order.
    """
    inserted_count = 0
    invalidated_count = 0
    reused_count = 0
    retry_count = 0
    pending_rows: list[CourseEmbeddingChunk] = []
    for key, chunk in desired.items():
        row = existing.get(key)
        if row is None:
            row = CourseEmbeddingChunk(
                course_version_id=key[0],
                field=chunk.field,
                language=chunk.language,
                chunk_index=chunk.chunk_index,
                status=CourseEmbeddingStatus.PENDING,
            )
            _apply(row, chunk)
            session.add(row)
            pending_rows.append(row)
            inserted_count += 1
            continue
        if _matches(row, chunk):
            if row.status is CourseEmbeddingStatus.COMPLETED:
                reused_count += 1
            else:
                retry_count += 1
                pending_rows.append(row)
            continue
        _apply(row, chunk)
        row.status = CourseEmbeddingStatus.PENDING
        row.embedding = None
        pending_rows.append(row)
        invalidated_count += 1
    return inserted_count, invalidated_count, reused_count, retry_count, tuple(pending_rows)


def _matches(row: CourseEmbeddingChunk, chunk: CourseEmbeddingChunkInput) -> bool:
    """Return whether a persisted row already carries the exact desired work key."""
    return row.text == chunk.text and _matches_identity(row, chunk)


class _EmbeddingIdentityView(Protocol):
    """The identity/provenance attributes both a persisted row and a projected read expose.

    It lets the one identity comparison serve the reconcile path (full ORM row) and the projected
    readiness path (SQLAlchemy ``Row``) without a Pydantic copy or text/vector hydration.
    """

    text_origin: TeachingTextOrigin
    representative_source_hash: str
    effective_text_hash: str
    source_text_hash: str
    chunk_text_hash: str
    embedding_model: str
    embedding_artifact_sha256: str
    embedding_configuration_hash: str
    translation_method: TranslationMethod | None
    translation_model: str | None
    translation_generated_at: datetime | None


def _matches_identity(row: _EmbeddingIdentityView, chunk: CourseEmbeddingChunkInput) -> bool:
    """Return whether a persisted/projected identity row matches the exact desired work key."""
    return (
        row.text_origin is chunk.text_origin
        and row.representative_source_hash == chunk.representative_source_hash
        and row.effective_text_hash == chunk.effective_text_hash
        and row.source_text_hash == chunk.source_text_hash
        and row.chunk_text_hash == chunk.chunk_text_hash
        and row.translation_method == chunk.translation_method
        and row.translation_model == chunk.translation_model
        and row.translation_generated_at == chunk.translation_generated_at
        and row.embedding_model == chunk.embedding_model
        and row.embedding_artifact_sha256 == chunk.embedding_artifact_sha256
        and row.embedding_configuration_hash == chunk.embedding_configuration_hash
    )


def _apply(row: CourseEmbeddingChunk, chunk: CourseEmbeddingChunkInput) -> None:
    """Assign every mutable work/provenance field on a changed persistent row."""
    row.text_origin = chunk.text_origin
    row.text = chunk.text
    row.representative_source_hash = chunk.representative_source_hash
    row.effective_text_hash = chunk.effective_text_hash
    row.source_text_hash = chunk.source_text_hash
    row.chunk_text_hash = chunk.chunk_text_hash
    row.translation_method = chunk.translation_method
    row.translation_model = chunk.translation_model
    row.translation_generated_at = chunk.translation_generated_at
    row.embedding_model = chunk.embedding_model
    row.embedding_artifact_sha256 = chunk.embedding_artifact_sha256
    row.embedding_configuration_hash = chunk.embedding_configuration_hash


def _unique_ids(row_ids: Sequence[UUID]) -> tuple[UUID, ...]:
    ids = tuple(row_ids)
    if not ids:
        raise ValueError("row IDs must not be empty")
    if len(ids) != len(set(ids)):
        raise ValueError("row IDs must be unique")
    return ids


def _load_rows(session: Session, ids: Sequence[UUID]) -> list[CourseEmbeddingChunk]:
    rows = list(
        session.scalars(select(CourseEmbeddingChunk).where(CourseEmbeddingChunk.id.in_(ids)))
    )
    if len(rows) != len(ids):
        raise ValueError("requested embedding chunk rows are missing")
    return rows
