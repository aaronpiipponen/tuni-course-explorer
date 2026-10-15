"""Opt-in PostgreSQL proof that the incremental job resumes real checkpoints to completion.

The real catalogue, candidate repository, selection and evidence writer run against a genuine
disposable database. Settings loading and the local model/rerank HTTP endpoints are stubbed.
"""

from __future__ import annotations

import pytest
from sqlalchemy import Engine, func, select

from course_explorer.db.models import (
    InferenceModelAttempt,
    InferenceProposal,
    InferenceTargetWork,
    InferredPrerequisiteSet,
)
from course_explorer.db.session import session_scope
from course_explorer.inference import job as job_module
from course_explorer.inference.evidence_repository import InferenceEvidenceRepository
from course_explorer.inference.proposal_repository import InferenceProposalRepository
from tests.inference._job_support import prepare_job_case, run_job

pytestmark = [
    pytest.mark.integration,
]


@pytest.mark.parametrize("recovery_window", ["uncomposed", "composed_unaccepted"])
@pytest.mark.parametrize("disposition", [None, "done", "failed"])
def test_job_resume_uses_real_checkpoints_acceptance_and_final_stores(
    database: tuple[Engine, object],
    monkeypatch: pytest.MonkeyPatch,
    recovery_window: str,
    disposition: str | None,
) -> None:
    """A refused unit resumes real checkpoints. An operator override and its clear never lose work."""
    _, factory = database
    repository, runtime, _boundary = prepare_job_case(factory, monkeypatch, ("job-t1", "job-t2"))

    # First run refuses after exactly one unit, yielding the unfinished cycle with one completed pool.
    calls = {"count": 0}

    def refuse_after_first() -> bool:
        calls["count"] += 1
        return calls["count"] <= 1

    first = run_job(factory, runtime, before_unit=refuse_after_first)
    assert first.stage != "complete"
    assert first.stage == "multiview"
    states = {
        state.target_group_id: state for state in repository.list_target_states(first.cycle_id)
    }
    assert sum(1 for state in states.values() if state.multiview_state == "completed") == 1

    # The next run advances through rerank and stops on the real retained inference barrier.
    def stop_at_inference() -> bool:
        return repository.read_cycle(first.cycle_id).stage != "inference"

    second = run_job(factory, runtime, before_unit=stop_at_inference)
    assert second.cycle_id == first.cycle_id
    assert second.stage != "complete"
    assert second.stage == "inference"
    states = {
        state.target_group_id: state for state in repository.list_target_states(second.cycle_id)
    }
    assert all(state.multiview_state == "completed" for state in states.values())
    assert all(state.rerank_state == "completed" for state in states.values())

    # A one-time compose failure after the provider's genuine durable work leaves the planned key
    # checkpointed and only the inference stage failed, never losing the completed model output.
    real_compose = job_module.compose_proposal_from_work
    compose_calls = {"count": 0}

    def flaky_compose(factory_, work_id, *, settings):
        compose_calls["count"] += 1
        if compose_calls["count"] == 1:
            raise RuntimeError("compose failed after durable work")
        return real_compose(factory_, work_id, settings=settings)

    monkeypatch.setattr(job_module, "compose_proposal_from_work", flaky_compose)
    with pytest.raises(RuntimeError):
        run_job(factory, runtime, before_unit=lambda: True)
    with session_scope(factory) as session:
        works = session.scalar(select(func.count()).select_from(InferenceTargetWork))
        attempts = session.scalar(select(func.count()).select_from(InferenceModelAttempt))
    assert works == 1
    assert attempts == 1
    failed = repository.read_target(first.cycle_id, "job-t1")
    assert failed.inference_state == "failed"
    assert failed.error_type == "RuntimeError"
    assert failed.generation_work_key_sha256 is not None
    assert repository.read_cycle(first.cycle_id).stage == "inference"

    # Record the completed generation, then run the ordinary post-publication cleanup
    # before reopen. The planned work's completion (and an already-composed proposal awaiting
    # acceptance) must survive cleanup so the next entry recovers it instead of regenerating.
    base_settings = job_module.load_inference_settings()
    evidence = InferenceEvidenceRepository(factory)
    original_work = evidence.read_work("job-t1", failed.generation_work_key_sha256)
    assert original_work is not None
    original_completion = evidence.read_completion(original_work.work_id)
    assert original_completion is not None
    original_proposal_id = None
    if recovery_window == "composed_unaccepted":
        original_proposal_id = real_compose(
            factory, original_work.work_id, settings=base_settings
        ).proposal_id
    # An explicit operator override and its clear never lose the genuinely completed work: the
    # surviving completion recovers through the saved planned key.
    if disposition is not None:
        assert repository.set_target_disposition("job-t1", disposition).disposition == disposition
    repository.prune_retained_state()
    if disposition is not None:
        cleared = repository.set_target_disposition("job-t1", None)
        assert cleared.disposition is None
        assert cleared.processed is False
    surviving_completion = evidence.read_completion(original_work.work_id)
    assert surviving_completion is not None
    if recovery_window == "uncomposed":
        assert surviving_completion.payload.descriptors is not None
        assert surviving_completion.payload.result is not None
    else:
        assert surviving_completion.payload.descriptors is None
        assert surviving_completion.payload.result is None
        assert original_proposal_id is not None
        assert (
            InferenceProposalRepository(factory).read_by_id(original_proposal_id).proposal_id
            == original_proposal_id
        )

    # Changing only the generation temperature must not force regeneration: the saved planned key
    # recovers the completed work with zero routing or attempt for that target, and only the
    # remaining target routes. A one-time publication failure then retains the publication cycle.
    monkeypatch.setattr(
        job_module,
        "load_inference_settings",
        lambda: base_settings.model_copy(update={"inference_temperature": 1.0}),
    )
    base_run = job_module.run_routed_operational_target
    routed = {"count": 0}

    def counting_run(*args, **kwargs):
        routed["count"] += 1
        return base_run(*args, **kwargs)

    monkeypatch.setattr(job_module, "run_routed_operational_target", counting_run)
    real_publish = job_module.publish_current_cohort
    publish_calls = {"count": 0}

    def flaky_publish(*args, **kwargs):
        publish_calls["count"] += 1
        if publish_calls["count"] == 1:
            raise RuntimeError("publication failed")
        return real_publish(*args, **kwargs)

    monkeypatch.setattr(job_module, "publish_current_cohort", flaky_publish)
    with pytest.raises(RuntimeError):
        run_job(factory, runtime, before_unit=lambda: True)
    assert routed["count"] == 1
    with session_scope(factory) as session:
        assert session.scalar(select(func.count()).select_from(InferenceModelAttempt)) == 2
    assert repository.read_cycle(first.cycle_id).stage == "publication"
    markers = {record.group_id: record for record in repository.read_processing()}
    assert markers["job-t1"].processed is True
    assert markers["job-t2"].processed is True
    if recovery_window == "composed_unaccepted":
        assert repository.read_target(first.cycle_id, "job-t1").proposal_id == original_proposal_id
    assert repository.read_coverage().published_targets == 0

    # Reopening the retained publication stage publishes and finishes with no repeated selection or
    # generation, and only then bulk-marks every catalogue course processed.
    routed_before = routed["count"]
    fifth = run_job(factory, runtime, before_unit=lambda: True)
    assert fifth.cycle_id == first.cycle_id
    assert fifth.stage == "complete"
    assert fifth.stage == "complete"
    assert routed["count"] == routed_before
    markers = {record.group_id: record for record in repository.read_processing()}
    assert all(marker.processed for marker in markers.values())
    with session_scope(factory) as session:
        assert session.scalar(select(func.count()).select_from(InferenceTargetWork)) == 2
        assert session.scalar(select(func.count()).select_from(InferenceModelAttempt)) == 2
        assert session.scalar(select(func.count()).select_from(InferenceProposal)) == 2
        assert session.scalar(select(func.count()).select_from(InferredPrerequisiteSet)) == 2
    coverage = repository.read_coverage()
    assert coverage.retained_complete_targets == 2
    assert coverage.published_targets == 2
    assert coverage.uncovered_targets == 0

    # A next ordinary run begins a fresh multiview-all cycle, but true markers skip rerank and
    # inference, so no further attempt is created and the retained coverage carries through.
    sixth = run_job(factory, runtime, before_unit=lambda: True)
    assert sixth.stage == "complete"
    assert sixth.cycle_id != fifth.cycle_id
    with session_scope(factory) as session:
        assert session.scalar(select(func.count()).select_from(InferenceModelAttempt)) == 2
    coverage = repository.read_coverage()
    assert coverage.retained_complete_targets == 2
    assert coverage.published_targets == 2
