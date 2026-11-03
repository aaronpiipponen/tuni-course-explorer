"""Single-owner builders for shared prerequisite expression fixtures.

These builders assemble official and inferred course leaves plus the shared official summary DTO.
`fixture_structure` encodes one hand-built expression as the native record bundle and returns the
structure the native projector materializes from it. This is test-only input construction and is
never imported by product code.
"""

from __future__ import annotations

import json
import struct
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
from course_explorer.prerequisite.projection import PrerequisiteGraphCompilation
from course_explorer.prerequisite.structure import PrerequisiteSolverStructure
from tests.prerequisite import _fixture_library


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


def _encode_text(out: bytearray, value: str) -> None:
    encoded = value.encode()
    out += struct.pack("<I", len(encoded))
    out += encoded


def _encode_strings(out: bytearray, values: Collection[str]) -> None:
    out += struct.pack("<I", len(values))
    for value in values:
        _encode_text(out, value)


def _encode_bound(value: object) -> str:
    if value is None:
        return ""
    text = format(value, "f") if isinstance(value, Decimal) else str(value)
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _encode_fact(
    out: bytearray,
    *,
    origin: PrerequisiteOrigin,
    official_kind: OfficialPrerequisiteKind | None,
    inferred_category: InferredPrerequisiteCategory | None,
    inference: InferenceNodeMetadata | None,
) -> None:
    out.append({PrerequisiteOrigin.OFFICIAL: 0, PrerequisiteOrigin.INFERRED: 1}.get(origin, 2))
    out.append(
        255
        if official_kind is None
        else {
            OfficialPrerequisiteKind.COMPULSORY: 0,
            OfficialPrerequisiteKind.RECOMMENDED: 1,
            OfficialPrerequisiteKind.MODULE_RULE: 2,
            OfficialPrerequisiteKind.SUBSTITUTION: 3,
        }[official_kind]
    )
    out.append(
        255
        if inferred_category is None
        else {
            InferredPrerequisiteCategory.REQUIRED: 0,
            InferredPrerequisiteCategory.RECOMMENDED: 1,
        }[inferred_category]
    )
    _encode_text(
        out,
        ""
        if inference is None
        else json.dumps(
            inference.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ),
    )


def fixture_compilation(
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
) -> PrerequisiteGraphCompilation:
    """Encode one fixture expression and return the native structure with its drawing."""
    nodes: list[dict[str, object]] = []
    cycle_groups = set(cycle_group_ids)

    def finish(entry: dict[str, object]) -> int:
        nodes.append(entry)
        return len(nodes) - 1

    def convert(
        node: PrerequisiteExpression,
        *,
        owner: str,
        key: tuple[str | int, ...],
        cycle_closing: bool = False,
    ) -> int:
        entry: dict[str, object] = {
            "fact": (
                node.origin,
                node.official_kind,
                node.inferred_category,
                node.inference,
            ),
            "source": key,
            "members": (),
            "diagnostics": (),
        }
        if isinstance(node, CourseRequirement):
            closes = cycle_closing or node.course_group_id in cycle_groups
            cycle_groups.discard(node.course_group_id)
            entry.update(
                kind=0,
                children=(),
                course=node.course_group_id,
                module="",
                work_key="",
                referenced="",
                detail="",
                reason="",
                credits_min_text="",
                credits_max_text="",
                manual_min_text="",
                require_min=-1,
                require_max=-1,
                count_min=-1,
                count_max=-1,
                module_rule=node.official_kind is OfficialPrerequisiteKind.MODULE_RULE,
                cycle=closes,
            )
            return finish(entry)
        if isinstance(node, ModuleBlockRequirement):
            child = convert(node.child, owner=owner, key=(*key, 0))
            entry.update(
                kind=7,
                children=(child,),
                course="",
                module=node.module_group_id,
                work_key="",
                referenced="",
                detail="",
                reason="",
                credits_min_text="",
                credits_max_text="",
                manual_min_text="",
                require_min=-1,
                require_max=-1,
                count_min=-1,
                count_max=-1,
                module_rule=False,
                cycle=False,
                members=_fixture_member_ids(node.child),
            )
            return finish(entry)
        if isinstance(node, OpaqueCreditRequirement):
            entry.update(
                kind=8,
                children=(),
                course="",
                module="",
                work_key=node.work_key,
                referenced="",
                detail="",
                reason="",
                credits_min_text=_encode_bound(node.credits_min),
                credits_max_text=_encode_bound(node.credits_max),
                manual_min_text=_encode_bound(node.credits_min),
                require_min=-1,
                require_max=-1,
                count_min=-1,
                count_max=-1,
                module_rule=node.official_kind is OfficialPrerequisiteKind.MODULE_RULE,
                cycle=False,
            )
            return finish(entry)
        if isinstance(node, UnresolvedRequirement):
            entry.update(
                kind=9,
                children=(),
                course="",
                module="",
                work_key="",
                referenced=node.referenced_group_id or "",
                detail=node.detail or "",
                reason=node.reason.value,
                credits_min_text="",
                credits_max_text="",
                manual_min_text="",
                require_min=-1,
                require_max=-1,
                count_min=-1,
                count_max=-1,
                module_rule=False,
                cycle=False,
            )
            return finish(entry)
        children = tuple(
            convert(child, owner=owner, key=(*key, position))
            for position, child in enumerate(_fixture_children(node))
        )
        entry.update(
            children=children,
            course="",
            module="",
            work_key="",
            referenced="",
            detail="",
            reason="",
            credits_min_text="",
            credits_max_text="",
            manual_min_text="",
            require_min=-1,
            require_max=-1,
            count_min=-1,
            count_max=-1,
            module_rule=False,
            cycle=False,
        )
        if isinstance(node, AndRequirement):
            entry.update(
                kind=(10 if node.composed_role is ComposedAndRole.EXPANDED_COURSE else 1),
                module_rule=node.official_kind is OfficialPrerequisiteKind.MODULE_RULE,
            )
        elif isinstance(node, OrRequirement):
            entry["kind"] = 3 if node.composed_role is ComposedOrRole.COURSE_ALTERNATIVES else 2
        elif isinstance(node, CardinalityRequirement):
            entry.update(
                kind=4,
                require_min=node.require_min,
                require_max=node.require_max,
                module_rule=node.official_kind is OfficialPrerequisiteKind.MODULE_RULE,
            )
        elif isinstance(node, CreditRequirement):
            entry.update(
                kind=5,
                credits_min_text=_encode_bound(node.credits_min),
                credits_max_text=_encode_bound(node.credits_max),
                module_rule=True,
            )
        elif isinstance(node, CourseCountRequirement):
            entry.update(
                kind=6,
                count_min=node.count_min,
                count_max=node.count_max,
                module_rule=True,
            )
        else:
            raise ValueError(f"unsupported fixture expression {type(node).__name__}")
        return finish(entry)

    root_use = (
        convert(requirements, owner=root.group_id, key=("r",)) if requirements is not None else -1
    )
    extra_root_uses = tuple(
        convert(extra, owner=root.group_id, key=("fixture_extra", index))
        for index, extra in enumerate(extra_requirements)
    )
    if root.group_id not in {course.group_id for course in courses}:
        courses = (root, *courses)
    ordered_courses = tuple(sorted(courses, key=lambda course: course.group_id))

    out = bytearray()
    out += struct.pack("<II", 1, 1)
    _encode_text(out, root.group_id)
    out += struct.pack(
        "<i???i",
        2026,
        active_only,
        include_recommended,
        include_inferred,
        root_use,
    )
    out += struct.pack("<I", len(extra_root_uses))
    for extra_root in extra_root_uses:
        out += struct.pack("<i", extra_root)
    out += struct.pack("<I", len(nodes))
    for entry in nodes:
        origin, official_kind, inferred_category, inference = entry["fact"]
        out.append(entry["kind"])
        out += struct.pack("<I", len(entry["children"]))
        for child in entry["children"]:
            out += struct.pack("<i", child)
        for name in (
            "course",
            "module",
            "work_key",
            "referenced",
            "detail",
            "reason",
            "credits_min_text",
            "credits_max_text",
            "manual_min_text",
        ):
            _encode_text(out, entry[name])
        out += struct.pack(
            "<iiii",
            -1 if entry["require_min"] is None else entry["require_min"],
            -1 if entry["require_max"] is None else entry["require_max"],
            -1 if entry["count_min"] is None else entry["count_min"],
            -1 if entry["count_max"] is None else entry["count_max"],
        )
        out += struct.pack("<??", bool(entry["module_rule"]), bool(entry["cycle"]))
        _encode_fact(
            out,
            origin=origin,
            official_kind=official_kind,
            inferred_category=inferred_category,
            inference=inference,
        )
        out += struct.pack("<I", len(entry["source"]))
        for part in entry["source"]:
            if isinstance(part, int):
                out += struct.pack("<?q", True, part)
            else:
                out += struct.pack("<?", False)
                _encode_text(out, part)
        _encode_strings(out, entry["members"])
    out += struct.pack("<I", len(ordered_courses))
    for course in ordered_courses:
        _encode_text(out, course.group_id)
        out += struct.pack("<?", course.name_fi is not None)
        _encode_text(out, course.name_fi or "")
        out += struct.pack("<?", course.name_en is not None)
        _encode_text(out, course.name_en or "")
        _encode_text(out, course.code)
        _encode_text(out, course.official_url)
        _encode_text(out, _encode_bound(course.credits_min))
        out += struct.pack("<?", course.credits_max is not None)
        _encode_text(out, _encode_bound(course.credits_max))
        out += struct.pack("<?", course.is_active)
    out += struct.pack("<I", 0)
    out += struct.pack("<I", len(coverage))
    for record in coverage:
        _encode_text(out, record.target_group_id)
        _encode_text(out, record.coverage_state.value)
        out += struct.pack(
            "<qqq",
            record.coverage.eligible_source_count,
            record.coverage.processed_source_count,
            record.coverage.accepted_source_count,
        )
    _encode_strings(out, tuple(sorted(excluded_group_ids)))
    _encode_strings(out, tuple(sorted(completed_node_keys)))
    _encode_strings(out, tuple(sorted(excluded_node_keys)))
    out += struct.pack("<I", 0)
    return _fixture_library.project_records(bytes(out))


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
    """Encode one fixture expression and return its native structure with projector bindings."""
    return fixture_compilation(
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
        extra_requirements=extra_requirements,
    ).solver
