"""The centroid table's persistence and identity contract over a disposable database."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from course_explorer.config import COURSE_EMBEDDING_DIMENSION
from course_explorer.db.models import CourseEmbeddingCentroid
from course_explorer.db.session import session_scope
from course_explorer.embeddings.centroid_repository import CourseCentroidRepository
from course_explorer.embeddings.centroids import CourseCentroid
from course_explorer.enums import CourseEmbeddingStatus
from tests.db import _schema_support
from tests.db._schema_support import embedding_chunk_row

pytestmark = [pytest.mark.integration]


def _centroid(group_id: str = "derived-course-0") -> CourseCentroid:
    return CourseCentroid(
        group_id=group_id,
        sisu_course_unit_id="derived-course-v0",
        representative_source_hash="d" * 64,
        chunk_count=1,
        centroid=(0.0,) * COURSE_EMBEDDING_DIMENSION,
    )


def test_centroid_repository_replaces_the_complete_centroid_set(
    database: tuple[object, object],
) -> None:
    """A complete replacement stores the configured rows with their identity fields."""
    factory, ids = _schema_support.two_course_versions.__wrapped__(database)
    with session_scope(factory) as session:
        session.add(
            embedding_chunk_row(
                ids["version_ids"][0],
                representative_source_hash="d" * 64,
                embedding_configuration_hash="b" * 64,
                status=CourseEmbeddingStatus.COMPLETED,
                embedding=[0.0] * COURSE_EMBEDDING_DIMENSION,
            )
        )
    repository = CourseCentroidRepository(factory)
    with session_scope(factory) as session:
        assert (
            repository.replace_all_in(
                session,
                (_centroid(),),
                embedding_configuration_hash="b" * 64,
            )
            == 1
        )
    with session_scope(factory) as session:
        row = session.execute(select(CourseEmbeddingCentroid)).scalar_one()
    assert row.group_id == "derived-course-0"
    assert row.embedding_configuration_hash == "b" * 64
    assert row.chunk_count == 1
    assert len(row.centroid) == COURSE_EMBEDDING_DIMENSION * 8

    with session_scope(factory) as session:
        assert repository.replace_all_in(session, (), embedding_configuration_hash="b" * 64) == 0
    with session_scope(factory) as session:
        assert session.execute(select(CourseEmbeddingCentroid)).all() == []
