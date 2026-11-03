"""Contract proof for the shared centroid and descriptive-chunk store."""

from __future__ import annotations

from pathlib import Path

import pytest

from course_explorer.constants import COURSE_EMBEDDING_DIMENSION
from course_explorer.embeddings.centroids import CourseCentroid
from course_explorer.embeddings.shared_store import SharedServingStore


def _centroid(group_id: str) -> CourseCentroid:
    return CourseCentroid(
        group_id=group_id,
        sisu_course_unit_id=f"{group_id}-version",
        representative_source_hash="a" * 64,
        chunk_count=1,
        centroid=(0.0,) * COURSE_EMBEDDING_DIMENSION,
    )


def test_shared_store_rejects_another_dataset_identity_or_academic_year(
    tmp_path: Path,
) -> None:
    """A store opened under another key or academic year is refused."""
    root = tmp_path / "store"
    SharedServingStore.build(
        root,
        dataset_key="key-one",
        academic_year_start=2026,
        centroids=(_centroid("course-a"),),
        chunks=(),
    )

    opened = SharedServingStore.open(root, dataset_key="key-one", academic_year_start=2026)
    assert opened.centroid_index == {("course-a", "course-a-version", "a" * 64): 0}

    with pytest.raises(ValueError, match="scripts/admin.py serving-artifacts"):
        SharedServingStore.open(root, dataset_key="key-two", academic_year_start=2026)
    with pytest.raises(ValueError, match="scripts/admin.py serving-artifacts"):
        SharedServingStore.open(root, dataset_key="key-one", academic_year_start=2027)
