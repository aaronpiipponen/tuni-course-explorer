"""Pure ranking and overlap filtering for request-local recommendation candidates."""

from __future__ import annotations

import math
import statistics
from collections.abc import Collection, Sequence

from pydantic import BaseModel, ConfigDict, Field

from course_explorer.comparison.service import overlap_percent
from course_explorer.config import SearchSettings
from course_explorer.curriculum import CourseSummary, RepresentedCourseSummary
from course_explorer.embeddings.hub import subtract_hub_for_field
from course_explorer.embeddings.read import TeachingEmbeddingChunk, TeachingEmbeddingNeighbor
from course_explorer.enums import TeachingTextField, TeachingTextOrigin
from course_explorer.search.lookup import DisplayLanguage, name_code_key, official_display_name

_DESCRIPTIVE_FIELDS = (TeachingTextField.CONTENT, TeachingTextField.OUTCOMES)


class SimilarityRecommendation(BaseModel):
    """One similarity-based result with its analysis meters.

    `relatedness` is hub-centred text similarity and `score` the ranking score. Both are percentages
    in `[0, 100]`.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    course: CourseSummary
    relatedness: float = Field(ge=0, le=100)
    score: float = Field(ge=0, le=100)
    overlap_with_basis: float | None = Field(default=None, ge=0, le=100)
    uses_derived_text: bool


def _name_key(record: RepresentedCourseSummary, language: DisplayLanguage):
    return name_code_key(record.summary, official_display_name(record.summary, language))


def rank_recommendation_candidates(
    neighbors: Sequence[TeachingEmbeddingNeighbor],
    represented: Sequence[RepresentedCourseSummary],
    *,
    excluded_group_ids: Collection[str],
    display_language: DisplayLanguage,
    settings: SearchSettings,
) -> tuple[tuple[RepresentedCourseSummary, float], ...]:
    """Filter to current representative identities and aggregate the best raw neighbour score into the ordered pool.

    The raw score only orders the pool. Hub-centred relatedness is computed and thresholded at the
    selection step, so (with no result-count cap) the configured relatedness floor alone cuts the
    returned list.
    """
    records = {record.summary.group_id: record for record in represented}
    scores: dict[str, float] = {}
    for neighbor in neighbors:
        record = records.get(neighbor.group_id)
        if (
            record is None
            or neighbor.group_id in excluded_group_ids
            or (neighbor.sisu_course_unit_id, neighbor.representative_source_hash)
            != (record.sisu_course_unit_id, record.source_hash)
        ):
            continue
        scores[neighbor.group_id] = max(scores.get(neighbor.group_id, 0.0), neighbor.score)
    candidates = [
        (records[group_id], 100 * max(0.0, min(1.0, score))) for group_id, score in scores.items()
    ]
    candidates.sort(key=lambda item: (-item[1], _name_key(item[0], display_language)))
    return tuple(candidates)


def _unit(vector: Sequence[float]) -> list[float]:
    """Return the vector's unit form, raising on a zero-length centred vector."""
    norm = math.sqrt(sum(component * component for component in vector))
    if norm == 0.0:
        raise ValueError("cannot compare a zero-length centred embedding")
    return [component / norm for component in vector]


def _centroid(units: Sequence[Sequence[float]]) -> list[float]:
    """Return the unit mean of a nonempty collection of unit vectors."""
    dimension = len(units[0])
    total = [0.0] * dimension
    for unit in units:
        for index, component in enumerate(unit):
            total[index] += component
    return _unit(total)


def recommendations_from_candidates(
    candidates: Sequence[tuple[RepresentedCourseSummary, float]],
    basis_chunks: Sequence[TeachingEmbeddingChunk],
    candidate_chunks: Sequence[TeachingEmbeddingChunk],
    *,
    display_language: DisplayLanguage,
    settings: SearchSettings,
    hub: Sequence[float],
    outcomes_hub: Sequence[float],
) -> tuple[SimilarityRecommendation, ...]:
    """Rank the pool by whole-basis hub-centred profile similarity and drop re-taught courses.

    Relatedness is the hub-centred cosine between the candidate's centroid and the trimmed basis
    profile: the mean of the basis course centroids that are most consistent with the whole basis
    (at or above the median consistency), so a broad degree's mandatory general strands (languages,
    thesis, orientation) cannot steer the profile. A candidate must relate to the degree's dominant
    subject rather than to one course. The near-duplicate test follows the shared comparison coverage
    rule but applies it to each single basis course, so a course duplicating one taken course is
    removed while a course sharing content with a broad basis is kept.
    """
    basis_descriptive = [chunk for chunk in basis_chunks if chunk.field in _DESCRIPTIVE_FIELDS]
    course_units: dict[str, list[list[float]]] = {}
    for chunk in basis_descriptive:
        course_units.setdefault(chunk.group_id, []).append(
            _unit(subtract_hub_for_field(chunk.embedding, chunk.field, hub, outcomes_hub))
        )
    centroids = {group: _centroid(units) for group, units in course_units.items()}
    # Build the profile from the basis courses most consistent with the whole basis, so a broad
    # degree's mandatory general strands (languages, thesis, orientation) do not steer it.
    if len(centroids) > 1:
        initial = _centroid(list(centroids.values()))
        consistency = {
            group: math.sumprod(centroid, initial) for group, centroid in centroids.items()
        }
        cut = statistics.median(consistency.values())
        kept = [centroid for group, centroid in centroids.items() if consistency[group] >= cut]
    else:
        kept = list(centroids.values())
    profile = _centroid(kept) if kept else []

    chunks_by_group: dict[str, list[TeachingEmbeddingChunk]] = {}
    for chunk in candidate_chunks:
        if chunk.field in _DESCRIPTIVE_FIELDS:
            chunks_by_group.setdefault(chunk.group_id, []).append(chunk)

    floor = settings.comparison_overlap_floor
    ceiling = settings.comparison_overlap_ceiling
    results: list[tuple[SimilarityRecommendation, tuple[bool, str, str, str]]] = []
    for record, _raw in candidates:
        candidate = chunks_by_group.get(record.summary.group_id)
        if not candidate or not profile:
            continue
        candidate_units = [
            _unit(subtract_hub_for_field(chunk.embedding, chunk.field, hub, outcomes_hub))
            for chunk in candidate
        ]
        relatedness = 100 * max(0.0, math.sumprod(_centroid(candidate_units), profile))
        if relatedness < settings.recommendation_min_relatedness * 100:
            continue
        total_characters = sum(chunk.character_count for chunk in candidate)
        coverage_sum = 0.0
        coverage_per_basis_course: dict[str, float] = {}
        for chunk, unit in zip(candidate, candidate_units, strict=True):
            best = 0.0
            for basis_group, units in course_units.items():
                course_best = max(math.sumprod(basis_unit, unit) for basis_unit in units)
                coverage_per_basis_course[basis_group] = coverage_per_basis_course.get(
                    basis_group, 0.0
                ) + chunk.character_count * max(0.0, course_best)
                if course_best > best:
                    best = course_best
            coverage_sum += chunk.character_count * max(0.0, best)
        strongest_course = max(
            (
                overlap_percent(covered / total_characters, floor=floor, ceiling=ceiling)
                for covered in coverage_per_basis_course.values()
            ),
            default=0.0,
        )
        if strongest_course >= settings.recommendation_near_duplicate_percent:
            continue
        candidate_covered = (
            overlap_percent(coverage_sum / total_characters, floor=floor, ceiling=ceiling)
            if total_characters > 0
            else None
        )
        score = 100 * max(
            0.0,
            relatedness / 100
            - settings.recommendation_overlap_penalty_weight * (candidate_covered or 0.0) / 100,
        )
        result = SimilarityRecommendation(
            course=record.summary,
            relatedness=relatedness,
            score=score,
            overlap_with_basis=candidate_covered,
            uses_derived_text=any(
                chunk.text_origin is TeachingTextOrigin.DERIVED for chunk in candidate
            )
            or any(chunk.text_origin is TeachingTextOrigin.DERIVED for chunk in basis_descriptive),
        )
        results.append((result, _name_key(record, display_language)))
    results.sort(key=lambda item: (-item[0].score, -item[0].relatedness, item[1]))
    return tuple(result for result, _ in results)
