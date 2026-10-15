"""Module expansion guards and course/module cycle detection."""

from __future__ import annotations

from course_explorer.curriculum import (
    CatalogueCurriculumPeriod,
)
from course_explorer.enums import (
    ModuleRuleType,
    PrerequisiteRequirementKind,
)
from course_explorer.prerequisite.domain import (
    AndRequirement,
    CourseRequirement,
    ModuleBlockRequirement,
    UnresolvedPrerequisiteReason,
    UnresolvedRequirement,
)
from course_explorer.prerequisite.graph import (
    PrerequisiteGraphCompiler,
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
    substitution_option,
)


def test_module_expansion_preserves_course_guards_and_detects_course_and_module_cycles() -> None:
    """Module expansion keeps inactive leaves and terminates on course and module cycles."""
    year_period = (CatalogueCurriculumPeriod(id="period-2026", academic_year_start=2026),)
    # An inactive course emitted by a module is a leaf: no children, substitutions, or reads.
    inactive_rule = module_rule(
        ModuleRuleType.COURSE_UNIT_RULE, referenced_group_id="module-inactive"
    )
    root = catalogue_course(
        "root",
        prerequisite_options=(
            prerequisite_option(
                0,
                PrerequisiteRequirementKind.COMPULSORY,
                prerequisite_module_member(0, "module-holder"),
            ),
        ),
    )
    modules = (
        catalogue_module(
            "module-holder",
            (
                module_version(
                    "module-holder-v1", rule=inactive_rule, curriculum_periods=year_period
                ),
            ),
        ),
        catalogue_module(
            "module-loop",
            (
                module_version(
                    "module-loop-v1",
                    rule=module_rule(ModuleRuleType.MODULE_RULE, referenced_group_id="module-loop"),
                    curriculum_periods=year_period,
                ),
            ),
        ),
    )
    courses = (
        root,
        catalogue_course(
            "module-inactive",
            is_active=False,
            prerequisite_options=(
                prerequisite_option(
                    0,
                    PrerequisiteRequirementKind.COMPULSORY,
                    prerequisite_course_member(0, "hidden-child"),
                ),
            ),
            substitution_options=(substitution_option(0, ("hidden-substitute", None)),),
        ),
        catalogue_course("hidden-child"),
        catalogue_course("hidden-substitute"),
    )
    inferred_read = RecordingInferredSetRead()
    compilation = PrerequisiteGraphCompiler(
        FakeCurriculumRead(courses, modules), inferred_read, RecordingEquivalenceGroupRead()
    ).compile("root")
    assert inferred_read.reads == []
    inlined = compilation.tree.requirements
    assert isinstance(inlined, ModuleBlockRequirement)
    assert inlined.module_group_id == "module-holder"
    inlined_leaf = inlined.child
    assert isinstance(inlined_leaf, CourseRequirement)
    assert inlined_leaf.course_group_id == "module-inactive"
    assert "hidden-child" not in {summary.group_id for summary in compilation.tree.courses}
    assert "hidden-substitute" not in {summary.group_id for summary in compilation.tree.courses}

    # A direct ModuleRule self-reference terminates with a deterministic cycle diagnostic.
    direct_cycle_root = catalogue_course(
        "direct-root",
        prerequisite_options=(
            prerequisite_option(
                0,
                PrerequisiteRequirementKind.COMPULSORY,
                prerequisite_module_member(0, "module-loop"),
            ),
        ),
    )
    direct = PrerequisiteGraphCompiler(
        FakeCurriculumRead((direct_cycle_root,), modules),
        RecordingInferredSetRead(),
        RecordingEquivalenceGroupRead(),
    ).compile("direct-root")
    direct_rule = direct.tree.requirements
    assert isinstance(direct_rule, ModuleBlockRequirement)
    direct_unresolved = direct_rule.child
    assert isinstance(direct_unresolved, UnresolvedRequirement)
    assert direct_unresolved.reason is UnresolvedPrerequisiteReason.MODULE_CYCLE

    # module -> course -> module terminates with the same structured reason.
    backedge_rule = module_rule(
        ModuleRuleType.COURSE_UNIT_RULE, referenced_group_id="module-back-course"
    )
    backedge_root = catalogue_course(
        "back-root",
        prerequisite_options=(
            prerequisite_option(
                0,
                PrerequisiteRequirementKind.COMPULSORY,
                prerequisite_module_member(0, "module-back"),
            ),
        ),
    )
    backedge_modules = (
        catalogue_module(
            "module-back",
            (module_version("module-back-v1", rule=backedge_rule, curriculum_periods=year_period),),
        ),
    )
    backedge_courses = (
        backedge_root,
        catalogue_course(
            "module-back-course",
            prerequisite_options=(
                prerequisite_option(
                    0,
                    PrerequisiteRequirementKind.COMPULSORY,
                    prerequisite_module_member(0, "module-back"),
                ),
            ),
        ),
    )
    backedge = PrerequisiteGraphCompiler(
        FakeCurriculumRead(backedge_courses, backedge_modules),
        RecordingInferredSetRead(),
        RecordingEquivalenceGroupRead(),
    ).compile("back-root")
    backedge_wrapper = backedge.tree.requirements
    assert isinstance(backedge_wrapper, ModuleBlockRequirement)
    backedge_branch = backedge_wrapper.child
    assert isinstance(backedge_branch, AndRequirement)
    backedge_course_leaf, backedge_cycle = backedge_branch.children
    assert isinstance(backedge_course_leaf, CourseRequirement)
    assert backedge_course_leaf.course_group_id == "module-back-course"
    assert isinstance(backedge_cycle, UnresolvedRequirement)
    assert backedge_cycle.reason is UnresolvedPrerequisiteReason.MODULE_CYCLE

    # A module course leaf that participates in a course cycle keeps the COURSE_CYCLE issue.
    course_cycle_rule = module_rule(ModuleRuleType.COURSE_UNIT_RULE, referenced_group_id="cycle-a")
    cycle_root = catalogue_course(
        "cycle-root",
        prerequisite_options=(
            prerequisite_option(
                0,
                PrerequisiteRequirementKind.COMPULSORY,
                prerequisite_module_member(0, "module-cycle"),
            ),
        ),
    )
    cycle_modules = (
        catalogue_module(
            "module-cycle",
            (
                module_version(
                    "module-cycle-v1", rule=course_cycle_rule, curriculum_periods=year_period
                ),
            ),
        ),
    )
    cycle_courses = (
        cycle_root,
        catalogue_course(
            "cycle-a",
            prerequisite_options=(
                prerequisite_option(
                    0,
                    PrerequisiteRequirementKind.COMPULSORY,
                    prerequisite_course_member(0, "cycle-b"),
                ),
            ),
        ),
        catalogue_course(
            "cycle-b",
            prerequisite_options=(
                prerequisite_option(
                    0,
                    PrerequisiteRequirementKind.COMPULSORY,
                    prerequisite_course_member(0, "cycle-a"),
                ),
            ),
        ),
    )
    cycle_compilation = PrerequisiteGraphCompiler(
        FakeCurriculumRead(cycle_courses, cycle_modules),
        RecordingInferredSetRead(),
        RecordingEquivalenceGroupRead(),
    ).compile("cycle-root")
    issues = cycle_compilation.tree.issues
    assert len(issues) == 1
    assert issues[0].reason is UnresolvedPrerequisiteReason.COURSE_CYCLE
    assert issues[0].course_group_path == ("cycle-root", "cycle-a", "cycle-b", "cycle-a")
