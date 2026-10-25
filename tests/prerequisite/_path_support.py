"""Shared builders for the prerequisite compiler and native solver tests."""

from __future__ import annotations

import functools
from collections.abc import Collection
from decimal import Decimal
from typing import Any

from course_explorer.curriculum import CourseSummary
from course_explorer.prerequisite import commands as command_module
from course_explorer.prerequisite.domain import (
    AndRequirement,
    CardinalityRequirement,
    ComposedAndRole,
    CourseRequirement,
    CreditRequirement,
    InferenceNodeMetadata,
    OfficialPrerequisiteKind,
    OrRequirement,
    PrerequisiteExpression,
    PrerequisiteOrigin,
)
from course_explorer.prerequisite.projection import (
    PrerequisiteGraphCompilation,
    project_prerequisite_graph,
)
from course_explorer.prerequisite.structure import (
    InferredCoverageRecord,
    PrerequisiteSolverStructure,
)
from tests.prerequisite._expression_support import (
    course_summary as course_summary,
)
from tests.prerequisite._expression_support import (
    fixture_structure as _fixture_structure,
)
from tests.prerequisite._expression_support import (
    inferred_course as _shared_inferred_course,
)
from tests.prerequisite._expression_support import (
    official_course as official_course,
)

fixture_structure = _fixture_structure

INFERENCE_METADATA = InferenceNodeMetadata(confidence=Decimal("0.9"))
inferred_course = functools.partial(_shared_inferred_course, inference=INFERENCE_METADATA)


def official_and(*group_ids: str) -> AndRequirement:
    """Build one ordinary official AND branch."""
    return AndRequirement(
        type="and",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.COMPULSORY,
        children=tuple(official_course(group_id) for group_id in group_ids),
    )


def official_or(*group_ids: str) -> OrRequirement:
    """Build one ordinary official OR branch."""
    return OrRequirement(
        type="or",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.COMPULSORY,
        children=tuple(official_course(group_id) for group_id in group_ids),
    )


def expanded_course(head: str, descendants) -> AndRequirement:
    """Build the compiler's exact expanded-course composed AND for a required course."""
    return AndRequirement(
        type="and",
        origin=PrerequisiteOrigin.COMPOSED,
        composed_role=ComposedAndRole.EXPANDED_COURSE,
        children=(official_course(head), descendants),
    )


def make_compilation(
    root: CourseSummary,
    requirements: PrerequisiteExpression | None,
    courses: tuple[CourseSummary, ...],
    *,
    include_recommended: bool = False,
    include_inferred: bool = False,
    active_only: bool = False,
    coverage: tuple[InferredCoverageRecord, ...] = (),
    excluded_group_ids: tuple[str, ...] = (),
    completed_node_keys: tuple[str, ...] = (),
    excluded_node_keys: tuple[str, ...] = (),
    cycle_group_ids: tuple[str, ...] = (),
) -> PrerequisiteGraphCompilation:
    """Build one valid native compilation through the real projector."""
    structure = _fixture_structure(
        requirements,
        root=root,
        courses=courses,
        include_recommended=include_recommended,
        include_inferred=include_inferred,
        active_only=active_only,
        excluded_group_ids=excluded_group_ids,
        completed_node_keys=completed_node_keys,
        excluded_node_keys=excluded_node_keys,
        cycle_group_ids=cycle_group_ids,
        coverage=coverage,
    )
    return project_prerequisite_graph(structure)


def selected_group_ids(result: dict[str, Any]) -> tuple[str, ...]:
    """Return the selected canonical course IDs of one route result."""
    return tuple(entry["course"]["group_id"] for entry in result["new_courses"])


def solve_route(
    structure: PrerequisiteSolverStructure,
    basis_group_ids: Collection[str],
    *,
    max_compact_nodes: int | None = None,
) -> dict[str, Any]:
    """Return the real Node solver result for one structure and its explicit basis."""
    return command_module._run_node_solver(
        {
            "operation": "route",
            "structure": structure.model_dump(mode="json"),
            "basis_group_ids": list(basis_group_ids),
            "max_compact_nodes": max_compact_nodes,
        }
    )


def module_course(group_id: str) -> CourseRequirement:
    """Build one official module-rule course-unit leaf."""
    return official_course(group_id, OfficialPrerequisiteKind.MODULE_RULE)


def module_and(*group_ids: str) -> AndRequirement:
    """Build one official all-mandatory module-rule AND over course-unit leaves."""
    return AndRequirement(
        type="and",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.MODULE_RULE,
        children=tuple(module_course(group_id) for group_id in group_ids),
    )


def module_cardinality(
    require_min: int, require_max: int | None, *group_ids: str
) -> CardinalityRequirement:
    """Build one official module-rule cardinality requirement over course-unit leaves."""
    return CardinalityRequirement(
        type="cardinality",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.MODULE_RULE,
        require_min=require_min,
        require_max=require_max,
        children=tuple(module_course(group_id) for group_id in group_ids),
    )


def module_credits(credits_min: str, credits_max: str | None, *group_ids: str) -> CreditRequirement:
    """Build one official module-rule credit-range requirement over an OR of course units."""
    return CreditRequirement(
        type="credits",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=OfficialPrerequisiteKind.MODULE_RULE,
        credits_min=Decimal(credits_min),
        credits_max=None if credits_max is None else Decimal(credits_max),
        child=OrRequirement(
            type="or",
            origin=PrerequisiteOrigin.OFFICIAL,
            official_kind=OfficialPrerequisiteKind.MODULE_RULE,
            children=tuple(module_course(group_id) for group_id in group_ids),
        ),
    )
