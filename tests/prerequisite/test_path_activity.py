"""Activity eligibility, exclusion routes, and inactive-candidate alternatives."""

from __future__ import annotations

from decimal import Decimal

from course_explorer.prerequisite.domain import (
    AndRequirement,
    ComposedOrRole,
    OfficialPrerequisiteKind,
    OrRequirement,
    PrerequisiteOrigin,
)
from course_explorer.prerequisite.path import (
    PrerequisitePathState,
    calculate_minimum_new_credits,
)
from tests.prerequisite._path_support import (
    course_summary,
    expanded_course,
    make_compilation,
    official_and,
    official_course,
    official_or,
    selected_group_ids,
)


def test_active_only_path_excludes_inactive_non_basis_candidates_and_uses_eligible_alternatives() -> (
    None
):
    """Active-only never proposes or charges an inactive course outside the basis."""
    root = course_summary("root")

    # A required inactive non-basis leaf has no eligible route: explicit no-solution, no fabrication.
    required_inactive = make_compilation(
        root,
        official_and("inactive-leaf"),
        (course_summary("inactive-leaf", credits_min="4", is_active=False),),
        active_only=True,
    )
    required_result = calculate_minimum_new_credits(required_inactive.tree, [])
    assert required_result.state is PrerequisitePathState.NO_SOLUTION
    assert required_result.new_courses == ()
    assert required_result.total_new_credits is None

    # An OR route with an eligible active alternative is exact and charges only the active course.
    alternative = make_compilation(
        root,
        official_or("inactive-leaf", "active-alt"),
        (
            course_summary("inactive-leaf", credits_min="1", is_active=False),
            course_summary("active-alt", credits_min="3"),
        ),
        active_only=True,
    )
    alternative_result = calculate_minimum_new_credits(alternative.tree, [])
    assert alternative_result.state is PrerequisitePathState.EXACT
    assert selected_group_ids(alternative_result) == ("active-alt",)
    assert alternative_result.total_new_credits == Decimal("3")

    # A retained inactive course in the chosen basis is an exact zero-cost witness.
    retained_basis = make_compilation(
        root,
        official_and("inactive-leaf"),
        (course_summary("inactive-leaf", credits_min="4", is_active=False),),
        active_only=True,
    )
    retained_result = calculate_minimum_new_credits(retained_basis.tree, ["inactive-leaf"])
    assert retained_result.state is PrerequisitePathState.EXACT
    assert selected_group_ids(retained_result) == ()
    assert retained_result.total_new_credits == Decimal("0")

    # A retained inactive course outside the basis neither satisfies nor is proposed.
    retained_only = calculate_minimum_new_credits(retained_basis.tree, [])
    assert retained_only.state is PrerequisitePathState.NO_SOLUTION
    assert selected_group_ids(retained_only) == ()

    # Identical all-course input selects the inactive course at its credits_min.
    all_courses = make_compilation(
        root,
        official_and("inactive-leaf"),
        (course_summary("inactive-leaf", credits_min="4", is_active=False),),
    )
    all_courses_result = calculate_minimum_new_credits(all_courses.tree, [])
    assert all_courses_result.state is PrerequisitePathState.EXACT
    assert selected_group_ids(all_courses_result) == ("inactive-leaf",)
    assert all_courses_result.total_new_credits == Decimal("4")


def test_exclusion_selects_other_or_else_no_solution() -> None:
    """A cheap excluded branch is denied. The other OR wins, and the only route is no-solution."""
    root = course_summary("root")

    alternative = make_compilation(
        root,
        official_or("excluded", "alt"),
        (course_summary("excluded", credits_min="1"), course_summary("alt", credits_min="3")),
        excluded_group_ids=("excluded",),
    )
    alternative_result = calculate_minimum_new_credits(alternative.tree, [])
    assert alternative_result.state is PrerequisitePathState.EXACT
    assert selected_group_ids(alternative_result) == ("alt",)
    assert alternative_result.total_new_credits == Decimal("3")
    # The denied excluded course is reported even though another option won.
    assert alternative_result.blocked_excluded_group_ids == ("excluded",)

    only = make_compilation(
        root,
        official_and("excluded"),
        (course_summary("excluded", credits_min="1"),),
        excluded_group_ids=("excluded",),
    )
    only_result = calculate_minimum_new_credits(only.tree, [])
    assert only_result.state is PrerequisitePathState.NO_SOLUTION
    assert only_result.new_courses == ()
    assert only_result.total_new_credits is None
    assert only_result.blocked_excluded_group_ids == ("excluded",)


def test_excluded_substitution_option_requires_every_member() -> None:
    """An excluded member invalidates only its AND substitution option. Another option works."""
    root = course_summary("root")
    substitution = AndRequirement(
        type="and",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.SUBSTITUTION,
        children=(official_course("s1"), official_course("s2")),
    )
    other = AndRequirement(
        type="and",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.SUBSTITUTION,
        children=(official_course("other"),),
    )
    requirements = OrRequirement(
        type="or",
        origin=PrerequisiteOrigin.COMPOSED,
        composed_role=ComposedOrRole.COURSE_ALTERNATIVES,
        children=(official_course("a"), substitution, other),
    )
    compilation = make_compilation(
        root,
        requirements,
        (
            course_summary("a", credits_min="6"),
            course_summary("s1", credits_min="2"),
            course_summary("s2", credits_min="2"),
            course_summary("other", credits_min="8"),
        ),
        excluded_group_ids=("s1",),
    )
    result = calculate_minimum_new_credits(compilation.tree, [])
    assert result.state is PrerequisitePathState.EXACT
    assert selected_group_ids(result) == ("a",)
    assert result.total_new_credits == Decimal("6")
    assert result.blocked_excluded_group_ids == ("s1",)


def test_excluded_course_does_not_poison_descendant_on_another_route() -> None:
    """A descendant under an excluded head is usable through another route."""
    root = course_summary("root")
    requirements = OrRequirement(
        type="or",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.COMPULSORY,
        children=(
            expanded_course("x", official_course("shared")),
            expanded_course("y", official_course("shared")),
        ),
    )
    compilation = make_compilation(
        root,
        requirements,
        (
            course_summary("x", credits_min="2"),
            course_summary("y", credits_min="3"),
            course_summary("shared", credits_min="4"),
        ),
        excluded_group_ids=("x",),
    )
    result = calculate_minimum_new_credits(compilation.tree, [])
    assert result.state is PrerequisitePathState.EXACT
    assert selected_group_ids(result) == ("shared", "y")
    assert result.total_new_credits == Decimal("7")
    assert result.blocked_excluded_group_ids == ("x",)
