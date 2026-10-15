"""Opt-in PostgreSQL repository tests for the shared execution, work and completion owner."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy import Engine, func, select

from course_explorer.db.models import (
    Course,
    InferenceModelAttempt,
    InferencePipelineRun,
    InferenceTargetWork,
)
from course_explorer.db.session import session_scope
from course_explorer.enums import InferenceWorkStatus
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
    InferenceExecutionProfile,
    InferenceTargetWorkRequest,
    InferenceWorkClaimAction,
    run_identity_sha256,
    work_key_sha256,
)
from course_explorer.inference.evidence_repository import InferenceEvidenceRepository
from tests.inference._fixture_support import final_store_counts, run_spec
from tests.prerequisite.conftest import PrerequisiteCatalogueSeed

pytestmark = [
    pytest.mark.integration,
]

INPUT_SHA256 = "3" * 64
STARTED_AT = datetime(2026, 9, 17, 12, 0, tzinfo=UTC)


def work_request(
    seed: PrerequisiteCatalogueSeed,
    *,
    target_group_id: str | None = None,
    input_sha256: str = INPUT_SHA256,
    activity_as_of_academic_year_start: int | None = None,
    activity_window_years: int | None = None,
) -> InferenceTargetWorkRequest:
    """Build one target-work request bound to the seeded target activity context."""
    return InferenceTargetWorkRequest(
        target_group_id=seed.active_target_group_id if target_group_id is None else target_group_id,
        activity_as_of_academic_year_start=(
            seed.activity_as_of_academic_year_start
            if activity_as_of_academic_year_start is None
            else activity_as_of_academic_year_start
        ),
        activity_window_years=(
            seed.activity_window_years if activity_window_years is None else activity_window_years
        ),
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


def complete(repository: InferenceEvidenceRepository, run_id: UUID, work_id: UUID):
    """Record one empty completion through the sole writer."""
    return repository.record_completion(
        run_id,
        work_id,
        result=_empty_result(),
        descriptors=_descriptors("x"),
        facts=_facts(),
        finished_at=STARTED_AT,
    )


def test_shared_execution_is_reused_by_coarse_identity(
    database: tuple[Engine, object], prerequisite_catalogue: PrerequisiteCatalogueSeed
) -> None:
    """One shared execution is selected for an identical coarse identity and never duplicated."""
    _, factory = database
    repository = InferenceEvidenceRepository(factory)
    spec = run_spec()

    created = repository.create_run(spec)
    assert created.spec == spec
    assert created.run_identity_sha256 == run_identity_sha256(spec)

    read_back = repository.read_run(created.run_id)
    assert read_back.spec.configuration == spec.configuration
    assert read_back.spec.model_identity == spec.model_identity
    assert read_back.spec.prompt_content_sha256 == spec.prompt_content_sha256
    assert read_back.spec.schema_sha256 == spec.schema_sha256

    # An identical coarse identity reuses the one retained execution row.
    second = repository.create_run(spec)
    assert second.run_id == created.run_id

    # A changed coarse identity (different model/runtime) creates a distinct execution.
    changed = run_spec(
        execution=InferenceExecutionProfile(
            route="local", model_identity="other-model", runtime_identity="other-runtime"
        )
    )
    distinct = repository.create_run(changed)
    assert distinct.run_id != created.run_id

    with pytest.raises(ValueError):
        repository.read_run(UUID(int=0))

    with session_scope(factory) as session:
        assert session.scalar(select(func.count()).select_from(InferencePipelineRun)) == 2
        assert session.scalar(select(func.count()).select_from(Course)) == 4


def test_claim_reuses_completed_matching_work_and_preserves_changed_identity_history(
    database: tuple[Engine, object],
    prerequisite_catalogue: PrerequisiteCatalogueSeed,
    set_prerequisite_course_activity,
) -> None:
    """A completed matching target row is reused. A changed identity keeps the stored evidence."""
    _, factory = database
    repository = InferenceEvidenceRepository(factory)
    seed = prerequisite_catalogue
    first_run = repository.create_run(run_spec())
    second_run = repository.create_run(run_spec())

    request = work_request(seed)
    created = repository.claim_work(first_run.run_id, request)
    assert created.action is InferenceWorkClaimAction.CREATED
    assert created.work.status is InferenceWorkStatus.PENDING
    assert created.work.request == request
    work_key = created.work.work_key_sha256
    assert work_key == work_key_sha256(request, first_run.run_identity_sha256)

    existing = repository.claim_work(second_run.run_id, request)
    assert existing.action is InferenceWorkClaimAction.EXISTING
    assert existing.work.work_id == created.work.work_id

    completed = complete(repository, first_run.run_id, created.work.work_id)
    assert completed.status is InferenceWorkStatus.COMPLETED
    completion = repository.read_completion(created.work.work_id)
    assert completion is not None
    assert completion.payload.facts.candidate_count == 0

    reused = repository.claim_work(second_run.run_id, request)
    assert reused.action is InferenceWorkClaimAction.REUSED
    assert reused.work.work_id == created.work.work_id

    read_back = repository.read_work(seed.active_target_group_id, work_key)
    assert read_back is not None and read_back.status is InferenceWorkStatus.COMPLETED
    assert repository.read_work(seed.active_target_group_id, "f" * 64) is None
    assert repository.read_work("missing-target", work_key) is None

    changed_input = repository.claim_work(
        second_run.run_id, work_request(seed, input_sha256="9" * 64)
    )
    assert changed_input.action is InferenceWorkClaimAction.CREATED
    assert changed_input.work.work_id != created.work.work_id

    set_prerequisite_course_activity(seed.active_target_group_id, True, 2027, 2)
    changed_activity = repository.claim_work(
        second_run.run_id,
        work_request(seed, activity_as_of_academic_year_start=2027, activity_window_years=2),
    )
    assert changed_activity.action is InferenceWorkClaimAction.CREATED
    assert changed_activity.work.work_key_sha256 != work_key

    preserved = repository.read_work(seed.active_target_group_id, work_key)
    assert preserved is not None and preserved.status is InferenceWorkStatus.COMPLETED

    with session_scope(factory) as session:
        assert session.scalar(select(func.count()).select_from(InferenceTargetWork)) == 3
        assert session.scalar(select(func.count()).select_from(InferenceModelAttempt)) == 1


def test_failed_work_is_visible_retryable_and_writes_no_raw_history(
    database: tuple[Engine, object], prerequisite_catalogue: PrerequisiteCatalogueSeed
) -> None:
    """A failed work row is visible, retries explicitly, and writes no raw attempt history."""
    _, factory = database
    repository = InferenceEvidenceRepository(factory)
    seed = prerequisite_catalogue
    run = repository.create_run(run_spec())
    created = repository.claim_work(run.run_id, work_request(seed))
    work_id = created.work.work_id
    assert repository.read_completion(work_id) is None

    failed = repository.fail_work(run.run_id, work_id)
    assert failed.status is InferenceWorkStatus.FAILED
    assert repository.read_completion(work_id) is None

    again = repository.claim_work(run.run_id, work_request(seed))
    assert again.action is InferenceWorkClaimAction.EXISTING
    # A completed-only completion writer refuses a non-pending row.
    with pytest.raises(ValueError):
        complete(repository, run.run_id, work_id)

    retried = repository.retry_work(run.run_id, work_id)
    assert retried.status is InferenceWorkStatus.PENDING
    with pytest.raises(ValueError):
        repository.retry_work(run.run_id, work_id)

    completed = repository.record_completion(
        run.run_id,
        work_id,
        result=_empty_result(),
        descriptors=_descriptors(seed.active_target_group_id),
        facts=_facts(),
        finished_at=STARTED_AT,
    )
    assert completed.status is InferenceWorkStatus.COMPLETED
    completion = repository.read_completion(work_id)
    assert completion is not None
    with pytest.raises(ValueError):
        repository.read_work_by_id(UUID(int=7))

    with session_scope(factory) as session:
        assert session.scalar(select(func.count()).select_from(InferenceModelAttempt)) == 1


def test_claim_rejects_unknown_inactive_and_stale_targets_without_final_store_writes(
    database: tuple[Engine, object],
    prerequisite_catalogue: PrerequisiteCatalogueSeed,
    set_prerequisite_course_activity,
) -> None:
    """Unknown/inactive/stale targets fail loudly and no final product store gains a row."""
    _, factory = database
    repository = InferenceEvidenceRepository(factory)
    seed = prerequisite_catalogue
    run = repository.create_run(run_spec())

    with pytest.raises(ValueError):
        repository.claim_work(run.run_id, work_request(seed, target_group_id="missing-target"))
    with pytest.raises(ValueError):
        repository.claim_work(
            run.run_id, work_request(seed, target_group_id=seed.inactive_target_group_id)
        )
    with pytest.raises(ValueError):
        repository.claim_work(
            run.run_id, work_request(seed, activity_as_of_academic_year_start=2025)
        )
    with pytest.raises(ValueError):
        repository.claim_work(UUID(int=1), work_request(seed))

    created = repository.claim_work(run.run_id, work_request(seed))
    failed = repository.fail_work(run.run_id, created.work.work_id)
    assert failed.status is InferenceWorkStatus.FAILED
    set_prerequisite_course_activity(seed.active_target_group_id, True, 2027, 3)
    with pytest.raises(ValueError):
        repository.claim_work(run.run_id, work_request(seed))
    retried = repository.retry_work(run.run_id, created.work.work_id)
    assert retried.status is InferenceWorkStatus.PENDING

    assert final_store_counts(factory) == (0, 0)
    with session_scope(factory) as session:
        assert session.scalar(select(func.count()).select_from(InferenceTargetWork)) == 1
        assert session.scalar(select(func.count()).select_from(InferenceModelAttempt)) == 0
        assert session.scalar(select(func.count()).select_from(Course)) == 4
