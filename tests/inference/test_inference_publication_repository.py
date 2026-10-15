"""Opt-in PostgreSQL publication/idempotency/withdrawal tests for the inference publisher.

These tests seed canonical courses with selected representatives, run/work/attempt evidence, and
accepted proposals through the real repositories, then exercise the one inference publication route
into the final inferred-set and equivalence stores.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import Engine, select

from course_explorer.db.models import (
    Course,
    InferenceModelAttempt,
    InferenceProposal,
    InferenceTargetWork,
    InferredEquivalenceGroup,
    InferredPrerequisiteSet,
)
from course_explorer.db.session import session_scope
from course_explorer.enums import (
    InferredProducerKind,
)
from course_explorer.inference import proposal_commands
from course_explorer.inference.domain import (
    InferenceTargetResultV2,
)
from course_explorer.inference.evidence_repository import InferenceEvidenceRepository
from course_explorer.inference.publication import (
    CurrentInferenceCohort,
    prepare_current_publication,
    publish_current_cohort,
)
from course_explorer.prerequisite.domain import (
    EquivalenceGroupMember,
    EquivalenceGroupPublication,
    InferenceEvidenceReference,
    InferenceNodeMetadata,
    InferredCoverageState,
    InferredPrerequisiteCategory,
    InferredReadState,
    OrRequirement,
    PrerequisiteExpression,
    PrerequisiteOrigin,
)
from course_explorer.prerequisite.equivalence_repository import InferredEquivalenceRepository
from course_explorer.prerequisite.repository import InferredPrerequisiteRepository
from tests.inference._publication_repository_support import (
    STARTED_AT,
    WINDOW,
    YEAR,
    _build_proposal,
    _cohort,
    _completed_work,
    _count,
    _course_requirement,
    _equivalence,
    _failed_work,
    _hash,
    _member_ids,
    _seed_course,
    settings_pair,
)

pytestmark = [
    pytest.mark.integration,
]


def test_publish_idempotent_complete_empty_and_recommended_through_the_stores(
    database: tuple[Engine, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Publishing is idempotent. Complete-empty and recommended results reach the stores."""
    _, factory = database
    settings, selection = settings_pair()
    target_one, member_one = "pub-target-one", "pub-member-one"
    target_two, member_two = "pub-target-two", "pub-member-two"
    for group_id, code in (
        (target_one, "PUB-T1"),
        (member_one, "PUB-C1"),
        (target_two, "PUB-T2"),
        (member_two, "PUB-C2"),
    ):
        _seed_course(factory, group_id, code)

    evidence = InferenceEvidenceRepository(factory)
    work_one, attempt_one, _ = _completed_work(
        evidence, target_one, candidate_group_ids=(member_one,)
    )
    work_two, attempt_two, _ = _completed_work(
        evidence, target_two, candidate_group_ids=(member_two,)
    )
    work_member, attempt_member, _ = _completed_work(
        evidence, member_one, candidate_group_ids=(target_one,)
    )
    required = _build_proposal(
        factory,
        target_one,
        work_one,
        attempt_one,
        expression=lambda reference: _course_requirement(
            member_one, InferredPrerequisiteCategory.REQUIRED, "0.9", reference=reference
        ),
        equivalence=lambda reference: (
            _equivalence((target_one, member_one), "0.9", reference=reference),
        ),
    )
    proposal_two = _build_proposal(
        factory,
        target_two,
        work_two,
        attempt_two,
        expression=lambda reference: _course_requirement(
            member_two, InferredPrerequisiteCategory.RECOMMENDED, "0.7", reference=reference
        ),
    )
    member_empty = _build_proposal(
        factory, member_one, work_member, attempt_member, expression=None
    )
    assert member_empty.expression is None

    cohort = _cohort(
        {
            target_one: required.proposal_id,
            target_two: proposal_two.proposal_id,
            member_one: member_empty.proposal_id,
        }
    )

    # An injected mid-publication failure leaves the completed atomic output in place and
    # changes no immutable evidence. The deterministic replay then repairs the rest without duplicates.
    original_publish = InferredPrerequisiteRepository.publish

    def _fail_on_target_one(self, publication):
        if publication.target_group_id == target_one:
            raise RuntimeError("injected publication failure")
        return original_publish(self, publication)

    monkeypatch.setattr(InferredPrerequisiteRepository, "publish", _fail_on_target_one)
    work_rows = _count(factory, InferenceTargetWork)
    raw_attempts = _count(factory, InferenceModelAttempt)
    raw_proposals = _count(factory, InferenceProposal)
    with pytest.raises(RuntimeError):
        publish_current_cohort(factory, cohort, settings, selection)
    partial_repository = InferredPrerequisiteRepository(factory)
    partial_member = partial_repository.read(member_one)
    assert partial_member.state is InferredReadState.CURRENT
    assert partial_member.current_set is not None
    assert partial_member.current_set.expression is None
    assert partial_repository.read(target_one).state is InferredReadState.UNAVAILABLE
    assert _count(factory, InferredPrerequisiteSet) == 1
    assert _count(factory, InferredEquivalenceGroup) == 0
    assert _count(factory, InferenceTargetWork) == work_rows
    assert _count(factory, InferenceModelAttempt) == raw_attempts
    assert _count(factory, InferenceProposal) == raw_proposals
    monkeypatch.setattr(InferredPrerequisiteRepository, "publish", original_publish)

    diagnostics = publish_current_cohort(factory, cohort, settings, selection)
    assert diagnostics.accepted_targets == 3
    assert diagnostics.published_targets == 3
    assert diagnostics.current_equivalence_groups == 1

    repository = InferredPrerequisiteRepository(factory)
    stored = repository.read(target_one).current_set
    assert stored is not None
    assert stored.input_hash == required.identity_sha256
    assert stored.expression == required.expression
    # The recommended target materializes its exact composed expression.
    recommended = repository.read(target_two).current_set
    assert recommended is not None
    assert recommended.expression == proposal_two.expression

    equivalence = InferredEquivalenceRepository(factory)
    groups = equivalence.read_for_member(member_one)
    assert len(groups) == 1
    assert _member_ids(groups[0]) == tuple(sorted((target_one, member_one)))
    assert groups[0].inference.confidence == Decimal("0.9")

    # An identical second publication is a no-op and appends no duplicate rows.
    set_count = _count(factory, InferredPrerequisiteSet)
    attempt_rows = _count(factory, InferenceModelAttempt)
    second = publish_current_cohort(factory, cohort, settings, selection)
    assert second.published_targets == 3
    assert _count(factory, InferredPrerequisiteSet) == set_count
    assert _count(factory, InferredEquivalenceGroup) == 1
    assert _count(factory, InferenceModelAttempt) == attempt_rows
    assert repository.read(target_one).current_set == stored

    # A cohort that omits a published inference target is rejected before any mutation.
    published_sets = _count(factory, InferredPrerequisiteSet)
    published_groups = _count(factory, InferredEquivalenceGroup)
    published_inputs = {
        group_id: repository.read(group_id).current_set.input_hash
        for group_id in (target_one, target_two, member_one)
    }
    with pytest.raises(ValueError):
        publish_current_cohort(
            factory, _cohort({target_one: required.proposal_id}), settings, selection
        )
    assert _count(factory, InferredPrerequisiteSet) == published_sets
    assert _count(factory, InferredEquivalenceGroup) == published_groups
    assert {
        group_id: repository.read(group_id).current_set.input_hash
        for group_id in (target_one, target_two, member_one)
    } == published_inputs
    assert repository.read(target_one).current_set == stored


def test_retained_publication_holds_output_through_failed_work_and_rewrites_empty_results(
    database: tuple[Engine, object],
) -> None:
    """Retained pointers hold their output through failed work and are wholly rewritten by a genuine empty result."""
    _, factory = database
    settings, selection = settings_pair()
    target_one, member_one = "wd-target-one", "wd-member-one"
    target_two = "wd-target-two"
    member_two, test_a, test_b = "wd-member-two", "wd-test-a", "wd-test-b"
    for group_id, code in (
        (target_one, "WD-T1"),
        (target_two, "WD-T2"),
        (member_one, "WD-C1"),
        (member_two, "WD-C2"),
        (test_a, "WD-TA"),
        (test_b, "WD-TB"),
    ):
        _seed_course(factory, group_id, code)

    evidence = InferenceEvidenceRepository(factory)
    work_one, attempt_one, _ = _completed_work(
        evidence, target_one, candidate_group_ids=(member_one,)
    )
    work_two, attempt_two, _ = _completed_work(
        evidence, target_two, candidate_group_ids=(member_two,)
    )
    proposal_one = _build_proposal(
        factory,
        target_one,
        work_one,
        attempt_one,
        expression=lambda reference: _course_requirement(
            member_one, InferredPrerequisiteCategory.REQUIRED, "0.9", reference=reference
        ),
        equivalence=lambda reference: (
            _equivalence((target_one, member_one), "0.9", reference=reference),
            _equivalence((target_one, member_two), "0.8", reference=reference),
        ),
    )
    proposal_two = _build_proposal(
        factory,
        target_two,
        work_two,
        attempt_two,
        expression=lambda reference: _course_requirement(
            member_two, InferredPrerequisiteCategory.REQUIRED, "0.7", reference=reference
        ),
        equivalence=lambda reference: (
            _equivalence((target_one, member_one), "0.7", reference=reference),
            _equivalence((target_two, member_two), "0.6", reference=reference),
        ),
    )

    # A test-owned group present over two live courses must hold through every reconciliation pass.
    equivalence = InferredEquivalenceRepository(factory)
    test_group_id = UUID(int=555)
    equivalence.publish(
        EquivalenceGroupPublication(
            group_id=test_group_id,
            members=(
                EquivalenceGroupMember(
                    course_group_id=test_a,
                    activity_as_of_academic_year_start=YEAR,
                    activity_window_years=WINDOW,
                ),
                EquivalenceGroupMember(
                    course_group_id=test_b,
                    activity_as_of_academic_year_start=YEAR,
                    activity_window_years=WINDOW,
                ),
            ),
            producer_kind=InferredProducerKind.TEST,
            producer_name="test-fixture",
            producer_version="1",
            input_hash=_hash("test-group"),
            inference=InferenceNodeMetadata(
                confidence=Decimal("0.5"), requirement_ids=(), evidence=()
            ),
            generated_at=STARTED_AT,
        )
    )

    cohort = _cohort({target_one: proposal_one.proposal_id, target_two: proposal_two.proposal_id})
    first = publish_current_cohort(factory, cohort, settings, selection)
    assert first.published_targets == 2
    assert first.current_equivalence_groups == 3
    assert _count(factory, InferredEquivalenceGroup) == 4

    # A failed work attempt for the second target does not withdraw its retained output: the
    # same accepted pointers are republished and the raw failure is preserved as evidence.
    _failed_work(evidence, target_two)
    raw_proposals = _count(factory, InferenceProposal)
    raw_attempts = _count(factory, InferenceModelAttempt)
    raw_works = _count(factory, InferenceTargetWork)
    retained = publish_current_cohort(factory, cohort, settings, selection)
    assert retained.accepted_targets == 2
    assert retained.published_targets == 2
    repository = InferredPrerequisiteRepository(factory)
    assert repository.read(target_two).state is InferredReadState.CURRENT
    assert _count(factory, InferenceProposal) == raw_proposals
    assert _count(factory, InferenceModelAttempt) == raw_attempts
    assert _count(factory, InferenceTargetWork) == raw_works

    # A genuine empty/no-group publication for the second target wholly rewrites it and removes
    # only its own supporters. The shared group keeps the first target's supporter.
    replacement_work, replacement_attempt, _ = _completed_work(
        evidence, target_two, candidate_group_ids=(member_two,), model_identity="other-model"
    )
    empty_two = _build_proposal(
        factory, target_two, replacement_work, replacement_attempt, expression=None
    )
    replaced = publish_current_cohort(
        factory,
        _cohort({target_one: proposal_one.proposal_id, target_two: empty_two.proposal_id}),
        settings,
        selection,
    )
    assert replaced.published_targets == 2
    empty_read = repository.read(target_two)
    assert empty_read.state is InferredReadState.CURRENT
    assert empty_read.current_set is not None
    assert empty_read.current_set.expression is None
    assert empty_read.current_set.input_hash == empty_two.identity_sha256
    remaining = {_member_ids(group) for group in equivalence.read_for_member(target_one)}
    assert remaining == {
        tuple(sorted((target_one, member_one))),
        tuple(sorted((target_one, member_two))),
    }
    shared = next(
        group
        for group in equivalence.read_for_member(member_one)
        if _member_ids(group) == tuple(sorted((target_one, member_one)))
    )
    assert [reference.reference_id for reference in shared.inference.evidence] == [
        str(proposal_one.proposal_id)
    ]
    assert tuple(sorted((target_two, member_two))) not in remaining
    assert test_group_id in {group.group_id for group in equivalence.read_for_member(test_a)}

    # Canonical year/window rollover with the retained cohort keeps the stored target/group rows,
    # contexts and timestamps as-is while the current reads succeed.
    with session_scope(factory) as session:
        for group_id in (target_one, target_two, member_one, member_two):
            course = session.scalar(select(Course).where(Course.group_id == group_id))
            assert course is not None
            course.activity_as_of_academic_year_start = YEAR + 1
            course.activity_window_years = WINDOW + 1
    stored_one = repository.read(target_one).current_set
    stored_two = repository.read(target_two).current_set
    stored_groups = {
        group.group_id: (group.generated_at, group.published_at)
        for group in equivalence.read_for_member(target_one)
    }
    before_sets = _count(factory, InferredPrerequisiteSet)
    before_groups = _count(factory, InferredEquivalenceGroup)
    rollover = publish_current_cohort(
        factory,
        _cohort({target_one: proposal_one.proposal_id, target_two: empty_two.proposal_id}),
        settings,
        selection,
    )
    assert rollover.published_targets == 2
    assert _count(factory, InferredPrerequisiteSet) == before_sets
    assert _count(factory, InferredEquivalenceGroup) == before_groups
    assert repository.read(target_one).current_set == stored_one
    assert repository.read(target_two).current_set == stored_two
    assert {
        group.group_id: (group.generated_at, group.published_at)
        for group in equivalence.read_for_member(target_one)
    } == stored_groups
    assert _count(factory, InferenceModelAttempt) == raw_attempts + 1

    # An explicit operator done target withdraws its whole predecessor contribution through the same
    # owners: no proposal, completion, final row or equivalence supporter is fabricated and
    # the unrelated genuine result is preserved.
    before_proposals = _count(factory, InferenceProposal)
    before_attempts = _count(factory, InferenceModelAttempt)
    done = publish_current_cohort(
        factory,
        CurrentInferenceCohort(
            eligible_target_group_ids=cohort.eligible_target_group_ids,
            accepted_proposal_ids={target_two: empty_two.proposal_id},
            completed_without_output_target_group_ids=(target_one,),
        ),
        settings,
        selection,
    )
    assert done.operator_done_targets == 1
    assert repository.read(target_one).state is InferredReadState.UNAVAILABLE
    assert repository.read(target_two).state is InferredReadState.CURRENT
    assert _count(factory, InferenceProposal) == before_proposals
    assert _count(factory, InferenceModelAttempt) == before_attempts
    assert tuple(sorted((target_one, member_one))) not in {
        _member_ids(group) for group in equivalence.read_for_member(target_one)
    }
    assert test_group_id in {group.group_id for group in equivalence.read_for_member(test_a)}


def test_complete_empty_v2_roundtrip_composes_and_publishes_complete_coverage(
    database: tuple[Engine, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A complete-empty v2 result carries through the DB round trip and publishes complete."""
    _, factory = database
    settings, selection = settings_pair()
    target = "pub-empty-roundtrip"
    source = "pub-empty-source"
    _seed_course(factory, target, "pub-empty-roundtrip-code")
    _seed_course(factory, source, "pub-empty-source-code")

    evidence = InferenceEvidenceRepository(factory)
    work, attempt, _ = _completed_work(evidence, target, candidate_group_ids=(source,))

    # The persisted completion carries the exact uncomposed v2 result before composition.
    stored = evidence.read_completion(work.work_id)
    assert stored is not None
    result = stored.payload.result
    assert type(result) is InferenceTargetResultV2
    assert result.required == ()
    assert result.recommended == ()
    assert result.equivalence == ()

    # Real composition through the shared helper and repositories.
    first = proposal_commands.compose_proposal_from_work(factory, work.work_id, settings=settings)
    assert first.expression is None
    assert first.equivalence == ()
    assert _count(factory, InferenceProposal) == 1

    cohort = _cohort({target: first.proposal_id})
    diagnostics = publish_current_cohort(factory, cohort, settings, selection)
    assert diagnostics.eligible_targets == 1
    assert diagnostics.selected_targets == 1
    assert diagnostics.processed_targets == 1
    assert diagnostics.accepted_targets == 1
    assert diagnostics.published_targets == 1

    repository = InferredPrerequisiteRepository(factory)
    stored_read = repository.read(target)
    assert stored_read.state is InferredReadState.CURRENT
    assert stored_read.current_set is not None
    assert stored_read.current_set.expression is None
    assert stored_read.current_set.coverage_state is InferredCoverageState.COMPLETE
    assert stored_read.current_set.coverage.eligible_source_count == 1
    assert stored_read.current_set.coverage.processed_source_count == 1
    assert stored_read.current_set.coverage.accepted_source_count == 0


def test_prepare_retained_cohort_validates_explicit_pointers_and_preserves_mixed_provenance(
    database: tuple[Engine, object],
) -> None:
    """Explicit retained pointers validate by chain. A missing pointer is uncovered, not empty."""
    _, factory = database
    settings, selection = settings_pair()
    for group_id, code in (
        ("T1", "T1-code"),
        ("T2", "T2-code"),
        ("T3", "T3-code"),
        ("C1", "C1-code"),
        ("C2", "C2-code"),
    ):
        _seed_course(factory, group_id, code)
    evidence = InferenceEvidenceRepository(factory)
    work_one, attempt_one, _ = _completed_work(evidence, "T1", candidate_group_ids=("C1", "C2"))
    work_two, attempt_two, _ = _completed_work(evidence, "T2", candidate_group_ids=("C1", "C2"))
    current = _build_proposal(
        factory,
        "T1",
        work_one,
        attempt_one,
        expression=lambda reference: _course_requirement(
            "C1", InferredPrerequisiteCategory.REQUIRED, "0.9", reference=reference
        ),
        equivalence=lambda reference: (_equivalence(("T1", "C1"), "0.9", reference=reference),),
    )
    historical = _build_proposal(
        factory,
        "T2",
        work_two,
        attempt_two,
        expression=None,
        equivalence=lambda reference: (_equivalence(("T2", "C1"), "0.7", reference=reference),),
        proposal_version="v0",
        official_hash="b" * 64,
    )
    cohort = CurrentInferenceCohort(
        eligible_target_group_ids=("T1", "T2", "T3"),
        accepted_proposal_ids={"T1": current.proposal_id, "T2": historical.proposal_id},
    )

    plan = prepare_current_publication(factory, cohort, settings, selection)

    assert [proposal.proposal_id for proposal in plan.proposals] == [
        current.proposal_id,
        historical.proposal_id,
    ]
    # A valid pointerless eligible target (T3) is uncovered and is never fabricated as empty.
    assert {publication.target_group_id for publication in plan.target_publications} == {"T1", "T2"}
    diagnostics = plan.diagnostics
    assert diagnostics.eligible_targets == 3
    assert diagnostics.selected_targets == 2
    assert diagnostics.processed_targets == 2
    assert diagnostics.local_targets == 2
    assert diagnostics.other_route_targets == 0
    assert diagnostics.accepted_targets == 2
    assert diagnostics.published_targets == 0
    assert diagnostics.observed_packet_candidates == 2 * 2
    assert diagnostics.expected_packet_candidates == 2 * selection.inference_selection_final_k
    assert diagnostics.historical_proposal_rows == 2
    assert diagnostics.current_equivalence_groups == 2

    # A pointerless eligible target that is not a canonical course fails read-only preparation.
    unknown = CurrentInferenceCohort(
        eligible_target_group_ids=("T1", "T2", "T9"),
        accepted_proposal_ids={"T1": current.proposal_id, "T2": historical.proposal_id},
    )
    with pytest.raises(ValueError):
        prepare_current_publication(factory, unknown, settings, selection)

    # A pointerless eligible target that is inactive fails read-only preparation too.
    with session_scope(factory) as session:
        course = session.scalar(select(Course).where(Course.group_id == "T3"))
        assert course is not None
        course.is_active = False
    inactive = CurrentInferenceCohort(
        eligible_target_group_ids=("T1", "T2", "T3"),
        accepted_proposal_ids={"T1": current.proposal_id, "T2": historical.proposal_id},
    )
    with pytest.raises(ValueError):
        prepare_current_publication(factory, inactive, settings, selection)

    # A selected pointer with no retained proposal raises before any write.
    broken = CurrentInferenceCohort(
        eligible_target_group_ids=("T1",),
        accepted_proposal_ids={"T1": UUID(int=999)},
    )
    with pytest.raises(ValueError):
        prepare_current_publication(factory, broken, settings, selection)


def test_exact_group_minimum_confidence_and_strict_ancestor_warning(
    database: tuple[Engine, object],
) -> None:
    """Group payloads carry the minimum genuine supporter confidence. Warnings never suppress."""
    _, factory = database
    settings, selection = settings_pair()
    for group_id, code in (
        ("T1", "T1-code"),
        ("B", "B-code"),
        ("C1", "C1-code"),
        ("C2", "C2-code"),
    ):
        _seed_course(factory, group_id, code)
    for group_id, code in (("C3", "C3-code"), ("C4", "C4-code")):
        _seed_course(factory, group_id, code, is_active=False)
    evidence = InferenceEvidenceRepository(factory)
    work_one, attempt_one, _ = _completed_work(
        evidence, "T1", candidate_group_ids=("C1", "C2", "C3", "C4")
    )
    work_two, attempt_two, _ = _completed_work(
        evidence, "B", candidate_group_ids=("C1", "C2", "C3", "C4")
    )

    # T1 names B and C directly. B names C directly, so C is a strict ancestor of B for T1.
    def expression_one(reference: InferenceEvidenceReference) -> PrerequisiteExpression:
        return OrRequirement(
            type="or",
            origin=PrerequisiteOrigin.INFERRED,
            inferred_category=InferredPrerequisiteCategory.REQUIRED,
            children=(
                _course_requirement(
                    "B", InferredPrerequisiteCategory.REQUIRED, "0.9", reference=reference
                ),
                _course_requirement(
                    "C", InferredPrerequisiteCategory.REQUIRED, "0.9", reference=reference
                ),
            ),
            inference=InferenceNodeMetadata(
                confidence=Decimal("0.5"), requirement_ids=(), evidence=(reference,)
            ),
        )

    def expression_two(reference: InferenceEvidenceReference) -> PrerequisiteExpression:
        return _course_requirement(
            "C", InferredPrerequisiteCategory.REQUIRED, "0.4", reference=reference
        )

    proposal_one = _build_proposal(
        factory,
        "T1",
        work_one,
        attempt_one,
        expression=expression_one,
        equivalence=lambda reference: (
            _equivalence(("T1", "C1"), "0.9", reference=reference),
            _equivalence(("T1", "C2", "C3"), "0.7", reference=reference),
            _equivalence(("T1", "C3", "C4"), "0.6", reference=reference),
        ),
    )
    proposal_two = _build_proposal(
        factory,
        "B",
        work_two,
        attempt_two,
        expression=expression_two,
        equivalence=lambda reference: (_equivalence(("T1", "C1"), "0.8", reference=reference),),
        proposal_version="v2",
    )
    cohort = _cohort({"T1": proposal_one.proposal_id, "B": proposal_two.proposal_id})

    plan = prepare_current_publication(factory, cohort, settings, selection)

    shared = next(
        publication
        for publication in plan.group_publications
        if tuple(member.course_group_id for member in publication.members) == ("C1", "T1")
    )
    assert shared.inference.confidence == Decimal("0.8")
    assert shared.producer_version == "v1+v2"
    assert shared.generated_at == STARTED_AT
    assert [reference.reference_id for reference in shared.inference.evidence] == sorted(
        (str(proposal_one.proposal_id), str(proposal_two.proposal_id))
    )

    trimmed = next(
        publication
        for publication in plan.group_publications
        if tuple(member.course_group_id for member in publication.members) == ("C2", "T1")
    )
    assert tuple(member.course_group_id for member in trimmed.members) == ("C2", "T1")
    assert all(
        tuple(member.course_group_id for member in publication.members) != ("T1",)
        for publication in plan.group_publications
    )
    assert plan.diagnostics.current_equivalence_groups == 2

    from course_explorer.inference.diagnostics import strict_ancestor_warnings

    warnings = strict_ancestor_warnings(plan.proposals)
    assert len(warnings) == 1
    assert warnings[0].target_group_id == "T1"
    assert warnings[0].via_group_id == "B"
    assert warnings[0].ancestor_group_id == "C"
    assert warnings[0].reason == "strict_ancestor"
    assert plan.diagnostics.transitive_warnings == warnings

    # The warning has no suppressing effect: both direct options stay in the published expression.
    target_publication = next(
        publication
        for publication in plan.target_publications
        if publication.target_group_id == "T1"
    )
    assert target_publication.expression is not None
    assert target_publication.coverage.accepted_source_count == 2
