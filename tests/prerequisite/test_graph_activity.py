"""Activity scope, excluded nodes, and inactive non-root pruning."""

from __future__ import annotations

from course_explorer.enums import PrerequisiteRequirementKind
from course_explorer.prerequisite.graph import (
    PrerequisiteGraphCompiler,
)
from tests.prerequisite._graph_support import (
    FakeCurriculumRead,
    RecordingEquivalenceGroupRead,
    RecordingInferredSetRead,
    catalogue_course,
    connector_nodes,
    course_nodes,
    current_result,
    leaf_group_ids,
    piece_of,
    prerequisite_course_member,
    prerequisite_option,
    substitution_option,
)
from tests.prerequisite._path_support import solve_route


def test_compiler_stops_inactive_non_root_leaves_before_child_reads() -> None:
    """An inactive non-root course never reads inferred sets, substitutions, or descendants."""
    inactive_leaf_courses = (
        catalogue_course(
            "root",
            prerequisite_options=(
                prerequisite_option(
                    0,
                    PrerequisiteRequirementKind.COMPULSORY,
                    prerequisite_course_member(0, "inactive-leaf"),
                ),
            ),
        ),
        catalogue_course(
            "inactive-leaf",
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
    inferred_read = RecordingInferredSetRead(
        {"root": current_result("root")},
    )
    compiler = PrerequisiteGraphCompiler(
        FakeCurriculumRead(inactive_leaf_courses), inferred_read, RecordingEquivalenceGroupRead()
    )

    compilation = compiler.compile("root", include_inferred=True)
    tree = compilation.solver
    assert inferred_read.reads == ["root"]
    assert "hidden-child" not in {summary.group_id for summary in tree.courses}
    assert "hidden-substitute" not in {summary.group_id for summary in tree.courses}
    # The singleton compulsory option collapses to its bare inactive leaf.
    assert tree.root_use_id is not None
    requirements = piece_of(tree, tree.root_use_id)
    assert requirements.kind == "course"
    assert requirements.course_group_id == "inactive-leaf"


def test_active_scope_drops_unretained_inactive_courses_from_the_compiled_tree() -> None:
    """Active-only drops the unretained inactive leaf and draws the retained inactive leaf."""
    root_options = (
        prerequisite_option(
            0,
            PrerequisiteRequirementKind.COMPULSORY,
            prerequisite_course_member(0, "inactive-leaf"),
            prerequisite_course_member(1, "active-alt"),
        ),
    )
    courses = (
        catalogue_course("root", prerequisite_options=root_options),
        catalogue_course("inactive-leaf", is_active=False),
        catalogue_course("active-alt"),
    )
    compiler = PrerequisiteGraphCompiler(
        FakeCurriculumRead(courses), RecordingInferredSetRead(), RecordingEquivalenceGroupRead()
    )

    all_courses = compiler.compile("root")
    assert all_courses.solver.active_only is False
    assert {node.course_group_id for node in course_nodes(all_courses.display)} == {
        "root",
        "inactive-leaf",
        "active-alt",
    }

    active_only = compiler.compile("root", active_only=True)
    assert active_only.solver.active_only is True
    # The unretained inactive leaf is dropped before any expansion, so only the active alternative
    # appears in the tree and the drawing.
    assert "inactive-leaf" not in {summary.group_id for summary in active_only.solver.courses}
    assert leaf_group_ids(active_only.solver, active_only.solver.root_use_id) == {"active-alt"}
    assert {node.course_group_id for node in course_nodes(active_only.display)} == {
        "root",
        "active-alt",
    }

    retained = compiler.compile("root", active_only=True, retained_group_ids=("inactive-leaf",))
    assert leaf_group_ids(retained.solver, retained.solver.root_use_id) == {
        "inactive-leaf",
        "active-alt",
    }
    assert {node.course_group_id for node in course_nodes(retained.display)} == {
        "root",
        "inactive-leaf",
        "active-alt",
    }


def test_excluded_nodes_and_descendants_stay_drawn_and_marked(solver_bundle: None) -> None:
    """Exclusion marks canonical nodes, draws them and descendants, and blocks an excluded root."""
    courses = (
        catalogue_course(
            "root",
            prerequisite_options=(
                prerequisite_option(
                    0,
                    PrerequisiteRequirementKind.COMPULSORY,
                    prerequisite_course_member(0, "a"),
                ),
                prerequisite_option(
                    1,
                    PrerequisiteRequirementKind.COMPULSORY,
                    prerequisite_course_member(0, "b"),
                ),
            ),
        ),
        catalogue_course(
            "a",
            prerequisite_options=(
                prerequisite_option(
                    0,
                    PrerequisiteRequirementKind.COMPULSORY,
                    prerequisite_course_member(0, "a-child"),
                ),
            ),
        ),
        catalogue_course("a-child"),
        catalogue_course("b"),
    )
    compiler = PrerequisiteGraphCompiler(
        FakeCurriculumRead(courses), RecordingInferredSetRead(), RecordingEquivalenceGroupRead()
    )

    plain = compiler.compile("root")
    excluded = compiler.compile("root", excluded_group_ids=("a",))

    # Exclusion prunes nothing and changes no path flag, connector, or edge. Only the marker differs.
    assert [node.node_id for node in course_nodes(excluded.display)] == [
        node.node_id for node in course_nodes(plain.display)
    ]
    assert connector_nodes(excluded.display) == connector_nodes(plain.display)
    assert excluded.display.edges == plain.display.edges
    assert excluded.solver.root_use_id == plain.solver.root_use_id
    assert excluded.solver.pieces == plain.solver.pieces
    assert excluded.solver.facts == plain.solver.facts
    assert excluded.solver.excluded_group_ids == ("a",)
    assert {"root", "a", "a-child", "b"} <= {
        summary.group_id for summary in excluded.solver.courses
    }

    assert "a" in excluded.solver.excluded_group_ids
    assert "a-child" not in excluded.solver.excluded_group_ids
    assert "b" not in excluded.solver.excluded_group_ids
    assert "root" not in excluded.solver.excluded_group_ids

    # An unrepresented exclusion never reaches the tree or the graph.
    no_op = compiler.compile("root", excluded_group_ids=("unknown",))
    assert no_op.solver.excluded_group_ids == ()
    assert no_op.display == plain.display

    # The opened root's own canonical exclusion is represented and blocks the whole request with a
    # located no-solution, while the source graph is drawn and the root node is marked.
    root_excluded = compiler.compile("root", excluded_group_ids=("root",))
    assert root_excluded.solver.excluded_group_ids == ("root",)
    assert root_excluded.solver.root_use_id == plain.solver.root_use_id
    assert root_excluded.solver.pieces == plain.solver.pieces
    assert root_excluded.solver.facts == plain.solver.facts
    assert [node.node_id for node in course_nodes(root_excluded.display)] == [
        node.node_id for node in course_nodes(plain.display)
    ]
    assert "root" in root_excluded.solver.excluded_group_ids
    assert "a" not in root_excluded.solver.excluded_group_ids
    blocked = solve_route(root_excluded.solver, [])
    assert blocked["state"] == "no_solution"
