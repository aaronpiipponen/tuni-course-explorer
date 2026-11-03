"""Official structure-of-studies projection for requested programme or module roots.

This module owns the read-only structure service: it selects exactly one official version of each
canonical module or programme for the configured academic year and projects that version's typed
rule tree into visible module/programme containers, shared `CourseSummary` course cards, and the
seven official rule kinds preserved as-is. A caller-supplied per-group version selection is
authoritative for the groups it names and must belong to that group's eligible set. It is a separate
projection from the prerequisite graph compiler's native calculation structure. A nested reference
that cannot be resolved is visible as an explicitly typed unresolved node.
A requested root that is unknown, has no unique current version or has no stored rule fails loudly
unless the batch read is asked to collect it as unavailable. An ambiguous root without an explicit
selection is reported separately as version-selection-required.
"""

from __future__ import annotations

from collections.abc import Collection, Iterator, Mapping
from decimal import Decimal
from typing import Literal, Protocol

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


class StudyStructureRootUnavailable(ValueError):
    """One requested root has no unique current official version with a stored rule."""


class StudyStructureVersionSelectionRequired(StudyStructureRootUnavailable):
    """One requested root has several eligible official versions and no explicit selection."""


class StudyStructureBatch(BaseModel):
    """One read of several canonical roots, the roots it could not project and the ones needing a choice."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    roots: tuple[StudyStructureModule, ...]
    unavailable_root_group_ids: tuple[str, ...]
    version_selection_required: tuple[str, ...] = ()


class FragmentBatchReader(Protocol):
    """The read a study fragment store offers to the batched service."""

    def read(
        self,
        root_group_ids: Collection[str],
        *,
        allow_unavailable: bool,
        module_versions: Mapping[str, str] | None,
    ) -> StudyStructureBatch | None:
        """Return the stored batch, or ``None`` when the service must read the roots."""
        ...


class StudyStructureService:
    """Project official programme/module structures for the configured academic year."""

    def __init__(self, curriculum: CurriculumStructureRead, *, academic_year_start: int) -> None:
        self._curriculum = curriculum
        self._academic_year_start = academic_year_start

    def read_many(
        self,
        root_group_ids: Collection[str],
        *,
        allow_unavailable: bool = False,
        module_versions: Mapping[str, str] | None = None,
        fragment_store: FragmentBatchReader | None = None,
    ) -> StudyStructureBatch:
        """Return every requested root in caller order over one shared module and summary read.

        Duplicate roots are read once and reported once. Only a root that is unknown, has no unique
        current version or has no stored rule is collected in ``unavailable_root_group_ids`` when
        ``allow_unavailable`` is true. An ambiguous root without an explicit selection is reported
        in ``version_selection_required`` regardless of that flag. Every other failure propagates.
        An empty request reads no repository data.
        """
        requested = tuple(dict.fromkeys(root_group_ids))
        versions = dict(module_versions or {})
        if not requested:
            return StudyStructureBatch(roots=(), unavailable_root_group_ids=())
        if fragment_store is not None:
            fragment = fragment_store.read(
                requested,
                allow_unavailable=allow_unavailable,
                module_versions=versions,
            )
            if fragment is not None:
                return fragment
        modules, module_map, course_summaries = self._prefetch_modules(requested, versions)
        roots: list[StudyStructureModule] = []
        unavailable: list[str] = []
        selection_required: list[str] = []
        for group_id in requested:
            try:
                roots.append(
                    self._project_root(
                        group_id,
                        modules=modules,
                        course_summaries=course_summaries,
                        module_map=module_map,
                        module_versions=versions,
                    )
                )
            except StudyStructureVersionSelectionRequired:
                selection_required.append(group_id)
            except StudyStructureRootUnavailable:
                if not allow_unavailable:
                    raise
                unavailable.append(group_id)
        return StudyStructureBatch(
            roots=tuple(roots),
            unavailable_root_group_ids=tuple(unavailable),
            version_selection_required=tuple(selection_required),
        )

    def _prefetch_modules(
        self,
        roots: Collection[str],
        module_versions: Mapping[str, str],
    ) -> tuple[
        dict[str, CatalogueModule],
        dict[str, CatalogueModule | None],
        dict[str, CourseSummary],
    ]:
        """Read every reachable module and every direct course summary in batched reads.

        The walk follows module-rule references and module-version candidates to a fixed point, so
        each reachable module is read once. An explicit selection outside a module's eligible set is
        left for projection to refuse through the same version selection. Summaries are read in
        batches of 1000. A missing module stays present in the map as ``None``.
        """
        modules: dict[str, CatalogueModule] = {}
        module_map: dict[str, CatalogueModule | None] = {}
        course_refs: set[str] = set()
        pending: set[str] = set(roots) | set(module_versions)
        loaded: set[str] = set()
        while True:
            batch = tuple(sorted(pending - loaded))
            if not batch:
                break
            loaded.update(batch)
            for module in self._curriculum.get_modules(batch):
                modules[module.group_id] = module
                module_map[module.group_id] = module
            for group_id in batch:
                module = modules.get(group_id)
                if module is None:
                    module_map.setdefault(group_id, None)
                    continue
                try:
                    version, _reason = self._select_version(module, module_versions)
                except ValueError:
                    continue
                if version is None or version.rule is None:
                    continue
                for child in self._iter_rule_nodes(version.rule):
                    if child.node_type is ModuleRuleType.COURSE_UNIT_RULE:
                        if child.referenced_group_id is not None:
                            course_refs.add(child.referenced_group_id)
                    elif child.node_type is ModuleRuleType.MODULE_RULE:
                        if child.referenced_group_id is not None:
                            pending.add(child.referenced_group_id)
        course_summaries: dict[str, CourseSummary] = {}
        ordered = sorted(course_refs)
        for start in range(0, len(ordered), 1000):
            for summary in self._curriculum.get_course_summaries(
                tuple(ordered[start : start + 1000])
            ):
                course_summaries[summary.group_id] = summary
        return modules, module_map, course_summaries

    @staticmethod
    def _iter_rule_nodes(rule: CatalogueModuleRule) -> Iterator[CatalogueModuleRule]:
        """Yield one module rule tree's nodes in order, including the root."""
        yield rule
        for child in rule.children:
            yield from StudyStructureService._iter_rule_nodes(child)

    def _project_root(
        self,
        root_group_id: str,
        *,
        modules: dict[str, CatalogueModule],
        course_summaries: dict[str, CourseSummary],
        module_map: dict[str, CatalogueModule | None],
        module_versions: Mapping[str, str],
    ) -> StudyStructureModule:
        """Project one requested root or classify its own identity and version failure."""
        module = modules.get(root_group_id)
        if module is None:
            raise StudyStructureRootUnavailable(
                f"unknown module {root_group_id!r} for academic year {self._academic_year_start}"
            )
        version, reason = self._select_version(module, module_versions)
        if version is None:
            if reason == "ambiguous_version":
                raise StudyStructureVersionSelectionRequired(
                    f"module {root_group_id!r} has several current versions for academic year "
                    f"{self._academic_year_start} and no explicit selection"
                )
            raise StudyStructureRootUnavailable(
                f"module {root_group_id!r} has no unique current version for academic year "
                f"{self._academic_year_start}: {reason}"
            )
        if version.rule is None:
            raise StudyStructureRootUnavailable(
                f"module {root_group_id!r} version {version.sisu_module_id!r} has no stored rule"
            )
        return self._project_module(
            module,
            version,
            ancestor_group_ids=(module.group_id,),
            course_summaries=course_summaries,
            module_map=module_map,
            module_versions=module_versions,
        )

    def _select_version(
        self, module: CatalogueModule, module_versions: Mapping[str, str]
    ) -> tuple[CatalogueModuleVersion | None, StudyStructureUnresolved | None]:
        """Select the explicit or sole usable version through the shared candidate policy."""
        candidates = module_version_candidates(
            module.versions, academic_year_start=self._academic_year_start
        )
        selected = module_versions.get(module.group_id)
        if selected is not None:
            for candidate in candidates:
                if candidate.sisu_module_id == selected:
                    return candidate, None
            raise ValueError(
                f"module {module.group_id!r} version {selected!r} is not eligible for academic year "
                f"{self._academic_year_start}"
            )
        if not candidates:
            return None, "no_current_version"
        if len(candidates) > 1:
            return None, "ambiguous_version"
        return candidates[0], None

    def _project_module(
        self,
        module: CatalogueModule,
        version: CatalogueModuleVersion,
        *,
        ancestor_group_ids: tuple[str, ...],
        course_summaries: dict[str, CourseSummary],
        module_map: dict[str, CatalogueModule | None],
        module_versions: Mapping[str, str],
    ) -> StudyStructureModule:
        """Project one selected module's rule tree over the prefetched course cards."""
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
                module_versions=module_versions,
            ),
        )

    def _project_rule(
        self,
        rule: CatalogueModuleRule,
        *,
        ancestor_group_ids: tuple[str, ...],
        course_summaries: dict[str, CourseSummary],
        module_map: dict[str, CatalogueModule | None],
        module_versions: Mapping[str, str],
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
                module_versions=module_versions,
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
                    module_versions=module_versions,
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
        module_versions: Mapping[str, str],
    ) -> tuple[StudyStructureModule | None, StudyStructureUnresolved | None]:
        """Project the referenced module once, or classify why it is unresolved."""
        referenced = rule.referenced_group_id
        if referenced is None:
            return None, "module_not_found"
        if referenced in ancestor_group_ids:
            return None, "module_cycle"
        module = module_map.get(referenced)
        if module is None:
            return None, "module_not_found"
        version, reason = self._select_version(module, module_versions)
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
            module_versions=module_versions,
        )
        return nested, None
