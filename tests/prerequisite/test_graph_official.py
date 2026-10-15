"""Official prerequisite compilation: direct, recommended, and directional substitutions."""

from __future__ import annotations

from course_explorer.enums import PrerequisiteRequirementKind
from course_explorer.prerequisite.domain import (
    AndRequirement,
    ComposedAndRole,
    ComposedOrRole,
    CourseRequirement,
    OfficialPrerequisiteKind,
    OrRequirement,
    PrerequisiteOrigin,
    expression_course_leaf_group_ids,
)
from course_explorer.prerequisite.graph import (
    PrerequisiteGraphCompiler,
)
from tests.prerequisite._graph_support import (
    FakeCurriculumRead,
    RecordingEquivalenceGroupRead,
    RecordingInferredSetRead,
    catalogue_course,
    official_course,
    prerequisite_course_member,
    prerequisite_option,
    substitution_option,
)


def test_compiler_preserves_official_or_of_and_recommended_and_directional_substitutions() -> None:
    """Source order, official provenance, and directional substitution OR-of-AND survive."""
    # Root: compulsory (A AND B) OR (C). Recommended (D) whose own compulsory child is D-child.
    root_options = (
        prerequisite_option(
            0,
            PrerequisiteRequirementKind.COMPULSORY,
            prerequisite_course_member(0, "a"),
            prerequisite_course_member(1, "b"),
        ),
        prerequisite_option(
            1,
            PrerequisiteRequirementKind.COMPULSORY,
            prerequisite_course_member(0, "c"),
        ),
        prerequisite_option(
            0,
            PrerequisiteRequirementKind.RECOMMENDED,
            prerequisite_course_member(0, "d"),
        ),
    )
    # Required course A has substitution options: (A1 AND A2) OR (A3), plus a genuinely empty option
    # and one mixing the real substitute A4 with a nonexistent member.
    a_substitutions = (
        substitution_option(0, ("a1", "3"), ("a2", None)),
        substitution_option(1, ("a3", None)),
        substitution_option(2),
        substitution_option(3, ("a4", None), ("missing-sub", None)),
    )
    courses = (
        catalogue_course("root", prerequisite_options=root_options),
        catalogue_course("a", substitution_options=a_substitutions),
        catalogue_course("b"),
        catalogue_course("c"),
        catalogue_course(
            "d",
            prerequisite_options=(
                prerequisite_option(
                    0,
                    PrerequisiteRequirementKind.COMPULSORY,
                    prerequisite_course_member(0, "d-child"),
                ),
            ),
        ),
        catalogue_course("d-child"),
        # A1 has its own ordinary prerequisite E and its own substitution option X.
        # Substitution chaining must not pull X in for the A occurrence.
        catalogue_course(
            "a1",
            prerequisite_options=(
                prerequisite_option(
                    0,
                    PrerequisiteRequirementKind.COMPULSORY,
                    prerequisite_course_member(0, "e"),
                ),
            ),
            substitution_options=(substitution_option(0, ("x", None)),),
        ),
        catalogue_course("a2"),
        catalogue_course("a3"),
        catalogue_course("a4"),
        catalogue_course("e"),
        catalogue_course("x"),
    )
    curriculum = FakeCurriculumRead(courses)
    inferred_read = RecordingInferredSetRead()
    compiler = PrerequisiteGraphCompiler(curriculum, inferred_read, RecordingEquivalenceGroupRead())

    # Default (recommended disabled): the recommended branch is pruned whole before traversal, so D
    # and its child never enter the tree, the drawing graph, or the requested course reads, and no
    # inferred set is read for it.
    disabled = compiler.compile("root")
    disabled_tree = disabled.tree
    assert disabled_tree.include_recommended is False
    disabled_groups = {course.group_id for course in disabled_tree.courses}
    assert "d" not in disabled_groups
    assert "d-child" not in disabled_groups
    assert "d" not in {node.course.group_id for node in disabled.graph.course_nodes}
    assert "d-child" not in {node.course.group_id for node in disabled.graph.course_nodes}
    requested = {group_id for batch in curriculum.course_reads for group_id in batch}
    assert "d" not in requested
    assert "d-child" not in requested
    assert inferred_read.reads == []

    # Enabled: the recommended branch expands D with its own compulsory child.
    compilation = compiler.compile("root", include_recommended=True)
    tree = compilation.tree
    requirements = tree.requirements
    # Compulsory and recommended roots stay distinct and join only through one composed AND.
    assert isinstance(requirements, AndRequirement)
    assert requirements.origin is PrerequisiteOrigin.COMPOSED
    assert requirements.official_kind is None
    assert requirements.inference is None

    compulsory_or, recommended_or = requirements.children
    assert isinstance(compulsory_or, OrRequirement)
    assert compulsory_or.origin is PrerequisiteOrigin.OFFICIAL
    assert compulsory_or.official_kind is OfficialPrerequisiteKind.COMPULSORY
    first_option, second_option = compulsory_or.children
    # Option order is retained. A singleton source option collapses to its bare member leaf.
    assert isinstance(first_option, AndRequirement)
    assert first_option.official_kind is OfficialPrerequisiteKind.COMPULSORY
    assert second_option == official_course("c")

    a_branch = first_option.children[0]
    # Taking A is `And(composed, (A leaf, its child requirements))`. A has no ordinary
    # prerequisites, so the leaf remains and substitutions wrap it in an OR.
    assert isinstance(a_branch, OrRequirement)
    assert a_branch.origin is PrerequisiteOrigin.COMPOSED
    original_leaf, option_one, option_two = a_branch.children
    assert original_leaf == official_course("a", OfficialPrerequisiteKind.COMPULSORY)
    assert isinstance(option_one, AndRequirement)
    assert option_one.origin is PrerequisiteOrigin.OFFICIAL
    assert option_one.official_kind is OfficialPrerequisiteKind.SUBSTITUTION
    option_one_courses = [expression_course_leaf_group_ids(child) for child in option_one.children]
    assert option_one_courses == [{"a1", "e"}, {"a2"}]
    a2_leaf = option_one.children[1]
    assert isinstance(a2_leaf, CourseRequirement)
    assert a2_leaf.origin is PrerequisiteOrigin.OFFICIAL
    assert a2_leaf.official_kind is OfficialPrerequisiteKind.SUBSTITUTION
    # A single-member substitution option collapses to its bare member leaf.
    assert option_two == official_course("a3", OfficialPrerequisiteKind.SUBSTITUTION)

    # The empty option and the option mixing the real substitute A4 with a nonexistent member are
    # dropped whole and disclosed. A holds, and no partial substitute becomes usable.
    assert "a4" not in {summary.group_id for summary in tree.courses}
    assert "missing-sub" not in {summary.group_id for summary in tree.courses}
    assert [part.kind.value for part in tree.ignored_parts] == [
        "empty_option",
        "missing_substitution_course",
    ]
    assert tree.ignored_parts[0].official_kind is OfficialPrerequisiteKind.SUBSTITUTION
    assert tree.ignored_parts[1].referenced_group_ids == ("a4", "missing-sub")
    assert tree.ignored_parts[1].detail == "substitution option 3 dropped: missing missing-sub"

    # A1's ordinary prerequisite E expands. Its own substitution X does not chain back.
    a1_branch = option_one.children[0]
    assert isinstance(a1_branch, AndRequirement)
    assert a1_branch.origin is PrerequisiteOrigin.COMPOSED
    a1_leaf, a1_children = a1_branch.children
    assert a1_leaf == official_course("a1", OfficialPrerequisiteKind.SUBSTITUTION)
    assert "x" not in {summary.group_id for summary in tree.courses}
    assert "x" not in str(a1_children)
    assert "e" in {summary.group_id for summary in tree.courses}

    # Recommended provenance is distinct when the recommended input is enabled. D expands its
    # own compulsory child as an ordinary descendant.
    assert isinstance(recommended_or, AndRequirement)
    assert recommended_or.origin is PrerequisiteOrigin.COMPOSED
    assert recommended_or.composed_role is ComposedAndRole.EXPANDED_COURSE
    assert recommended_or.children[0] == official_course("d", OfficialPrerequisiteKind.RECOMMENDED)
    assert recommended_or.children[1] == official_course("d-child")
    assert "d-child" in {summary.group_id for summary in tree.courses}

    # Projection keeps substitutions directional OR-of-AND rather than flattened equivalence.
    substitution_members = [
        member
        for edge in compilation.graph.edges
        for member in edge.relationships
        if member.official_kind is OfficialPrerequisiteKind.SUBSTITUTION
    ]
    assert substitution_members

    # E is reached only through A1's expansion and is not a direct root prerequisite.
    assert not any(
        edge.source_node_id == "course:root" and edge.target_node_id == "course:e"
        for edge in compilation.graph.edges
    )
    assert inferred_read.reads == []

    # Direct-many on the same fixture keeps separate category roots, preserves directional
    # substitutions, stops ordinary course ancestors (d-child/e absent) and leaves the recursive
    # result above identical.
    direct = compiler.compile_direct_many(("root",))
    assert [entry.tree.root.group_id for entry in direct] == ["root"]
    direct_entry = direct[0]
    assert direct_entry.required is not None
    assert direct_entry.recommended is not None
    direct_groups = {course.group_id for course in direct_entry.tree.courses}
    assert {"a", "a1", "a2", "a3", "b", "c", "d"} <= direct_groups
    assert "d-child" not in direct_groups
    assert "e" not in direct_groups
    assert "x" not in direct_groups
    assert isinstance(direct_entry.required, OrRequirement)
    first_direct_option = direct_entry.required.children[0]
    assert isinstance(first_direct_option, AndRequirement)
    direct_a_branch = first_direct_option.children[0]
    assert isinstance(direct_a_branch, OrRequirement)
    assert direct_a_branch.composed_role is ComposedOrRole.COURSE_ALTERNATIVES
    assert direct_entry.recommended == official_course("d", OfficialPrerequisiteKind.RECOMMENDED)
    assert "d-child" in {summary.group_id for summary in tree.courses}
