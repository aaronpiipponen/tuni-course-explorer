"""Shared publication builders for the current inferred-set repository tests."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from course_explorer.enums import (
    InferredCoverageState,
    InferredProducerKind,
)
from course_explorer.prerequisite.domain import (
    AndRequirement,
    CourseRequirement,
    InferenceEvidenceKind,
    InferenceEvidenceReference,
    InferenceNodeMetadata,
    InferredPrerequisiteCategory,
    InferredSetCoverage,
    InferredSetPublication,
    PrerequisiteOrigin,
)
from tests.prerequisite.conftest import PrerequisiteCatalogueSeed

GENERATED_AT = datetime(2026, 9, 14, 12, 0, tzinfo=UTC)
INPUT_HASH = "a" * 64
_DEFAULT_EXPRESSION = object()


def _metadata(*, evidenced: bool = False) -> InferenceNodeMetadata:
    """Build inferred node metadata, optionally with one evidence reference."""
    return InferenceNodeMetadata(
        confidence=Decimal("0.9"),
        requirement_ids=("R1",),
        evidence=(
            (
                InferenceEvidenceReference(
                    kind=InferenceEvidenceKind.EXPRESSION_PROPOSAL, reference_id="proposal-1"
                ),
            )
            if evidenced
            else ()
        ),
    )


def _target_expression(
    *source_group_ids: str,
    evidenced: bool = False,
    category: InferredPrerequisiteCategory = InferredPrerequisiteCategory.REQUIRED,
) -> AndRequirement:
    """Build one inferred AND tree over the supplied canonical source courses."""
    return AndRequirement(
        type="and",
        origin=PrerequisiteOrigin.INFERRED,
        inferred_category=category,
        inference=_metadata(evidenced=evidenced),
        children=tuple(
            CourseRequirement(
                type="course",
                origin=PrerequisiteOrigin.INFERRED,
                inferred_category=category,
                course_group_id=group_id,
                inference=_metadata(evidenced=evidenced),
            )
            for group_id in source_group_ids
        ),
    )


def _publication(
    seed: PrerequisiteCatalogueSeed,
    *,
    target_group_id: str | None = None,
    expression=_DEFAULT_EXPRESSION,
    coverage: InferredSetCoverage | None = None,
    coverage_state: InferredCoverageState = InferredCoverageState.COMPLETE,
    producer_kind: InferredProducerKind = InferredProducerKind.TEST,
    activity_as_of_academic_year_start: int | None = None,
    activity_window_years: int | None = None,
    generated_at: datetime = GENERATED_AT,
) -> InferredSetPublication:
    """Build one publication request bound to the seeded target activity context."""
    if expression is _DEFAULT_EXPRESSION:
        expression = _target_expression(seed.active_source_group_id)
        coverage = InferredSetCoverage(
            eligible_source_count=1, processed_source_count=1, accepted_source_count=1
        )
    if coverage is None:
        coverage = InferredSetCoverage(
            eligible_source_count=2,
            processed_source_count=2,
            accepted_source_count=1,
        )
    return InferredSetPublication(
        target_group_id=seed.active_target_group_id if target_group_id is None else target_group_id,
        activity_as_of_academic_year_start=(
            seed.activity_as_of_academic_year_start
            if activity_as_of_academic_year_start is None
            else activity_as_of_academic_year_start
        ),
        activity_window_years=(
            seed.activity_window_years if activity_window_years is None else activity_window_years
        ),
        producer_kind=producer_kind,
        producer_name="test-fixture",
        producer_version="1",
        input_hash=INPUT_HASH,
        coverage_state=coverage_state,
        coverage=coverage,
        expression=expression,
        generated_at=generated_at,
    )
