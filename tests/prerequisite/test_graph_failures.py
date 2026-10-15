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
    ComposedOrRole,
    InferredPrerequisiteCategory,
    OfficialPrerequisiteKind,
    OrRequirement,
    PrerequisiteOrigin,
    UnresolvedPrerequisiteReason,
    expression_course_leaf_group_ids,
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
    current_result,
    inferred_course,
    module_rule,
    module_version,
    official_course,
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
    tree = compilation.tree
    assert tree.requirements == official_course("real-member")
    assert tree.issues == ()
    assert "self-root" not in expression_course_leaf_group_ids(tree.requirements)
    assert self_read.reads == []
    # No self edge and no self summary beyond the represented root course.
    assert not any(
        edge.source_node_id == "course:self-root" and edge.target_node_id == "course:self-root"
        for edge in compilation.graph.edges
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
    assert empty_root.tree.requirements is None
    assert empty_root.tree.issues == ()
    assert empty_root.graph.edges == ()

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
    assert mixed_root.tree.requirements == official_course("survivor")
    assert mixed_root.tree.issues == ()

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
    assert inferred_compilation.tree.requirements == inferred_course("inferred-real")
    assert inferred_compilation.tree.issues == ()
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
    substitution = substitution_compilation.tree.requirements
    assert isinstance(substitution, OrRequirement)
    assert substitution.origin is PrerequisiteOrigin.COMPOSED
    assert substitution.composed_role is ComposedOrRole.COURSE_ALTERNATIVES
    original_branch, substitute_branch = substitution.children
    assert original_branch == official_course("sub-owner")
    assert substitute_branch == official_course("substitute", OfficialPrerequisiteKind.SUBSTITUTION)
    assert substitution_compilation.tree.issues == ()

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
    indirect_issues = indirect.tree.issues
    assert len(indirect_issues) == 1
    assert indirect_issues[0].reason is UnresolvedPrerequisiteReason.COURSE_CYCLE
    assert indirect_issues[0].course_group_path == ("indirect-a", "indirect-b", "indirect-a")

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
    assert module_self_compilation.tree.requirements is None
    assert module_self_compilation.tree.issues == ()
    assert module_self_read.reads == ["module-self-root"]
    assert module_self_equivalence.reads == []
    assert module_self_compilation.graph.edges == ()
    assert {node.course.group_id for node in module_self_compilation.graph.course_nodes} == {
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
    assert len(module_back_compilation.tree.issues) == 1
    back_issue = module_back_compilation.tree.issues[0]
    assert back_issue.reason is UnresolvedPrerequisiteReason.COURSE_CYCLE
    assert back_issue.course_group_path == ("module-back-root", "mid-course", "module-back-root")


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
    assert all_courses.tree.inferred_coverage == ()
    assert active_only.tree.inferred_coverage == ()
    assert all_courses.tree.active_only is False
    assert active_only.tree.active_only is True

    # All-course scope represents the inactive root and both official leaves of its own structure.
    all_requirements = all_courses.tree.requirements
    assert isinstance(all_requirements, AndRequirement)
    assert all_requirements.origin is PrerequisiteOrigin.COMPOSED
    assert all(child.origin is PrerequisiteOrigin.OFFICIAL for child in all_requirements.children)
    assert {summary.group_id for summary in all_courses.tree.courses} == {
        "inactive-root",
        "inactive-child",
        "inactive-recommended",
    }
    # An inactive non-root member of the root's own structure is a leaf.
    inactive_leaf = next(
        summary for summary in all_courses.tree.courses if summary.group_id == "inactive-child"
    )
    assert inactive_leaf.is_active is False
    assert "hidden-grandchild" not in {summary.group_id for summary in all_courses.tree.courses}
    assert "hidden-substitute" not in {summary.group_id for summary in all_courses.tree.courses}
    assert {node.course.group_id for node in all_courses.graph.course_nodes} == {
        "inactive-root",
        "inactive-child",
        "inactive-recommended",
    }

    # Active-only drops the two unretained inactive non-root members, so the inactive root represents
    # only itself and compiles to no requirement.
    assert active_only.tree.requirements is None
    assert {summary.group_id for summary in active_only.tree.courses} == {"inactive-root"}
    assert {node.course.group_id for node in active_only.graph.course_nodes} == {"inactive-root"}
