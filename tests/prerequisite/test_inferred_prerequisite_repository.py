"""Opt-in PostgreSQL publication/read/idempotency tests for current inferred sets."""

import pytest
from sqlalchemy import Engine, func, select

from course_explorer.db.models import (
    Course,
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
    InferredActivityReconciliation,
    InferredPrerequisiteCategory,
    InferredPublicationAction,
    InferredReadState,
    InferredSetCoverage,
    OfficialPrerequisiteKind,
    PrerequisiteOrigin,
    dump_prerequisite_expression,
)
from course_explorer.prerequisite.repository import InferredPrerequisiteRepository
from tests.prerequisite._set_repository_support import (
    GENERATED_AT,
    INPUT_HASH,
    _metadata,
    _publication,
    _target_expression,
)
from tests.prerequisite.conftest import PrerequisiteCatalogueSeed

pytestmark = [
    pytest.mark.integration,
]


def test_publish_read_replace_and_identical_retry_are_atomic_and_idempotent(
    database: tuple[Engine, object], prerequisite_catalogue: PrerequisiteCatalogueSeed
) -> None:
    """Creation, identical retry, and changed replacement keep exactly one current row."""
    engine, factory = database
    repository = InferredPrerequisiteRepository(factory)
    seed = prerequisite_catalogue

    publication = _publication(seed).model_copy(update={"producer_name": "test-fixture-ä"})
    created = repository.publish(publication)
    assert created.action is InferredPublicationAction.CREATED
    original_id = created.current_set.set_id
    original_published_at = created.current_set.published_at
    original_generated_at = created.current_set.generated_at

    first_read = repository.read(seed.active_target_group_id)
    assert first_read.state is InferredReadState.CURRENT
    assert first_read.current_set is not None
    assert first_read.current_set.expression == _target_expression(seed.active_source_group_id)

    retry = repository.publish(
        publication.model_copy(update={"generated_at": GENERATED_AT.replace(hour=13)})
    )
    assert retry.action is InferredPublicationAction.UNCHANGED
    assert retry.current_set.set_id == original_id
    assert retry.current_set.generated_at == original_generated_at
    assert retry.current_set.published_at == original_published_at

    replaced = repository.publish(
        publication.model_copy(
            update={
                "coverage": InferredSetCoverage(
                    eligible_source_count=2, processed_source_count=2, accepted_source_count=1
                )
            }
        )
    )
    assert replaced.action is InferredPublicationAction.REPLACED
    assert replaced.current_set.set_id == original_id
    assert replaced.current_set.payload_hash != created.current_set.payload_hash

    with session_scope(factory) as session:
        assert session.scalar(select(func.count()).select_from(InferredPrerequisiteSet)) == 1
    read_after = repository.read(seed.active_target_group_id)
    assert read_after.current_set is not None
    assert read_after.current_set.coverage.eligible_source_count == 2

    # A rejected changed publication with an unknown source rolls back and leaves the stored
    # current row with its exact identity, hash, timestamp, and row count.
    with pytest.raises(ValueError):
        repository.publish(
            _publication(
                seed,
                expression=CourseRequirement(
                    type="course",
                    origin=PrerequisiteOrigin.INFERRED,
                    inferred_category=InferredPrerequisiteCategory.REQUIRED,
                    course_group_id="not-a-canonical-course",
                    inference=_metadata(),
                ),
            )
        )
    read_after_failure = repository.read(seed.active_target_group_id)
    assert read_after_failure.state is InferredReadState.CURRENT
    assert read_after_failure.current_set is not None
    assert read_after_failure.current_set.set_id == replaced.current_set.set_id
    assert read_after_failure.current_set.payload_hash == replaced.current_set.payload_hash
    assert read_after_failure.current_set.generated_at == replaced.current_set.generated_at
    with session_scope(factory) as session:
        assert session.scalar(select(func.count()).select_from(InferredPrerequisiteSet)) == 1


def test_inferred_categories_round_trip_and_change_canonical_payload_hash(
    database: tuple[Engine, object], prerequisite_catalogue: PrerequisiteCatalogueSeed
) -> None:
    """Required/recommended categories survive publication/read and change the canonical hash."""
    _, factory = database
    repository = InferredPrerequisiteRepository(factory)
    seed = prerequisite_catalogue

    # Both publications use the same active+inactive source expression and complete coverage, so
    # only the occurrence category differs between their canonical payloads.
    sources = (seed.active_source_group_id, seed.inactive_source_group_id)
    coverage = InferredSetCoverage(
        eligible_source_count=2, processed_source_count=2, accepted_source_count=2
    )
    required = repository.publish(
        _publication(
            seed,
            expression=_target_expression(*sources, category=InferredPrerequisiteCategory.REQUIRED),
            coverage=coverage,
        )
    )
    assert required.action is InferredPublicationAction.CREATED
    assert (
        required.current_set.expression.inferred_category is InferredPrerequisiteCategory.REQUIRED
    )
    first_read = repository.read(seed.active_target_group_id)
    assert first_read.state is InferredReadState.CURRENT
    assert first_read.current_set is not None
    original_hash = first_read.current_set.payload_hash
    assert first_read.current_set.expression == _target_expression(*sources)
    assert all(
        child.inferred_category is InferredPrerequisiteCategory.REQUIRED
        for child in first_read.current_set.expression.children
    )

    # Replacing only the occurrence category changes the hash.
    recommended = repository.publish(
        _publication(
            seed,
            expression=_target_expression(
                *sources, category=InferredPrerequisiteCategory.RECOMMENDED
            ),
            coverage=coverage,
        )
    )
    assert recommended.action is InferredPublicationAction.REPLACED
    assert recommended.current_set.payload_hash != original_hash

    read_back = repository.read(seed.active_target_group_id)
    assert read_back.state is InferredReadState.CURRENT
    assert read_back.current_set is not None
    assert read_back.current_set.payload_hash == recommended.current_set.payload_hash
    assert (
        read_back.current_set.expression.inferred_category
        is InferredPrerequisiteCategory.RECOMMENDED
    )
    assert all(
        child.inferred_category is InferredPrerequisiteCategory.RECOMMENDED
        for child in read_back.current_set.expression.children
    )

    # An inactive target is rejected without creating or replacing a set.
    with pytest.raises(ValueError):
        repository.publish(_publication(seed, target_group_id=seed.inactive_target_group_id))
    with session_scope(factory) as session:
        assert session.scalar(select(func.count()).select_from(InferredPrerequisiteSet)) == 1


def test_read_distinguishes_unavailable_complete_empty_partial_and_stale_context(
    database: tuple[Engine, object],
    prerequisite_catalogue: PrerequisiteCatalogueSeed,
    set_prerequisite_course_activity,
) -> None:
    """Unavailable, complete-empty, partial, and stale states stay distinct."""
    _, factory = database
    repository = InferredPrerequisiteRepository(factory)
    seed = prerequisite_catalogue

    absent = repository.read(seed.active_target_group_id)
    assert absent.state is InferredReadState.UNAVAILABLE
    assert absent.current_set is None

    empty = repository.publish(
        _publication(
            seed,
            expression=None,
            coverage=InferredSetCoverage(
                eligible_source_count=0, processed_source_count=0, accepted_source_count=0
            ),
        )
    )
    assert empty.action is InferredPublicationAction.CREATED
    empty_read = repository.read(seed.active_target_group_id)
    assert empty_read.state is InferredReadState.CURRENT
    assert empty_read.current_set is not None
    assert empty_read.current_set.expression is None

    partial = repository.publish(
        _publication(
            seed,
            expression=None,
            coverage=InferredSetCoverage(
                eligible_source_count=3, processed_source_count=1, accepted_source_count=0
            ),
            coverage_state=InferredCoverageState.PARTIAL,
        )
    )
    assert partial.action is InferredPublicationAction.REPLACED
    partial_read = repository.read(seed.active_target_group_id)
    assert partial_read.state is InferredReadState.CURRENT
    assert partial_read.current_set is not None
    assert partial_read.current_set.coverage_state is InferredCoverageState.PARTIAL
    assert partial_read.current_set.coverage.processed_source_count == 1
    assert partial_read.current_set.expression is None

    repository.publish(_publication(seed))
    set_prerequisite_course_activity(seed.active_target_group_id, True, 2027, 3)
    stale = repository.read(seed.active_target_group_id)
    assert stale.state is InferredReadState.STALE_ACTIVITY_CONTEXT
    assert stale.current_set is None
    assert stale.stored_activity_as_of_academic_year_start == 2026
    assert stale.stored_activity_window_years == 3


def test_publish_rejects_official_unsupported_unknown_self_or_unevidenced_inference_nodes(
    database: tuple[Engine, object], prerequisite_catalogue: PrerequisiteCatalogueSeed
) -> None:
    """One shared trust boundary rejects every non-inferred or unevidenced node shape."""
    _, factory = database
    repository = InferredPrerequisiteRepository(factory)
    seed = prerequisite_catalogue

    official_leaf = CourseRequirement(
        type="course",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.COMPULSORY,
        course_group_id=seed.active_source_group_id,
    )
    with pytest.raises(ValueError):
        repository.publish(_publication(seed, expression=official_leaf))

    # The origin gate applies at every occurrence: an official leaf nested inside an otherwise
    # valid inferred AND wrapper is refused by the same traversal.
    official_leaf_in_inferred_and = AndRequirement(
        type="and",
        origin=PrerequisiteOrigin.INFERRED,
        inferred_category=InferredPrerequisiteCategory.REQUIRED,
        inference=_metadata(),
        children=(official_leaf,),
    )
    with pytest.raises(ValueError):
        repository.publish(_publication(seed, expression=official_leaf_in_inferred_and))

    unsupported = AndRequirement(
        type="and",
        origin=PrerequisiteOrigin.INFERRED,
        inferred_category=InferredPrerequisiteCategory.REQUIRED,
        inference=_metadata(),
        children=(
            CourseRequirement(
                type="course",
                origin=PrerequisiteOrigin.INFERRED,
                inferred_category=InferredPrerequisiteCategory.REQUIRED,
                course_group_id=seed.active_source_group_id,
                inference=_metadata(),
            ),
        ),
    )
    unsupported_with_module = dump_prerequisite_expression(unsupported)
    unsupported_with_module["children"].append(
        {
            "type": "module",
            "origin": "official",
            "official_kind": "module_rule",
            "inference": None,
            "module_group_id": "module-a",
        }
    )
    from course_explorer.prerequisite.domain import parse_prerequisite_expression

    with pytest.raises(ValueError):
        repository.publish(
            _publication(seed, expression=parse_prerequisite_expression(unsupported_with_module))
        )

    unknown_leaf = CourseRequirement(
        type="course",
        origin=PrerequisiteOrigin.INFERRED,
        inferred_category=InferredPrerequisiteCategory.REQUIRED,
        course_group_id="not-a-canonical-course",
        inference=_metadata(),
    )
    with pytest.raises(ValueError):
        repository.publish(_publication(seed, expression=unknown_leaf))

    self_leaf = CourseRequirement(
        type="course",
        origin=PrerequisiteOrigin.INFERRED,
        inferred_category=InferredPrerequisiteCategory.REQUIRED,
        course_group_id=seed.active_target_group_id,
        inference=_metadata(),
    )
    with pytest.raises(ValueError):
        repository.publish(_publication(seed, expression=self_leaf))

    unevidenced = _target_expression(seed.active_source_group_id, evidenced=False)
    with pytest.raises(ValueError):
        repository.publish(
            _publication(seed, expression=unevidenced, producer_kind=InferredProducerKind.INFERENCE)
        )

    accepted_mismatch = _target_expression(seed.active_source_group_id)
    with pytest.raises(ValueError):
        repository.publish(
            _publication(
                seed,
                expression=accepted_mismatch,
                coverage=InferredSetCoverage(
                    eligible_source_count=1, processed_source_count=1, accepted_source_count=0
                ),
            )
        )
    with pytest.raises(ValueError):
        repository.publish(
            _publication(
                seed,
                expression=None,
                coverage=InferredSetCoverage(
                    eligible_source_count=1, processed_source_count=1, accepted_source_count=1
                ),
            )
        )

    # The canonical-target boundary is distinct from the source lookup above: an unknown target is
    # refused before any write, and the read path refuses it too.
    with pytest.raises(ValueError):
        repository.publish(_publication(seed, target_group_id="missing-target"))
    with pytest.raises(ValueError):
        repository.read("missing-target")

    # Every rejected publication above left the inferred-set store untouched.
    with session_scope(factory) as session:
        assert session.scalar(select(func.count()).select_from(InferredPrerequisiteSet)) == 0


def test_reconcile_activity_removes_only_stale_final_sets(
    database: tuple[Engine, object],
    prerequisite_catalogue: PrerequisiteCatalogueSeed,
    set_prerequisite_course_activity,
) -> None:
    """Reconciliation deletes stale inferred rows and leaves course rows untouched."""
    _, factory = database
    repository = InferredPrerequisiteRepository(factory)
    seed = prerequisite_catalogue

    repository.publish(_publication(seed, target_group_id=seed.active_target_group_id))
    # Publish the second target while it is active, then make it inactive so
    # reconciliation proves it removes only stale final sets.
    set_prerequisite_course_activity(seed.inactive_target_group_id, True, 2026, 3)
    repository.publish(_publication(seed, target_group_id=seed.inactive_target_group_id))
    set_prerequisite_course_activity(seed.inactive_target_group_id, False, 2026, 3)

    with session_scope(factory) as session:
        course_count = session.scalar(select(func.count()).select_from(Course))

    removed = repository.reconcile_activity()
    assert removed == InferredActivityReconciliation(
        removed_target_group_ids=(seed.inactive_target_group_id,)
    )
    with session_scope(factory) as session:
        remaining = list(session.scalars(select(InferredPrerequisiteSet.target_course_id)))
        assert session.scalar(select(func.count()).select_from(Course)) == course_count
        assert len(remaining) == 1

    still_current = repository.read(seed.active_target_group_id)
    assert still_current.state is InferredReadState.CURRENT
    with session_scope(factory) as session:
        inactive = session.scalar(
            select(Course).where(Course.group_id == seed.inactive_target_group_id)
        )
        assert inactive is not None
        assert inactive.is_active is False
        assert inactive.activity_as_of_academic_year_start == 2026
        assert inactive.activity_window_years == 3


def test_reconcile_activity_with_current_input_hashes_does_not_touch_test_sets(
    database: tuple[Engine, object],
    prerequisite_catalogue: PrerequisiteCatalogueSeed,
    set_prerequisite_course_activity,
) -> None:
    """An explicit policy map removes only non-current inference sets, never test rows."""
    _, factory = database
    repository = InferredPrerequisiteRepository(factory)
    seed = prerequisite_catalogue
    target = seed.active_target_group_id
    test_target = seed.inactive_target_group_id
    set_prerequisite_course_activity(
        test_target, True, seed.activity_as_of_academic_year_start, seed.activity_window_years
    )
    repository.publish(_publication(seed, target_group_id=test_target))
    repository.publish(
        _publication(
            seed,
            producer_kind=InferredProducerKind.INFERENCE,
            expression=_target_expression(seed.active_source_group_id, evidenced=True),
        )
    )

    # A matching current identity keeps the inference set, and a named test target is not touched.
    assert repository.reconcile_activity(
        current_inference_input_hashes={target: INPUT_HASH, test_target: None}
    ) == InferredActivityReconciliation(removed_target_group_ids=())
    assert repository.read(target).state is InferredReadState.CURRENT
    assert repository.read(test_target).state is InferredReadState.CURRENT

    # A changed identity removes only the inference-produced set for the named target.
    assert repository.reconcile_activity(
        current_inference_input_hashes={target: "b" * 64, test_target: None}
    ) == InferredActivityReconciliation(removed_target_group_ids=(target,))
    assert repository.read(target).state is InferredReadState.UNAVAILABLE
    assert repository.read(test_target).state is InferredReadState.CURRENT

    # An invalid map value is rejected before any mutation.
    repository.publish(
        _publication(
            seed,
            producer_kind=InferredProducerKind.INFERENCE,
            expression=_target_expression(seed.active_source_group_id, evidenced=True),
        )
    )
    with pytest.raises(ValueError):
        repository.reconcile_activity(current_inference_input_hashes={target: "not-a-hash"})
    assert repository.read(target).state is InferredReadState.CURRENT

    # The default None preserves the activity-only behavior.
    assert repository.reconcile_activity() == InferredActivityReconciliation(
        removed_target_group_ids=()
    )
    assert repository.read(target).state is InferredReadState.CURRENT
    assert repository.read(test_target).state is InferredReadState.CURRENT


def test_inference_generation_context_retained_while_test_context_and_inactive_targets_reconcile(
    database: tuple[Engine, object],
    prerequisite_catalogue: PrerequisiteCatalogueSeed,
    set_prerequisite_course_activity,
) -> None:
    """Active inference rows keep their stored context. Test rows and inactive targets reconcile."""
    _, factory = database
    repository = InferredPrerequisiteRepository(factory)
    seed = prerequisite_catalogue
    target = seed.active_target_group_id

    repository.publish(
        _publication(
            seed,
            producer_kind=InferredProducerKind.INFERENCE,
            expression=_target_expression(seed.active_source_group_id, evidenced=True),
        )
    )
    set_prerequisite_course_activity(target, True, 2027, 3)

    # The current read, scoped inference-target list and reconciliation all retain the active
    # inference row even though the stored generation context differs from the live course.
    retained = repository.read(target)
    assert retained.state is InferredReadState.CURRENT
    assert retained.current_set is not None
    assert retained.current_set.activity_as_of_academic_year_start == 2026
    assert target in repository.list_inference_target_group_ids()
    assert repository.reconcile_activity() == InferredActivityReconciliation(
        removed_target_group_ids=()
    )
    assert repository.read(target).state is InferredReadState.CURRENT

    # A strict publication refuses a stale generation context for either producer.
    with pytest.raises(ValueError):
        repository.publish(
            _publication(
                seed,
                producer_kind=InferredProducerKind.INFERENCE,
                expression=_target_expression(seed.active_source_group_id, evidenced=True),
            )
        )

    # A test-produced row requires exact context equality and is pruned on rollover.
    test_target = seed.inactive_target_group_id
    set_prerequisite_course_activity(test_target, True, 2026, 3)
    repository.publish(_publication(seed, target_group_id=test_target))
    set_prerequisite_course_activity(test_target, True, 2027, 3)
    assert repository.read(test_target).state is InferredReadState.STALE_ACTIVITY_CONTEXT
    removed_test = repository.reconcile_activity()
    assert test_target in removed_test.removed_target_group_ids
    assert repository.read(target).state is InferredReadState.CURRENT

    # An inactive target of either producer reconciles away.
    set_prerequisite_course_activity(target, False, 2027, 3)
    removed_inactive = repository.reconcile_activity()
    assert target in removed_inactive.removed_target_group_ids
    assert repository.read(target).state is InferredReadState.UNAVAILABLE
