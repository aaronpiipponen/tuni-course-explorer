"""Opt-in PostgreSQL proofs for derived teaching-text and embedding schema constraints."""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import DataError, IntegrityError

from course_explorer.constants import COURSE_EMBEDDING_DIMENSION
from course_explorer.db.models import (
    CourseEmbeddingChunk,
    CourseVersion,
    DerivedCourseText,
)
from course_explorer.db.session import session_scope
from course_explorer.enums import (
    CourseEmbeddingStatus,
    TeachingTextField,
    TeachingTextLanguage,
)
from tests.db._schema_support import (
    constraint_name,
    derived_text_row,
    embedding_chunk_row,
)
from tests.db._schema_support import two_course_versions as two_course_versions

pytestmark = [
    pytest.mark.integration,
]


def test_derived_course_text_constraints_and_cascade(
    two_course_versions: tuple[object, dict[str, uuid.UUID]],
) -> None:
    """Derived rows keep source/target provenance distinct and cascade with their version."""
    factory, ids = two_course_versions
    version_ids = ids["version_ids"]

    with pytest.raises(IntegrityError) as same_language:
        with session_scope(factory) as session:
            session.add(
                derived_text_row(
                    version_ids[0],
                    language=TeachingTextLanguage.FI,
                    source_language=TeachingTextLanguage.FI,
                )
            )
    assert constraint_name(same_language.value) == (
        "ck_derived_course_texts_source_and_target_languages_differ"
    )

    with session_scope(factory) as session:
        session.add(
            derived_text_row(
                version_ids[0],
                field=TeachingTextField.CONTENT,
                language=TeachingTextLanguage.EN,
            )
        )
        session.add(
            derived_text_row(
                version_ids[1],
                field=TeachingTextField.NAME,
                language=TeachingTextLanguage.FI,
                source_language=TeachingTextLanguage.EN,
                text="Johdanto",
            )
        )

    with session_scope(factory) as session:
        version = session.get(CourseVersion, version_ids[0])
        assert version is not None
        session.delete(version)
    with session_scope(factory) as session:
        remaining = list(session.scalars(select(DerivedCourseText)))
    assert len(remaining) == 1
    assert remaining[0].course_version_id == version_ids[1]


def test_course_embedding_constraints_vector_dimension_and_cascade(
    two_course_versions: tuple[object, dict[str, uuid.UUID]],
) -> None:
    """Origin provenance is enforced. Vectors round-trip at the exact dimension and cascade."""
    factory, ids = two_course_versions
    version_ids = ids["version_ids"]

    with pytest.raises(IntegrityError) as official_hashes:
        with session_scope(factory) as session:
            session.add(embedding_chunk_row(version_ids[0], effective_text_hash="f" * 64))
    assert constraint_name(official_hashes.value) == (
        "ck_course_embedding_chunks_origin_provenance_consistent"
    )

    with pytest.raises(DataError):
        with session_scope(factory) as session:
            session.add(
                embedding_chunk_row(
                    version_ids[0],
                    embedding=[0.25] * (COURSE_EMBEDDING_DIMENSION - 1),
                    status=CourseEmbeddingStatus.COMPLETED,
                )
            )

    vector = [0.25] * COURSE_EMBEDDING_DIMENSION
    with session_scope(factory) as session:
        session.add(
            embedding_chunk_row(
                version_ids[0], embedding=vector, status=CourseEmbeddingStatus.COMPLETED
            )
        )
        session.add(
            embedding_chunk_row(
                version_ids[1],
                field=TeachingTextField.NAME,
                language=TeachingTextLanguage.FI,
            )
        )

    with session_scope(factory) as session:
        stored = session.scalars(
            select(CourseEmbeddingChunk).where(
                CourseEmbeddingChunk.course_version_id == version_ids[0]
            )
        ).one()
        assert stored.embedding is not None
        assert len(stored.embedding) == COURSE_EMBEDDING_DIMENSION
        assert all(component == pytest.approx(0.25) for component in stored.embedding)

    with session_scope(factory) as session:
        version = session.get(CourseVersion, version_ids[0])
        assert version is not None
        session.delete(version)
    with session_scope(factory) as session:
        remaining = list(session.scalars(select(CourseEmbeddingChunk)))
    assert len(remaining) == 1
    assert remaining[0].course_version_id == version_ids[1]
