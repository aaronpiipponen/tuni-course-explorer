"""Public pure recommendation-service proofs over small stored-vector carriers."""

from __future__ import annotations

import math
import statistics

import pytest

from course_explorer.comparison.service import overlap_percent
from course_explorer.config import SearchSettings
from course_explorer.embeddings.hub import subtract_hub_for_field
from course_explorer.embeddings.read import TeachingEmbeddingChunk, TeachingEmbeddingNeighbor
from course_explorer.enums import (
    DESCRIPTIVE_TEACHING_TEXT_FIELDS,
    TeachingTextField,
    TeachingTextLanguage,
    TeachingTextOrigin,
)
from course_explorer.recommendations.service import (
    rank_recommendation_candidates,
    recommendations_from_candidates,
)
from tests.support import course, represented_rows, settings_factory, version


def _chunk(
    group_id: str,
    vector: tuple[float, float],
    *,
    origin=TeachingTextOrigin.OFFICIAL,
    field=TeachingTextField.CONTENT,
    character_count: int = 10,
):
    return TeachingEmbeddingChunk(
        group_id=group_id,
        field=field,
        language=TeachingTextLanguage.EN,
        chunk_index=0,
        text_origin=origin,
        character_count=character_count,
        embedding=vector,
    )


def test_recommendations_rank_whole_basis_profile_and_drop_a_duplicated_course() -> None:
    """Rank by the whole-basis profile and drop a course that duplicates one basis course."""
    records = represented_rows(
        (
            course("basis-one", version("b1", name_en="Basis one")),
            course("basis-two", version("b2", name_en="Basis two")),
            course("aligned", version("a", name_en="Aligned")),
            course("duplicate", version("d", name_en="Duplicate")),
            course("offtopic", version("o", name_en="Off topic")),
        )
    )
    settings = settings_factory(
        SearchSettings,
        RECOMMENDATION_MIN_RELATEDNESS="0.5",
        RECOMMENDATION_NEAR_DUPLICATE_PERCENT="90",
        RECOMMENDATION_OVERLAP_PENALTY_WEIGHT="0.0",
        COMPARISON_OVERLAP_FLOOR="0.0",
        COMPARISON_OVERLAP_CEILING="1.0",
    )
    # Raw neighbour scores only bound the pool. Relatedness is recomputed as the profile cosine.
    neighbors = (
        TeachingEmbeddingNeighbor(0, "aligned", "a", "a" * 64, 0.9),
        TeachingEmbeddingNeighbor(0, "duplicate", "d", "a" * 64, 0.9),
        TeachingEmbeddingNeighbor(0, "offtopic", "o", "a" * 64, 0.9),
    )
    candidates = rank_recommendation_candidates(
        neighbors,
        records,
        excluded_group_ids={"basis-one", "basis-two"},
        display_language="en",
        settings=settings,
    )
    basis = (_chunk("basis-one", (1.0, 0.0)), _chunk("basis-two", (0.0, 1.0)))
    results = recommendations_from_candidates(
        candidates,
        basis,
        (
            _chunk("aligned", (1.0, 1.0), origin=TeachingTextOrigin.DERIVED),
            _chunk("duplicate", (1.0, 0.0)),
            _chunk("offtopic", (-1.0, -1.0)),
        ),
        display_language="en",
        settings=settings,
        hub=(0.0, 0.0),
        outcomes_hub=(0.0, 0.0),
    )
    # Aligned matches the whole-basis profile. Duplicate re-teaches basis-one (dropped).
    # Off-topic points away from the profile (below the relatedness floor).
    assert [result.course.group_id for result in results] == ["aligned"]
    assert results[0].relatedness == pytest.approx(100.0)
    assert results[0].overlap_with_basis == pytest.approx(70.7, abs=0.1)
    assert results[0].course.name_en == "Aligned"
    assert results[0].uses_derived_text is True


def _scalar_meters(candidates, basis, chunks, settings, hub, outcomes_hub):
    """Compute the same formula with Python scalars, as the reference for the vectorized scorer."""

    def unit(vector):
        norm = math.sqrt(sum(component * component for component in vector))
        if norm == 0.0:
            raise ValueError("cannot compare a zero-length centred embedding")
        return [component / norm for component in vector]

    def centroid(units):
        total = [0.0] * len(units[0])
        for row in units:
            for index, component in enumerate(row):
                total[index] += component
        return unit(total)

    basis_descriptive = [
        chunk for chunk in basis if chunk.field in DESCRIPTIVE_TEACHING_TEXT_FIELDS
    ]
    course_units: dict[str, list[list[float]]] = {}
    for chunk in basis_descriptive:
        course_units.setdefault(chunk.group_id, []).append(
            unit(list(subtract_hub_for_field(chunk.embedding, chunk.field, hub, outcomes_hub)))
        )
    centroids = {group: centroid(rows) for group, rows in course_units.items()}
    if len(centroids) > 1:
        initial = centroid(list(centroids.values()))
        consistency = {group: math.sumprod(point, initial) for group, point in centroids.items()}
        cut = statistics.median(consistency.values())
        kept = [point for group, point in centroids.items() if consistency[group] >= cut]
    else:
        kept = list(centroids.values())
    profile = centroid(kept) if kept else []

    chunks_by_group: dict[str, list[TeachingEmbeddingChunk]] = {}
    for chunk in chunks:
        if chunk.field in DESCRIPTIVE_TEACHING_TEXT_FIELDS:
            chunks_by_group.setdefault(chunk.group_id, []).append(chunk)

    floor = settings.comparison_overlap_floor
    ceiling = settings.comparison_overlap_ceiling
    meters: dict[str, tuple[float, float, float | None, bool]] = {}
    for record, _raw in candidates:
        candidate = chunks_by_group.get(record.summary.group_id)
        if not candidate or not profile:
            continue
        units = [
            unit(list(subtract_hub_for_field(chunk.embedding, chunk.field, hub, outcomes_hub)))
            for chunk in candidate
        ]
        relatedness = 100 * max(0.0, math.sumprod(centroid(units), profile))
        if relatedness < settings.recommendation_min_relatedness * 100:
            continue
        total_characters = sum(chunk.character_count for chunk in candidate)
        coverage_sum = 0.0
        coverage_per_basis_course: dict[str, float] = {}
        for chunk, row in zip(candidate, units, strict=True):
            best = 0.0
            for basis_group, basis_units in course_units.items():
                course_best = max(math.sumprod(basis_row, row) for basis_row in basis_units)
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
        covered = (
            overlap_percent(coverage_sum / total_characters, floor=floor, ceiling=ceiling)
            if total_characters > 0
            else None
        )
        score = 100 * max(
            0.0,
            relatedness / 100
            - settings.recommendation_overlap_penalty_weight * (covered or 0.0) / 100,
        )
        meters[record.summary.group_id] = (
            relatedness,
            score,
            covered,
            any(chunk.text_origin is TeachingTextOrigin.DERIVED for chunk in candidate)
            or any(chunk.text_origin is TeachingTextOrigin.DERIVED for chunk in basis_descriptive),
        )
    return meters


def test_vectorized_recommendations_match_the_scalar_formula_and_keep_ties() -> None:
    """The float64 scorer keeps the scalar retained set, order, ties and flags within last bits."""
    records = represented_rows(
        (
            course("group-basis-one", version("b1", name_en="Basis one")),
            course("group-basis-two", version("b2", name_en="Basis two")),
            course("group-multi", version("m", name_en="Multi chunk")),
            course("group-tie-one", version("t1", name_en="Tie one")),
            course("group-tie-two", version("t2", name_en="Tie two")),
            course("group-duplicate", version("d", name_en="Duplicate")),
            course("group-below", version("b", name_en="Below floor")),
        )
    )
    by_group = {record.summary.group_id: record for record in records}
    settings = settings_factory(
        SearchSettings,
        RECOMMENDATION_MIN_RELATEDNESS="0.5",
        RECOMMENDATION_NEAR_DUPLICATE_PERCENT="90",
        RECOMMENDATION_OVERLAP_PENALTY_WEIGHT="0.25",
        COMPARISON_OVERLAP_FLOOR="0.0",
        COMPARISON_OVERLAP_CEILING="1.0",
    )
    pool = (
        "group-tie-one",
        "group-multi",
        "group-duplicate",
        "group-below",
        "group-tie-two",
    )
    candidates = tuple((by_group[group_id], 50.0) for group_id in pool)
    basis = (_chunk("group-basis-one", (1.0, 0.0)), _chunk("group-basis-two", (0.0, 1.0)))
    chunks = (
        _chunk("group-multi", (0.6, 0.8), origin=TeachingTextOrigin.DERIVED),
        _chunk("group-multi", (0.28, 0.96), origin=TeachingTextOrigin.DERIVED),
        _chunk("group-tie-one", (0.6, 0.8)),
        _chunk("group-tie-two", (0.6, 0.8)),
        _chunk("group-duplicate", (1.0, 0.0)),
        _chunk("group-below", (-1.0, 0.0)),
    )

    results = recommendations_from_candidates(
        candidates,
        basis,
        chunks,
        display_language="en",
        settings=settings,
        hub=(0.0, 0.0),
        outcomes_hub=(0.0, 0.0),
    )
    expected = _scalar_meters(candidates, basis, chunks, settings, (0.0, 0.0), (0.0, 0.0))

    # The duplicate is dropped as a near duplicate of one basis course and the away-facing course
    # falls below the relatedness floor, so both scorers retain the same three courses.
    assert [result.course.group_id for result in results] == [
        "group-tie-one",
        "group-tie-two",
        "group-multi",
    ]
    assert {result.course.group_id for result in results} == set(expected)
    assert results[2].uses_derived_text is True
    assert results[0].uses_derived_text is False
    # Two candidates hold the same vector, so their scores tie exactly and the name key decides.
    assert results[0].score == results[1].score
    for result in results:
        relatedness, score, overlap, derived = expected[result.course.group_id]
        assert result.relatedness == pytest.approx(relatedness, abs=1e-10)
        assert result.score == pytest.approx(score, abs=1e-10)
        assert result.overlap_with_basis == pytest.approx(overlap, abs=1e-10)
        assert result.uses_derived_text is derived
