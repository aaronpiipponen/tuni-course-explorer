"""Public pure recommendation-service proofs over small stored-vector carriers."""

from __future__ import annotations

import uuid

import numpy
import pytest

from course_explorer.config import SearchSettings
from course_explorer.embeddings.read import TeachingEmbeddingChunk, TeachingEmbeddingNeighbor
from course_explorer.embeddings.vector_math import unit_row
from course_explorer.enums import (
    DESCRIPTIVE_TEACHING_TEXT_FIELDS,
    TeachingTextField,
    TeachingTextLanguage,
    TeachingTextOrigin,
)
from course_explorer.recommendations.service import (
    filter_neighbors_by_centroid,
    prepare_recommendation_basis,
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
        chunk_id=uuid.uuid5(uuid.NAMESPACE_URL, f"{group_id}/{field}/0"),
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
    # The neighbour read supplies the pool identities. Relatedness is the profile cosine.
    neighbors = (
        TeachingEmbeddingNeighbor("aligned", "a", "a" * 64),
        TeachingEmbeddingNeighbor("duplicate", "d", "a" * 64),
        TeachingEmbeddingNeighbor("offtopic", "o", "a" * 64),
    )
    basis = (_chunk("basis-one", (1.0, 0.0)), _chunk("basis-two", (0.0, 1.0)))
    chunks = (
        _chunk("aligned", (1.0, 1.0), origin=TeachingTextOrigin.DERIVED),
        _chunk("duplicate", (1.0, 0.0)),
        _chunk("offtopic", (-1.0, -1.0)),
    )
    by_group = {record.summary.group_id: record for record in records}
    candidate_groups = ("aligned", "duplicate", "offtopic")
    positions = {
        (
            by_group[group_id].summary.group_id,
            by_group[group_id].sisu_course_unit_id,
            by_group[group_id].source_hash,
        ): position
        for position, group_id in enumerate(candidate_groups)
    }
    centroids = tuple(
        unit_row(numpy.asarray(chunk.embedding, dtype=numpy.float64)) for chunk in chunks
    )
    prepared = prepare_recommendation_basis(
        basis,
        hub=(0.0, 0.0),
        outcomes_hub=(0.0, 0.0),
    )
    filtered_neighbors = filter_neighbors_by_centroid(
        neighbors,
        _CentroidLookup(positions, centroids),
        prepared,
        settings=settings,
    )
    assert {neighbor.group_id for neighbor in filtered_neighbors} == {
        "aligned",
        "duplicate",
    }
    candidates = rank_recommendation_candidates(filtered_neighbors, records)
    results = recommendations_from_candidates(
        candidates,
        basis,
        _ChunkRows(chunks),
        display_language="en",
        settings=settings,
        hub=(0.0, 0.0),
        outcomes_hub=(0.0, 0.0),
        basis=prepared,
    )
    # The prefilter keeps the aligned and duplicate candidates at this floor, and the scorer drops
    # the duplicate as a near-duplicate of one basis course.
    assert [result.course.group_id for result in results] == ["aligned"]
    assert results[0].relatedness == pytest.approx(100.0)
    assert results[0].overlap_with_basis == pytest.approx(70.7, abs=0.1)
    assert results[0].course.name_en == "Aligned"
    assert results[0].uses_derived_text is True


class _ChunkRows:
    """Small stored-chunk source over the test carriers, keyed by canonical group."""

    def __init__(self, chunks) -> None:
        self._chunks = tuple(
            chunk for chunk in chunks if chunk.field in DESCRIPTIVE_TEACHING_TEXT_FIELDS
        )
        self._spans: dict[str, tuple[int, int]] = {}
        for position, chunk in enumerate(self._chunks):
            start, count = self._spans.get(chunk.group_id, (position, 0))
            self._spans[chunk.group_id] = (start, count + 1)

    def chunk_span(self, triple):
        return self._spans.get(triple[0])

    def descriptive_rows(self, indices):
        selected = [self._chunks[int(index)] for index in indices]
        return (
            numpy.asarray([chunk.embedding for chunk in selected], dtype=numpy.float64),
            numpy.asarray(
                [1 if chunk.field is TeachingTextField.OUTCOMES else 0 for chunk in selected],
                dtype=numpy.int32,
            ),
            numpy.asarray([chunk.character_count for chunk in selected], dtype=numpy.int64),
            numpy.asarray(
                [1 if chunk.text_origin is TeachingTextOrigin.DERIVED else 0 for chunk in selected],
                dtype=numpy.uint8,
            ),
        )


class _CentroidLookup:
    """Small exact lookup for the centroid-filter service proof."""

    def __init__(self, positions, centroids) -> None:
        self._positions = positions
        self._centroids = centroids

    def position(self, group_id, sisu_course_unit_id, representative_source_hash):
        return self._positions.get((group_id, sisu_course_unit_id, representative_source_hash))

    def centroids(self, positions):
        return numpy.asarray([self._centroids[position] for position in positions])
