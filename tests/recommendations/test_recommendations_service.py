"""Public pure recommendation-service proofs over small stored-vector carriers."""

from __future__ import annotations

import pytest

from course_explorer.config import SearchSettings
from course_explorer.embeddings.read import TeachingEmbeddingChunk, TeachingEmbeddingNeighbor
from course_explorer.enums import TeachingTextField, TeachingTextLanguage, TeachingTextOrigin
from course_explorer.recommendations.service import (
    rank_recommendation_candidates,
    recommendations_from_candidates,
)
from tests.support import course, represented_rows, settings_factory, version


def _chunk(group_id: str, vector: tuple[float, float], *, origin=TeachingTextOrigin.OFFICIAL):
    return TeachingEmbeddingChunk(
        group_id=group_id,
        field=TeachingTextField.CONTENT,
        language=TeachingTextLanguage.EN,
        chunk_index=0,
        text_origin=origin,
        character_count=10,
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
