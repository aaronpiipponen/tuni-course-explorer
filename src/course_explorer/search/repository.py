"""Exact-cosine read repository for current completed compatible course chunk vectors.

This is the sole search reader for `course_embedding_chunks`. It computes exact best-chunk cosine
scores with pgvector, filters to completed rows carrying the exact embedding configuration hash,
groups by canonical course and exact representative identity, and returns every qualifying version
for those groups.
"""

from __future__ import annotations

from collections.abc import Sequence

from pgvector.sqlalchemy import Vector
from sqlalchemy import bindparam, func, select
from sqlalchemy.orm import Session, sessionmaker

from course_explorer.constants import COURSE_EMBEDDING_DIMENSION
from course_explorer.db.models import (
    Course,
    CourseEmbeddingChunk,
    CourseVersion,
)
from course_explorer.embeddings.hub import subtract_hub
from course_explorer.enums import CourseEmbeddingStatus
from course_explorer.search.service import SemanticCourseScore


class SemanticSearchRepository:
    """Read current completed compatible best-chunk cosine scores through one exact SQL query."""

    def __init__(self, factory: sessionmaker[Session]) -> None:
        self._factory = factory

    def search(
        self,
        query_embedding: Sequence[float],
        *,
        hub: Sequence[float],
        min_score: float,
        embedding_configuration_hash: str,
        include_inactive: bool,
    ) -> tuple[SemanticCourseScore, ...]:
        """Return every exact-version best-chunk score at or above the threshold, unfiltered by rank."""
        hub_parameter = bindparam(
            "hub_vector", value=list(hub), type_=Vector(COURSE_EMBEDDING_DIMENSION)
        )
        query_parameter = bindparam(
            "centred_query",
            value=list(subtract_hub(query_embedding, hub)),
            type_=Vector(COURSE_EMBEDDING_DIMENSION),
        )
        centred_embedding = CourseEmbeddingChunk.embedding - hub_parameter
        score_expression = 1 - centred_embedding.cosine_distance(query_parameter)
        statement = (
            select(
                Course.group_id,
                CourseVersion.sisu_course_unit_id,
                CourseEmbeddingChunk.representative_source_hash,
                func.max(score_expression).label("score"),
            )
            .join(CourseVersion, CourseVersion.id == CourseEmbeddingChunk.course_version_id)
            .join(Course, Course.id == CourseVersion.course_id)
            .where(
                CourseEmbeddingChunk.status == CourseEmbeddingStatus.COMPLETED,
                CourseEmbeddingChunk.embedding.is_not(None),
                CourseEmbeddingChunk.embedding_configuration_hash == embedding_configuration_hash,
            )
            .group_by(
                Course.group_id,
                CourseVersion.sisu_course_unit_id,
                CourseEmbeddingChunk.representative_source_hash,
            )
            .having(func.max(score_expression) >= min_score)
            .order_by(Course.group_id, CourseVersion.sisu_course_unit_id)
        )
        if not include_inactive:
            statement = statement.where(Course.is_active.is_(True))
        with self._factory() as session:
            rows = tuple(session.execute(statement))
        return tuple(
            SemanticCourseScore(
                group_id=group_id,
                sisu_course_unit_id=sisu_course_unit_id,
                representative_source_hash=representative_source_hash,
                score=float(score),
            )
            for group_id, sisu_course_unit_id, representative_source_hash, score in rows
        )
