"""Opt-in PostgreSQL proof that the nearest-chunk read fills its requested limit under filters."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import Engine

from course_explorer.config import load_search_settings
from course_explorer.constants import COURSE_EMBEDDING_DIMENSION
from course_explorer.curriculum_repository import CurriculumRepository
from course_explorer.db.models import CurriculumPeriod
from course_explorer.db.session import session_scope
from course_explorer.embeddings.centroids import CourseCentroid
from course_explorer.embeddings.generation import embedding_configuration_sha256
from course_explorer.embeddings.read import TeachingEmbeddingRepository
from course_explorer.embeddings.shared_store import SharedServingStore
from course_explorer.enums import TeachingTextField, TeachingTextLanguage
from tests.search._repository_support import (
    CURRENT_YEAR,
    _add_chunk,
    _add_course,
    _add_version,
    embedding_settings,
    seed_neighbors,
)

pytestmark = [
    pytest.mark.integration,
]


def test_nearest_chunk_read_fills_the_requested_limit_under_filters(
    database: tuple[Engine, object],
    tmp_path: Path,
) -> None:
    """One basis chunk receives the configured limit when activity and exclusions leave enough rows."""
    _, factory = database
    eligible = 45
    excluded_groups = {f"group-excluded-{index}" for index in range(5)}
    inactive_groups = {f"group-inactive-{index}" for index in range(5)}
    with session_scope(factory) as session:
        session.add(CurriculumPeriod(id="period-2026", academic_year_start=CURRENT_YEAR))
        session.flush()
        basis_course = _add_course(session, "group-basis", is_active=True)
        basis_version = _add_version(
            session,
            course_id=basis_course,
            source_id="source-basis",
            index=700,
            source_hash="7" * 64,
            code="BASIS.1",
            name_fi="Peruskurssi",
            name_en="Basis course",
            membership_year=CURRENT_YEAR,
        )
        _add_chunk(
            session,
            version_id=basis_version,
            source_hash="7" * 64,
            field=TeachingTextField.CONTENT,
            language=TeachingTextLanguage.EN,
            chunk_index=0,
            text="basis chunk",
            cosine=1.0,
        )
        for index in range(eligible):
            group_id = f"group-eligible-{index:02d}"
            course_id = _add_course(session, group_id, is_active=True)
            version_id = _add_version(
                session,
                course_id=course_id,
                source_id=f"source-eligible-{index:02d}",
                index=800 + index,
                source_hash=f"{index:02d}" * 32,
                code=f"ELIG.1{index:02d}",
                name_fi=None,
                name_en=f"Eligible {index}",
                membership_year=CURRENT_YEAR,
            )
            _add_chunk(
                session,
                version_id=version_id,
                source_hash=f"{index:02d}" * 32,
                field=TeachingTextField.CONTENT,
                language=TeachingTextLanguage.EN,
                chunk_index=0,
                text=f"eligible chunk {index}",
                cosine=0.99 - index * 0.01,
            )
        for index, group_id in enumerate(sorted(excluded_groups)):
            course_id = _add_course(session, group_id, is_active=True)
            version_id = _add_version(
                session,
                course_id=course_id,
                source_id=f"source-excluded-{index}",
                index=900 + index,
                source_hash=f"{index + 50:02d}" * 32,
                code=f"EXCL.1{index}",
                name_fi=None,
                name_en=f"Excluded {index}",
                membership_year=CURRENT_YEAR,
            )
            _add_chunk(
                session,
                version_id=version_id,
                source_hash=f"{index + 50:02d}" * 32,
                field=TeachingTextField.CONTENT,
                language=TeachingTextLanguage.EN,
                chunk_index=0,
                text=f"excluded chunk {index}",
                cosine=1.0,
            )
        for index, group_id in enumerate(sorted(inactive_groups)):
            course_id = _add_course(session, group_id, is_active=False)
            version_id = _add_version(
                session,
                course_id=course_id,
                source_id=f"source-inactive-{index}",
                index=950 + index,
                source_hash=f"{index + 60:02d}" * 32,
                code=f"INAC.1{index}",
                name_fi=None,
                name_en=f"Inactive {index}",
                membership_year=CURRENT_YEAR,
            )
            _add_chunk(
                session,
                version_id=version_id,
                source_hash=f"{index + 60:02d}" * 32,
                field=TeachingTextField.CONTENT,
                language=TeachingTextLanguage.EN,
                chunk_index=0,
                text=f"inactive chunk {index}",
                cosine=1.0,
            )

    configuration_hash = embedding_configuration_sha256(embedding_settings())
    top_k = load_search_settings().recommendation_chunk_top_k
    represented = CurriculumRepository(factory).get_represented_summaries(["group-basis"])
    seed_neighbors(factory, rows_per_chunk=128)
    repository = TeachingEmbeddingRepository(factory)
    all_chunks = repository.read_stored_chunks(
        represented,
        embedding_configuration_hash=configuration_hash,
    )
    store = SharedServingStore.build(
        tmp_path / "store",
        dataset_key="nearest-test",
        academic_year_start=CURRENT_YEAR,
        centroids=(
            CourseCentroid(
                group_id="group-basis",
                sisu_course_unit_id="source-basis",
                representative_source_hash="0" * 64,
                chunk_count=1,
                centroid=(0.0,) * COURSE_EMBEDDING_DIMENSION,
            ),
        ),
        chunks=all_chunks,
    )
    basis_chunks = store.chunks_for(represented)
    assert len(basis_chunks) == 1

    neighbors = repository.find_nearest_chunks(
        basis_chunks,
        embedding_configuration_hash=configuration_hash,
        top_k=top_k,
        active_only=True,
        excluded_group_ids={"group-basis", *excluded_groups},
    )

    assert len(neighbors) == top_k
    returned_groups = {neighbor.group_id for neighbor in neighbors}
    assert returned_groups == {f"group-eligible-{index:02d}" for index in range(40)}
    assert not returned_groups & excluded_groups
    assert not returned_groups & inactive_groups
