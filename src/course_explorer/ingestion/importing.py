"""Reusable live-source capture and current-run normalization composition.

This module sequences the accepted capture
and normalization services behind one import contract for its callers. An optional
lifecycle gate observes only durable response-unit boundaries. Normalization itself is one
indivisible transaction that is never polled, split, or interrupted.
"""

from __future__ import annotations

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, model_validator

from course_explorer.enums import IngestionRunStatus
from course_explorer.ingestion.capture import (
    CaptureBoundary,
    CaptureReport,
    capture_curriculum,
)
from course_explorer.ingestion.manifest import RawCaptureStore
from course_explorer.ingestion.normalization import (
    NormalizationPersistence,
    NormalizationReport,
    normalize_curriculum,
)
from course_explorer.ingestion.repository import CapturePersistence
from course_explorer.ingestion.source import CurriculumSource


class CurriculumImportReport(BaseModel):
    """Nested operator report for one capture/normalization run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    capture: CaptureReport
    normalization: NormalizationReport

    @model_validator(mode="after")
    def validate_consistency(self) -> CurriculumImportReport:
        if self.capture.run_id != self.normalization.run_id:
            raise ValueError("capture and normalization run IDs must match")
        if self.capture.status is not IngestionRunStatus.COMPLETED:
            raise ValueError("import report requires completed capture")
        if (
            self.capture.course_object_count
            != self.normalization.course_version_count
            + len(self.normalization.excluded_null_code_course_versions)
            or self.capture.module_object_count != self.normalization.module_version_count
        ):
            raise ValueError("capture and normalization object counts must reconcile")
        if (
            self.capture.unresolved_course_group_count
            != self.normalization.unresolved_course_group_count
            or self.capture.unresolved_module_group_count
            != self.normalization.unresolved_module_group_count
        ):
            raise ValueError("capture and normalization unresolved counts must match")
        return self


def import_curriculum(
    *,
    source: CurriculumSource,
    store: RawCaptureStore,
    capture_repository: CapturePersistence,
    normalization_repository: NormalizationPersistence,
    checkpoint_response_count: int,
    current_academic_year_start: int,
    activity_window_years: int,
    course_guide_base_url: AnyHttpUrl,
    verification_start_index: int = 0,
    on_boundary: CaptureBoundary | None = None,
) -> CurriculumImportReport | None:
    """Complete this ingestion run's live-source capture before its one normalized transaction.

    A controlled ``None`` from capture means the controller paused or stopped at a durable
    boundary, so this function returns ``None`` without parsing or writing anything. The
    capture-to-normalization gate is consulted once after completed verified capture. Once
    ``normalize_curriculum`` begins, nothing polls, signals, splits, or interrupts it, and only
    its committed transaction or its failure is reported.
    """
    capture = capture_curriculum(
        source,
        store,
        capture_repository,
        checkpoint_response_count=checkpoint_response_count,
        verification_start_index=verification_start_index,
        on_boundary=on_boundary,
    )
    if capture is None:
        return None
    if on_boundary is not None and not on_boundary(
        "before_normalization", capture.response_count, capture.response_count
    ):
        return None
    normalization = normalize_curriculum(
        store,
        normalization_repository,
        current_academic_year_start=current_academic_year_start,
        activity_window_years=activity_window_years,
        course_guide_base_url=course_guide_base_url,
    )
    return CurriculumImportReport(capture=capture, normalization=normalization)
