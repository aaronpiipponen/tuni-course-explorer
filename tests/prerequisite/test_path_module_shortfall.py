"""Active module shortfall maxima across all rule families."""

from __future__ import annotations

from decimal import Decimal

import pytest

from course_explorer.curriculum import CatalogueCurriculumPeriod
from course_explorer.enums import ModuleRuleType, PrerequisiteRequirementKind
from course_explorer.prerequisite.domain import (
    AndRequirement,
    CardinalityRequirement,
    CourseCountRequirement,
    CreditRequirement,
    OfficialPrerequisiteKind,
    OrRequirement,
    PrerequisiteOrigin,
)
from course_explorer.prerequisite.graph import PrerequisiteGraphCompiler
from course_explorer.prerequisite.path import (
    PrerequisiteModuleShortfallKind,
    PrerequisitePathState,
    calculate_minimum_new_credits,
)
from course_explorer.prerequisite.satisfaction import (
    PrerequisiteSatisfactionState,
)
from tests.prerequisite._graph_support import (
    FakeCurriculumRead,
    RecordingEquivalenceGroupRead,
    RecordingInferredSetRead,
    catalogue_course,
    catalogue_module,
    module_rule,
    module_version,
    prerequisite_module_member,
    prerequisite_option,
)
from tests.prerequisite._path_support import (
    course_summary,
    expanded_course,
    make_compilation,
    module_and,
    module_cardinality,
    module_course,
    selected_group_ids,
)


def test_active_module_shortfall_returns_maximum_for_all_rule_families() -> None:
    """Activity-only module rules report the maximum active witness and their exact deficits."""
    root = course_summary("root")

    # A bare module course unit unavailable only by activity is one reduced all-mandatory position.
    bare = make_compilation(
        root,
        module_course("inactive-unit"),
        (course_summary("inactive-unit", credits_min="4", is_active=False),),
        active_only=True,
    )
    bare_result = calculate_minimum_new_credits(bare.tree, [], completed_group_ids=[])
    assert bare_result.state is PrerequisitePathState.SHORTFALL
    assert bare_result.satisfaction.requirements_state is PrerequisiteSatisfactionState.UNSATISFIED
    assert bare_result.satisfaction.active_only is True
    assert selected_group_ids(bare_result) == ()
    assert bare_result.total_new_credits == Decimal("0")
    assert bare_result.blockers == ()
    assert [
        (
            entry.kind,
            entry.occurrence_id,
            entry.required_count,
            entry.achieved_count,
            entry.count_deficit,
        )
        for entry in bare_result.shortfalls
    ] == [
        (PrerequisiteModuleShortfallKind.ALL_MANDATORY, "r", 1, 0, 1),
    ]

    # All-mandatory: one active child is taken, the unavailable child is one exact parent deficit.
    all_mandatory = make_compilation(
        root,
        module_and("active-a", "inactive-b"),
        (
            course_summary("active-a", credits_min="3"),
            course_summary("inactive-b", credits_min="9", is_active=False),
        ),
        active_only=True,
    )
    all_mandatory_result = calculate_minimum_new_credits(
        all_mandatory.tree, [], completed_group_ids=[]
    )
    assert all_mandatory_result.state is PrerequisitePathState.SHORTFALL
    assert selected_group_ids(all_mandatory_result) == ("active-a",)
    assert all_mandatory_result.total_new_credits == Decimal("3")
    assert [
        (
            entry.kind,
            entry.required_count,
            entry.achieved_count,
            entry.count_deficit,
        )
        for entry in all_mandatory_result.shortfalls
    ] == [(PrerequisiteModuleShortfallKind.ALL_MANDATORY, 2, 1, 1)]

    # Nested shortfall plus an unavailable sibling carries both the nested and one parent deficit.
    nested = CardinalityRequirement(
        type="cardinality",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.MODULE_RULE,
        require_min=2,
        require_max=2,
        children=(module_course("active-nested"), module_course("inactive-nested")),
    )
    mixed = make_compilation(
        root,
        AndRequirement(
            type="and",
            origin=PrerequisiteOrigin.OFFICIAL,
            official_kind=OfficialPrerequisiteKind.MODULE_RULE,
            children=(nested, module_course("inactive-sibling")),
        ),
        (
            course_summary("active-nested", credits_min="4"),
            course_summary("inactive-nested", credits_min="6", is_active=False),
            course_summary("inactive-sibling", credits_min="7", is_active=False),
        ),
        active_only=True,
    )
    mixed_result = calculate_minimum_new_credits(mixed.tree, [], completed_group_ids=[])
    assert mixed_result.state is PrerequisitePathState.SHORTFALL
    assert selected_group_ids(mixed_result) == ("active-nested",)
    assert mixed_result.total_new_credits == Decimal("4")
    assert [(entry.kind, entry.occurrence_id) for entry in mixed_result.shortfalls] == [
        (PrerequisiteModuleShortfallKind.ALL_MANDATORY, "r"),
        (PrerequisiteModuleShortfallKind.CARDINALITY, "r.0"),
    ]
    parent_entry = mixed_result.shortfalls[0]
    assert (parent_entry.required_count, parent_entry.achieved_count) == (2, 1)
    assert parent_entry.count_deficit == 1
    nested_entry = mixed_result.shortfalls[1]
    assert (nested_entry.required_count, nested_entry.achieved_count) == (2, 1)
    assert nested_entry.count_deficit == 1

    # A module position whose reduced child meets the parent's own bound adds no parent
    # deficit: only the nested record propagates.
    nested_only = make_compilation(
        root,
        AndRequirement(
            type="and",
            origin=PrerequisiteOrigin.OFFICIAL,
            official_kind=OfficialPrerequisiteKind.MODULE_RULE,
            children=(
                CardinalityRequirement(
                    type="cardinality",
                    origin=PrerequisiteOrigin.OFFICIAL,
                    official_kind=OfficialPrerequisiteKind.MODULE_RULE,
                    require_min=2,
                    require_max=2,
                    children=(
                        module_course("active-nested"),
                        module_course("inactive-nested"),
                    ),
                ),
                module_course("active-ok"),
            ),
        ),
        (
            course_summary("active-nested", credits_min="4"),
            course_summary("inactive-nested", credits_min="6", is_active=False),
            course_summary("active-ok", credits_min="2"),
        ),
        active_only=True,
    )
    nested_only_result = calculate_minimum_new_credits(nested_only.tree, [], completed_group_ids=[])
    assert nested_only_result.state is PrerequisitePathState.SHORTFALL
    assert selected_group_ids(nested_only_result) == ("active-nested", "active-ok")
    assert nested_only_result.total_new_credits == Decimal("6")
    assert [
        (entry.kind, entry.occurrence_id, entry.required_count, entry.achieved_count)
        for entry in nested_only_result.shortfalls
    ] == [(PrerequisiteModuleShortfallKind.CARDINALITY, "r.0", 2, 1)]

    # Cardinality: the largest selectable count below require_min becomes the achieved count.
    cardinality = make_compilation(
        root,
        module_cardinality(2, 3, "active-a", "inactive-b", "inactive-c"),
        (
            course_summary("active-a", credits_min="5"),
            course_summary("inactive-b", credits_min="2", is_active=False),
            course_summary("inactive-c", credits_min="1", is_active=False),
        ),
        active_only=True,
    )
    cardinality_result = calculate_minimum_new_credits(cardinality.tree, [], completed_group_ids=[])
    assert cardinality_result.state is PrerequisitePathState.SHORTFALL
    assert selected_group_ids(cardinality_result) == ("active-a",)
    assert cardinality_result.total_new_credits == Decimal("5")
    entry = cardinality_result.shortfalls[0]
    assert entry.kind is PrerequisiteModuleShortfallKind.CARDINALITY
    assert entry.occurrence_id == "r"
    assert (entry.required_count, entry.achieved_count, entry.count_deficit) == (2, 1, 1)

    # Credits: the greatest sub-minimum witness total is measured from direct witnesses, not closure.
    credits = make_compilation(
        root,
        CreditRequirement(
            type="credits",
            origin=PrerequisiteOrigin.OFFICIAL,
            official_kind=OfficialPrerequisiteKind.MODULE_RULE,
            credits_min=Decimal("10"),
            credits_max=None,
            child=OrRequirement(
                type="or",
                origin=PrerequisiteOrigin.OFFICIAL,
                official_kind=OfficialPrerequisiteKind.MODULE_RULE,
                children=(
                    expanded_course("active-head", module_course("deep-tail")),
                    module_course("inactive-big"),
                ),
            ),
        ),
        (
            course_summary("active-head", credits_min="4"),
            course_summary("deep-tail", credits_min="100"),
            course_summary("inactive-big", credits_min="12", is_active=False),
        ),
        active_only=True,
    )
    credits_result = calculate_minimum_new_credits(credits.tree, [], completed_group_ids=[])
    assert credits_result.state is PrerequisitePathState.SHORTFALL
    # The witness total is the head's 4 credits. The charged closure includes the deep tail.
    assert selected_group_ids(credits_result) == ("active-head", "deep-tail")
    assert credits_result.total_new_credits == Decimal("104")
    credits_shortfall = credits_result.shortfalls[0]
    assert credits_shortfall.kind is PrerequisiteModuleShortfallKind.CREDITS
    assert credits_shortfall.occurrence_id == "r"
    assert credits_shortfall.required_credits == Decimal("10")
    assert credits_shortfall.achieved_credits == Decimal("4")
    assert credits_shortfall.credit_deficit == Decimal("6")

    # A mixed credit frontier that overflows the upper bound elsewhere keeps its greatest
    # below-minimum active witness: only the inactive in-range alternative proves activity is why.
    mixed_credit = make_compilation(
        root,
        CreditRequirement(
            type="credits",
            origin=PrerequisiteOrigin.OFFICIAL,
            official_kind=OfficialPrerequisiteKind.MODULE_RULE,
            credits_min=Decimal("5"),
            credits_max=Decimal("10"),
            child=module_cardinality(1, 1, "credit-low", "credit-high", "credit-fit-inactive"),
        ),
        (
            course_summary("credit-low", credits_min="3"),
            course_summary("credit-high", credits_min="12"),
            course_summary("credit-fit-inactive", credits_min="6", is_active=False),
        ),
        active_only=True,
    )
    mixed_credit_result = calculate_minimum_new_credits(
        mixed_credit.tree, [], completed_group_ids=[]
    )
    assert mixed_credit_result.state is PrerequisitePathState.SHORTFALL
    assert selected_group_ids(mixed_credit_result) == ("credit-low",)
    assert mixed_credit_result.total_new_credits == Decimal("3")
    assert [
        (
            entry.kind,
            entry.occurrence_id,
            entry.required_credits,
            entry.achieved_credits,
            entry.credit_deficit,
        )
        for entry in mixed_credit_result.shortfalls
    ] == [(PrerequisiteModuleShortfallKind.CREDITS, "r", Decimal("5"), Decimal("3"), Decimal("2"))]

    # Course count: distinct witness count below count_min becomes the achieved count.
    course_count = make_compilation(
        root,
        CourseCountRequirement(
            type="course_count",
            origin=PrerequisiteOrigin.OFFICIAL,
            official_kind=OfficialPrerequisiteKind.MODULE_RULE,
            count_min=3,
            count_max=None,
            child=AndRequirement(
                type="and",
                origin=PrerequisiteOrigin.OFFICIAL,
                official_kind=OfficialPrerequisiteKind.MODULE_RULE,
                children=(
                    module_course("active-a"),
                    module_course("active-b"),
                    module_course("inactive-c"),
                ),
            ),
        ),
        (
            course_summary("active-a", credits_min="2"),
            course_summary("active-b", credits_min="3"),
            course_summary("inactive-c", credits_min="1", is_active=False),
        ),
        active_only=True,
    )
    course_count_result = calculate_minimum_new_credits(
        course_count.tree, [], completed_group_ids=[]
    )
    assert course_count_result.state is PrerequisitePathState.SHORTFALL
    assert selected_group_ids(course_count_result) == ("active-a", "active-b")
    assert course_count_result.total_new_credits == Decimal("5")
    count_entry = course_count_result.shortfalls[0]
    assert count_entry.kind is PrerequisiteModuleShortfallKind.COURSE_COUNT
    assert (count_entry.required_count, count_entry.achieved_count) == (3, 2)
    assert count_entry.count_deficit == 1


@pytest.mark.parametrize(
    "node_type",
    [ModuleRuleType.CREDITS_RULE, ModuleRuleType.COURSE_UNIT_COUNT_RULE],
)
def test_zero_minimum_module_bound_preserves_child_activity_shortfall(node_type) -> None:
    """A zero-minimum module numeric rule reports only its inactive child's cardinality deficit."""
    year_period = (CatalogueCurriculumPeriod(id="period-2026", academic_year_start=2026),)
    numeric_fields = (
        {"credits_min": "0"} if node_type is ModuleRuleType.CREDITS_RULE else {"count_min": 0}
    )
    module = catalogue_module(
        "module-zero",
        (
            module_version(
                "module-zero-v1",
                rule=module_rule(
                    node_type,
                    **numeric_fields,
                    children=(
                        module_rule(
                            ModuleRuleType.COMPOSITE_RULE,
                            require_min=1,
                            require_max=1,
                            children=(
                                module_rule(
                                    ModuleRuleType.COURSE_UNIT_RULE,
                                    referenced_group_id="inactive",
                                ),
                            ),
                        ),
                    ),
                ),
                curriculum_periods=year_period,
            ),
        ),
    )
    root = catalogue_course(
        "root",
        prerequisite_options=(
            prerequisite_option(
                0,
                PrerequisiteRequirementKind.COMPULSORY,
                prerequisite_module_member(0, "module-zero"),
            ),
        ),
    )
    compilation = PrerequisiteGraphCompiler(
        FakeCurriculumRead((root, catalogue_course("inactive", is_active=False)), (module,)),
        RecordingInferredSetRead(),
        RecordingEquivalenceGroupRead(),
    ).compile("root", active_only=True, retained_group_ids=("inactive",))

    result = calculate_minimum_new_credits(compilation.tree, [], completed_group_ids=[])

    assert result.state is PrerequisitePathState.SHORTFALL
    assert result.satisfaction.requirements_state is PrerequisiteSatisfactionState.UNSATISFIED
    assert selected_group_ids(result) == ()
    assert result.total_new_credits == Decimal("0")
    assert result.blockers == ()
    assert [
        (
            entry.kind,
            entry.occurrence_id,
            entry.required_count,
            entry.achieved_count,
            entry.count_deficit,
        )
        for entry in result.shortfalls
    ] == [(PrerequisiteModuleShortfallKind.CARDINALITY, "r.0.0", 1, 0, 1)]
