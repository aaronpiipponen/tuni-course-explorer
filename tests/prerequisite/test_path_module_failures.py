"""Activity-only module shortfalls that preserve strict failures."""

from __future__ import annotations

from decimal import Decimal

from course_explorer.prerequisite.domain import (
    AndRequirement,
    CourseCountRequirement,
    CreditRequirement,
    OfficialPrerequisiteKind,
    OrRequirement,
    PrerequisiteOrigin,
    UnresolvedPrerequisiteReason,
    UnresolvedRequirement,
)
from course_explorer.prerequisite.graph import (
    PrerequisiteCompilationIssue,
)
from course_explorer.prerequisite.path import (
    PrerequisitePathState,
    calculate_minimum_new_credits,
)
from tests.prerequisite._path_support import (
    course_summary,
    expanded_course,
    make_compilation,
    module_and,
    module_course,
    module_credits,
    official_and,
    official_course,
    selected_group_ids,
)


def test_active_module_shortfall_is_activity_only_and_preserves_strict_failures() -> None:
    """Shortfall is activity-only. All-course, ordinary, impossible, and unresolved stay strict."""
    root = course_summary("root")
    inactive_child = course_summary("inactive-b", credits_min="9", is_active=False)
    active_child = course_summary("active-a", credits_min="3")

    # The same otherwise-valid module rules solve exactly in all-course scope.
    all_courses = make_compilation(
        root,
        module_and("active-a", "inactive-b"),
        (active_child, inactive_child),
    )
    all_courses_result = calculate_minimum_new_credits(all_courses.tree, [])
    assert all_courses_result.state is PrerequisitePathState.EXACT
    assert selected_group_ids(all_courses_result) == ("active-a", "inactive-b")
    assert all_courses_result.total_new_credits == Decimal("12")
    assert all_courses_result.shortfalls == ()

    # An ordinary inactive compulsory leaf outside a module rule is no-solution.
    ordinary = make_compilation(
        root,
        official_and("inactive-b"),
        (inactive_child,),
        active_only=True,
    )
    ordinary_result = calculate_minimum_new_credits(ordinary.tree, [])
    assert ordinary_result.state is PrerequisitePathState.NO_SOLUTION
    assert ordinary_result.shortfalls == ()

    # An impossible module lower bound is no-solution even under active-only.
    impossible = make_compilation(
        root,
        module_credits("60", None, "active-a"),
        (active_child,),
        active_only=True,
    )
    impossible_result = calculate_minimum_new_credits(impossible.tree, [])
    assert impossible_result.state is PrerequisitePathState.NO_SOLUTION
    assert impossible_result.shortfalls == ()

    # An upper-bound-only failure is not an activity shortfall: it is no-solution.
    too_high = make_compilation(
        root,
        CourseCountRequirement(
            type="course_count",
            origin=PrerequisiteOrigin.OFFICIAL,
            official_kind=OfficialPrerequisiteKind.MODULE_RULE,
            count_min=1,
            count_max=1,
            child=module_and("active-a", "active-b"),
        ),
        (
            course_summary("active-a", credits_min="1"),
            course_summary("active-b", credits_min="1"),
        ),
        active_only=True,
    )
    too_high_result = calculate_minimum_new_credits(too_high.tree, [])
    assert too_high_result.state is PrerequisitePathState.NO_SOLUTION
    assert too_high_result.shortfalls == ()

    # A module position holding an unresolved child is never absorbed into a parent deficit.
    module_with_unresolved = make_compilation(
        root,
        AndRequirement(
            type="and",
            origin=PrerequisiteOrigin.OFFICIAL,
            official_kind=OfficialPrerequisiteKind.MODULE_RULE,
            children=(
                module_course("active-a"),
                UnresolvedRequirement(
                    type="unresolved",
                    origin=PrerequisiteOrigin.OFFICIAL,
                    official_kind=OfficialPrerequisiteKind.MODULE_RULE,
                    reason=UnresolvedPrerequisiteReason.MISSING_MODULE,
                ),
            ),
        ),
        (active_child,),
        active_only=True,
    )
    module_with_unresolved_result = calculate_minimum_new_credits(module_with_unresolved.tree, [])
    assert module_with_unresolved_result.state is PrerequisitePathState.UNRESOLVED
    assert module_with_unresolved_result.shortfalls == ()

    cycle_issue = PrerequisiteCompilationIssue(
        reason=UnresolvedPrerequisiteReason.COURSE_CYCLE,
        course_group_path=("root", "active-a", "root"),
        occurrence_id="r.0",
        action_key="course:active-a",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.MODULE_RULE,
    )
    cyclic = make_compilation(
        root,
        module_and("active-a"),
        (active_child,),
        active_only=True,
        issues=(cycle_issue,),
    )
    cyclic_result = calculate_minimum_new_credits(cyclic.tree, [])
    assert cyclic_result.state is PrerequisitePathState.UNRESOLVED
    assert cyclic_result.shortfalls == ()

    # A module position may not absorb an expanded-course branch whose active head is fine but
    # whose own ordinary prerequisite is unavailable: that would weaken a course prerequisite.
    nested_ordinary = make_compilation(
        root,
        AndRequirement(
            type="and",
            origin=PrerequisiteOrigin.OFFICIAL,
            official_kind=OfficialPrerequisiteKind.MODULE_RULE,
            children=(
                expanded_course("active-head", official_course("inactive-tail")),
                module_course("inactive-sibling"),
            ),
        ),
        (
            course_summary("active-head", credits_min="4"),
            course_summary("inactive-tail", credits_min="1", is_active=False),
            course_summary("inactive-sibling", credits_min="1", is_active=False),
        ),
        active_only=True,
    )
    nested_ordinary_result = calculate_minimum_new_credits(nested_ordinary.tree, [])
    assert nested_ordinary_result.state is PrerequisitePathState.NO_SOLUTION
    assert nested_ordinary_result.shortfalls == ()

    # A module numeric node whose only child is an expanded course with an unavailable ordinary
    # prerequisite must not fabricate a zero-measure deficit.
    numeric_compilation = make_compilation(
        root,
        CreditRequirement(
            type="credits",
            origin=PrerequisiteOrigin.OFFICIAL,
            official_kind=OfficialPrerequisiteKind.MODULE_RULE,
            credits_min=Decimal("2"),
            credits_max=None,
            child=expanded_course("active-head", official_course("inactive-tail")),
        ),
        (
            course_summary("active-head", credits_min="4"),
            course_summary("inactive-tail", credits_min="1", is_active=False),
            course_summary("inactive-other", credits_min="1", is_active=False),
        ),
        active_only=True,
    )
    numeric_result = calculate_minimum_new_credits(numeric_compilation.tree, [])
    assert numeric_result.state is PrerequisitePathState.NO_SOLUTION
    assert numeric_result.shortfalls == ()

    # A module position emptied by an ordinary prerequisite never neutral-fills inside an enclosing
    # module numeric rule either: the whole rule is no-solution.
    ordinary_in_module = AndRequirement(
        type="and",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.MODULE_RULE,
        children=(official_course("inactive-b"),),
    )
    outer_credit = make_compilation(
        root,
        CreditRequirement(
            type="credits",
            origin=PrerequisiteOrigin.OFFICIAL,
            official_kind=OfficialPrerequisiteKind.MODULE_RULE,
            credits_min=Decimal("2"),
            credits_max=None,
            child=ordinary_in_module,
        ),
        (course_summary("inactive-b", credits_min="4", is_active=False),),
        active_only=True,
    )
    outer_credit_result = calculate_minimum_new_credits(outer_credit.tree, [])
    assert outer_credit_result.state is PrerequisitePathState.NO_SOLUTION
    assert outer_credit_result.shortfalls == ()

    # An available exact active alternative always beats every reduced candidate.
    exact_wins = make_compilation(
        root,
        OrRequirement(
            type="or",
            origin=PrerequisiteOrigin.OFFICIAL,
            official_kind=OfficialPrerequisiteKind.COMPULSORY,
            children=(
                module_and("inactive-b"),
                official_course("active-a"),
            ),
        ),
        (active_child, inactive_child),
        active_only=True,
    )
    exact_wins_result = calculate_minimum_new_credits(exact_wins.tree, [])
    assert exact_wins_result.state is PrerequisitePathState.EXACT
    assert selected_group_ids(exact_wins_result) == ("active-a",)
    assert exact_wins_result.shortfalls == ()

    # An excluded module position is a strict no-solution, never an activity-only shortfall.
    excluded = make_compilation(
        root,
        module_course("module-unit"),
        (course_summary("module-unit", credits_min="4"),),
        active_only=True,
        excluded_group_ids=("module-unit",),
    )
    excluded_result = calculate_minimum_new_credits(excluded.tree, [])
    assert excluded_result.state is PrerequisitePathState.NO_SOLUTION
    assert excluded_result.shortfalls == ()
    assert excluded_result.blocked_excluded_group_ids == ("module-unit",)
