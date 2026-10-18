"""Truth-table and candidate-semantics contracts for prerequisite satisfaction."""

from __future__ import annotations

from decimal import Decimal

from course_explorer.prerequisite.domain import (
    AndRequirement,
    ComposedAndRole,
    CourseCountRequirement,
    CreditRequirement,
    OfficialPrerequisiteKind,
    OrRequirement,
    PrerequisiteOrigin,
    UnresolvedPrerequisiteReason,
    UnresolvedRequirement,
)
from course_explorer.prerequisite.satisfaction import (
    PrerequisiteSatisfactionSession,
    PrerequisiteSatisfactionState,
    evaluate_prerequisite_expression,
    evaluate_prerequisite_satisfaction,
)
from tests.prerequisite._path_support import (
    course_summary,
    inferred_course,
    make_compilation,
    module_cardinality,
    official_course,
)
from tests.prerequisite._path_support import (
    official_and as official_option,
)


def test_canonical_completion_identity_satisfies_repeated_leaves() -> None:
    """Repeated canonical leaves share one completion identity."""
    root = course_summary("root")
    requirements = AndRequirement(
        type="and",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.COMPULSORY,
        children=(official_course("a"), official_course("a"), official_course("b")),
    )
    compilation = make_compilation(
        root,
        requirements,
        (course_summary("a"), course_summary("b")),
    )

    evaluation = evaluate_prerequisite_satisfaction(
        compilation.tree,
        ["b", "zzz-unrelated", "a", "a"],
    )
    # Caller input normalizes to one sorted unique canonical tuple. Unrelated IDs are retained.
    assert evaluation.basis_group_ids == ("a", "b", "zzz-unrelated")
    assert evaluation.requirements_state is PrerequisiteSatisfactionState.SATISFIED
    assert evaluation.root_group_id == "root"

    # Ordering of caller input never changes the evaluation.
    reversed_input = evaluate_prerequisite_satisfaction(
        compilation.tree,
        ["a", "b", "zzz-unrelated"],
    )
    assert reversed_input == evaluation

    # Public credit/count wrappers keep the same canonical witness identity. AND(a, a, b) is two
    # distinct courses and ten credits, so exact count 2 and exact credits 10 hold and count 3 not.
    basis = ["a", "b"]
    exact_count_two = CourseCountRequirement(
        type="course_count",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.MODULE_RULE,
        count_min=2,
        count_max=2,
        child=requirements,
    )
    assert (
        evaluate_prerequisite_expression(compilation.tree, exact_count_two, basis)
        is PrerequisiteSatisfactionState.SATISFIED
    )
    exact_count_three = CourseCountRequirement(
        type="course_count",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.MODULE_RULE,
        count_min=3,
        count_max=3,
        child=requirements,
    )
    assert (
        evaluate_prerequisite_expression(compilation.tree, exact_count_three, basis)
        is PrerequisiteSatisfactionState.UNSATISFIED
    )
    exact_ten_credits = CreditRequirement(
        type="credits",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.MODULE_RULE,
        credits_min=Decimal("10"),
        credits_max=Decimal("10"),
        child=requirements,
    )
    assert (
        evaluate_prerequisite_expression(compilation.tree, exact_ten_credits, basis)
        is PrerequisiteSatisfactionState.SATISFIED
    )

    # The request-local session shares one fixed basis/completed context across several subtree
    # evaluations: repeated leaves, exact count/credit wrappers and repeated calls keep their
    # explicit public states.
    session = PrerequisiteSatisfactionSession(compilation.tree, basis)
    assert session.evaluate(requirements) is PrerequisiteSatisfactionState.SATISFIED
    for index, expression in enumerate(requirements.children):
        assert session.evaluate(expression) == session.evaluate(
            expression, occurrence_id=f"r.{index}"
        )
    assert session.evaluate(exact_count_two) is PrerequisiteSatisfactionState.SATISFIED
    assert session.evaluate(exact_count_three) is PrerequisiteSatisfactionState.UNSATISFIED
    assert session.evaluate(exact_ten_credits) is PrerequisiteSatisfactionState.SATISFIED
    assert session.evaluate(None) is PrerequisiteSatisfactionState.SATISFIED
    assert session.evaluate(exact_count_two) is PrerequisiteSatisfactionState.SATISFIED

    # A cardinality over two positions both naming one course is one variable, so the witness is one
    # course and five credits: exact count 1 passes and exact count 2 fails on the position/witness
    # distinction.
    positions = module_cardinality(2, 2, "a", "a")
    positions_tree = make_compilation(root, positions, (course_summary("a"),))
    exact_one_course = CourseCountRequirement(
        type="course_count",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.MODULE_RULE,
        count_min=1,
        count_max=1,
        child=positions,
    )
    assert (
        evaluate_prerequisite_expression(positions_tree.tree, exact_one_course, ["a"])
        is PrerequisiteSatisfactionState.SATISFIED
    )
    exact_two_courses = CourseCountRequirement(
        type="course_count",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.MODULE_RULE,
        count_min=2,
        count_max=2,
        child=positions,
    )
    assert (
        evaluate_prerequisite_expression(positions_tree.tree, exact_two_courses, ["a"])
        is PrerequisiteSatisfactionState.UNSATISFIED
    )

    # The same session distinguishes one canonical witness from two positions naming it.
    positions_session = PrerequisiteSatisfactionSession(positions_tree.tree, ["a"])
    assert positions_session.evaluate(exact_one_course) is PrerequisiteSatisfactionState.SATISFIED
    assert (
        positions_session.evaluate(exact_two_courses) is PrerequisiteSatisfactionState.UNSATISFIED
    )


def test_logical_states_follow_the_already_filtered_compilation() -> None:
    """AND/OR truth tables are exact, a rootless tree is satisfied, and no policy is re-applied."""
    root = course_summary("root")

    rootless = make_compilation(root, None, ())
    rootless_evaluation = evaluate_prerequisite_satisfaction(rootless.tree, [])
    assert rootless_evaluation.requirements_state is PrerequisiteSatisfactionState.SATISFIED

    and_tree = make_compilation(
        root, official_option("a", "b"), (course_summary("a"), course_summary("b"))
    )
    and_evaluation = evaluate_prerequisite_satisfaction(and_tree.tree, ["a"])
    assert and_evaluation.requirements_state is PrerequisiteSatisfactionState.UNSATISFIED

    or_requirements = OrRequirement(
        type="or",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.COMPULSORY,
        children=(official_course("a"), official_course("b")),
    )
    or_tree = make_compilation(root, or_requirements, (course_summary("a"), course_summary("b")))
    assert (
        evaluate_prerequisite_satisfaction(or_tree.tree, ["a"]).requirements_state
        is PrerequisiteSatisfactionState.SATISFIED
    )
    assert (
        evaluate_prerequisite_satisfaction(or_tree.tree, []).requirements_state
        is PrerequisiteSatisfactionState.UNSATISFIED
    )

    # An enabled recommended category is part of the supplied tree and therefore affects the result.
    recommended_tree = make_compilation(
        root,
        official_course("recommended", OfficialPrerequisiteKind.RECOMMENDED),
        (course_summary("recommended"),),
        include_recommended=True,
    )
    recommended_evaluation = evaluate_prerequisite_satisfaction(
        recommended_tree.tree, ["recommended"]
    )
    assert recommended_evaluation.include_recommended is True
    assert recommended_evaluation.include_inferred is False
    assert recommended_evaluation.requirements_state is PrerequisiteSatisfactionState.SATISFIED

    inferred_tree = make_compilation(
        root,
        inferred_course("inferred"),
        (course_summary("inferred"),),
        include_inferred=True,
    )
    inferred_evaluation = evaluate_prerequisite_satisfaction(inferred_tree.tree, [])
    assert inferred_evaluation.include_inferred is True
    assert inferred_evaluation.include_recommended is False
    assert inferred_evaluation.requirements_state is PrerequisiteSatisfactionState.UNSATISFIED

    # The public subtree evaluator shares the same fold: a selected leaf, a neutral None, an
    # unsatisfied leaf and an unresolved leaf keep their tri-state meanings without changing the
    # full-report result.
    subtree_tree = make_compilation(
        root, official_option("a", "b"), (course_summary("a"), course_summary("b"))
    )
    assert (
        evaluate_prerequisite_expression(subtree_tree.tree, official_course("a"), ["a"])
        is PrerequisiteSatisfactionState.SATISFIED
    )
    assert (
        evaluate_prerequisite_expression(subtree_tree.tree, None, ["a"])
        is PrerequisiteSatisfactionState.SATISFIED
    )
    assert (
        evaluate_prerequisite_expression(subtree_tree.tree, official_course("a"), [])
        is PrerequisiteSatisfactionState.UNSATISFIED
    )
    assert (
        evaluate_prerequisite_expression(
            subtree_tree.tree,
            UnresolvedRequirement(
                type="unresolved",
                origin=PrerequisiteOrigin.OFFICIAL,
                official_kind=OfficialPrerequisiteKind.COMPULSORY,
                reason=UnresolvedPrerequisiteReason.MISSING_COURSE,
            ),
            [],
        )
        is PrerequisiteSatisfactionState.UNRESOLVED
    )

    # One request-local session over the same tree/basis evaluates several subtrees and a rootless
    # None expression with the explicit states.
    subtree_session = PrerequisiteSatisfactionSession(subtree_tree.tree, ["a"])
    assert subtree_session.evaluate(official_course("a")) is PrerequisiteSatisfactionState.SATISFIED
    assert subtree_session.evaluate(None) is PrerequisiteSatisfactionState.SATISFIED
    assert (
        subtree_session.evaluate(
            UnresolvedRequirement(
                type="unresolved",
                origin=PrerequisiteOrigin.OFFICIAL,
                official_kind=OfficialPrerequisiteKind.COMPULSORY,
                reason=UnresolvedPrerequisiteReason.MISSING_COURSE,
            )
        )
        is PrerequisiteSatisfactionState.UNRESOLVED
    )

    # The observed unbounded 27-leaf cardinality must fold without enumerating selections, and nested
    # numeric wrappers keep exact reachable totals rather than treating them as an interval.
    leaves = tuple(f"leaf-{index:02d}" for index in range(27))
    cardinality = module_cardinality(1, None, *leaves)
    cardinality_tree = make_compilation(
        root, cardinality, tuple(course_summary(group_id) for group_id in leaves)
    )
    assert (
        evaluate_prerequisite_satisfaction(cardinality_tree.tree, leaves).requirements_state
        is PrerequisiteSatisfactionState.SATISFIED
    )
    exact_count_two = CourseCountRequirement(
        type="course_count",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.MODULE_RULE,
        count_min=2,
        count_max=2,
        child=cardinality,
    )
    exact_ten_credits = CreditRequirement(
        type="credits",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.MODULE_RULE,
        credits_min=Decimal("10"),
        credits_max=Decimal("10"),
        child=exact_count_two,
    )
    assert (
        evaluate_prerequisite_expression(cardinality_tree.tree, exact_ten_credits, leaves)
        is PrerequisiteSatisfactionState.SATISFIED
    )
    exact_twelve_credits = CreditRequirement(
        type="credits",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.MODULE_RULE,
        credits_min=Decimal("12"),
        credits_max=Decimal("12"),
        child=cardinality,
    )
    assert (
        evaluate_prerequisite_expression(cardinality_tree.tree, exact_twelve_credits, leaves)
        is PrerequisiteSatisfactionState.UNSATISFIED
    )


def test_logical_composed_and_requires_every_child() -> None:
    """An ordinary logical composed AND requires every child even when it looks course-headed."""
    root = course_summary("root")
    logical_and = AndRequirement(
        type="and",
        origin=PrerequisiteOrigin.COMPOSED,
        composed_role=ComposedAndRole.LOGICAL,
        children=(official_course("a"), official_course("b")),
    )
    compilation = make_compilation(root, logical_and, (course_summary("a"), course_summary("b")))

    evaluation = evaluate_prerequisite_satisfaction(compilation.tree, ["a"])
    assert evaluation.requirements_state is PrerequisiteSatisfactionState.UNSATISFIED

    # Completing both children satisfies the ordinary conjunction.
    both = evaluate_prerequisite_satisfaction(compilation.tree, ["a", "b"])
    assert both.requirements_state is PrerequisiteSatisfactionState.SATISFIED


def test_expanded_course_satisfaction_stops_at_a_basis_head() -> None:
    """A basis head satisfies its expanded branch and supplies one numeric witness."""
    root = course_summary("root")
    requirements = AndRequirement(
        type="and",
        origin=PrerequisiteOrigin.COMPOSED,
        composed_role=ComposedAndRole.EXPANDED_COURSE,
        children=(official_course("a"), official_course("e")),
    )
    compilation = make_compilation(
        root,
        requirements,
        (course_summary("a"), course_summary("e")),
    )

    covered = evaluate_prerequisite_satisfaction(compilation.tree, ["a"])
    assert covered.requirements_state is PrerequisiteSatisfactionState.SATISFIED

    # A descendant in the basis does not add another witness to the expanded head.
    with_descendant = evaluate_prerequisite_satisfaction(compilation.tree, ["a", "e"])
    assert with_descendant.requirements_state is PrerequisiteSatisfactionState.SATISFIED
    assert with_descendant.basis_group_ids == ("a", "e")
    exact_one = CourseCountRequirement(
        type="course_count",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.MODULE_RULE,
        count_min=1,
        count_max=1,
        child=requirements,
    )
    exact_two = CourseCountRequirement(
        type="course_count",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.MODULE_RULE,
        count_min=2,
        count_max=2,
        child=requirements,
    )
    assert (
        evaluate_prerequisite_expression(compilation.tree, exact_one, ["a", "e"])
        is PrerequisiteSatisfactionState.SATISFIED
    )
    assert (
        evaluate_prerequisite_expression(compilation.tree, exact_two, ["a", "e"])
        is PrerequisiteSatisfactionState.UNSATISFIED
    )


def test_excluded_completed_and_selected_basis_cannot_satisfy() -> None:
    """An excluded course is no witness even when in the basis or completed history."""
    root = course_summary("root")
    expanded = AndRequirement(
        type="and",
        origin=PrerequisiteOrigin.COMPOSED,
        composed_role=ComposedAndRole.EXPANDED_COURSE,
        children=(official_course("head"), official_course("head-child")),
    )
    requirements = OrRequirement(
        type="or",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.COMPULSORY,
        children=(official_course("leaf"), expanded, official_course("keep")),
    )
    compilation = make_compilation(
        root,
        requirements,
        (
            course_summary("leaf"),
            course_summary("head"),
            course_summary("head-child"),
            course_summary("keep"),
        ),
        excluded_group_ids=("head", "leaf"),
    )

    # A selected/completed excluded leaf and an excluded completed head are no witnesses, so the
    # official OR is unsatisfied.
    evaluation = evaluate_prerequisite_satisfaction(compilation.tree, ["leaf", "head"])
    assert evaluation.requirements_state is PrerequisiteSatisfactionState.UNSATISFIED

    # The unrelated basis course is a witness and satisfies the OR.
    with_keep = evaluate_prerequisite_satisfaction(compilation.tree, ["leaf", "head", "keep"])
    assert with_keep.requirements_state is PrerequisiteSatisfactionState.SATISFIED
