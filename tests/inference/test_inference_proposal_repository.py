"""Opt-in PostgreSQL repository tests for immutable inference-owned accepted proposals."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import NAMESPACE_URL, UUID, uuid5

import pytest
from sqlalchemy import Engine, func, select

from course_explorer.db.models import (
    InferenceProposal,
)
from course_explorer.db.session import session_scope
from course_explorer.inference.context import (
    RequestCourseDescriptor,
    RequestCourseDescriptors,
)
from course_explorer.inference.domain import (
    InferenceRoutingMetadata,
    InferenceTargetResultV2,
)
from course_explorer.inference.evidence import (
    InferenceCompletionFacts,
    InferenceCompletionPayload,
    InferenceModelAttemptRecord,
    InferencePipelineRunSpec,
    InferenceTargetWorkRecord,
    InferenceTargetWorkRequest,
)
from course_explorer.inference.evidence_repository import InferenceEvidenceRepository
from course_explorer.inference.proposal_repository import InferenceProposalRepository
from course_explorer.inference.proposals import (
    EquivalenceProposalCandidate,
    TargetProposal,
    proposal_identity_sha256,
)
from course_explorer.prerequisite.domain import (
    CourseRequirement,
    InferenceEvidenceKind,
    InferenceEvidenceReference,
    InferenceNodeMetadata,
    InferredPrerequisiteCategory,
    PrerequisiteOrigin,
)
from tests.inference._fixture_support import final_store_counts
from tests.prerequisite.conftest import PrerequisiteCatalogueSeed

pytestmark = [
    pytest.mark.integration,
]

STARTED_AT = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)


def run_spec() -> InferencePipelineRunSpec:
    """Derive one shared execution spec for the proposal boundary tests."""
    return InferencePipelineRunSpec(
        model_identity="Qwen/Qwen3.8-27B-FP8@rev;artifact=x@rev/f.gguf;quant=IQ3_MIX;sha256="
        + "9" * 64,
        runtime_identity="llama.cpp@rev;alias=a;context=131072",
        prompt_version="v9",
        prompt_content_sha256="1" * 64,
        schema_version="v2",
        schema_sha256="2" * 64,
        pipeline_version="v1",
        configuration={"route": "local"},
    )


def work_request(
    seed: PrerequisiteCatalogueSeed,
    *,
    input_sha256: str = "a" * 64,
) -> InferenceTargetWorkRequest:
    """Build one target-work request bound to the seeded target activity context."""
    return InferenceTargetWorkRequest(
        target_group_id=seed.active_target_group_id,
        activity_as_of_academic_year_start=seed.activity_as_of_academic_year_start,
        activity_window_years=seed.activity_window_years,
        input_sha256=input_sha256,
    )


def _empty_result() -> InferenceTargetResultV2:
    return InferenceTargetResultV2(
        required=(),
        recommended=(),
        equivalence=(),
        routing=InferenceRoutingMetadata(confidence=0.5, flags=(), suppressed=()),
    )


def _descriptors(target_group_id: str) -> RequestCourseDescriptors:
    return RequestCourseDescriptors(
        target=RequestCourseDescriptor(
            group_id=target_group_id,
            course_code="TARGET.1",
            representative_source_sha256="a" * 64,
        ),
        candidates=(),
    )


def _facts() -> InferenceCompletionFacts:
    return InferenceCompletionFacts(target_teaching_text_sha256="b" * 64, candidate_count=0)


def proposal(
    work: InferenceTargetWorkRecord,
    attempt: InferenceModelAttemptRecord,
    official_snapshot_sha256: str,
    proposal_version: str,
    seed: PrerequisiteCatalogueSeed,
    *,
    expression: bool = True,
) -> TargetProposal:
    """Build one otherwise valid proposal directly for repository boundary tests."""
    identity = proposal_identity_sha256(work, attempt, official_snapshot_sha256, proposal_version)
    proposal_id = uuid5(NAMESPACE_URL, identity)
    reference = InferenceEvidenceReference(
        kind=InferenceEvidenceKind.EXPRESSION_PROPOSAL, reference_id=str(proposal_id)
    )
    expression_value = (
        CourseRequirement(
            type="course",
            origin=PrerequisiteOrigin.INFERRED,
            inferred_category=InferredPrerequisiteCategory.REQUIRED,
            course_group_id=seed.active_source_group_id,
            inference=InferenceNodeMetadata(
                confidence=Decimal("0.9"),
                requirement_ids=("required_1",),
                evidence=(reference,),
            ),
        )
        if expression
        else None
    )
    members = tuple(sorted((seed.active_source_group_id, seed.active_target_group_id)))
    return TargetProposal(
        proposal_id=proposal_id,
        target_group_id=work.request.target_group_id,
        source_attempt_id=attempt.attempt_id,
        proposal_version=proposal_version,
        identity_sha256=identity,
        expression=expression_value,
        equivalence=(
            EquivalenceProposalCandidate(
                members=members,
                inference=InferenceNodeMetadata(
                    confidence=Decimal("0.8"),
                    requirement_ids=(),
                    evidence=(reference,),
                ),
                finding_flags=(),
            ),
        ),
        option_flags=(),
    )


def completed_work(
    evidence: InferenceEvidenceRepository, seed: PrerequisiteCatalogueSeed
) -> tuple[InferenceTargetWorkRecord, InferenceModelAttemptRecord]:
    """Create one completed completion through the sole evidence writer."""
    run = evidence.create_run(run_spec())
    created = evidence.claim_work(run.run_id, work_request(seed))
    completed = evidence.record_completion(
        run.run_id,
        created.work.work_id,
        result=_empty_result(),
        descriptors=_descriptors(seed.active_target_group_id),
        facts=_facts(),
        finished_at=STARTED_AT,
    )
    assert completed.status.value == "completed"
    completion = evidence.read_completion(completed.work_id)
    assert completion is not None
    return completed, completion


def test_proposal_persists_once_and_rebuilds_only_for_changed_official_or_policy_identity(
    database: tuple[Engine, object], prerequisite_catalogue: PrerequisiteCatalogueSeed
) -> None:
    """An identical identity is reused. Changed official/version identity appends a distinct row."""
    _, factory = database
    seed = prerequisite_catalogue
    evidence = InferenceEvidenceRepository(factory)
    repository = InferenceProposalRepository(factory)
    work, attempt = completed_work(evidence, seed)

    read_work = evidence.read_work_by_id(work.work_id)
    assert read_work == work

    first = repository.save(proposal(work, attempt, "a" * 64, "v1", seed))
    again = repository.save(proposal(work, attempt, "a" * 64, "v1", seed))
    assert again.proposal_id == first.proposal_id
    assert again.expression == first.expression
    with session_scope(factory) as session:
        assert session.scalar(select(func.count()).select_from(InferenceProposal)) == 1

    changed_official = repository.save(proposal(work, attempt, "b" * 64, "v1", seed))
    changed_version = repository.save(proposal(work, attempt, "a" * 64, "v2", seed))
    assert len({first.proposal_id, changed_official.proposal_id, changed_version.proposal_id}) == 3
    with session_scope(factory) as session:
        assert session.scalar(select(func.count()).select_from(InferenceProposal)) == 3

    assert repository.count_for_targets((seed.active_target_group_id,)) == 3
    assert repository.count_for_targets(()) == 0

    retained_first = repository.read_by_id(first.proposal_id)
    assert retained_first.expression is not None
    assert retained_first.equivalence[0].members == tuple(
        sorted((seed.active_source_group_id, seed.active_target_group_id))
    )

    by_id = repository.read_by_id(changed_official.proposal_id)
    assert by_id == changed_official
    with pytest.raises(ValueError):
        repository.read_by_id(UUID(int=0))

    # A conflicting payload under an identity is rejected, not overwritten or appended.
    with pytest.raises(ValueError):
        repository.save(proposal(work, attempt, "a" * 64, "v1", seed, expression=False))
    with session_scope(factory) as session:
        assert session.scalar(select(func.count()).select_from(InferenceProposal)) == 3

    assert final_store_counts(factory) == (0, 0)
    assert repository.count_for_targets(("missing-target",)) == 0
    with pytest.raises(ValueError):
        evidence.read_work_by_id(UUID(int=0))


def test_proposal_rejects_failed_work_and_preserves_evidence(
    database: tuple[Engine, object],
    prerequisite_catalogue: PrerequisiteCatalogueSeed,
    set_prerequisite_course_activity,
) -> None:
    """Failed or stale input cannot be stored and completions stay untouched."""
    _, factory = database
    seed = prerequisite_catalogue
    evidence = InferenceEvidenceRepository(factory)
    repository = InferenceProposalRepository(factory)
    run = evidence.create_run(run_spec())

    failed_work = evidence.claim_work(run.run_id, work_request(seed, input_sha256="f" * 64))
    failed = evidence.fail_work(run.run_id, failed_work.work.work_id)
    placeholder = InferenceModelAttemptRecord(
        attempt_id=UUID(int=999),
        target_work_id=failed.work_id,
        payload=InferenceCompletionPayload(facts=_facts(), descriptors=None, result=None),
        finished_at=STARTED_AT,
    )
    with pytest.raises(ValueError):
        repository.save(proposal(failed, placeholder, "c" * 64, "v1", seed))

    work, attempt = completed_work(evidence, seed)
    repository.save(proposal(work, attempt, "d" * 64, "v1", seed))
    with session_scope(factory) as session:
        assert session.scalar(select(func.count()).select_from(InferenceProposal)) == 1

    set_prerequisite_course_activity(seed.active_target_group_id, True, 2027, 3)
    with pytest.raises(ValueError):
        repository.save(proposal(work, attempt, "e" * 64, "v1", seed))

    completion = evidence.read_completion(work.work_id)
    assert completion is not None
    with session_scope(factory) as session:
        assert session.scalar(select(func.count()).select_from(InferenceProposal)) == 1
    assert final_store_counts(factory) == (0, 0)
