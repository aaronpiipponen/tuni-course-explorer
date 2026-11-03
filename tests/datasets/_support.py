"""Shared fixtures for dataset-role settings, receipt, and verification tests."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from course_explorer.administration import administrative_json, atomic_write_private_text
from course_explorer.config import load_administrative_dataset_settings
from course_explorer.curriculum import CatalogueSummary
from course_explorer.datasets import (
    DatasetPointer,
    DatasetReceipt,
    DatasetVerification,
    clear_dataset_cache,
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
from course_explorer_admin.datasets import admin_state_root

REVISION = "a" * 40
INITIAL_ID = "0" * 32
WORKING_ID = "1" * 32


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
    *,
    dataset_id: str = INITIAL_ID,
    database_name: str = "course_explorer",
    kind: Literal["initial", "returned", "copied"] = "initial",
    predecessor_id: str | None = None,
    dump_sha256: str | None = None,
) -> DatasetReceipt:
    """Return one valid dataset receipt for the supplied identity and kind."""
    return DatasetReceipt(
        schema_version=1,
        dataset_id=dataset_id,
        database_name=database_name,
        predecessor_id=predecessor_id,
        kind=kind,
        dump_sha256=dump_sha256,
        verification=sample_verification(),
    )


def write_dataset_roles() -> Path:
    """Write one Selected and one Working receipt and pointer under the configured state root.

    The stages resolve the Working role, and a Working receipt needs a distinct Selected one beside
    it. Both roles name their own dataset and database, so the role guard accepts them. A proof that
    replaces its own database context resolves the roles without connecting to these names.
    """
    state_root = admin_state_root(load_administrative_dataset_settings())
    roles = (
        ("selected", INITIAL_ID, "course_explorer_selected_proof", "initial", None, None),
        ("working", WORKING_ID, "course_explorer_working_proof", "copied", INITIAL_ID, "b" * 64),
    )
    for role, dataset_id, database_name, kind, predecessor_id, dump_sha256 in roles:
        receipt = sample_receipt(
            dataset_id=dataset_id,
            database_name=database_name,
            kind=kind,  # type: ignore[arg-type]
            predecessor_id=predecessor_id,
            dump_sha256=dump_sha256,
        )
        directory = state_root / "datasets" / dataset_id
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        atomic_write_private_text(directory / "receipt.json", administrative_json(receipt))
        atomic_write_private_text(
            state_root / f"{role}-dataset.json",
            administrative_json(DatasetPointer(schema_version=1, dataset_id=dataset_id)),
        )
    clear_dataset_cache()
    return state_root
