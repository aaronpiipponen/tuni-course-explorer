"""Sole transaction owner for immutable inference-owned result proposals.

This repository persists one append-only ``inference_proposals`` row per versioned proposal identity.
It validates the current active target/activity context, the referenced completed work and its
matching completion, and the proposal id/version before writing, reuses an identical identity
as-is, and rejects a conflicting same identity. On save it releases the completion's consumed
descriptors and uncomposed result in the same transaction. It never calls the final inferred-set or
equivalence publication repositories, never writes official curriculum, and never recalculates a
proposal from raw evidence.
"""

from __future__ import annotations

import json
from collections.abc import Collection
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from course_explorer.db.models import (
    Course,
    InferenceModelAttempt,
    InferenceProposal,
    InferenceTargetWork,
)
from course_explorer.db.session import session_scope
from course_explorer.enums import InferenceWorkStatus
from course_explorer.inference.evidence import (
    InferenceModelAttemptRecord,
    InferencePipelineRunRecord,
    InferenceTargetWorkRecord,
)
from course_explorer.inference.evidence_repository import InferenceEvidenceRepository
from course_explorer.inference.proposals import (
    AcceptedOptionFlags,
    EquivalenceProposalCandidate,
    TargetProposal,
)
from course_explorer.prerequisite.domain import (
    dump_prerequisite_expression,
    parse_prerequisite_expression,
)


def _decode_equivalence(value: list[object]) -> tuple[EquivalenceProposalCandidate, ...]:
    """Rebuild the strict equivalence candidates from their stored JSON-native records."""
    return tuple(
        EquivalenceProposalCandidate.model_validate_json(json.dumps(item)) for item in value
    )


def _decode_option_flags(value: list[object]) -> tuple[AcceptedOptionFlags, ...]:
    """Rebuild the strict accepted-option flags from their stored JSON-native records."""
    return tuple(AcceptedOptionFlags.model_validate_json(json.dumps(item)) for item in value)


class InferenceProposalRepository:
    """Append-only persistence for immutable inference-owned accepted-result proposals."""

    def __init__(self, factory: sessionmaker[Session]) -> None:
        self._factory = factory
        self._evidence = InferenceEvidenceRepository(factory)

    def save(self, proposal: TargetProposal) -> TargetProposal:
        """Validate and append one proposal, releasing consumed completion content atomically."""
        envelope = {
            "expression": (
                None
                if proposal.expression is None
                else dump_prerequisite_expression(proposal.expression)
            ),
            "option_flags": [flags.model_dump(mode="json") for flags in proposal.option_flags],
        }
        equivalence_dump = [candidate.model_dump(mode="json") for candidate in proposal.equivalence]
        with session_scope(self._factory) as session:
            course = session.scalar(
                select(Course).where(Course.group_id == proposal.target_group_id).with_for_update()
            )
            if course is None:
                raise ValueError(f"unknown canonical target course {proposal.target_group_id}")
            if not course.is_active:
                raise ValueError(
                    f"cannot store a proposal for inactive target {proposal.target_group_id}"
                )
            completion = session.scalar(
                select(InferenceModelAttempt)
                .where(InferenceModelAttempt.id == proposal.source_attempt_id)
                .with_for_update()
            )
            if completion is None:
                raise ValueError(f"unknown inference completion {proposal.source_attempt_id}")
            work = session.scalar(
                select(InferenceTargetWork)
                .where(InferenceTargetWork.id == completion.target_work_id)
                .with_for_update()
            )
            if work is None:
                raise ValueError("the referenced completion has no target work")
            if work.target_course_id != course.id:
                raise ValueError("the referenced work does not belong to the proposal target")
            if work.status is not InferenceWorkStatus.COMPLETED:
                raise ValueError("a proposal requires completed referenced work")
            if (
                work.activity_as_of_academic_year_start != course.activity_as_of_academic_year_start
                or work.activity_window_years != course.activity_window_years
            ):
                raise ValueError("the referenced work activity context is stale for the target")
            if proposal.proposal_id != uuid5(NAMESPACE_URL, proposal.identity_sha256):
                raise ValueError("the proposal id does not match its identity digest")
            existing = session.scalar(
                select(InferenceProposal).where(
                    InferenceProposal.identity_sha256 == proposal.identity_sha256
                )
            )
            if existing is not None:
                if (
                    existing.proposal_version == proposal.proposal_version
                    and existing.target_course_id == course.id
                    and existing.source_attempt_id == proposal.source_attempt_id
                    and existing.expression == envelope
                    and existing.equivalence == equivalence_dump
                ):
                    return self._decode(existing, proposal.target_group_id)
                raise ValueError("conflicting proposal identity for an existing proposal digest")
            row = InferenceProposal(
                id=proposal.proposal_id,
                target_course_id=course.id,
                source_attempt_id=proposal.source_attempt_id,
                proposal_version=proposal.proposal_version,
                identity_sha256=proposal.identity_sha256,
                expression=envelope,
                equivalence=equivalence_dump,
            )
            session.add(row)
            completion.request_payload = {
                "facts": completion.request_payload["facts"],
                "descriptors": None,
                "result": None,
            }
            session.flush()
            session.refresh(row)
            return self._decode(row, proposal.target_group_id)

    def read_completed(
        self, proposal_id: UUID
    ) -> tuple[
        TargetProposal,
        InferenceTargetWorkRecord,
        InferenceModelAttemptRecord,
        InferencePipelineRunRecord,
    ]:
        """Read one proposal with its work, completion and shared execution by real FK joins."""
        proposal = self.read_by_id(proposal_id)
        with self._factory() as session:
            work_id = session.scalar(
                select(InferenceModelAttempt.target_work_id).where(
                    InferenceModelAttempt.id == proposal.source_attempt_id
                )
            )
        if work_id is None:
            raise ValueError("the proposal references no recorded completion")
        work = self._evidence.read_work_by_id(work_id)
        completion = self._evidence.read_completion(work_id)
        if completion is None:
            raise ValueError("the proposal references no recorded completion")
        run = self._evidence.read_run(work.created_by_run_id)
        return proposal, work, completion, run

    def read_completed_many(
        self, proposal_ids: Collection[UUID]
    ) -> dict[
        UUID,
        tuple[
            TargetProposal,
            InferenceTargetWorkRecord,
            InferenceModelAttemptRecord,
            InferencePipelineRunRecord,
        ],
    ]:
        """Read many proposals with their work, completion and execution in a fixed number of reads.

        Each entry equals what `read_completed` returns for that id, and an unknown id or a missing
        completion fails with the same message. The reads are one proposal join and one batch read
        each of the work rows, the completions and the executions.
        """
        if not all(isinstance(proposal_id, UUID) for proposal_id in proposal_ids):
            raise ValueError("proposal_id must be a UUID")
        requested = set(proposal_ids)
        if not requested:
            return {}
        with self._factory() as session:
            rows = session.execute(
                select(InferenceProposal, Course.group_id, InferenceModelAttempt.target_work_id)
                .join(Course, Course.id == InferenceProposal.target_course_id)
                .outerjoin(
                    InferenceModelAttempt,
                    InferenceModelAttempt.id == InferenceProposal.source_attempt_id,
                )
                .where(InferenceProposal.id.in_(requested))
            ).all()
            decoded = {
                row.id: (self._decode(row, target_group_id=target_group_id), work_id)
                for row, target_group_id, work_id in rows
            }
        for proposal_id in proposal_ids:
            if proposal_id not in decoded:
                raise ValueError(f"unknown inference proposal {proposal_id}")
        work_ids = {work_id for _, work_id in decoded.values() if work_id is not None}
        works = self._evidence.read_works_by_ids(work_ids)
        completions = self._evidence.read_completions_for_works(work_ids)
        runs = self._evidence.read_runs({work.created_by_run_id for work in works.values()})
        completed = {}
        for proposal_id, (proposal, work_id) in decoded.items():
            if work_id is None:
                raise ValueError("the proposal references no recorded completion")
            if work_id not in works:
                raise ValueError(f"unknown inference target work {work_id}")
            if work_id not in completions:
                raise ValueError("the proposal references no recorded completion")
            work = works[work_id]
            if work.created_by_run_id not in runs:
                raise ValueError(f"unknown inference pipeline run {work.created_by_run_id}")
            completed[proposal_id] = (
                proposal,
                work,
                completions[work_id],
                runs[work.created_by_run_id],
            )
        return completed

    def read_for_work(self, work_id: UUID) -> TargetProposal | None:
        """Return the one retained proposal composed from a work id, or None when absent."""
        with self._factory() as session:
            rows = session.execute(
                select(InferenceProposal, Course.group_id)
                .join(
                    InferenceModelAttempt,
                    InferenceModelAttempt.id == InferenceProposal.source_attempt_id,
                )
                .join(Course, Course.id == InferenceProposal.target_course_id)
                .where(InferenceModelAttempt.target_work_id == work_id)
            ).all()
            if not rows:
                return None
            if len(rows) > 1:
                raise ValueError("multiple retained proposals for one completed target work")
            proposal, target_group_id = rows[0]
            return self._decode(proposal, target_group_id=target_group_id)

    def read_by_id(self, proposal_id: UUID) -> TargetProposal:
        """Return one retained proposal by its exact id, or fail clearly for an unknown id."""
        if not isinstance(proposal_id, UUID):
            raise ValueError("proposal_id must be a UUID")
        with self._factory() as session:
            row = session.execute(
                select(InferenceProposal, Course.group_id)
                .join(Course, Course.id == InferenceProposal.target_course_id)
                .where(InferenceProposal.id == proposal_id)
            ).one_or_none()
            if row is None:
                raise ValueError(f"unknown inference proposal {proposal_id}")
            proposal, target_group_id = row
            return self._decode(proposal, target_group_id=target_group_id)

    def count_for_targets(self, target_group_ids: Collection[str]) -> int:
        """Count every retained proposal row over all supplied canonical target identities.

        The aggregate deduplicates the requested IDs, rejects a non-string or blank ID, and returns
        0 when none remain. It counts every retained proposal version and source completion through
        one scoped SQL count, applying no current-selection or work-status filter and hydrating no
        proposal row. An unknown ID has no rows.
        """
        requested: set[str] = set()
        for target_group_id in target_group_ids:
            if not isinstance(target_group_id, str) or not target_group_id.strip():
                raise ValueError("target_group_ids must be nonblank strings")
            requested.add(target_group_id)
        if not requested:
            return 0
        with self._factory() as session:
            return int(
                session.scalar(
                    select(func.count())
                    .select_from(InferenceProposal)
                    .join(Course, Course.id == InferenceProposal.target_course_id)
                    .where(Course.group_id.in_(requested))
                )
            )

    @staticmethod
    def _decode(row: InferenceProposal, target_group_id: str) -> TargetProposal:
        """Rebuild one strict proposal DTO and its expression/flags from a persisted row."""
        envelope = row.expression
        expression = (
            None
            if envelope is None or envelope["expression"] is None
            else parse_prerequisite_expression(envelope["expression"])
        )
        option_flags = () if envelope is None else _decode_option_flags(envelope["option_flags"])
        return TargetProposal(
            proposal_id=row.id,
            target_group_id=target_group_id,
            source_attempt_id=row.source_attempt_id,
            proposal_version=row.proposal_version,
            identity_sha256=row.identity_sha256,
            expression=expression,
            equivalence=_decode_equivalence(row.equivalence),
            option_flags=option_flags,
        )
