"""Activity scope, excluded nodes, and inactive non-root pruning."""

from __future__ import annotations

from course_explorer.enums import PrerequisiteRequirementKind
from course_explorer.prerequisite.domain import expression_course_leaf_group_ids
from course_explorer.prerequisite.graph import (
    PrerequisiteGraphCompiler,
)
from course_explorer.prerequisite.path import (
    PrerequisitePathState,
    calculate_minimum_new_credits,
)
from tests.prerequisite._graph_support import (
    FakeCurriculumRead,
    RecordingEquivalenceGroupRead,
    RecordingInferredSetRead,
    catalogue_course,
    current_result,
    official_course,
    prerequisite_course_member,
    prerequisite_option,
    substitution_option,
)


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
    tree = compilation.tree
    assert inferred_read.reads == ["root"]
    assert "hidden-child" not in {summary.group_id for summary in tree.courses}
    assert "hidden-substitute" not in {summary.group_id for summary in tree.courses}
    requirements = tree.requirements
    # The singleton compulsory option collapses to its bare inactive leaf.
    assert requirements == official_course("inactive-leaf")
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
    assert all_courses.tree.active_only is False
    assert {node.course.group_id for node in all_courses.graph.course_nodes} == {
        "root",
        "inactive-leaf",
        "active-alt",
    }

    active_only = compiler.compile("root", active_only=True)
    assert active_only.tree.active_only is True
    # The unretained inactive leaf is dropped before any expansion, so only the active alternative
    # appears in the tree and the drawing.
    assert "inactive-leaf" not in {summary.group_id for summary in active_only.tree.courses}
    assert expression_course_leaf_group_ids(active_only.tree.requirements) == {"active-alt"}
    assert {node.course.group_id for node in active_only.graph.course_nodes} == {
        "root",
        "active-alt",
    }

    retained = compiler.compile("root", active_only=True, retained_group_ids=("inactive-leaf",))
    assert expression_course_leaf_group_ids(retained.tree.requirements) == {
        "inactive-leaf",
        "active-alt",
    }
    assert {node.course.group_id for node in retained.graph.course_nodes} == {
        "root",
        "inactive-leaf",
        "active-alt",
    }


def test_excluded_nodes_and_descendants_stay_drawn_and_marked() -> None:
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
    assert [node.node_id for node in excluded.graph.course_nodes] == [
        node.node_id for node in plain.graph.course_nodes
    ]
    assert excluded.graph.connector_nodes == plain.graph.connector_nodes
    assert excluded.graph.edges == plain.graph.edges
    assert excluded.tree.requirements == plain.tree.requirements
    assert excluded.tree.excluded_group_ids == ("a",)
    assert {"root", "a", "a-child", "b"} <= {summary.group_id for summary in excluded.tree.courses}

    nodes_by_group = {node.course.group_id: node for node in excluded.graph.course_nodes}
    assert nodes_by_group["a"].is_excluded is True
    assert nodes_by_group["a-child"].is_excluded is False
    assert nodes_by_group["b"].is_excluded is False
    assert nodes_by_group["root"].is_excluded is False

    # An unrepresented exclusion never reaches the tree or the graph.
    no_op = compiler.compile("root", excluded_group_ids=("unknown",))
    assert no_op.tree.excluded_group_ids == ()
    assert no_op.graph == plain.graph

    # The opened root's own canonical exclusion is represented and blocks the whole request with a
    # located no-solution, while the source graph is drawn and the root node is marked.
    root_excluded = compiler.compile("root", excluded_group_ids=("root",))
    assert root_excluded.tree.excluded_group_ids == ("root",)
    assert root_excluded.tree.requirements == plain.tree.requirements
    assert {node.course.group_id for node in root_excluded.graph.course_nodes} == {
        "root",
        "a",
        "a-child",
        "b",
    }
    root_nodes = {node.course.group_id: node for node in root_excluded.graph.course_nodes}
    assert root_nodes["root"].is_excluded is True
    assert root_nodes["a"].is_excluded is False
    blocked = calculate_minimum_new_credits(root_excluded.tree, [])
    assert blocked.state is PrerequisitePathState.NO_SOLUTION
