"""Single-owner builders for shared prerequisite expression fixtures.

These builders assemble official and inferred course leaves plus the shared official summary DTO.
`fixture_structure` converts one hand-built expression into the native calculation structure the
product services consume. It is test-only input construction and is never imported by product code.
"""

from __future__ import annotations

from collections.abc import Collection
from decimal import Decimal

from course_explorer.curriculum import CourseSummary
from course_explorer.prerequisite.domain import (
    AndRequirement,
    CardinalityRequirement,
    ComposedAndRole,
    ComposedOrRole,
    CourseCountRequirement,
    CourseRequirement,
    CreditRequirement,
    InferenceNodeMetadata,
    InferredPrerequisiteCategory,
    ModuleBlockRequirement,
    OfficialPrerequisiteKind,
    OpaqueCreditRequirement,
    OrRequirement,
    PrerequisiteExpression,
    PrerequisiteOrigin,
    UnresolvedRequirement,
)
from course_explorer.prerequisite.projection import project_prerequisite_graph
from course_explorer.prerequisite.structure import (
    PrerequisiteSolverStructure,
    PrerequisiteStructureBuilder,
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


def _fixture_children(expression: PrerequisiteExpression) -> tuple[PrerequisiteExpression, ...]:
    """Return one fixture expression's ordered child occurrences."""
    if isinstance(expression, (AndRequirement, OrRequirement, CardinalityRequirement)):
        return expression.children
    if isinstance(expression, (CreditRequirement, CourseCountRequirement, ModuleBlockRequirement)):
        return (expression.child,)
    return ()


def _fixture_member_ids(expression: PrerequisiteExpression) -> tuple[str, ...]:
    """Return one module fixture's explicit official member course IDs."""
    found: set[str] = set()

    def walk(node: PrerequisiteExpression) -> None:
        if isinstance(node, CourseRequirement):
            found.add(node.course_group_id)
            return
        if (
            isinstance(node, AndRequirement)
            and node.composed_role is ComposedAndRole.EXPANDED_COURSE
        ):
            head = node.children[0]
            if isinstance(head, CourseRequirement):
                found.add(head.course_group_id)
            return
        if (
            isinstance(node, OrRequirement)
            and node.composed_role is ComposedOrRole.COURSE_ALTERNATIVES
        ):
            walk(node.children[0])
            return
        for child in _fixture_children(node):
            walk(child)

    walk(expression)
    return tuple(sorted(found))


def fixture_structure(
    requirements: PrerequisiteExpression | None,
    *,
    root: CourseSummary,
    courses: tuple[CourseSummary, ...],
    include_recommended: bool = False,
    include_inferred: bool = False,
    active_only: bool = False,
    excluded_group_ids: tuple[str, ...] = (),
    completed_node_keys: Collection[str] = (),
    excluded_node_keys: Collection[str] = (),
    cycle_group_ids: Collection[str] = (),
    coverage: tuple[object, ...] = (),
    extra_requirements: tuple[PrerequisiteExpression, ...] = (),
) -> PrerequisiteSolverStructure:
    """Build one native structure with projector-installed bindings from a fixture expression."""
    builder = PrerequisiteStructureBuilder()
    cycle_groups = set(cycle_group_ids)

    def convert(
        node: PrerequisiteExpression,
        *,
        owner: str,
        key: tuple[str | int, ...],
        cycle_closing: bool = False,
    ) -> str:
        fact = builder.intern_fact(
            origin=node.origin,
            official_kind=node.official_kind,
            inferred_category=node.inferred_category,
            inference=node.inference,
        )
        if isinstance(node, CourseRequirement):
            closes = cycle_closing or node.course_group_id in cycle_groups
            cycle_groups.discard(node.course_group_id)
            piece = builder.intern_piece(
                kind="course",
                course_group_id=node.course_group_id,
                module_rule=node.official_kind is OfficialPrerequisiteKind.MODULE_RULE,
                cycle_closing=closes,
            )
            return builder.intern_use(piece_id=piece, fact_id=fact, children=(), source_key=key)
        if isinstance(node, ModuleBlockRequirement):
            child = convert(node.child, owner=owner, key=(*key, 0))
            piece = builder.intern_piece(
                kind="module_block",
                children=(builder.piece_id_of_use(child),),
                module_group_id=node.module_group_id,
            )
            return builder.intern_use(
                piece_id=piece,
                fact_id=fact,
                children=(child,),
                source_key=key,
                member_group_ids=_fixture_member_ids(node.child),
            )
        if isinstance(node, OpaqueCreditRequirement):
            piece = builder.intern_piece(
                kind="opaque_credits",
                work_key=node.work_key,
                credits_min=node.credits_min,
                credits_max=node.credits_max,
                manual_credits_min=node.credits_min,
                module_rule=node.official_kind is OfficialPrerequisiteKind.MODULE_RULE,
            )
            return builder.intern_use(piece_id=piece, fact_id=fact, children=(), source_key=key)
        if isinstance(node, UnresolvedRequirement):
            piece = builder.intern_piece(
                kind="unresolved",
                reason=node.reason.value,
                referenced_group_id=node.referenced_group_id,
                detail=node.detail,
            )
            return builder.intern_use(piece_id=piece, fact_id=fact, children=(), source_key=key)
        children = tuple(
            convert(child, owner=owner, key=(*key, index))
            for index, child in enumerate(_fixture_children(node))
        )
        child_pieces = tuple(builder.piece_id_of_use(child) for child in children)
        if isinstance(node, AndRequirement):
            kind = (
                "expanded_course"
                if node.composed_role is ComposedAndRole.EXPANDED_COURSE
                else "and"
            )
            piece = builder.intern_piece(
                kind=kind,
                children=child_pieces,
                module_rule=node.official_kind is OfficialPrerequisiteKind.MODULE_RULE,
            )
        elif isinstance(node, OrRequirement):
            kind = (
                "course_alternatives"
                if node.composed_role is ComposedOrRole.COURSE_ALTERNATIVES
                else "or"
            )
            piece = builder.intern_piece(kind=kind, children=child_pieces)
        elif isinstance(node, CardinalityRequirement):
            piece = builder.intern_piece(
                kind="cardinality",
                children=child_pieces,
                require_min=node.require_min,
                require_max=node.require_max,
                module_rule=node.official_kind is OfficialPrerequisiteKind.MODULE_RULE,
            )
        elif isinstance(node, CreditRequirement):
            piece = builder.intern_piece(
                kind="credits",
                children=child_pieces,
                credits_min=node.credits_min,
                credits_max=node.credits_max,
                module_rule=True,
            )
        elif isinstance(node, CourseCountRequirement):
            piece = builder.intern_piece(
                kind="course_count",
                children=child_pieces,
                count_min=node.count_min,
                count_max=node.count_max,
                module_rule=True,
            )
        else:
            raise ValueError(f"unsupported fixture expression {type(node).__name__}")
        return builder.intern_use(piece_id=piece, fact_id=fact, children=children, source_key=key)

    root_use = (
        convert(requirements, owner=root.group_id, key=("r",)) if requirements is not None else None
    )
    extra_root_uses = tuple(
        convert(extra, owner=root.group_id, key=("fixture_extra", index))
        for index, extra in enumerate(extra_requirements)
    )
    if root.group_id not in {course.group_id for course in courses}:
        courses = (root, *courses)
    structure = builder.finish(
        root_group_id=root.group_id,
        academic_year_start=2026,
        root_use_id=root_use,
        extra_root_use_ids=extra_root_uses,
        root_diagnostic_ids=(),
        courses=tuple(sorted(courses, key=lambda course: course.group_id)),
        modules=(),
        include_recommended=include_recommended,
        include_inferred=include_inferred,
        active_only=active_only,
        inferred_coverage=coverage,  # type: ignore[arg-type]
        excluded_group_ids=tuple(sorted(excluded_group_ids)),
        completed_node_keys=tuple(sorted(completed_node_keys)),
        excluded_node_keys=tuple(sorted(excluded_node_keys)),
    )
    return project_prerequisite_graph(structure).solver
