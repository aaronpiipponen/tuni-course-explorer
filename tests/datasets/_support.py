"""Shared fixtures for selected-dataset settings, receipt, and verification tests."""

from __future__ import annotations

from course_explorer.curriculum import CatalogueSummary
from course_explorer.datasets import (
    DatasetReceipt,
    DatasetVerification,
)
from course_explorer.embeddings.generation import (
    CourseEmbeddingCoverageCount,
    CourseEmbeddingCoverageReport,
)
from course_explorer.enums import (
    TeachingTextField,
    TeachingTextLanguage,
    TeachingTextOrigin,
)
from course_explorer.inference.diagnostics import InferenceCoverageSummary
from course_explorer.teaching_text.service import (
    TeachingTextCoverageCount,
    TeachingTextCoverageReport,
)

REVISION = "a" * 40
INITIAL_ID = "0" * 32


def sample_verification() -> DatasetVerification:
    """Return one valid two-course, one-chunk, uncovered verification report."""
    fields = tuple(
        TeachingTextCoverageCount(
            field=field,
            language=language,
            official_count=1,
            derived_count=0,
            stale_count=0,
            missing_count=0,
        )
        for field in TeachingTextField
        for language in TeachingTextLanguage
    )
    cells = tuple(
        CourseEmbeddingCoverageCount(
            field=field,
            language=language,
            origin=origin,
            pending_count=0,
            completed_count=1
            if (field, language, origin)
            == (TeachingTextField.CONTENT, TeachingTextLanguage.FI, TeachingTextOrigin.OFFICIAL)
            else 0,
            failed_count=0,
        )
        for field in TeachingTextField
        for language in TeachingTextLanguage
        for origin in TeachingTextOrigin
    )
    return DatasetVerification(
        schema_version=1,
        alembic_revision="fixture-schema",
        table_row_counts={"courses": 2, "course_embedding_chunks": 1},
        catalogue=CatalogueSummary(
            curriculum_period_count=1,
            canonical_course_count=2,
            active_course_count=1,
            course_version_count=2,
            canonical_module_count=0,
            module_version_count=0,
        ),
        teaching_text=TeachingTextCoverageReport(
            canonical_course_count=2,
            representative_course_count=2,
            no_representative_course_count=0,
            name_only_course_count=0,
            unembeddable_course_count=0,
            fields=fields,
            stale_texts=(),
            unrepresented_group_ids=(),
        ),
        embeddings=CourseEmbeddingCoverageReport(
            total_chunk_count=1,
            pending_count=0,
            completed_count=1,
            failed_count=0,
            fields=cells,
        ),
        inference=InferenceCoverageSummary(
            schema_version=1,
            eligible_targets=2,
            retained_complete_targets=0,
            published_targets=0,
            uncovered_targets=2,
            current_equivalence_groups=0,
            historical_proposal_rows=0,
            generation_counts=(),
            cycle_id=None,
            stage=None,
            multiview_completed=0,
            rerank_completed=0,
            rerank_skipped=0,
            inference_completed=0,
            inference_skipped=0,
            failed_targets=0,
            pending_targets=0,
        ),
    )


def sample_receipt(
    *, dataset_id: str = INITIAL_ID, database_name: str = "course_explorer"
) -> DatasetReceipt:
    """Return one initial dataset receipt for the supplied identity."""
    return DatasetReceipt(
        schema_version=1,
        dataset_id=dataset_id,
        database_name=database_name,
        predecessor_id=None,
        kind="initial",
        dump_sha256=None,
        verification=sample_verification(),
    )
