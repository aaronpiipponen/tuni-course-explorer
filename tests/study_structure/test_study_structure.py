"""Contracts for the official structure-of-studies projection."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

import pytest

from course_explorer.curriculum import CatalogueCurriculumPeriod, CatalogueModule, CourseSummary
from course_explorer.enums import ModuleRuleType, ModuleType
from course_explorer.study_structure.service import (
    StudyStructureModule,
    StudyStructureRule,
    StudyStructureService,
)
from tests.prerequisite._graph_support import (
    catalogue_module,
    course_summary,
    module_rule,
    module_version,
)

YEAR = 2026


class _InMemoryStructureRead:
    """`CurriculumStructureRead` over supplied official DTOs."""

    def __init__(
        self, modules: tuple[CatalogueModule, ...], summaries: tuple[CourseSummary, ...]
    ) -> None:
        self._modules = tuple(sorted(modules, key=lambda module: module.group_id))
        self._summaries = {summary.group_id: summary for summary in summaries}

    def get_modules(self, group_ids) -> tuple[CatalogueModule, ...]:
        """Return only the requested supplied modules, in canonical group order."""
        wanted = set(group_ids)
        return tuple(module for module in self._modules if module.group_id in wanted)

    def get_course_summaries(self, group_ids) -> tuple[CourseSummary, ...]:
        """Return only the requested supplied summaries, in canonical group order."""
        return tuple(
            self._summaries[group_id]
            for group_id in sorted(set(group_ids))
            if group_id in self._summaries
        )


def _periods(selection: str) -> tuple[CatalogueCurriculumPeriod, ...]:
    """Exact-year membership for the default case, membership-free for the validity case."""
    if selection == "exact_year":
        return (CatalogueCurriculumPeriod(id="period-2026", academic_year_start=YEAR),)
    return ()


def _validity(selection: str) -> dict[str, date]:
    """Membership-free validity bounds for the fallback selection case."""
    if selection == "validity":
        return {"validity_start": date(2026, 1, 1)}
    return {}


def _study_rule() -> object:
    return module_rule(
        ModuleRuleType.COURSE_UNIT_RULE,
        local_id="study-course",
        referenced_group_id="course-group-inactive",
    )


def _degree_rule() -> object:
    return module_rule(
        ModuleRuleType.COMPOSITE_RULE,
        local_id="degree-root",
        all_mandatory=True,
        children=(
            module_rule(
                ModuleRuleType.COURSE_UNIT_RULE,
                local_id="mandatory-course",
                referenced_group_id="course-group-a",
            ),
            module_rule(
                ModuleRuleType.MODULE_RULE,
                sibling_position=1,
                local_id="nested-study",
                referenced_group_id="module-group-study",
            ),
            module_rule(
                ModuleRuleType.COMPOSITE_RULE,
                sibling_position=2,
                local_id="choice",
                require_min=1,
                require_max=2,
                children=(
                    module_rule(
                        ModuleRuleType.COURSE_UNIT_RULE,
                        local_id="choice-a",
                        referenced_group_id="course-group-b",
                    ),
                    module_rule(
                        ModuleRuleType.COURSE_UNIT_RULE,
                        sibling_position=1,
                        local_id="choice-b",
                        referenced_group_id="course-group-b",
                    ),
                ),
            ),
            module_rule(
                ModuleRuleType.CREDITS_RULE,
                sibling_position=3,
                local_id="credits",
                credits_min="5",
                credits_max="10",
                children=(
                    module_rule(
                        ModuleRuleType.COURSE_UNIT_COUNT_RULE,
                        local_id="count",
                        count_min=1,
                        count_max=2,
                        children=(
                            module_rule(
                                ModuleRuleType.COURSE_UNIT_RULE,
                                local_id="count-course",
                                referenced_group_id="course-group-c",
                            ),
                        ),
                    ),
                ),
            ),
            module_rule(
                ModuleRuleType.ANY_COURSE_UNIT_RULE,
                sibling_position=4,
                local_id="any-course",
            ),
            module_rule(
                ModuleRuleType.ANY_MODULE_RULE,
                sibling_position=5,
                local_id="any-module",
            ),
        ),
    ).model_copy(update={"description": {"fi": "Tutkintorakenne", "en": "Degree structure"}})


def _standard_read(selection: str) -> _InMemoryStructureRead:
    degree_version = module_version(
        "module-group-degree-v1",
        rule=_degree_rule(),
        module_type=ModuleType.DEGREE_PROGRAMME,
        curriculum_periods=_periods(selection),
        **_validity(selection),
    ).model_copy(update={"target_credits_min": Decimal("180")})
    modules = (
        catalogue_module("module-group-degree", (degree_version,)),
        catalogue_module(
            "module-group-study",
            (
                module_version(
                    "module-group-study-v1",
                    rule=_study_rule(),
                    curriculum_periods=_periods(selection),
                    **_validity(selection),
                ),
            ),
        ),
    )
    summaries = (
        course_summary("course-group-a"),
        course_summary("course-group-b"),
        course_summary("course-group-c"),
        course_summary("course-group-inactive", is_active=False),
    )
    return _InMemoryStructureRead(modules, summaries)


def _assert_inherited(projected: StudyStructureRule, source: object) -> None:
    """Assert every official AST field except children carries through the projection."""
    for key, value in source.model_dump(exclude={"children", "description"}).items():
        assert projected.model_dump()[key] == value


def _assert_projection_matches(source: object, projected: StudyStructureRule) -> None:
    """Assert the whole projected subtree keeps the source fields and child order exactly."""
    _assert_inherited(projected, source)
    assert len(projected.children) == len(source.children)
    for source_child, projected_child in zip(source.children, projected.children, strict=True):
        _assert_projection_matches(source_child, projected_child)


def _assert_full_structure(selection: str) -> None:
    read = _standard_read(selection)
    root = StudyStructureService(read, academic_year_start=YEAR).read("module-group-degree")

    assert root.module.group_id == "module-group-degree"
    assert root.module.sisu_module_id == "module-group-degree-v1"
    assert root.module.module_type is ModuleType.DEGREE_PROGRAMME
    assert root.module.code is None
    assert root.module.name_en == "Module module-group-degree-v1"
    assert (root.target_credits_min, root.target_credits_max) == (Decimal("180"), None)
    assert root.rule.node_type is ModuleRuleType.COMPOSITE_RULE
    assert root.rule.all_mandatory is True
    assert root.rule.local_id == "degree-root"
    assert root.rule.description is None
    assert "description" not in root.rule.model_dump()
    assert "description" not in root.rule.model_dump_json()
    assert len(root.rule.children) == 6
    _assert_projection_matches(_degree_rule(), root.rule)

    mandatory, nested, choice, credits, any_course, any_module = root.rule.children
    assert mandatory.node_type is ModuleRuleType.COURSE_UNIT_RULE
    assert mandatory.course == course_summary("course-group-a")
    assert mandatory.children == ()

    assert nested.node_type is ModuleRuleType.MODULE_RULE
    assert nested.local_id == "nested-study"
    assert nested.referenced_group_id == "module-group-study"
    assert nested.module is not None
    study = nested.module
    assert study.module.group_id == "module-group-study"
    assert study.module.module_type is ModuleType.STUDY_MODULE
    assert study.rule.node_type is ModuleRuleType.COURSE_UNIT_RULE
    assert study.rule.course is not None
    assert study.rule.course.group_id == "course-group-inactive"
    assert study.rule.course.is_active is False
    _assert_projection_matches(_study_rule(), study.rule)

    assert choice.node_type is ModuleRuleType.COMPOSITE_RULE
    assert (choice.require_min, choice.require_max) == (1, 2)
    assert [child.course.group_id for child in choice.children] == [
        "course-group-b",
        "course-group-b",
    ]
    assert choice.children[0].local_id != choice.children[1].local_id

    assert credits.node_type is ModuleRuleType.CREDITS_RULE
    assert (credits.credits_min, credits.credits_max) == (Decimal("5"), Decimal("10"))
    count = credits.children[0]
    assert count.node_type is ModuleRuleType.COURSE_UNIT_COUNT_RULE
    assert (count.count_min, count.count_max) == (1, 2)
    assert count.children[0].course == course_summary("course-group-c")

    assert any_course.node_type is ModuleRuleType.ANY_COURSE_UNIT_RULE
    assert any_module.node_type is ModuleRuleType.ANY_MODULE_RULE
    for unrestricted in (any_course, any_module):
        assert unrestricted.course is None
        assert unrestricted.module is None
        assert unrestricted.unresolved is None

    assert StudyStructureModule.model_validate_json(root.model_dump_json()) == root
    payload = json.loads(root.model_dump_json())
    assert payload["target_credits_min"] == "180"
    assert payload["rule"]["children"][3]["credits_min"] == "5"


def _assert_nested_missing_course() -> None:
    rule = module_rule(
        ModuleRuleType.COMPOSITE_RULE,
        all_mandatory=True,
        children=(
            module_rule(ModuleRuleType.COURSE_UNIT_RULE, referenced_group_id="course-group-absent"),
            module_rule(
                ModuleRuleType.COURSE_UNIT_RULE,
                sibling_position=1,
                referenced_group_id="course-group-a",
            ),
        ),
    )
    modules = (
        catalogue_module(
            "module-group-root",
            (
                module_version(
                    "module-group-root-v1",
                    rule=rule,
                    curriculum_periods=_periods("exact_year"),
                ),
            ),
        ),
    )
    root = StudyStructureService(
        _InMemoryStructureRead(modules, (course_summary("course-group-a"),)),
        academic_year_start=YEAR,
    ).read("module-group-root")
    missing, present = root.rule.children
    assert missing.course is None
    assert missing.unresolved == "course_not_represented"
    assert missing.referenced_group_id == "course-group-absent"
    assert present.course == course_summary("course-group-a")
    assert present.unresolved is None


def _assert_nested_missing_module() -> None:
    rule = module_rule(ModuleRuleType.MODULE_RULE, referenced_group_id="module-group-absent")
    modules = (
        catalogue_module(
            "module-group-root",
            (
                module_version(
                    "module-group-root-v1",
                    rule=rule,
                    curriculum_periods=_periods("exact_year"),
                ),
            ),
        ),
    )
    root = StudyStructureService(
        _InMemoryStructureRead(modules, ()), academic_year_start=YEAR
    ).read("module-group-root")
    assert root.rule.module is None
    assert root.rule.unresolved == "module_not_found"


def _assert_ambiguous_nested_year() -> None:
    rule = module_rule(ModuleRuleType.MODULE_RULE, referenced_group_id="module-group-ambiguous")
    ambiguous = catalogue_module(
        "module-group-ambiguous",
        (
            module_version(
                "module-group-ambiguous-v1",
                rule=module_rule(ModuleRuleType.ANY_MODULE_RULE),
                curriculum_periods=_periods("exact_year"),
            ),
            module_version(
                "module-group-ambiguous-v2",
                rule=module_rule(ModuleRuleType.ANY_MODULE_RULE),
                curriculum_periods=_periods("exact_year"),
            ),
        ),
    )
    root_module = catalogue_module(
        "module-group-root",
        (
            module_version(
                "module-group-root-v1", rule=rule, curriculum_periods=_periods("exact_year")
            ),
        ),
    )
    root = StudyStructureService(
        _InMemoryStructureRead((root_module, ambiguous), ()), academic_year_start=YEAR
    ).read("module-group-root")
    assert root.rule.module is None
    assert root.rule.unresolved == "ambiguous_version"


def _assert_ancestor_cycle() -> None:
    root_rule = module_rule(ModuleRuleType.MODULE_RULE, referenced_group_id="module-group-study")
    study_rule = module_rule(ModuleRuleType.MODULE_RULE, referenced_group_id="module-group-root")
    modules = (
        catalogue_module(
            "module-group-root",
            (
                module_version(
                    "module-group-root-v1",
                    rule=root_rule,
                    curriculum_periods=_periods("exact_year"),
                ),
            ),
        ),
        catalogue_module(
            "module-group-study",
            (
                module_version(
                    "module-group-study-v1",
                    rule=study_rule,
                    curriculum_periods=_periods("exact_year"),
                ),
            ),
        ),
    )
    root = StudyStructureService(
        _InMemoryStructureRead(modules, ()), academic_year_start=YEAR
    ).read("module-group-root")
    study = root.rule.module
    assert study is not None
    assert study.module.group_id == "module-group-study"
    assert study.rule.module is None
    assert study.rule.unresolved == "module_cycle"


def _assert_unknown_root() -> None:
    with pytest.raises(ValueError):
        StudyStructureService(_InMemoryStructureRead((), ()), academic_year_start=YEAR).read(
            "module-group-absent"
        )


def _assert_ambiguous_root() -> None:
    module = catalogue_module(
        "module-group-root",
        (
            module_version(
                "module-group-root-v1",
                rule=module_rule(ModuleRuleType.ANY_MODULE_RULE),
                curriculum_periods=_periods("exact_year"),
            ),
            module_version(
                "module-group-root-v2",
                rule=module_rule(ModuleRuleType.ANY_MODULE_RULE),
                curriculum_periods=_periods("exact_year"),
            ),
        ),
    )
    with pytest.raises(ValueError):
        StudyStructureService(_InMemoryStructureRead((module,), ()), academic_year_start=YEAR).read(
            "module-group-root"
        )


@pytest.mark.parametrize(
    "scenario",
    [
        "exact_year",
        "validity",
        "nested_missing_course",
        "nested_missing_module",
        "ambiguous_year",
        "ancestor_cycle",
        "unknown_root",
        "ambiguous_root",
    ],
)
def test_structure_preserves_official_containers_rules_and_courses(scenario: str) -> None:
    """Structure carries every official container, rule kind and reference, typed."""
    if scenario in {"exact_year", "validity"}:
        _assert_full_structure(scenario)
    elif scenario == "nested_missing_course":
        _assert_nested_missing_course()
    elif scenario == "nested_missing_module":
        _assert_nested_missing_module()
    elif scenario == "ambiguous_year":
        _assert_ambiguous_nested_year()
    elif scenario == "ancestor_cycle":
        _assert_ancestor_cycle()
    elif scenario == "unknown_root":
        _assert_unknown_root()
    else:
        _assert_ambiguous_root()
