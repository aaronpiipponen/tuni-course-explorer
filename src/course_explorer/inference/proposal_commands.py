"""Bounded offline-only composition of one accepted proposal from a completed work id.

One work id composes the current catalogue, the completion's compact request descriptors, and the
already-completed uncomposed result into exactly one immutable, versioned inference-owned proposal
through the pure composer and the proposal repository. It reads only the target and the candidate
identities the stored result actually names, so it never reruns selection, enumerates the catalogue,
or calls a provider, reranker, external model route, or GPU worker. This is one-shot composition and
inspection.

The reusable :func:`compose_proposal_from_work` opens no database context of its own so the
incremental inference job can compose through the same one composition path inside its own session
factory.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session, sessionmaker

from course_explorer.config import InferenceSettings
from course_explorer.curriculum_repository import CurriculumRepository
from course_explorer.inference.evidence_repository import InferenceEvidenceRepository
from course_explorer.inference.proposal_repository import InferenceProposalRepository
from course_explorer.inference.proposals import (
    TargetProposal,
    compose_target_proposal,
    named_candidate_group_ids,
)


def compose_proposal_from_work(
    factory: sessionmaker[Session], work_id: UUID, *, settings: InferenceSettings
) -> TargetProposal:
    """Compose and store exactly one accepted proposal for one completed validated work id.

    An already-saved proposal for the work is returned as-is. Otherwise the completion's
    descriptors are read once for the scoped target/candidate identities. The current catalogue is
    read only for the target and the candidate group IDs the result actually names. Every identity
    check and the direct-official dedup live in the pure composer, and the proposal repository owns the one
    append-only write. It creates no engine and calls no provider.
    """
    if not isinstance(work_id, UUID):
        raise ValueError("work_id must be a UUID")
    proposals = InferenceProposalRepository(factory)
    existing = proposals.read_for_work(work_id)
    if existing is not None:
        return existing
    evidence = InferenceEvidenceRepository(factory)
    work = evidence.read_work_by_id(work_id)
    completion = evidence.read_completion(work_id)
    if completion is None:
        raise ValueError(f"target work {work_id} has no retained completion")
    descriptors = completion.payload.descriptors
    result = completion.payload.result
    if descriptors is None or result is None:
        raise ValueError(f"target work {work_id} has no uncomposed validated result")
    referenced_group_ids = named_candidate_group_ids(result, descriptors)

    curriculum = CurriculumRepository(factory)
    target_rows = curriculum.get_courses((descriptors.target.group_id,))
    if len(target_rows) != 1:
        raise ValueError(f"unknown current canonical target {descriptors.target.group_id}")
    referenced_courses = curriculum.get_courses(referenced_group_ids)
    proposal = compose_target_proposal(
        work,
        completion,
        descriptors,
        target_rows[0],
        referenced_courses,
        settings.inference_proposal_version,
    )
    return proposals.save(proposal)
