"""Real PostgreSQL command composition plus network-free CLI contracts.

The command function is exercised end to end over a real normalized test database. The CLI
adapter is proved network-free against canned reports. Shared report builders live in
`_command_support`. This module owns the real command cases and the script loading.
"""

from __future__ import annotations

import importlib.util
import json
from decimal import Decimal
from pathlib import Path

import pytest

from course_explorer.ingestion.normalization import normalize_curriculum
from course_explorer.ingestion.normalization_repository import NormalizationRepository
from course_explorer.ingestion.repository import CaptureRepository
from course_explorer.prerequisite import commands as command_module
from course_explorer.prerequisite.domain import (
    CardinalityRequirement,
    CreditRequirement,
    OfficialPrerequisiteKind,
    PrerequisiteOrigin,
)
from course_explorer.prerequisite.path import (
    MinimumCreditPathEvaluation,
    PrerequisitePathState,
    calculate_minimum_new_credits,
)
from tests.ingestion._normalization_repository_support import (
    GUIDE_URL,
    build_completed_fixture_store,
    fixture_bytes,
)
from tests.prerequisite._command_support import (
    excluded_graph_report_for,
    excluded_report_for,
    report_for,
    search_settings,
    shortfall_report_for,
)
from tests.prerequisite._path_support import course_summary, make_compilation, official_course

_CLI_SPEC = importlib.util.spec_from_file_location(
    "prerequisites", Path(__file__).parents[2] / "scripts" / "prerequisites.py"
)
assert _CLI_SPEC is not None and _CLI_SPEC.loader is not None
_CLI_MODULE = importlib.util.module_from_spec(_CLI_SPEC)
_CLI_SPEC.loader.exec_module(_CLI_MODULE)


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
    database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The three selected/completed combinations resolve canonically against real persistence."""
    _inactive_prerequisite_fixture(database, tmp_path)
    monkeypatch.setattr(command_module, "load_search_settings", search_settings)

    # Omitted selected input uses completed courses as the selected basis.
    no_selected = command_module.run_prerequisite_command(
        "CS.A2", completed_codes=["CS.I1"], basis="selected"
    )
    assert no_selected.selected_group_ids == ("course-group-inactive",)
    assert no_selected.completed_group_ids == ("course-group-inactive",)
    assert no_selected.basis is command_module.PrerequisiteCalculationBasis.SELECTED
    no_selected_route = command_module.run_minimum_route_command(
        "CS.A2", completed_codes=["CS.I1"], basis="selected"
    )
    assert no_selected_route.satisfaction.basis_group_ids == ("course-group-inactive",)
    assert no_selected_route.total_new_credits == Decimal("0")
    assert no_selected_route.new_courses == ()

    # (b) --selected with no --completed is valid with an empty completed basis. The real route
    # charges the inactive prerequisite under the default all-course scope.
    no_completed = command_module.run_prerequisite_command("CS.A2", selected_codes=["CS.I1"])
    assert no_completed.selected_group_ids == ("course-group-inactive",)
    assert no_completed.completed_group_ids == ()
    assert no_completed.basis is command_module.PrerequisiteCalculationBasis.COMPLETED
    no_completed_route = command_module.run_minimum_route_command("CS.A2", selected_codes=["CS.I1"])
    assert no_completed_route.satisfaction.basis_group_ids == ()
    assert no_completed_route.total_new_credits == Decimal("3")
    assert [entry.course.group_id for entry in no_completed_route.new_courses] == [
        "course-group-inactive"
    ]

    # An explicit selected basis covers the full selected set.
    selected_basis = command_module.run_prerequisite_command(
        "CS.A2",
        selected_codes=["course-group-inactive", "TIE.B"],
        completed_codes=["CS.I1"],
        basis="selected",
    )
    assert selected_basis.selected_group_ids == ("course-group-inactive", "course-group-tie")
    assert selected_basis.completed_group_ids == ("course-group-inactive",)
    selected_basis_route = command_module.run_minimum_route_command(
        "CS.A2",
        selected_codes=["course-group-inactive", "TIE.B"],
        completed_codes=["CS.I1"],
        basis="selected",
    )
    assert selected_basis_route.satisfaction.basis_group_ids == (
        "course-group-inactive",
        "course-group-tie",
    )
    assert selected_basis_route.total_new_credits == Decimal("0")
    assert selected_basis_route.new_courses == ()

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
    assert root_excluded.excluded_group_ids == ("course-group-a",)
    root_node = next(node for node in root_excluded.compilation.graph.course_nodes if node.is_root)
    assert root_node.is_excluded
    root_excluded_route = command_module.run_minimum_route_command(
        "course-group-a", excluded_codes=["course-group-a"]
    )
    assert root_excluded_route.state is PrerequisitePathState.NO_SOLUTION
    assert root_excluded_route.problems[0].reason == "excluded_node"
    assert root_excluded_route.problems[0].origin is PrerequisiteOrigin.COMPOSED
    assert root_excluded_route.blocked_excluded_group_ids == ("course-group-a",)


@pytest.mark.integration
def test_drawing_refusal_preserves_calculation_and_truthful_counts(
    database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The drawable count gates presentation only and never changes the separate route operation."""
    _inactive_prerequisite_fixture(database, tmp_path)
    monkeypatch.setattr(command_module, "load_search_settings", search_settings)

    allowed = command_module.run_prerequisite_command(
        "CS.A2", completed_codes=["CS.I1"], max_drawing_elements=1_000_000
    )
    graph = allowed.compilation.graph
    count = command_module.prerequisite_drawing_allowance(graph, max_elements=1_000_000)
    assert allowed.drawing == count
    assert count.course_count == len(graph.course_nodes)
    assert count.node_count == (
        len(graph.course_nodes)
        + len(graph.module_nodes)
        + len(graph.ignored_nodes)
        + len(graph.connector_nodes)
    )
    assert count.edge_count == len(graph.edges)
    refused = command_module.run_prerequisite_command(
        "CS.A2", completed_codes=["CS.I1"], max_drawing_elements=count.element_count - 1
    )
    assert refused.drawing.allowed is False
    assert refused.drawing.model_dump(exclude={"limit", "allowed"}) == count.model_dump(
        exclude={"limit", "allowed"}
    )
    assert refused.compilation == allowed.compilation
    at_limit = command_module.run_prerequisite_command(
        "CS.A2", completed_codes=["CS.I1"], max_drawing_elements=count.element_count
    )
    assert at_limit.drawing.allowed is True
    assert at_limit.compilation == allowed.compilation
    unlimited = command_module.run_prerequisite_command("CS.A2", completed_codes=["CS.I1"])
    assert unlimited.drawing.allowed is True
    assert unlimited.drawing.limit is None

    # The independent route operation has no drawing limit and keeps its authoritative result.
    route = command_module.run_minimum_route_command("CS.A2", completed_codes=["CS.I1"])
    assert route.state is PrerequisitePathState.EXACT
    assert route.total_new_credits == Decimal("0")
    assert route.satisfaction.basis_group_ids == ("course-group-inactive",)


def test_prerequisite_cli_forwards_completed_codes_and_toggles_and_prints_one_report(
    monkeypatch, capsys
) -> None:
    """The script forwards its arguments and prints exactly the one dispatched operation's JSON."""
    expected = report_for()
    route_expected = calculate_minimum_new_credits(expected.compilation.tree, ())
    graph_calls: list[dict] = []
    route_calls: list[dict] = []
    monkeypatch.setattr(
        _CLI_MODULE,
        "run_prerequisite_command",
        lambda course_code, **kwargs: (
            graph_calls.append({"course_code": course_code, **kwargs}) or expected
        ),
    )
    monkeypatch.setattr(
        _CLI_MODULE,
        "run_minimum_route_command",
        lambda course_code, **kwargs: (
            route_calls.append({"course_code": course_code, **kwargs}) or route_expected
        ),
    )

    assert _CLI_MODULE.main(["COMP.CS.500"]) == 0
    assert graph_calls[-1] == {
        "course_code": "COMP.CS.500",
        "completed_codes": [],
        "selected_codes": [],
        "excluded_codes": [],
        "completed_node_keys": [],
        "excluded_node_keys": [],
        "include_recommended": False,
        "include_inferred": False,
        "active_only": False,
        "basis": "completed",
    }
    assert route_calls == []
    default_output = capsys.readouterr().out
    assert default_output == expected.model_dump_json() + "\n"
    # The default dispatch is the graph-only report: compilation and drawing facts, no route result.
    default_payload = json.loads(default_output)
    assert "path" not in default_payload
    assert "state" not in default_payload
    assert default_payload["drawing"]["limit"] is None
    assert default_payload["compilation"]["tree"]["root"]["credits_min"] == "5"

    full_arguments = [
        "COMP.CS.500",
        "--completed",
        "COMP.CS.100",
        "--completed",
        "MATH.1",
        "--selected",
        "COMP.CS.200",
        "--excluded",
        "COMP.CS.300",
        "--excluded",
        "COMP.CS.400",
        "--include-recommended",
        "--include-inferred",
        "--active-only",
        "--basis",
        "selected",
        "--completed-node",
        "module:module-x",
        "--excluded-node",
        "requirement:abc",
    ]
    full_options = {
        "course_code": "COMP.CS.500",
        "completed_codes": ["COMP.CS.100", "MATH.1"],
        "selected_codes": ["COMP.CS.200"],
        "excluded_codes": ["COMP.CS.300", "COMP.CS.400"],
        "completed_node_keys": ["module:module-x"],
        "excluded_node_keys": ["requirement:abc"],
        "include_recommended": True,
        "include_inferred": True,
        "active_only": True,
        "basis": "selected",
    }
    assert _CLI_MODULE.main(full_arguments) == 0
    assert graph_calls[-1] == full_options
    assert route_calls == []
    assert capsys.readouterr().out == expected.model_dump_json() + "\n"

    # --route dispatches the same parsed options to the route operation only and prints its result.
    assert _CLI_MODULE.main([*full_arguments, "--route"]) == 0
    assert graph_calls[-1] == full_options
    assert route_calls[-1] == full_options
    route_output = capsys.readouterr().out
    assert route_output == route_expected.model_dump_json() + "\n"
    route_payload = json.loads(route_output)
    assert route_payload["state"] == "exact"
    assert route_payload["total_new_credits"] == "5"
    assert route_payload["new_courses"]
    assert "compilation" not in route_payload
    assert "drawing" not in route_payload
    assert "path" not in route_payload

    # A real graph report keeps the excluded node drawn and marked and embeds no route result.
    excluded_graph = excluded_graph_report_for()
    monkeypatch.setattr(
        _CLI_MODULE, "run_prerequisite_command", lambda course_code, **kwargs: excluded_graph
    )
    assert _CLI_MODULE.main(["COMP.CS.500", "--excluded", "blocked"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["excluded_group_ids"] == ["blocked"]
    assert "path" not in payload
    assert [
        node["course"]["group_id"]
        for node in payload["compilation"]["graph"]["course_nodes"]
        if node["is_excluded"]
    ] == ["blocked"]

    # The separate no-solution route result names the blocking exclusion through --route.
    excluded_route = excluded_report_for()
    assert excluded_route.state is PrerequisitePathState.NO_SOLUTION
    monkeypatch.setattr(
        _CLI_MODULE, "run_minimum_route_command", lambda course_code, **kwargs: excluded_route
    )
    assert _CLI_MODULE.main(["COMP.CS.500", "--excluded", "blocked", "--route"]) == 0
    excluded_payload = json.loads(capsys.readouterr().out)
    assert excluded_payload["state"] == "no_solution"
    assert excluded_payload["blocked_excluded_group_ids"] == ["blocked"]
    assert "compilation" not in excluded_payload

    # The active-only case prints a real shortfall route result as-is through the same CLI adapter.
    shortfall = shortfall_report_for()
    monkeypatch.setattr(
        _CLI_MODULE, "run_minimum_route_command", lambda course_code, **kwargs: shortfall
    )
    assert _CLI_MODULE.main(["COMP.CS.500", "--active-only", "--route"]) == 0
    shortfall_output = capsys.readouterr().out
    assert shortfall_output == shortfall.model_dump_json() + "\n"
    shortfall_payload = json.loads(shortfall_output)
    assert shortfall_payload["state"] == "shortfall"
    assert shortfall_payload["new_courses"] == []
    assert shortfall_payload["total_new_credits"] == "0"
    first_shortfall = shortfall_payload["shortfalls"][0]
    assert first_shortfall["kind"] == "all_mandatory"
    assert first_shortfall["required_count"] == 1
    assert first_shortfall["achieved_count"] == 0
    assert first_shortfall["count_deficit"] == 1

    greedy_miss = make_compilation(
        expected.compilation.tree.root,
        CreditRequirement(
            type="credits",
            origin=PrerequisiteOrigin.OFFICIAL,
            official_kind=OfficialPrerequisiteKind.MODULE_RULE,
            credits_min=Decimal("3"),
            credits_max=Decimal("3"),
            child=CardinalityRequirement(
                type="cardinality",
                origin=PrerequisiteOrigin.OFFICIAL,
                official_kind=OfficialPrerequisiteKind.MODULE_RULE,
                require_min=1,
                require_max=1,
                children=(official_course("cheap"), official_course("dear")),
            ),
        ),
        (course_summary("cheap", credits_min="1"), course_summary("dear", credits_min="3")),
    ).tree
    failed_path = calculate_minimum_new_credits(greedy_miss, [], max_compact_nodes=1)
    monkeypatch.setattr(
        _CLI_MODULE, "run_minimum_route_command", lambda course_code, **kwargs: failed_path
    )
    assert _CLI_MODULE.main(["COMP.CS.500", "--route"]) == 0
    failed_payload = json.loads(capsys.readouterr().out)
    assert failed_payload["state"] == "approximation_failed"
    assert failed_payload["total_new_credits"] is None
    assert failed_payload["new_courses"] == []
    assert failed_payload["problems"][0]["reason"] == "search_too_large"

    # A package failure is not caught into a fabricated JSON error line for either dispatch.
    def fail(course_code, **kwargs):
        raise ValueError("unknown official course code 'MISSING'")

    monkeypatch.setattr(_CLI_MODULE, "run_prerequisite_command", fail)
    monkeypatch.setattr(_CLI_MODULE, "run_minimum_route_command", fail)
    with pytest.raises(ValueError):
        _CLI_MODULE.main(["MISSING"])
    with pytest.raises(ValueError):
        _CLI_MODULE.main(["MISSING", "--route"])


@pytest.mark.integration
def test_graph_and_route_commands_execute_only_their_operation(
    database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The graph read never runs the route solver and the route read never projects a drawing."""
    _inactive_prerequisite_fixture(database, tmp_path)
    monkeypatch.setattr(command_module, "load_search_settings", search_settings)
    projector_calls: list[str] = []
    solver_calls: list[str] = []
    real_projector = command_module.project_prerequisite_graph
    real_solver = command_module.calculate_minimum_new_credits

    def watched_projector(tree, **kwargs):
        projector_calls.append(tree.root.group_id)
        return real_projector(tree, **kwargs)

    def watched_solver(*args, **kwargs):
        solver_calls.append(args[0].root.group_id)
        return real_solver(*args, **kwargs)

    monkeypatch.setattr(command_module, "project_prerequisite_graph", watched_projector)
    monkeypatch.setattr(command_module, "calculate_minimum_new_credits", watched_solver)

    graph_report = command_module.run_prerequisite_command("CS.A2", completed_codes=["CS.I1"])
    assert projector_calls == ["course-group-a"]
    assert solver_calls == []
    assert graph_report.compilation.graph.course_nodes
    assert "path" not in type(graph_report).model_fields

    route = command_module.run_minimum_route_command("CS.A2", completed_codes=["CS.I1"])
    assert projector_calls == ["course-group-a"]
    assert solver_calls == ["course-group-a"]
    assert isinstance(route, MinimumCreditPathEvaluation)
    assert route.state is PrerequisitePathState.EXACT
    assert route.total_new_credits == Decimal("0")
