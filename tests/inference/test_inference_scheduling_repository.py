"""Opt-in PostgreSQL proofs for the processing-marker, cycle and checkpoint repository.

These tests build genuine rows through the real evidence/proposal repositories and the same strict
packet DTOs the operating path uses, then exercise reconcile/seed, cycle resume, strict checkpoints,
legitimate skips, atomic acceptance and the guarded whole-cycle finish. They run against the
dedicated ``*_test`` database.
"""

from __future__ import annotations

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker

from course_explorer.db.models import (
    Course,
    CourseText,
    CourseVersion,
    InferenceCourseProcessing,
    InferenceModelAttempt,
    InferenceProcessingCycle,
    InferenceProcessingTarget,
    InferenceProposal,
    InferenceTargetFailure,
    InferenceTargetWork,
)
from course_explorer.db.session import session_scope
from course_explorer.inference.prompts import load_prompt_pack
from course_explorer.inference.scheduling import ProcessingTargetRecord
from course_explorer.inference.scheduling_repository import InferenceSchedulingRepository
from course_explorer.prerequisite.domain import (
    InferredCoverageState,
    InferredProducerKind,
)
from tests.inference._scheduling_support import (
    HASH_D,
    HASH_E,
    build_pool,
    build_target_input,
    complete_target,
    publish_final_set,
    reconcile,
    seed_courses,
)

pytestmark = [
    pytest.mark.integration,
]


def _candidate_ids(count: int = 50) -> tuple[str, ...]:
    """Return the deterministic candidate group IDs used by the cycle scenarios."""
    return tuple(f"cand-{index:02d}" for index in range(count))


def _seed_cycle_catalogue(factory: object, target: str = "cyc-target") -> tuple[str, ...]:
    """Seed one active target plus fifty represented active/inactive candidate sources."""
    candidates = _candidate_ids()
    specs = [(target, "CYC.T", True)]
    specs.extend(
        (group_id, f"CYC.{index:02d}", index % 2 == 0) for index, group_id in enumerate(candidates)
    )
    seed_courses(factory, specs)
    return candidates


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
    """Build one strict checkpoint DTO with explicit state."""
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


def _set_marker_processed(factory: object, group_id: str, processed: bool) -> None:
    """Directly set one processing marker flag for a test-only precondition."""
    with session_scope(factory) as session:
        course_id = session.scalar(select(Course.id).where(Course.group_id == group_id))
        assert course_id is not None
        marker = session.scalar(
            select(InferenceCourseProcessing).where(
                InferenceCourseProcessing.course_id == course_id
            )
        )
        assert marker is not None
        marker.processed = processed


def _count(factory: object, model: type) -> int:
    with session_scope(factory) as session:
        return int(session.scalar(select(func.count()).select_from(model)))


def _assert_cycle_lock_timeout(
    engine: Engine,
    factory: object,
    cycle_id,
    call: object,
) -> None:
    """Run one public call under a competing held cycle lock and assert a timeout.

    The holder opens its own ``factory()`` transaction and locks the exact cycle row ``FOR UPDATE``.
    The contender runs on a separate engine connection whose transaction sets a test-only lock
    timeout. The repository's evidence reads and mutable transaction join it as savepoints so the
    local timeout holds. A public checkpoint/acceptance must then raise a PostgreSQL lock timeout
    (SQLSTATE ``55P03``) instead of committing any target/marker change.
    """
    holder = factory()
    holder.begin()
    holder.execute(
        select(InferenceProcessingCycle)
        .where(InferenceProcessingCycle.id == cycle_id)
        .with_for_update()
    )
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            connection.exec_driver_sql("SET LOCAL lock_timeout = '100ms'")
            contender_factory = sessionmaker(
                bind=connection,
                expire_on_commit=False,
                join_transaction_mode="create_savepoint",
            )
            contender = InferenceSchedulingRepository(contender_factory)
            with pytest.raises(DBAPIError) as excinfo:
                call(contender)
            assert excinfo.value.orig.sqlstate == "55P03"
            transaction.rollback()
    finally:
        holder.rollback()
        holder.close()


def _marker_processed(factory: object, group_id: str) -> bool | None:
    """Read one processing marker flag, or ``None`` when the marker is absent."""
    with session_scope(factory) as session:
        return session.scalar(
            select(InferenceCourseProcessing.processed)
            .join(Course, Course.id == InferenceCourseProcessing.course_id)
            .where(Course.group_id == group_id)
        )


def test_text_and_activity_reset_but_calendar_and_generator_do_not(
    database: tuple[Engine, object],
) -> None:
    """Seeds certify true, and only text/activity changes reset a marker."""
    _, factory = database
    pack = load_prompt_pack("v9")
    candidates = _candidate_ids()
    seed_courses(
        factory,
        [
            ("target-ok", "OK.1", True),
            ("src", "SRC.1", True),
            ("inactive-x", "INX.1", False),
            *[
                (group_id, f"CAN.{index:02d}", index % 2 == 0)
                for index, group_id in enumerate(candidates)
            ],
        ],
    )

    fixture_ok = complete_target(
        factory,
        build_target_input(build_pool(factory, "target-ok", candidates)),
        pack,
    )
    publish_final_set(factory, "target-ok", input_hash=fixture_ok.proposal.identity_sha256)
    # A test-owned set and a partial inference set are never seeded.
    publish_final_set(
        factory,
        candidates[0],
        input_hash=HASH_E,
        producer_kind=InferredProducerKind.TEST,
    )
    publish_final_set(
        factory,
        candidates[2],
        input_hash=HASH_E,
        coverage_state=InferredCoverageState.PARTIAL,
    )

    repository = InferenceSchedulingRepository(factory)
    seeds = repository.read_seed_proposals()
    assert seeds == {"target-ok": fixture_ok.proposal.proposal_id}

    records = {record.group_id: record for record in reconcile(factory, seeds)}
    # A saved written-text descriptor certifies true with its pointer.
    assert records["target-ok"].processed is True
    assert records["target-ok"].accepted_proposal_id == fixture_ok.proposal.proposal_id
    assert records["inactive-x"].processed is False
    assert records["inactive-x"].accepted_proposal_id is None

    # A changed effective teaching text resets false while the pointer is retained.
    with session_scope(factory) as session:
        text = session.scalar(
            select(CourseText)
            .join(CourseVersion, CourseVersion.id == CourseText.course_version_id)
            .join(Course, Course.id == CourseVersion.course_id)
            .where(Course.group_id == "target-ok")
        )
        assert text is not None
        text.content_fi = "Muuttunut sisalto"
    after_text = {record.group_id: record for record in reconcile(factory, seeds)}
    assert after_text["target-ok"].processed is False
    assert after_text["target-ok"].accepted_proposal_id == fixture_ok.proposal.proposal_id

    # A calendar rollover or generator change (no teaching-text change) does not reset a marker.
    _set_marker_processed(factory, "inactive-x", True)
    with session_scope(factory) as session:
        course = session.scalar(select(Course).where(Course.group_id == "inactive-x"))
        assert course is not None
        course.activity_as_of_academic_year_start = 2027
    calendar = {record.group_id: record for record in reconcile(factory, seeds)}
    assert calendar["inactive-x"].processed is True

    # An inactive course that becomes active without a completed result resets false once.
    with session_scope(factory) as session:
        course = session.scalar(select(Course).where(Course.group_id == "inactive-x"))
        assert course is not None
        course.is_active = True
    activated = {record.group_id: record for record in reconcile(factory, seeds)}
    assert activated["inactive-x"].processed is False
    assert activated["inactive-x"].accepted_proposal_id is None
    repeated = {record.group_id: record for record in reconcile(factory, seeds)}
    assert repeated["inactive-x"].processed is False


def test_checkpoint_rejects_cross_stage_mutation_without_partial_write(
    database: tuple[Engine, object],
) -> None:
    """Every changed stage is checked independently and no partial write is committed."""
    _, factory = database
    candidates = _seed_cycle_catalogue(factory)
    reconcile(factory)
    repository = InferenceSchedulingRepository(factory)
    pool = build_pool(factory, "cyc-target", candidates)
    target_input = build_target_input(pool)

    cycle = repository.begin_cycle(HASH_D, ("cyc-target",))

    # Completing multiview and rerank together is refused while the cycle is multiview.
    with pytest.raises(ValueError):
        repository.checkpoint(
            _target_record(
                cycle.cycle_id,
                "cyc-target",
                multiview_state="completed",
                rerank_state="completed",
                pool_input=pool,
                target_input=target_input,
            )
        )
    # A multiview completion plus a planned key is refused for the inference stage.
    with pytest.raises(ValueError):
        repository.checkpoint(
            _target_record(
                cycle.cycle_id,
                "cyc-target",
                multiview_state="completed",
                pool_input=pool,
                generation_work_key_sha256=HASH_E,
            )
        )
    saved = repository.read_target(cycle.cycle_id, "cyc-target")
    assert (saved.multiview_state, saved.rerank_state, saved.inference_state) == (
        "pending",
        "pending",
        "pending",
    )
    assert saved.pool_input is None
    assert saved.target_input is None
    assert saved.generation_work_key_sha256 is None

    # Complete multiview normally, then advance to the rerank stage.
    repository.checkpoint(
        _target_record(cycle.cycle_id, "cyc-target", multiview_state="completed", pool_input=pool)
    )
    repository.set_stage(cycle.cycle_id, "rerank")

    # Complete rerank normally, advance inference, and the planned-key checkpoint succeeds.
    repository.checkpoint(
        _target_record(
            cycle.cycle_id,
            "cyc-target",
            multiview_state="completed",
            rerank_state="completed",
            pool_input=pool,
            target_input=target_input,
        )
    )
    repository.set_stage(cycle.cycle_id, "inference")
    planned = repository.read_target(cycle.cycle_id, "cyc-target").model_copy(
        update={"generation_work_key_sha256": HASH_E}
    )
    assert repository.checkpoint(planned).generation_work_key_sha256 == HASH_E


def test_checkpoint_and_acceptance_respect_a_locked_cycle(
    database: tuple[Engine, object],
) -> None:
    """Public checkpoint and acceptance block on a held cycle row lock instead of committing."""
    engine, factory = database
    pack = load_prompt_pack("v9")
    candidates = _seed_cycle_catalogue(factory)
    reconcile(factory)
    repository = InferenceSchedulingRepository(factory)
    pool = build_pool(factory, "cyc-target", candidates)
    target_input = build_target_input(pool)
    fixture = complete_target(factory, target_input, pack)

    cycle = repository.begin_cycle(HASH_D, ("cyc-target",))
    multiview = _target_record(
        cycle.cycle_id, "cyc-target", multiview_state="completed", pool_input=pool
    )

    _assert_cycle_lock_timeout(
        engine, factory, cycle.cycle_id, lambda contender: contender.checkpoint(multiview)
    )
    saved = repository.read_target(cycle.cycle_id, "cyc-target")
    assert (saved.multiview_state, saved.rerank_state, saved.inference_state) == (
        "pending",
        "pending",
        "pending",
    )
    assert saved.pool_input is None

    # After the lock is released the same checkpoint commits normally.
    repository.checkpoint(multiview)
    repository.set_stage(cycle.cycle_id, "rerank")
    repository.checkpoint(
        _target_record(
            cycle.cycle_id,
            "cyc-target",
            multiview_state="completed",
            rerank_state="completed",
            pool_input=pool,
            target_input=target_input,
        )
    )
    repository.set_stage(cycle.cycle_id, "inference")
    planned = repository.read_target(cycle.cycle_id, "cyc-target").model_copy(
        update={"generation_work_key_sha256": fixture.work.work_key_sha256}
    )
    repository.checkpoint(planned)

    _assert_cycle_lock_timeout(
        engine,
        factory,
        cycle.cycle_id,
        lambda contender: contender.accept_target(cycle.cycle_id, "cyc-target", fixture.proposal),
    )
    assert _marker_processed(factory, "cyc-target") is False
    assert repository.read_target(cycle.cycle_id, "cyc-target").inference_state == "pending"

    # After the lock is released the same acceptance commits normally.
    accepted = repository.accept_target(cycle.cycle_id, "cyc-target", fixture.proposal)
    assert accepted.processed is True


def test_cycle_checkpoints_and_acceptance_survive_reopen_without_raw_rewrite(
    database: tuple[Engine, object],
) -> None:
    """Resume, immutable strict payloads, legitimate skips and atomic acceptance all hold."""
    _, factory = database
    pack = load_prompt_pack("v9")
    candidates = _seed_cycle_catalogue(factory)
    reconcile(factory)
    repository = InferenceSchedulingRepository(factory)

    pool = build_pool(factory, "cyc-target", candidates)
    target_input = build_target_input(pool)
    fixture = complete_target(factory, target_input, pack)

    cycle = repository.begin_cycle(HASH_D, ("cyc-target",))
    assert cycle.stage == "multiview"
    # Reopening with the same input/universe resumes the same unfinished cycle.
    assert repository.begin_cycle(HASH_D, ("cyc-target",)).cycle_id == cycle.cycle_id

    multiview = _target_record(
        cycle.cycle_id, "cyc-target", multiview_state="completed", pool_input=pool
    )
    stored = repository.checkpoint(multiview)
    assert stored == multiview
    # An identical replay succeeds. A conflicting completed payload is refused.
    assert repository.checkpoint(multiview) == multiview
    conflicting = _target_record(
        cycle.cycle_id,
        "cyc-target",
        multiview_state="completed",
        pool_input=build_pool(factory, "cyc-target", tuple(reversed(candidates))),
    )
    with pytest.raises(ValueError):
        repository.checkpoint(conflicting)
    repository.set_stage(cycle.cycle_id, "rerank")
    reranked = _target_record(
        cycle.cycle_id,
        "cyc-target",
        multiview_state="completed",
        rerank_state="completed",
        pool_input=pool,
        target_input=target_input,
    )
    repository.checkpoint(reranked)
    repository.set_stage(cycle.cycle_id, "inference")
    planned = repository.read_target(cycle.cycle_id, "cyc-target").model_copy(
        update={"generation_work_key_sha256": fixture.work.work_key_sha256}
    )
    repository.checkpoint(planned)

    attempts_before = _count(factory, InferenceModelAttempt)
    proposals_before = _count(factory, InferenceProposal)
    marker = repository.accept_target(cycle.cycle_id, "cyc-target", fixture.proposal)
    assert marker.processed is True
    assert marker.accepted_proposal_id == fixture.proposal.proposal_id
    # An identical retry is a no-op. A conflicting completed proposal is refused.
    assert repository.accept_target(cycle.cycle_id, "cyc-target", fixture.proposal) == marker
    other = complete_target(factory, target_input, pack, model_identity="other-model")
    with pytest.raises(ValueError):
        repository.accept_target(cycle.cycle_id, "cyc-target", other.proposal)
    assert _count(factory, InferenceModelAttempt) == attempts_before + 1
    assert _count(factory, InferenceProposal) == proposals_before + 1

    # The state projection is stage state alone.
    states = repository.list_target_states(cycle.cycle_id)
    assert len(states) == 1
    assert states[0].inference_state == "completed"

    # Finish the cycle, then a matching completed cycle starts the next one.
    repository.set_stage(cycle.cycle_id, "publication")
    finished = repository.finish_cycle(cycle.cycle_id, input_sha256=HASH_D)
    assert finished.stage == "complete"
    assert finished.stage == "complete"

    # In the next cycle all markers are true, so a rerank/inference skip is legitimate.
    fresh = repository.begin_cycle(HASH_D, ("cyc-target",))
    repository.checkpoint(
        _target_record(fresh.cycle_id, "cyc-target", multiview_state="completed", pool_input=pool)
    )
    repository.set_stage(fresh.cycle_id, "rerank")
    # A false live member makes a rerank/inference skip illegitimate.
    _set_marker_processed(factory, candidates[0], False)
    illegal = _target_record(
        fresh.cycle_id,
        "cyc-target",
        multiview_state="completed",
        rerank_state="skipped",
        inference_state="skipped",
        pool_input=pool,
    )
    with pytest.raises(ValueError):
        repository.checkpoint(illegal)
    # With every member true the same skip is legitimate.
    _set_marker_processed(factory, candidates[0], True)
    skipped = repository.read_target(fresh.cycle_id, "cyc-target").model_copy(
        update={
            "rerank_state": "skipped",
            "inference_state": "skipped",
            "generation_work_key_sha256": None,
            "error_type": None,
        }
    )
    records = repository.read_processing()
    by_group = {record.group_id: record for record in records}
    assert by_group["cyc-target"].processed is True
    assert by_group["cyc-target"].accepted_proposal_id == fixture.proposal.proposal_id
    skipped_result = repository.checkpoint(skipped)
    assert skipped_result.rerank_state == "skipped"
    assert skipped_result.inference_state == "skipped"
    assert skipped_result.pool_input is None and skipped_result.target_input is None

    # A changed input digest creates another cycle and retains the other cycles and rows.
    changed = repository.begin_cycle("e" * 64, ("cyc-target",))
    assert changed.cycle_id != fresh.cycle_id
    # begin_cycle prunes unanchored cycles, so only the changed current cycle is retained.
    assert _count(factory, InferenceProcessingCycle) == 1


def test_successful_cycle_marks_all_courses_and_failed_or_partial_cycle_cannot_finish(
    database: tuple[Engine, object],
) -> None:
    """Only a fully completed publication cycle bulk-marks every course. Pending/failed/coverage guards hold."""
    _, factory = database
    pack = load_prompt_pack("v9")
    candidates = _seed_cycle_catalogue(factory)
    reconcile(factory)
    repository = InferenceSchedulingRepository(factory)
    pool = build_pool(factory, "cyc-target", candidates)
    target_input = build_target_input(pool)
    fixture = complete_target(factory, target_input, pack)

    cycle = repository.begin_cycle(HASH_D, ("cyc-target",))
    # A pending target row refuses both stage advance and finish.
    with pytest.raises(ValueError):
        repository.set_stage(cycle.cycle_id, "rerank")
    with pytest.raises(ValueError):
        repository.finish_cycle(cycle.cycle_id, input_sha256=HASH_D)

    repository.checkpoint(
        _target_record(cycle.cycle_id, "cyc-target", multiview_state="completed", pool_input=pool)
    )
    repository.set_stage(cycle.cycle_id, "rerank")
    repository.checkpoint(
        _target_record(
            cycle.cycle_id,
            "cyc-target",
            multiview_state="completed",
            rerank_state="completed",
            pool_input=pool,
            target_input=target_input,
        )
    )
    repository.set_stage(cycle.cycle_id, "inference")
    planned = repository.read_target(cycle.cycle_id, "cyc-target").model_copy(
        update={"generation_work_key_sha256": fixture.work.work_key_sha256}
    )
    repository.checkpoint(planned)

    # A failed required unit is recorded safely and cannot be finalized or bulk-marked.
    failed = repository.read_target(cycle.cycle_id, "cyc-target").model_copy(
        update={"inference_state": "failed", "error_type": "InferenceRequestError"}
    )
    repository.checkpoint(failed)
    _set_marker_processed(factory, "cyc-target", False)
    with pytest.raises(ValueError):
        repository.set_stage(cycle.cycle_id, "publication")
    assert repository.read_target(cycle.cycle_id, "cyc-target").inference_state == "failed"

    # Successful acceptance lets the cycle finish and bulk-marks all catalogue courses true.
    retry_planned = repository.read_target(cycle.cycle_id, "cyc-target").model_copy(
        update={"generation_work_key_sha256": fixture.work.work_key_sha256}
    )
    repository.checkpoint(retry_planned)
    accepted = repository.accept_target(cycle.cycle_id, "cyc-target", fixture.proposal)
    assert accepted.processed is True
    # The finish stage re-marks a marker left unprocessed.
    _set_marker_processed(factory, "cyc-target", False)
    repository.set_stage(cycle.cycle_id, "publication")
    finished = repository.finish_cycle(cycle.cycle_id, input_sha256=HASH_D)
    assert finished.stage == "complete"
    with session_scope(factory) as session:
        flags = session.execute(
            select(Course.group_id, InferenceCourseProcessing.processed).join(
                InferenceCourseProcessing,
                InferenceCourseProcessing.course_id == Course.id,
            )
        ).all()
    flags_by_group = dict(flags)
    assert flags_by_group["cyc-target"] is True
    assert all(flag is True for flag in flags_by_group.values())
    # No inactive candidate ever received a target row or a model attempt.
    inactive = {f"cand-{index:02d}" for index in range(1, 50, 2)}
    with session_scope(factory) as session:
        target_rows = session.scalars(
            select(InferenceProcessingTarget)
            .join(Course, Course.id == InferenceProcessingTarget.target_course_id)
            .where(Course.group_id.in_(inactive))
        ).all()
    assert target_rows == []
    assert _count(factory, InferenceTargetWork) == 1
    assert _count(factory, InferenceModelAttempt) == 1

    # A canonical course added after reconcile has no marker and blocks the finish coverage check.
    cycle_two = repository.begin_cycle(HASH_D, ("cyc-target",))
    repository.checkpoint(
        _target_record(
            cycle_two.cycle_id, "cyc-target", multiview_state="completed", pool_input=pool
        )
    )
    repository.set_stage(cycle_two.cycle_id, "rerank")
    repository.checkpoint(
        _target_record(
            cycle_two.cycle_id,
            "cyc-target",
            multiview_state="completed",
            rerank_state="completed",
            pool_input=pool,
            target_input=target_input,
        )
    )
    repository.set_stage(cycle_two.cycle_id, "inference")
    planned_two = repository.read_target(cycle_two.cycle_id, "cyc-target").model_copy(
        update={"generation_work_key_sha256": fixture.work.work_key_sha256}
    )
    repository.checkpoint(planned_two)
    accepted_two = repository.accept_target(cycle_two.cycle_id, "cyc-target", fixture.proposal)
    assert accepted_two.processed is True
    repository.set_stage(cycle_two.cycle_id, "publication")
    # A canonical course added after reconcile has no marker and blocks the finish coverage check.
    with session_scope(factory) as session:
        session.add(
            Course(
                group_id="late-course",
                is_active=True,
                activity_as_of_academic_year_start=2026,
                activity_window_years=3,
            )
        )
    with pytest.raises(ValueError):
        repository.finish_cycle(cycle_two.cycle_id, input_sha256=HASH_D)


def _ready_inference_cycle(
    factory: object,
    repository: InferenceSchedulingRepository,
    *,
    input_sha256: str,
    pool,
    target_input,
) -> object:
    """Begin/resume one cycle and bring its single target to the ready inference stage."""
    cycle = repository.begin_cycle(input_sha256, ("cyc-target",))
    repository.checkpoint(
        _target_record(cycle.cycle_id, "cyc-target", multiview_state="completed", pool_input=pool)
    )
    repository.set_stage(cycle.cycle_id, "rerank")
    repository.checkpoint(
        _target_record(
            cycle.cycle_id,
            "cyc-target",
            multiview_state="completed",
            rerank_state="completed",
            pool_input=pool,
            target_input=target_input,
        )
    )
    repository.set_stage(cycle.cycle_id, "inference")
    return cycle


def test_generation_reservation_survives_interruption_and_cycle_restart(
    database: tuple[Engine, object],
) -> None:
    """A durable reservation holds through abandonment and the next calculation restarts greedy."""
    _, factory = database
    candidates = _seed_cycle_catalogue(factory)
    reconcile(factory)
    repository = InferenceSchedulingRepository(factory)
    pool = build_pool(factory, "cyc-target", candidates)
    value = build_target_input(pool)
    cycle = _ready_inference_cycle(
        factory, repository, input_sha256=HASH_D, pool=pool, target_input=value
    )

    # The calculation's first attempt is greedy. The reservation is durable even without an outcome.
    assert repository.reserve_generation_attempt(cycle.cycle_id, "cyc-target") == (1, True)
    # Abandoning the pass resumes the same calculation at the next lifetime ordinal.
    assert repository.begin_cycle(HASH_D, ("cyc-target",)).cycle_id == cycle.cycle_id
    assert repository.reserve_generation_attempt(cycle.cycle_id, "cyc-target") == (2, False)

    # Another cycle-target calculation starts greedy at the next lifetime ordinal.
    changed = _ready_inference_cycle(
        factory, repository, input_sha256="e" * 64, pool=pool, target_input=value
    )
    assert changed.cycle_id != cycle.cycle_id
    assert repository.reserve_generation_attempt(changed.cycle_id, "cyc-target") == (3, True)


def _marker_facts(factory: object, group_id: str) -> tuple[bool, int, str | None]:
    """Read one marker's processed flag, lifetime counter and durable decision directly."""
    with session_scope(factory) as session:
        row = session.scalar(
            select(InferenceCourseProcessing)
            .join(Course, Course.id == InferenceCourseProcessing.course_id)
            .where(Course.group_id == group_id)
        )
        assert row is not None
        return row.processed, int(row.generation_attempt_count), row.disposition


def _target_facts(
    factory: object, cycle_id: object, group_id: str
) -> tuple[str, str | None, str | None, bool]:
    """Read one target checkpoint's inference state, error, planned key and started fact."""
    with session_scope(factory) as session:
        row = session.scalar(
            select(InferenceProcessingTarget)
            .join(Course, Course.id == InferenceProcessingTarget.target_course_id)
            .where(
                InferenceProcessingTarget.cycle_id == cycle_id,
                Course.group_id == group_id,
            )
        )
        assert row is not None
        return (
            row.inference_state,
            row.error_type,
            row.generation_work_key_sha256,
            bool(row.generation_started),
        )


@pytest.mark.parametrize(
    ("prior", "next_choice"),
    [
        (None, None),
        (None, "done"),
        (None, "failed"),
        ("done", None),
        ("done", "done"),
        ("done", "failed"),
        ("failed", None),
        ("failed", "done"),
        ("failed", "failed"),
    ],
)
def test_operator_disposition_survives_text_change_and_cycle_restart(
    database: tuple[Engine, object],
    prior: str | None,
    next_choice: str | None,
) -> None:
    """One explicit decision transition persists across text, cycles and pruning, and clears alone."""
    _, factory = database
    pack = load_prompt_pack("v9")
    candidates = _seed_cycle_catalogue(factory)
    reconcile(factory)
    repository = InferenceSchedulingRepository(factory)
    pool = build_pool(factory, "cyc-target", candidates)
    target_input = build_target_input(pool)
    fixture = complete_target(factory, target_input, pack)
    cycle = _ready_inference_cycle(
        factory, repository, input_sha256=HASH_D, pool=pool, target_input=target_input
    )
    planned = repository.read_target(cycle.cycle_id, "cyc-target").model_copy(
        update={"generation_work_key_sha256": fixture.work.work_key_sha256}
    )
    repository.checkpoint(planned)
    assert repository.reserve_generation_attempt(cycle.cycle_id, "cyc-target") == (1, True)
    accepted = repository.accept_target(cycle.cycle_id, "cyc-target", fixture.proposal)
    assert accepted.processed is True
    assert accepted.accepted_proposal_id == fixture.proposal.proposal_id

    # An explicit decision is set through the real owner. NULL is no override.
    if prior is not None:
        assert repository.set_target_disposition("cyc-target", prior).disposition == prior
    before_proposals = _count(factory, InferenceProposal)
    before_failures = _count(factory, InferenceTargetFailure)

    changed = repository.set_target_disposition("cyc-target", next_choice)  # type: ignore[arg-type]
    assert changed.disposition == next_choice

    # The decision, the independent flag, the genuine pointer and every lifetime/calculation fact
    # survive. Only an actual nonnull-to-NULL clear returns this one target to automatic eligibility.
    processed, counter, disposition = _marker_facts(factory, "cyc-target")
    assert disposition == next_choice
    expected_processed = not (prior is not None and next_choice is None)
    assert processed is expected_processed
    assert counter == 1
    assert changed.accepted_proposal_id == fixture.proposal.proposal_id
    assert _count(factory, InferenceProposal) == before_proposals
    assert _count(factory, InferenceTargetFailure) == before_failures

    inference_state, error_type, key, started = _target_facts(factory, cycle.cycle_id, "cyc-target")
    assert key == fixture.work.work_key_sha256
    assert started is True
    if next_choice == "done":
        assert (inference_state, error_type) == ("completed", None)
    elif next_choice == "failed":
        assert (inference_state, error_type) == ("failed", "OperatorDisposition")
    elif prior is None:
        # A NULL-to-NULL repeat is a no-op: the accepted terminal state is untouched.
        assert inference_state == "completed"
    else:
        # A clear reopens only this target's inference state and keeps recoverable upstream stages.
        assert (inference_state, error_type) == ("pending", None)
        assert repository.read_target(cycle.cycle_id, "cyc-target").rerank_state == "completed"

    # A real teaching-text change and ordinary pruning never change the explicit decision.
    with session_scope(factory) as session:
        text = session.scalar(
            select(CourseText)
            .join(CourseVersion, CourseVersion.id == CourseText.course_version_id)
            .join(Course, Course.id == CourseVersion.course_id)
            .where(Course.group_id == "cyc-target")
        )
        assert text is not None
        text.content_fi = "Muuttunut opetussisalto"
    reconcile(factory)
    repository.prune_retained_state()
    assert _marker_facts(factory, "cyc-target")[2] == next_choice
    assert (
        repository.read_target_processing("cyc-target").accepted_proposal_id
        == fixture.proposal.proposal_id
    )

    # Another cycle carries the retained decision onto its target row.
    fresh = repository.begin_cycle("e" * 64, ("cyc-target",))
    assert fresh.cycle_id != cycle.cycle_id
    fresh_state = _target_facts(factory, fresh.cycle_id, "cyc-target")[0]
    assert (
        fresh_state
        == {
            "done": "completed",
            "failed": "failed",
            None: "pending",
        }[next_choice]
    )

    if next_choice == "failed":
        # A terminal failed decision on a completed cycle reopens it at inference so it is
        # incomplete, never silently complete.
        repository.set_target_disposition("cyc-target", None)
        repository.checkpoint(
            _target_record(
                fresh.cycle_id, "cyc-target", multiview_state="completed", pool_input=pool
            )
        )
        repository.set_stage(fresh.cycle_id, "rerank")
        repository.checkpoint(
            _target_record(
                fresh.cycle_id,
                "cyc-target",
                multiview_state="completed",
                rerank_state="completed",
                pool_input=pool,
                target_input=target_input,
            )
        )
        repository.set_stage(fresh.cycle_id, "inference")
        planned_fresh = repository.read_target(fresh.cycle_id, "cyc-target").model_copy(
            update={"generation_work_key_sha256": fixture.work.work_key_sha256}
        )
        repository.checkpoint(planned_fresh)
        repository.accept_target(fresh.cycle_id, "cyc-target", fixture.proposal)
        repository.set_stage(fresh.cycle_id, "publication")
        finished = repository.finish_cycle(fresh.cycle_id, input_sha256="e" * 64)
        assert finished.stage == "complete"
        assert repository.set_target_disposition("cyc-target", "failed").disposition == "failed"
        assert repository.read_cycle(fresh.cycle_id).stage == "inference"
