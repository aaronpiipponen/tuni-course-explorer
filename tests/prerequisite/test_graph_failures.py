"""Direct self-occurrence dropping, indirect cycles, and inactive-root handling."""

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
    InferredPrerequisiteCategory,
    OfficialPrerequisiteKind,
    PrerequisiteOrigin,
)
from course_explorer.prerequisite.graph import (
    PrerequisiteGraphCompiler,
)
from tests.prerequisite._graph_support import (
    INFERENCE_METADATA,
    FakeCurriculumRead,
    RecordingEquivalenceGroupRead,
    RecordingInferredSetRead,
    catalogue_course,
    catalogue_module,
    child_uses,
    course_nodes,
    current_result,
    fact_of,
    inferred_course,
    issues,
    leaf_group_ids,
    module_rule,
    module_version,
    piece_of,
    prerequisite_course_member,
    prerequisite_module_member,
    prerequisite_option,
    substitution_option,
)


def test_compiler_drops_direct_self_occurrences_but_preserves_indirect_cycles() -> None:
    """A direct self occurrence disappears. Genuine indirect cycles keep their issues."""
    # A compilable course whose only option is a self AND a real member drops the self occurrence.
    courses = (
        catalogue_course(
            "self-root",
            prerequisite_options=(
                prerequisite_option(
                    0,
                    PrerequisiteRequirementKind.COMPULSORY,
                    prerequisite_course_member(0, "self-root"),
                    prerequisite_course_member(1, "real-member"),
                ),
            ),
        ),
        catalogue_course("real-member"),
    )
    self_read = RecordingInferredSetRead()
    compiler = PrerequisiteGraphCompiler(
        FakeCurriculumRead(courses), self_read, RecordingEquivalenceGroupRead()
    )

    compilation = compiler.compile("self-root")
    tree = compilation.solver
    assert tree.root_use_id is not None
    root_piece = piece_of(tree, tree.root_use_id)
    assert root_piece.kind == "course"
    assert root_piece.course_group_id == "real-member"
    assert issues(tree) == ()
    assert "self-root" not in leaf_group_ids(tree, tree.root_use_id)
    assert self_read.reads == []
    # No self edge and no self summary beyond the represented root course.
    assert not any(
        edge.source_node_id == "course:self-root" and edge.target_node_id == "course:self-root"
        for edge in compilation.display.edges
    )
    assert {course.group_id for course in tree.courses} == {"self-root", "real-member"}

    # A self-only option disappears. With no other option the compulsory contribution is absent.
    empty_root = PrerequisiteGraphCompiler(
        FakeCurriculumRead(
            (
                catalogue_course(
                    "empty-root",
                    prerequisite_options=(
                        prerequisite_option(
                            0,
                            PrerequisiteRequirementKind.COMPULSORY,
                            prerequisite_course_member(0, "empty-root"),
                        ),
                    ),
                ),
            )
        ),
        RecordingInferredSetRead(),
        RecordingEquivalenceGroupRead(),
    ).compile("empty-root")
    assert empty_root.solver.root_use_id is None
    assert issues(empty_root.solver) == ()
    assert empty_root.display.edges == ()

    # A self-only option beside a real option disappears while the real option collapses normally.
    mixed_root = PrerequisiteGraphCompiler(
        FakeCurriculumRead(
            (
                catalogue_course(
                    "mixed-root",
                    prerequisite_options=(
                        prerequisite_option(
                            0,
                            PrerequisiteRequirementKind.COMPULSORY,
                            prerequisite_course_member(0, "mixed-root"),
                        ),
                        prerequisite_option(
                            1,
                            PrerequisiteRequirementKind.COMPULSORY,
                            prerequisite_course_member(0, "survivor"),
                        ),
                    ),
                ),
                catalogue_course("survivor"),
            )
        ),
        RecordingInferredSetRead(),
        RecordingEquivalenceGroupRead(),
    ).compile("mixed-root")
    assert mixed_root.solver.root_use_id is not None
    mixed_piece = piece_of(mixed_root.solver, mixed_root.solver.root_use_id)
    assert mixed_piece.kind == "course" and mixed_piece.course_group_id == "survivor"
    assert issues(mixed_root.solver) == ()

    # An inferred connector containing the immediate owner is filtered and collapses to the real
    # member. The owner's own inferred read is the only read and no cycle issue is emitted.
    inferred_read = RecordingInferredSetRead(
        {
            "inferred-root": current_result(
                "inferred-root",
                expression=AndRequirement(
                    type="and",
                    origin=PrerequisiteOrigin.INFERRED,
                    inferred_category=InferredPrerequisiteCategory.REQUIRED,
                    inference=INFERENCE_METADATA,
                    children=(
                        inferred_course("inferred-root"),
                        inferred_course("inferred-real"),
                    ),
                ),
            ),
            "inferred-real": current_result("inferred-real"),
        }
    )
    inferred_compilation = PrerequisiteGraphCompiler(
        FakeCurriculumRead((catalogue_course("inferred-root"), catalogue_course("inferred-real"))),
        inferred_read,
        RecordingEquivalenceGroupRead(),
    ).compile("inferred-root", include_inferred=True)
    inferred_root = inferred_compilation.solver.root_use_id
    assert inferred_root is not None
    inferred_piece = piece_of(inferred_compilation.solver, inferred_root)
    inferred_fact = fact_of(inferred_compilation.solver, inferred_root)
    assert inferred_piece.kind == "course" and inferred_piece.course_group_id == "inferred-real"
    assert inferred_fact.origin is PrerequisiteOrigin.INFERRED
    assert issues(inferred_compilation.solver) == ()
    assert inferred_read.reads == ["inferred-root", "inferred-real"]

    # A substitution member equal to its immediate owning course is dropped. The option emptied
    # only by that self occurrence disappears while the real option holds.
    substitution_compilation = PrerequisiteGraphCompiler(
        FakeCurriculumRead(
            (
                catalogue_course(
                    "sub-root",
                    prerequisite_options=(
                        prerequisite_option(
                            0,
                            PrerequisiteRequirementKind.COMPULSORY,
                            prerequisite_course_member(0, "sub-owner"),
                        ),
                    ),
                ),
                catalogue_course(
                    "sub-owner",
                    substitution_options=(
                        substitution_option(0, ("sub-owner", None)),
                        substitution_option(1, ("substitute", None)),
                    ),
                ),
                catalogue_course("substitute"),
            )
        ),
        RecordingInferredSetRead(),
        RecordingEquivalenceGroupRead(),
    ).compile("sub-root")
    substitution_root = substitution_compilation.solver.root_use_id
    assert substitution_root is not None
    assert piece_of(substitution_compilation.solver, substitution_root).kind == (
        "course_alternatives"
    )
    original_branch, substitute_branch = child_uses(
        substitution_compilation.solver, substitution_root
    )
    original_piece = piece_of(substitution_compilation.solver, original_branch)
    substitute_piece = piece_of(substitution_compilation.solver, substitute_branch)
    substitute_fact = fact_of(substitution_compilation.solver, substitute_branch)
    assert original_piece.kind == "course" and original_piece.course_group_id == "sub-owner"
    assert substitute_piece.kind == "course" and substitute_piece.course_group_id == "substitute"
    assert substitute_fact.official_kind is OfficialPrerequisiteKind.SUBSTITUTION
    assert issues(substitution_compilation.solver) == ()

    # Unlike the self-only cases above, a genuine A -> B -> A back-edge keeps its complete-path
    # COURSE_CYCLE blocker exactly.
    indirect = PrerequisiteGraphCompiler(
        FakeCurriculumRead(
            (
                catalogue_course(
                    "indirect-a",
                    prerequisite_options=(
                        prerequisite_option(
                            0,
                            PrerequisiteRequirementKind.COMPULSORY,
                            prerequisite_course_member(0, "indirect-b"),
                        ),
                    ),
                ),
                catalogue_course(
                    "indirect-b",
                    prerequisite_options=(
                        prerequisite_option(
                            0,
                            PrerequisiteRequirementKind.COMPULSORY,
                            prerequisite_course_member(0, "indirect-a"),
                        ),
                    ),
                ),
            )
        ),
        RecordingInferredSetRead(),
        RecordingEquivalenceGroupRead(),
    ).compile("indirect-a")
    indirect_issues = issues(indirect.solver)
    assert len(indirect_issues) == 1
    assert indirect_issues[0].kind == "course_cycle"

    # A direct module `CourseUnitRule` naming its immediate owning course is dropped like a direct
    # self occurrence: no edge, issue, or equivalence read, and only the root's own inferred read.
    year_period = (CatalogueCurriculumPeriod(id="period-2026", academic_year_start=2026),)
    module_self_root = catalogue_course(
        "module-self-root",
        prerequisite_options=(
            prerequisite_option(
                0,
                PrerequisiteRequirementKind.COMPULSORY,
                prerequisite_module_member(0, "module-self"),
            ),
        ),
    )
    module_self = catalogue_module(
        "module-self",
        (
            module_version(
                "module-self-v1",
                rule=module_rule(
                    ModuleRuleType.COURSE_UNIT_RULE, referenced_group_id="module-self-root"
                ),
                curriculum_periods=year_period,
            ),
        ),
    )
    module_self_read = RecordingInferredSetRead(
        {"module-self-root": current_result("module-self-root")}
    )
    module_self_equivalence = RecordingEquivalenceGroupRead()
    module_self_compilation = PrerequisiteGraphCompiler(
        FakeCurriculumRead((module_self_root,), (module_self,)),
        module_self_read,
        module_self_equivalence,
    ).compile("module-self-root", include_inferred=True)
    assert module_self_compilation.solver.root_use_id is None
    assert issues(module_self_compilation.solver) == ()
    assert module_self_read.reads == ["module-self-root"]
    assert module_self_equivalence.reads == []
    assert module_self_compilation.display.edges == ()
    assert {node.course_group_id for node in course_nodes(module_self_compilation.display)} == {
        "module-self-root"
    }

    # An earlier, non-immediate ancestor emitted by a module rule keeps its complete-path cycle issue:
    # root -> mid-course -> (module rule names root) is a genuine indirect cycle.
    module_back = catalogue_module(
        "module-back",
        (
            module_version(
                "module-back-v1",
                rule=module_rule(
                    ModuleRuleType.COURSE_UNIT_RULE, referenced_group_id="module-back-root"
                ),
                curriculum_periods=year_period,
            ),
        ),
    )
    module_back_root = catalogue_course(
        "module-back-root",
        prerequisite_options=(
            prerequisite_option(
                0,
                PrerequisiteRequirementKind.COMPULSORY,
                prerequisite_course_member(0, "mid-course"),
            ),
        ),
    )
    mid_course = catalogue_course(
        "mid-course",
        prerequisite_options=(
            prerequisite_option(
                0,
                PrerequisiteRequirementKind.COMPULSORY,
                prerequisite_module_member(0, "module-back"),
            ),
        ),
    )
    module_back_compilation = PrerequisiteGraphCompiler(
        FakeCurriculumRead((module_back_root, mid_course), (module_back,)),
        RecordingInferredSetRead(),
        RecordingEquivalenceGroupRead(),
    ).compile("module-back-root")
    assert len(issues(module_back_compilation.solver)) == 1
    back_issue = issues(module_back_compilation.solver)[0]
    assert back_issue.kind == "course_cycle"


def test_inactive_root_compiles_official_structure_and_active_only_drops_unretained_members() -> (
    None
):
    """An explicitly opened inactive root compiles its own official structure, and active-only drops its unretained members."""
    courses = (
        catalogue_course(
            "inactive-root",
            is_active=False,
            prerequisite_options=(
                prerequisite_option(
                    0,
                    PrerequisiteRequirementKind.COMPULSORY,
                    prerequisite_course_member(0, "inactive-child"),
                ),
                prerequisite_option(
                    0,
                    PrerequisiteRequirementKind.RECOMMENDED,
                    prerequisite_course_member(0, "inactive-recommended"),
                ),
            ),
        ),
        # An inactive non-root member is a leaf: its own prerequisites and substitutions never
        # enter the tree even though the root itself compiles its official structure.
        catalogue_course(
            "inactive-child",
            is_active=False,
            prerequisite_options=(
                prerequisite_option(
                    0,
                    PrerequisiteRequirementKind.COMPULSORY,
                    prerequisite_course_member(0, "hidden-grandchild"),
                ),
            ),
            substitution_options=(substitution_option(0, ("hidden-substitute", None)),),
        ),
        catalogue_course("inactive-recommended", is_active=False),
        catalogue_course("hidden-grandchild"),
        catalogue_course("hidden-substitute"),
    )
    inferred_read = RecordingInferredSetRead(
        {
            "inactive-root": current_result("inactive-root"),
            "inactive-child": current_result("inactive-child"),
            "inactive-recommended": current_result("inactive-recommended"),
        }
    )
    compiler = PrerequisiteGraphCompiler(
        FakeCurriculumRead(courses), inferred_read, RecordingEquivalenceGroupRead()
    )

    all_courses = compiler.compile("inactive-root", include_inferred=True, include_recommended=True)
    active_only = compiler.compile(
        "inactive-root",
        include_inferred=True,
        include_recommended=True,
        active_only=True,
    )

    # Both scopes compile the root's own official structure and never read an inferred set.
    assert inferred_read.reads == []
    assert all_courses.solver.inferred_coverage == ()
    assert active_only.solver.inferred_coverage == ()
    assert all_courses.solver.active_only is False
    assert active_only.solver.active_only is True

    # All-course scope represents the inactive root and both official leaves of its own structure.
    all_root = all_courses.solver.root_use_id
    assert all_root is not None
    assert piece_of(all_courses.solver, all_root).kind == "and"
    all_children = child_uses(all_courses.solver, all_root)
    assert all(
        fact_of(all_courses.solver, child).origin is PrerequisiteOrigin.OFFICIAL
        for child in all_children
    )
    assert {summary.group_id for summary in all_courses.solver.courses} == {
        "inactive-root",
        "inactive-child",
        "inactive-recommended",
    }
    # An inactive non-root member of the root's own structure is a leaf.
    inactive_leaf = next(
        summary for summary in all_courses.solver.courses if summary.group_id == "inactive-child"
    )
    assert inactive_leaf.is_active is False
    assert "hidden-grandchild" not in {summary.group_id for summary in all_courses.solver.courses}
    assert "hidden-substitute" not in {summary.group_id for summary in all_courses.solver.courses}
    assert {node.course_group_id for node in course_nodes(all_courses.display)} == {
        "inactive-root",
        "inactive-child",
        "inactive-recommended",
    }

    # Active-only drops the two unretained inactive non-root members, so the inactive root represents
    # only itself and compiles to no requirement.
    assert active_only.solver.root_use_id is None
    assert {summary.group_id for summary in active_only.solver.courses} == {"inactive-root"}
    assert {node.course_group_id for node in course_nodes(active_only.display)} == {"inactive-root"}
