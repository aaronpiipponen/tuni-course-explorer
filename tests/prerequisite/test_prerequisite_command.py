"""Real PostgreSQL command composition for the prerequisite commands.

The command functions are exercised end to end over a real normalized test database. The shared
search policy lives in `_command_support`. This module owns the real command cases.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from course_explorer.ingestion.normalization import normalize_curriculum
from course_explorer.ingestion.normalization_repository import NormalizationRepository
from course_explorer.ingestion.repository import CaptureRepository
from course_explorer.prerequisite import commands as command_module
from tests.ingestion._normalization_repository_support import (
    GUIDE_URL,
    build_completed_fixture_store,
    fixture_bytes,
)
from tests.prerequisite._command_support import search_settings
from tests.prerequisite._graph_support import course_nodes, root_summary
from tests.prerequisite._path_support import selected_group_ids, solve_route


def _inactive_prerequisite_fixture(database, tmp_path: Path):
    """Normalize one real capture whose CS.A2 compulsory prerequisite is the inactive group."""
    _, factory = database
    capture_repository = CaptureRepository(factory)
    courses = json.loads(fixture_bytes("courses.json"))
    course_a_v2 = next(course for course in courses if course["id"] == "course-a-v2")
    course_a_v2["compulsoryFormalPrerequisites"] = [
        {"prerequisites": [{"type": "CourseUnit", "courseUnitGroupId": "course-group-inactive"}]}
    ]
    store = build_completed_fixture_store(
        tmp_path,
        capture_repository,
        courses_body=json.dumps(courses, sort_keys=True, separators=(",", ":")).encode(),
    )
    normalize_curriculum(
        store,
        NormalizationRepository(factory),
        current_academic_year_start=2026,
        activity_window_years=3,
        course_guide_base_url=GUIDE_URL,
    )
    return factory


@pytest.mark.integration
def test_two_basis_selection_display_and_basis_rule(
    database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, solver_bundle: None
) -> None:
    """The three selected/completed combinations resolve canonically against real persistence."""
    _inactive_prerequisite_fixture(database, tmp_path)
    monkeypatch.setattr(command_module, "load_search_settings", search_settings)

    # Omitted selected input uses completed courses as the selected basis.
    command_module.run_prerequisite_command("CS.A2", completed_codes=["CS.I1"], basis="selected")
    no_selected_route = command_module.run_minimum_route_command(
        "CS.A2", completed_codes=["CS.I1"], basis="selected"
    )
    assert no_selected_route["satisfaction"]["basis_group_ids"] == ["course-group-inactive"]
    assert Decimal(no_selected_route["total_new_credits"]) == Decimal("0")
    assert no_selected_route["new_courses"] == []

    # (b) --selected with no --completed is valid with an empty completed basis. The real route
    # charges the inactive prerequisite under the default all-course scope.
    command_module.run_prerequisite_command("CS.A2", selected_codes=["CS.I1"])
    no_completed_route = command_module.run_minimum_route_command("CS.A2", selected_codes=["CS.I1"])
    assert no_completed_route["satisfaction"]["basis_group_ids"] == []
    assert Decimal(no_completed_route["total_new_credits"]) == Decimal("3")
    assert selected_group_ids(no_completed_route) == ("course-group-inactive",)

    # An explicit selected basis covers the full selected set.
    command_module.run_prerequisite_command(
        "CS.A2",
        selected_codes=["course-group-inactive", "TIE.B"],
        completed_codes=["CS.I1"],
        basis="selected",
    )
    selected_basis_route = command_module.run_minimum_route_command(
        "CS.A2",
        selected_codes=["course-group-inactive", "TIE.B"],
        completed_codes=["CS.I1"],
        basis="selected",
    )
    assert selected_basis_route["satisfaction"]["basis_group_ids"] == [
        "course-group-inactive",
        "course-group-tie",
    ]
    assert Decimal(selected_basis_route["total_new_credits"]) == Decimal("0")
    assert selected_basis_route["new_courses"] == []

    # (d) a completed course outside a non-empty selected set fails loudly in both preparations.
    with pytest.raises(ValueError):
        command_module.run_prerequisite_command(
            "CS.A2", selected_codes=["TIE.B"], completed_codes=["CS.I1"]
        )
    with pytest.raises(ValueError):
        command_module.run_minimum_route_command(
            "CS.A2", selected_codes=["TIE.B"], completed_codes=["CS.I1"]
        )

    # Root exclusion is request-owned and keeps the root card, while the separate route operation
    # owns the located problem and the no-solution outcome.
    root_excluded = command_module.run_prerequisite_command(
        "course-group-a", excluded_codes=["course-group-a"]
    )
    assert root_excluded.solver.excluded_group_ids == ("course-group-a",)
    root_node = next(node for node in course_nodes(root_excluded.display) if node.is_root)
    assert root_node.course_group_id == "course-group-a"
    assert "node_states" not in root_excluded.display.model_dump()
    root_excluded_route = command_module.run_minimum_route_command(
        "course-group-a", excluded_codes=["course-group-a"]
    )
    assert root_excluded_route["state"] == "no_solution"
    assert root_excluded_route["problems"][0]["reason"] == "excluded_node"
    assert root_excluded_route["blocked_excluded_group_ids"] == ["course-group-a"]


@pytest.mark.integration
def test_drawing_refusal_preserves_calculation_and_truthful_counts(
    database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, solver_bundle: None
) -> None:
    """The drawable count gates presentation only and never changes the separate route operation."""
    _inactive_prerequisite_fixture(database, tmp_path)
    monkeypatch.setattr(command_module, "load_search_settings", search_settings)

    allowed = command_module.run_prerequisite_command(
        "CS.A2", completed_codes=["CS.I1"], max_drawing_elements=1_000_000
    )
    graph = allowed.display
    count = allowed.drawing
    assert count.course_count == sum(1 for node in graph.nodes if node.kind == "course")
    assert count.node_count == len(graph.nodes)
    assert count.edge_count == len(graph.edges)
    refused = command_module.run_prerequisite_command(
        "CS.A2", completed_codes=["CS.I1"], max_drawing_elements=count.element_count - 1
    )
    assert refused.drawing.allowed is False
    assert refused.drawing.model_dump(exclude={"limit", "allowed"}) == count.model_dump(
        exclude={"limit", "allowed"}
    )
    assert refused.display is None
    assert refused.solver == allowed.solver
    at_limit = command_module.run_prerequisite_command(
        "CS.A2", completed_codes=["CS.I1"], max_drawing_elements=count.element_count
    )
    assert at_limit.drawing.allowed is True
    assert at_limit.display == allowed.display
    unlimited = command_module.run_prerequisite_command("CS.A2", completed_codes=["CS.I1"])
    assert unlimited.drawing.allowed is True
    assert unlimited.drawing.limit is None

    # The independent route operation has no drawing limit and keeps its authoritative result.
    route = command_module.run_minimum_route_command("CS.A2", completed_codes=["CS.I1"])
    assert route["state"] == "exact"
    assert Decimal(route["total_new_credits"]) == Decimal("0")
    assert route["satisfaction"]["basis_group_ids"] == ["course-group-inactive"]


@pytest.mark.integration
def test_graph_and_route_commands_share_preparation_without_mixing_results(
    database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, solver_bundle: None
) -> None:
    """Each command projects once. The graph read never solves and the route result holds no graph."""
    _inactive_prerequisite_fixture(database, tmp_path)
    monkeypatch.setattr(command_module, "load_search_settings", search_settings)
    projector_calls: list[str] = []
    solver_calls: list[str] = []
    real_projector = command_module.project_prerequisite_graph
    real_node_route = command_module._node_route

    def watched_projector(structure, **kwargs):
        projector_calls.append(root_summary(structure).group_id)
        return real_projector(structure, **kwargs)

    def watched_node_route(context):
        solver_calls.append(context.solver.root_group_id)
        return real_node_route(context)

    monkeypatch.setattr(command_module, "project_prerequisite_graph", watched_projector)
    monkeypatch.setattr(command_module, "_node_route", watched_node_route)

    graph_report = command_module.run_prerequisite_command("CS.A2", completed_codes=["CS.I1"])
    assert projector_calls == ["course-group-a"]
    assert solver_calls == []
    assert course_nodes(graph_report.display)
    assert "path" not in type(graph_report).model_fields

    route = command_module.run_minimum_route_command("CS.A2", completed_codes=["CS.I1"])
    # The route read reuses the one shared preparation and its single projection, then solves.
    assert projector_calls == ["course-group-a", "course-group-a"]
    assert solver_calls == ["course-group-a"]
    assert isinstance(route, dict)
    assert route["state"] == "exact"
    assert Decimal(route["total_new_credits"]) == Decimal("0")
    assert "solver" not in route
    assert "drawing" not in route


@pytest.mark.integration
def test_machine_route_command_returns_the_shared_node_result(
    database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, solver_bundle: None
) -> None:
    """The machine route command returns the shared Node result for its prepared graph."""
    _inactive_prerequisite_fixture(database, tmp_path)
    monkeypatch.setattr(command_module, "load_search_settings", search_settings)
    prepared = command_module.run_prerequisite_command("CS.A2", completed_codes=["CS.I1"])
    expected = solve_route(
        prepared.solver,
        ["course-group-inactive"],
        max_compact_nodes=search_settings().prerequisite_path_max_compact_nodes,
    )
    route = command_module.run_minimum_route_command("CS.A2", completed_codes=["CS.I1"])
    assert route == expected
    assert route["state"] == "exact"
    assert Decimal(route["total_new_credits"]) == Decimal("0")
    assert selected_group_ids(route) == ()
