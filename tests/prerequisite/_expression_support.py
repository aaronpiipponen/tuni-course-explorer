"""Single-owner builders for shared prerequisite expression fixtures.

These builders assemble official and inferred course leaves plus the shared official summary DTO
used by the graph, path, satisfaction, domain and command test owners. The builders assemble the
supplied structure. Inferred leaves take their metadata from the caller.
"""

from __future__ import annotations

from decimal import Decimal

from course_explorer.curriculum import CourseSummary
from course_explorer.prerequisite.domain import (
    AndRequirement,
    CardinalityRequirement,
    CourseCountRequirement,
    CourseRequirement,
    CreditRequirement,
    InferenceNodeMetadata,
    InferredPrerequisiteCategory,
    ModuleBlockRequirement,
    ModuleRequirement,
    OfficialPrerequisiteKind,
    OpaqueCreditRequirement,
    OrRequirement,
    PrerequisiteExpression,
    PrerequisiteNodeOccurrence,
    PrerequisiteOrigin,
)


def course_summary(
    group_id: str,
    *,
    credits_min: str = "5",
    credits_max: str | None = None,
    is_active: bool = True,
) -> CourseSummary:
    """Build one shared official summary for direct projector/path/command tests."""
    return CourseSummary(
        group_id=group_id,
        name_en=f"Course {group_id}",
        code=group_id.upper(),
        credits_min=Decimal(credits_min),
        credits_max=None if credits_max is None else Decimal(credits_max),
        is_active=is_active,
        official_url=f"https://example.invalid/{group_id}",
    )


def official_course(
    group_id: str, kind: OfficialPrerequisiteKind = OfficialPrerequisiteKind.COMPULSORY
) -> CourseRequirement:
    """Build one official course leaf."""
    return CourseRequirement(
        type="course",
        origin=PrerequisiteOrigin.OFFICIAL,
        official_kind=kind,
        course_group_id=group_id,
    )


def inferred_course(
    group_id: str,
    category: InferredPrerequisiteCategory = InferredPrerequisiteCategory.REQUIRED,
    *,
    inference: InferenceNodeMetadata,
) -> CourseRequirement:
    """Build one inferred course leaf with an explicit category and caller-supplied metadata."""
    return CourseRequirement(
        type="course",
        origin=PrerequisiteOrigin.INFERRED,
        inferred_category=category,
        course_group_id=group_id,
        inference=inference,
    )


def _fixture_action_key(expression: PrerequisiteExpression, occurrence_id: str) -> str:
    """Return one fixture expression's metadata-only action identity.

    Canonical course/module/opaque nodes use their source identity. Every other structural node
    uses a fixture-only `requirement:test:<occurrence_id>` key. This is metadata for hand-built
    projector/path fixtures.
    """
    if isinstance(expression, CourseRequirement):
        return f"course:{expression.course_group_id}"
    if isinstance(expression, (ModuleRequirement, ModuleBlockRequirement)):
        return f"module:{expression.module_group_id}"
    if isinstance(expression, OpaqueCreditRequirement):
        return f"opaque:{expression.work_key}"
    return f"requirement:test:{occurrence_id}"


def _fixture_children(expression: PrerequisiteExpression) -> tuple[PrerequisiteExpression, ...]:
    """Return one fixture expression's ordered child occurrences."""
    if isinstance(expression, (AndRequirement, OrRequirement, CardinalityRequirement)):
        return expression.children
    if isinstance(expression, (CreditRequirement, CourseCountRequirement, ModuleBlockRequirement)):
        return (expression.child,)
    return ()


def node_occurrences_for_fixture(
    expression: PrerequisiteExpression | None,
) -> tuple[PrerequisiteNodeOccurrence, ...]:
    """Build node occurrences with fixture metadata for one hand-built fixture expression tree.

    The builder walks the supplied structure exactly like the product occurrence walker and assigns
    each node its fixture metadata. Tests of real source-key behavior use the real
    compiler instead.
    """
    occurrences: list[PrerequisiteNodeOccurrence] = []

    def walk(node: PrerequisiteExpression, occurrence_id: str) -> None:
        occurrences.append(
            PrerequisiteNodeOccurrence(
                occurrence_id=occurrence_id,
                action_key=_fixture_action_key(node, occurrence_id),
            )
        )
        for index, child in enumerate(_fixture_children(node)):
            walk(child, f"{occurrence_id}.{index}")

    if expression is not None:
        walk(expression, "r")
    return tuple(occurrences)
