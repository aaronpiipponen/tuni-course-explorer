"""Contracts for computing and writing the two embedding hubs."""

from __future__ import annotations

from pathlib import Path

import pytest

from course_explorer.embeddings.generation import CourseEmbeddingChunkInput
from course_explorer.embeddings.hub_files import (
    CurrentChunkVectors,
    compute_embedding_hubs,
    write_hub_file,
)
from course_explorer.enums import TeachingTextField


def _chunk(field: TeachingTextField) -> CourseEmbeddingChunkInput:
    # The hub arithmetic reads only the field, so the remaining provenance is left unset.
    return CourseEmbeddingChunkInput.model_construct(field=field)


def test_hubs_average_every_unit_chunk_and_only_outcome_chunks_and_write_compact_arrays(
    tmp_path: Path,
) -> None:
    current = CurrentChunkVectors(
        chunks=(
            _chunk(TeachingTextField.NAME),
            _chunk(TeachingTextField.CONTENT),
            _chunk(TeachingTextField.OUTCOMES),
        ),
        vectors=((2.0, 0.0), (0.0, 3.0), (0.0, -1.0)),
    )

    hubs = compute_embedding_hubs(current)

    assert hubs.catalogue == pytest.approx((1 / 3, 0.0))
    assert hubs.outcomes == (0.0, -1.0)
    assert (hubs.chunk_count, hubs.outcomes_chunk_count) == (3, 1)
    target = tmp_path / "config" / "derived" / "embedding-outcomes-hub.json"
    write_hub_file(target, hubs.outcomes)
    assert target.read_text(encoding="utf-8") == "[0.0,-1.0]\n"


def test_hubs_refuse_a_dataset_without_outcome_chunks() -> None:
    current = CurrentChunkVectors(chunks=(_chunk(TeachingTextField.NAME),), vectors=((1.0, 0.0),))

    with pytest.raises(ValueError, match="at least one vector"):
        compute_embedding_hubs(current)
