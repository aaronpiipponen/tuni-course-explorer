"""Tests for direct official Kori reference extraction."""

import pytest

from course_explorer.ingestion.references import (
    SourceReferences,
    extract_course_references,
    extract_module_references,
)
from course_explorer.ingestion.source import KoriContractError


def test_course_references_preserve_formal_and_substitution_groups() -> None:
    """Formal course/module groups and directional substitutions remain distinguishable."""
    course = {
        "compulsoryFormalPrerequisites": [
            {
                "prerequisites": [
                    {"type": "CourseUnit", "courseUnitGroupId": "course-a"},
                    {"type": "Module", "moduleGroupId": "module-a"},
                ]
            }
        ],
        "recommendedFormalPrerequisites": [
            {"prerequisites": [{"type": "CourseUnit", "courseUnitGroupId": "course-b"}]}
        ],
        "substitutions": [
            [{"courseUnitGroupId": "course-c"}],
            [{"courseUnitGroupId": "course-d"}, {"courseUnitGroupId": "course-e"}],
        ],
    }

    assert extract_course_references(course).course_group_ids == frozenset(
        {"course-a", "course-b", "course-c", "course-d", "course-e"}
    )
    assert extract_course_references(course).module_group_ids == frozenset({"module-a"})


def test_module_references_walk_nested_rules_without_resolving_any_rules() -> None:
    """Nested explicit rules are collected while unrestricted rules add no object."""
    module = {
        "rule": {
            "type": "CreditsRule",
            "rule": {
                "type": "CompositeRule",
                "rules": [
                    {"type": "CourseUnitRule", "courseUnitGroupId": "course-a"},
                    {"type": "ModuleRule", "moduleGroupId": "module-a"},
                    {"type": "AnyCourseUnitRule"},
                    {"type": "AnyModuleRule"},
                ],
            },
        }
    }

    assert extract_module_references(module) == SourceReferences(
        course_group_ids=frozenset({"course-a"}), module_group_ids=frozenset({"module-a"})
    )


def test_reference_discovery_rejects_unknown_or_malformed_source_shapes() -> None:
    """Unknown source types fail instead of disappearing."""
    invalid_courses = (
        {"compulsoryFormalPrerequisites": [{"prerequisites": [{"type": "Unknown"}]}]},
    )
    for course in invalid_courses:
        with pytest.raises(KoriContractError):
            extract_course_references(course)

    invalid_modules = ({"rule": {"type": "UnknownRule"}},)
    for module in invalid_modules:
        with pytest.raises(KoriContractError):
            extract_module_references(module)
