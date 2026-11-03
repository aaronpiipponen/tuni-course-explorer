"""Scoped read-only projection of current compatible teaching-text chunk vectors.

This neutral read owner serves request-time consumers that need whole stored chunk vectors rather
than a best-chunk score: it selects the exact requested current representatives' completed,
configuration-compatible rows and returns each row's carrier metadata, character length and vector.
A descriptive read answers from the shared float64 chunk store of the serving artifact build. The
repository also holds the bounded nearest-chunk read. It never re-derives official identity, reads
stored text or source snapshots, generates, repairs or writes a chunk, and imports no comparison or
inference code. The search score aggregation lives in `search/repository.py`. This is a separate
projection.
"""

from __future__ import annotations

import uuid
from collections.abc import Collection, Sequence
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

import numpy
from sqlalchemy import Integer, column, func, select, tuple_, values
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Session, sessionmaker

from course_explorer.curriculum import RepresentedCourseSummary
from course_explorer.db.models import (
    Course,
    CourseEmbeddingChunk,
    CourseEmbeddingNeighbor,
    CourseVersion,
)
from course_explorer.embeddings.hub import subtract_hub, subtract_hub_for_field
from course_explorer.enums import (
    CourseEmbeddingStatus,
    TeachingTextField,
    TeachingTextLanguage,
    TeachingTextOrigin,
)

if TYPE_CHECKING:
    from course_explorer.embeddings.shared_store import SharedServingStore

# The number of requested representative triples per statement. One row-value IN list over a whole
# catalogue exceeds the database's expression stack depth.
_REQUEST_BATCH_SIZE = 1000


@dataclass(frozen=True)
class TeachingEmbeddingChunk:
    """One current compatible chunk vector for one exact requested representative.

    This is a request-local read carrier. It copies only the identity (including the representative
    version and source hash), cell, retained origin, stored character length and the vector, so no
    stored text or source hash from the teaching-text store is materialized.
    """

    chunk_id: uuid.UUID
    group_id: str
    field: TeachingTextField
    language: TeachingTextLanguage
    chunk_index: int
    text_origin: TeachingTextOrigin
    character_count: int
    embedding: Sequence[float] | numpy.ndarray
    sisu_course_unit_id: str = ""
    representative_source_hash: str = ""


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
    """One request-local nearest stored chunk hit for one representative triple."""

    group_id: str
    sisu_course_unit_id: str
    representative_source_hash: str


class TeachingEmbeddingRepository:
    """Read current compatible vectors or bounded approximate neighbors."""

    def __init__(self, factory: sessionmaker[Session]) -> None:
        self._factory = factory

    def get_chunks(
        self,
        represented: Sequence[RepresentedCourseSummary],
        *,
        embedding_configuration_hash: str,
        descriptive_only: bool = False,
        shared_store: SharedServingStore | None = None,
    ) -> tuple[TeachingEmbeddingChunk, ...]:
        """Return every compatible chunk for the requested current representatives.

        An empty request returns `()` before opening a session. Otherwise column-projected
        statements join `course_embedding_chunks -> course_versions -> courses`, scoped by the exact
        requested `(group_id, sisu_course_unit_id, representative_source_hash)` triples in sorted
        batches of `_REQUEST_BATCH_SIZE`, so a whole-catalogue request stays within the database's
        expression depth. Each course has one requested triple, so the batches concatenate in
        order. The read returns only completed, non-null, exact-configuration rows. A missing
        compatible row is absent, and the read generates or repairs nothing. With `descriptive_only`
        the statement keeps only the content and outcomes rows.

        A requested set holds one triple per canonical group, so concatenating each triple's
        ordered carriers in sorted-triple order reproduces the statement order. A descriptive read
        answers from the supplied shared store, and a missing store raises ``ValueError``. The
        all-field read, which comparison uses, keeps the database projection. Results are ordered by
        group, field, language and chunk index.
        """
        if descriptive_only:
            if shared_store is None:
                raise ValueError("a descriptive chunk read requires the shared serving store")
            return shared_store.chunks_for(represented)
        return self.read_stored_chunks(
            represented, embedding_configuration_hash=embedding_configuration_hash
        )

    def read_stored_chunks(
        self,
        represented: Sequence[RepresentedCourseSummary],
        *,
        embedding_configuration_hash: str,
    ) -> tuple[TeachingEmbeddingChunk, ...]:
        """Read every completed compatible chunk row with its identity and float64 vector.

        The artifact builder uses this read to write the shared store and both hubs. A
        non-descriptive read, which comparison uses, shares this exact database projection. A
        descriptive read uses the shared store instead.
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
        ordered = sorted(requested)
        with self._factory() as session:
            return tuple(
                chunk
                for start in range(0, len(ordered), _REQUEST_BATCH_SIZE)
                for _triple, chunk in self._read_batch(
                    session,
                    ordered[start : start + _REQUEST_BATCH_SIZE],
                    embedding_configuration_hash,
                )
            )

    @staticmethod
    def _read_batch(
        session: Session,
        requested: Sequence[tuple[str, str, str]],
        embedding_configuration_hash: str,
    ) -> tuple[tuple[tuple[str, str, str], TeachingEmbeddingChunk], ...]:
        statement = (
            select(
                CourseEmbeddingChunk.id,
                Course.group_id,
                CourseVersion.sisu_course_unit_id,
                CourseEmbeddingChunk.representative_source_hash,
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
                ).in_(tuple(requested)),
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
        return tuple(
            (
                (group_id, sisu_course_unit_id, representative_source_hash),
                TeachingEmbeddingChunk(
                    chunk_id=chunk_id,
                    group_id=group_id,
                    field=field,
                    language=language,
                    chunk_index=chunk_index,
                    text_origin=text_origin,
                    character_count=character_count,
                    embedding=numpy.asarray(embedding, dtype=numpy.float64),
                    sisu_course_unit_id=sisu_course_unit_id,
                    representative_source_hash=representative_source_hash,
                ),
            )
            for (
                chunk_id,
                group_id,
                sisu_course_unit_id,
                representative_source_hash,
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
        """Read at most `top_k` stored nearest descriptive neighbors per supplied chunk.

        The stored neighbour table is the only read path. Its rows join the target chunk, version
        and course for the identity, and the request's activity scope and excluded groups apply
        before the per-chunk limit. The window orders each chunk's rows by descending score and
        target chunk and keeps the top `top_k`, and the projection returns each representative
        triple once, which is the pool the prefilter and scorer read. A dataset whose stored chunks
        carry no neighbour row returns no neighbour: the opened artifact set refuses that dataset,
        and this read does not re-verify the table's coverage.
        """
        if not basis_chunks:
            return ()
        query_values = (
            values(
                column("query_index", Integer),
                column("query_chunk_id", PgUUID(as_uuid=True)),
                name="basis_chunks",
            )
            .data([(index, chunk.chunk_id) for index, chunk in enumerate(basis_chunks)])
            .alias("basis_chunks")
        )
        ranked = (
            select(
                query_values.c.query_index.label("query_index"),
                Course.group_id.label("group_id"),
                CourseVersion.sisu_course_unit_id.label("sisu_course_unit_id"),
                CourseEmbeddingChunk.representative_source_hash.label("source_hash"),
                CourseEmbeddingNeighbor.score.label("score"),
                func.row_number()
                .over(
                    partition_by=query_values.c.query_index,
                    order_by=(
                        CourseEmbeddingNeighbor.score.desc(),
                        CourseEmbeddingNeighbor.target_chunk_id,
                    ),
                )
                .label("position"),
            )
            .select_from(
                query_values.join(
                    CourseEmbeddingNeighbor,
                    CourseEmbeddingNeighbor.query_chunk_id == query_values.c.query_chunk_id,
                )
            )
            .join(
                CourseEmbeddingChunk,
                CourseEmbeddingChunk.id == CourseEmbeddingNeighbor.target_chunk_id,
            )
            .join(CourseVersion, CourseVersion.id == CourseEmbeddingChunk.course_version_id)
            .join(Course, Course.id == CourseVersion.course_id)
            .where(
                CourseEmbeddingChunk.embedding_configuration_hash == embedding_configuration_hash,
                Course.group_id.not_in(tuple(excluded_group_ids)) if excluded_group_ids else True,
                Course.is_active.is_(True) if active_only else True,
            )
            .subquery("ranked_neighbors")
        )
        statement = (
            select(
                ranked.c.group_id,
                ranked.c.sisu_course_unit_id,
                ranked.c.source_hash,
            )
            .where(ranked.c.position <= top_k)
            .group_by(ranked.c.group_id, ranked.c.sisu_course_unit_id, ranked.c.source_hash)
        )
        with self._factory() as session:
            rows = tuple(session.execute(statement))
        return tuple(TeachingEmbeddingNeighbor(*row) for row in rows)
