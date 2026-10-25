"""Scoped read-only projection of current compatible teaching-text chunk vectors.

This neutral read owner serves request-time consumers that need whole stored chunk vectors rather
than a best-chunk score: it selects the exact requested current representatives' completed,
configuration-compatible rows and returns each row's carrier metadata, character length and vector.
It also holds the bounded descriptive chunk cache that a repeated recommendation read answers from,
and the bounded nearest-chunk read. It never re-derives official identity, reads stored text or
source snapshots, generates, repairs or writes a chunk, and imports no comparison or inference code.
The search score aggregation lives in `search/repository.py`. This is a separate projection.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
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
    DESCRIPTIVE_TEACHING_TEXT_FIELDS,
    CourseEmbeddingStatus,
    TeachingTextField,
    TeachingTextLanguage,
    TeachingTextOrigin,
)

# The number of requested representative triples per statement. One row-value IN list over a whole
# catalogue exceeds the database's expression stack depth.
_REQUEST_BATCH_SIZE = 1000


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


class DescriptiveChunkCache:
    """Bounded least-recently-used store of descriptive chunk tuples for one dataset identity.

    An entry is one tuple of `TeachingEmbeddingChunk` carriers keyed by the read triple
    `(group_id, sisu_course_unit_id, representative_source_hash)`. An empty tuple is a retained
    entry, so absence is decided by key membership. An entry stays until the least-recently-used
    bound evicts it or the instance is replaced. One lock serializes both methods, and dropping the
    instance discards every entry. One instance belongs to one serving dataset identity.
    """

    def __init__(self, *, max_entries: int) -> None:
        self._max_entries = max_entries
        self._lock = threading.Lock()
        self._entries: OrderedDict[tuple[str, str, str], tuple[TeachingEmbeddingChunk, ...]] = (
            OrderedDict()
        )

    def get(self, triple: tuple[str, str, str]) -> tuple[TeachingEmbeddingChunk, ...] | None:
        """Return the retained tuple and touch its recency, or `None` when the triple is absent."""
        with self._lock:
            if triple not in self._entries:
                return None
            self._entries.move_to_end(triple)
            return self._entries[triple]

    def put(self, triple: tuple[str, str, str], chunks: tuple[TeachingEmbeddingChunk, ...]) -> None:
        """Retain one tuple as the most recently used and drop the least recently used entries."""
        with self._lock:
            self._entries[triple] = chunks
            self._entries.move_to_end(triple)
            while len(self._entries) > self._max_entries:
                self._entries.popitem(last=False)


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
        cache: DescriptiveChunkCache | None = None,
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
        ordered carriers in sorted-triple order reproduces the uncached statement order. A supplied
        cache answers the triples it retains, reads only the missing triples, and retains every
        triple it reads, an empty result included. A supplied cache requires `descriptive_only`, so
        the all-field read passes no cache. Results are ordered by group, field, language and chunk
        index, and vector components are returned as ordinary floats.
        """
        if cache is not None and not descriptive_only:
            raise ValueError("a chunk cache requires descriptive_only")
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
        if cache is None:
            with self._factory() as session:
                return tuple(
                    chunk
                    for start in range(0, len(ordered), _REQUEST_BATCH_SIZE)
                    for _triple, chunk in self._read_batch(
                        session,
                        ordered[start : start + _REQUEST_BATCH_SIZE],
                        embedding_configuration_hash,
                        descriptive_only=descriptive_only,
                    )
                )
        retained: dict[tuple[str, str, str], tuple[TeachingEmbeddingChunk, ...]] = {}
        missing: list[tuple[str, str, str]] = []
        for triple in ordered:
            chunks = cache.get(triple)
            if chunks is None:
                missing.append(triple)
            else:
                retained[triple] = chunks
        if missing:
            with self._factory() as session:
                for start in range(0, len(missing), _REQUEST_BATCH_SIZE):
                    batch = missing[start : start + _REQUEST_BATCH_SIZE]
                    grouped: dict[tuple[str, str, str], list[TeachingEmbeddingChunk]] = {
                        triple: [] for triple in batch
                    }
                    for triple, chunk in self._read_batch(
                        session,
                        batch,
                        embedding_configuration_hash,
                        descriptive_only=descriptive_only,
                    ):
                        grouped[triple].append(chunk)
                    for triple in batch:
                        entry = tuple(grouped[triple])
                        cache.put(triple, entry)
                        retained[triple] = entry
        return tuple(chunk for triple in ordered for chunk in retained[triple])

    @staticmethod
    def _read_batch(
        session: Session,
        requested: Sequence[tuple[str, str, str]],
        embedding_configuration_hash: str,
        *,
        descriptive_only: bool,
    ) -> tuple[tuple[tuple[str, str, str], TeachingEmbeddingChunk], ...]:
        statement = (
            select(
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
        if descriptive_only:
            statement = statement.where(
                CourseEmbeddingChunk.field.in_(DESCRIPTIVE_TEACHING_TEXT_FIELDS)
            )
        return tuple(
            (
                (group_id, sisu_course_unit_id, representative_source_hash),
                TeachingEmbeddingChunk(
                    group_id=group_id,
                    field=field,
                    language=language,
                    chunk_index=chunk_index,
                    text_origin=text_origin,
                    character_count=character_count,
                    embedding=tuple(embedding),
                ),
            )
            for (
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
                CourseEmbeddingChunk.field.in_(DESCRIPTIVE_TEACHING_TEXT_FIELDS),
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
