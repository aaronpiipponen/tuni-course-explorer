"""Per-course centroid preparation from the current descriptive chunk vectors."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy

from course_explorer.embeddings.generation import CourseEmbeddingChunkInput
from course_explorer.embeddings.vector_math import unit_row, unit_rows
from course_explorer.enums import DESCRIPTIVE_TEACHING_TEXT_FIELDS


@dataclass(frozen=True, slots=True)
class CourseCentroid:
    """One represented course's hub-centred unit centroid and its representative identity."""

    group_id: str
    sisu_course_unit_id: str
    representative_source_hash: str
    chunk_count: int
    centroid: tuple[float, ...]


def compute_course_centroids(
    chunks: Sequence[CourseEmbeddingChunkInput],
    vectors: Sequence[Sequence[float]],
    *,
    catalogue_hub: Sequence[float],
    outcomes_hub: Sequence[float],
) -> tuple[CourseCentroid, ...]:
    """Return one centroid per course with at least one descriptive content or outcomes chunk.

    The centroid is the unit mean of the course's hub-centred, unit-normalized descriptive chunk
    vectors. The field hub is subtracted before each row is normalized. A course with no
    descriptive chunk has no centroid and no row. The result is ordered by canonical group ID.
    `ValueError` is raised when `chunks` and `vectors` differ in length, when one course's
    descriptive chunks carry more than one representative identity, and when a centred row has zero
    length.
    """
    if len(chunks) != len(vectors):
        raise ValueError("chunks and vectors must have the same length")
    grouped: dict[str, list[int]] = {}
    for index, chunk in enumerate(chunks):
        if chunk.field in DESCRIPTIVE_TEACHING_TEXT_FIELDS:
            grouped.setdefault(chunk.group_id, []).append(index)

    centroids: list[CourseCentroid] = []
    for group_id in sorted(grouped):
        indices = grouped[group_id]
        first = chunks[indices[0]]
        for index in indices[1:]:
            chunk = chunks[index]
            if (
                chunk.sisu_course_unit_id != first.sisu_course_unit_id
                or chunk.representative_source_hash != first.representative_source_hash
            ):
                raise ValueError(f"course {group_id} carries more than one representative identity")
        rows = unit_rows(
            [vectors[index] for index in indices],
            [chunks[index].field for index in indices],
            catalogue_hub,
            outcomes_hub,
        )
        centroid = unit_row(rows.mean(axis=0))
        centroids.append(
            CourseCentroid(
                group_id=group_id,
                sisu_course_unit_id=first.sisu_course_unit_id,
                representative_source_hash=first.representative_source_hash,
                chunk_count=len(indices),
                centroid=tuple(float(value) for value in centroid),
            )
        )
    return tuple(centroids)


def centroid_bytes(centroid: Sequence[float]) -> bytes:
    """Return one centroid as little-endian float64 bytes."""
    return numpy.asarray(centroid, dtype="<f8").tobytes()
