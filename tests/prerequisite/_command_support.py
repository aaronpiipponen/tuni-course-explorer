"""Shared report builders for the prerequisite command/CLI tests."""

from __future__ import annotations

from course_explorer.config import SearchSettings
from course_explorer.prerequisite import commands as command_module
from course_explorer.prerequisite.domain import (
    CourseRequirement,
    OfficialPrerequisiteKind,
    PrerequisiteOrigin,
)
from course_explorer.prerequisite.graph import (
    PrerequisiteCalculationTree,
    PrerequisiteGraphCompilation,
    project_prerequisite_graph,
)
from course_explorer.prerequisite.path import (
    MinimumCreditPathEvaluation,
    calculate_minimum_new_credits,
)
from tests.prerequisite._expression_support import course_summary, official_course
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
    """Build one valid compilation whose root requires the prerequisite course."""
    root = course_summary(root_id)
    prerequisite = course_summary(prerequisite_id, is_active=is_active)
    tree = PrerequisiteCalculationTree(
        root=root,
        academic_year_start=2026,
        requirements=official_course(prerequisite_id),
        courses=tuple(
            sorted((root, prerequisite), key=lambda course: course.group_id),
        ),
        include_recommended=False,
        include_inferred=False,
        active_only=active_only,
        inferred_coverage=(),
        issues=(),
    )
    return PrerequisiteGraphCompilation(tree=tree, graph=project_prerequisite_graph(tree))


def graph_report_for(
    compilation: PrerequisiteGraphCompilation,
    *,
    excluded_group_ids: tuple[str, ...] = (),
) -> command_module.PrerequisiteGraphReport:
    """Build one graph-only report from a real compilation, without any route result."""
    return command_module.PrerequisiteGraphReport(
        compilation=compilation,
        selected_group_ids=(),
        completed_group_ids=(),
        basis=command_module.PrerequisiteCalculationBasis.COMPLETED,
        excluded_group_ids=excluded_group_ids,
        drawing=command_module.prerequisite_drawing_allowance(compilation.graph, max_elements=None),
    )


def report_for(root_id: str = "root", prerequisite_id: str = "prereq"):
    """Build one valid graph-only report from a real compilation."""
    return graph_report_for(compilation_for(root_id, prerequisite_id))


def _shortfall_tree() -> PrerequisiteCalculationTree:
    """Build the real active-only module-shortfall tree over one unavailable member."""
    root = course_summary("root")
    unavailable = course_summary("inactive-unit", credits_min="4", is_active=False)
    return PrerequisiteCalculationTree(
        root=root,
        academic_year_start=2026,
        requirements=CourseRequirement(
            type="course",
            origin=PrerequisiteOrigin.OFFICIAL,
            official_kind=OfficialPrerequisiteKind.MODULE_RULE,
            course_group_id="inactive-unit",
        ),
        courses=tuple(sorted((root, unavailable), key=lambda course: course.group_id)),
        include_recommended=False,
        include_inferred=False,
        active_only=True,
        inferred_coverage=(),
        issues=(),
    )


def shortfall_report_for() -> MinimumCreditPathEvaluation:
    """Build one real active-only module-shortfall route result from the real path service."""
    return calculate_minimum_new_credits(_shortfall_tree(), [])


def _excluded_tree() -> PrerequisiteCalculationTree:
    """Build the real tree whose drawn excluded node blocks the only route."""
    root = course_summary("root")
    blocked = course_summary("blocked")
    return PrerequisiteCalculationTree(
        root=root,
        academic_year_start=2026,
        requirements=official_course("blocked"),
        courses=tuple(sorted((root, blocked), key=lambda course: course.group_id)),
        include_recommended=False,
        include_inferred=False,
        active_only=False,
        inferred_coverage=(),
        issues=(),
        excluded_group_ids=("blocked",),
    )


def excluded_report_for() -> MinimumCreditPathEvaluation:
    """Build one real no-solution route result whose excluded node blocks the only route."""
    return calculate_minimum_new_credits(_excluded_tree(), [])


def excluded_graph_report_for() -> command_module.PrerequisiteGraphReport:
    """Build the matching graph-only report whose drawn excluded node is marked."""
    tree = _excluded_tree()
    return graph_report_for(
        PrerequisiteGraphCompilation(tree=tree, graph=project_prerequisite_graph(tree)),
        excluded_group_ids=("blocked",),
    )
