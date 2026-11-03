"""Pure ranking and overlap filtering for request-local recommendation candidates."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

import numpy
from pydantic import BaseModel, ConfigDict, Field

from course_explorer.config import SearchSettings
from course_explorer.curriculum import CourseSummary, RepresentedCourseSummary
from course_explorer.embeddings.read import TeachingEmbeddingChunk, TeachingEmbeddingNeighbor
from course_explorer.embeddings.vector_math import unit_row, unit_rows
from course_explorer.enums import DESCRIPTIVE_TEACHING_TEXT_FIELDS
from course_explorer.search.lookup import DisplayLanguage, name_code_key, official_display_name


class SimilarityRecommendation(BaseModel):
    """One similarity-based result with its analysis meters.

    `relatedness` is the hub-centred text similarity calibrated for display and `score` the ranking
    score. Both are percentages in `[0, 100]`.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    course: CourseSummary
    relatedness: float = Field(ge=0, le=100)
    score: float = Field(ge=0, le=100)
    overlap_with_basis: float | None = Field(default=None, ge=0, le=100)
    uses_derived_text: bool


class ChunkRowSource(Protocol):
    """The mapped descriptive chunk rows the native scorer marshals directly."""

    def chunk_span(self, triple: tuple[str, str, str]) -> tuple[int, int] | None:
        """Return one representative's first chunk offset and count, or ``None``."""
        ...

    def descriptive_rows(self, indices: numpy.ndarray) -> tuple[numpy.ndarray, ...]:
        """Return the requested chunk vectors, fields, character counts and derived flags."""
        ...


class CentroidLookup(Protocol):
    """The exact representative-to-centroid lookup the candidate filter reads."""

    def position(
        self,
        group_id: str,
        sisu_course_unit_id: str,
        representative_source_hash: str,
    ) -> int | None:
        """Return the centroid row index for one current representative, or `None`."""
        ...

    def centroids(self, positions: Sequence[int]) -> numpy.ndarray:
        """Return the requested cached centroid rows as one float64 matrix."""
        ...


@dataclass(frozen=True, slots=True)
class RecommendationBasis:
    """The basis chunks and the trimmed profile shared by the prefilter and the scorer."""

    basis_descriptive: tuple[TeachingEmbeddingChunk, ...]
    basis_units: numpy.ndarray
    course_count: int
    profile: numpy.ndarray | None


def _name_key(record: RepresentedCourseSummary, language: DisplayLanguage):
    return name_code_key(record.summary, official_display_name(record.summary, language))


def rank_recommendation_candidates(
    neighbors: Sequence[TeachingEmbeddingNeighbor],
    represented: Sequence[RepresentedCourseSummary],
) -> tuple[RepresentedCourseSummary, ...]:
    """Filter to current representative identities, each group once, in first-seen order.

    The stored-neighbour read already removes excluded groups and the activity scope. The native
    scorer orders the returned pool. Hub-centred relatedness is computed and thresholded at the
    selection step, so (with no result-count cap) the configured relatedness floor alone cuts the
    returned list.
    """
    records = {record.summary.group_id: record for record in represented}
    candidates: dict[str, RepresentedCourseSummary] = {}
    for neighbor in neighbors:
        record = records.get(neighbor.group_id)
        if record is None or (
            neighbor.sisu_course_unit_id,
            neighbor.representative_source_hash,
        ) != (
            record.sisu_course_unit_id,
            record.source_hash,
        ):
            continue
        candidates.setdefault(neighbor.group_id, record)
    return tuple(candidates.values())


def _unit_rows(
    chunks: Sequence[TeachingEmbeddingChunk],
    hub: Sequence[float],
    outcomes_hub: Sequence[float],
) -> numpy.ndarray:
    """Return one float64 unit row per chunk after its field's hub is subtracted."""
    return unit_rows(
        [chunk.embedding for chunk in chunks],
        [chunk.field for chunk in chunks],
        hub,
        outcomes_hub,
    )


def prepare_recommendation_basis(
    basis_chunks: Sequence[TeachingEmbeddingChunk],
    *,
    hub: Sequence[float],
    outcomes_hub: Sequence[float],
) -> RecommendationBasis:
    """Return the normalized basis rows and the trimmed profile used by the whole recommendation read."""
    basis_descriptive = tuple(
        chunk for chunk in basis_chunks if chunk.field in DESCRIPTIVE_TEACHING_TEXT_FIELDS
    )
    course_groups: list[str] = []
    course_index: dict[str, int] = {}
    course_rows: list[int] = []
    for chunk in basis_descriptive:
        if chunk.group_id not in course_index:
            course_index[chunk.group_id] = len(course_groups)
            course_groups.append(chunk.group_id)
        course_rows.append(course_index[chunk.group_id])
    basis_units = _unit_rows(basis_descriptive, hub, outcomes_hub)
    if not course_groups:
        return RecommendationBasis(
            basis_descriptive=basis_descriptive,
            basis_units=basis_units,
            course_count=0,
            profile=None,
        )
    course_by_row = numpy.asarray(course_rows, dtype=numpy.intp)
    points: list[numpy.ndarray] = []
    for position in range(len(course_groups)):
        rows = numpy.flatnonzero(course_by_row == position)
        points.append(unit_row(basis_units[rows].mean(axis=0)))
    point_matrix = numpy.asarray(points, dtype=numpy.float64)
    # Build the profile from the basis courses most consistent with the whole basis, so a broad
    # degree's mandatory general strands (languages, thesis, orientation) do not steer it.
    if len(course_groups) > 1:
        initial = unit_row(point_matrix.mean(axis=0))
        consistency = point_matrix @ initial
        cut = float(numpy.median(consistency))
        kept = point_matrix[consistency >= cut]
    else:
        kept = point_matrix
    profile = unit_row(kept.mean(axis=0)) if len(kept) else None
    return RecommendationBasis(
        basis_descriptive=basis_descriptive,
        basis_units=basis_units,
        course_count=len(course_groups),
        profile=profile,
    )


def filter_neighbors_by_centroid(
    neighbors: Sequence[TeachingEmbeddingNeighbor],
    lookup: CentroidLookup,
    basis: RecommendationBasis,
    *,
    settings: SearchSettings,
) -> tuple[TeachingEmbeddingNeighbor, ...]:
    """Keep neighbor hits whose course centroid passes the configured relatedness floor.

    A hit from another representative identity is removed, and the stored-neighbour read has
    already removed excluded groups and the activity scope. The returned hits preserve the input
    order. The candidate pool that `rank_recommendation_candidates` builds from them is the pool the
    scorer reduces at the same floor.
    """
    if basis.profile is None:
        return ()
    positions: dict[tuple[str, str, str], int] = {}
    for neighbor in neighbors:
        key = (
            neighbor.group_id,
            neighbor.sisu_course_unit_id,
            neighbor.representative_source_hash,
        )
        if key in positions:
            continue
        position = lookup.position(*key)
        if position is not None:
            positions[key] = position
    if not positions:
        return ()
    floor = settings.recommendation_min_relatedness * 100
    relatedness = lookup.centroids(tuple(positions.values())) @ basis.profile
    kept = {
        key
        for key, value in zip(positions, relatedness, strict=True)
        if 100 * max(0.0, float(value)) >= floor
    }
    return tuple(
        neighbor
        for neighbor in neighbors
        if (
            neighbor.group_id,
            neighbor.sisu_course_unit_id,
            neighbor.representative_source_hash,
        )
        in kept
    )


def recommendations_from_candidates(
    candidates: Sequence[RepresentedCourseSummary],
    basis_chunks: Sequence[TeachingEmbeddingChunk],
    chunk_rows: ChunkRowSource,
    *,
    display_language: DisplayLanguage,
    settings: SearchSettings,
    hub: Sequence[float],
    outcomes_hub: Sequence[float],
    basis: RecommendationBasis | None = None,
) -> tuple[SimilarityRecommendation, ...]:
    """Rank the pool by whole-basis hub-centred profile similarity and drop re-taught courses.

    Relatedness is the hub-centred cosine between the candidate's centroid and the trimmed basis
    profile: the mean of the basis course centroids that are most consistent with the whole basis
    (at or above the median consistency), so a broad degree's mandatory general strands (languages,
    thesis, orientation) cannot steer the profile. A candidate must relate to the degree's dominant
    subject rather than to one course. The near-duplicate test follows the shared comparison coverage
    rule but applies it to each single basis course, so a course duplicating one taken course is
    removed while a course sharing content with a broad basis is kept.

    Every stored row is float64. The native scorer applies the formula to the candidate array in
    the pool order and returns each retained candidate's relatedness, score, overlap and derived
    flag. A supplied prepared basis is the profile that the centroid prefilter applies.
    """
    prepared = (
        basis
        if basis is not None
        else prepare_recommendation_basis(
            basis_chunks,
            hub=hub,
            outcomes_hub=outcomes_hub,
        )
    )
    from course_explorer.recommendations.native_scorer import score_candidates

    return score_candidates(
        candidates,
        chunk_rows,
        display_language=display_language,
        settings=settings,
        hub=hub,
        outcomes_hub=outcomes_hub,
        basis=prepared,
    )
