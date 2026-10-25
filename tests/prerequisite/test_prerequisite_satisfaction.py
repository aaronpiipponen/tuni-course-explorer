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
    evaluate_prerequisite_satisfaction,
)
from tests.prerequisite._graph_support import child_uses
from tests.prerequisite._path_support import (
    course_summary,
    fixture_structure,
    inferred_course,
    make_compilation,
    module_cardinality,
    official_course,
)
from tests.prerequisite._path_support import (
    official_and as official_option,
)


def _course_piece(structure, group_id: str) -> str:
    """Return the one non-cyclic course piece for a canonical group ID."""
    matches = [
        piece.piece_id
        for piece in structure.pieces
        if piece.kind == "course"
        and piece.course_group_id == group_id
        and not piece.cycle_closing
        and not piece.module_rule
    ]
    assert len(matches) == 1
    return matches[0]


def _extra_piece(structure, kind: str, child_piece_id: str, **fields) -> str:
    """Return the one registered wrapper piece with the supplied kind, child and scalars."""
    matches = [
        piece.piece_id
        for piece in structure.pieces
        if piece.kind == kind
        and child_piece_id in piece.children
        and all(getattr(piece, name) == value for name, value in fields.items())
    ]
    assert len(matches) == 1
    return matches[0]


def _piece_id_of_root(structure) -> str:
    """Return the native piece ID the primary root use evaluates."""
    assert structure.root_use_id is not None
    return next(use.piece_id for use in structure.uses if use.use_id == structure.root_use_id)


def _piece_of_use(structure, use_id: str) -> str:
    """Return the native piece ID one source use evaluates."""
    return next(use.piece_id for use in structure.uses if use.use_id == use_id)


def _unresolved_piece(structure, reason: str) -> str:
    """Return the one registered unresolved piece carrying the supplied source reason."""
    matches = [
        piece.piece_id
        for piece in structure.pieces
        if piece.kind == "unresolved" and piece.reason == reason
    ]
    assert len(matches) == 1
    return matches[0]


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
        compilation.solver,
        ["b", "zzz-unrelated", "a", "a"],
    )
    # Caller input normalizes to one sorted unique canonical tuple. Unrelated IDs are retained.
    assert evaluation.basis_group_ids == ("a", "b", "zzz-unrelated")
    assert evaluation.requirements_state is PrerequisiteSatisfactionState.SATISFIED
    assert evaluation.root_group_id == "root"

    # Ordering of caller input never changes the evaluation.
    reversed_input = evaluate_prerequisite_satisfaction(
        compilation.solver,
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
    exact_count_three = CourseCountRequirement(
        type="course_count",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.MODULE_RULE,
        count_min=3,
        count_max=3,
        child=requirements,
    )
    exact_ten_credits = CreditRequirement(
        type="credits",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.MODULE_RULE,
        credits_min=Decimal("10"),
        credits_max=Decimal("10"),
        child=requirements,
    )
    wrappers = fixture_structure(
        requirements,
        root=root,
        courses=(course_summary("a"), course_summary("b")),
        extra_requirements=(exact_count_two, exact_count_three, exact_ten_credits),
    )
    requirements_piece = wrappers.root_use_id
    assert requirements_piece is not None
    requirements_piece_id = _piece_id_of_root(wrappers)
    count_two_piece = _extra_piece(
        wrappers, "course_count", requirements_piece_id, count_min=2, count_max=2
    )
    count_three_piece = _extra_piece(
        wrappers, "course_count", requirements_piece_id, count_min=3, count_max=3
    )
    ten_credits_piece = _extra_piece(
        wrappers,
        "credits",
        requirements_piece_id,
        credits_min=Decimal("10"),
        credits_max=Decimal("10"),
    )

    # The request-local session shares one fixed basis/completed context across several subtree
    # evaluations: repeated leaves, exact count/credit wrappers and repeated calls keep their
    # explicit public states.
    session = PrerequisiteSatisfactionSession(wrappers, basis)
    assert session.evaluate(requirements_piece_id) is PrerequisiteSatisfactionState.SATISFIED
    for child_use in child_uses(wrappers, requirements_piece):
        assert (
            session.evaluate(_piece_of_use(wrappers, child_use))
            is PrerequisiteSatisfactionState.SATISFIED
        )
    assert session.evaluate(count_two_piece) is PrerequisiteSatisfactionState.SATISFIED
    assert session.evaluate(count_three_piece) is PrerequisiteSatisfactionState.UNSATISFIED
    assert session.evaluate(ten_credits_piece) is PrerequisiteSatisfactionState.SATISFIED
    assert session.evaluate(None) is PrerequisiteSatisfactionState.SATISFIED
    assert session.evaluate(count_two_piece) is PrerequisiteSatisfactionState.SATISFIED

    # A cardinality over two positions both naming one course is one variable, so the witness is one
    # course and five credits: exact count 1 passes and exact count 2 fails on the position/witness
    # distinction.
    positions = module_cardinality(2, 2, "a", "a")
    exact_one_course = CourseCountRequirement(
        type="course_count",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.MODULE_RULE,
        count_min=1,
        count_max=1,
        child=positions,
    )
    exact_two_courses = CourseCountRequirement(
        type="course_count",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.MODULE_RULE,
        count_min=2,
        count_max=2,
        child=positions,
    )
    positions_structure = fixture_structure(
        positions,
        root=root,
        courses=(course_summary("a"),),
        extra_requirements=(exact_one_course, exact_two_courses),
    )
    positions_root = positions_structure.root_use_id
    assert positions_root is not None
    positions_piece_id = _piece_id_of_root(positions_structure)
    one_course_piece = _extra_piece(
        positions_structure, "course_count", positions_piece_id, count_min=1, count_max=1
    )
    two_courses_piece = _extra_piece(
        positions_structure, "course_count", positions_piece_id, count_min=2, count_max=2
    )

    # The same session distinguishes one canonical witness from two positions naming it.
    positions_session = PrerequisiteSatisfactionSession(positions_structure, ["a"])
    assert positions_session.evaluate(one_course_piece) is PrerequisiteSatisfactionState.SATISFIED
    assert (
        positions_session.evaluate(two_courses_piece) is PrerequisiteSatisfactionState.UNSATISFIED
    )


def test_logical_states_follow_the_already_filtered_compilation() -> None:
    """AND/OR truth tables are exact, a rootless tree is satisfied, and no policy is re-applied."""
    root = course_summary("root")

    rootless = make_compilation(root, None, ())
    rootless_evaluation = evaluate_prerequisite_satisfaction(rootless.solver, [])
    assert rootless_evaluation.requirements_state is PrerequisiteSatisfactionState.SATISFIED

    and_tree = make_compilation(
        root, official_option("a", "b"), (course_summary("a"), course_summary("b"))
    )
    and_evaluation = evaluate_prerequisite_satisfaction(and_tree.solver, ["a"])
    assert and_evaluation.requirements_state is PrerequisiteSatisfactionState.UNSATISFIED

    or_requirements = OrRequirement(
        type="or",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.COMPULSORY,
        children=(official_course("a"), official_course("b")),
    )
    or_tree = make_compilation(root, or_requirements, (course_summary("a"), course_summary("b")))
    assert (
        evaluate_prerequisite_satisfaction(or_tree.solver, ["a"]).requirements_state
        is PrerequisiteSatisfactionState.SATISFIED
    )
    assert (
        evaluate_prerequisite_satisfaction(or_tree.solver, []).requirements_state
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
        recommended_tree.solver, ["recommended"]
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
    inferred_evaluation = evaluate_prerequisite_satisfaction(inferred_tree.solver, [])
    assert inferred_evaluation.include_inferred is True
    assert inferred_evaluation.include_recommended is False
    assert inferred_evaluation.requirements_state is PrerequisiteSatisfactionState.UNSATISFIED

    # The public subtree evaluator shares the same fold: a selected leaf, a neutral None, an
    # unsatisfied leaf and an unresolved leaf keep their tri-state meanings without changing the
    # full-report result.
    unresolved_requirement = UnresolvedRequirement(
        type="unresolved",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.COMPULSORY,
        reason=UnresolvedPrerequisiteReason.MISSING_COURSE,
    )
    subtree_structure = fixture_structure(
        official_option("a", "b"),
        root=root,
        courses=(course_summary("a"), course_summary("b")),
        extra_requirements=(unresolved_requirement,),
    )
    course_a_piece = _course_piece(subtree_structure, "a")
    unresolved_piece = _unresolved_piece(subtree_structure, "missing_course")

    # One request-local session over the same tree/basis evaluates several subtrees and a rootless
    # None expression with the explicit states.
    subtree_session = PrerequisiteSatisfactionSession(subtree_structure, ["a"])
    assert subtree_session.evaluate(course_a_piece) is PrerequisiteSatisfactionState.SATISFIED
    assert subtree_session.evaluate(None) is PrerequisiteSatisfactionState.SATISFIED
    assert subtree_session.evaluate(unresolved_piece) is PrerequisiteSatisfactionState.UNRESOLVED
    empty_session = PrerequisiteSatisfactionSession(subtree_structure, [])
    assert empty_session.evaluate(course_a_piece) is PrerequisiteSatisfactionState.UNSATISFIED

    # The observed unbounded 27-leaf cardinality must fold without enumerating selections, and nested
    # numeric wrappers keep exact reachable totals rather than treating them as an interval.
    leaves = tuple(f"leaf-{index:02d}" for index in range(27))
    cardinality = module_cardinality(1, None, *leaves)
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
    exact_twelve_credits = CreditRequirement(
        type="credits",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.MODULE_RULE,
        credits_min=Decimal("12"),
        credits_max=Decimal("12"),
        child=cardinality,
    )
    cardinality_structure = fixture_structure(
        cardinality,
        root=root,
        courses=tuple(course_summary(group_id) for group_id in leaves),
        extra_requirements=(exact_count_two, exact_ten_credits, exact_twelve_credits),
    )
    assert (
        evaluate_prerequisite_satisfaction(cardinality_structure, leaves).requirements_state
        is PrerequisiteSatisfactionState.SATISFIED
    )
    cardinality_root = cardinality_structure.root_use_id
    assert cardinality_root is not None
    count_two_piece = _extra_piece(
        cardinality_structure,
        "course_count",
        _piece_id_of_root(cardinality_structure),
        count_min=2,
        count_max=2,
    )
    ten_credits_piece = _extra_piece(
        cardinality_structure,
        "credits",
        count_two_piece,
        credits_min=Decimal("10"),
        credits_max=Decimal("10"),
    )
    twelve_credits_piece = _extra_piece(
        cardinality_structure,
        "credits",
        _piece_id_of_root(cardinality_structure),
        credits_min=Decimal("12"),
        credits_max=Decimal("12"),
    )
    cardinality_session = PrerequisiteSatisfactionSession(cardinality_structure, leaves)
    assert (
        cardinality_session.evaluate(ten_credits_piece) is PrerequisiteSatisfactionState.SATISFIED
    )
    assert (
        cardinality_session.evaluate(twelve_credits_piece)
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

    evaluation = evaluate_prerequisite_satisfaction(compilation.solver, ["a"])
    assert evaluation.requirements_state is PrerequisiteSatisfactionState.UNSATISFIED

    # Completing both children satisfies the ordinary conjunction.
    both = evaluate_prerequisite_satisfaction(compilation.solver, ["a", "b"])
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

    covered = evaluate_prerequisite_satisfaction(compilation.solver, ["a"])
    assert covered.requirements_state is PrerequisiteSatisfactionState.SATISFIED

    # A descendant in the basis does not add another witness to the expanded head.
    with_descendant = evaluate_prerequisite_satisfaction(compilation.solver, ["a", "e"])
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
    expanded_structure = fixture_structure(
        requirements,
        root=root,
        courses=(course_summary("a"), course_summary("e")),
        extra_requirements=(exact_one, exact_two),
    )
    expanded_root = expanded_structure.root_use_id
    assert expanded_root is not None
    expanded_piece_id = _piece_id_of_root(expanded_structure)
    exact_one_piece = _extra_piece(
        expanded_structure, "course_count", expanded_piece_id, count_min=1, count_max=1
    )
    exact_two_piece = _extra_piece(
        expanded_structure, "course_count", expanded_piece_id, count_min=2, count_max=2
    )
    expanded_session = PrerequisiteSatisfactionSession(expanded_structure, ["a", "e"])
    assert expanded_session.evaluate(exact_one_piece) is PrerequisiteSatisfactionState.SATISFIED
    assert expanded_session.evaluate(exact_two_piece) is PrerequisiteSatisfactionState.UNSATISFIED


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
    evaluation = evaluate_prerequisite_satisfaction(compilation.solver, ["leaf", "head"])
    assert evaluation.requirements_state is PrerequisiteSatisfactionState.UNSATISFIED

    # The unrelated basis course is a witness and satisfies the OR.
    with_keep = evaluate_prerequisite_satisfaction(compilation.solver, ["leaf", "head", "keep"])
    assert with_keep.requirements_state is PrerequisiteSatisfactionState.SATISFIED
