"""Shared report builders for the prerequisite command/CLI tests."""

from __future__ import annotations

from typing import Any

from course_explorer.config import SearchSettings
from course_explorer.prerequisite import commands as command_module
from course_explorer.prerequisite.domain import (
    CourseRequirement,
    OfficialPrerequisiteKind,
    PrerequisiteOrigin,
)
from course_explorer.prerequisite.projection import (
    PrerequisiteGraphCompilation,
    project_prerequisite_graph,
)
from course_explorer.prerequisite.structure import PrerequisiteSolverStructure
from tests.prerequisite._expression_support import (
    course_summary,
    fixture_structure,
    official_course,
)
from tests.prerequisite._path_support import solve_route
from tests.support import settings_factory


def search_settings() -> SearchSettings:
    """Build the real required search policy from the composed public configuration."""
    return settings_factory(SearchSettings)


def compilation_for(
    root_id: str,
    prerequisite_id: str,
    *,
    is_active: bool = True,
    active_only: bool = False,
) -> PrerequisiteGraphCompilation:
    """Build one valid native compilation whose root requires the prerequisite course."""
    root = course_summary(root_id)
    prerequisite = course_summary(prerequisite_id, is_active=is_active)
    requirements = official_course(prerequisite_id)
    structure = fixture_structure(
        requirements,
        root=root,
        courses=(root, prerequisite),
        active_only=active_only,
    )
    return project_prerequisite_graph(structure)


def graph_report_for(
    compilation: PrerequisiteGraphCompilation,
) -> command_module.PrerequisiteGraphReport:
    """Build one graph-only report from a real compilation, without any route result."""
    return command_module.PrerequisiteGraphReport(
        solver=compilation.solver,
        display=compilation.display,
        drawing=compilation.drawing,
    )


def report_for(root_id: str = "root", prerequisite_id: str = "prereq"):
    """Build one valid graph-only report from a real compilation."""
    return graph_report_for(compilation_for(root_id, prerequisite_id))


def _shortfall_structure() -> PrerequisiteSolverStructure:
    """Build the real active-only module-shortfall structure over one unavailable member."""
    root = course_summary("root")
    unavailable = course_summary("inactive-unit", credits_min="4", is_active=False)
    requirements = CourseRequirement(
        type="course",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.MODULE_RULE,
        course_group_id="inactive-unit",
    )
    return fixture_structure(
        requirements,
        root=root,
        courses=(root, unavailable),
        active_only=True,
    )


def shortfall_report_for() -> dict[str, Any]:
    """Build one real active-only module-shortfall route result through the Node solver."""
    return solve_route(_shortfall_structure(), [])


def _excluded_structure() -> PrerequisiteSolverStructure:
    """Build the real structure whose drawn excluded node blocks the only route."""
    root = course_summary("root")
    blocked = course_summary("blocked")
    requirements = official_course("blocked")
    return fixture_structure(
        requirements,
        root=root,
        courses=(root, blocked),
        excluded_group_ids=("blocked",),
    )


def excluded_report_for() -> dict[str, Any]:
    """Build one real no-solution route result whose excluded node blocks the only route."""
    return solve_route(_excluded_structure(), [])


def excluded_graph_report_for() -> command_module.PrerequisiteGraphReport:
    """Build the matching graph-only report whose excluded course is drawn."""
    return graph_report_for(project_prerequisite_graph(_excluded_structure()))
