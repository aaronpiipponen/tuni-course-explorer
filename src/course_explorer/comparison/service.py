"""Pure request-time course-comparison meters, directional overlap and verdict.

This module owns the comparison arithmetic and nothing else: it takes already-read teaching-text
chunk carriers and configured policy, and returns percentage meters plus one verdict label. It reads
only the values it is given. All calculations
share one unit-vector/cosine core, so the whole-text thematic meter, the per-field meters
and the asymmetric overlap measure track one definition. A zero-length vector raises `ValueError`,
and a field or language that is missing on either side is `None`. The meters are analysis
percentages that estimate equivalence.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal

from pydantic import BaseModel, ConfigDict

from course_explorer.config import SearchSettings
from course_explorer.embeddings.read import TeachingEmbeddingChunk, centre_chunks
from course_explorer.enums import (
    DESCRIPTIVE_TEACHING_TEXT_FIELDS,
    TeachingTextField,
    TeachingTextLanguage,
)

ComparisonVerdict = Literal[
    "heavily_overlapping",
    "partly_overlapping",
    "same_area_different_content",
    "loosely_related",
    "unrelated",
]


class _ComparisonModel(BaseModel):
    """Frozen, closed base for the comparison report contract."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class DirectionalOverlap(_ComparisonModel):
    """The share of each course's descriptive text strongly matched in the other, in percent."""

    a_in_b: float | None
    b_in_a: float | None


class ComparisonMeters(_ComparisonModel):
    """One comparison's thematic, per-field and directional overlap percentages."""

    overall_relatedness: float | None
    content_similarity: float | None
    learning_outcome_similarity: float | None
    overlap: DirectionalOverlap


def _unit(vector: Sequence[float]) -> tuple[float, ...]:
    """Return the vector's unit form, raising on a zero-length vector."""
    norm = math.sqrt(sum(component * component for component in vector))
    if norm == 0.0:
        raise ValueError("cannot compare a zero-length teaching embedding")
    return tuple(component / norm for component in vector)


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    """Return the cosine between two vectors, clipped to `[-1, 1]`."""
    dot = sum(a * b for a, b in zip(_unit(left), _unit(right), strict=True))
    return max(-1.0, min(1.0, dot))


def _percent(cosine: float) -> float:
    """Convert a cosine into a `0-100` similarity percentage, treating negative as unrelated."""
    return 100.0 * max(0.0, cosine)


def overlap_percent(mean_cosine: float, *, floor: float, ceiling: float) -> float:
    """Map a graded mean-cosine overlap into the configured calibrated `0-100` percentage.

    The raw directional coverage is the character-weighted mean of each source chunk's best
    destination cosine. The calibration maps the configured floor to 0 and ceiling to 100 so a
    partial match reads as a partial percentage.
    """
    if ceiling <= floor:
        raise ValueError("overlap ceiling must exceed the floor")
    return 100.0 * max(0.0, min(1.0, (mean_cosine - floor) / (ceiling - floor)))


def _mean(values: Sequence[float]) -> float:
    """Return the equal-weight mean of a nonempty sequence."""
    return sum(values) / len(values)


def _field_chunks(
    chunks: Sequence[TeachingEmbeddingChunk],
    field: TeachingTextField,
    language: TeachingTextLanguage,
) -> tuple[TeachingEmbeddingChunk, ...]:
    """Return the chunks of one exact field and language."""
    return tuple(chunk for chunk in chunks if chunk.field == field and chunk.language == language)


def _centroid(chunks: Sequence[TeachingEmbeddingChunk]) -> tuple[float, ...]:
    """Return the character-count-weighted mean of the chunks' unit vectors."""
    total = sum(chunk.character_count for chunk in chunks)
    if total <= 0:
        raise ValueError("cannot build a teaching centroid from zero character weight")
    dimension = len(chunks[0].embedding)
    sums = [0.0] * dimension
    for chunk in chunks:
        unit = _unit(chunk.embedding)
        for index, component in enumerate(unit):
            sums[index] += component * chunk.character_count
    return tuple(component / total for component in sums)


def _field_similarity(
    a: Sequence[TeachingEmbeddingChunk],
    b: Sequence[TeachingEmbeddingChunk],
    field: TeachingTextField,
) -> float | None:
    """Average one field's per-language centroid cosine, or `None` when no language is common."""
    cosines: list[float] = []
    for language in TeachingTextLanguage:
        a_chunks = _field_chunks(a, field, language)
        b_chunks = _field_chunks(b, field, language)
        if not a_chunks or not b_chunks:
            continue
        cosines.append(_cosine(_centroid(a_chunks), _centroid(b_chunks)))
    if not cosines:
        return None
    return _percent(_mean(cosines))


def _overall_similarity(
    a: Sequence[TeachingEmbeddingChunk],
    b: Sequence[TeachingEmbeddingChunk],
    settings: SearchSettings,
) -> float | None:
    """Average the per-language weighted whole-text centroid cosine, or `None` when none is common."""
    weights = {
        TeachingTextField.NAME: settings.comparison_name_weight,
        TeachingTextField.CONTENT: settings.comparison_content_weight,
        TeachingTextField.OUTCOMES: settings.comparison_outcomes_weight,
    }
    cosines: list[float] = []
    for language in TeachingTextLanguage:
        a_centroids: list[tuple[float, ...]] = []
        b_centroids: list[tuple[float, ...]] = []
        included: list[float] = []
        for field, weight in weights.items():
            a_chunks = _field_chunks(a, field, language)
            b_chunks = _field_chunks(b, field, language)
            if not a_chunks or not b_chunks:
                continue
            a_centroids.append(_unit(_centroid(a_chunks)))
            b_centroids.append(_unit(_centroid(b_chunks)))
            included.append(weight)
        if not included:
            continue
        total_weight = sum(included)
        a_combined = _weighted_sum(a_centroids, included, total_weight)
        b_combined = _weighted_sum(b_centroids, included, total_weight)
        cosines.append(_cosine(a_combined, b_combined))
    if not cosines:
        return None
    return _percent(_mean(cosines))


def _weighted_sum(
    vectors: Sequence[Sequence[float]], weights: Sequence[float], total_weight: float
) -> tuple[float, ...]:
    """Return the weight-normalized sum of the supplied vectors."""
    dimension = len(vectors[0])
    sums = [0.0] * dimension
    for vector, weight in zip(vectors, weights, strict=True):
        for index, component in enumerate(vector):
            sums[index] += component * weight
    return tuple(component / total_weight for component in sums)


def _prepare_descriptive_chunks(
    chunks: Sequence[TeachingEmbeddingChunk],
) -> Mapping[TeachingTextLanguage, tuple[tuple[tuple[float, ...], int], ...]]:
    """Normalize descriptive chunks once and group their vectors and character weights."""
    grouped: dict[TeachingTextLanguage, list[tuple[tuple[float, ...], int]]] = {}
    for chunk in chunks:
        if chunk.field in DESCRIPTIVE_TEACHING_TEXT_FIELDS:
            grouped.setdefault(chunk.language, []).append(
                (_unit(chunk.embedding), chunk.character_count)
            )
    return MappingProxyType({language: tuple(values) for language, values in grouped.items()})


@dataclass(frozen=True, init=False)
class PreparedTeachingOverlap:
    """One request-local descriptive-vector projection reused across overlap comparisons."""

    _by_language: Mapping[TeachingTextLanguage, tuple[tuple[tuple[float, ...], int], ...]]

    def __init__(self, chunks: Sequence[TeachingEmbeddingChunk]) -> None:
        object.__setattr__(self, "_by_language", _prepare_descriptive_chunks(chunks))

    def compare(
        self, chunks: Sequence[TeachingEmbeddingChunk], *, floor: float, ceiling: float
    ) -> DirectionalOverlap:
        """Compare supplied chunks against this prepared side with graded, calibrated coverage."""
        other_by_language = _prepare_descriptive_chunks(chunks)
        a_in_b_languages: list[float] = []
        b_in_a_languages: list[float] = []
        for language, a_chunks in other_by_language.items():
            b_chunks = self._by_language.get(language)
            if b_chunks is None:
                continue
            a_total = sum(weight for _, weight in a_chunks)
            b_total = sum(weight for _, weight in b_chunks)
            if a_total <= 0 or b_total <= 0:
                raise ValueError("cannot weight overlap by a zero total character count")
            scores = [
                [max(-1.0, min(1.0, math.sumprod(a_vector, b_vector))) for b_vector, _ in b_chunks]
                for a_vector, _ in a_chunks
            ]
            a_mean = (
                sum(
                    weight * max(0.0, max(row))
                    for (_, weight), row in zip(a_chunks, scores, strict=True)
                )
                / a_total
            )
            b_mean = (
                sum(
                    weight * max(0.0, max(row[b_index] for row in scores))
                    for b_index, (_, weight) in enumerate(b_chunks)
                )
                / b_total
            )
            a_in_b_languages.append(a_mean)
            b_in_a_languages.append(b_mean)
        if not a_in_b_languages:
            return DirectionalOverlap(a_in_b=None, b_in_a=None)
        return DirectionalOverlap(
            a_in_b=overlap_percent(_mean(a_in_b_languages), floor=floor, ceiling=ceiling),
            b_in_a=overlap_percent(_mean(b_in_a_languages), floor=floor, ceiling=ceiling),
        )


def teaching_overlap(
    a: Sequence[TeachingEmbeddingChunk],
    b: Sequence[TeachingEmbeddingChunk],
    *,
    hub: Sequence[float],
    outcomes_hub: Sequence[float],
    floor: float,
    ceiling: float,
) -> DirectionalOverlap:
    """Return the reusable directional content/outcome overlap between two hub-centred collections.

    For each language with at least one descriptive chunk on both sides, every source chunk's best
    centred cosine against the destination chunks of that language (content may match outcomes) is
    averaged by character weight, then mapped through the configured floor/ceiling calibration, so a
    partial match reads as a partial percentage. The two directions are computed independently and
    available languages are averaged equally. With no common descriptive-text language both
    directions are `None`. This is an embedding/window-weighted text approximation that estimates
    equivalence from text.
    """
    return PreparedTeachingOverlap(centre_chunks(b, hub, outcomes_hub=outcomes_hub)).compare(
        centre_chunks(a, hub, outcomes_hub=outcomes_hub),
        floor=floor,
        ceiling=ceiling,
    )


def compare_teaching_chunks(
    a: Sequence[TeachingEmbeddingChunk],
    b: Sequence[TeachingEmbeddingChunk],
    *,
    settings: SearchSettings,
    hub: Sequence[float],
    outcomes_hub: Sequence[float],
) -> ComparisonMeters:
    """Return the whole-text, content, outcome and directional-overlap meters for two courses."""
    centred_a = centre_chunks(a, hub, outcomes_hub=outcomes_hub)
    centred_b = centre_chunks(b, hub, outcomes_hub=outcomes_hub)
    return ComparisonMeters(
        overall_relatedness=_overall_similarity(centred_a, centred_b, settings),
        content_similarity=_field_similarity(centred_a, centred_b, TeachingTextField.CONTENT),
        learning_outcome_similarity=_field_similarity(
            centred_a, centred_b, TeachingTextField.OUTCOMES
        ),
        overlap=teaching_overlap(
            a,
            b,
            hub=hub,
            outcomes_hub=outcomes_hub,
            floor=settings.comparison_overlap_floor,
            ceiling=settings.comparison_overlap_ceiling,
        ),
    )


def comparison_verdict(
    meters: ComparisonMeters, *, settings: SearchSettings
) -> ComparisonVerdict | None:
    """Return the first matching verdict label from the configured thresholds.

    The strongest available directional overlap decides the two overlap labels. Otherwise the
    overall relatedness meter decides same-area, loose or unrelated. When no overlap threshold
    matched and overall relatedness is `None`, the verdict is `None`.
    """
    overlaps = [
        value for value in (meters.overlap.a_in_b, meters.overlap.b_in_a) if value is not None
    ]
    strongest_overlap = max(overlaps) if overlaps else None
    if strongest_overlap is not None:
        if strongest_overlap >= settings.comparison_heavy_overlap_percent:
            return "heavily_overlapping"
        if strongest_overlap >= settings.comparison_partial_overlap_percent:
            return "partly_overlapping"
    overall = meters.overall_relatedness
    if overall is not None:
        if overall >= settings.comparison_same_area_percent:
            return "same_area_different_content"
        if overall >= settings.comparison_loose_related_percent:
            return "loosely_related"
        return "unrelated"
    return None
