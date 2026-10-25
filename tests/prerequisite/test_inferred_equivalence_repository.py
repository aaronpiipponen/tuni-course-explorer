"""Opt-in PostgreSQL publication/read/reconciliation tests for inferred equivalence groups."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, delete, func, select, update

from course_explorer.db.models import (
    Course,
    InferredEquivalenceGroup,
    InferredEquivalenceGroupMember,
    InferredPrerequisiteSet,
)
from course_explorer.db.session import session_scope
from course_explorer.enums import (
    InferredCoverageState,
    InferredProducerKind,
)
from course_explorer.prerequisite.domain import (
    AndRequirement,
    CourseRequirement,
    EquivalenceActivityReconciliation,
    InferredPrerequisiteCategory,
    InferredPublicationAction,
    InferredSetCoverage,
    InferredSetPublication,
    PrerequisiteOrigin,
)
from course_explorer.prerequisite.equivalence_repository import InferredEquivalenceRepository
from course_explorer.prerequisite.repository import InferredPrerequisiteRepository
from tests.prerequisite._equivalence_repository_support import (
    GENERATED_AT,
    INPUT_HASH,
    _activate_all_four,
    _group_count,
    _inference,
    _member,
    _member_count,
    _members,
    _publication,
)
from tests.prerequisite.conftest import PrerequisiteCatalogueSeed

pytestmark = [
    pytest.mark.integration,
]


def test_equivalence_publish_read_replace_and_identical_retry_are_atomic_and_idempotent(
    database: tuple[Engine, object],
    prerequisite_catalogue: PrerequisiteCatalogueSeed,
    set_prerequisite_course_activity,
) -> None:
    """Creation, symmetric reads, identical retry, and same-UUID replacement stay exact."""
    _, factory = database
    repository = InferredEquivalenceRepository(factory)
    seed = prerequisite_catalogue
    active_target = seed.active_target_group_id
    inactive_target = seed.inactive_target_group_id
    active_source = seed.active_source_group_id
    _activate_all_four(seed, set_prerequisite_course_activity)

    group_id = UUID(int=1)
    publication = _publication(
        group_id=group_id, members=_members(seed, active_target, inactive_target, active_source)
    ).model_copy(update={"producer_name": "test-fixture-ä"})
    created = repository.publish(publication)
    assert created.action is InferredPublicationAction.CREATED
    assert created.current_group.group_id == group_id
    assert [member.course_group_id for member in created.current_group.members] == sorted(
        [active_target, inactive_target, active_source]
    )
    original_published_at = created.current_group.published_at
    original_generated_at = created.current_group.generated_at
    original_payload_hash = created.current_group.payload_hash

    # Every member observes the identical group: membership is symmetric inside one group.
    for member_group_id in (active_target, inactive_target, active_source):
        assert repository.read_for_member(member_group_id) == (created.current_group,)

    # The bulk reader agrees exactly with the singleton reader, deduplicates requested IDs, rejects
    # blanks and unknown identities, and returns {} for an empty request.
    bulk = repository.read_for_members((active_target, inactive_target, active_source))
    for member_group_id in (active_target, inactive_target, active_source):
        assert bulk[member_group_id] == repository.read_for_member(member_group_id)
    assert repository.read_for_members(()) == {}
    assert repository.read_for_members((active_target, active_target, active_target)) == {
        active_target: bulk[active_target]
    }
    with pytest.raises(ValueError):
        repository.read_for_members(("",))
    with pytest.raises(ValueError):
        repository.read_for_members(("absent-canonical-course",))

    retry = repository.publish(
        publication.model_copy(update={"generated_at": GENERATED_AT.replace(hour=13)})
    )
    assert retry.action is InferredPublicationAction.UNCHANGED
    assert retry.current_group.generated_at == original_generated_at
    assert retry.current_group.published_at == original_published_at
    assert retry.current_group.payload_hash == original_payload_hash

    replaced = repository.publish(
        publication.model_copy(update={"members": _members(seed, active_target, inactive_target)})
    )
    assert replaced.action is InferredPublicationAction.REPLACED
    assert replaced.current_group.group_id == group_id
    assert replaced.current_group.payload_hash != original_payload_hash
    assert [member.course_group_id for member in replaced.current_group.members] == sorted(
        [active_target, inactive_target]
    )

    assert _group_count(factory) == 1
    assert _member_count(factory) == 2
    assert repository.read_for_member(active_source) == ()
    # A known canonical course with no group gets an explicit empty bulk entry.
    assert repository.read_for_members((active_source,))[active_source] == ()

    # A changed stale-member replacement fails and leaves the group payload/member rows in place.
    with pytest.raises(ValueError):
        repository.publish(
            _publication(
                group_id=group_id,
                members=tuple(
                    sorted(
                        (
                            _member(seed, active_target),
                            _member(seed, active_source, activity_window_years=2),
                        ),
                        key=lambda member: member.course_group_id,
                    )
                ),
            )
        )
    read_after_failure = repository.read_for_member(active_target)
    assert read_after_failure == (replaced.current_group,)
    assert read_after_failure[0].payload_hash == replaced.current_group.payload_hash
    assert read_after_failure[0].generated_at == replaced.current_group.generated_at
    assert read_after_failure[0].published_at == replaced.current_group.published_at
    assert _group_count(factory) == 1
    assert _member_count(factory) == 2

    # An unevidenced INFERENCE replacement is rejected without persisted rows.
    with pytest.raises(ValueError):
        repository.publish(
            _publication(
                group_id=group_id,
                members=_members(seed, active_target, inactive_target),
                producer_kind=InferredProducerKind.INFERENCE,
                inference=_inference(evidenced=False),
            )
        )
    assert _group_count(factory) == 1
    assert _member_count(factory) == 2

    # Overlapping groups stay distinct. Exact membership never merges or closes transitively.
    second_group_id = uuid4()
    second_group = repository.publish(
        _publication(
            group_id=second_group_id, members=_members(seed, inactive_target, active_source)
        )
    )
    assert second_group.action is InferredPublicationAction.CREATED

    first_read = repository.read_for_member(active_target)
    assert len(first_read) == 1
    assert first_read[0].group_id == group_id
    assert {member.course_group_id for member in first_read[0].members} == {
        active_target,
        inactive_target,
    }
    shared_read = repository.read_for_member(inactive_target)
    assert {group.group_id for group in shared_read} == {group_id, second_group_id}
    source_read = repository.read_for_member(active_source)
    assert len(source_read) == 1
    assert source_read[0].group_id == second_group_id
    assert {member.course_group_id for member in source_read[0].members} == {
        inactive_target,
        active_source,
    }
    # The bulk reader keeps overlapping exact groups distinct and matches the singleton reads.
    overlap_bulk = repository.read_for_members((inactive_target, active_source))
    assert overlap_bulk[inactive_target] == shared_read
    assert overlap_bulk[active_source] == source_read
    # No merged/transitive synthetic group ever appears. Only the two exact published groups exist.
    assert not any(
        {member.course_group_id for member in group.members} == {active_target, active_source}
        for group in (*first_read, *shared_read, *source_read)
    )
    assert _group_count(factory) == 2
    assert _member_count(factory) == 4
    # The second publication leaves the first group payload identical.
    assert repository.read_for_member(active_target)[0].payload_hash == (
        replaced.current_group.payload_hash
    )


def test_equivalence_read_fails_loudly_on_stale_or_malformed_stored_group(
    database: tuple[Engine, object],
    prerequisite_catalogue: PrerequisiteCatalogueSeed,
    set_prerequisite_course_activity,
) -> None:
    """Read never returns a partial or fabricated group from stale or malformed durable state."""
    _, factory = database
    repository = InferredEquivalenceRepository(factory)
    seed = prerequisite_catalogue
    active_target = seed.active_target_group_id
    active_source = seed.active_source_group_id
    group_id = uuid4()

    original_publication = _publication(
        group_id=group_id, members=_members(seed, active_target, active_source)
    )
    repository.publish(original_publication)

    # Deleting one member row leaves a durable one-member group. The domain member shape refuses it
    # before any partial group can be returned.
    with session_scope(factory) as session:
        source_course_id = session.scalar(select(Course.id).where(Course.group_id == active_source))
        session.execute(
            delete(InferredEquivalenceGroupMember).where(
                InferredEquivalenceGroupMember.equivalence_group_id == group_id,
                InferredEquivalenceGroupMember.course_id == source_course_id,
            )
        )
    with pytest.raises(ValueError):
        repository.read_for_member(active_target)
    with pytest.raises(ValueError):
        repository.read_for_members((active_target,))

    # Restore both members by publishing again with a different input hash.
    repository.publish(original_publication.model_copy(update={"input_hash": "b" * 64}))

    # Make one member canonical course inactive: the strict test read refuses the stale group.
    set_prerequisite_course_activity(
        active_source,
        False,
        seed.activity_as_of_academic_year_start,
        seed.activity_window_years,
    )
    with pytest.raises(ValueError):
        repository.read_for_member(active_target)
    with pytest.raises(ValueError):
        repository.read_for_members((active_target,))
    set_prerequisite_course_activity(
        active_source,
        True,
        seed.activity_as_of_academic_year_start,
        seed.activity_window_years,
    )

    # A malformed stored inference payload fails loudly instead of fabricating provenance.
    with session_scope(factory) as session:
        session.execute(
            update(InferredEquivalenceGroup)
            .where(InferredEquivalenceGroup.id == group_id)
            .values(inference={"confidence": "not-a-decimal"})
        )
    with pytest.raises(ValueError):
        repository.read_for_member(active_target)
    with pytest.raises(ValueError):
        repository.read_for_members((active_target,))


def test_equivalence_reconcile_republishes_survivors_prunes_small_groups_and_is_idempotent(
    database: tuple[Engine, object],
    prerequisite_catalogue: PrerequisiteCatalogueSeed,
    set_prerequisite_course_activity,
) -> None:
    """Survivors retain group identity. Smaller groups are pruned and a rerun is a no-op."""
    _, factory = database
    repository = InferredEquivalenceRepository(factory)
    seed = prerequisite_catalogue
    active_target = seed.active_target_group_id
    inactive_target = seed.inactive_target_group_id
    active_source = seed.active_source_group_id
    inactive_source = seed.inactive_source_group_id
    _activate_all_four(seed, set_prerequisite_course_activity)

    surviving_group_id = uuid4()
    removed_group_id = uuid4()
    surviving = repository.publish(
        _publication(
            group_id=surviving_group_id,
            members=_members(seed, active_target, inactive_target, active_source),
        )
    )
    removed = repository.publish(
        _publication(
            group_id=removed_group_id, members=_members(seed, active_source, inactive_source)
        )
    )
    assert removed.action is InferredPublicationAction.CREATED

    # A per-target inferred expression set proves reconciliation never touches that store.
    inferred = InferredPrerequisiteRepository(factory).publish(
        InferredSetPublication(
            target_group_id=active_target,
            activity_as_of_academic_year_start=seed.activity_as_of_academic_year_start,
            activity_window_years=seed.activity_window_years,
            producer_kind=InferredProducerKind.TEST,
            producer_name="test-fixture",
            producer_version="1",
            input_hash=INPUT_HASH,
            coverage_state=InferredCoverageState.COMPLETE,
            coverage=InferredSetCoverage(
                eligible_source_count=1, processed_source_count=1, accepted_source_count=1
            ),
            expression=AndRequirement(
                type="and",
                origin=PrerequisiteOrigin.INFERRED,
                inferred_category=InferredPrerequisiteCategory.REQUIRED,
                inference=_inference(),
                children=(
                    CourseRequirement(
                        type="course",
                        origin=PrerequisiteOrigin.INFERRED,
                        inferred_category=InferredPrerequisiteCategory.REQUIRED,
                        course_group_id=active_source,
                        inference=_inference(),
                    ),
                ),
            ),
            generated_at=GENERATED_AT,
        )
    )
    with session_scope(factory) as session:
        course_count = session.scalar(select(func.count()).select_from(Course))

    set_prerequisite_course_activity(
        active_source,
        False,
        seed.activity_as_of_academic_year_start,
        seed.activity_window_years,
    )

    reconciliation = repository.reconcile_activity()
    assert reconciliation == EquivalenceActivityReconciliation(
        updated_group_ids=(surviving_group_id,),
        removed_group_ids=(removed_group_id,),
    )

    survivors = repository.read_for_member(active_target)
    assert len(survivors) == 1
    assert survivors[0].group_id == surviving_group_id
    assert survivors[0].generated_at == surviving.current_group.generated_at
    assert survivors[0].input_hash == surviving.current_group.input_hash
    assert survivors[0].producer_name == surviving.current_group.producer_name
    assert [member.course_group_id for member in survivors[0].members] == sorted(
        [active_target, inactive_target]
    )
    assert survivors[0].payload_hash != surviving.current_group.payload_hash
    assert survivors[0].published_at >= surviving.current_group.published_at
    assert repository.read_for_member(inactive_source) == ()

    with session_scope(factory) as session:
        assert session.scalar(select(func.count()).select_from(Course)) == course_count
        assert session.scalar(select(func.count()).select_from(InferredPrerequisiteSet)) == 1
        stored_set = session.scalar(select(InferredPrerequisiteSet))
        assert stored_set is not None
        assert stored_set.id == inferred.current_set.set_id
        inactive = session.scalar(select(Course).where(Course.group_id == active_source))
        assert inactive is not None
        assert inactive.is_active is False

    assert repository.reconcile_activity() == EquivalenceActivityReconciliation(
        updated_group_ids=(), removed_group_ids=()
    )
    assert _group_count(factory) == 1
    assert _member_count(factory) == 2


def test_withdraw_absent_inference_groups_preserves_test_and_is_idempotent(
    database: tuple[Engine, object], prerequisite_catalogue: PrerequisiteCatalogueSeed
) -> None:
    """Only inference-owned groups absent from the keep set are withdrawn. Test rows hold."""
    _, factory = database
    repository = InferredEquivalenceRepository(factory)
    seed = prerequisite_catalogue
    inference_group_id = uuid4()
    test_group_id = uuid4()
    active_target = seed.active_target_group_id
    active_source = seed.active_source_group_id

    repository.publish(
        _publication(
            group_id=inference_group_id,
            members=_members(seed, active_target, active_source),
            producer_kind=InferredProducerKind.INFERENCE,
            inference=_inference(evidenced=True),
        )
    )
    repository.publish(
        _publication(group_id=test_group_id, members=_members(seed, active_target, active_source))
    )
    assert _group_count(factory) == 2

    # A malformed or repeated keep identity is rejected before any mutation.
    with pytest.raises(ValueError):
        repository.withdraw_absent_inference_groups(("not-a-uuid",))  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        repository.withdraw_absent_inference_groups((inference_group_id, inference_group_id))
    assert _group_count(factory) == 2

    # Keeping both identities removes nothing.
    assert repository.withdraw_absent_inference_groups((inference_group_id, test_group_id)) == ()
    assert _group_count(factory) == 2

    # Dropping the inference group leaves the test-owned group and its members untouched.
    assert repository.withdraw_absent_inference_groups((test_group_id,)) == (inference_group_id,)
    assert _group_count(factory) == 1
    assert _member_count(factory) == 2
    assert [group.group_id for group in repository.read_for_member(active_target)] == [
        test_group_id
    ]

    # Repeated or empty keep sets never remove the surviving test group.
    assert repository.withdraw_absent_inference_groups(()) == ()
    assert repository.withdraw_absent_inference_groups((test_group_id,)) == ()
    assert _group_count(factory) == 1
    assert _member_count(factory) == 2


def test_inference_member_generation_context_retained_with_strict_publication_and_test_reads(
    database: tuple[Engine, object],
    prerequisite_catalogue: PrerequisiteCatalogueSeed,
    set_prerequisite_course_activity,
) -> None:
    """Active inference members keep their stored context. Test reads and subsequent writes stay strict."""
    _, factory = database
    repository = InferredEquivalenceRepository(factory)
    seed = prerequisite_catalogue
    active_target = seed.active_target_group_id
    active_source = seed.active_source_group_id
    inactive_target = seed.inactive_target_group_id
    inactive_source = seed.inactive_source_group_id
    _activate_all_four(seed, set_prerequisite_course_activity)

    inference_group_id = uuid4()
    test_group_id = uuid4()
    repository.publish(
        _publication(
            group_id=inference_group_id,
            members=_members(seed, active_target, active_source),
            producer_kind=InferredProducerKind.INFERENCE,
            inference=_inference(evidenced=True),
        )
    )
    repository.publish(
        _publication(
            group_id=test_group_id, members=_members(seed, inactive_target, inactive_source)
        )
    )
    for group_id in (active_target, active_source, inactive_target, inactive_source):
        set_prerequisite_course_activity(group_id, True, 2027, 3)

    # The active inference group is retained through the rollover. The test group read is strict.
    retained = repository.read_for_member(active_target)
    assert len(retained) == 1
    assert retained[0].group_id == inference_group_id
    with pytest.raises(ValueError):
        repository.read_for_member(inactive_target)

    # Reconcile keeps the inference group and removes only the mismatched test group.
    reconciliation = repository.reconcile_activity()
    assert reconciliation.removed_group_ids == (test_group_id,)
    assert inference_group_id in {
        group.group_id for group in repository.read_for_member(active_target)
    }

    # A strict inference publication refuses a stale generation context.
    with pytest.raises(ValueError):
        repository.publish(
            _publication(
                group_id=uuid4(),
                members=_members(seed, active_target, active_source),
                producer_kind=InferredProducerKind.INFERENCE,
                inference=_inference(evidenced=True),
            )
        )

    # Inactive trimming removes the retained inference group once it drops below two members.
    set_prerequisite_course_activity(active_source, False, 2027, 3)
    removed = repository.reconcile_activity()
    assert inference_group_id in removed.removed_group_ids
    assert repository.read_for_member(active_target) == ()
