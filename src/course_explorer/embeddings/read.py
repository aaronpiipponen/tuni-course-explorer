"""Scoped read-only projection of current compatible teaching-text chunk vectors.

This neutral read owner serves request-time consumers that need whole stored chunk vectors rather
than a best-chunk score: it selects the exact requested current representatives' completed,
configuration-compatible rows and returns each row's carrier metadata, character length and vector.
It never re-derives official identity, reads stored text or source snapshots, generates, repairs or
writes a chunk, and imports no comparison or inference code. The search score aggregation lives in
`search/repository.py`. This is a separate projection.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from dataclasses import dataclass, replace

from pgvector.sqlalchemy import Vector
from sqlalchemy import Enum as SqlEnum
from sqlalchemy import Integer, cast, column, func, select, true, tuple_, values
from sqlalchemy.orm import Session, sessionmaker

from course_explorer.constants import COURSE_EMBEDDING_DIMENSION
from course_explorer.curriculum import RepresentedCourseSummary
from course_explorer.db.models import Course, CourseEmbeddingChunk, CourseVersion
from course_explorer.embeddings.hub import subtract_hub, subtract_hub_for_field
from course_explorer.enums import (
    CourseEmbeddingStatus,
    TeachingTextField,
    TeachingTextLanguage,
    TeachingTextOrigin,
)


@dataclass(frozen=True)
class TeachingEmbeddingChunk:
    """One current compatible chunk vector for one exact requested representative.

    This is a request-local read carrier. It copies only the identity, cell, retained origin,
    stored character length and the vector, so no stored text or source hash is materialized.
    """

    group_id: str
    field: TeachingTextField
    language: TeachingTextLanguage
    chunk_index: int
    text_origin: TeachingTextOrigin
    character_count: int
    embedding: tuple[float, ...]


def centre_chunks(
    chunks: Sequence[TeachingEmbeddingChunk],
    hub: Sequence[float],
    *,
    outcomes_hub: Sequence[float] | None = None,
) -> tuple[TeachingEmbeddingChunk, ...]:
    """Return the chunks with each embedding in its field's hub-centred form.

    Outcomes use the outcomes hub when supplied, because the outcomes field shares a template.
    """
    if outcomes_hub is None:
        return tuple(
            replace(chunk, embedding=subtract_hub(chunk.embedding, hub)) for chunk in chunks
        )
    return tuple(
        replace(
            chunk,
            embedding=subtract_hub_for_field(chunk.embedding, chunk.field, hub, outcomes_hub),
        )
        for chunk in chunks
    )


@dataclass(frozen=True)
class TeachingEmbeddingNeighbor:
    """One request-local nearest stored chunk hit with its basis query position."""

    query_index: int
    group_id: str
    sisu_course_unit_id: str
    representative_source_hash: str
    score: float


class TeachingEmbeddingRepository:
    """Read current compatible vectors or bounded approximate neighbors."""

    def __init__(self, factory: sessionmaker[Session]) -> None:
        self._factory = factory

    def get_chunks(
        self,
        represented: Sequence[RepresentedCourseSummary],
        *,
        embedding_configuration_hash: str,
    ) -> tuple[TeachingEmbeddingChunk, ...]:
        """Return every compatible chunk for the requested current representatives.

        An empty request returns `()` before opening a session. Otherwise one column-projected
        statement joins `course_embedding_chunks -> course_versions -> courses`, scoped by the exact
        requested `(group_id, sisu_course_unit_id, representative_source_hash)` triples, and returns
        only completed, non-null, exact-configuration rows. A missing compatible row is absent, and the
        read generates or repairs nothing. Results are ordered by group, field, language
        and chunk index, and vector components are returned as ordinary floats.
        """
        requested = {
            (
                record.summary.group_id,
                record.sisu_course_unit_id,
                record.source_hash,
            )
            for record in represented
        }
        if not requested:
            return ()

        statement = (
            select(
                Course.group_id,
                CourseEmbeddingChunk.field,
                CourseEmbeddingChunk.language,
                CourseEmbeddingChunk.chunk_index,
                CourseEmbeddingChunk.text_origin,
                func.length(CourseEmbeddingChunk.text).label("character_count"),
                CourseEmbeddingChunk.embedding,
            )
            .join(CourseVersion, CourseVersion.id == CourseEmbeddingChunk.course_version_id)
            .join(Course, Course.id == CourseVersion.course_id)
            .where(
                tuple_(
                    Course.group_id,
                    CourseVersion.sisu_course_unit_id,
                    CourseEmbeddingChunk.representative_source_hash,
                ).in_(tuple(sorted(requested))),
                CourseEmbeddingChunk.status == CourseEmbeddingStatus.COMPLETED,
                CourseEmbeddingChunk.embedding.is_not(None),
                CourseEmbeddingChunk.embedding_configuration_hash == embedding_configuration_hash,
            )
            .order_by(
                Course.group_id,
                CourseEmbeddingChunk.field,
                CourseEmbeddingChunk.language,
                CourseEmbeddingChunk.chunk_index,
            )
        )
        with self._factory() as session:
            return tuple(
                TeachingEmbeddingChunk(
                    group_id=group_id,
                    field=field,
                    language=language,
                    chunk_index=chunk_index,
                    text_origin=text_origin,
                    character_count=character_count,
                    embedding=tuple(embedding),
                )
                for (
                    group_id,
                    field,
                    language,
                    chunk_index,
                    text_origin,
                    character_count,
                    embedding,
                ) in session.execute(statement)
            )

    def find_nearest_chunks(
        self,
        basis_chunks: Sequence[TeachingEmbeddingChunk],
        *,
        embedding_configuration_hash: str,
        top_k: int,
        active_only: bool,
        excluded_group_ids: Collection[str] = (),
    ) -> tuple[TeachingEmbeddingNeighbor, ...]:
        """Find at most `top_k` same-language descriptive neighbors per supplied chunk."""
        if not basis_chunks:
            return ()

        query_rows = tuple(
            (index, chunk.language.value, list(chunk.embedding))
            for index, chunk in enumerate(basis_chunks)
        )
        query_values = (
            values(
                column("query_index", Integer),
                column(
                    "language",
                    SqlEnum(
                        TeachingTextLanguage,
                        name="derived_target_language",
                        native_enum=False,
                        values_callable=lambda members: [member.value for member in members],
                    ),
                ),
                column("embedding", Vector(COURSE_EMBEDDING_DIMENSION)),
                name="basis_queries",
            )
            .data(query_rows)
            .alias("basis_queries")
        )
        query_embedding = cast(query_values.c.embedding, Vector(COURSE_EMBEDDING_DIMENSION))
        distance = CourseEmbeddingChunk.embedding.cosine_distance(query_embedding)
        nearest = (
            select(
                Course.group_id.label("group_id"),
                CourseVersion.sisu_course_unit_id.label("sisu_course_unit_id"),
                CourseEmbeddingChunk.representative_source_hash.label("source_hash"),
                (1 - distance).label("score"),
            )
            .join(CourseVersion, CourseVersion.id == CourseEmbeddingChunk.course_version_id)
            .join(Course, Course.id == CourseVersion.course_id)
            .where(
                CourseEmbeddingChunk.status == CourseEmbeddingStatus.COMPLETED,
                CourseEmbeddingChunk.embedding.is_not(None),
                CourseEmbeddingChunk.embedding_configuration_hash == embedding_configuration_hash,
                CourseEmbeddingChunk.field.in_(
                    (TeachingTextField.CONTENT, TeachingTextField.OUTCOMES)
                ),
                CourseEmbeddingChunk.language == query_values.c.language,
                Course.group_id.not_in(tuple(excluded_group_ids)) if excluded_group_ids else True,
                Course.is_active.is_(True) if active_only else True,
            )
            .order_by(distance)
            .limit(top_k)
            .lateral("nearest_chunks")
        )
        statement = (
            select(
                query_values.c.query_index,
                nearest.c.group_id,
                nearest.c.sisu_course_unit_id,
                nearest.c.source_hash,
                nearest.c.score,
            )
            .select_from(query_values.join(nearest, true()))
            .order_by(query_values.c.query_index, nearest.c.score.desc())
        )
        with self._factory() as session:
            rows = tuple(session.execute(statement))
        return tuple(TeachingEmbeddingNeighbor(*row) for row in rows)
