"""Genuine disposable-PostgreSQL fixtures shared by the scheduling repository tests.

These helpers build real database rows through the repositories and the same strict compact
selection DTOs the operating path uses, so the scheduling integration tests exercise the actual store
rather than a fake: seeded canonical courses with selected representatives, the resolved effective
teaching text, one label-free multiview pool and CE-only target input, and one genuine
completed/validated proposal whose recorded request-identity binds that target input.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select

from course_explorer.config import load_inference_settings
from course_explorer.curriculum_repository import CurriculumRepository
from course_explorer.db.models import (
    Course,
    CourseText,
    CourseVersion,
    CourseVersionCurriculumPeriod,
    CurriculumPeriod,
    InferenceCourseProcessing,
    IngestionRun,
    SourceSnapshot,
)
from course_explorer.db.session import session_scope
from course_explorer.enums import (
    IngestionRunStatus,
    SourceObjectType,
)
from course_explorer.inference.context import (
    InferenceCandidatePacket,
    InferenceCourseReference,
    InferenceSelectionReferences,
    InferenceTargetPacket,
    _course_reference,
    _packet_course,
    processing_text_sha256,
    request_descriptors_from_packet,
    selection_references_sha256,
)
from course_explorer.inference.domain import (
    InferenceRoutingMetadata,
    InferenceTargetResultV2,
)
from course_explorer.inference.evidence import (
    InferenceCompletionFacts,
    InferenceExecutionProfile,
    InferenceModelAttemptRecord,
    InferencePipelineRunRecord,
    InferencePipelineRunSpec,
    InferenceRequestEvidence,
    InferenceTargetWorkRecord,
    InferenceTargetWorkRequest,
)
from course_explorer.inference.evidence_repository import InferenceEvidenceRepository
from course_explorer.inference.operational import OperationalPoolInput, OperationalTargetInput
from course_explorer.inference.proposal_commands import compose_proposal_from_work
from course_explorer.inference.proposals import TargetProposal
from course_explorer.inference.scheduling import (
    CourseProcessingRecord,
    ProcessingCycleRecord,
    ProcessingTargetRecord,
)
from course_explorer.inference.scheduling_repository import InferenceSchedulingRepository
from course_explorer.inference.target_pass import (
    render_target_request,
    request_sha256,
    target_input_sha256,
)
from course_explorer.prerequisite.domain import (
    InferredCoverageState,
    InferredProducerKind,
    InferredSetCoverage,
    InferredSetPublication,
)
from course_explorer.prerequisite.repository import InferredPrerequisiteRepository
from course_explorer.teaching_text.repository import DerivedTranslationRepository
from course_explorer.teaching_text.service import TeachingTextService
from tests.inference._fixture_support import fixture_sha256 as digest

YEAR = 2026
WINDOW = 3
STARTED_AT = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)
HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64
HASH_D = "d" * 64
HASH_E = "e" * 64
MODEL_IDENTITY = "Qwen/Qwen3.8-27B-FP8@rev;artifact=x@rev/f.gguf;quant=IQ3_MIX;sha256=" + "9" * 64
RUNTIME_IDENTITY = "llama.cpp@rev;alias=a;context=131072"


def seed_courses(factory: object, specs: list[tuple[str, str, bool]]) -> None:
    """Seed canonical courses with selected representatives and teaching text in one transaction.

    Each spec is ``(group_id, code, is_active)``. Every course gets a distinct source hash and a
    name plus content cell so it is representable and embeddable.
    """
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
        for group_id, code, is_active in specs:
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
                source_hash=digest(f"source-{group_id}"),
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
            session.add(CourseText(course_version_id=version.id, content_fi=f"Sisalto {code}"))
        session.flush()


def read_effective(factory: object):
    """Return the current canonical courses and their resolved effective teaching text."""
    curriculum = CurriculumRepository(factory)
    courses = curriculum.list_courses(active_only=None)
    effective = TeachingTextService(
        curriculum, DerivedTranslationRepository(factory)
    ).build_catalogue(courses=courses)
    return courses, effective


def attempt_count(factory: object, group_id: str) -> int:
    """Read one target's durable lifetime generation-attempt count from its marker."""
    with session_scope(factory) as session:
        value = session.scalar(
            select(InferenceCourseProcessing.generation_attempt_count)
            .join(Course, Course.id == InferenceCourseProcessing.course_id)
            .where(Course.group_id == group_id)
        )
    assert value is not None
    return int(value)


def reconcile(
    factory: object, seed_proposals: dict | None = None
) -> tuple[CourseProcessingRecord, ...]:
    """Reconcile processing markers over the current full catalogue."""
    courses, effective = read_effective(factory)
    repository = InferenceSchedulingRepository(factory)
    return repository.reconcile_courses(
        courses,
        {course.group_id: course for course in effective.courses},
        seed_proposals=seed_proposals or {},
    )


def prepare_generation_cycle(
    factory: object, value: OperationalTargetInput
) -> tuple[InferenceSchedulingRepository, ProcessingCycleRecord]:
    """Bring the current cycle to the inference stage for one target's exact retained input.

    It reconciles markers, begins/resumes the matching cycle, and, for a fresh multiview row,
    checkpoints a synthetic pool and then the completed rerank carrying ``value`` as the retained
    target input before advancing to inference. A cycle already on inference for the same input is
    returned as-is.
    """
    reconcile(factory)
    repository = InferenceSchedulingRepository(factory)
    cycle = repository.begin_cycle(value.packet_sha256, (value.target_group_id,))
    if cycle.stage == "inference":
        return repository, cycle
    pool = OperationalPoolInput(references=value.references, pool_sha256=value.packet_sha256)
    repository.checkpoint(
        _target_record(
            cycle.cycle_id,
            value.target_group_id,
            multiview_state="completed",
            pool_input=pool,
        )
    )
    repository.set_stage(cycle.cycle_id, "rerank")
    repository.checkpoint(
        _target_record(
            cycle.cycle_id,
            value.target_group_id,
            multiview_state="completed",
            rerank_state="completed",
            pool_input=pool,
            target_input=value,
        )
    )
    repository.set_stage(cycle.cycle_id, "inference")
    return repository, repository.read_cycle(cycle.cycle_id)


def _target_record(
    cycle_id,
    target_group_id: str,
    *,
    multiview_state: str = "pending",
    rerank_state: str = "pending",
    inference_state: str = "pending",
    pool_input=None,
    target_input=None,
    generation_work_key_sha256=None,
    proposal_id=None,
    error_type=None,
) -> ProcessingTargetRecord:
    """Build one strict checkpoint DTO with explicit state for a fixture transition."""
    return ProcessingTargetRecord(
        cycle_id=cycle_id,
        target_group_id=target_group_id,
        multiview_state=multiview_state,  # type: ignore[arg-type]
        rerank_state=rerank_state,  # type: ignore[arg-type]
        inference_state=inference_state,  # type: ignore[arg-type]
        pool_input=pool_input,
        target_input=target_input,
        generation_work_key_sha256=generation_work_key_sha256,
        proposal_id=proposal_id,
        error_type=error_type,
    )


def _catalogue_maps(factory: object) -> tuple[dict, dict]:
    courses, effective = read_effective(factory)
    return (
        {course.group_id: course for course in courses},
        {course.group_id: course for course in effective.courses},
    )


def _reference(factory: object, group_id: str) -> InferenceCourseReference:
    courses_by_group, effective_by_group = _catalogue_maps(factory)
    return _course_reference(courses_by_group[group_id], effective_by_group[group_id])


def materialize(factory: object, references: InferenceSelectionReferences) -> InferenceTargetPacket:
    """Materialize compact references into one transient packet from the current catalogue."""
    courses_by_group, effective_by_group = _catalogue_maps(factory)

    def course(reference: InferenceCourseReference):
        return _packet_course(
            courses_by_group[reference.group_id], effective_by_group[reference.group_id]
        )

    return InferenceTargetPacket(
        packet_version="v1",
        target=course(references.target),
        candidates=tuple(
            InferenceCandidatePacket(course=course(reference))
            for reference in references.candidates
        ),
        embedding_configuration_sha256=HASH_B,
    )


def build_pool(
    factory: object,
    target_group_id: str,
    candidate_group_ids: tuple[str, ...],
) -> OperationalPoolInput:
    """Build one real full multiview pool selection over current catalogue identities."""
    references = InferenceSelectionReferences(
        target=_reference(factory, target_group_id),
        candidates=tuple(_reference(factory, group_id) for group_id in candidate_group_ids),
    )
    return OperationalPoolInput(
        references=references,
        pool_sha256=selection_references_sha256(references),
    )


def build_target_input(pool: OperationalPoolInput) -> OperationalTargetInput:
    """Build one CE-only target selection carrying exactly the pool's candidates in reverse order."""
    references = InferenceSelectionReferences(
        target=pool.references.target,
        candidates=tuple(reversed(pool.references.candidates)),
    )
    return OperationalTargetInput(
        references=references,
        packet_sha256=selection_references_sha256(references),
    )


@dataclass(frozen=True)
class CompletedFixture:
    """One genuine completed target result bound to its retained target input."""

    target_input: OperationalTargetInput
    packet: InferenceTargetPacket
    request: InferenceRequestEvidence
    work: InferenceTargetWorkRecord
    attempt: InferenceModelAttemptRecord
    run: InferencePipelineRunRecord
    proposal: TargetProposal


def _execution(*, model_identity: str = MODEL_IDENTITY) -> InferenceExecutionProfile:
    return InferenceExecutionProfile(
        route="local",
        model_identity=model_identity,
        runtime_identity=RUNTIME_IDENTITY,
    )


def complete_target(
    factory: object,
    target_input: OperationalTargetInput,
    pack,
    *,
    model_identity: str = MODEL_IDENTITY,
) -> CompletedFixture:
    """Create one genuine completed/validated proposal whose recorded input binds the target input.

    ``model_identity`` lets a caller build a second, distinct completed result for the same target so
    acceptance conflict/idempotency can be exercised.
    """
    packet = materialize(factory, target_input.references)
    settings = load_inference_settings()
    request = render_target_request(packet, pack, "v2")
    request_digest = request_sha256(request)
    input_sha256 = target_input_sha256(target_input, request_digest)
    evidence = InferenceEvidenceRepository(factory)
    spec = InferencePipelineRunSpec.from_contracts(
        settings, execution=_execution(model_identity=model_identity)
    )
    run = evidence.create_run(spec)
    target = packet.target
    work = evidence.claim_work(
        run.run_id,
        InferenceTargetWorkRequest(
            target_group_id=target_input.target_group_id,
            activity_as_of_academic_year_start=target.activity_as_of_academic_year_start,
            activity_window_years=target.activity_window_years,
        ),
        input_sha256,
    ).work
    result = InferenceTargetResultV2(
        required=(),
        recommended=(),
        equivalence=(),
        routing=InferenceRoutingMetadata(confidence=Decimal("0.5"), flags=(), suppressed=()),
    )
    descriptors = request_descriptors_from_packet(packet)
    facts = InferenceCompletionFacts(
        target_teaching_text_sha256=processing_text_sha256(
            tuple(
                (cell.field.value, cell.language.value, cell.text) for cell in packet.target.texts
            )
        ),
        candidate_count=len(packet.candidates),
    )
    completed = evidence.record_completion(
        run.run_id,
        work.work_id,
        result=result,
        descriptors=descriptors,
        facts=facts,
        finished_at=STARTED_AT,
    )
    run_record = evidence.read_run(run.run_id)
    proposal = compose_proposal_from_work(factory, completed.work_id, settings=settings)
    assert completed.status.value == "completed"
    attempt = evidence.read_completion(completed.work_id)
    assert attempt is not None
    return CompletedFixture(
        target_input=target_input,
        packet=packet,
        request=request,
        work=completed,
        attempt=attempt,
        run=run_record,
        proposal=proposal,
    )


def publish_final_set(
    factory: object,
    target_group_id: str,
    *,
    input_hash: str,
    coverage_state: InferredCoverageState = InferredCoverageState.COMPLETE,
    producer_kind: InferredProducerKind = InferredProducerKind.INFERENCE,
) -> None:
    """Publish one current final inferred set through the repository."""
    InferredPrerequisiteRepository(factory).publish(
        InferredSetPublication(
            target_group_id=target_group_id,
            activity_as_of_academic_year_start=YEAR,
            activity_window_years=WINDOW,
            producer_kind=producer_kind,
            producer_name="test-fixture",
            producer_version="1",
            input_hash=input_hash,
            coverage_state=coverage_state,
            coverage=(
                InferredSetCoverage(
                    eligible_source_count=1,
                    processed_source_count=1,
                    accepted_source_count=0,
                )
                if coverage_state is InferredCoverageState.COMPLETE
                else InferredSetCoverage(
                    eligible_source_count=2,
                    processed_source_count=1,
                    accepted_source_count=0,
                )
            ),
            expression=None,
            generated_at=STARTED_AT,
        )
    )
