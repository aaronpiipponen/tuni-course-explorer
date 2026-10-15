"""Sole mutable owner of the teaching-text marker, processing cycle and per-target checkpoints.

This repository is the one durable scheduling store for offline inference. It reconciles canonical
courses' teaching-text processing markers, seeds active genuine pointers from the final
publisher's output, begins/resumes the one serial processing cycle, checkpoints strict per-target
stage payloads, atomically accepts a completed whole-target result, and bulk-marks the catalogue
processed only at a successful completed cycle. It also owns the operator's durable per-target
disposition decision (NULL/done/failed) and its one transition, projecting that decision onto the
current cycle's checkpoints and back to automatic eligibility without inventing any model work. It
reads immutable evidence only through the proposal/evidence owners and validates selected
pointers by their foreign-key target ownership. It never writes raw model output, never mutates a
final inferred set directly, and never duplicates a second proposal decoder.

Markers are scheduling state, never an "inferred-before" coverage claim: an inactive candidate source
can be marked processed without a target result, and a generation model/prompt/settings change alone
never resets a marker.
"""

from __future__ import annotations

import json
from collections.abc import Collection, Mapping, Sequence
from uuid import UUID

from sqlalchemy import and_, case, delete, func, or_, select, tuple_, update
from sqlalchemy.orm import Session, sessionmaker

from course_explorer.curriculum import CatalogueCourse, CatalogueTeachingCourse
from course_explorer.db.models import (
    Course,
    InferenceCourseProcessing,
    InferenceModelAttempt,
    InferencePipelineRun,
    InferenceProcessingCycle,
    InferenceProcessingTarget,
    InferenceProposal,
    InferenceTargetFailure,
    InferenceTargetWork,
    InferredEquivalenceGroup,
    InferredEquivalenceGroupMember,
    InferredPrerequisiteSet,
)
from course_explorer.db.session import session_scope
from course_explorer.enums import (
    InferenceWorkStatus,
    InferredCoverageState,
    InferredProducerKind,
)
from course_explorer.inference.context import processing_text_sha256
from course_explorer.inference.diagnostics import (
    InferenceCoverageSummary,
    InferenceGenerationCount,
)
from course_explorer.inference.evidence import (
    InferenceModelAttemptRecord,
    InferencePipelineRunRecord,
    InferenceTargetWorkRecord,
)
from course_explorer.inference.evidence_repository import InferenceEvidenceRepository
from course_explorer.inference.failures import FailureReason, FailureStage
from course_explorer.inference.proposal_repository import InferenceProposalRepository
from course_explorer.inference.proposals import TargetProposal
from course_explorer.inference.publication import CurrentInferenceCohort
from course_explorer.inference.scheduling import (
    CourseProcessingRecord,
    ProcessingCycleRecord,
    ProcessingTargetRecord,
    ProcessingTargetState,
    TargetDisposition,
    TargetFailureRecord,
    select_inference,
    select_rerank,
)
from course_explorer.teaching_text.service import EffectiveCourseTeachingText
from course_explorer.validation import require_sha256 as _require_sha256
from course_explorer.validation import require_text as _require_text

_STAGE_ORDER = ("multiview", "rerank", "inference", "publication")
_SETTABLE_STAGES = frozenset(_STAGE_ORDER)

# The one fixed safe inference error type recorded for an operator FAILED decision. It is a class
# token, never a message: the durable marker decision, not this text, is the terminal authority.
_OPERATOR_DISPOSITION_ERROR = "OperatorDisposition"


def _pool_digest(record: ProcessingTargetRecord) -> str | None:
    """Return the compact pool digest, or None when no pool payload is retained."""
    return None if record.pool_input is None else record.pool_input.pool_sha256


def _target_digest(record: ProcessingTargetRecord) -> str | None:
    """Return the compact selected-target digest, or None when no shortlist is retained."""
    return None if record.target_input is None else record.target_input.packet_sha256


class InferenceSchedulingRepository:
    """The one mutable scheduling/checkpoint store over the inference processing tables."""

    def __init__(self, factory: sessionmaker[Session]) -> None:
        self._factory = factory
        self._proposals = InferenceProposalRepository(factory)
        self._evidence = InferenceEvidenceRepository(factory)

    def read_seed_proposals(self) -> dict[str, UUID]:
        """Return genuine retained accepted pointers keyed by canonical target group ID.

        The shared selected-ID owner supplies the exact pointers: with no markers at all, the
        active genuine INFERENCE/COMPLETE final sets joined to the unique retained proposal whose
        identity hash matches. Otherwise the marker pointers. Every pointer's referenced
        completion is read once through the proposal owner's FK-joined completed read, and a
        broken or ambiguous pointer fails loudly. This is a once-at-entry read that writes nothing.
        """
        with self._factory() as session:
            selected = self._selected_proposal_ids(session)
        seeds: dict[str, UUID] = {}
        for group_id, proposal_id in selected.items():
            proposal, _work, _completion, _run = self._read_completed_proposal(proposal_id)
            if proposal.target_group_id != group_id:
                raise ValueError(
                    f"seed proposal {proposal_id} does not belong to target {group_id}"
                )
            seeds[group_id] = proposal_id
        return seeds

    def reconcile_courses(
        self,
        courses: Sequence[CatalogueCourse | CatalogueTeachingCourse],
        effective: Mapping[str, EffectiveCourseTeachingText],
        *,
        seed_proposals: Mapping[str, UUID],
    ) -> tuple[CourseProcessingRecord, ...]:
        """Reconcile processing markers over one full canonical catalogue in one transaction.

        New markers start FALSE. A changed teaching-text-only hash resets FALSE. An inactive course
        that has become active without an accepted completed proposal resets FALSE once. Existing
        accepted pointers are never cleared, ``was_active`` is always refreshed, and a seeded pointer
        marks processed TRUE only when its saved text-only descriptor hash equals the current
        exact hash. The operator disposition decision and the lifetime generation counter are never
        changed here: calendar rollover and generator metadata changes never reset a marker.
        """
        course_list = tuple(courses)
        group_ids = tuple(course.group_id for course in course_list)
        if len(set(group_ids)) != len(group_ids):
            raise ValueError("catalogue group IDs must be unique")
        represented = {
            course.group_id for course in course_list if course.representative is not None
        }
        if set(effective) - represented:
            raise ValueError("effective text may be supplied only for represented courses")
        seed_hashes: dict[str, str] = {}
        for group_id, proposal_id in seed_proposals.items():
            _require_text(group_id, "seed group_id")
            proposal, _work, completion, _run = self._read_completed_proposal(proposal_id)
            if proposal.target_group_id != group_id:
                raise ValueError(
                    f"seed proposal {proposal_id} does not belong to target {group_id}"
                )
            seed_hashes[group_id] = completion.payload.facts.target_teaching_text_sha256
        current_text_hashes = {
            group_id: (
                processing_text_sha256(())
                if effective.get(group_id) is None
                else processing_text_sha256(
                    tuple(
                        (cell.field.value, cell.language.value, cell.text)
                        for cell in effective[group_id].texts
                    )
                )
            )
            for group_id in group_ids
        }
        with session_scope(self._factory) as session:
            course_ids = dict(
                session.execute(
                    select(Course.group_id, Course.id).where(Course.group_id.in_(group_ids))
                ).all()
            )
            missing = set(group_ids) - set(course_ids)
            if missing:
                raise ValueError(f"canonical catalogue courses are missing: {sorted(missing)}")
            row_by_course = {
                row.course_id: row
                for row in session.scalars(
                    select(InferenceCourseProcessing).where(
                        InferenceCourseProcessing.course_id.in_(tuple(course_ids.values()))
                    )
                )
            }
            records: list[CourseProcessingRecord] = []
            for course in course_list:
                course_id = course_ids[course.group_id]
                current_hash = current_text_hashes[course.group_id]
                row = row_by_course.get(course_id)
                if row is None:
                    seed_id = seed_proposals.get(course.group_id)
                    processed = False
                    if seed_id is not None:
                        saved_hash = seed_hashes[course.group_id]
                        processed = saved_hash == current_hash
                    row = InferenceCourseProcessing(
                        course_id=course_id,
                        teaching_text_sha256=current_hash,
                        processed=processed,
                        was_active=course.is_active,
                        accepted_proposal_id=seed_id,
                    )
                    session.add(row)
                else:
                    reset = row.teaching_text_sha256 != current_hash
                    if not row.was_active and course.is_active and row.accepted_proposal_id is None:
                        # One-time inactive-to-active reset for a course with no completed result.
                        reset = True
                    row.teaching_text_sha256 = current_hash
                    row.was_active = course.is_active
                    if reset:
                        row.processed = False
                records.append(
                    CourseProcessingRecord(
                        group_id=course.group_id,
                        teaching_text_sha256=current_hash,
                        processed=bool(row.processed),
                        was_active=course.is_active,
                        accepted_proposal_id=row.accepted_proposal_id,
                        disposition=row.disposition,
                    )
                )
            session.flush()
        return tuple(sorted(records, key=lambda record: record.group_id))

    def read_processing(self) -> tuple[CourseProcessingRecord, ...]:
        """Return one group/hash/flag/pointer projection over every marker, sorted by group ID."""
        with self._factory() as session:
            return self._processing_records(session)

    def read_target_processing(self, target_group_id: str) -> CourseProcessingRecord:
        """Return exactly one canonical target's marker projection, or fail when it is absent.

        It shares the scoped marker read used by the whole-catalogue projection, so a
        single-target identity/decision read never materializes every processing row.
        """
        _require_text(target_group_id, "target_group_id")
        with self._factory() as session:
            records = self._processing_records(session, (target_group_id,))
        if not records:
            raise ValueError(f"target {target_group_id} has no processing marker")
        return records[0]

    def read_operator_failed_target_group_ids(self) -> tuple[str, ...]:
        """Return sorted active canonical targets carrying an explicit FAILED decision.

        It is a scoped column projection over the marker decision only, so a terminal operator
        failure is reported from its durable owner rather than inferred from error text or a
        possibly absent failure episode.
        """
        with self._factory() as session:
            return self._active_marker_group_ids(session, "failed")

    def read_publication_cohort(self) -> CurrentInferenceCohort:
        """Return the whole active-target publication cohort with its selected pointers.

        Every active canonical course is eligible. The accepted pointers are the exact retained
        proposals selected by the shared owner (marker-done targets are excluded from selection), and
        the marker-done identities are supplied separately as the explicit
        complete-without-output cohort. Each selected pointer is validated against its foreign-key
        target ownership in one scoped projection without fetching any JSON payload or hydrating an
        ORM row. A bad pointer fails loudly rather than disappearing or reporting zero.
        """
        with self._factory() as session:
            active_ids = tuple(
                session.scalars(
                    select(Course.group_id)
                    .where(Course.is_active.is_(True))
                    .order_by(Course.group_id)
                )
            )
            selected = self._selected_proposal_ids(session)
            self._validate_selected_pointers(session, selected)
            return CurrentInferenceCohort(
                eligible_target_group_ids=active_ids,
                accepted_proposal_ids=selected,
                completed_without_output_target_group_ids=self._active_marker_group_ids(
                    session, "done"
                ),
            )

    def read_coverage(self) -> InferenceCoverageSummary:
        """Return the aggregate scheduling, retained-result and generation coverage read.

        All counts are SQL aggregates over scoped projections: no raw request/result/configuration
        JSON is fetched and no durability counter is maintained. Retained pointers, published final
        sets, current exact groups, active proposal history, mixed-generation grouping and the
        retained cycle's stage counters are each read once. Explicit operator DONE targets are
        counted as retained complete coverage (and as published once their inference-owned output is
        actually withdrawn) without contributing any generation identity. Marker-done targets are
        excluded from selected generation/publication coverage. With no retained cycle the stage
        counters are zero and the cycle identity is absent, independent of any retained results.
        """
        with self._factory() as session:
            eligible = int(
                session.scalar(
                    select(func.count()).select_from(Course).where(Course.is_active.is_(True))
                )
            )
            selected = self._selected_proposal_ids(session)
            self._validate_selected_pointers(session, selected)
            done_ids = self._active_marker_group_ids(session, "done")
            retained = len(selected) + len(done_ids)
            published = 0
            if selected:
                published = int(
                    session.scalar(
                        select(func.count(func.distinct(InferredPrerequisiteSet.target_course_id)))
                        .select_from(InferredPrerequisiteSet)
                        .join(
                            InferenceProposal,
                            and_(
                                InferenceProposal.identity_sha256
                                == InferredPrerequisiteSet.input_hash,
                                InferenceProposal.target_course_id
                                == InferredPrerequisiteSet.target_course_id,
                            ),
                        )
                        .join(Course, Course.id == InferredPrerequisiteSet.target_course_id)
                        .where(
                            Course.is_active.is_(True),
                            InferredPrerequisiteSet.producer_kind == InferredProducerKind.INFERENCE,
                            InferredPrerequisiteSet.coverage_state
                            == InferredCoverageState.COMPLETE,
                            InferenceProposal.id.in_(tuple(selected.values())),
                        )
                    )
                )
            published += self._done_without_output_count(session, done_ids)
            groups = self._current_equivalence_group_count(session)
            historical = int(
                session.scalar(
                    select(func.count())
                    .select_from(InferenceProposal)
                    .join(Course, Course.id == InferenceProposal.target_course_id)
                    .where(Course.is_active.is_(True))
                )
            )
            generation_counts = self._generation_counts(session, selected)
            (
                cycle_id,
                stage,
                multiview_completed,
                rerank_completed,
                rerank_skipped,
                inference_completed,
                inference_skipped,
                failed_targets,
                pending_targets,
            ) = self._latest_cycle_progress(session)
        return InferenceCoverageSummary(
            eligible_targets=eligible,
            retained_complete_targets=retained,
            published_targets=published,
            uncovered_targets=eligible - retained,
            current_equivalence_groups=groups,
            historical_proposal_rows=historical,
            generation_counts=generation_counts,
            cycle_id=cycle_id,
            stage=stage,
            multiview_completed=multiview_completed,
            rerank_completed=rerank_completed,
            rerank_skipped=rerank_skipped,
            inference_completed=inference_completed,
            inference_skipped=inference_skipped,
            failed_targets=failed_targets,
            pending_targets=pending_targets,
        )

    @staticmethod
    def _selected_proposal_ids(session: Session) -> dict[str, UUID]:
        """Return the shared active-target accepted-pointer projection.

        With ANY processing markers present, only each active course's nonnull marker pointer is
        authority: a missing marker or pointer is uncovered and never falls back to raw/history/final
        output. A marker-done target is excluded here so its retained predecessor is not selected for
        generation/publication coverage, while its marker pointer is retained for ordinary reuse. With NO markers at all (bootstrap), each active genuine INFERENCE/COMPLETE
        final set is joined to the unique retained proposal whose identity hash and target match. A
        broken or ambiguous final pointer fails loudly rather than quietly reporting zero.
        """
        marker_count = int(
            session.scalar(select(func.count()).select_from(InferenceCourseProcessing))
        )
        if marker_count:
            rows = session.execute(
                select(Course.group_id, InferenceCourseProcessing.accepted_proposal_id)
                .join(
                    InferenceCourseProcessing,
                    InferenceCourseProcessing.course_id == Course.id,
                )
                .where(
                    Course.is_active.is_(True),
                    InferenceCourseProcessing.accepted_proposal_id.is_not(None),
                    or_(
                        InferenceCourseProcessing.disposition.is_(None),
                        InferenceCourseProcessing.disposition != "done",
                    ),
                )
            ).all()
            return {group_id: proposal_id for group_id, proposal_id in rows}
        rows = session.execute(
            select(
                Course.group_id,
                InferenceProposal.id,
            )
            .select_from(Course)
            .join(InferredPrerequisiteSet, InferredPrerequisiteSet.target_course_id == Course.id)
            .outerjoin(
                InferenceProposal,
                and_(
                    InferenceProposal.identity_sha256 == InferredPrerequisiteSet.input_hash,
                    InferenceProposal.target_course_id == Course.id,
                ),
            )
            .where(
                Course.is_active.is_(True),
                InferredPrerequisiteSet.producer_kind == InferredProducerKind.INFERENCE,
                InferredPrerequisiteSet.coverage_state == InferredCoverageState.COMPLETE,
            )
        ).all()
        selected: dict[str, UUID] = {}
        grouped: dict[str, list[UUID | None]] = {}
        for group_id, proposal_id in rows:
            grouped.setdefault(group_id, []).append(proposal_id)
        for group_id, pointers in grouped.items():
            resolved = [pointer for pointer in pointers if pointer is not None]
            if len(pointers) != 1 or len(resolved) != 1:
                raise ValueError(
                    f"genuine final inferred set for {group_id} does not reference exactly one proposal"
                )
            selected[group_id] = resolved[0]
        return selected

    @staticmethod
    def _active_marker_group_ids(
        session: Session, disposition: TargetDisposition
    ) -> tuple[str, ...]:
        """Return sorted active canonical targets carrying one explicit marker decision."""
        return tuple(
            session.scalars(
                select(Course.group_id)
                .join(
                    InferenceCourseProcessing,
                    InferenceCourseProcessing.course_id == Course.id,
                )
                .where(
                    Course.is_active.is_(True),
                    InferenceCourseProcessing.disposition == disposition,
                )
                .order_by(Course.group_id)
            )
        )

    @staticmethod
    def _done_without_output_count(session: Session, done_ids: Sequence[str]) -> int:
        """Count explicit DONE targets with no inference-produced final set remaining.

        A done target with stale inference output counts as published only after the publisher
        withdraws that output. That absence makes the target published. No final row is fabricated
        for a done target.
        """
        ids = tuple(done_ids)
        if not ids:
            return 0
        still_output = set(
            session.scalars(
                select(Course.group_id)
                .join(
                    InferredPrerequisiteSet,
                    InferredPrerequisiteSet.target_course_id == Course.id,
                )
                .where(
                    Course.group_id.in_(ids),
                    InferredPrerequisiteSet.producer_kind == InferredProducerKind.INFERENCE,
                )
            )
        )
        return sum(1 for group_id in ids if group_id not in still_output)

    @staticmethod
    def _validate_selected_pointers(session: Session, selected: Mapping[str, UUID]) -> None:
        """Relationally check every selected pointer names its own target in one scoped projection.

        The proposal target must be the supplied cohort course. A wrong-target pointer fails loudly
        instead of counting as coverage. No recorded-chain re-proof, JSON payload or ORM hydration
        happens on this immutable read.
        """
        if not selected:
            return
        rows = session.execute(
            select(InferenceProposal.id, Course.group_id)
            .join(Course, Course.id == InferenceProposal.target_course_id)
            .where(InferenceProposal.id.in_(tuple(selected.values())))
        ).all()
        supplied = {proposal_id: group_id for group_id, proposal_id in selected.items()}
        seen: set[UUID] = set()
        for proposal_id, group_id in rows:
            if proposal_id in seen:
                raise ValueError("a selected proposal resolved to more than one target")
            seen.add(proposal_id)
            if supplied[proposal_id] != group_id:
                raise ValueError("a selected proposal target does not match its cohort course")
        if seen != set(selected.values()):
            raise ValueError("a selected proposal has no target ownership")

    def _current_equivalence_group_count(self, session: Session) -> int:
        """Count inference-owned groups whose at-least-two members are all active."""
        active_counts = (
            select(
                InferredEquivalenceGroupMember.equivalence_group_id.label("group_id"),
                func.count().label("total"),
                func.sum(case((Course.is_active.is_(True), 1), else_=0)).label("active"),
            )
            .join(Course, Course.id == InferredEquivalenceGroupMember.course_id, isouter=True)
            .group_by(InferredEquivalenceGroupMember.equivalence_group_id)
            .subquery()
        )
        return int(
            session.scalar(
                select(func.count())
                .select_from(InferredEquivalenceGroup)
                .join(active_counts, active_counts.c.group_id == InferredEquivalenceGroup.id)
                .where(
                    InferredEquivalenceGroup.producer_kind == InferredProducerKind.INFERENCE,
                    active_counts.c.total >= 2,
                    active_counts.c.active == active_counts.c.total,
                )
            )
        )

    @staticmethod
    def _generation_counts(
        session: Session, selected: Mapping[str, UUID]
    ) -> tuple[InferenceGenerationCount, ...]:
        """Group selected pointers by shared execution identity and recorded route."""
        if not selected:
            return ()
        route = InferencePipelineRun.configuration["route"].astext
        rows = session.execute(
            select(
                InferencePipelineRun.model_identity,
                InferencePipelineRun.prompt_version,
                InferencePipelineRun.schema_version,
                InferencePipelineRun.pipeline_version,
                route.label("route"),
                func.count().label("targets"),
            )
            .select_from(InferenceProposal)
            .join(
                InferenceModelAttempt,
                InferenceModelAttempt.id == InferenceProposal.source_attempt_id,
            )
            .join(
                InferenceTargetWork,
                InferenceTargetWork.id == InferenceModelAttempt.target_work_id,
            )
            .join(
                InferencePipelineRun,
                InferencePipelineRun.id == InferenceTargetWork.created_by_run_id,
            )
            .where(InferenceProposal.id.in_(tuple(selected.values())))
            .group_by(
                InferencePipelineRun.model_identity,
                InferencePipelineRun.prompt_version,
                InferencePipelineRun.schema_version,
                InferencePipelineRun.pipeline_version,
                route,
            )
        ).all()
        counts = [
            InferenceGenerationCount(
                model_identity=model_identity,
                prompt_version=prompt_version,
                schema_version=schema_version,
                pipeline_version=pipeline_version,
                route=row_route,
                targets=int(targets),
            )
            for (
                model_identity,
                prompt_version,
                schema_version,
                pipeline_version,
                row_route,
                targets,
            ) in rows
        ]
        return tuple(
            sorted(
                counts,
                key=lambda count: (
                    count.model_identity,
                    count.prompt_version,
                    count.schema_version,
                    count.pipeline_version,
                    count.route,
                ),
            )
        )

    @staticmethod
    def _latest_cycle_progress(
        session: Session,
    ) -> tuple[UUID | None, str | None, int, int, int, int, int, int, int]:
        """Return the retained cycle's id/stage and its per-state target counters."""
        latest = session.execute(
            select(InferenceProcessingCycle.id, InferenceProcessingCycle.stage)
            .order_by(
                InferenceProcessingCycle.created_at.desc(),
                InferenceProcessingCycle.id.desc(),
            )
            .limit(1)
        ).one_or_none()
        if latest is None:
            return (None, None, 0, 0, 0, 0, 0, 0, 0)
        counts = session.execute(
            select(
                func.sum(
                    case((InferenceProcessingTarget.multiview_state == "completed", 1), else_=0)
                ),
                func.sum(case((InferenceProcessingTarget.rerank_state == "completed", 1), else_=0)),
                func.sum(case((InferenceProcessingTarget.rerank_state == "skipped", 1), else_=0)),
                func.sum(
                    case((InferenceProcessingTarget.inference_state == "completed", 1), else_=0)
                ),
                func.sum(
                    case((InferenceProcessingTarget.inference_state == "skipped", 1), else_=0)
                ),
                func.sum(
                    case(
                        (
                            or_(
                                InferenceProcessingTarget.multiview_state == "failed",
                                InferenceProcessingTarget.rerank_state == "failed",
                                InferenceProcessingTarget.inference_state == "failed",
                            ),
                            1,
                        ),
                        else_=0,
                    )
                ),
                func.sum(
                    case(
                        (
                            and_(
                                InferenceProcessingTarget.multiview_state != "failed",
                                InferenceProcessingTarget.rerank_state != "failed",
                                InferenceProcessingTarget.inference_state != "failed",
                                or_(
                                    InferenceProcessingTarget.multiview_state == "pending",
                                    InferenceProcessingTarget.rerank_state == "pending",
                                    InferenceProcessingTarget.inference_state == "pending",
                                ),
                            ),
                            1,
                        ),
                        else_=0,
                    )
                ),
            )
            .select_from(InferenceProcessingTarget)
            .where(InferenceProcessingTarget.cycle_id == latest.id)
        ).one()
        return (
            latest.id,
            latest.stage,
            int(counts[0] or 0),
            int(counts[1] or 0),
            int(counts[2] or 0),
            int(counts[3] or 0),
            int(counts[4] or 0),
            int(counts[5] or 0),
            int(counts[6] or 0),
        )

    def begin_cycle(
        self, input_sha256: str, active_target_group_ids: Sequence[str]
    ) -> ProcessingCycleRecord:
        """Resume an unfinished matching cycle or append a fresh multiview-all cycle.

        Every supplied target must be a known active and reconciled canonical course. The most
        recent retained cycle is considered: it is resumed only when unfinished with the identical
        input digest and target-ID universe, and a completed or changed cycle gives way to a fresh
        multiview-all cycle. Each fresh target row
        carries its marker's retained operator disposition decision forward.
        """
        _require_sha256(input_sha256, "cycle input_sha256")
        target_ids = tuple(active_target_group_ids)
        if len(set(target_ids)) != len(target_ids):
            raise ValueError("active target group IDs must be unique")
        for group_id in target_ids:
            _require_text(group_id, "active target group_id")
        with session_scope(self._factory) as session:
            course_rows = (
                {}
                if not target_ids
                else {
                    row.group_id: row
                    for row in session.execute(
                        select(Course.id, Course.group_id, Course.is_active).where(
                            Course.group_id.in_(target_ids)
                        )
                    ).all()
                }
            )
            missing = set(target_ids) - set(course_rows)
            if missing:
                raise ValueError(f"active target courses are missing: {sorted(missing)}")
            for group_id in target_ids:
                if not course_rows[group_id].is_active:
                    raise ValueError(f"target {group_id} is not an active canonical course")
            reconciled = (
                set()
                if not target_ids
                else set(
                    session.scalars(
                        select(Course.group_id)
                        .join(
                            InferenceCourseProcessing,
                            InferenceCourseProcessing.course_id == Course.id,
                        )
                        .where(Course.group_id.in_(target_ids))
                    )
                )
            )
            if reconciled != set(target_ids):
                raise ValueError("active targets must be reconciled before a cycle begins")
            latest = self._latest_cycle(session, for_update=True)
            if (
                latest is not None
                and latest.stage != "complete"
                and latest.input_sha256 == input_sha256
            ):
                existing_ids = set(
                    session.scalars(
                        select(Course.group_id)
                        .join(
                            InferenceProcessingTarget,
                            InferenceProcessingTarget.target_course_id == Course.id,
                        )
                        .where(InferenceProcessingTarget.cycle_id == latest.id)
                    )
                )
                if existing_ids == set(target_ids):
                    earliest_failed = self._earliest_failed_stage(session, latest.id)
                    if earliest_failed is not None and _STAGE_ORDER.index(
                        earliest_failed
                    ) < _STAGE_ORDER.index(latest.stage):
                        latest.stage = earliest_failed
                        session.flush()
                    return self._cycle_record(latest)
            cycle = InferenceProcessingCycle(input_sha256=input_sha256, stage="multiview")
            session.add(cycle)
            session.flush()
            self._prune_superseded_cycles(session, keep_cycle_id=cycle.id)
            markers = {
                record.group_id: record for record in self._processing_records(session, target_ids)
            }
            for group_id in sorted(target_ids):
                row = InferenceProcessingTarget(
                    cycle_id=cycle.id,
                    target_course_id=course_rows[group_id].id,
                    multiview_state="pending",
                    rerank_state="pending",
                    inference_state="pending",
                )
                decision = markers[group_id].disposition
                if decision is not None:
                    # A new cycle's target row carries the retained operator decision forward. The
                    # marker is its single durable owner and no model work is invented here.
                    self._apply_target_disposition(row, decision)
                session.add(row)
            session.flush()
            return self._cycle_record(cycle)

    def read_cycle(self, cycle_id: UUID) -> ProcessingCycleRecord:
        """Return one retained cycle by id, or fail clearly for an unknown id."""
        with self._factory() as session:
            cycle = session.get(InferenceProcessingCycle, cycle_id)
            if cycle is None:
                raise ValueError(f"unknown inference processing cycle {cycle_id}")
            return self._cycle_record(cycle)

    def list_target_states(self, cycle_id: UUID) -> tuple[ProcessingTargetState, ...]:
        """Return only the cycle/group/three-state projection for one cycle, sorted by group ID."""
        with self._factory() as session:
            if (
                session.scalar(
                    select(InferenceProcessingCycle.id).where(
                        InferenceProcessingCycle.id == cycle_id
                    )
                )
                is None
            ):
                raise ValueError(f"unknown inference processing cycle {cycle_id}")
            rows = session.execute(
                select(
                    InferenceProcessingTarget.cycle_id,
                    Course.group_id,
                    InferenceProcessingTarget.multiview_state,
                    InferenceProcessingTarget.rerank_state,
                    InferenceProcessingTarget.inference_state,
                )
                .join(Course, Course.id == InferenceProcessingTarget.target_course_id)
                .where(InferenceProcessingTarget.cycle_id == cycle_id)
                .order_by(Course.group_id)
            ).all()
        return tuple(
            ProcessingTargetState(
                cycle_id=row.cycle_id,
                target_group_id=row.group_id,
                multiview_state=row.multiview_state,
                rerank_state=row.rerank_state,
                inference_state=row.inference_state,
            )
            for row in rows
        )

    def read_target(self, cycle_id: UUID, target_group_id: str) -> ProcessingTargetRecord:
        """Load exactly one unit's strict checkpoint JSON, or fail clearly when absent."""
        _require_text(target_group_id, "target_group_id")
        with self._factory() as session:
            row = self._target_row(session, cycle_id, target_group_id)
            if row is None:
                raise ValueError(f"cycle {cycle_id} has no target checkpoint for {target_group_id}")
            return self._target_record(row, target_group_id)

    def record_target_failure(
        self,
        cycle_id: UUID,
        target_group_id: str,
        *,
        stage: FailureStage,
        attempt_count: int,
        error_type: str,
        reason: FailureReason,
        exhausted: bool,
    ) -> tuple[ProcessingTargetRecord, TargetFailureRecord]:
        """Atomically mark one target's executing stage FAILED and append its failure episode.

        It locks the unfinished cycle and its one target row, maps ``inference_preparation``
        to the inference stage, requires the executing stage to be pending/failed with its
        dependencies present, preserves every successful payload/planned key/pointer, and appends one
        append-only episode. For generation the caller records one episode per failed whole-target
        attempt (``attempt_count`` one, and ``exhausted`` only on a bounded route's final pass
        request). Bounded multiview/rerank/preparation stages keep recording one summary episode for
        the pass. Preparation requires completed multiview and rerank with a retained target input
        exactly like inference and needs no generation key/work/attempt. It returns the updated
        checkpoint together with the owning failure DTO.
        """
        _require_text(target_group_id, "target_group_id")
        mapped_stage = "inference" if stage == "inference_preparation" else stage
        if mapped_stage not in ("multiview", "rerank", "inference"):
            raise ValueError(
                "failure stage must be multiview, rerank, inference_preparation, or inference"
            )
        if (
            isinstance(attempt_count, bool)
            or not isinstance(attempt_count, int)
            or attempt_count < 1
        ):
            raise ValueError("failure attempt_count must be a positive integer")
        _require_text(error_type, "failure error_type")
        with session_scope(self._factory) as session:
            cycle = self._require_latest_unfinished(session, expected_id=cycle_id)
            row = self._target_row(session, cycle.id, target_group_id, for_update=True)
            if row is None:
                raise ValueError(f"target {target_group_id} is not part of the latest cycle")
            stored = self._target_record(row, target_group_id)
            attribute = f"{mapped_stage}_state"
            if getattr(stored, attribute) not in ("pending", "failed"):
                raise ValueError(
                    f"cannot record a failure for a {getattr(stored, attribute)} stage"
                )
            if mapped_stage == "rerank" and stored.multiview_state != "completed":
                raise ValueError("a rerank failure requires completed multiview")
            if mapped_stage == "inference":
                if stored.multiview_state != "completed" or stored.rerank_state != "completed":
                    raise ValueError("an inference failure requires completed multiview and rerank")
                if stored.target_input is None:
                    raise ValueError("an inference failure requires the retained target input")
                if self._marker_disposition(session, target_group_id) is not None:
                    raise ValueError("an operator decision owns this target's inference state")
            updated = stored.model_copy(update={attribute: "failed", "error_type": error_type})
            self._validate_transition(session, cycle, stored, updated)
            row.multiview_state = updated.multiview_state
            row.rerank_state = updated.rerank_state
            row.inference_state = updated.inference_state
            row.error_type = updated.error_type
            session.add(
                failure := InferenceTargetFailure(
                    cycle_id=cycle.id,
                    target_course_id=row.target_course_id,
                    stage=stage,
                    attempt_count=attempt_count,
                    error_type=error_type,
                    reason=reason,
                    exhausted=exhausted,
                )
            )
            session.flush()
            session.refresh(failure)
            session.refresh(row)
            return (
                self._target_record(row, target_group_id),
                self._failure_record(failure, target_group_id),
            )

    def reserve_generation_attempt(self, cycle_id: UUID, target_group_id: str) -> tuple[int, bool]:
        """Reserve one durable generation attempt as ``(lifetime ordinal, calculation-first flag)``.

        It locks the unfinished inference-stage cycle and the one supplied target row, reads
        only the projection (the three stage states, whether a retained target input exists,
        and whether the cycle-target calculation already started), and atomically advances the
        canonical course marker's lifetime counter. The calculation-first fact is the
        cycle-target row, not the lifetime ordinal: only a new cycle-target starts a new
        calculation. Both facts commit before the caller issues HTTP, so an interruption never
        re-draws a used seed, and a refused/unsent request consumes its first status and seed.
        """
        _require_text(target_group_id, "target_group_id")
        with session_scope(self._factory) as session:
            cycle = self._require_latest_unfinished(session, expected_id=cycle_id)
            if cycle.stage != "inference":
                raise ValueError("reserving a generation attempt requires the inference stage")
            row = session.execute(
                select(
                    InferenceProcessingTarget.target_course_id,
                    InferenceProcessingTarget.multiview_state,
                    InferenceProcessingTarget.rerank_state,
                    InferenceProcessingTarget.inference_state,
                    InferenceProcessingTarget.target_input.is_not(None).label("has_target_input"),
                    InferenceProcessingTarget.generation_started,
                    Course.group_id,
                )
                .join(Course, Course.id == InferenceProcessingTarget.target_course_id)
                .where(
                    InferenceProcessingTarget.cycle_id == cycle.id,
                    Course.group_id == target_group_id,
                )
                .with_for_update(of=InferenceProcessingTarget)
            ).one_or_none()
            if row is None:
                raise ValueError(f"target {target_group_id} is not part of the latest cycle")
            if row.inference_state not in ("pending", "failed"):
                raise ValueError("a generation attempt requires a pending/failed inference stage")
            if row.multiview_state != "completed" or row.rerank_state != "completed":
                raise ValueError("a generation attempt requires completed multiview and rerank")
            if not row.has_target_input:
                raise ValueError("a generation attempt requires the retained target input")
            if (
                session.scalar(
                    select(InferenceCourseProcessing.disposition).where(
                        InferenceCourseProcessing.course_id == row.target_course_id
                    )
                )
                is not None
            ):
                raise ValueError(
                    "an operator decision owns this target; it cannot reserve a generation attempt"
                )
            first_attempt = not row.generation_started
            session.execute(
                update(InferenceProcessingTarget)
                .where(
                    InferenceProcessingTarget.cycle_id == cycle.id,
                    InferenceProcessingTarget.target_course_id == row.target_course_id,
                )
                .values(generation_started=True)
            )
            ordinal = session.execute(
                update(InferenceCourseProcessing)
                .where(InferenceCourseProcessing.course_id == row.target_course_id)
                .values(
                    generation_attempt_count=InferenceCourseProcessing.generation_attempt_count + 1
                )
                .returning(InferenceCourseProcessing.generation_attempt_count)
            ).scalar_one_or_none()
            if ordinal is None:
                raise ValueError(f"target {target_group_id} has no processing marker")
            return int(ordinal), first_attempt

    def read_target_failures(
        self, cycle_id: UUID, *, unresolved_only: bool = True
    ) -> tuple[TargetFailureRecord, ...]:
        """Return retained failure episodes for one cycle, latest-per-failed-target or full history.

        It is a scoped column projection joining the canonical group id. No JSON payload, catalogue
        or per-unit hydration happens. ``unresolved_only`` returns the latest episode for each target
        failed in the cycle (no fabricated record for a failure with no episode). Otherwise
        it returns the full episode history.
        """
        with self._factory() as session:
            if (
                session.scalar(
                    select(InferenceProcessingCycle.id).where(
                        InferenceProcessingCycle.id == cycle_id
                    )
                )
                is None
            ):
                raise ValueError(f"unknown inference processing cycle {cycle_id}")
            base = (
                select(
                    InferenceTargetFailure.id,
                    InferenceTargetFailure.cycle_id,
                    InferenceTargetFailure.target_course_id,
                    Course.group_id,
                    InferenceTargetFailure.stage,
                    InferenceTargetFailure.attempt_count,
                    InferenceTargetFailure.error_type,
                    InferenceTargetFailure.reason,
                    InferenceTargetFailure.exhausted,
                    InferenceTargetFailure.created_at,
                )
                .join(Course, Course.id == InferenceTargetFailure.target_course_id)
                .where(InferenceTargetFailure.cycle_id == cycle_id)
            )
            if unresolved_only:
                ranked = base.add_columns(
                    func.row_number()
                    .over(
                        partition_by=InferenceTargetFailure.target_course_id,
                        order_by=(
                            InferenceTargetFailure.created_at.desc(),
                            InferenceTargetFailure.id.desc(),
                        ),
                    )
                    .label("rank")
                ).subquery()
                failed = (
                    select(InferenceProcessingTarget.target_course_id)
                    .where(
                        InferenceProcessingTarget.cycle_id == cycle_id,
                        or_(
                            InferenceProcessingTarget.multiview_state == "failed",
                            InferenceProcessingTarget.rerank_state == "failed",
                            InferenceProcessingTarget.inference_state == "failed",
                        ),
                    )
                    .subquery()
                )
                rows = session.execute(
                    select(ranked)
                    .join(failed, failed.c.target_course_id == ranked.c.target_course_id)
                    .where(ranked.c.rank == 1)
                    .order_by(ranked.c.group_id, ranked.c.created_at, ranked.c.id)
                ).all()
            else:
                rows = session.execute(
                    base.order_by(
                        Course.group_id,
                        InferenceTargetFailure.created_at,
                        InferenceTargetFailure.id,
                    )
                ).all()
        return tuple(
            TargetFailureRecord(
                failure_id=row.id,
                cycle_id=row.cycle_id,
                target_group_id=row.group_id,
                stage=row.stage,
                attempt_count=row.attempt_count,
                error_type=row.error_type,
                reason=row.reason,
                exhausted=row.exhausted,
                created_at=row.created_at,
            )
            for row in rows
        )

    def set_target_disposition(
        self, target_group_id: str, disposition: TargetDisposition | None
    ) -> CourseProcessingRecord:
        """Set one canonical target's durable operator disposition decision.

        The decision is one nullable marker choice (NULL/automatic, ``done``, ``failed``). Every
        transition among the three and every harmless repeat is supported, and only an explicit
        nonnull-to-NULL clear returns this target to automatic eligibility. It requires an active
        canonical course and its marker, then locks the retained cycle and the supplied target row
        using the owners. The cycle MAY be absent or complete, so
        no unfinished-cycle barrier is applied. A nonnull decision projects onto the current cycle's
        checkpoint (inference state/error only) and is carried to new-cycle rows by :meth:`begin_cycle`.
        No synthetic proposal, completion, failure episode or reservation is created.
        """
        _require_text(target_group_id, "target_group_id")
        if disposition is not None and disposition not in ("done", "failed"):
            raise ValueError("disposition must be None, 'done', or 'failed'")
        with session_scope(self._factory) as session:
            course = session.scalar(
                select(Course).where(Course.group_id == target_group_id).with_for_update()
            )
            if course is None or not course.is_active:
                raise ValueError(f"target {target_group_id} is not a current active course")
            marker = session.scalar(
                select(InferenceCourseProcessing)
                .where(InferenceCourseProcessing.course_id == course.id)
                .with_for_update()
            )
            if marker is None:
                raise ValueError(f"target {target_group_id} has no processing marker")
            if marker.disposition == disposition:
                # A harmless repeat is a no-op repository write: the decision and every genuine
                # payload/counter stay exactly as they are.
                return self._marker_record(marker, target_group_id)
            cycle = self._latest_cycle(session, for_update=True)
            row = (
                None
                if cycle is None
                else session.scalar(
                    select(InferenceProcessingTarget)
                    .where(
                        InferenceProcessingTarget.cycle_id == cycle.id,
                        InferenceProcessingTarget.target_course_id == course.id,
                    )
                    .with_for_update()
                )
            )
            if disposition is not None:
                marker.disposition = disposition
                if row is not None:
                    self._apply_target_disposition(row, disposition)
                    if disposition == "failed" and cycle.stage == "complete":
                        # A terminal operator failure reopens a completed cycle at inference so it is
                        # incomplete. Done never fabricates cycle completion.
                        cycle.stage = "inference"
                session.flush()
                return self._marker_record(marker, target_group_id)
            marker.disposition = None
            # Clearing returns only this target to automatic eligibility through the
            # own-FALSE membership rule, even after a done cycle bulk-marked every marker TRUE.
            marker.processed = False
            if row is not None:
                self._clear_target_to_automatic(cycle, row, target_group_id)
            session.flush()
            return self._marker_record(marker, target_group_id)

    @staticmethod
    def _apply_target_disposition(
        row: InferenceProcessingTarget, disposition: TargetDisposition
    ) -> None:
        """Project one nonnull operator decision onto a target checkpoint's inference state.

        It sets only the inference state and its safe inference error. Every payload, the
        planned key, the proposal pointer, the calculation-started fact and the multiview/rerank
        states are preserved, so clearing reuses completed work. An upstream multiview or
        rerank failure keeps its own error text: the durable marker decision, never error text, is
        the terminal authority.
        """
        row.inference_state = "completed" if disposition == "done" else "failed"
        if row.multiview_state == "failed" or row.rerank_state == "failed":
            return
        row.error_type = None if disposition == "done" else _OPERATOR_DISPOSITION_ERROR

    def _clear_target_to_automatic(
        self,
        cycle: InferenceProcessingCycle,
        row: InferenceProcessingTarget,
        target_group_id: str,
    ) -> None:
        """Return one target's latest checkpoint to automatic eligibility inside the setter.

        Only this target's row is touched: the decision-owned inference state is reopened pending,
        the staged proposal pointer is cleared, and the genuine planned key/predecessor stay for the
        pruning closure to protect. Completed upstream selection is preserved when a retained
        shortlist or recoverable completed planned work exists. Otherwise only the genuinely
        unavailable stage is reopened (rerank with a retained pool, or multiview plus rerank without
        one). Already pending/failed upstream work keeps its payloads. The cycle is rewound to this
        target's earliest nonterminal stage, bounded by its current stage, and complete/publication may
        reopen and every other target row is intact. ``generation_started`` is preserved: clearing
        is not a new calculation and reuses no consumed seed.
        """
        planned_key = row.generation_work_key_sha256
        recoverable = False
        if planned_key is not None:
            work = self._evidence.read_work(target_group_id, planned_key)
            recoverable = work is not None and work.status is InferenceWorkStatus.COMPLETED
        if row.target_input is None and not recoverable:
            if row.pool_input is not None and row.multiview_state == "completed":
                if row.rerank_state in ("completed", "skipped"):
                    row.rerank_state = "pending"
            else:
                if row.multiview_state in ("completed", "skipped"):
                    row.multiview_state = "pending"
                if row.rerank_state in ("completed", "skipped"):
                    row.rerank_state = "pending"
        row.inference_state = "pending"
        row.error_type = None
        row.proposal_id = None
        target_index = next(
            (
                index
                for index, state in enumerate(
                    (row.multiview_state, row.rerank_state, row.inference_state)
                )
                if state in ("pending", "failed")
            ),
            None,
        )
        cycle_index = (
            _STAGE_ORDER.index(cycle.stage)
            if cycle.stage in _SETTABLE_STAGES
            else len(_STAGE_ORDER)
        )
        if target_index is not None and target_index < cycle_index:
            cycle.stage = _STAGE_ORDER[target_index]

    @staticmethod
    def _marker_disposition(session: Session, target_group_id: str) -> str | None:
        """Return one canonical target's durable operator decision at a real decision boundary."""
        return session.scalar(
            select(InferenceCourseProcessing.disposition)
            .join(Course, Course.id == InferenceCourseProcessing.course_id)
            .where(Course.group_id == target_group_id)
        )

    def checkpoint(self, target: ProcessingTargetRecord) -> ProcessingTargetRecord:
        """Persist one per-target stage checkpoint, refusing illegal transitions.

        It locks the unfinished cycle and its one target row and applies only legal
        pending/failed-to-terminal transitions through the one transition owner. It manages compact
        payload lifecycles: a completed multiview serializes its pool. A rerank completion or
        skip releases the consumed pool (the skip has already consumed it through ``_require_skip``).
        A completed rerank serializes its shortlist. An inference skip releases the consumed
        shortlist. Planned-key/failure-only writes leave JSON columns alone, and a
        new inference completion or proposal is owned solely by :meth:`accept_target`. An identical
        decision-owned terminal inference/key/proposal is permitted so a legitimate upstream
        checkpoint can advance for that target.
        """
        with session_scope(self._factory) as session:
            cycle = self._require_latest_unfinished(session, expected_id=target.cycle_id)
            row = self._target_row(session, cycle.id, target.target_group_id, for_update=True)
            if row is None:
                raise ValueError(f"target {target.target_group_id} is not part of the latest cycle")
            stored = self._target_record(row, target.target_group_id)
            new_completion = (
                target.inference_state == "completed" and stored.inference_state != "completed"
            )
            new_proposal = (
                target.proposal_id is not None and target.proposal_id != stored.proposal_id
            )
            if new_completion or new_proposal:
                raise ValueError("inference completion is owned by accept_target, not checkpoint")
            self._validate_transition(session, cycle, stored, target)
            if target.rerank_state == "skipped" and stored.rerank_state != "skipped":
                self._require_skip(session, stored, target, rerank=True)
            if target.inference_state == "skipped" and stored.inference_state != "skipped":
                if not (target.rerank_state == "skipped" and stored.rerank_state != "skipped"):
                    self._require_skip(session, stored, target, rerank=False)
            row.multiview_state = target.multiview_state
            row.rerank_state = target.rerank_state
            row.inference_state = target.inference_state
            row.generation_work_key_sha256 = target.generation_work_key_sha256
            row.error_type = target.error_type
            if target.multiview_state == "completed" and stored.multiview_state != "completed":
                row.pool_input = (
                    None if target.pool_input is None else target.pool_input.model_dump(mode="json")
                )
            if target.rerank_state in ("completed", "skipped") and stored.rerank_state not in (
                "completed",
                "skipped",
            ):
                row.pool_input = None
            if target.rerank_state == "completed" and stored.rerank_state != "completed":
                row.target_input = (
                    None
                    if target.target_input is None
                    else target.target_input.model_dump(mode="json")
                )
            if target.rerank_state == "skipped":
                row.target_input = None
            if target.inference_state == "skipped" and stored.inference_state != "skipped":
                row.target_input = None
            session.flush()
            session.refresh(row)
            return self._target_record(row, target.target_group_id)

    def set_stage(
        self,
        cycle_id: UUID,
        stage: str,
        *,
        exhausted_target_group_ids: Collection[str] = (),
    ) -> None:
        """Advance the unfinished cycle by exactly one adjacent forward stage.

        ``exhausted_target_group_ids`` names the targets whose current-stage failure this invocation
        actually exhausted, so their failed stage (and a dependent pending downstream stage) does not
        block the forward transition.
        """
        if stage not in _SETTABLE_STAGES:
            raise ValueError("stage must be multiview, rerank, inference, or publication")
        with session_scope(self._factory) as session:
            cycle = session.scalar(
                select(InferenceProcessingCycle)
                .where(InferenceProcessingCycle.id == cycle_id)
                .with_for_update()
            )
            if cycle is None:
                raise ValueError(f"unknown inference processing cycle {cycle_id}")
            latest = self._latest_cycle(session)
            if latest is None or latest.id != cycle.id:
                raise ValueError("only the latest retained cycle may advance its stage")
            if cycle.stage == "complete":
                raise ValueError("a completed cycle cannot change stage")
            if cycle.stage == stage:
                return
            current_index = _STAGE_ORDER.index(cycle.stage)
            if _STAGE_ORDER.index(stage) != current_index + 1:
                raise ValueError("only adjacent forward stage transitions are allowed")
            self._require_stage_settled(
                session,
                cycle.id,
                cycle.stage,
                exhausted_target_group_ids=exhausted_target_group_ids,
            )
            cycle.stage = stage

    def accept_target(
        self, cycle_id: UUID, target_group_id: str, proposal: TargetProposal
    ) -> CourseProcessingRecord:
        """Atomically accept one completed whole-target result and mark its course processed.

        The saved proposal must equal the supplied DTO and belong to the supplied FK target, and the
        retained planned work key must bind the recorded completed work. Under one cycle/target/marker
        lock it sets the inference stage completed with the proposal pointer and the course marker
        processed TRUE. An identical retry succeeds. A conflicting completed result fails.
        """
        _require_text(target_group_id, "target_group_id")
        if not isinstance(proposal, TargetProposal):
            raise ValueError("proposal must be a TargetProposal")
        saved, work, _completion, _run = self._read_completed_proposal(proposal.proposal_id)
        if saved != proposal:
            raise ValueError("the supplied proposal does not match the saved proposal")
        if saved.target_group_id != target_group_id:
            raise ValueError("the proposal does not belong to the supplied target")
        with session_scope(self._factory) as session:
            cycle = self._require_latest_unfinished(session, expected_id=cycle_id)
            if cycle.stage != "inference":
                raise ValueError("acceptance requires the inference stage")
            course = session.scalar(
                select(Course).where(Course.group_id == target_group_id).with_for_update()
            )
            if course is None or not course.is_active:
                raise ValueError(f"target {target_group_id} is not a current active course")
            marker = session.scalar(
                select(InferenceCourseProcessing)
                .where(InferenceCourseProcessing.course_id == course.id)
                .with_for_update()
            )
            if marker is None:
                raise ValueError(f"target {target_group_id} has no processing marker")
            if marker.disposition is not None:
                raise ValueError(
                    "an operator decision owns this target; clear it before acceptance"
                )
            row = session.scalar(
                select(InferenceProcessingTarget)
                .where(
                    InferenceProcessingTarget.cycle_id == cycle.id,
                    InferenceProcessingTarget.target_course_id == course.id,
                )
                .with_for_update()
            )
            if row is None:
                raise ValueError(f"target {target_group_id} is not part of the latest cycle")
            if row.inference_state == "completed":
                if row.proposal_id == proposal.proposal_id:
                    return self._marker_record(marker, target_group_id)
                raise ValueError("conflicting completed inference result for this target")
            if row.inference_state not in ("pending", "failed"):
                raise ValueError("a skipped inference target cannot be accepted")
            if row.multiview_state != "completed" or row.rerank_state != "completed":
                raise ValueError("acceptance requires completed multiview and rerank stages")
            if row.generation_work_key_sha256 != work.work_key_sha256:
                raise ValueError("the planned work key does not match the recorded work key")
            row.inference_state = "completed"
            row.proposal_id = proposal.proposal_id
            row.error_type = None
            row.target_input = None
            marker.processed = True
            marker.accepted_proposal_id = proposal.proposal_id
            session.flush()
            return self._marker_record(marker, target_group_id)

    def finish_cycle(self, cycle_id: UUID, *, input_sha256: str) -> ProcessingCycleRecord:
        """Complete one publication-stage cycle and bulk-mark every catalogue course processed.

        It requires the unfinished cycle on the publication stage, no pending/failed required
        target, full marker coverage of the database catalogue, and the caller's recomputed input
        digest to equal the recorded cycle input. After a successful call it marks ALL canonical
        courses TRUE (inactive included) and marks the cycle complete in one transaction. Identical
        retry returns the same record, and partial/rerank-only/failed cycles never finish.
        """
        _require_sha256(input_sha256, "cycle input_sha256")
        with session_scope(self._factory) as session:
            cycle = session.scalar(
                select(InferenceProcessingCycle)
                .where(InferenceProcessingCycle.id == cycle_id)
                .with_for_update()
            )
            if cycle is None:
                raise ValueError(f"unknown inference processing cycle {cycle_id}")
            latest = self._latest_cycle(session)
            if latest is None or latest.id != cycle.id:
                raise ValueError("only the latest retained cycle may finish")
            if cycle.stage == "complete":
                if cycle.input_sha256 != input_sha256:
                    raise ValueError("the supplied input digest does not match the completed cycle")
                return self._cycle_record(cycle)
            if cycle.stage != "publication":
                raise ValueError("finishing requires the publication stage")
            if cycle.input_sha256 != input_sha256:
                raise ValueError("the supplied input digest does not match the cycle input")
            self._require_cycle_terminal(session, cycle.id)
            missing_markers = session.scalar(
                select(func.count())
                .select_from(Course)
                .outerjoin(
                    InferenceCourseProcessing,
                    InferenceCourseProcessing.course_id == Course.id,
                )
                .where(InferenceCourseProcessing.course_id.is_(None))
            )
            if missing_markers:
                raise ValueError(
                    "processing does not cover every canonical course; cannot bulk-mark processed"
                )
            session.execute(update(InferenceCourseProcessing).values(processed=True))
            cycle.stage = "complete"
            session.flush()
            return self._cycle_record(cycle)

    def prune_retained_state(self) -> None:
        """Prune proposals, completions, work and executions no owner references any more.

        Called after successful publication. It removes proposals not referenced by any course
        marker (inactive included) or by a current-cycle staged target, then their unreferenced
        completions, work rows and shared executions. Every current-cycle planned generation key and
        its complete dependency closure (its completion and any already-composed proposal) is always
        protected, so an uncomposed or composed-but-unaccepted completed result is recoverable
        instead of being regenerated.
        """
        with session_scope(self._factory) as session:
            current_cycle_id = session.scalar(
                select(InferenceProcessingCycle.id)
                .order_by(
                    InferenceProcessingCycle.created_at.desc(),
                    InferenceProcessingCycle.id.desc(),
                )
                .limit(1)
            )
            protected_proposals: set[UUID] = {
                proposal_id
                for proposal_id in session.scalars(
                    select(InferenceCourseProcessing.accepted_proposal_id)
                )
                if proposal_id is not None
            }
            if current_cycle_id is not None:
                protected_proposals |= {
                    proposal_id
                    for proposal_id in session.scalars(
                        select(InferenceProcessingTarget.proposal_id).where(
                            InferenceProcessingTarget.cycle_id == current_cycle_id
                        )
                    )
                    if proposal_id is not None
                }
            protected_completions: set[UUID] = set()
            if protected_proposals:
                protected_completions |= set(
                    session.scalars(
                        select(InferenceProposal.source_attempt_id).where(
                            InferenceProposal.id.in_(tuple(protected_proposals))
                        )
                    )
                )
            protected_work: set[UUID] = set()
            if current_cycle_id is not None:
                planned = session.execute(
                    select(
                        InferenceProcessingTarget.target_course_id,
                        InferenceProcessingTarget.generation_work_key_sha256,
                    ).where(
                        InferenceProcessingTarget.cycle_id == current_cycle_id,
                        InferenceProcessingTarget.generation_work_key_sha256.is_not(None),
                    )
                ).all()
                for target_course_id, work_key in planned:
                    work_id = session.scalar(
                        select(InferenceTargetWork.id).where(
                            InferenceTargetWork.target_course_id == target_course_id,
                            InferenceTargetWork.work_key_sha256 == work_key,
                        )
                    )
                    if work_id is not None:
                        protected_work.add(work_id)
            if protected_completions:
                protected_work |= set(
                    session.scalars(
                        select(InferenceModelAttempt.target_work_id).where(
                            InferenceModelAttempt.id.in_(tuple(protected_completions))
                        )
                    )
                )
            if protected_work:
                # Protect the complete planned-generation dependency closure: an uncomposed
                # completion awaiting composition or an already-composed proposal awaiting
                # acceptance must survive so the next entry recovers the completed generation
                # instead of regenerating it. The outer join tolerates proposal absence and no
                # result JSON or ORM entity is fetched.
                for completion_id, proposal_id in session.execute(
                    select(InferenceModelAttempt.id, InferenceProposal.id)
                    .outerjoin(
                        InferenceProposal,
                        InferenceProposal.source_attempt_id == InferenceModelAttempt.id,
                    )
                    .where(InferenceModelAttempt.target_work_id.in_(tuple(protected_work)))
                ).all():
                    protected_completions.add(completion_id)
                    if proposal_id is not None:
                        protected_proposals.add(proposal_id)
            self._delete_unprotected(
                session, InferenceProposal, InferenceProposal.id, protected_proposals
            )
            self._delete_unprotected(
                session, InferenceModelAttempt, InferenceModelAttempt.id, protected_completions
            )
            self._delete_unprotected(
                session, InferenceTargetWork, InferenceTargetWork.id, protected_work
            )
            session.execute(
                delete(InferencePipelineRun).where(
                    InferencePipelineRun.id.not_in(select(InferenceTargetWork.created_by_run_id))
                )
            )

    def _read_completed_proposal(
        self, proposal_id: UUID
    ) -> tuple[
        TargetProposal,
        InferenceTargetWorkRecord,
        InferenceModelAttemptRecord,
        InferencePipelineRunRecord,
    ]:
        """Delegate to the proposal repository's one shared completed read."""
        return self._proposals.read_completed(proposal_id)

    @staticmethod
    def _earliest_failed_stage(session: Session, cycle_id: UUID) -> str | None:
        """Return the earliest stage any target of one cycle is failed at, if any.

        Only the three stage-state columns are projected.
        ``inference_preparation`` is an inference-state failure and therefore reports ``inference``.
        """
        rows = session.execute(
            select(
                InferenceProcessingTarget.multiview_state,
                InferenceProcessingTarget.rerank_state,
                InferenceProcessingTarget.inference_state,
            ).where(InferenceProcessingTarget.cycle_id == cycle_id)
        ).all()
        earliest: int | None = None
        for multiview, rerank, inference in rows:
            for index, state in ((0, multiview), (1, rerank), (2, inference)):
                if state == "failed" and (earliest is None or index < earliest):
                    earliest = index
        return None if earliest is None else _STAGE_ORDER[earliest]

    @staticmethod
    def _latest_cycle(
        session: Session, *, for_update: bool = False
    ) -> InferenceProcessingCycle | None:
        statement = (
            select(InferenceProcessingCycle)
            .order_by(
                InferenceProcessingCycle.created_at.desc(),
                InferenceProcessingCycle.id.desc(),
            )
            .limit(1)
        )
        if for_update:
            statement = statement.with_for_update()
        return session.scalar(statement)

    @staticmethod
    def _require_latest_unfinished(
        session: Session, *, expected_id: UUID | None = None
    ) -> InferenceProcessingCycle:
        latest = InferenceSchedulingRepository._latest_cycle(session, for_update=True)
        if latest is None:
            raise ValueError("no processing cycle exists")
        if latest.stage == "complete":
            raise ValueError("the latest retained cycle is already complete")
        if expected_id is not None and latest.id != expected_id:
            raise ValueError("the checkpoint is not for the latest retained cycle")
        return latest

    @staticmethod
    def _cycle_record(cycle: InferenceProcessingCycle) -> ProcessingCycleRecord:
        return ProcessingCycleRecord(
            cycle_id=cycle.id,
            input_sha256=cycle.input_sha256,
            stage=cycle.stage,
        )

    @staticmethod
    def _marker_record(marker: InferenceCourseProcessing, group_id: str) -> CourseProcessingRecord:
        return CourseProcessingRecord(
            group_id=group_id,
            teaching_text_sha256=marker.teaching_text_sha256,
            processed=marker.processed,
            was_active=marker.was_active,
            accepted_proposal_id=marker.accepted_proposal_id,
            disposition=marker.disposition,
        )

    @staticmethod
    def _target_record(
        row: InferenceProcessingTarget, target_group_id: str
    ) -> ProcessingTargetRecord:
        payload = {
            "cycle_id": row.cycle_id,
            "target_group_id": target_group_id,
            "multiview_state": row.multiview_state,
            "rerank_state": row.rerank_state,
            "inference_state": row.inference_state,
            "pool_input": row.pool_input,
            "target_input": row.target_input,
            "generation_work_key_sha256": row.generation_work_key_sha256,
            "proposal_id": row.proposal_id,
            "error_type": row.error_type,
        }
        return ProcessingTargetRecord.model_validate_json(json.dumps(payload, default=str))

    @staticmethod
    def _target_row(
        session: Session,
        cycle_id: UUID,
        target_group_id: str,
        *,
        for_update: bool = False,
    ) -> InferenceProcessingTarget | None:
        statement = (
            select(InferenceProcessingTarget)
            .join(Course, Course.id == InferenceProcessingTarget.target_course_id)
            .where(
                InferenceProcessingTarget.cycle_id == cycle_id,
                Course.group_id == target_group_id,
            )
        )
        if for_update:
            statement = statement.with_for_update()
        return session.scalar(statement)

    @staticmethod
    def _processing_records(
        session: Session, group_ids: Sequence[str] | None = None
    ) -> tuple[CourseProcessingRecord, ...]:
        """Read the marker projection over all markers or the supplied exact group IDs.

        Only ``Course.group_id`` and the marker's hash/flags/pointer/decision columns are selected,
        joined on the course identity and sorted by group ID. No ORM marker entity, timestamp, or
        course ID is hydrated, so a whole-catalogue summary and a scoped per-unit check share one
        bounded read. ``None`` selects every marker. An explicit empty scope returns ``()`` without a
        query.
        """
        statement = (
            select(
                Course.group_id,
                InferenceCourseProcessing.teaching_text_sha256,
                InferenceCourseProcessing.processed,
                InferenceCourseProcessing.was_active,
                InferenceCourseProcessing.accepted_proposal_id,
                InferenceCourseProcessing.disposition,
            )
            .join(Course, Course.id == InferenceCourseProcessing.course_id)
            .order_by(Course.group_id)
        )
        if group_ids is not None:
            ids = tuple(group_ids)
            if not ids:
                return ()
            statement = statement.where(Course.group_id.in_(ids))
        rows = session.execute(statement).all()
        return tuple(
            CourseProcessingRecord(
                group_id=group_id,
                teaching_text_sha256=teaching_text_sha256,
                processed=processed,
                was_active=was_active,
                accepted_proposal_id=accepted_proposal_id,
                disposition=disposition,
            )
            for (
                group_id,
                teaching_text_sha256,
                processed,
                was_active,
                accepted_proposal_id,
                disposition,
            ) in rows
        )

    @staticmethod
    def _live_markers(
        session: Session, group_ids: Sequence[str]
    ) -> dict[str, CourseProcessingRecord]:
        ids = tuple(group_ids)
        if not ids:
            return {}
        by_group = {
            record.group_id: record
            for record in InferenceSchedulingRepository._processing_records(session, ids)
        }
        missing = set(ids) - set(by_group)
        if missing:
            raise ValueError(f"processing markers are missing for {sorted(missing)}")
        return by_group

    def _validate_transition(
        self,
        session: Session,
        cycle: InferenceProcessingCycle,
        stored: ProcessingTargetRecord,
        target: ProcessingTargetRecord,
    ) -> None:
        """Reject any illegal stage transition and require the matching cycle stage."""
        multiview_changed = stored.multiview_state != target.multiview_state or _pool_digest(
            stored
        ) != _pool_digest(target)
        rerank_changed = stored.rerank_state != target.rerank_state or _target_digest(
            stored
        ) != _target_digest(target)
        inference_changed = stored.inference_state != target.inference_state
        key_changed = stored.generation_work_key_sha256 != target.generation_work_key_sha256
        if (inference_changed or key_changed or target.proposal_id != stored.proposal_id) and (
            self._marker_disposition(session, target.target_group_id) is not None
        ):
            # An automatic checkpoint may advance legitimate upstream stages, but it can never
            # rewrite the inference state, planned key or proposal the operator decision owns. The
            # marker is read only when one of those decision-owned fields actually changes.
            raise ValueError(
                "an operator decision owns this target's inference state, planned key and proposal"
            )
        if stored.multiview_state in ("completed", "skipped"):
            if target.multiview_state != stored.multiview_state or _pool_digest(
                target
            ) != _pool_digest(stored):
                raise ValueError("a completed multiview stage is immutable")
        elif target.multiview_state == "pending" and stored.multiview_state == "failed":
            raise ValueError("a failed multiview stage cannot return to pending")
        if stored.rerank_state in ("completed", "skipped"):
            if target.rerank_state != stored.rerank_state or _target_digest(
                target
            ) != _target_digest(stored):
                raise ValueError("a completed or skipped rerank stage is immutable")
        elif target.rerank_state == "pending" and stored.rerank_state == "failed":
            raise ValueError("a failed rerank stage cannot return to pending")
        if stored.inference_state in ("completed", "skipped"):
            if target.inference_state != stored.inference_state:
                raise ValueError("a completed or skipped inference stage is immutable")
        elif target.inference_state == "pending" and stored.inference_state == "failed":
            raise ValueError("a failed inference stage cannot return to pending")
        if multiview_changed and cycle.stage != "multiview":
            raise ValueError("a multiview checkpoint requires the multiview stage")
        if rerank_changed and cycle.stage != "rerank":
            raise ValueError("a rerank checkpoint requires the rerank stage")
        if (inference_changed or key_changed) and cycle.stage != "inference":
            # The one legitimate cascade: during rerank, a rerank skip atomically skips inference
            # with no target input and no planned-key change. The live membership predicate
            # flows through _require_skip(..., rerank=True) in checkpoint.
            rerank_skip_cascade = (
                cycle.stage == "rerank"
                and not key_changed
                and stored.rerank_state in ("pending", "failed")
                and target.rerank_state == "skipped"
                and stored.inference_state == "pending"
                and target.inference_state == "skipped"
            )
            if not rerank_skip_cascade:
                raise ValueError("an inference checkpoint requires the inference stage")

    def _require_skip(
        self,
        session: Session,
        stored: ProcessingTargetRecord,
        target: ProcessingTargetRecord,
        *,
        rerank: bool,
    ) -> None:
        """Require the live membership predicate to be FALSE before a legitimate skip."""
        if rerank and stored.rerank_state == "failed":
            raise ValueError("a failed rerank stage cannot be skipped")
        if not rerank and stored.inference_state == "failed":
            raise ValueError("a failed inference stage cannot be skipped")
        if rerank:
            pool = target.pool_input if target.pool_input is not None else stored.pool_input
            if pool is None:
                raise ValueError("a rerank skip requires the retained multiview pool")
            candidate_ids = tuple(reference.group_id for reference in pool.references.candidates)
        else:
            target_input = (
                target.target_input if target.target_input is not None else stored.target_input
            )
            if target_input is None:
                raise ValueError("an inference skip requires the retained top-50 target input")
            candidate_ids = tuple(
                reference.group_id for reference in target_input.references.candidates
            )
        markers = self._live_markers(session, (*candidate_ids, target.target_group_id))
        own = markers[target.target_group_id]
        predicate = (
            select_rerank(own.processed, candidate_ids, markers)
            if rerank
            else select_inference(own.processed, candidate_ids, markers)
        )
        if predicate:
            raise ValueError("a skip is only legitimate when the live membership filter is FALSE")

    @staticmethod
    def _failure_record(
        failure: InferenceTargetFailure, target_group_id: str
    ) -> TargetFailureRecord:
        """Map one inserted failure row to its retained read contract."""
        return TargetFailureRecord(
            failure_id=failure.id,
            cycle_id=failure.cycle_id,
            target_group_id=target_group_id,
            stage=failure.stage,
            attempt_count=failure.attempt_count,
            error_type=failure.error_type,
            reason=failure.reason,
            exhausted=failure.exhausted,
            created_at=failure.created_at,
        )

    @staticmethod
    def _prune_superseded_cycles(session: Session, *, keep_cycle_id: UUID | None = None) -> None:
        """Delete checkpoint rows no retained failure episode references, keeping anchors payload-free.

        Cycles and targets referenced by a retained failure episode stay as referential anchors
        with their ids/state but no pool/shortlist/planned-key/proposal payload. Every other
        checkpoint row is deleted. The current cycle is always kept.
        """
        anchors = set(
            session.execute(
                select(InferenceTargetFailure.cycle_id, InferenceTargetFailure.target_course_id)
            ).all()
        )
        anchor_cycles = {cycle_id for cycle_id, _ in anchors}
        if keep_cycle_id is not None:
            anchor_cycles.add(keep_cycle_id)
        if anchors:
            session.execute(
                update(InferenceProcessingTarget)
                .where(
                    tuple_(
                        InferenceProcessingTarget.cycle_id,
                        InferenceProcessingTarget.target_course_id,
                    ).in_(tuple(anchors))
                )
                .values(
                    pool_input=None,
                    target_input=None,
                    generation_work_key_sha256=None,
                    proposal_id=None,
                )
            )
            session.execute(
                delete(InferenceProcessingTarget).where(
                    ~tuple_(
                        InferenceProcessingTarget.cycle_id,
                        InferenceProcessingTarget.target_course_id,
                    ).in_(tuple(anchors))
                )
            )
        else:
            session.execute(delete(InferenceProcessingTarget))
        if anchor_cycles:
            session.execute(
                delete(InferenceProcessingCycle).where(
                    InferenceProcessingCycle.id.not_in(tuple(anchor_cycles))
                )
            )
        else:
            session.execute(delete(InferenceProcessingCycle))

    @staticmethod
    def _delete_unprotected(
        session: Session, model: type, id_column: object, protected: set[UUID]
    ) -> None:
        """Delete every row of one table whose id is not in the protected set."""
        if protected:
            session.execute(delete(model).where(id_column.not_in(tuple(protected))))
        else:
            session.execute(delete(model))

    @staticmethod
    def _require_stage_settled(
        session: Session,
        cycle_id: UUID,
        stage: str,
        *,
        exhausted_target_group_ids: Collection[str] = (),
    ) -> None:
        """Require every target row of the current stage to be terminal or an exhausted failure.

        Besides completed/legitimate-skipped states it allows the current failed stage of a
        caller-named exhausted target, a marker-owned terminal FAILED decision at the inference stage
        (so a terminal operator failure can move on to publication without being retried), and a
        dependent pending downstream stage whose upstream failure is in that same exhausted scope. Any
        other pending/failed row blocks the transition.
        """
        exhausted = set(exhausted_target_group_ids)
        if stage == "multiview":
            terminal = InferenceProcessingTarget.multiview_state == "completed"
        elif stage == "rerank":
            terminal = InferenceProcessingTarget.rerank_state.in_(("completed", "skipped"))
        else:
            terminal = InferenceProcessingTarget.inference_state.in_(("completed", "skipped"))
        rows = session.execute(
            select(
                Course.group_id,
                InferenceProcessingTarget.multiview_state,
                InferenceProcessingTarget.rerank_state,
                InferenceProcessingTarget.inference_state,
            )
            .join(Course, Course.id == InferenceProcessingTarget.target_course_id)
            .where(InferenceProcessingTarget.cycle_id == cycle_id, ~terminal)
        ).all()
        operator_failed: set[str] = set()
        if stage == "inference":
            failed_ids = tuple(
                group_id for group_id, _mv, _rr, inference in rows if inference == "failed"
            )
            if failed_ids:
                operator_failed = set(
                    session.scalars(
                        select(Course.group_id)
                        .join(
                            InferenceCourseProcessing,
                            InferenceCourseProcessing.course_id == Course.id,
                        )
                        .where(
                            Course.group_id.in_(failed_ids),
                            InferenceCourseProcessing.disposition == "failed",
                        )
                    )
                )
        blocked: list[str] = []
        for group_id, multiview, rerank, inference in rows:
            allowed = False
            if group_id in exhausted:
                if stage == "multiview":
                    allowed = multiview == "failed"
                elif stage == "rerank":
                    allowed = rerank == "failed" or (rerank == "pending" and multiview == "failed")
                else:
                    allowed = inference == "failed" or (
                        inference == "pending" and (rerank == "failed" or multiview == "failed")
                    )
            elif stage == "inference" and group_id in operator_failed:
                allowed = True
            if not allowed:
                blocked.append(group_id)
        if blocked:
            raise ValueError(f"cycle stage {stage} still has non-terminal target rows")

    @staticmethod
    def _require_cycle_terminal(session: Session, cycle_id: UUID) -> None:
        """Require every target checkpoint to be a completed/legitimate-skip terminal matrix."""
        bad = session.scalar(
            select(func.count())
            .select_from(InferenceProcessingTarget)
            .where(
                InferenceProcessingTarget.cycle_id == cycle_id,
                (
                    (InferenceProcessingTarget.multiview_state != "completed")
                    | InferenceProcessingTarget.rerank_state.not_in(("completed", "skipped"))
                    | InferenceProcessingTarget.inference_state.not_in(("completed", "skipped"))
                ),
            )
        )
        if bad:
            raise ValueError("cycle has pending or failed target rows and cannot finish")
