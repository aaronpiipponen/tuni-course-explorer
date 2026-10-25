"""Integration proofs for the incremental inference job's control, guard and recovery behavior.

The real catalogue, candidate repository, selection and completion writer run against the disposable
database. Only settings loading and the local model/rerank HTTP endpoints are stubbed.
"""

from __future__ import annotations

import pytest
from sqlalchemy import Engine

from course_explorer.inference import job as job_module
from course_explorer.inference.failures import InferenceTargetsFailed
from course_explorer.inference.job import InferenceJobProgress
from course_explorer.prerequisite.domain import InferredReadState
from course_explorer.prerequisite.repository import InferredPrerequisiteRepository
from tests.inference._job_support import (
    _generation_payloads,
    _latest_cycle_id,
    prepare_job_case,
    run_job,
)
from tests.inference._scheduling_support import attempt_count

pytestmark = [
    pytest.mark.integration,
]


def test_job_control_refusal_preserves_partial_work(
    database: tuple[Engine, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A refused unit yields the unfinished cycle with partial multiview work and no publication."""
    _, factory = database
    repository, runtime, _boundary = prepare_job_case(factory, monkeypatch, ("job-t1", "job-t2"))

    calls = {"count": 0}

    def refuse_after_first() -> bool:
        calls["count"] += 1
        return calls["count"] <= 1

    yielded = run_job(factory, runtime, before_unit=refuse_after_first)
    assert yielded.stage == "multiview"
    states = {
        state.target_group_id: state for state in repository.list_target_states(yielded.cycle_id)
    }
    assert sum(1 for state in states.values() if state.multiview_state == "completed") == 1
    assert not all(marker.processed for marker in repository.read_processing())


def test_oversize_target_fails_without_generation_or_false_coverage(
    database: tuple[Engine, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A packet fitting neither base key fails while the fitting survivor publishes."""
    _, factory = database
    repository, runtime, boundary = prepare_job_case(factory, monkeypatch, ("job-t1", "job-t2"))
    # Only job-t1's rendered packet is oversized, and job-t2 fits the first ordered local key.
    boundary.tokenize_tokens_for = lambda request: 200000 if b"job-t1" in request.content else 1000

    with pytest.raises(InferenceTargetsFailed):
        run_job(factory, runtime, before_unit=lambda: True)

    cycle_id = _latest_cycle_id(factory)
    failed = repository.read_target(cycle_id, "job-t1")
    assert failed.inference_state == "failed"
    # The failed target keeps its retained shortlist and planned key so the next entry retries it.
    assert failed.target_input is not None
    assert failed.generation_work_key_sha256 is None
    assert repository.read_target(cycle_id, "job-t2").inference_state == "completed"

    # One fit-preparation episode, and no generation request, reservation or work identity.
    history = repository.read_target_failures(cycle_id, unresolved_only=False)
    assert len(history) == 1
    assert history[0].target_group_id == "job-t1"
    assert history[0].stage == "inference_preparation"
    assert history[0].reason == "context_exceeded"
    assert history[0].error_type == "TargetContextError"
    assert history[0].attempt_count == 1
    assert history[0].exhausted is True
    assert _generation_payloads(boundary, "job-t1") == []
    assert attempt_count(factory, "job-t1") == 0

    # The survivor is published, the failed target is uncovered, and the cycle is unfinished.
    assert InferredPrerequisiteRepository(factory).read("job-t2").state is InferredReadState.CURRENT
    assert (
        InferredPrerequisiteRepository(factory).read("job-t1").state
        is InferredReadState.UNAVAILABLE
    )
    coverage = repository.read_coverage()
    assert coverage.retained_complete_targets == 1
    assert coverage.published_targets == 1
    assert coverage.uncovered_targets == 1
    assert repository.read_cycle(cycle_id).stage == "publication"


def test_multiview_exhaustion_is_durable_and_retries_on_ordinary_entry(
    database: tuple[Engine, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A pool deeper than the measurable universe exhausts and retries on ordinary entry."""
    _, factory = database
    repository, runtime, _boundary = prepare_job_case(factory, monkeypatch, ("job-t1", "job-t2"))
    base_settings = job_module.load_inference_settings()
    monkeypatch.setattr(
        job_module,
        "load_inference_settings",
        lambda: base_settings.model_copy(
            update={"inference_max_attempts": 3, "inference_retry_backoff_seconds": 0.0}
        ),
    )
    base = job_module.load_inference_selection_settings()
    monkeypatch.setattr(
        job_module,
        "load_inference_selection_settings",
        lambda: base.model_copy(
            update={"inference_selection_pool_k": 1000, "inference_selection_final_k": 1000}
        ),
    )

    observed: list[InferenceJobProgress] = []
    with pytest.raises(InferenceTargetsFailed):
        run_job(factory, runtime, before_unit=lambda: True, on_checkpoint=observed.append)

    cycle_id = _latest_cycle_id(factory)
    cycle = repository.read_cycle(cycle_id)
    assert cycle.stage == "publication"
    for group_id in ("job-t1", "job-t2"):
        record = repository.read_target(cycle_id, group_id)
        assert record.multiview_state == "failed"
        assert record.inference_state == "pending"
    failures = repository.read_target_failures(cycle_id)
    assert {failure.target_group_id for failure in failures} == {"job-t1", "job-t2"}
    assert all(failure.stage == "multiview" for failure in failures)
    assert all(failure.reason == "insufficient_candidates" for failure in failures)
    assert all(failure.attempt_count == 3 for failure in failures)
    assert not all(marker.processed for marker in repository.read_processing())

    # Current multiview exhaustion blocks every downstream stage for both targets.
    final = observed[-1]
    assert final.failed_targets == 2
    assert (
        final.multiview_not_remaining,
        final.rerank_not_remaining,
        final.inference_not_remaining,
    ) == (2, 2, 2)

    # Restoring the configured pool depth lets the ordinary next entry complete.
    monkeypatch.setattr(job_module, "load_inference_selection_settings", lambda: base)
    completed = run_job(factory, runtime, before_unit=lambda: True)
    assert completed.stage == "complete"
    # The cycle's failure history holds both exhausted episodes.
    history = repository.read_target_failures(cycle_id, unresolved_only=False)
    assert len(history) == 2
    assert all(failure.exhausted for failure in history)


def test_invalid_current_output_never_completes_and_valid_retry_completes(
    database: tuple[Engine, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A structurally valid but acceptance-invalid answer is never completed. A valid retry is."""
    _, factory = database
    repository, runtime, boundary = prepare_job_case(factory, monkeypatch, ("job-t1", "job-t2"))
    base = job_module.load_inference_settings()
    monkeypatch.setattr(
        job_module,
        "load_inference_settings",
        lambda: base.model_copy(
            update={"inference_max_attempts": 3, "inference_retry_backoff_seconds": 0.0}
        ),
    )

    # The first twelve job-t1 completions return a multi-set (invalid) result, then the boundary
    # returns the default valid empty result. No invalid answer may be recorded as completed.
    invalid = (
        '{"required":[{"requirement_id":"r1","options":[{"course_codes":["JOBC.00"],'
        '"evidence":"e","confidence":0.5,"finding_flags":[]}]},'
        '{"requirement_id":"r2","options":[{"course_codes":["JOBC.01"],"evidence":"e",'
        '"confidence":0.5,"finding_flags":[]}]}],"recommended":[],"equivalence":[],'
        '"routing":{"confidence":0.5,"flags":[],"suppressed":[]}}'
    )
    invalid_seen = {"count": 0}

    def content_for(index: int, request) -> str:
        if b"job-t1" in request.content and invalid_seen["count"] < 11:
            invalid_seen["count"] += 1
            return invalid
        return boundary.content

    boundary.content_for = content_for

    completed = run_job(factory, runtime, before_unit=lambda: True)
    assert completed.stage == "complete"
    for group_id in ("job-t1", "job-t2"):
        assert repository.read_target(completed.cycle_id, group_id).inference_state == "completed"

    # Each failed attempt records one safe nonexhausted episode, and the cycle's failure history
    # holds all of them.
    history = repository.read_target_failures(completed.cycle_id, unresolved_only=False)
    job_one = [failure for failure in history if failure.target_group_id == "job-t1"]
    assert len(job_one) == 11
    assert all(failure.attempt_count == 1 for failure in job_one)
    assert all(failure.reason == "multiple_requirement_sets" for failure in job_one)
    assert all(failure.exhausted is False for failure in job_one)
    assert repository.read_target_failures(completed.cycle_id) == ()

    # The first local attempt is greedy at the base seed. Every retry samples at the configured
    # retry temperature with an increasing deterministic seed (beyond the local cap and ten).
    payloads = _generation_payloads(boundary, "job-t1")
    assert len(payloads) == 12
    assert payloads[0]["temperature"] == 0.0
    assert payloads[0]["seed"] == 0
    assert all(payload["temperature"] == 0.3 for payload in payloads[1:])
    assert [payload["seed"] for payload in payloads[1:]] == list(range(1, 12))
    assert attempt_count(factory, "job-t1") == 12


def test_generation_checkpoint_yield_resumes_same_calculation(
    database: tuple[Engine, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A committed failed-attempt checkpoint yields the same calculation, resumed at the next seed."""
    _, factory = database
    repository, runtime, boundary = prepare_job_case(factory, monkeypatch, ("job-t1", "job-t2"))
    base = job_module.load_inference_settings()
    monkeypatch.setattr(
        job_module,
        "load_inference_settings",
        lambda: base.model_copy(
            update={"inference_max_attempts": 3, "inference_retry_backoff_seconds": 0.0}
        ),
    )

    invalid = (
        '{"required":[{"requirement_id":"r1","options":[{"course_codes":["JOBC.00"],'
        '"evidence":"e","confidence":0.5,"finding_flags":[]}]},'
        '{"requirement_id":"r2","options":[{"course_codes":["JOBC.01"],"evidence":"e",'
        '"confidence":0.5,"finding_flags":[]}]}],"recommended":[],"equivalence":[],'
        '"routing":{"confidence":0.5,"flags":[],"suppressed":[]}}'
    )
    invalid_seen = {"count": 0}

    def content_for(index: int, request) -> str:
        if b"job-t2" in request.content and invalid_seen["count"] < 1:
            invalid_seen["count"] += 1
            return invalid
        return boundary.content

    boundary.content_for = content_for

    # The checkpoint callback verifies the committed safe episode through the real repository, then
    # withdraws request admission so the writer yields after the first committed failure.
    admitted = {"value": True}
    observed: list[InferenceJobProgress] = []

    def on_generation_attempt_checkpoint() -> None:
        cycle_id = _latest_cycle_id(factory)
        failures = repository.read_target_failures(cycle_id, unresolved_only=False)
        assert any(
            failure.target_group_id == "job-t2" and failure.reason == "multiple_requirement_sets"
            for failure in failures
        )
        admitted["value"] = False

    yielded = run_job(
        factory,
        runtime,
        before_unit=lambda: True,
        before_request=lambda: admitted["value"],
        on_checkpoint=observed.append,
        on_generation_attempt_checkpoint=on_generation_attempt_checkpoint,
    )
    assert yielded.stage == "inference"
    cycle_id = yielded.cycle_id
    assert repository.read_target(cycle_id, "job-t1").inference_state == "completed"
    assert repository.read_target(cycle_id, "job-t2").inference_state == "failed"
    job_two = [
        failure
        for failure in repository.read_target_failures(cycle_id, unresolved_only=False)
        if failure.target_group_id == "job-t2"
    ]
    assert len(job_two) == 1
    assert job_two[0].attempt_count == 1
    assert job_two[0].exhausted is False
    assert attempt_count(factory, "job-t2") == 1

    # The next entry resumes the same cycle: job-t2 accepts at the next seed and retry temperature, with
    # no survivor/upstream rerun and no extra episode.
    admitted["value"] = True
    survivor_payloads_before = len(_generation_payloads(boundary, "job-t1"))
    completed = run_job(
        factory,
        runtime,
        before_unit=lambda: True,
        before_request=lambda: admitted["value"],
        on_checkpoint=lambda progress: None,
    )
    assert completed.stage == "complete"
    assert completed.cycle_id == cycle_id
    assert repository.read_target(cycle_id, "job-t2").inference_state == "completed"
    assert len(_generation_payloads(boundary, "job-t1")) == survivor_payloads_before
    assert len(repository.read_target_failures(cycle_id, unresolved_only=False)) == 1
    assert attempt_count(factory, "job-t2") == 2
    job_two_payloads = _generation_payloads(boundary, "job-t2")
    assert len(job_two_payloads) == 2
    assert job_two_payloads[0]["temperature"] == 0.0
    assert job_two_payloads[0]["seed"] == 0
    assert job_two_payloads[1]["temperature"] == 0.3
    assert job_two_payloads[1]["seed"] == 1


@pytest.mark.parametrize("choice", ["done", "failed"])
@pytest.mark.parametrize("variant", ["retained_shortlist", "consumed_selection"])
def test_operator_disposition_clear_resumes_automatic_processing(
    database: tuple[Engine, object],
    monkeypatch: pytest.MonkeyPatch,
    variant: str,
    choice: str,
) -> None:
    """An explicit decision sends no generation, and clearing resumes only the affected target."""
    _, factory = database
    repository, runtime, boundary = prepare_job_case(factory, monkeypatch, ("job-t1", "job-t2"))

    if variant == "consumed_selection":
        # Finish a genuine cycle, then run the next matching multiview-all cycle whose processed
        # targets skip rerank and inference and consume both selection payloads.
        genuine = run_job(factory, runtime, before_unit=lambda: True)
        assert genuine.stage == "complete"
        skip = run_job(
            factory,
            runtime,
            before_unit=lambda: (
                repository.read_cycle(_latest_cycle_id(factory)).stage != "publication"
            ),
        )
        assert skip.cycle_id != genuine.cycle_id
        assert skip.stage == "publication"
        cycle_id = skip.cycle_id
        consumed = repository.read_target(cycle_id, "job-t1")
        assert (consumed.rerank_state, consumed.inference_state) == ("skipped", "skipped")
        assert consumed.pool_input is None and consumed.target_input is None
    else:
        # Yield after the real rerank so both targets keep a genuine retained shortlist.
        yielded = run_job(
            factory,
            runtime,
            before_unit=lambda: (
                repository.read_cycle(_latest_cycle_id(factory)).stage != "inference"
            ),
        )
        assert yielded.stage == "inference"
        cycle_id = yielded.cycle_id
        retained = repository.read_target(cycle_id, "job-t1")
        assert retained.rerank_state == "completed"
        assert retained.inference_state == "pending"
        assert retained.target_input is not None

    requests_before = len(_generation_payloads(boundary, "job-t1"))
    attempts_before = attempt_count(factory, "job-t1")

    # The explicit decision is set through the real repository owner.
    assert repository.set_target_disposition("job-t1", choice).disposition == choice

    # A disposed invocation honours the decision: zero requests, reservations or episodes for it,
    # while the survivor is published usefully and a done cycle completes without output.
    observed: list[InferenceJobProgress] = []
    if choice == "failed":
        with pytest.raises(InferenceTargetsFailed):
            run_job(factory, runtime, before_unit=lambda: True, on_checkpoint=observed.append)
    else:
        disposed = run_job(
            factory, runtime, before_unit=lambda: True, on_checkpoint=observed.append
        )
        assert disposed.stage == "complete"
    assert len(_generation_payloads(boundary, "job-t1")) == requests_before
    assert attempt_count(factory, "job-t1") == attempts_before
    assert repository.read_target_failures(cycle_id, unresolved_only=False) == ()
    assert repository.read_target_failures(cycle_id) == ()
    if choice == "failed":
        # Zero inference remaining for the decided target holds on every reentry too.
        repeated: list[InferenceJobProgress] = []
        with pytest.raises(InferenceTargetsFailed):
            run_job(factory, runtime, before_unit=lambda: True, on_checkpoint=repeated.append)
        assert len(_generation_payloads(boundary, "job-t1")) == requests_before
        assert repeated[-1].inference_not_remaining >= 1
        if variant == "consumed_selection":
            # A predecessor result is available under an explicit terminal failure.
            assert (
                InferredPrerequisiteRepository(factory).read("job-t1").state
                is InferredReadState.CURRENT
            )
    else:
        # A done target completes with no public inferred output, never a fabricated empty model result.
        assert (
            InferredPrerequisiteRepository(factory).read("job-t1").state
            is InferredReadState.UNAVAILABLE
        )

    # Clearing returns only this target to automatic eligibility.
    survivor_requests = len(_generation_payloads(boundary, "job-t2"))
    cleared = repository.set_target_disposition("job-t1", None)
    assert cleared.disposition is None
    assert cleared.processed is False
    cleared_row = repository.read_target(cycle_id, "job-t1")
    assert cleared_row.inference_state == "pending"
    if variant == "retained_shortlist":
        # The retained shortlist keeps the completed upstream stages reusable.
        assert cleared_row.rerank_state == "completed"
        assert cleared_row.target_input is not None
    else:
        # Consumed payloads cannot support inference: only this target's multiview/rerank reopen.
        assert (cleared_row.multiview_state, cleared_row.rerank_state) == ("pending", "pending")

    reentered = run_job(factory, runtime, before_unit=lambda: True)
    assert reentered.stage == "complete"
    assert repository.read_target(reentered.cycle_id, "job-t1").inference_state == "completed"
    # Only the affected target was rebuilt. The survivor sent no further request.
    assert len(_generation_payloads(boundary, "job-t2")) == survivor_requests
    if variant == "retained_shortlist":
        # The reused retained shortlist issues exactly one real generation for this target.
        assert len(_generation_payloads(boundary, "job-t1")) == requests_before + 1
        assert attempt_count(factory, "job-t1") == attempts_before + 1
    else:
        # The rebuilt selection matches the genuine completed work, so it is reused with no further
        # request and no consumed reservation.
        assert len(_generation_payloads(boundary, "job-t1")) == requests_before
        assert attempt_count(factory, "job-t1") == attempts_before
