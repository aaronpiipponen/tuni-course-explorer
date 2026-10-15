"""Sole writer and reader for global inferred equivalence groups.

This repository owns the `inferred_equivalence_groups`/`inferred_equivalence_group_members`
trust boundary. It validates every publication against canonical membership, member activity
context, and group-level inferred evidence, replaces one caller-identified group atomically,
and is idempotent for identical semantic payloads. Reads are symmetric by every member and
fail loudly on stale or malformed durable state. Per-member activity reconciliation republishes
surviving groups and removes groups below two current members. It writes only the equivalence-group
tables.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Collection, Mapping, Sequence
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from course_explorer.db.models import (
    Course,
    InferredEquivalenceGroup,
    InferredEquivalenceGroupMember,
)
from course_explorer.db.session import session_scope
from course_explorer.enums import InferredProducerKind
from course_explorer.hashing import json_sha256
from course_explorer.prerequisite.domain import (
    CurrentEquivalenceGroup,
    EquivalenceActivityReconciliation,
    EquivalenceGroupMember,
    EquivalenceGroupPublication,
    EquivalenceGroupPublicationResult,
    EquivalenceGroupPublisher,
    EquivalenceGroupRead,
    InferenceNodeMetadata,
    InferredPublicationAction,
)


class _EquivalenceCourseContext(Protocol):
    """The five canonical columns the shared equivalence validator consumes.

    Full `Course` ORM objects satisfy it structurally. The bulk read projects exactly these
    columns, so validation never materializes a whole course or representative.
    """

    id: UUID
    group_id: str
    is_active: bool
    activity_as_of_academic_year_start: int
    activity_window_years: int


def _validate_group(
    group_id: UUID,
    members: Sequence[EquivalenceGroupMember],
    *,
    producer_kind: InferredProducerKind,
    inference: InferenceNodeMetadata,
    courses: Mapping[str, _EquivalenceCourseContext],
    require_current_context: bool = True,
) -> None:
    """Enforce the equivalence-group trust boundary.

    Shared by publication and read so one validator owns the boundary: every member must be an
    active canonical course with a matching activity snapshot, and, for an inference producer,
    the group-level metadata needs at least one evidence reference. Member shape, cardinality and
    ordering are owned by the domain `_EquivalenceGroupFields` boundary. All rejections raise
    `ValueError` naming the group. ``require_current_context=False`` relaxes only the
    generation-context equality of active inference-owned members for the retained read path.
    Test-owned members require exact context equality, and publication always uses the
    strict default.
    """
    if producer_kind is InferredProducerKind.INFERENCE and not inference.evidence:
        raise ValueError(f"equivalence group {group_id} requires at least one evidence reference")
    enforce_context = require_current_context or producer_kind is not InferredProducerKind.INFERENCE
    for member in members:
        course = courses.get(member.course_group_id)
        if course is None:
            raise ValueError(
                f"equivalence group {group_id} member {member.course_group_id} "
                "is not a canonical course"
            )
        if not course.is_active:
            raise ValueError(
                f"equivalence group {group_id} member {member.course_group_id} is inactive"
            )
        if enforce_context and (
            member.activity_as_of_academic_year_start != course.activity_as_of_academic_year_start
            or member.activity_window_years != course.activity_window_years
        ):
            raise ValueError(
                f"equivalence group {group_id} member {member.course_group_id} "
                "activity context does not match the canonical course"
            )


def _canonical_payload(
    *,
    group_id: UUID,
    members: Sequence[EquivalenceGroupMember],
    producer_kind: InferredProducerKind,
    producer_name: str,
    producer_version: str,
    input_hash: str,
    inference_dump: dict[str, object],
) -> dict[str, object]:
    """Build the one canonical payload dict whose canonical JSON bytes define `payload_hash`.

    It excludes `generated_at`, `published_at`, and database row identities so an
    exact semantic retry returns `UNCHANGED`. Members are sorted by canonical identity so one
    membership has one spelling regardless of caller order.
    """
    ordered = sorted(members, key=lambda member: member.course_group_id)
    return {
        "group_id": str(group_id),
        "members": [
            {
                "course_group_id": member.course_group_id,
                "activity_as_of_academic_year_start": member.activity_as_of_academic_year_start,
                "activity_window_years": member.activity_window_years,
            }
            for member in ordered
        ],
        "producer_kind": producer_kind.value,
        "producer_name": producer_name,
        "producer_version": producer_version,
        "input_hash": input_hash,
        "inference": inference_dump,
    }


def _validated_group_ids(keep_group_ids: Collection[UUID]) -> set[UUID]:
    """Reject malformed or duplicate group identities before one withdrawal mutation."""
    validated: set[UUID] = set()
    for group_id in keep_group_ids:
        if not isinstance(group_id, UUID):
            raise ValueError("withdrawal keep set must contain only UUID group identities")
        if group_id in validated:
            raise ValueError("withdrawal keep set must not repeat a group identity")
        validated.add(group_id)
    return validated


class InferredEquivalenceRepository(EquivalenceGroupRead, EquivalenceGroupPublisher):
    """Publish, read, and reconcile target-independent inferred equivalence groups."""

    def __init__(self, factory: sessionmaker[Session]) -> None:
        self._factory = factory

    def publish(
        self, publication: EquivalenceGroupPublication
    ) -> EquivalenceGroupPublicationResult:
        """Validate and atomically create or replace one caller-identified equivalence group."""
        member_group_ids = sorted(member.course_group_id for member in publication.members)
        payload = _canonical_payload(
            group_id=publication.group_id,
            members=publication.members,
            producer_kind=publication.producer_kind,
            producer_name=publication.producer_name,
            producer_version=publication.producer_version,
            input_hash=publication.input_hash,
            inference_dump=publication.inference.model_dump(mode="json"),
        )
        payload_hash = json_sha256(payload, ensure_ascii=False)
        with session_scope(self._factory) as session:
            courses = list(
                session.scalars(
                    select(Course)
                    .where(Course.group_id.in_(member_group_ids))
                    .order_by(Course.group_id)
                    .with_for_update()
                )
            )
            courses_by_group_id = {course.group_id: course for course in courses}
            _validate_group(
                publication.group_id,
                publication.members,
                producer_kind=publication.producer_kind,
                inference=publication.inference,
                courses=courses_by_group_id,
            )
            courses_by_id = {course.id: course for course in courses}

            group_row = session.scalar(
                select(InferredEquivalenceGroup)
                .where(InferredEquivalenceGroup.id == publication.group_id)
                .with_for_update()
            )
            if group_row is None:
                group_row = InferredEquivalenceGroup(
                    id=publication.group_id,
                    producer_kind=publication.producer_kind,
                    producer_name=publication.producer_name,
                    producer_version=publication.producer_version,
                    input_hash=publication.input_hash,
                    payload_hash=payload_hash,
                    inference=publication.inference.model_dump(mode="json"),
                    generated_at=publication.generated_at,
                )
                session.add(group_row)
                members = [
                    InferredEquivalenceGroupMember(
                        equivalence_group_id=publication.group_id,
                        course_id=courses_by_group_id[member.course_group_id].id,
                        activity_as_of_academic_year_start=(
                            member.activity_as_of_academic_year_start
                        ),
                        activity_window_years=member.activity_window_years,
                    )
                    for member in publication.members
                ]
                session.add_all(members)
                session.flush()
                session.refresh(group_row)
                return EquivalenceGroupPublicationResult(
                    action=InferredPublicationAction.CREATED,
                    current_group=self._current_group(group_row, members, courses_by_id),
                )

            existing_members = list(
                session.scalars(
                    select(InferredEquivalenceGroupMember).where(
                        InferredEquivalenceGroupMember.equivalence_group_id == publication.group_id
                    )
                )
            )
            if group_row.payload_hash == payload_hash:
                return EquivalenceGroupPublicationResult(
                    action=InferredPublicationAction.UNCHANGED,
                    current_group=self._current_group(group_row, existing_members, courses_by_id),
                )

            session.execute(
                delete(InferredEquivalenceGroupMember).where(
                    InferredEquivalenceGroupMember.equivalence_group_id == publication.group_id
                )
            )
            group_row.producer_kind = publication.producer_kind
            group_row.producer_name = publication.producer_name
            group_row.producer_version = publication.producer_version
            group_row.input_hash = publication.input_hash
            group_row.payload_hash = payload_hash
            group_row.inference = publication.inference.model_dump(mode="json")
            group_row.generated_at = publication.generated_at
            group_row.published_at = datetime.now(UTC)
            members = [
                InferredEquivalenceGroupMember(
                    equivalence_group_id=publication.group_id,
                    course_id=courses_by_group_id[member.course_group_id].id,
                    activity_as_of_academic_year_start=(member.activity_as_of_academic_year_start),
                    activity_window_years=member.activity_window_years,
                )
                for member in publication.members
            ]
            session.add_all(members)
            session.flush()
            return EquivalenceGroupPublicationResult(
                action=InferredPublicationAction.REPLACED,
                current_group=self._current_group(group_row, members, courses_by_id),
            )

    def read_for_member(self, member_group_id: str) -> tuple[CurrentEquivalenceGroup, ...]:
        """Return every validated current group containing one canonical course member."""
        return self.read_for_members((member_group_id,))[member_group_id]

    def read_for_members(
        self, member_group_ids: Collection[str]
    ) -> dict[str, tuple[CurrentEquivalenceGroup, ...]]:
        """Return each requested canonical member's exact validated current groups.

        One session loads the requested canonical courses through a five-column projection, then
        bulk-loads the distinct groups those courses belong to, all their member rows and the member
        courses, building each group once through the shared validator. Every requested known course
        gets an explicit entry, including `()` when it belongs to no group. Unknown requested IDs and
        blanks raise exactly like the singleton reader, and an empty request returns `{}` before any
        I/O. Groups are assigned only to requested IDs actually in their membership, so overlapping
        groups stay distinct and no transitive closure is computed.
        """
        requested = tuple(sorted(set(member_group_ids)))
        for member_group_id in requested:
            if not member_group_id.strip():
                raise ValueError("member_group_id must not be blank")
        if not requested:
            return {}
        with self._factory() as session:
            requested_rows = session.execute(
                select(
                    Course.id,
                    Course.group_id,
                    Course.is_active,
                    Course.activity_as_of_academic_year_start,
                    Course.activity_window_years,
                ).where(Course.group_id.in_(requested))
            ).all()
            courses_by_group_id = {row.group_id: row for row in requested_rows}
            missing = [group_id for group_id in requested if group_id not in courses_by_group_id]
            if missing:
                raise ValueError(f"unknown canonical course {missing[0]}")
            requested_course_ids = [row.id for row in requested_rows]
            group_ids = tuple(
                session.scalars(
                    select(InferredEquivalenceGroupMember.equivalence_group_id)
                    .where(InferredEquivalenceGroupMember.course_id.in_(requested_course_ids))
                    .distinct()
                )
            )
            result: dict[str, tuple[CurrentEquivalenceGroup, ...]] = {
                group_id: () for group_id in requested
            }
            if not group_ids:
                return result
            group_rows = list(
                session.scalars(
                    select(InferredEquivalenceGroup).where(
                        InferredEquivalenceGroup.id.in_(group_ids)
                    )
                )
            )
            member_rows = list(
                session.scalars(
                    select(InferredEquivalenceGroupMember).where(
                        InferredEquivalenceGroupMember.equivalence_group_id.in_(group_ids)
                    )
                )
            )
            member_course_ids = {member.course_id for member in member_rows}
            member_course_rows = session.execute(
                select(
                    Course.id,
                    Course.group_id,
                    Course.is_active,
                    Course.activity_as_of_academic_year_start,
                    Course.activity_window_years,
                ).where(Course.id.in_(member_course_ids))
            ).all()
            courses_by_id = {row.id: row for row in member_course_rows}
            members_by_group_id: dict[UUID, list[InferredEquivalenceGroupMember]] = defaultdict(
                list
            )
            for member in member_rows:
                members_by_group_id[member.equivalence_group_id].append(member)
            groups = tuple(
                sorted(
                    (
                        self._current_group(row, members_by_group_id.get(row.id, []), courses_by_id)
                        for row in group_rows
                    ),
                    key=lambda group: group.group_id,
                )
            )
            requested_set = set(requested)
            for group in groups:
                for member in group.members:
                    if member.course_group_id in requested_set:
                        result[member.course_group_id] = result[member.course_group_id] + (group,)
            return result

    def reconcile_activity(self) -> EquivalenceActivityReconciliation:
        """Remove stale members, republish survivors, and delete groups below two members."""
        updated_group_ids: list[UUID] = []
        removed_group_ids: list[UUID] = []
        with session_scope(self._factory) as session:
            group_rows = list(session.scalars(select(InferredEquivalenceGroup).with_for_update()))
            member_rows = list(
                session.scalars(select(InferredEquivalenceGroupMember).with_for_update())
            )
            member_course_ids = {member.course_id for member in member_rows}
            courses_by_id = (
                {
                    loaded.id: loaded
                    for loaded in session.scalars(
                        select(Course).where(Course.id.in_(member_course_ids)).with_for_update()
                    )
                }
                if member_course_ids
                else {}
            )
            members_by_group_id: dict[UUID, list[InferredEquivalenceGroupMember]] = defaultdict(
                list
            )
            for member in member_rows:
                members_by_group_id[member.equivalence_group_id].append(member)

            for group_row in group_rows:
                current_members = members_by_group_id.get(group_row.id, [])
                survivors = [
                    member
                    for member in current_members
                    if self._member_is_current(
                        member, courses_by_id, producer_kind=group_row.producer_kind
                    )
                ]
                if len(survivors) == len(current_members) and len(survivors) >= 2:
                    continue
                if len(survivors) < 2:
                    session.execute(
                        delete(InferredEquivalenceGroupMember).where(
                            InferredEquivalenceGroupMember.equivalence_group_id == group_row.id
                        )
                    )
                    session.execute(
                        delete(InferredEquivalenceGroup).where(
                            InferredEquivalenceGroup.id == group_row.id
                        )
                    )
                    removed_group_ids.append(group_row.id)
                    continue
                session.execute(
                    delete(InferredEquivalenceGroupMember).where(
                        InferredEquivalenceGroupMember.equivalence_group_id == group_row.id
                    )
                )
                group_members = [
                    EquivalenceGroupMember(
                        course_group_id=courses_by_id[member.course_id].group_id,
                        activity_as_of_academic_year_start=(
                            member.activity_as_of_academic_year_start
                        ),
                        activity_window_years=member.activity_window_years,
                    )
                    for member in survivors
                ]
                group_row.payload_hash = json_sha256(
                    _canonical_payload(
                        group_id=group_row.id,
                        members=group_members,
                        producer_kind=group_row.producer_kind,
                        producer_name=group_row.producer_name,
                        producer_version=group_row.producer_version,
                        input_hash=group_row.input_hash,
                        inference_dump=group_row.inference,
                    ),
                    ensure_ascii=False,
                )
                group_row.published_at = datetime.now(UTC)
                session.add_all(
                    InferredEquivalenceGroupMember(
                        equivalence_group_id=group_row.id,
                        course_id=member.course_id,
                        activity_as_of_academic_year_start=(
                            member.activity_as_of_academic_year_start
                        ),
                        activity_window_years=member.activity_window_years,
                    )
                    for member in survivors
                )
                updated_group_ids.append(group_row.id)
        return EquivalenceActivityReconciliation(
            updated_group_ids=tuple(sorted(updated_group_ids)),
            removed_group_ids=tuple(sorted(removed_group_ids)),
        )

    def withdraw_absent_inference_groups(
        self, keep_group_ids: Collection[UUID]
    ) -> tuple[UUID, ...]:
        """Remove inference-owned groups absent from one validated caller-kept exact-group set.

        It locks the inference-production group rows and deletes only their group/member
        rows. Test groups, per-target inferred sets, and proposal/raw evidence are never touched.
        ``reconcile_activity`` owns the member-level activity pruning and below-two-member removal
        that runs before this withdrawal, so the keep set is exactly the prepared current exact
        groups. Repeated calls are a no-op because a removed identity is absent.
        """
        keep = _validated_group_ids(keep_group_ids)
        with session_scope(self._factory) as session:
            group_rows = list(
                session.scalars(
                    select(InferredEquivalenceGroup)
                    .where(InferredEquivalenceGroup.producer_kind == InferredProducerKind.INFERENCE)
                    .with_for_update()
                )
            )
            absent = tuple(
                sorted(group_row.id for group_row in group_rows if group_row.id not in keep)
            )
            if absent:
                session.execute(
                    delete(InferredEquivalenceGroupMember).where(
                        InferredEquivalenceGroupMember.equivalence_group_id.in_(absent)
                    )
                )
                session.execute(
                    delete(InferredEquivalenceGroup).where(InferredEquivalenceGroup.id.in_(absent))
                )
        return absent

    def _current_group(
        self,
        group_row: InferredEquivalenceGroup,
        member_rows: Sequence[InferredEquivalenceGroupMember],
        courses_by_id: Mapping[UUID, _EquivalenceCourseContext],
    ) -> CurrentEquivalenceGroup:
        """Map one stored group and its member rows to the validated read/publish contract."""
        missing_course_ids = [
            member.course_id for member in member_rows if member.course_id not in courses_by_id
        ]
        if missing_course_ids:
            raise ValueError(
                f"equivalence group {group_row.id} references unknown membership "
                f"{sorted(str(course_id) for course_id in missing_course_ids)}"
            )
        ordered_rows = sorted(
            member_rows, key=lambda member: courses_by_id[member.course_id].group_id
        )
        members = tuple(
            EquivalenceGroupMember(
                course_group_id=courses_by_id[member.course_id].group_id,
                activity_as_of_academic_year_start=member.activity_as_of_academic_year_start,
                activity_window_years=member.activity_window_years,
            )
            for member in ordered_rows
        )
        courses_by_group_id = {course.group_id: course for course in (courses_by_id.values())}
        inference = self._parse_inference(group_row)
        _validate_group(
            group_row.id,
            members,
            producer_kind=group_row.producer_kind,
            inference=inference,
            courses=courses_by_group_id,
            require_current_context=False,
        )
        return CurrentEquivalenceGroup(
            group_id=group_row.id,
            members=members,
            producer_kind=group_row.producer_kind,
            producer_name=group_row.producer_name,
            producer_version=group_row.producer_version,
            input_hash=group_row.input_hash,
            inference=inference,
            generated_at=group_row.generated_at,
            payload_hash=group_row.payload_hash,
            published_at=group_row.published_at,
        )

    def _parse_inference(self, group_row: InferredEquivalenceGroup) -> InferenceNodeMetadata:
        """Parse stored group-level evidence metadata, failing loudly when malformed."""
        try:
            return InferenceNodeMetadata.model_validate(group_row.inference)
        except ValidationError as error:
            raise ValueError(
                f"equivalence group {group_row.id} has malformed inference metadata"
            ) from error

    @staticmethod
    def _member_is_current(
        member: InferredEquivalenceGroupMember,
        courses_by_id: Mapping[UUID, Course],
        *,
        producer_kind: InferredProducerKind,
    ) -> bool:
        """Return whether a stored member matches its live canonical course context.

        An active inference-owned member is current regardless of its stored generation context,
        because the canonical activity rule already owns its eligibility and a calendar-only
        rollover must retain it. A test-owned member requires exact context equality.
        """
        course = courses_by_id.get(member.course_id)
        if course is None or not course.is_active:
            return False
        if producer_kind is InferredProducerKind.INFERENCE:
            return True
        return (
            member.activity_as_of_academic_year_start == course.activity_as_of_academic_year_start
            and member.activity_window_years == course.activity_window_years
        )
