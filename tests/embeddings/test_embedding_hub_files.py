"""Contracts for computing and writing the two embedding hubs."""

from __future__ import annotations

from pathlib import Path

import pytest

from course_explorer.embeddings.centroids import compute_course_centroids
from course_explorer.embeddings.generation import CourseEmbeddingChunkInput
from course_explorer.embeddings.hub_files import (
    CurrentChunkVectors,
    compute_embedding_hubs,
    write_hub_file,
)
from course_explorer.enums import TeachingTextField


def _chunk(
    field: TeachingTextField,
    *,
    group_id: str = "course-a",
    sisu: str = "sisu-a",
    source_hash: str = "a" * 64,
) -> CourseEmbeddingChunkInput:
    # The hub and centroid arithmetic reads the field and the representative identity.
    return CourseEmbeddingChunkInput.model_construct(
        group_id=group_id,
        sisu_course_unit_id=sisu,
        representative_source_hash=source_hash,
        field=field,
    )


def test_hubs_average_every_unit_chunk_and_only_outcome_chunks_and_write_compact_arrays(
    tmp_path: Path,
) -> None:
    """Average catalogue and outcome hubs over unit chunks and write a compact array."""
    current = CurrentChunkVectors(
        chunks=(
            _chunk(TeachingTextField.NAME),
            _chunk(TeachingTextField.CONTENT),
            _chunk(TeachingTextField.OUTCOMES),
        ),
        vectors=((2.0, 0.0), (0.0, 3.0), (0.0, -1.0)),
        stored=(),
    )

    hubs = compute_embedding_hubs(current)

    assert hubs.catalogue == pytest.approx((1 / 3, 0.0))
    assert hubs.outcomes == (0.0, -1.0)
    assert (hubs.chunk_count, hubs.outcomes_chunk_count) == (3, 1)
    target = tmp_path / "build" / "embedding-outcomes-hub.json"
    write_hub_file(target, hubs.outcomes)
    assert target.read_text(encoding="utf-8") == "[0.0,-1.0]\n"

    centroids = compute_course_centroids(
        (
            _chunk(TeachingTextField.CONTENT),
            _chunk(TeachingTextField.OUTCOMES),
            _chunk(TeachingTextField.NAME),
        ),
        ((1.0, 0.0), (0.0, 1.0), (1.0, 1.0)),
        catalogue_hub=hubs.catalogue,
        outcomes_hub=hubs.outcomes,
    )
    assert len(centroids) == 1
    centroid = centroids[0]
    assert centroid.group_id == "course-a"
    assert centroid.sisu_course_unit_id == "sisu-a"
    assert centroid.chunk_count == 2
    assert centroid.centroid == pytest.approx((1 / 2**0.5, 1 / 2**0.5))


def test_hubs_refuse_a_dataset_without_outcome_chunks() -> None:
    """Refuse a dataset that holds no outcome chunk."""
    current = CurrentChunkVectors(
        chunks=(_chunk(TeachingTextField.NAME),), vectors=((1.0, 0.0),), stored=()
    )

    with pytest.raises(ValueError, match="at least one vector"):
        compute_embedding_hubs(current)
