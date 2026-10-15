"""Contracts for the course-comparison meters, overlap and verdict."""

from __future__ import annotations

import pytest

from course_explorer.comparison.service import (
    PreparedTeachingOverlap,
    compare_teaching_chunks,
    comparison_verdict,
    teaching_overlap,
)
from course_explorer.config import SearchSettings
from course_explorer.embeddings.read import TeachingEmbeddingChunk
from course_explorer.enums import TeachingTextField, TeachingTextLanguage, TeachingTextOrigin
from tests.support import settings_factory


def _chunk(
    group_id: str,
    *,
    vector: tuple[float, ...],
    field: TeachingTextField = TeachingTextField.CONTENT,
    language: TeachingTextLanguage = TeachingTextLanguage.EN,
    chunk_index: int = 0,
    characters: int = 10,
) -> TeachingEmbeddingChunk:
    """Build one real chunk carrier with an explicit character weight."""
    return TeachingEmbeddingChunk(
        group_id=group_id,
        field=field,
        language=language,
        chunk_index=chunk_index,
        text_origin=TeachingTextOrigin.OFFICIAL,
        character_count=characters,
        embedding=vector,
    )


def _settings() -> SearchSettings:
    """Build the explicit comparison policy the mechanics are proved against.

    A zero floor and unit ceiling make the graded overlap equal to the character-weighted mean of the
    best cosines times 100, so the synthetic vectors give exact expectations.
    """
    return settings_factory(
        SearchSettings,
        COMPARISON_OVERLAP_FLOOR="0.0",
        COMPARISON_OVERLAP_CEILING="1.0",
        COMPARISON_HEAVY_OVERLAP_PERCENT="75",
        COMPARISON_PARTIAL_OVERLAP_PERCENT="30",
        COMPARISON_SAME_AREA_PERCENT="85",
        COMPARISON_LOOSE_RELATED_PERCENT="78",
    )


# The zero hub makes centring an identity on these synthetic vectors, so the raw-cosine
# expectations below hold. The dedicated hub test proves a non-zero hub changes the result.
_HUB = (0.0, 0.0)


def test_hub_subtraction_removes_a_shared_component() -> None:
    """A large vector component shared by both sides is removed before the cosine is taken."""
    settings = _settings()
    shared = (1.0, 0.0)
    raw = compare_teaching_chunks(
        (_chunk("a", vector=(1.0, 0.1)),),
        (_chunk("b", vector=(1.0, -0.1)),),
        settings=settings,
        hub=(0.0, 0.0),
        outcomes_hub=(0.0, 0.0),
    )
    centred = compare_teaching_chunks(
        (_chunk("a", vector=(1.0, 0.1)),),
        (_chunk("b", vector=(1.0, -0.1)),),
        settings=settings,
        hub=shared,
        outcomes_hub=shared,
    )
    assert raw.content_similarity > 90.0
    assert centred.content_similarity == pytest.approx(0.0)
    assert comparison_verdict(centred, settings=settings) == "unrelated"


def test_comparison_identical_chunks_are_fully_similar_and_overlapping() -> None:
    settings = _settings()

    # Identical descriptive teaching is fully similar and fully overlapping.
    identical = compare_teaching_chunks(
        (_chunk("a", vector=(1.0, 0.0)),),
        (_chunk("b", vector=(1.0, 0.0)),),
        settings=settings,
        hub=_HUB,
        outcomes_hub=_HUB,
    )
    assert identical.content_similarity == pytest.approx(100.0)
    assert identical.learning_outcome_similarity is None
    assert identical.overall_relatedness == pytest.approx(100.0)
    assert identical.overlap.a_in_b == pytest.approx(100.0)
    assert identical.overlap.b_in_a == pytest.approx(100.0)
    assert comparison_verdict(identical, settings=settings) == "heavily_overlapping"


def test_prepared_overlap_preserves_directional_containment() -> None:
    """A course inside a larger one reads high one way and low the other, weighted by size."""
    settings = _settings()
    a = (_chunk("a", vector=(1.0, 0.0), characters=10),)
    b = (
        _chunk("b", vector=(1.0, 0.0), chunk_index=0, characters=10),
        _chunk("b", vector=(0.0, 1.0), chunk_index=1, characters=90),
    )
    prepared = PreparedTeachingOverlap(b)
    prepared_overlap = prepared.compare(a, floor=0.0, ceiling=1.0)
    contained = compare_teaching_chunks(a, b, settings=settings, hub=_HUB, outcomes_hub=_HUB)
    assert prepared_overlap == contained.overlap
    assert prepared_overlap == teaching_overlap(
        a, b, hub=_HUB, outcomes_hub=_HUB, floor=0.0, ceiling=1.0
    )
    assert contained.overlap.a_in_b == pytest.approx(100.0)
    assert contained.overlap.b_in_a == pytest.approx(10.0)
    assert comparison_verdict(contained, settings=settings) == "heavily_overlapping"


def test_graded_overlap_is_partial_for_partly_shared_chunks() -> None:
    """A partly-matching chunk pair reads as a partial overlap, distinct from a saturated 0 or
    100."""
    settings = _settings()
    thematic_a = (
        _chunk("a", vector=(1.0, 0.0), chunk_index=0),
        _chunk("a", vector=(0.0, 1.0), chunk_index=1),
    )
    thematic_b = (_chunk("b", vector=(1.0, 1.0)),)
    thematic = compare_teaching_chunks(
        thematic_a, thematic_b, settings=settings, hub=_HUB, outcomes_hub=_HUB
    )
    assert PreparedTeachingOverlap(thematic_b).compare(
        thematic_a, floor=0.0, ceiling=1.0
    ) == teaching_overlap(
        thematic_a, thematic_b, hub=_HUB, outcomes_hub=_HUB, floor=0.0, ceiling=1.0
    )
    assert thematic.overall_relatedness == pytest.approx(100.0)
    assert thematic.overlap.a_in_b == pytest.approx(70.7, abs=0.1)
    assert thematic.overlap.b_in_a == pytest.approx(70.7, abs=0.1)
    assert comparison_verdict(thematic, settings=settings) == "partly_overlapping"


def test_partial_overlap_uses_configured_verdict() -> None:
    settings = _settings()
    # Two descriptive chunks sharing about 0.6 cosine read as a partial overlap.
    partial = compare_teaching_chunks(
        (_chunk("a", vector=(1.0, 0.0), characters=100),),
        (_chunk("b", vector=(0.6, 0.8), characters=100),),
        settings=settings,
        hub=_HUB,
        outcomes_hub=_HUB,
    )
    assert partial.overlap.a_in_b == pytest.approx(60.0)
    assert partial.overlap.b_in_a == pytest.approx(60.0)
    assert comparison_verdict(partial, settings=settings) == "partly_overlapping"


def test_unrelated_chunks_have_zero_similarity_and_overlap() -> None:
    settings = _settings()
    # Unrelated orthogonal teaching is zero similarity and unrelated.
    unrelated = compare_teaching_chunks(
        (_chunk("a", vector=(1.0, 0.0)),),
        (_chunk("b", vector=(0.0, 1.0)),),
        settings=settings,
        hub=_HUB,
        outcomes_hub=_HUB,
    )
    assert unrelated.content_similarity == pytest.approx(0.0)
    assert unrelated.overall_relatedness == pytest.approx(0.0)
    assert unrelated.overlap.a_in_b == pytest.approx(0.0)
    assert comparison_verdict(unrelated, settings=settings) == "unrelated"


def test_name_only_relatedness_has_no_descriptive_overlap() -> None:
    settings = _settings()
    # Name-only teaching produces a null content/outcome meter and descriptive overlap.
    name_only = compare_teaching_chunks(
        (_chunk("a", field=TeachingTextField.NAME, vector=(1.0, 0.0)),),
        (_chunk("b", field=TeachingTextField.NAME, vector=(1.0, 0.0)),),
        settings=settings,
        hub=_HUB,
        outcomes_hub=_HUB,
    )
    assert name_only.content_similarity is None
    assert name_only.learning_outcome_similarity is None
    assert name_only.overall_relatedness == pytest.approx(100.0)
    assert name_only.overlap.a_in_b is None
    assert name_only.overlap.b_in_a is None
    assert comparison_verdict(name_only, settings=settings) == "same_area_different_content"


def test_disjoint_languages_have_unavailable_meters() -> None:
    settings = _settings()
    # Disjoint languages produce a null value in every meter.
    disjoint = compare_teaching_chunks(
        (_chunk("a", language=TeachingTextLanguage.FI, vector=(1.0, 0.0)),),
        (_chunk("b", language=TeachingTextLanguage.EN, vector=(1.0, 0.0)),),
        settings=settings,
        hub=_HUB,
        outcomes_hub=_HUB,
    )
    assert disjoint.content_similarity is None
    assert disjoint.learning_outcome_similarity is None
    assert disjoint.overall_relatedness is None
    assert disjoint.overlap.a_in_b is None
    assert disjoint.overlap.b_in_a is None
    assert comparison_verdict(disjoint, settings=settings) is None


def test_common_languages_are_averaged_equally() -> None:
    settings = _settings()
    # Both common languages are averaged equally rather than blended across languages.
    mixed = compare_teaching_chunks(
        (
            _chunk("a", language=TeachingTextLanguage.FI, vector=(1.0, 0.0)),
            _chunk("a", language=TeachingTextLanguage.EN, vector=(1.0, 0.0)),
        ),
        (
            _chunk("b", language=TeachingTextLanguage.FI, vector=(1.0, 0.0)),
            _chunk("b", language=TeachingTextLanguage.EN, vector=(0.0, 1.0)),
        ),
        settings=settings,
        hub=_HUB,
        outcomes_hub=_HUB,
    )
    assert mixed.content_similarity == pytest.approx(50.0)
    assert mixed.overlap.a_in_b == pytest.approx(50.0)
    assert mixed.overlap.b_in_a == pytest.approx(50.0)
