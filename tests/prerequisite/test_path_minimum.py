"""Minimum-new-credit path solving over direct, cardinality, credit, and course-count trees."""

from __future__ import annotations

from decimal import Decimal

import pytest

from course_explorer.curriculum import CatalogueCurriculumPeriod
from course_explorer.enums import ModuleRuleType, PrerequisiteRequirementKind
from course_explorer.prerequisite.domain import (
    AndRequirement,
    CardinalityRequirement,
    ComposedAndRole,
    ComposedOrRole,
    CourseCountRequirement,
    CreditRequirement,
    OfficialPrerequisiteKind,
    OpaqueCreditRequirement,
    OrRequirement,
    PrerequisiteOrigin,
    UnresolvedPrerequisiteReason,
    UnresolvedRequirement,
)
from course_explorer.prerequisite.graph import (
    PrerequisiteCompilationIssue,
    PrerequisiteGraphCompiler,
)
from course_explorer.prerequisite.path import (
    PrerequisitePathBlockerKind,
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
    prerequisite_course_member,
    prerequisite_module_member,
    prerequisite_option,
)
from tests.prerequisite._path_support import (
    course_summary,
    expanded_course,
    make_compilation,
    module_cardinality,
    official_and,
    official_course,
    official_or,
    selected_group_ids,
)


def test_minimum_path_uses_global_union_and_new_credits_not_local_course_count() -> None:
    """Globally cheapest canonical union wins. Credits, not course count, decide the minimum."""
    root = course_summary("root")

    # A three-course cheap branch beats a single dear course: minimize credits, never course count.
    cheap = official_and("a", "b", "c")
    dear = official_and("d")
    requirements = OrRequirement(
        type="or",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.COMPULSORY,
        children=(cheap, dear),
    )
    compilation = make_compilation(
        root,
        requirements,
        (
            course_summary("a", credits_min="1"),
            course_summary("b", credits_min="1"),
            course_summary("c", credits_min="1"),
            course_summary("d", credits_min="10"),
        ),
    )
    result = calculate_minimum_new_credits(compilation.tree, [], completed_group_ids=[])
    assert result.state is PrerequisitePathState.EXACT
    assert selected_group_ids(result) == ("a", "b", "c")
    assert result.total_new_credits == Decimal("3")

    # Overlapping branches share one canonical course. The global union is cheaper than local minima.
    overlapping = AndRequirement(
        type="and",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.COMPULSORY,
        children=(official_or("a", "b"), official_or("a", "c")),
    )
    overlap_compilation = make_compilation(
        root,
        overlapping,
        (
            course_summary("a", credits_min="2"),
            course_summary("b", credits_min="5"),
            course_summary("c", credits_min="5"),
        ),
    )
    overlap_result = calculate_minimum_new_credits(
        overlap_compilation.tree, [], completed_group_ids=[]
    )
    assert selected_group_ids(overlap_result) == ("a",)
    assert overlap_result.total_new_credits == Decimal("2")

    # Completed courses cost zero, repeated occurrences cost once, and evidence lists every branch.
    repeated = official_and("a", "a", "b")
    repeated_compilation = make_compilation(
        root,
        repeated,
        (course_summary("a", credits_min="2"), course_summary("b", credits_min="4")),
    )
    repeated_result = calculate_minimum_new_credits(
        repeated_compilation.tree, ["a"], completed_group_ids=["a"]
    )
    assert selected_group_ids(repeated_result) == ("b",)
    assert repeated_result.total_new_credits == Decimal("4")

    incomplete_result = calculate_minimum_new_credits(
        repeated_compilation.tree, [], completed_group_ids=[]
    )
    assert selected_group_ids(incomplete_result) == ("a", "b")
    assert incomplete_result.total_new_credits == Decimal("6")
    a_entry = next(entry for entry in incomplete_result.new_courses if entry.course.group_id == "a")
    assert a_entry.occurrence_ids == ("r.0", "r.1")


def _compile_opaque_root(root, modules, courses=(), completed_node_keys=()):
    """Compile one real graph fixture used by the opaque-source-work path contracts."""
    return PrerequisiteGraphCompiler(
        FakeCurriculumRead((root, *courses), modules),
        RecordingInferredSetRead(),
        RecordingEquivalenceGroupRead(),
    ).compile(root.group_id, completed_node_keys=completed_node_keys)


def test_minimum_path_expands_new_courses_and_directional_substitutions() -> None:
    """A substitute includes its own prerequisite. Substitution is whole OR-of-AND."""
    root = course_summary("root")

    # Directional substitution: A with prereq E, or one whole multi-member option, or A3.
    original_branch = expanded_course("a", official_course("e"))
    option_one = AndRequirement(
        type="and",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.SUBSTITUTION,
        children=(
            expanded_course("a1", official_course("e1")),
            official_course("a2", OfficialPrerequisiteKind.SUBSTITUTION),
        ),
    )
    option_two = AndRequirement(
        type="and",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.SUBSTITUTION,
        children=(official_course("a3", OfficialPrerequisiteKind.SUBSTITUTION),),
    )
    substitution = OrRequirement(
        type="or",
        origin=PrerequisiteOrigin.COMPOSED,
        composed_role=ComposedOrRole.COURSE_ALTERNATIVES,
        children=(original_branch, option_one, option_two),
    )
    substitution_compilation = make_compilation(
        root,
        substitution,
        (
            course_summary("a", credits_min="10"),
            course_summary("e", credits_min="10"),
            course_summary("a1", credits_min="1"),
            course_summary("e1", credits_min="1"),
            course_summary("a2", credits_min="1"),
            course_summary("a3", credits_min="50"),
        ),
    )

    # The globally cheapest route is option one, and it must include the substitute's own prereq E1.
    option_one_result = calculate_minimum_new_credits(
        substitution_compilation.tree, [], completed_group_ids=[]
    )
    assert selected_group_ids(option_one_result) == ("a1", "a2", "e1")
    assert option_one_result.total_new_credits == Decimal("3")
    # The substituted head and its own prerequisite keep their exact occurrence identities.
    a1_entry = next(
        entry for entry in option_one_result.new_courses if entry.course.group_id == "a1"
    )
    e1_entry = next(
        entry for entry in option_one_result.new_courses if entry.course.group_id == "e1"
    )
    assert a1_entry.occurrence_ids == ("r.1.0.0",)
    assert e1_entry.occurrence_ids == ("r.1.0.1",)

    # One member is not enough: the option is AND, so the remaining member is charged.
    partial = calculate_minimum_new_credits(
        substitution_compilation.tree, ["a1"], completed_group_ids=["a1"]
    )
    assert selected_group_ids(partial) == ("a2",)
    assert partial.total_new_credits == Decimal("1")

    # Completing the other member makes the completed substitute's own prerequisite required again.
    other_member = calculate_minimum_new_credits(
        substitution_compilation.tree, ["a2"], completed_group_ids=["a2"]
    )
    assert selected_group_ids(other_member) == ("a1", "e1")
    assert other_member.total_new_credits == Decimal("2")

    # A whole option satisfies: no residual course, and no reverse/chained substitute is invented.
    satisfied_option = calculate_minimum_new_credits(
        substitution_compilation.tree, ["a1", "a2"], completed_group_ids=["a1", "a2"]
    )
    assert satisfied_option.state is PrerequisitePathState.EXACT
    assert satisfied_option.total_new_credits == Decimal("0")
    assert selected_group_ids(satisfied_option) == ()

    # Completing only a substitute member's prerequisite never substitutes for the required course.
    prerequisite_only = calculate_minimum_new_credits(
        substitution_compilation.tree, ["e1"], completed_group_ids=["e1"]
    )
    assert selected_group_ids(prerequisite_only) == ("a1", "a2")


def test_logical_composed_and_charges_every_incomplete_child() -> None:
    """An ordinary logical composed AND charges every incomplete child instead of a false zero."""
    root = course_summary("root")
    logical_and = AndRequirement(
        type="and",
        origin=PrerequisiteOrigin.COMPOSED,
        composed_role=ComposedAndRole.LOGICAL,
        children=(official_course("a"), official_course("b")),
    )
    compilation = make_compilation(
        root,
        logical_and,
        (course_summary("a", credits_min="3"), course_summary("b", credits_min="4")),
    )

    result = calculate_minimum_new_credits(compilation.tree, ["a"], completed_group_ids=["a"])
    assert result.satisfaction.requirements_state is PrerequisiteSatisfactionState.UNSATISFIED
    assert result.state is PrerequisitePathState.EXACT
    assert selected_group_ids(result) == ("b",)
    assert result.total_new_credits == Decimal("4")

    # Completing both children yields the ordinary zero-cost exact result.
    completed = calculate_minimum_new_credits(
        compilation.tree, ["a", "b"], completed_group_ids=["a", "b"]
    )
    assert completed.state is PrerequisitePathState.EXACT
    assert selected_group_ids(completed) == ()
    assert completed.total_new_credits == Decimal("0")


def test_minimum_path_solves_cardinality_credit_and_course_count_on_witnesses() -> None:
    """Numeric wrappers measure direct witnesses while total cost adds recursive prerequisite closure."""
    root = course_summary("root")
    cardinality = CardinalityRequirement(
        type="cardinality",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.MODULE_RULE,
        require_min=1,
        require_max=2,
        children=(official_course("a"), official_course("b"), official_course("c")),
    )
    cardinality_compilation = make_compilation(
        root,
        cardinality,
        (
            course_summary("a", credits_min="1"),
            course_summary("b", credits_min="2"),
            course_summary("c", credits_min="5"),
        ),
    )
    chosen = calculate_minimum_new_credits(cardinality_compilation.tree, [], completed_group_ids=[])
    assert selected_group_ids(chosen) == ("a",)
    assert chosen.total_new_credits == Decimal("1")

    # Repeated canonical occurrences collapse: two of (a, a, b) cost one canonical a.
    overlap = CardinalityRequirement(
        type="cardinality",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.MODULE_RULE,
        require_min=2,
        require_max=2,
        children=(official_course("a"), official_course("a"), official_course("b")),
    )
    overlap_compilation = make_compilation(
        root,
        overlap,
        (course_summary("a", credits_min="1"), course_summary("b", credits_min="4")),
    )
    overlap_result = calculate_minimum_new_credits(
        overlap_compilation.tree, [], completed_group_ids=[]
    )
    assert selected_group_ids(overlap_result) == ("a",)
    assert overlap_result.total_new_credits == Decimal("1")

    # A zero-cardinality neutral selection is a valid exact zero-cost solution.
    neutral = CardinalityRequirement(
        type="cardinality",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.MODULE_RULE,
        require_min=0,
        require_max=1,
        children=(official_course("a"),),
    )
    neutral_compilation = make_compilation(root, neutral, (course_summary("a"),))
    neutral_result = calculate_minimum_new_credits(
        neutral_compilation.tree, [], completed_group_ids=[]
    )
    assert neutral_result.state is PrerequisitePathState.EXACT
    assert neutral_result.total_new_credits == Decimal("0")
    assert selected_group_ids(neutral_result) == ()

    # Credit bounds filter the direct witness A, but the charged cost includes recursive prereq E.
    credit = CreditRequirement(
        type="credits",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.MODULE_RULE,
        credits_min=Decimal("1"),
        credits_max=Decimal("1"),
        child=expanded_course("a", official_course("e")),
    )
    credit_compilation = make_compilation(
        root,
        credit,
        (
            course_summary("a", credits_min="1", credits_max="99"),
            course_summary("e", credits_min="100", credits_max="999"),
        ),
    )
    credit_result = calculate_minimum_new_credits(
        credit_compilation.tree, [], completed_group_ids=[]
    )
    assert credit_result.state is PrerequisitePathState.EXACT
    assert selected_group_ids(credit_result) == ("a", "e")
    assert credit_result.total_new_credits == Decimal("101")

    # Course-count bounds measure distinct witnesses only.
    count = CourseCountRequirement(
        type="course_count",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.MODULE_RULE,
        count_min=1,
        count_max=1,
        child=official_or("a", "b"),
    )
    count_compilation = make_compilation(
        root,
        count,
        (course_summary("a", credits_min="3"), course_summary("b", credits_min="2")),
    )
    count_result = calculate_minimum_new_credits(count_compilation.tree, [], completed_group_ids=[])
    assert selected_group_ids(count_result) == ("b",)
    assert count_result.total_new_credits == Decimal("2")


def test_minimum_path_reports_unresolved_cycles_and_no_solution() -> None:
    """Unknown structure and impossible constraints stay explicit without fabricated answers."""
    root = course_summary("root")

    # An explicit zero-credit opaque obligation is a real zero requirement: it costs nothing and is
    # satisfied, so the whole route is exact zero with no blocker.
    zero_opaque = make_compilation(
        root,
        OpaqueCreditRequirement(
            type="opaque_credits",
            origin=PrerequisiteOrigin.OFFICIAL,
            official_kind=OfficialPrerequisiteKind.MODULE_RULE,
            work_key="w-zero",
            credits_min=Decimal("0"),
        ),
        (),
    )
    unrestricted_result = calculate_minimum_new_credits(
        zero_opaque.tree, [], completed_group_ids=[]
    )
    assert unrestricted_result.state is PrerequisitePathState.EXACT
    assert unrestricted_result.total_new_credits == Decimal("0")
    assert selected_group_ids(unrestricted_result) == ()
    assert unrestricted_result.blockers == ()

    # A positive-cost known branch beside a genuinely missing module is unresolved, not a claimed
    # minimum: unknown source structure could be cheaper.
    mixed = OrRequirement(
        type="or",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.COMPULSORY,
        children=(
            official_course("a"),
            UnresolvedRequirement(
                type="unresolved",
                origin=PrerequisiteOrigin.OFFICIAL,
                official_kind=OfficialPrerequisiteKind.MODULE_RULE,
                reason=UnresolvedPrerequisiteReason.MISSING_MODULE,
            ),
        ),
    )
    mixed_compilation = make_compilation(root, mixed, (course_summary("a", credits_min="5"),))
    mixed_result = calculate_minimum_new_credits(mixed_compilation.tree, [], completed_group_ids=[])
    assert mixed_result.state is PrerequisitePathState.UNRESOLVED
    assert mixed_result.total_new_credits is None
    assert selected_group_ids(mixed_result) == ()

    # A known satisfying alternative wins, including a zero-cost completion.
    known = calculate_minimum_new_credits(mixed_compilation.tree, ["a"], completed_group_ids=["a"])
    assert known.state is PrerequisitePathState.EXACT
    assert known.total_new_credits == Decimal("0")
    assert known.blockers == ()

    # A course cycle blocks an exact answer but is irrelevant once the requirement is satisfied.
    cycle_issue = PrerequisiteCompilationIssue(
        reason=UnresolvedPrerequisiteReason.COURSE_CYCLE,
        course_group_path=("root", "a", "root"),
        occurrence_id="r.0",
        action_key="course:a",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.COMPULSORY,
    )
    cycle_compilation = make_compilation(
        root,
        official_and("a", "a"),
        (course_summary("a", credits_min="2"),),
        issues=(cycle_issue,),
    )
    cycle_result = calculate_minimum_new_credits(cycle_compilation.tree, [], completed_group_ids=[])
    assert cycle_result.state is PrerequisitePathState.UNRESOLVED
    assert cycle_result.total_new_credits is None
    assert selected_group_ids(cycle_result) == ()
    assert cycle_result.blockers[0].kind is PrerequisitePathBlockerKind.COURSE_CYCLE
    assert cycle_result.blockers[0].course_group_path == ("root", "a", "root")
    cycle_satisfied = calculate_minimum_new_credits(
        cycle_compilation.tree, ["a"], completed_group_ids=["a"]
    )
    assert cycle_satisfied.state is PrerequisitePathState.EXACT
    assert cycle_satisfied.total_new_credits == Decimal("0")

    # A selected-only basis does not resolve the real cycle: the closing occurrence is unresolved
    # unless the containing branch is completed history.
    cycle_selected_only = calculate_minimum_new_credits(
        cycle_compilation.tree, ["a"], completed_group_ids=[]
    )
    assert cycle_selected_only.state is PrerequisitePathState.UNRESOLVED
    assert any(
        blocker.kind is PrerequisitePathBlockerKind.COURSE_CYCLE
        for blocker in cycle_selected_only.blockers
    )

    # An impossible numeric bound is a represented no-solution result, not an unresolved one.
    impossible = CreditRequirement(
        type="credits",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.MODULE_RULE,
        credits_min=Decimal("10"),
        credits_max=Decimal("10"),
        child=official_course("a"),
    )
    impossible_compilation = make_compilation(
        root, impossible, (course_summary("a", credits_min="5"),)
    )
    impossible_result = calculate_minimum_new_credits(
        impossible_compilation.tree, [], completed_group_ids=[]
    )
    assert impossible_result.state is PrerequisitePathState.NO_SOLUTION
    assert impossible_result.total_new_credits is None
    assert selected_group_ids(impossible_result) == ()
    assert impossible_result.blockers == ()


def test_minimum_path_handles_large_nested_choice_rules_exactly() -> None:
    """A 27-way nested choice folds exactly to the globally cheapest three-course path."""
    root = course_summary("root")
    choice_ids = tuple(f"choice-{index:02d}" for index in range(27))
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
            child=module_cardinality(1, None, *choice_ids),
        ),
    )
    compilation = make_compilation(
        root,
        requirements,
        tuple(course_summary(group_id, credits_min="1") for group_id in choice_ids),
    )

    result = calculate_minimum_new_credits(compilation.tree, [], completed_group_ids=[])

    assert result.state is PrerequisitePathState.EXACT
    assert selected_group_ids(result) == ("choice-00", "choice-01", "choice-02")
    assert result.total_new_credits == Decimal("3")
    assert result.shortfalls == ()
    assert result.blockers == ()
    assert [entry.occurrence_ids for entry in result.new_courses] == [
        ("r.0.0.0",),
        ("r.0.0.1",),
        ("r.0.0.2",),
    ]


_OPAQUE_YEAR = (CatalogueCurriculumPeriod(id="period-2026", academic_year_start=2026),)


def _opaque_module(group_id: str, rule, *, credits: str | None = None):
    return catalogue_module(
        group_id,
        (
            module_version(
                f"{group_id}-v1",
                rule=rule,
                curriculum_periods=_OPAQUE_YEAR,
                target_credits_min=credits,
            ),
        ),
    )


def _opaque_course_root(root_id: str, *members):
    return catalogue_course(
        root_id,
        prerequisite_options=(
            prerequisite_option(0, PrerequisiteRequirementKind.COMPULSORY, *members),
        ),
    )


def test_repeated_unexpandable_module_work_is_charged_once() -> None:
    blank = _opaque_module("module-blank", module_rule(ModuleRuleType.COMPOSITE_RULE), credits="35")
    root = _opaque_course_root(
        "blank-root",
        prerequisite_module_member(0, "module-blank"),
        prerequisite_module_member(1, "module-blank"),
    )
    result = calculate_minimum_new_credits(
        _compile_opaque_root(root, (blank,)).tree, [], completed_group_ids=[]
    )
    assert result.state is PrerequisitePathState.EXACT
    assert result.new_courses == ()
    assert len(result.new_opaque_work) == 1
    assert result.new_opaque_work[0].credits_min == Decimal("35")
    assert len(result.new_opaque_work[0].occurrence_ids) == 2
    assert result.total_new_credits == Decimal("35")


def test_repeated_bounded_work_keeps_intrinsic_identity_and_occurrences() -> None:
    rule = module_rule(
        ModuleRuleType.CREDITS_RULE,
        credits_min="10",
        children=(module_rule(ModuleRuleType.ANY_COURSE_UNIT_RULE),),
    )
    module = _opaque_module("module-bounded", rule)
    root = _opaque_course_root(
        "bounded-root",
        prerequisite_module_member(0, "module-bounded"),
        prerequisite_module_member(1, "module-bounded"),
    )
    result = calculate_minimum_new_credits(
        _compile_opaque_root(root, (module,)).tree, [], completed_group_ids=[]
    )
    assert len(result.new_opaque_work) == 1
    assert result.new_opaque_work[0].credits_min == Decimal("10")
    assert result.new_opaque_work[0].occurrence_ids == ("r.0.0", "r.1.0")
    assert result.total_new_credits == Decimal("10")


def test_distinct_opaque_siblings_are_charged_separately() -> None:
    rule = module_rule(
        ModuleRuleType.COMPOSITE_RULE,
        all_mandatory=True,
        children=(
            module_rule(
                ModuleRuleType.CREDITS_RULE,
                credits_min="10",
                children=(module_rule(ModuleRuleType.ANY_COURSE_UNIT_RULE),),
            ),
            module_rule(
                ModuleRuleType.CREDITS_RULE,
                sibling_position=1,
                credits_min="10",
                children=(module_rule(ModuleRuleType.ANY_COURSE_UNIT_RULE),),
            ),
        ),
    )
    module = _opaque_module("module-siblings", rule)
    root = _opaque_course_root("sibling-root", prerequisite_module_member(0, "module-siblings"))
    result = calculate_minimum_new_credits(
        _compile_opaque_root(root, (module,)).tree, [], completed_group_ids=[]
    )
    assert len(result.new_opaque_work) == 2
    assert result.total_new_credits == Decimal("20")


def test_resolved_members_cost_courses_not_module_target() -> None:
    module = _opaque_module(
        "module-member",
        module_rule(ModuleRuleType.COURSE_UNIT_RULE, referenced_group_id="member"),
        credits="35",
    )
    root = _opaque_course_root("member-root", prerequisite_module_member(0, "module-member"))
    result = calculate_minimum_new_credits(
        _compile_opaque_root(root, (module,), (catalogue_course("member"),)).tree,
        [],
        completed_group_ids=[],
    )
    assert result.state is PrerequisitePathState.EXACT
    assert selected_group_ids(result) == ("member",)
    assert result.total_new_credits == Decimal("5")
    assert result.new_opaque_work == ()


def test_unknown_course_count_never_fabricates_courses() -> None:
    module = _opaque_module(
        "module-unknown",
        module_rule(
            ModuleRuleType.COURSE_UNIT_COUNT_RULE,
            count_min=1,
            children=(module_rule(ModuleRuleType.ANY_COURSE_UNIT_RULE),),
        ),
    )
    root = _opaque_course_root("unknown-root", prerequisite_module_member(0, "module-unknown"))
    result = calculate_minimum_new_credits(
        _compile_opaque_root(root, (module,)).tree, [], completed_group_ids=[]
    )
    assert result.state is PrerequisitePathState.UNRESOLVED
    assert result.new_courses == ()
    assert result.total_new_credits is None
    assert any(
        blocker.reason is UnresolvedPrerequisiteReason.UNKNOWN_COURSE_COUNT
        for blocker in result.blockers
    )


def test_completed_unknown_extent_fails_positive_credit_bound() -> None:
    inner = _opaque_module(
        "module-inner",
        module_rule(ModuleRuleType.COURSE_UNIT_RULE, referenced_group_id="member"),
    )
    outer = _opaque_module(
        "module-outer",
        module_rule(
            ModuleRuleType.CREDITS_RULE,
            credits_min="10",
            children=(module_rule(ModuleRuleType.MODULE_RULE, referenced_group_id="module-inner"),),
        ),
    )
    root = _opaque_course_root("outer-root", prerequisite_module_member(0, "module-outer"))
    tree = _compile_opaque_root(
        root,
        (inner, outer),
        (catalogue_course("member"),),
        completed_node_keys=("module:module-inner",),
    ).tree
    result = calculate_minimum_new_credits(tree, [], completed_group_ids=[])
    assert result.state is PrerequisitePathState.UNRESOLVED
    assert result.new_courses == ()
    assert any(
        problem.reason == UnresolvedPrerequisiteReason.UNKNOWN_CREDIT_EXTENT.value
        for problem in result.problems
    )


@pytest.mark.parametrize("wrapper", ["credits", "count"])
def test_zero_bound_unknown_extent_wrappers_preserve_unpaid_sibling(wrapper: str) -> None:
    inner = _opaque_module(
        "module-inner", module_rule(ModuleRuleType.COURSE_UNIT_RULE, referenced_group_id="member")
    )
    child = module_rule(ModuleRuleType.MODULE_RULE, referenced_group_id="module-inner")
    bound = (
        module_rule(ModuleRuleType.CREDITS_RULE, credits_min="0", children=(child,))
        if wrapper == "credits"
        else module_rule(ModuleRuleType.COURSE_UNIT_COUNT_RULE, count_min=0, children=(child,))
    )
    trivial = _opaque_module("module-trivial", bound)
    root = _opaque_course_root(
        "trivial-root",
        prerequisite_module_member(0, "module-trivial"),
        prerequisite_course_member(1, "unpaid"),
    )
    tree = _compile_opaque_root(
        root,
        (inner, trivial),
        (catalogue_course("member"), catalogue_course("unpaid")),
        completed_node_keys=("module:module-inner",),
    ).tree
    result = calculate_minimum_new_credits(tree, [], completed_group_ids=[])
    assert result.state is PrerequisitePathState.EXACT
    assert result.total_new_credits == Decimal("5")
    assert selected_group_ids(result) == ("unpaid",)
    assert not any(
        problem.reason == UnresolvedPrerequisiteReason.UNKNOWN_CREDIT_EXTENT.value
        for problem in result.problems
    )
    greedy = calculate_minimum_new_credits(tree, [], completed_group_ids=[], max_compact_nodes=1)
    assert greedy.state is PrerequisitePathState.APPROXIMATE
    assert selected_group_ids(greedy) == ("unpaid",)


def test_bounded_unknown_extent_with_unpaid_sibling_is_unresolved() -> None:
    inner = _opaque_module(
        "module-inner", module_rule(ModuleRuleType.COURSE_UNIT_RULE, referenced_group_id="member")
    )
    bounded = _opaque_module(
        "module-trivial",
        module_rule(
            ModuleRuleType.CREDITS_RULE,
            credits_min="5",
            children=(module_rule(ModuleRuleType.MODULE_RULE, referenced_group_id="module-inner"),),
        ),
    )
    root = _opaque_course_root(
        "trivial-root",
        prerequisite_module_member(0, "module-trivial"),
        prerequisite_course_member(1, "unpaid"),
    )
    tree = _compile_opaque_root(
        root,
        (inner, bounded),
        (catalogue_course("member"), catalogue_course("unpaid")),
        completed_node_keys=("module:module-inner",),
    ).tree
    result = calculate_minimum_new_credits(tree, [], completed_group_ids=[])
    assert result.state is PrerequisitePathState.UNRESOLVED
    assert any(
        problem.reason == UnresolvedPrerequisiteReason.UNKNOWN_CREDIT_EXTENT.value
        for problem in result.problems
    )


@pytest.mark.parametrize("completed_kind", ["module", "credit_rule"])
def test_known_completed_extent_satisfies_credit_bound_without_member_courses(
    completed_kind: str,
) -> None:
    inner = _opaque_module(
        "module-known",
        (
            module_rule(ModuleRuleType.COURSE_UNIT_RULE, referenced_group_id="member")
            if completed_kind == "module"
            else module_rule(
                ModuleRuleType.CREDITS_RULE,
                credits_min="10",
                children=(
                    module_rule(ModuleRuleType.COURSE_UNIT_RULE, referenced_group_id="member"),
                ),
            )
        ),
        credits="10",
    )
    outer = _opaque_module(
        "module-known-outer",
        module_rule(
            ModuleRuleType.CREDITS_RULE,
            credits_min="10",
            children=(module_rule(ModuleRuleType.MODULE_RULE, referenced_group_id="module-known"),),
        ),
    )
    root = _opaque_course_root(
        "known-root",
        prerequisite_module_member(0, "module-known-outer"),
        prerequisite_course_member(1, "unpaid"),
    )
    compilation = _compile_opaque_root(
        root,
        (inner, outer),
        (catalogue_course("member"), catalogue_course("unpaid")),
    )
    tree = compilation.tree
    completed_key = next(
        occurrence.action_key
        for occurrence in tree.node_occurrences
        if occurrence.occurrence_id == ("r.0.0.0" if completed_kind == "module" else "r.0.0.0.0")
    )
    tree = _compile_opaque_root(
        root,
        (inner, outer),
        (catalogue_course("member"), catalogue_course("unpaid")),
        completed_node_keys=(completed_key,),
    ).tree
    result = calculate_minimum_new_credits(tree, [], completed_group_ids=[])
    assert result.state is PrerequisitePathState.EXACT
    assert result.total_new_credits == Decimal("5")
    assert selected_group_ids(result) == ("unpaid",)
    assert not any(
        problem.reason == UnresolvedPrerequisiteReason.UNKNOWN_CREDIT_EXTENT.value
        for problem in result.problems
    )
    greedy = calculate_minimum_new_credits(tree, [], completed_group_ids=[], max_compact_nodes=1)
    assert greedy.state is PrerequisitePathState.APPROXIMATE
    assert greedy.total_new_credits == Decimal("5")
    assert selected_group_ids(greedy) == ("unpaid",)
    assert greedy.new_opaque_work == ()


def test_known_alternative_survives_unknown_count_option() -> None:
    unknown = _opaque_module(
        "module-unknown",
        module_rule(
            ModuleRuleType.COURSE_UNIT_COUNT_RULE,
            count_min=1,
            children=(module_rule(ModuleRuleType.ANY_COURSE_UNIT_RULE),),
        ),
    )
    root = catalogue_course(
        "unknown-alt-root",
        prerequisite_options=(
            prerequisite_option(
                0,
                PrerequisiteRequirementKind.COMPULSORY,
                prerequisite_course_member(0, "known-alt"),
            ),
            prerequisite_option(
                1,
                PrerequisiteRequirementKind.COMPULSORY,
                prerequisite_module_member(0, "module-unknown"),
            ),
        ),
    )
    result = calculate_minimum_new_credits(
        _compile_opaque_root(root, (unknown,), (catalogue_course("known-alt"),)).tree,
        ["known-alt"],
        completed_group_ids=["known-alt"],
    )
    assert result.state is PrerequisitePathState.EXACT
    assert result.total_new_credits == Decimal("0")
    assert selected_group_ids(result) == ()


def test_duplicate_recommended_occurrence_route_matches_a_fixture_without_the_duplicate() -> None:
    """A fixture with a duplicate recommended occurrence charges the same total and selects the same courses as a fixture without the duplicate."""
    duplicated_root = catalogue_course(
        "duplicated-root",
        prerequisite_options=(
            prerequisite_option(
                0, PrerequisiteRequirementKind.COMPULSORY, prerequisite_course_member(0, "head")
            ),
            prerequisite_option(
                1, PrerequisiteRequirementKind.RECOMMENDED, prerequisite_course_member(0, "head")
            ),
            prerequisite_option(
                2, PrerequisiteRequirementKind.RECOMMENDED, prerequisite_course_member(0, "head")
            ),
        ),
    )
    without_duplicate_root = catalogue_course(
        "plain-root",
        prerequisite_options=(
            prerequisite_option(
                0, PrerequisiteRequirementKind.COMPULSORY, prerequisite_course_member(0, "head")
            ),
            prerequisite_option(
                1, PrerequisiteRequirementKind.RECOMMENDED, prerequisite_course_member(0, "head")
            ),
        ),
    )
    head = catalogue_course(
        "head",
        prerequisite_options=(
            prerequisite_option(
                0,
                PrerequisiteRequirementKind.COMPULSORY,
                prerequisite_course_member(0, "head-prereq"),
            ),
        ),
    )
    courses = (duplicated_root, without_duplicate_root, head, catalogue_course("head-prereq"))
    duplicated_result = calculate_minimum_new_credits(
        PrerequisiteGraphCompiler(
            FakeCurriculumRead(courses),
            RecordingInferredSetRead(),
            RecordingEquivalenceGroupRead(),
        )
        .compile("duplicated-root", include_recommended=True)
        .tree,
        [],
        completed_group_ids=[],
    )
    without_duplicate_result = calculate_minimum_new_credits(
        PrerequisiteGraphCompiler(
            FakeCurriculumRead(courses),
            RecordingInferredSetRead(),
            RecordingEquivalenceGroupRead(),
        )
        .compile("plain-root", include_recommended=True)
        .tree,
        [],
        completed_group_ids=[],
    )
    assert duplicated_result.state is PrerequisitePathState.EXACT
    assert duplicated_result.state is without_duplicate_result.state
    assert duplicated_result.total_new_credits == without_duplicate_result.total_new_credits
    assert selected_group_ids(duplicated_result) == selected_group_ids(without_duplicate_result)
