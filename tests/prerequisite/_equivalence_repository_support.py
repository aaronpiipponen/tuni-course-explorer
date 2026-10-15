"""Shared publication and counting builders for the equivalence-group repository tests."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select

from course_explorer.db.models import (
    InferredEquivalenceGroup,
    InferredEquivalenceGroupMember,
)
from course_explorer.db.session import session_scope
from course_explorer.enums import InferredProducerKind
from course_explorer.prerequisite.domain import (
    EquivalenceGroupMember,
    EquivalenceGroupPublication,
    InferenceEvidenceKind,
    InferenceEvidenceReference,
    InferenceNodeMetadata,
)
from tests.prerequisite.conftest import PrerequisiteCatalogueSeed

GENERATED_AT = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)
INPUT_HASH = "a" * 64


def _inference(*, evidenced: bool = False) -> InferenceNodeMetadata:
    """Build valid group-level metadata, optionally with one evidence reference."""
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


def _member(
    seed: PrerequisiteCatalogueSeed,
    group_id: str,
    *,
    activity_as_of_academic_year_start: int | None = None,
    activity_window_years: int | None = None,
) -> EquivalenceGroupMember:
    """Build one member bound to the seeded publication activity context."""
    return EquivalenceGroupMember(
        course_group_id=group_id,
        activity_as_of_academic_year_start=(
            seed.activity_as_of_academic_year_start
            if activity_as_of_academic_year_start is None
            else activity_as_of_academic_year_start
        ),
        activity_window_years=(
            seed.activity_window_years if activity_window_years is None else activity_window_years
        ),
    )


def _members(
    seed: PrerequisiteCatalogueSeed, *group_ids: str, **context: int
) -> tuple[EquivalenceGroupMember, ...]:
    """Build one canonical sorted member tuple for the supplied canonical identities."""
    members = [_member(seed, group_id, **context) for group_id in group_ids]
    return tuple(sorted(members, key=lambda member: member.course_group_id))


def _publication(
    *,
    group_id,
    members: tuple[EquivalenceGroupMember, ...],
    producer_kind: InferredProducerKind = InferredProducerKind.TEST,
    inference: InferenceNodeMetadata | None = None,
    input_hash: str = INPUT_HASH,
    generated_at: datetime = GENERATED_AT,
) -> EquivalenceGroupPublication:
    """Build one equivalence-group publication over explicit members."""
    return EquivalenceGroupPublication(
        group_id=group_id,
        members=members,
        producer_kind=producer_kind,
        producer_name="test-fixture",
        producer_version="1",
        input_hash=input_hash,
        inference=_inference() if inference is None else inference,
        generated_at=generated_at,
    )


def _activate_all_four(seed: PrerequisiteCatalogueSeed, set_prerequisite_course_activity) -> None:
    """Activate the seeded inactive courses so four active members can be published."""
    for group_id in (seed.inactive_target_group_id, seed.inactive_source_group_id):
        set_prerequisite_course_activity(
            group_id,
            True,
            seed.activity_as_of_academic_year_start,
            seed.activity_window_years,
        )


def _group_count(factory: object) -> int:
    """Return the number of stored equivalence groups."""
    with session_scope(factory) as session:
        return session.scalar(select(func.count()).select_from(InferredEquivalenceGroup))


def _member_count(factory: object) -> int:
    """Return the number of stored equivalence group members."""
    with session_scope(factory) as session:
        return session.scalar(select(func.count()).select_from(InferredEquivalenceGroupMember))
