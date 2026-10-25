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
    UnresolvedPrerequisiteReason,
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
    child_uses,
    issues,
    module_rule,
    module_version,
    piece_of,
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
    inlined_root = compilation.solver.root_use_id
    assert inlined_root is not None
    inlined = piece_of(compilation.solver, inlined_root)
    assert inlined.kind == "module_block"
    assert inlined.module_group_id == "module-holder"
    inlined_leaf = piece_of(compilation.solver, child_uses(compilation.solver, inlined_root)[0])
    assert inlined_leaf.kind == "course"
    assert inlined_leaf.course_group_id == "module-inactive"
    assert "hidden-child" not in {summary.group_id for summary in compilation.solver.courses}
    assert "hidden-substitute" not in {summary.group_id for summary in compilation.solver.courses}

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
    direct_root = direct.solver.root_use_id
    assert direct_root is not None
    direct_rule = piece_of(direct.solver, direct_root)
    assert direct_rule.kind == "module_block"
    direct_unresolved = piece_of(direct.solver, child_uses(direct.solver, direct_root)[0])
    assert direct_unresolved.kind == "unresolved"
    assert direct_unresolved.reason is UnresolvedPrerequisiteReason.MODULE_CYCLE.value

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
    backedge_root = backedge.solver.root_use_id
    assert backedge_root is not None
    assert piece_of(backedge.solver, backedge_root).kind == "module_block"
    backedge_branch = piece_of(backedge.solver, child_uses(backedge.solver, backedge_root)[0])
    assert backedge_branch.kind == "expanded_course"
    backedge_course_use, backedge_cycle_use = child_uses(
        backedge.solver, child_uses(backedge.solver, backedge_root)[0]
    )
    backedge_course_leaf = piece_of(backedge.solver, backedge_course_use)
    backedge_cycle = piece_of(backedge.solver, backedge_cycle_use)
    assert backedge_course_leaf.kind == "course"
    assert backedge_course_leaf.course_group_id == "module-back-course"
    assert backedge_cycle.kind == "unresolved"
    assert backedge_cycle.reason is UnresolvedPrerequisiteReason.MODULE_CYCLE.value

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
    cycle_issues = issues(cycle_compilation.solver)
    assert len(cycle_issues) == 1
    assert cycle_issues[0].kind == "course_cycle"
