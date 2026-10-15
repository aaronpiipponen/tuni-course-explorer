"""Direct course and module group-reference extraction from validated Kori objects."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from course_explorer.enums import ModuleRuleType
from course_explorer.ingestion.source import KoriContractError


@dataclass(frozen=True)
class SourceReferences:
    """Concrete course and module group IDs directly named by one source object."""

    course_group_ids: frozenset[str]
    module_group_ids: frozenset[str]


def _require_mapping(value: Any, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise KoriContractError(f"{context} must be an object")
    return value


def _require_group_id(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise KoriContractError(f"{field} must be a non-blank string")
    return value


def _formal_references(value: Any, field: str) -> tuple[set[str], set[str]]:
    if value is None:
        return set(), set()
    if not isinstance(value, list):
        raise KoriContractError(f"{field} must be a list")

    courses: set[str] = set()
    modules: set[str] = set()
    for group in value:
        group_mapping = _require_mapping(group, f"{field} group")
        prerequisites = group_mapping.get("prerequisites")
        if not isinstance(prerequisites, list):
            raise KoriContractError(f"{field} group prerequisites must be a list")
        for member in prerequisites:
            member_mapping = _require_mapping(member, f"{field} member")
            member_type = member_mapping.get("type")
            if member_type == "CourseUnit":
                courses.add(
                    _require_group_id(member_mapping.get("courseUnitGroupId"), "courseUnitGroupId")
                )
            elif member_type == "Module":
                modules.add(_require_group_id(member_mapping.get("moduleGroupId"), "moduleGroupId"))
            else:
                raise KoriContractError(f"unknown {field} member type")
    return courses, modules


def _substitution_references(value: Any) -> set[str]:
    if value is None:
        return set()
    if not isinstance(value, list):
        raise KoriContractError("substitutions must be a list")

    references: set[str] = set()
    for option in value:
        if not isinstance(option, list):
            raise KoriContractError("substitution option must be a list")
        for member in option:
            member_mapping = _require_mapping(member, "substitution member")
            references.add(
                _require_group_id(member_mapping.get("courseUnitGroupId"), "courseUnitGroupId")
            )
    return references


def extract_course_references(course: Mapping[str, Any]) -> SourceReferences:
    """Extract direct official course and module group IDs from one Kori course object."""
    if not isinstance(course, Mapping):
        raise KoriContractError("course must be an object")
    course_ids: set[str] = set()
    module_ids: set[str] = set()
    for field in ("compulsoryFormalPrerequisites", "recommendedFormalPrerequisites"):
        formal_courses, formal_modules = _formal_references(course.get(field), field)
        course_ids.update(formal_courses)
        module_ids.update(formal_modules)
    course_ids.update(_substitution_references(course.get("substitutions")))
    return SourceReferences(frozenset(course_ids), frozenset(module_ids))


_RULE_TYPES = {member.value for member in ModuleRuleType}


def _walk_rule(rule: Any, courses: set[str], modules: set[str]) -> None:
    rule_mapping = _require_mapping(rule, "module rule")
    rule_type = rule_mapping.get("type")
    if rule_type not in _RULE_TYPES:
        raise KoriContractError("unknown module rule type")
    if rule_type not in {"CourseUnitRule", "ModuleRule"} and (
        "courseUnitGroupId" in rule_mapping or "moduleGroupId" in rule_mapping
    ):
        raise KoriContractError(f"{rule_type} has mismatched group field")

    if rule_type == "CourseUnitRule":
        if "moduleGroupId" in rule_mapping:
            raise KoriContractError("CourseUnitRule has mismatched group field")
        courses.add(_require_group_id(rule_mapping.get("courseUnitGroupId"), "courseUnitGroupId"))
    elif rule_type == "ModuleRule":
        if "courseUnitGroupId" in rule_mapping:
            raise KoriContractError("ModuleRule has mismatched group field")
        modules.add(_require_group_id(rule_mapping.get("moduleGroupId"), "moduleGroupId"))
    elif rule_type in {"CreditsRule", "CourseUnitCountRule"}:
        if "rule" not in rule_mapping:
            raise KoriContractError(f"{rule_type} requires nested rule")
        _walk_rule(rule_mapping["rule"], courses, modules)
    elif rule_type == "CompositeRule":
        nested_rules = rule_mapping.get("rules")
        if not isinstance(nested_rules, list):
            raise KoriContractError("CompositeRule rules must be a list")
        for nested_rule in nested_rules:
            _walk_rule(nested_rule, courses, modules)


def extract_module_references(module: Mapping[str, Any]) -> SourceReferences:
    """Extract explicit recursive rule references while preserving unrestricted uncertainty."""
    if not isinstance(module, Mapping):
        raise KoriContractError("module must be an object")
    rule = module.get("rule")
    if rule is None:
        return SourceReferences(frozenset(), frozenset())
    courses: set[str] = set()
    modules: set[str] = set()
    _walk_rule(rule, courses, modules)
    return SourceReferences(frozenset(courses), frozenset(modules))
