"""Public contracts for bounded approximate minimum-credit PATH attempts."""

from __future__ import annotations

from decimal import Decimal

import pytest

from course_explorer.prerequisite.domain import (
    AndRequirement,
    CardinalityRequirement,
    CourseCountRequirement,
    CreditRequirement,
    ModuleBlockRequirement,
    OfficialPrerequisiteKind,
    OpaqueCreditRequirement,
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
    official_course,
    official_or,
    selected_group_ids,
)


def test_path_below_size_limit_preserves_complete_exact_bytes() -> None:
    root = course_summary("root")
    small = make_compilation(root, official_course("small"), (course_summary("small"),))
    ordinary = calculate_minimum_new_credits(small.tree, [], completed_group_ids=[])
    capped_ordinary = calculate_minimum_new_credits(
        small.tree, [], completed_group_ids=[], max_compact_nodes=20000
    )
    assert ordinary.model_dump_json() == capped_ordinary.model_dump_json()


@pytest.mark.parametrize("overlapping_option", [False, True])
def test_scalar_greedy_route_deduplicates_shared_prerequisites_and_opaque_work(
    overlapping_option: bool,
) -> None:
    root = course_summary("root")
    heads = tuple(f"head-{index:02d}" for index in range(40))
    choices = []
    for head in heads:
        original = expanded_course(head, official_course("shared"))
        if overlapping_option:
            bait = expanded_course(
                f"bait-{head}",
                AndRequirement(
                    type="and",
                    origin=PrerequisiteOrigin.OFFICIAL,
                    official_kind=OfficialPrerequisiteKind.COMPULSORY,
                    children=(official_course("shared"), official_course("shared")),
                ),
            )
            choices.append(
                OrRequirement(
                    type="or",
                    origin=PrerequisiteOrigin.OFFICIAL,
                    official_kind=OfficialPrerequisiteKind.COMPULSORY,
                    children=(original, bait),
                )
            )
        else:
            choices.append(original)
    pick = CardinalityRequirement(
        type="cardinality",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.MODULE_RULE,
        require_min=20,
        require_max=None,
        children=tuple(choices),
    )
    repeated_opaque = OpaqueCreditRequirement(
        type="opaque_credits",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.MODULE_RULE,
        work_key="same-work",
        credits_min=Decimal("5"),
    )
    tree = make_compilation(
        root,
        AndRequirement(
            type="and",
            origin=PrerequisiteOrigin.OFFICIAL,
            official_kind=OfficialPrerequisiteKind.COMPULSORY,
            children=(official_course("shared"), repeated_opaque, repeated_opaque, pick),
        ),
        (
            course_summary("shared", credits_min="3"),
            *(course_summary(head, credits_min="1") for head in heads),
            *(course_summary(f"bait-{head}", credits_min="0.5") for head in heads),
        ),
    ).tree
    result = calculate_minimum_new_credits(tree, [], completed_group_ids=[], max_compact_nodes=1)
    assert result.state is PrerequisitePathState.APPROXIMATE
    assert selected_group_ids(result) == tuple(sorted((*heads[:20], "shared")))
    assert result.total_new_credits == Decimal("28")
    assert len(result.new_opaque_work) == 1
    assert result.new_opaque_work[0].occurrence_ids == ("r.1", "r.2")
    shared = next(entry for entry in result.new_courses if entry.course.group_id == "shared")
    expected_shared = (
        "r.0",
        *(f"r.3.{index}.0.1" if overlapping_option else f"r.3.{index}.1" for index in range(20)),
    )
    assert shared.occurrence_ids == tuple(sorted(expected_shared))
    assert [
        entry.occurrence_ids
        for entry in result.new_courses
        if entry.course.group_id.startswith("head-")
    ] == [
        ((f"r.3.{index}.0.0" if overlapping_option else f"r.3.{index}.0"),) for index in range(20)
    ]
    assert not any(entry.course.group_id.startswith("bait-") for entry in result.new_courses)


@pytest.mark.parametrize(
    ("pick_minimum", "duplicate_position"), [(0, False), (1, False), (1, True)]
)
def test_path_approximation_extends_greedy_prefixes_for_numeric_bounds(
    pick_minimum: int, duplicate_position: bool
) -> None:
    root = course_summary("root")
    choices = tuple(f"choice-{index:02d}" for index in range(27))
    pick = CardinalityRequirement(
        type="cardinality",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.MODULE_RULE,
        require_min=pick_minimum,
        require_max=None,
        children=tuple(
            official_course(choice)
            for choice in (
                (choices[0], choices[0], *choices[1:]) if duplicate_position else choices
            )
        ),
    )
    requirements = CreditRequirement(
        type="credits",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.MODULE_RULE,
        credits_min=Decimal("3"),
        credits_max=Decimal("3"),
        child=CourseCountRequirement(
            type="course_count",
            origin=PrerequisiteOrigin.OFFICIAL,
            official_kind=OfficialPrerequisiteKind.MODULE_RULE,
            count_min=3,
            count_max=3,
            child=pick,
        ),
    )
    tree = make_compilation(
        root, requirements, tuple(course_summary(choice, credits_min="1") for choice in choices)
    ).tree
    # A small budget forces another heuristic pass while allowing its three-course witness.
    result = calculate_minimum_new_credits(tree, [], completed_group_ids=[], max_compact_nodes=1)
    assert result.state is PrerequisitePathState.APPROXIMATE
    assert selected_group_ids(result) == choices[:3]
    assert result.total_new_credits == Decimal("3")
    if duplicate_position:
        assert [entry.occurrence_ids for entry in result.new_courses] == [
            ("r.0.0.0", "r.0.0.1"),
            ("r.0.0.2",),
            ("r.0.0.3",),
        ]
    else:
        assert [entry.occurrence_ids for entry in result.new_courses] == [
            (f"r.0.0.{index}",) for index in range(3)
        ]


@pytest.mark.parametrize("limit", [1, 10000])
def test_path_approximation_failure_reports_search_too_large_without_a_route(limit: int) -> None:
    root = course_summary("root")
    wide = CardinalityRequirement(
        type="cardinality",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.MODULE_RULE,
        require_min=20,
        require_max=20,
        children=tuple(official_course(f"wide-{index:02d}") for index in range(40)),
    )
    numeric_choice = CreditRequirement(
        type="credits",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.MODULE_RULE,
        credits_min=Decimal("3"),
        credits_max=Decimal("3"),
        child=CardinalityRequirement(
            type="cardinality",
            origin=PrerequisiteOrigin.OFFICIAL,
            official_kind=OfficialPrerequisiteKind.MODULE_RULE,
            require_min=1,
            require_max=1,
            children=(official_course("cheap"), official_course("dear")),
        ),
    )
    tree = make_compilation(
        root,
        AndRequirement(
            type="and",
            origin=PrerequisiteOrigin.OFFICIAL,
            official_kind=OfficialPrerequisiteKind.COMPULSORY,
            children=(wide, numeric_choice),
        ),
        tuple(course_summary(f"wide-{index:02d}", credits_min="1") for index in range(40))
        + (course_summary("cheap", credits_min="1"), course_summary("dear", credits_min="3")),
    ).tree
    result = calculate_minimum_new_credits(
        tree, [], completed_group_ids=[], max_compact_nodes=limit
    )
    assert result.state is PrerequisitePathState.APPROXIMATION_FAILED
    assert result.total_new_credits is None
    assert result.new_courses == ()
    assert result.new_opaque_work == ()
    assert result.selected_occurrence_ids == ()
    assert result.shortfalls == ()
    assert [(problem.reason, problem.occurrence_id) for problem in result.problems] == [
        ("search_too_large", "root")
    ]


@pytest.mark.parametrize("completed", [False, True])
def test_scalar_greedy_expanded_head_preserves_selected_vs_completed_history(
    completed: bool,
) -> None:
    """A selected head keeps descendants. Completing it skips its expanded descendants."""
    root = course_summary("root")
    requirements = AndRequirement(
        type="and",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.COMPULSORY,
        children=(expanded_course("head", official_course("history")), official_course("sibling")),
    )
    compilation = make_compilation(
        root,
        requirements,
        tuple(course_summary(group_id) for group_id in ("head", "history", "sibling")),
    )
    tree = compilation.tree.model_copy(update={"completed_node_keys": (), "excluded_node_keys": ()})
    basis = ("head",)
    history = ("head",) if completed else ()
    result = calculate_minimum_new_credits(
        tree, basis, completed_group_ids=history, max_compact_nodes=1
    )
    assert result.state is PrerequisitePathState.APPROXIMATE
    assert selected_group_ids(result) == (("sibling",) if completed else ("history", "sibling"))
    assert result.total_new_credits == Decimal("5" if completed else "10")
    sibling = next(item for item in result.new_courses if item.course.group_id == "sibling")
    assert sibling.occurrence_ids == ("r.1",)
    if not completed:
        descendant = next(item for item in result.new_courses if item.course.group_id == "history")
        assert descendant.occurrence_ids == ("r.0.1",)


@pytest.mark.parametrize("denial", ["excluded_course", "excluded_module", "inactive_course"])
def test_scalar_greedy_route_rejects_unavailable_alternatives(denial: str) -> None:
    """An excluded/completed module or inactive cheap option cannot enter the chosen route."""
    root = course_summary("root")
    cheap = (
        ModuleBlockRequirement(
            type="module_block",
            origin=PrerequisiteOrigin.OFFICIAL,
            official_kind=OfficialPrerequisiteKind.COMPULSORY,
            module_group_id="module-cheap",
            child=official_course("cheap"),
        )
        if denial == "excluded_module"
        else official_course("cheap")
    )
    requirements = official_or("dear")
    requirements = requirements.model_copy(update={"children": (cheap, official_course("dear"))})
    compilation = make_compilation(
        root,
        requirements,
        (
            course_summary("cheap", credits_min="1", is_active=denial != "inactive_course"),
            course_summary("dear", credits_min="4"),
        ),
        active_only=denial == "inactive_course",
    )
    tree = compilation.tree.model_copy(
        update={
            "excluded_group_ids": ("cheap",) if denial == "excluded_course" else (),
            "completed_node_keys": ("module:module-cheap",) if denial == "excluded_module" else (),
            "excluded_node_keys": ("module:module-cheap",) if denial == "excluded_module" else (),
        }
    )
    result = calculate_minimum_new_credits(tree, (), completed_group_ids=(), max_compact_nodes=1)
    assert result.state is PrerequisitePathState.APPROXIMATE
    assert selected_group_ids(result) == ("dear",)
    assert result.total_new_credits == Decimal("4")
    assert all(item.course.group_id != "cheap" for item in result.new_courses)
