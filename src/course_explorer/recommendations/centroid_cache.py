"""Exact representative-to-centroid lookup over the shared serving centroid matrix."""

from __future__ import annotations

from collections.abc import Sequence

import numpy

from course_explorer.embeddings.shared_store import SharedServingStore


class CourseCentroidCache:
    """The shared centroid matrix of one serving artifact build.

    The matrix and its identity index are mapped from the build's read-only store, so every worker
    reads the same rows. Construction opens no database and retains no copy of the matrix.
    """

    def __init__(self, shared_store: SharedServingStore) -> None:
        self._store = shared_store

    def position(
        self,
        group_id: str,
        sisu_course_unit_id: str,
        representative_source_hash: str,
    ) -> int | None:
        """Return the centroid row index for one current representative, or `None`."""
        return self._store.position(group_id, sisu_course_unit_id, representative_source_hash)

    def centroids(self, positions: Sequence[int]) -> numpy.ndarray:
        """Return the requested mapped centroid rows as one float64 matrix."""
        return self._store.centroid_rows(positions)
