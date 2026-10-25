"""Official prerequisite compilation: direct, recommended, and directional substitutions."""

from __future__ import annotations

from course_explorer.enums import PrerequisiteRequirementKind
from course_explorer.prerequisite.domain import OfficialPrerequisiteKind
from course_explorer.prerequisite.graph import (
    PrerequisiteGraphCompiler,
)
from tests.prerequisite._graph_support import (
    FakeCurriculumRead,
    RecordingEquivalenceGroupRead,
    RecordingInferredSetRead,
    catalogue_course,
    child_uses,
    course_node_ids,
    fact_of,
    leaf_group_ids,
    piece_of,
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

    # Default (recommended disabled): the recommended branch is pruned whole before traversal.
    disabled = compiler.compile("root")
    disabled_solver = disabled.solver
    assert disabled_solver.include_recommended is False
    disabled_groups = {course.group_id for course in disabled_solver.courses}
    assert "d" not in disabled_groups
    assert "d-child" not in disabled_groups
    assert "d" not in course_node_ids(disabled.display)
    assert "d-child" not in course_node_ids(disabled.display)
    requested = {group_id for batch in curriculum.course_reads for group_id in batch}
    assert "d" not in requested
    assert "d-child" not in requested
    assert inferred_read.reads == []

    # Enabled: the recommended branch expands D with its own compulsory child.
    compilation = compiler.compile("root", include_recommended=True)
    structure = compilation.solver
    requirements = structure.root_use_id
    assert requirements is not None
    root_piece = piece_of(structure, requirements)
    assert root_piece.kind == "and"
    assert fact_of(structure, requirements).origin.value == "composed"
    compulsory_or, recommended_root = child_uses(structure, requirements)
    compulsory_piece = piece_of(structure, compulsory_or)
    assert compulsory_piece.kind == "or"
    compulsory_fact = fact_of(structure, compulsory_or)
    assert compulsory_fact.origin.value == "official"
    assert compulsory_fact.official_kind is OfficialPrerequisiteKind.COMPULSORY
    first_option, second_option = child_uses(structure, compulsory_or)
    assert piece_of(structure, first_option).kind == "and"
    assert piece_of(structure, second_option).kind == "course"
    assert leaf_group_ids(structure, second_option) == {"c"}
    a_branch = child_uses(structure, first_option)[0]
    assert piece_of(structure, a_branch).kind == "course_alternatives"
    original_leaf, option_one, option_two = child_uses(structure, a_branch)
    assert leaf_group_ids(structure, original_leaf) == {"a"}
    assert piece_of(structure, option_one).kind == "and"
    option_one_children = child_uses(structure, option_one)
    assert [leaf_group_ids(structure, child) for child in option_one_children] == [
        {"a1", "e"},
        {"a2"},
    ]
    assert leaf_group_ids(structure, option_two) == {"a3"}
    assert fact_of(structure, option_two).official_kind is OfficialPrerequisiteKind.SUBSTITUTION

    # The empty option and the missing substitution are disclosed and dropped whole.
    assert "a4" not in {summary.group_id for summary in structure.courses}
    assert "missing-sub" not in {summary.group_id for summary in structure.courses}
    ignored = [
        d
        for d in structure.diagnostics
        if d.kind in {"empty_option", "missing_substitution_course"}
    ]
    assert [item.kind for item in ignored] == [
        "empty_option",
        "missing_substitution_course",
    ]
    assert ignored[0].fact_id in {fact.fact_id for fact in structure.facts}
    assert ignored[1].referenced_group_ids == ("a4", "missing-sub")
    assert ignored[1].detail == "substitution option 3 dropped: missing missing-sub"

    # A1's ordinary prerequisite E expands, and its own substitution X does not chain back.
    a1_branch = option_one_children[0]
    assert piece_of(structure, a1_branch).kind == "expanded_course"
    a1_leaf, a1_children = child_uses(structure, a1_branch)
    assert leaf_group_ids(structure, a1_leaf) == {"a1"}
    assert leaf_group_ids(structure, a1_children) == {"e"}
    assert "x" not in {summary.group_id for summary in structure.courses}

    # Recommended provenance stays distinct and D expands its own compulsory child.
    assert piece_of(structure, recommended_root).kind == "expanded_course"
    d_leaf, d_child = child_uses(structure, recommended_root)
    assert leaf_group_ids(structure, d_leaf) == {"d"}
    assert fact_of(structure, d_leaf).official_kind is OfficialPrerequisiteKind.RECOMMENDED
    assert leaf_group_ids(structure, d_child) == {"d-child"}
    assert "d-child" in {summary.group_id for summary in structure.courses}

    # Projection keeps substitutions directional OR-of-AND rather than flattened equivalence.
    substitution_members = [
        member
        for member in structure.members
        if next(fact for fact in structure.facts if fact.fact_id == member.fact_id).official_kind
        is OfficialPrerequisiteKind.SUBSTITUTION
    ]
    assert substitution_members
    assert not any(
        edge.source_node_id == "course:root" and edge.target_node_id == "course:e"
        for edge in compilation.display.edges
    )
    assert inferred_read.reads == []

    # Direct-many keeps separate category roots and stops ordinary course ancestors.
    direct = compiler.compile_direct_many(("root",))
    assert [entry.solver.root_group_id for entry in direct] == ["root"]
    direct_entry = direct[0]
    assert direct_entry.required_use_id is not None
    assert direct_entry.recommended_use_id is not None
    direct_groups = {course.group_id for course in direct_entry.solver.courses}
    assert {"a", "a1", "a2", "a3", "b", "c", "d"} <= direct_groups
    assert "d-child" not in direct_groups
    assert "e" not in direct_groups
    assert "x" not in direct_groups
    assert piece_of(direct_entry.solver, direct_entry.required_use_id).kind == "or"
    first_direct_option = child_uses(direct_entry.solver, direct_entry.required_use_id)[0]
    assert piece_of(direct_entry.solver, first_direct_option).kind == "and"
    direct_a_branch = child_uses(direct_entry.solver, first_direct_option)[0]
    assert piece_of(direct_entry.solver, direct_a_branch).kind == "course_alternatives"
    assert leaf_group_ids(direct_entry.solver, direct_entry.recommended_use_id) == {"d"}
