"""Sole persistence owner of the derived per-course embedding centroids."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import delete
from sqlalchemy.orm import Session, sessionmaker

from course_explorer.db.models import CourseEmbeddingCentroid
from course_explorer.embeddings.centroids import CourseCentroid, centroid_bytes


class CourseCentroidRepository:
    """Replace the complete centroid set of one selected dataset."""

    def __init__(self, factory: sessionmaker[Session]) -> None:
        self._factory = factory

    def replace_all_in(
        self,
        session: Session,
        centroids: Sequence[CourseCentroid],
        *,
        embedding_configuration_hash: str,
    ) -> int:
        """Replace every centroid row in the caller's transaction and return the row count.

        The caller commits, so the centroid rows can share one transaction with another derived
        table. An empty set deletes every row and leaves the table empty.
        """
        items = tuple(centroids)
        session.execute(delete(CourseEmbeddingCentroid))
        session.add_all(
            [
                CourseEmbeddingCentroid(
                    group_id=item.group_id,
                    sisu_course_unit_id=item.sisu_course_unit_id,
                    representative_source_hash=item.representative_source_hash,
                    embedding_configuration_hash=embedding_configuration_hash,
                    chunk_count=item.chunk_count,
                    centroid=centroid_bytes(item.centroid),
                )
                for item in items
            ]
        )
        return len(items)
