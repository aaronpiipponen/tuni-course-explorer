"""Sole writer and reader for the current final inferred prerequisite sets.

This repository owns the `inferred_prerequisite_sets` trust boundary. It validates every
publication against active canonical target identity, activity context, canonical inferred
source courses, evidence policy, and coverage before writing, replaces one target's current
set atomically, is idempotent for identical payloads, and distinguishes unavailable, stale,
partial, and complete reads. It never writes official curriculum rows. Its activity reconciliation
also
supports an explicit policy map that removes inference-produced sets a fresh cohort stops
supporting, and it exposes a scoped projection of live inference targets.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from datetime import UTC, datetime

from sqlalchemy import cast, delete, func, literal, select
from sqlalchemy.dialects.postgresql import JSONB, JSONPATH
from sqlalchemy.orm import Session, sessionmaker

from course_explorer.db.models import (
    Course,
    InferredPrerequisiteSet,
)
from course_explorer.db.session import session_scope
from course_explorer.enums import InferredProducerKind
from course_explorer.hashing import json_sha256
from course_explorer.prerequisite.domain import (
    AndRequirement,
    CourseRequirement,
    CurrentInferredSet,
    InferredActivityReconciliation,
    InferredPublicationAction,
    InferredReadState,
    InferredSetCoverage,
    InferredSetPublication,
    InferredSetPublicationResult,
    InferredSetPublisher,
    InferredSetRead,
    InferredSetReadResult,
    OrRequirement,
    PrerequisiteExpression,
    PrerequisiteOrigin,
    dump_prerequisite_expression,
    expression_course_leaf_group_ids,
    parse_prerequisite_expression,
)
from course_explorer.validation import require_sha256

_ALLOWED_INFERRED_NODES = (CourseRequirement, AndRequirement, OrRequirement)


def _canonical_ids_for_expression(
    session: Session, expression: PrerequisiteExpression | None
) -> set[str]:
    """Return the canonical group IDs of one expression's course leaves only.

    The shared inferred-store validator rejects unknown or non-canonical source leaves, so the read
    is scoped to the exact leaf identities the expression names. Publication and read touch only
    those leaves. A `None`
    expression yields the empty set and the validator handles it directly.
    """
    leaves = expression_course_leaf_group_ids(expression)
    if not leaves:
        return set()
    return set(session.scalars(select(Course.group_id).where(Course.group_id.in_(leaves))))


def _validate_current_inference_input_hashes(
    mapping: Mapping[str, str | None],
) -> dict[str, str | None]:
    """Validate one explicit policy reconciliation map before any mutation."""
    validated: dict[str, str | None] = {}
    for target_group_id, identity in mapping.items():
        if not isinstance(target_group_id, str) or not target_group_id.strip():
            raise ValueError("current inference input hashes require nonblank target group IDs")
        if identity is not None:
            require_sha256(identity, "current inference input hash")
        validated[target_group_id] = identity
    return validated


def _validate_storable_expression(
    expression: PrerequisiteExpression | None,
    *,
    producer_kind: InferredProducerKind,
    accepted_source_count: int,
    target_group_id: str,
    canonical_group_ids: Collection[str],
) -> tuple[str, ...]:
    """Enforce the inferred-store trust boundary and return sorted distinct source IDs.

    Shared by publication and read so one validator owns the boundary. A `None` expression is
    the complete/partial empty result and requires zero accepted sources. A non-`None`
    expression must contain only inferred course/AND/OR nodes, an explicit required/recommended
    `inferred_category` on every occurrence, non-self canonical source leaves, evidence required
    for the inference producer, and exactly the declared distinct accepted source count. All
    domain rejections raise `ValueError`.
    """
    if expression is None:
        if accepted_source_count != 0:
            raise ValueError("an empty inferred expression requires zero accepted sources")
        return ()
    sources: set[str] = set()
    _collect_inferred_sources(
        expression,
        producer_kind=producer_kind,
        target_group_id=target_group_id,
        canonical_group_ids=canonical_group_ids,
        sources=sources,
    )
    if not sources:
        raise ValueError("a non-empty inferred expression must contain at least one course leaf")
    if accepted_source_count != len(sources):
        raise ValueError(
            "accepted_source_count must equal the number of distinct inferred source courses"
        )
    return tuple(sorted(sources))


def _collect_inferred_sources(
    node: PrerequisiteExpression,
    *,
    producer_kind: InferredProducerKind,
    target_group_id: str,
    canonical_group_ids: Collection[str],
    sources: set[str],
) -> None:
    """Walk one expression node, validating inferred store policy and collecting leaves."""
    if not isinstance(node, _ALLOWED_INFERRED_NODES):
        raise ValueError(
            f"inferred sets support only course/and/or nodes, not {type(node).__name__}"
        )
    if node.origin is not PrerequisiteOrigin.INFERRED:
        raise ValueError("every node in an inferred set must carry inferred origin")
    if producer_kind is InferredProducerKind.INFERENCE and not node.inference.evidence:
        raise ValueError("inference-produced nodes require at least one evidence reference")
    if isinstance(node, CourseRequirement):
        if node.course_group_id not in canonical_group_ids:
            raise ValueError(
                f"inferred source course {node.course_group_id} is not a canonical course"
            )
        if node.course_group_id == target_group_id:
            raise ValueError("an inferred set must not reference its own target as a source")
        sources.add(node.course_group_id)
        return
    for child in node.children:
        _collect_inferred_sources(
            child,
            producer_kind=producer_kind,
            target_group_id=target_group_id,
            canonical_group_ids=canonical_group_ids,
            sources=sources,
        )


def _row_to_current_set(
    row: InferredPrerequisiteSet, *, target_group_id: str
) -> CurrentInferredSet:
    """Map one persisted row and its canonical target identity to the read/publish contract."""
    return CurrentInferredSet(
        set_id=row.id,
        target_group_id=target_group_id,
        activity_as_of_academic_year_start=row.activity_as_of_academic_year_start,
        activity_window_years=row.activity_window_years,
        producer_kind=row.producer_kind,
        producer_name=row.producer_name,
        producer_version=row.producer_version,
        input_hash=row.input_hash,
        coverage_state=row.coverage_state,
        coverage=InferredSetCoverage(
            eligible_source_count=row.eligible_source_count,
            processed_source_count=row.processed_source_count,
            accepted_source_count=row.accepted_source_count,
        ),
        expression=(
            None if row.expression is None else parse_prerequisite_expression(row.expression)
        ),
        generated_at=row.generated_at,
        payload_hash=row.payload_hash,
        published_at=row.published_at,
    )


def _canonical_payload(
    publication: InferredSetPublication, expression_dump: dict[str, object] | None
) -> dict[str, object]:
    """Build the one canonical payload dict whose canonical JSON bytes define `payload_hash`."""
    return {
        "target_group_id": publication.target_group_id,
        "activity_as_of_academic_year_start": publication.activity_as_of_academic_year_start,
        "activity_window_years": publication.activity_window_years,
        "producer_kind": publication.producer_kind.value,
        "producer_name": publication.producer_name,
        "producer_version": publication.producer_version,
        "input_hash": publication.input_hash,
        "coverage_state": publication.coverage_state.value,
        "eligible_source_count": publication.coverage.eligible_source_count,
        "processed_source_count": publication.coverage.processed_source_count,
        "accepted_source_count": publication.coverage.accepted_source_count,
        "expression": expression_dump,
    }


class InferredPrerequisiteRepository(InferredSetRead, InferredSetPublisher):
    """Publish, read, and reconcile the one current inferred set per canonical target."""

    def __init__(self, factory: sessionmaker[Session]) -> None:
        self._factory = factory

    def read(self, target_group_id: str) -> InferredSetReadResult:
        """Return availability, stale context, or the current validated inferred set.

        An inactive target is always stale. A test-produced row is stale when its stored generation
        context differs from the live course. An active inference-owned row is current with its
        stored context, because its eligibility is owned by the canonical activity rule
        and a calendar-only rollover must not hide retained accepted output.
        """
        if not target_group_id.strip():
            raise ValueError("target_group_id must not be blank")
        with self._factory() as session:
            course = session.scalar(select(Course).where(Course.group_id == target_group_id))
            if course is None:
                raise ValueError(f"unknown canonical target course {target_group_id}")
            row = session.scalar(
                select(InferredPrerequisiteSet).where(
                    InferredPrerequisiteSet.target_course_id == course.id
                )
            )
            if row is None:
                return InferredSetReadResult(
                    target_group_id=target_group_id, state=InferredReadState.UNAVAILABLE
                )
            context_matches = (
                row.activity_as_of_academic_year_start == course.activity_as_of_academic_year_start
                and row.activity_window_years == course.activity_window_years
            )
            if not course.is_active or (
                row.producer_kind is not InferredProducerKind.INFERENCE and not context_matches
            ):
                return InferredSetReadResult(
                    target_group_id=target_group_id,
                    state=InferredReadState.STALE_ACTIVITY_CONTEXT,
                    stored_activity_as_of_academic_year_start=(
                        row.activity_as_of_academic_year_start
                    ),
                    stored_activity_window_years=row.activity_window_years,
                )
            current_set = _row_to_current_set(row, target_group_id=target_group_id)
            canonical_group_ids = _canonical_ids_for_expression(session, current_set.expression)
            _validate_storable_expression(
                current_set.expression,
                producer_kind=row.producer_kind,
                accepted_source_count=row.accepted_source_count,
                target_group_id=target_group_id,
                canonical_group_ids=canonical_group_ids,
            )
            return InferredSetReadResult(
                target_group_id=target_group_id,
                state=InferredReadState.CURRENT,
                current_set=current_set,
            )

    def find_candidate_group_ids(self, source_group_ids: Collection[str]) -> tuple[str, ...]:
        """Return active targets whose inferred expression names any requested source course.

        One bounded JSONPath existence read over the current inferred-set store, never a payload
        hydration: the typed `JSONPATH` parameter's `$ids[*]` variable is bound as one JSONB object
        of sorted distinct source IDs, and the recursive descent finds any nested course leaf. This
        is only a candidate superset. `read()` owns current/stale/valid semantics and the
        compiler decides whether the expression satisfies the target.
        """
        requested = tuple(sorted({group_id for group_id in source_group_ids if group_id}))
        if not requested:
            return ()
        with self._factory() as session:
            return tuple(
                session.scalars(
                    select(Course.group_id)
                    .join(
                        InferredPrerequisiteSet,
                        InferredPrerequisiteSet.target_course_id == Course.id,
                    )
                    .where(
                        Course.is_active.is_(True),
                        InferredPrerequisiteSet.expression.is_not(None),
                        func.jsonb_path_exists(
                            InferredPrerequisiteSet.expression,
                            cast(
                                literal(
                                    '$.** ? (@.type == "course" && @.course_group_id == $ids[*])'
                                ),
                                JSONPATH,
                            ),
                            literal({"ids": list(requested)}, type_=JSONB),
                        ),
                    )
                    .order_by(Course.group_id)
                )
            )

    def publish(self, publication: InferredSetPublication) -> InferredSetPublicationResult:
        """Validate and atomically create or replace one target's current inferred set."""
        expression_dump = (
            None
            if publication.expression is None
            else dump_prerequisite_expression(publication.expression)
        )
        payload_hash = json_sha256(
            _canonical_payload(publication, expression_dump), ensure_ascii=False
        )
        with session_scope(self._factory) as session:
            course = session.scalar(
                select(Course)
                .where(Course.group_id == publication.target_group_id)
                .with_for_update()
            )
            if course is None:
                raise ValueError(f"unknown canonical target course {publication.target_group_id}")
            if not course.is_active:
                raise ValueError(
                    f"cannot publish an inferred set for inactive target {publication.target_group_id}"
                )
            if (
                publication.activity_as_of_academic_year_start
                != course.activity_as_of_academic_year_start
                or publication.activity_window_years != course.activity_window_years
            ):
                raise ValueError("publication activity context does not match the target course")
            canonical_group_ids = _canonical_ids_for_expression(session, publication.expression)
            _validate_storable_expression(
                publication.expression,
                producer_kind=publication.producer_kind,
                accepted_source_count=publication.coverage.accepted_source_count,
                target_group_id=publication.target_group_id,
                canonical_group_ids=canonical_group_ids,
            )
            row = session.scalar(
                select(InferredPrerequisiteSet)
                .where(InferredPrerequisiteSet.target_course_id == course.id)
                .with_for_update()
            )
            if row is None:
                row = InferredPrerequisiteSet(
                    target_course_id=course.id,
                    activity_as_of_academic_year_start=(
                        publication.activity_as_of_academic_year_start
                    ),
                    activity_window_years=publication.activity_window_years,
                    coverage_state=publication.coverage_state,
                    eligible_source_count=publication.coverage.eligible_source_count,
                    processed_source_count=publication.coverage.processed_source_count,
                    accepted_source_count=publication.coverage.accepted_source_count,
                    producer_kind=publication.producer_kind,
                    producer_name=publication.producer_name,
                    producer_version=publication.producer_version,
                    input_hash=publication.input_hash,
                    payload_hash=payload_hash,
                    expression=expression_dump,
                    generated_at=publication.generated_at,
                )
                session.add(row)
                session.flush()
                session.refresh(row)
                return InferredSetPublicationResult(
                    action=InferredPublicationAction.CREATED,
                    current_set=_row_to_current_set(
                        row, target_group_id=publication.target_group_id
                    ),
                )
            if row.payload_hash == payload_hash:
                return InferredSetPublicationResult(
                    action=InferredPublicationAction.UNCHANGED,
                    current_set=_row_to_current_set(
                        row, target_group_id=publication.target_group_id
                    ),
                )
            row.activity_as_of_academic_year_start = publication.activity_as_of_academic_year_start
            row.activity_window_years = publication.activity_window_years
            row.coverage_state = publication.coverage_state
            row.eligible_source_count = publication.coverage.eligible_source_count
            row.processed_source_count = publication.coverage.processed_source_count
            row.accepted_source_count = publication.coverage.accepted_source_count
            row.producer_kind = publication.producer_kind
            row.producer_name = publication.producer_name
            row.producer_version = publication.producer_version
            row.input_hash = publication.input_hash
            row.payload_hash = payload_hash
            row.expression = expression_dump
            row.generated_at = publication.generated_at
            row.published_at = datetime.now(UTC)
            session.flush()
            return InferredSetPublicationResult(
                action=InferredPublicationAction.REPLACED,
                current_set=_row_to_current_set(row, target_group_id=publication.target_group_id),
            )

    def list_inference_target_group_ids(self) -> tuple[str, ...]:
        """Return canonical active targets with a current active inference-owned final set.

        This is the scoped projection of live inference-produced sets on an active target.
        Eligibility depends on the canonical activity rule alone, so an active inference row is
        current through a calendar-only rollover. It lets a publisher refuse a cohort that omits a target it would
        otherwise silently withdraw.
        """
        with self._factory() as session:
            return tuple(
                session.scalars(
                    select(Course.group_id)
                    .join(
                        InferredPrerequisiteSet,
                        InferredPrerequisiteSet.target_course_id == Course.id,
                    )
                    .where(
                        InferredPrerequisiteSet.producer_kind == InferredProducerKind.INFERENCE,
                        Course.is_active.is_(True),
                    )
                    .order_by(Course.group_id)
                )
            )

    def reconcile_activity(
        self, *, current_inference_input_hashes: Mapping[str, str | None] | None = None
    ) -> InferredActivityReconciliation:
        """Delete stale inferred sets and, when supplied, inference output whose input hash changed.

        An inactive target of either producer is stale and removed. A test-produced row whose
        stored generation context differs from the live course is removed, while an active
        inference-owned row with a differing stored context is retained: its eligibility is owned
        by the canonical activity rule and a calendar-only rollover must not delete accepted output.
        With the default `None` this preserves the activity-only behavior for every caller.
        When a cohort map is supplied it names every eligible target and records its current accepted
        proposal identity or `None` for no accepted current result. After the activity removal this
        additionally removes only inference-produced final sets for named targets whose stored
        `input_hash` does not equal the non-None current identity. Test/official rows and inference
        evidence are never touched, and validation completes before any mutation.
        """
        validated = (
            None
            if current_inference_input_hashes is None
            else _validate_current_inference_input_hashes(current_inference_input_hashes)
        )
        with session_scope(self._factory) as session:
            stale = tuple(
                session.execute(
                    select(InferredPrerequisiteSet.id, Course.group_id)
                    .join(Course, Course.id == InferredPrerequisiteSet.target_course_id)
                    .where(
                        (Course.is_active.is_(False))
                        | (
                            (
                                InferredPrerequisiteSet.producer_kind
                                != InferredProducerKind.INFERENCE
                            )
                            & (
                                (
                                    InferredPrerequisiteSet.activity_as_of_academic_year_start
                                    != Course.activity_as_of_academic_year_start
                                )
                                | (
                                    InferredPrerequisiteSet.activity_window_years
                                    != Course.activity_window_years
                                )
                            )
                        )
                    )
                )
            )
            if stale:
                session.execute(
                    delete(InferredPrerequisiteSet).where(
                        InferredPrerequisiteSet.id.in_(tuple(set_id for set_id, _ in stale))
                    )
                )
            removed = {group_id for _, group_id in stale}
            if validated:
                targets = tuple(validated)
                policy_rows = session.execute(
                    select(
                        InferredPrerequisiteSet.id,
                        Course.group_id,
                        InferredPrerequisiteSet.input_hash,
                    )
                    .join(Course, Course.id == InferredPrerequisiteSet.target_course_id)
                    .where(
                        Course.group_id.in_(targets),
                        InferredPrerequisiteSet.producer_kind == InferredProducerKind.INFERENCE,
                    )
                ).all()
                unwanted = [
                    set_id
                    for set_id, group_id, stored_hash in policy_rows
                    if group_id not in removed
                    and (validated[group_id] is None or stored_hash != validated[group_id])
                ]
                if unwanted:
                    session.execute(
                        delete(InferredPrerequisiteSet).where(
                            InferredPrerequisiteSet.id.in_(tuple(unwanted))
                        )
                    )
                removed.update(
                    group_id
                    for set_id, group_id, stored_hash in policy_rows
                    if group_id not in removed
                    and (validated[group_id] is None or stored_hash != validated[group_id])
                )
        return InferredActivityReconciliation(removed_target_group_ids=tuple(sorted(removed)))
