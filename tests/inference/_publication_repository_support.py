"""Shared real-store builders for the inference publication repository tests.

These helpers seed canonical courses, shared execution/work/completion evidence, and accepted
proposals through the real repositories, then exercise the one inference publication route into the
final inferred-set and equivalence stores.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import func, select

from course_explorer.config import InferenceSelectionSettings, InferenceSettings
from course_explorer.curriculum_repository import CurriculumRepository
from course_explorer.db.models import (
    Course,
    CourseVersion,
    CourseVersionCurriculumPeriod,
    CurriculumPeriod,
    IngestionRun,
    SourceSnapshot,
)
from course_explorer.db.session import session_scope
from course_explorer.enums import (
    InferenceWorkStatus,
    IngestionRunStatus,
    SourceObjectType,
)
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
    InferenceModelAttemptRecord,
    InferencePipelineRunRecord,
    InferencePipelineRunSpec,
    InferenceTargetWorkRecord,
    InferenceTargetWorkRequest,
)
from course_explorer.inference.evidence_repository import InferenceEvidenceRepository
from course_explorer.inference.proposal_repository import InferenceProposalRepository
from course_explorer.inference.proposals import (
    EquivalenceProposalCandidate,
    TargetProposal,
    official_snapshot_sha256,
    proposal_identity_sha256,
)
from course_explorer.inference.publication import CurrentInferenceCohort
from course_explorer.prerequisite.domain import (
    CourseRequirement,
    InferenceEvidenceKind,
    InferenceEvidenceReference,
    InferenceNodeMetadata,
    InferredPrerequisiteCategory,
    PrerequisiteExpression,
    PrerequisiteOrigin,
)
from tests.inference._fixture_support import fixture_sha256 as _hash
from tests.support import settings_factory

STARTED_AT = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)
YEAR = 2026
WINDOW = 3
_MODEL_IDENTITY = "Qwen/Qwen3.8-27B-FP8@rev;artifact=x@rev/f.gguf;quant=IQ3_MIX;sha256=" + "9" * 64
_RUNTIME_IDENTITY = "llama.cpp@rev;alias=a;context=131072"


def settings_pair() -> tuple[InferenceSettings, InferenceSelectionSettings]:
    """Build one otherwise valid settings pair without reading the environment."""
    return settings_factory(InferenceSettings), settings_factory(InferenceSelectionSettings)


def _seed_course(factory: object, group_id: str, code: str, *, is_active: bool = True) -> None:
    """Seed one canonical course with a selected representative version and period."""
    with session_scope(factory) as session:
        run = IngestionRun(
            status=IngestionRunStatus.COMPLETED,
            raw_root_path="data/raw",
            manifest_path="data/raw/manifest.json",
        )
        session.add(run)
        session.flush()
        period_id = f"period-{YEAR}"
        if session.get(CurriculumPeriod, period_id) is None:
            session.add(CurriculumPeriod(id=period_id, academic_year_start=YEAR))
            session.flush()
        course = Course(
            group_id=group_id,
            is_active=is_active,
            activity_as_of_academic_year_start=YEAR,
            activity_window_years=WINDOW,
        )
        session.add(course)
        session.flush()
        snapshot = SourceSnapshot(
            ingestion_run_id=run.id,
            object_type=SourceObjectType.COURSE_UNIT,
            source_object_id=code,
            response_path=f"courses/{code}",
            response_item_index=0,
            source_hash=_hash(f"source-{group_id}"),
        )
        session.add(snapshot)
        session.flush()
        version = CourseVersion(
            course_id=course.id,
            sisu_course_unit_id=f"sisu-{group_id}",
            code=code,
            name_fi=f"Nimi {code}",
            name_en=f"Name {code}",
            credits_min=5,
            credits_max=None,
            official_url=f"https://example.test/courses/{code}",
            document_state="ACTIVE",
            source_snapshot_id=snapshot.id,
            source_modification_ordinal=0,
        )
        session.add(version)
        session.flush()
        session.add(
            CourseVersionCurriculumPeriod(
                course_version_id=version.id, curriculum_period_id=period_id
            )
        )


def _run_spec(*, model_identity: str = _MODEL_IDENTITY) -> InferencePipelineRunSpec:
    """Build one v9/v2/v1 shared execution spec with the supplied coarse model identity."""
    return InferencePipelineRunSpec(
        model_identity=model_identity,
        runtime_identity=_RUNTIME_IDENTITY,
        prompt_version="v9",
        schema_version="v2",
        pipeline_version="v1",
        configuration={"route": "local"},
    )


def _completed_work(
    evidence: InferenceEvidenceRepository,
    target_group_id: str,
    *,
    candidate_group_ids: tuple[str, ...],
    model_identity: str = _MODEL_IDENTITY,
    input_seed: str | None = None,
) -> tuple[InferenceTargetWorkRecord, InferenceModelAttemptRecord, InferencePipelineRunRecord]:
    """Create one completed validated work through the sole evidence writer and read the run back."""
    spec = _run_spec(model_identity=model_identity)
    run = evidence.create_run(spec)
    request = InferenceTargetWorkRequest(
        target_group_id=target_group_id,
        activity_as_of_academic_year_start=YEAR,
        activity_window_years=WINDOW,
    )
    work = evidence.claim_work(
        run.run_id,
        request,
        _hash(input_seed or f"input-{target_group_id}"),
    ).work
    descriptors = RequestCourseDescriptors(
        target=RequestCourseDescriptor(
            group_id=target_group_id,
            course_code=f"{target_group_id}-code",
            representative_source_sha256=_hash(f"source-{target_group_id}"),
        ),
        candidates=tuple(
            RequestCourseDescriptor(
                group_id=group_id,
                course_code=f"{group_id}-code",
                representative_source_sha256=_hash(f"source-{group_id}"),
            )
            for group_id in candidate_group_ids
        ),
    )
    result = InferenceTargetResultV2(
        required=(),
        recommended=(),
        equivalence=(),
        routing=InferenceRoutingMetadata(confidence=Decimal("0.5"), flags=(), suppressed=()),
    )
    facts = InferenceCompletionFacts(
        target_teaching_text_sha256=_hash(f"text-{target_group_id}"),
        candidate_count=len(candidate_group_ids),
    )
    completed = evidence.record_completion(
        run.run_id,
        work.work_id,
        result=result,
        descriptors=descriptors,
        facts=facts,
        finished_at=STARTED_AT,
    )
    assert completed.status is InferenceWorkStatus.COMPLETED
    attempt = evidence.read_completion(completed.work_id)
    assert attempt is not None
    return completed, attempt, evidence.read_run(run.run_id)


def _failed_work(
    evidence: InferenceEvidenceRepository, target_group_id: str
) -> InferenceTargetWorkRecord:
    """Create one failed work through the sole evidence writer."""
    spec = _run_spec()
    run = evidence.create_run(spec)
    request = InferenceTargetWorkRequest(
        target_group_id=target_group_id,
        activity_as_of_academic_year_start=YEAR,
        activity_window_years=WINDOW,
    )
    work = evidence.claim_work(run.run_id, request, _hash(f"failed-input-{target_group_id}")).work
    failed = evidence.fail_work(run.run_id, work.work_id)
    assert failed.status is InferenceWorkStatus.FAILED
    return failed


def _course_requirement(
    group_id: str,
    category: InferredPrerequisiteCategory,
    confidence: str,
    *,
    reference: InferenceEvidenceReference,
) -> CourseRequirement:
    """Build one inferred direct course option bound to its proposal reference."""
    return CourseRequirement(
        type="course",
        origin=PrerequisiteOrigin.INFERRED,
        inferred_category=category,
        course_group_id=group_id,
        inference=InferenceNodeMetadata(
            confidence=Decimal(confidence),
            requirement_ids=("r1",),
            evidence=(reference,),
        ),
    )


def _equivalence(
    members: tuple[str, ...],
    confidence: str,
    *,
    reference: InferenceEvidenceReference,
) -> EquivalenceProposalCandidate:
    """Build one exact equivalence candidate bound to its proposal reference."""
    return EquivalenceProposalCandidate(
        members=tuple(sorted(members)),
        inference=InferenceNodeMetadata(
            confidence=Decimal(confidence),
            requirement_ids=(),
            evidence=(reference,),
        ),
        finding_flags=(),
    )


def _build_proposal(
    factory: object,
    target_group_id: str,
    work: InferenceTargetWorkRecord,
    attempt: InferenceModelAttemptRecord,
    *,
    expression: Callable[[InferenceEvidenceReference], PrerequisiteExpression] | None = None,
    equivalence: Callable[[InferenceEvidenceReference], tuple[EquivalenceProposalCandidate, ...]]
    | None = None,
    proposal_version: str = "v1",
    official_hash: str | None = None,
) -> TargetProposal:
    """Persist one accepted proposal whose supplied factories bind the real proposal reference."""
    target = CurriculumRepository(factory).get_courses((target_group_id,))
    assert len(target) == 1 and target[0].representative is not None
    resolved_hash = official_snapshot_sha256(target[0]) if official_hash is None else official_hash
    identity = proposal_identity_sha256(work, attempt, resolved_hash, proposal_version)
    proposal_id = uuid5(NAMESPACE_URL, identity)
    reference = InferenceEvidenceReference(
        kind=InferenceEvidenceKind.EXPRESSION_PROPOSAL, reference_id=str(proposal_id)
    )
    proposal = TargetProposal(
        proposal_id=proposal_id,
        target_group_id=target_group_id,
        source_attempt_id=attempt.attempt_id,
        proposal_version=proposal_version,
        identity_sha256=identity,
        expression=None if expression is None else expression(reference),
        equivalence=() if equivalence is None else equivalence(reference),
        option_flags=(),
    )
    stored = InferenceProposalRepository(factory).save(proposal)
    assert stored.identity_sha256 == identity
    return stored


def _cohort(ids: dict[str, UUID]) -> CurrentInferenceCohort:
    """Build one sorted eligible cohort over the supplied target/accepted-pointer mapping."""
    return CurrentInferenceCohort(
        eligible_target_group_ids=tuple(sorted(ids)), accepted_proposal_ids=dict(ids)
    )


def _count(factory: object, model: type) -> int:
    """Return the row count of one ORM table."""
    with session_scope(factory) as session:
        return session.scalar(select(func.count()).select_from(model))


def _member_ids(group) -> tuple[str, ...]:
    """Return one current group's sorted canonical member IDs."""
    return tuple(member.course_group_id for member in group.members)
