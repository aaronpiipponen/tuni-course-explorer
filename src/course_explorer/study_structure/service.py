"""Official structure-of-studies projection for one programme or module.

This module owns the read-only structure service: it selects exactly one official version of a
canonical module or programme for the configured academic year and projects that version's typed
rule tree into visible module/programme containers, shared `CourseSummary` course cards, and the
seven official rule kinds preserved as-is. It is a separate projection from the prerequisite graph
compiler's minimized expression. A nested reference that cannot be resolved is visible as an
explicitly typed unresolved node.
Only an unknown or ambiguous root fails loudly.
"""

from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from course_explorer.curriculum import (
    CatalogueModule,
    CatalogueModuleRule,
    CatalogueModuleVersion,
    CourseSummary,
    CurriculumStructureRead,
    ModuleSummary,
    module_version_candidates,
)
from course_explorer.enums import ModuleRuleType

StudyStructureUnresolved = Literal[
    "course_not_represented",
    "module_not_found",
    "no_current_version",
    "ambiguous_version",
    "missing_rule",
    "module_cycle",
]


class StudyStructureRule(CatalogueModuleRule):
    """One official rule node projected into the structure view.

    It carries every official AST field (node kind, position, identity, nullable bounds, reference
    and ordered children) and adds the resolved reference targets and an explicit unresolved
    marker. The interface renders each official constraint from the imported rule. The structure
    response sends the official text the interface needs.
    """

    description: dict[str, str] | None = Field(default=None, exclude=True)
    children: tuple[StudyStructureRule, ...] = ()
    course: CourseSummary | None = None
    module: StudyStructureModule | None = None
    unresolved: StudyStructureUnresolved | None = None


class StudyStructureModule(BaseModel):
    """One selected official module/programme version and its projected rule tree."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    module: ModuleSummary
    target_credits_min: Decimal | None = None
    target_credits_max: Decimal | None = None
    rule: StudyStructureRule


StudyStructureRule.model_rebuild()
StudyStructureModule.model_rebuild()


class StudyStructureService:
    """Project one official programme/module structure for the configured academic year."""

    def __init__(self, curriculum: CurriculumStructureRead, *, academic_year_start: int) -> None:
        self._curriculum = curriculum
        self._academic_year_start = academic_year_start

    def read(self, root_group_id: str) -> StudyStructureModule:
        """Return the root's official structure, failing loudly for an unknown or ambiguous root."""
        modules = {
            module.group_id: module for module in self._curriculum.get_modules((root_group_id,))
        }
        module = modules.get(root_group_id)
        if module is None:
            raise ValueError(
                f"unknown module {root_group_id!r} for academic year {self._academic_year_start}"
            )
        version, reason = self._select_version(module)
        if version is None:
            raise ValueError(
                f"module {root_group_id!r} has no unique current version for academic year "
                f"{self._academic_year_start}: {reason}"
            )
        if version.rule is None:
            raise ValueError(
                f"module {root_group_id!r} version {version.sisu_module_id!r} has no stored rule"
            )
        return self._project_module(
            module,
            version,
            ancestor_group_ids=(module.group_id,),
            course_summaries={},
            module_map={module.group_id: module},
        )

    def _select_version(
        self, module: CatalogueModule
    ) -> tuple[CatalogueModuleVersion | None, StudyStructureUnresolved | None]:
        """Select the one usable version through the shared candidate policy, else its reason."""
        candidates = module_version_candidates(
            module.versions, academic_year_start=self._academic_year_start
        )
        if not candidates:
            return None, "no_current_version"
        if len(candidates) > 1:
            return None, "ambiguous_version"
        return candidates[0], None

    def _load_module(
        self, group_id: str, module_map: dict[str, CatalogueModule | None]
    ) -> CatalogueModule | None:
        """Read one referenced module once and reuse the result for repeated references."""
        if group_id not in module_map:
            loaded = self._curriculum.get_modules((group_id,))
            module_map[group_id] = loaded[0] if loaded else None
        return module_map[group_id]

    def _collect_course_refs(self, rule: CatalogueModuleRule) -> Iterator[str]:
        """Yield direct course references of one module's rule tree, not nested module targets."""
        if rule.node_type is ModuleRuleType.COURSE_UNIT_RULE:
            if rule.referenced_group_id is not None:
                yield rule.referenced_group_id
            return
        if rule.node_type is ModuleRuleType.MODULE_RULE:
            return
        for child in rule.children:
            yield from self._collect_course_refs(child)

    def _project_module(
        self,
        module: CatalogueModule,
        version: CatalogueModuleVersion,
        *,
        ancestor_group_ids: tuple[str, ...],
        course_summaries: dict[str, CourseSummary],
        module_map: dict[str, CatalogueModule | None],
    ) -> StudyStructureModule:
        """Bulk-fetch one selected module's direct course cards once, then project its rule tree."""
        missing = tuple(
            dict.fromkeys(
                group_id
                for group_id in self._collect_course_refs(version.rule)
                if group_id not in course_summaries
            )
        )
        for summary in self._curriculum.get_course_summaries(missing):
            course_summaries[summary.group_id] = summary
        return StudyStructureModule(
            module=ModuleSummary(
                group_id=module.group_id,
                sisu_module_id=version.sisu_module_id,
                module_type=version.module_type,
                code=version.code,
                name_fi=version.name_fi,
                name_en=version.name_en,
            ),
            target_credits_min=version.target_credits_min,
            target_credits_max=version.target_credits_max,
            rule=self._project_rule(
                version.rule,
                ancestor_group_ids=ancestor_group_ids,
                course_summaries=course_summaries,
                module_map=module_map,
            ),
        )

    def _project_rule(
        self,
        rule: CatalogueModuleRule,
        *,
        ancestor_group_ids: tuple[str, ...],
        course_summaries: dict[str, CourseSummary],
        module_map: dict[str, CatalogueModule | None],
    ) -> StudyStructureRule:
        """Copy one official rule node and resolve only its direct course/module reference."""
        inherited = rule.model_dump(exclude={"children", "description"})
        if rule.node_type is ModuleRuleType.COURSE_UNIT_RULE:
            course = (
                None
                if rule.referenced_group_id is None
                else course_summaries.get(rule.referenced_group_id)
            )
            return StudyStructureRule(
                **inherited,
                course=course,
                unresolved=None if course is not None else "course_not_represented",
            )
        if rule.node_type is ModuleRuleType.MODULE_RULE:
            nested, reason = self._resolve_nested_module(
                rule,
                ancestor_group_ids=ancestor_group_ids,
                course_summaries=course_summaries,
                module_map=module_map,
            )
            return StudyStructureRule(**inherited, module=nested, unresolved=reason)
        return StudyStructureRule(
            **inherited,
            children=tuple(
                self._project_rule(
                    child,
                    ancestor_group_ids=ancestor_group_ids,
                    course_summaries=course_summaries,
                    module_map=module_map,
                )
                for child in rule.children
            ),
        )

    def _resolve_nested_module(
        self,
        rule: CatalogueModuleRule,
        *,
        ancestor_group_ids: tuple[str, ...],
        course_summaries: dict[str, CourseSummary],
        module_map: dict[str, CatalogueModule | None],
    ) -> tuple[StudyStructureModule | None, StudyStructureUnresolved | None]:
        """Project the referenced module once, or classify why it is unresolved."""
        referenced = rule.referenced_group_id
        if referenced is None:
            return None, "module_not_found"
        if referenced in ancestor_group_ids:
            return None, "module_cycle"
        module = self._load_module(referenced, module_map)
        if module is None:
            return None, "module_not_found"
        version, reason = self._select_version(module)
        if version is None:
            return None, reason
        if version.rule is None:
            return None, "missing_rule"
        nested = self._project_module(
            module,
            version,
            ancestor_group_ids=(*ancestor_group_ids, referenced),
            course_summaries=course_summaries,
            module_map=module_map,
        )
        return nested, None
