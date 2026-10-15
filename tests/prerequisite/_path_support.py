"""Shared builders for the minimum-new-credit path tests."""

from __future__ import annotations

import functools
from decimal import Decimal

from course_explorer.curriculum import CourseSummary
from course_explorer.prerequisite.domain import (
    AndRequirement,
    CardinalityRequirement,
    ComposedAndRole,
    CourseRequirement,
    CreditRequirement,
    InferenceNodeMetadata,
    OfficialPrerequisiteKind,
    OrRequirement,
    PrerequisiteNodeOccurrence,
    PrerequisiteOrigin,
)
from course_explorer.prerequisite.graph import (
    InferredCoverageRecord,
    PrerequisiteCalculationTree,
    PrerequisiteCompilationIssue,
    PrerequisiteGraphCompilation,
    project_prerequisite_graph,
)
from course_explorer.prerequisite.path import (
    MinimumCreditPathEvaluation,
)
from tests.prerequisite._expression_support import (
    course_summary as course_summary,
)
from tests.prerequisite._expression_support import (
    inferred_course as _shared_inferred_course,
)
from tests.prerequisite._expression_support import (
    node_occurrences_for_fixture as _node_occurrences_for_fixture,
)
from tests.prerequisite._expression_support import (
    official_course as official_course,
)

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
    requirements,
    courses: tuple[CourseSummary, ...],
    *,
    include_recommended: bool = False,
    include_inferred: bool = False,
    active_only: bool = False,
    coverage: tuple[InferredCoverageRecord, ...] = (),
    issues: tuple[PrerequisiteCompilationIssue, ...] = (),
    excluded_group_ids: tuple[str, ...] = (),
) -> PrerequisiteGraphCompilation:
    """Build one valid compilation, deriving its drawing graph through the real projector."""
    if root.group_id not in {course.group_id for course in courses}:
        courses = (root, *courses)
    ordered = tuple(sorted(courses, key=lambda course: course.group_id))
    node_occurrences = (
        PrerequisiteNodeOccurrence(occurrence_id="root", action_key=f"course:{root.group_id}"),
        *_node_occurrences_for_fixture(requirements),
    )
    tree = PrerequisiteCalculationTree(
        root=root,
        academic_year_start=2026,
        requirements=requirements,
        courses=ordered,
        include_recommended=include_recommended,
        include_inferred=include_inferred,
        active_only=active_only,
        inferred_coverage=coverage,
        issues=issues,
        excluded_group_ids=excluded_group_ids,
        node_occurrences=node_occurrences,
    )
    return PrerequisiteGraphCompilation(tree=tree, graph=project_prerequisite_graph(tree))


def selected_group_ids(result: MinimumCreditPathEvaluation) -> tuple[str, ...]:
    """Return the selected canonical course IDs of one result."""
    return tuple(entry.course.group_id for entry in result.new_courses)


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
