"""Coverage fidelity and deterministic tie-breaking for the minimum-credit path."""

from __future__ import annotations

from decimal import Decimal

import pytest

from course_explorer.enums import InferredCoverageState
from course_explorer.prerequisite.domain import (
    AndRequirement,
    CourseCountRequirement,
    CreditRequirement,
    InferredSetCoverage,
    ModuleBlockRequirement,
    OfficialPrerequisiteKind,
    OpaqueCreditRequirement,
    OrRequirement,
    PrerequisiteOrigin,
)
from course_explorer.prerequisite.graph import (
    InferredCoverageRecord,
)
from course_explorer.prerequisite.path import (
    MinimumCreditPathEvaluation,
    PrerequisitePathState,
    calculate_minimum_new_credits,
)
from course_explorer.prerequisite.satisfaction import (
    PrerequisiteSatisfactionState,
)
from tests.prerequisite._path_support import (
    course_summary,
    expanded_course,
    inferred_course,
    make_compilation,
    module_cardinality,
    official_and,
    official_course,
    official_or,
    selected_group_ids,
)


def test_minimum_path_preserves_coverage_and_deterministic_ties() -> None:
    """Coverage fidelity and deterministic ties survive the public service result."""
    root = course_summary("root")

    # Current inferred coverage is copied as-is and partial coverage is exact.
    coverage = (
        InferredCoverageRecord(
            target_group_id="root",
            coverage_state=InferredCoverageState.PARTIAL,
            coverage=InferredSetCoverage(
                eligible_source_count=3, processed_source_count=1, accepted_source_count=1
            ),
        ),
    )
    inferred_compilation = make_compilation(
        root,
        inferred_course("z"),
        (course_summary("z", credits_min="2"),),
        include_inferred=True,
        coverage=coverage,
    )
    inferred_result = calculate_minimum_new_credits(
        inferred_compilation.tree, [], completed_group_ids=[]
    )
    assert inferred_result.state is PrerequisitePathState.EXACT
    assert inferred_result.inferred_coverage == inferred_compilation.tree.inferred_coverage
    assert selected_group_ids(inferred_result) == ("z",)
    assert inferred_result.satisfaction.include_inferred is True

    # Equal-credit alternatives prefer the active course: an earlier-ranked inactive candidate loses
    # to a lower-ranked active one with the same new credits.
    tie = make_compilation(
        root,
        official_or("a", "b"),
        (
            course_summary("a", credits_min="5", is_active=False),
            course_summary("b", credits_min="5"),
        ),
    )
    tie_result = calculate_minimum_new_credits(tie.tree, [], completed_group_ids=[])
    assert selected_group_ids(tie_result) == ("b",)
    assert tie_result == calculate_minimum_new_credits(tie.tree, [], completed_group_ids=[])

    # With equal activity the canonical-ID order decides the same-credit tie.
    stable = make_compilation(
        root,
        official_or("a", "b"),
        (course_summary("a", credits_min="5"), course_summary("b", credits_min="5")),
    )
    stable_result = calculate_minimum_new_credits(stable.tree, [], completed_group_ids=[])
    assert selected_group_ids(stable_result) == ("a",)

    # Equal-cost real courses beat opaque obligations: new opaque IDs are compared first.
    opaque = OpaqueCreditRequirement(
        type="opaque_credits",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.MODULE_RULE,
        work_key="opaque",
        credits_min=Decimal("5"),
    )
    mixed = make_compilation(
        root,
        OrRequirement(
            type="or",
            origin=PrerequisiteOrigin.OFFICIAL,
            official_kind=OfficialPrerequisiteKind.COMPULSORY,
            children=(official_course("a"), opaque),
        ),
        (course_summary("a", credits_min="5"),),
    )
    mixed_result = calculate_minimum_new_credits(mixed.tree, [], completed_group_ids=[])
    assert selected_group_ids(mixed_result) == ("a",)
    assert mixed_result.new_opaque_work == ()

    # When the new-work identities tie, combined attested/opaque witnesses are ordered as one
    # typed coordinate and evidence belongs only to the winning attested branch.
    shared_work = OpaqueCreditRequirement(
        type="opaque_credits",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.MODULE_RULE,
        work_key="shared-work",
        credits_min=Decimal("5"),
    )
    manual_module = ModuleBlockRequirement(
        type="module_block",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.MODULE_RULE,
        module_group_id="manual",
        child=official_course("member"),
    )
    witness_tie = make_compilation(
        root,
        AndRequirement(
            type="and",
            origin=PrerequisiteOrigin.OFFICIAL,
            official_kind=OfficialPrerequisiteKind.COMPULSORY,
            children=(
                shared_work,
                CreditRequirement(
                    type="credits",
                    origin=PrerequisiteOrigin.OFFICIAL,
                    official_kind=OfficialPrerequisiteKind.MODULE_RULE,
                    credits_min=Decimal("5"),
                    credits_max=Decimal("5"),
                    child=OrRequirement(
                        type="or",
                        origin=PrerequisiteOrigin.OFFICIAL,
                        official_kind=OfficialPrerequisiteKind.MODULE_RULE,
                        children=(manual_module, shared_work),
                    ),
                ),
            ),
        ),
        (course_summary("member"),),
    )
    witness_tie_tree = witness_tie.tree.model_copy(
        update={
            "completed_node_keys": ("module:manual",),
            "node_occurrences": tuple(
                occurrence.model_copy(update={"manual_credits_min": Decimal("5")})
                if occurrence.action_key == "module:manual"
                else occurrence
                for occurrence in witness_tie.tree.node_occurrences
            ),
        }
    )
    witness_tie_result = calculate_minimum_new_credits(witness_tie_tree, [], completed_group_ids=[])
    assert witness_tie_result.state is PrerequisitePathState.EXACT
    assert witness_tie_result.total_new_credits == Decimal("5")
    assert witness_tie_result.new_opaque_work[0].occurrence_ids == ("r.0",)
    assert "r.1.0" in witness_tie_result.selected_occurrence_ids
    assert "r.1.1" not in witness_tie_result.selected_occurrence_ids


def test_selected_basis_head_keeps_prerequisite_closure_while_completed_head_skips_it() -> None:
    """A selected-but-incomplete expanded head costs its closure. A completed head is free."""
    root = course_summary("root")
    plain = make_compilation(
        root,
        expanded_course("a", official_course("e")),
        (course_summary("a", credits_min="2"), course_summary("e", credits_min="3")),
    )

    # Empty basis charges the head and its descendant.
    empty = calculate_minimum_new_credits(plain.tree, [], completed_group_ids=[])
    assert empty.state is PrerequisitePathState.EXACT
    assert selected_group_ids(empty) == ("a", "e")
    assert empty.total_new_credits == Decimal("5")
    assert empty.selected_occurrence_ids == ("r", "r.0", "r.1")

    # Selected-only basis: the head itself is free but its descendant closure is charged.
    selected = calculate_minimum_new_credits(plain.tree, ["a"], completed_group_ids=[])
    assert selected.satisfaction.requirements_state is PrerequisiteSatisfactionState.UNSATISFIED
    assert selected.state is PrerequisitePathState.EXACT
    assert selected.satisfaction.completed_group_ids == ()
    assert selected_group_ids(selected) == ("e",)
    assert selected.selected_occurrence_ids == ("r", "r.0", "r.1")
    assert selected.total_new_credits == Decimal("3")

    # Completed head alone costs zero and skips its historical descendant.
    completed = calculate_minimum_new_credits(plain.tree, ["a"], completed_group_ids=["a"])
    assert completed.state is PrerequisitePathState.EXACT
    assert completed.satisfaction.requirements_state is PrerequisiteSatisfactionState.SATISFIED
    assert completed.satisfaction.completed_group_ids == ("a",)
    assert selected_group_ids(completed) == ()
    assert completed.selected_occurrence_ids == ()
    assert completed.total_new_credits == Decimal("0")

    # Two expanded heads share one descendant: the closure is globally deduplicated when one
    # head is completed and the other is selected-but-incomplete.
    shared_tree = make_compilation(
        root,
        AndRequirement(
            type="and",
            origin=PrerequisiteOrigin.OFFICIAL,
            official_kind=OfficialPrerequisiteKind.COMPULSORY,
            children=(
                expanded_course("a", official_course("shared")),
                expanded_course("b", official_course("shared")),
            ),
        ),
        (
            course_summary("a", credits_min="2"),
            course_summary("b", credits_min="3"),
            course_summary("shared", credits_min="4"),
        ),
    )
    mixed = calculate_minimum_new_credits(shared_tree.tree, ["a", "b"], completed_group_ids=["a"])
    assert mixed.state is PrerequisitePathState.EXACT
    # B is selected but incomplete, so the official root is unsatisfied while the path is exact.
    assert mixed.satisfaction.requirements_state is PrerequisiteSatisfactionState.UNSATISFIED
    # Completed A skips its own closure. Selected-but-incomplete B is free for itself and charges the
    # shared descendant exactly once.
    assert selected_group_ids(mixed) == ("shared",)
    assert mixed.total_new_credits == Decimal("4")
    assert mixed.selected_occurrence_ids == ("r", "r.0", "r.0.0", "r.1", "r.1.0", "r.1.1")


@pytest.mark.parametrize(
    ("required", "optional", "expected"),
    [("z", "a", ("a", "z")), ("a", "z", ("a",))],
)
def test_minimum_path_zero_credit_ties_ignore_tree_variable_order(
    required: str, optional: str, expected: tuple[str, ...]
) -> None:
    """Canonical-ID ties are order-independent even with zero-credit courses and tuple prefixes."""
    root = course_summary("root")
    requirements = AndRequirement(
        type="and",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.COMPULSORY,
        children=(
            OpaqueCreditRequirement(
                type="opaque_credits",
                origin=PrerequisiteOrigin.OFFICIAL,
                official_kind=OfficialPrerequisiteKind.MODULE_RULE,
                work_key="mandatory-opaque",
                credits_min=Decimal("2"),
            ),
            official_course(required),
            module_cardinality(0, 1, optional),
        ),
    )
    compilation = make_compilation(
        root,
        requirements,
        (
            course_summary(required, credits_min="1"),
            course_summary(optional, credits_min="0"),
        ),
    )

    result = calculate_minimum_new_credits(compilation.tree, [], completed_group_ids=[])

    assert result.state is PrerequisitePathState.EXACT
    assert result.total_new_credits == Decimal("3")
    assert len(result.new_opaque_work) == 1
    assert selected_group_ids(result) == expected
    assert result.blockers == ()
    assert result.shortfalls == ()
    evidence_by_group = {
        entry.course.group_id: entry.occurrence_ids for entry in result.new_courses
    }
    assert evidence_by_group[required] == ("r.1",)
    if optional in expected:
        assert evidence_by_group[optional] == ("r.2.0",)
    else:
        assert optional not in evidence_by_group

    reversed_source = make_compilation(
        root,
        requirements.model_copy(update={"children": tuple(reversed(requirements.children))}),
        compilation.tree.courses,
    )
    reversed_result = calculate_minimum_new_credits(
        reversed_source.tree, [], completed_group_ids=[]
    )
    assert selected_group_ids(reversed_result) == expected


def test_minimum_path_reconstructs_only_feasible_projected_evidence() -> None:
    """Rejected routes and projected descendants never leak evidence. Every valid label unions."""
    root = course_summary("root")
    count_node = CourseCountRequirement(
        type="course_count",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.MODULE_RULE,
        count_min=1,
        count_max=1,
        child=OrRequirement(
            type="or",
            origin=PrerequisiteOrigin.OFFICIAL,
            official_kind=OfficialPrerequisiteKind.MODULE_RULE,
            children=(
                official_and("shared", "extra"),
                official_course("shared"),
                official_and("shared", "shared"),
            ),
        ),
    )
    requirements = AndRequirement(
        type="and",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.COMPULSORY,
        children=(
            expanded_course("head", count_node),
            official_course("shared"),
        ),
    )
    compilation = make_compilation(
        root,
        requirements,
        (
            course_summary("head", credits_min="2"),
            course_summary("shared", credits_min="1"),
            course_summary("extra", credits_min="0"),
        ),
    )

    result = calculate_minimum_new_credits(compilation.tree, [], completed_group_ids=[])

    assert result.state is PrerequisitePathState.EXACT
    assert selected_group_ids(result) == ("head", "shared")
    assert result.total_new_credits == Decimal("3")
    assert result.blockers == ()
    assert result.shortfalls == ()
    evidence_by_group = {
        entry.course.group_id: entry.occurrence_ids for entry in result.new_courses
    }
    assert evidence_by_group["head"] == ("r.0.0",)
    # The count filter rejects the two-witness shared+extra route, so its shared leaf
    # `r.0.1.0.0.0` must not leak. Equal-identity alternatives and canonical joins union the rest.
    assert evidence_by_group["shared"] == (
        "r.0.1.0.1",
        "r.0.1.0.2.0",
        "r.0.1.0.2.1",
        "r.1",
    )
    # Exact selected-occurrence evidence covers the structural constraint and the chosen leaf, and
    # never the rejected count alternative.
    assert "r.0.1" in result.selected_occurrence_ids
    assert "r.0.1.0.1" in result.selected_occurrence_ids
    assert not any(
        occurrence_id.startswith("r.0.1.0.0") for occurrence_id in result.selected_occurrence_ids
    )


@pytest.mark.parametrize("max_compact_nodes", [None, 1])
def test_route_activity_tie_counts_only_distinct_new_courses(max_compact_nodes) -> None:
    """The public ranking spends minimum new credits, then fewest distinct inactive new courses.

    The parametrization runs the exact optimizer and the forced-approximation cap over the
    same public ranking contract. The approximate route keeps the primary credit ordering.
    """
    root = course_summary("root")
    expected_state = (
        PrerequisitePathState.EXACT
        if max_compact_nodes is None
        else PrerequisitePathState.APPROXIMATE
    )

    def solve(requirements, courses) -> MinimumCreditPathEvaluation:
        compilation = make_compilation(root, requirements, courses)
        return calculate_minimum_new_credits(
            compilation.tree, (), completed_group_ids=[], max_compact_nodes=max_compact_nodes
        )

    # Credits stay primary: a cheaper inactive candidate beats a dearer active one.
    cheap = solve(
        official_or("inactive-cheap", "active-dear"),
        (
            course_summary("inactive-cheap", credits_min="1", is_active=False),
            course_summary("active-dear", credits_min="5"),
        ),
    )
    assert cheap.state is expected_state
    assert selected_group_ids(cheap) == ("inactive-cheap",)
    assert cheap.total_new_credits == Decimal("1")

    # On equal credits the fewest distinct inactive new courses decide, even when that candidate
    # sorts lower. One shared inactive descendant counts once on every branch.
    head = expanded_course("head", official_course("inactive-shared"))
    extra = AndRequirement(
        type="and",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.COMPULSORY,
        children=(
            expanded_course("head", official_course("inactive-shared")),
            official_course("inactive-extra"),
        ),
    )
    activity_tie = solve(
        OrRequirement(
            type="or",
            origin=PrerequisiteOrigin.OFFICIAL,
            official_kind=OfficialPrerequisiteKind.COMPULSORY,
            children=(head, extra),
        ),
        (
            course_summary("head", credits_min="5"),
            course_summary("inactive-shared", credits_min="5", is_active=False),
            course_summary("inactive-extra", credits_min="0", is_active=False),
        ),
    )
    assert activity_tie.state is expected_state
    assert selected_group_ids(activity_tie) == ("head", "inactive-shared")
    assert activity_tie.total_new_credits == Decimal("10")

    # A basis-covered inactive course charges no credits and no inactivity penalty, so it wins over
    # the equal-credit active alternative with no new work at all.
    basis_compilation = make_compilation(
        root,
        official_or("inactive-covered", "active-alternative"),
        (
            course_summary("inactive-covered", credits_min="5", is_active=False),
            course_summary("active-alternative", credits_min="5"),
        ),
    )
    basis_covered = calculate_minimum_new_credits(
        basis_compilation.tree,
        ("inactive-covered",),
        completed_group_ids=[],
        max_compact_nodes=max_compact_nodes,
    )
    assert basis_covered.state is PrerequisitePathState.EXACT
    assert basis_covered.total_new_credits == Decimal("0")
    assert selected_group_ids(basis_covered) == ()
    assert basis_covered.new_opaque_work == ()
