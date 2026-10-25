"""Authoritative prerequisite compiler: native calculation structure from official and inferred sources.

The compiler reads the official curriculum seam, the current inferred-set seam and the global
equivalence-group seam, and interns one content-addressed piece DAG per request. A piece is one
provenance-free structural calculation node with ordered child slots. A source use binds one
source position and its provenance fact to a piece. Ordered paths through the use graph are the
implicit occurrences, so no occurrence record, reaching path or recursive solver structure is
built, stored or sent.

The mandatory-position rule, ordered source dispatch, cycle termination, module inlining,
substitution and equivalence branches, and activity policy define every compiled structure. One
ignored-source diagnostic marks each official source part that compilation simplified or dropped.
Provenance stays in the fact table. It never changes calculation cost or piece identity,
while every relationship and diagnostic keeps its own precise origin. A direct compilation returns
the same native structure plus its two pruned category roots for discovery. The drawing projection
lives in `projection.py` and consumes this structure. No second calculation representation exists.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Collection, Sequence
from dataclasses import dataclass, field, replace
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING

from course_explorer.curriculum import (
    CatalogueCourse,
    CatalogueModule,
    CatalogueModuleRule,
    CatalogueModuleVersion,
    CataloguePrerequisiteMember,
    CatalogueSubstitutionMember,
    CourseSummary,
    CurriculumGraphRead,
    ModuleSummary,
    course_summary,
    module_version_candidates,
)
from course_explorer.enums import (
    ModuleRuleType,
    PrerequisiteMemberType,
    PrerequisiteRequirementKind,
)
from course_explorer.prerequisite.domain import (
    AndRequirement,
    ComposedAndRole,
    CourseRequirement,
    CurrentEquivalenceGroup,
    EquivalenceGroupRead,
    InferenceNodeMetadata,
    InferredPrerequisiteCategory,
    InferredReadState,
    InferredSetRead,
    InferredSetReadResult,
    OfficialPrerequisiteKind,
    OrRequirement,
    PrerequisiteExpression,
    PrerequisiteOrigin,
    UnresolvedPrerequisiteReason,
    expression_course_leaf_group_ids,
)
from course_explorer.prerequisite.structure import (
    InferredCoverageRecord,
    PrerequisiteSolverStructure,
    PrerequisiteStructureBuilder,
    module_member_group_ids,
)

if TYPE_CHECKING:
    from course_explorer.prerequisite.projection import PrerequisiteGraphCompilation


_REQUIREMENT_KIND_TO_OFFICIAL: dict[PrerequisiteRequirementKind, OfficialPrerequisiteKind] = {
    PrerequisiteRequirementKind.COMPULSORY: OfficialPrerequisiteKind.COMPULSORY,
    PrerequisiteRequirementKind.RECOMMENDED: OfficialPrerequisiteKind.RECOMMENDED,
}


class PrerequisiteIgnoredPartKind(StrEnum):
    """Application handling of one official source part the calculation simplified or dropped."""

    EMPTY_OPTION = "empty_option"
    MISSING_SUBSTITUTION_COURSE = "missing_substitution_course"
    MISSING_MODULE_ALTERNATIVE = "missing_module_alternative"
    MODULE_VERSION_FALLBACK = "module_version_fallback"
    FREE_CHOICE = "free_choice"
    UNEXPANDABLE_CONTENT = "unexpandable_content"
    ALL_MANDATORY_BOUNDS = "all_mandatory_bounds"


@dataclass(frozen=True)
class DirectPrerequisiteCompilation:
    """One candidate's request-local native structure and direct category roots for discovery."""

    solver: PrerequisiteSolverStructure
    required_use_id: str | None
    recommended_use_id: str | None


@dataclass
class DirectPrerequisiteReadContext:
    """Request-local raw-input caches shared across direct-compile policies."""

    courses_by_group_id: dict[str, CatalogueCourse] = field(default_factory=dict)
    modules_by_group_id: dict[str, CatalogueModule] = field(default_factory=dict)
    missing_course_group_ids: set[str] = field(default_factory=set)
    missing_module_group_ids: set[str] = field(default_factory=set)
    inferred_read_cache: dict[str, InferredSetReadResult] = field(default_factory=dict)
    equivalence_read_cache: dict[str, tuple[CurrentEquivalenceGroup, ...]] = field(
        default_factory=dict
    )


def _connector_children(
    expression: PrerequisiteExpression,
) -> tuple[PrerequisiteExpression, ...]:
    """Return one stored source expression's ordered child occurrences."""
    if isinstance(expression, (AndRequirement, OrRequirement)):
        return expression.children
    return ()


def _require_category_homogeneous(
    expression: PrerequisiteExpression, category: InferredPrerequisiteCategory
) -> None:
    """Reject one inferred option branch that switches to another required/recommended category."""
    if expression.inferred_category is not None and expression.inferred_category is not category:
        raise ValueError("inferred option branch mixes required and recommended occurrences")
    for child in _connector_children(expression):
        _require_category_homogeneous(child, category)


def _category_option_pair(
    category: InferredPrerequisiteCategory,
    options: tuple[PrerequisiteExpression, ...],
) -> tuple[tuple[PrerequisiteExpression, ...], tuple[PrerequisiteExpression, ...]]:
    """Return `(required, recommended)` option tuples for one homogeneous category pool."""
    if category is InferredPrerequisiteCategory.REQUIRED:
        return (options, ())
    return ((), options)


def _inferred_category_options(
    category: InferredPrerequisiteCategory, children: tuple[PrerequisiteExpression, ...]
) -> tuple[PrerequisiteExpression, ...]:
    """Return one mixed-root category partition's complete stored options."""
    if not children:
        return ()
    if len(children) == 1:
        child = children[0]
        _require_category_homogeneous(child, category)
        if isinstance(child, OrRequirement):
            return child.children
        return (child,)
    if any(isinstance(child, OrRequirement) for child in children):
        raise ValueError("inferred category mixes an OR child with another same-category child")
    for child in children:
        _require_category_homogeneous(child, category)
    return (
        AndRequirement(
            type="and",
            origin=PrerequisiteOrigin.COMPOSED,
            composed_role=ComposedAndRole.LOGICAL,
            children=children,
        ),
    )


def _inferred_option_roots(
    expression: PrerequisiteExpression,
) -> tuple[tuple[PrerequisiteExpression, ...], tuple[PrerequisiteExpression, ...]]:
    """Split one stored inferred root into its required and recommended complete options."""
    root_category = expression.inferred_category
    if root_category is None:
        raise ValueError("inferred option root requires an occurrence category")
    if isinstance(expression, CourseRequirement):
        _require_category_homogeneous(expression, root_category)
        return _category_option_pair(root_category, (expression,))
    if isinstance(expression, OrRequirement):
        for child in expression.children:
            if child.inferred_category is not root_category:
                raise ValueError("inferred option OR mixes categories")
        for child in expression.children:
            _require_category_homogeneous(child, root_category)
        return _category_option_pair(root_category, expression.children)
    if isinstance(expression, AndRequirement):
        child_categories = tuple(child.inferred_category for child in expression.children)
        if all(child_category is root_category for child_category in child_categories):
            _require_category_homogeneous(expression, root_category)
            return _category_option_pair(root_category, (expression,))
        if root_category not in child_categories:
            raise ValueError("inferred option AND disagrees with its own category")
        partitions: dict[InferredPrerequisiteCategory, list[PrerequisiteExpression]] = {
            InferredPrerequisiteCategory.REQUIRED: [],
            InferredPrerequisiteCategory.RECOMMENDED: [],
        }
        for child, child_category in zip(expression.children, child_categories):
            if child_category is None:
                raise ValueError("inferred option AND has an uncategorized child")
            partitions[child_category].append(child)
        options = {
            category: _inferred_category_options(category, tuple(children))
            for category, children in partitions.items()
        }
        return (
            options[InferredPrerequisiteCategory.REQUIRED],
            options[InferredPrerequisiteCategory.RECOMMENDED],
        )
    raise ValueError("inferred option root must be a course, AND, or OR node")


def _unexpected_rule_field(rule: CatalogueModuleRule, *allowed: str) -> str | None:
    """Return the first populated module-rule field not named for the selected rule kind."""
    populated_fields = {
        "require_min": rule.require_min,
        "require_max": rule.require_max,
        "all_mandatory": rule.all_mandatory,
        "credits_min": rule.credits_min,
        "credits_max": rule.credits_max,
        "count_min": rule.count_min,
        "count_max": rule.count_max,
        "referenced_group_id": rule.referenced_group_id,
    }
    for name, value in populated_fields.items():
        if value is not None and name not in allowed:
            return name
    return None


def _module_content_unexpandable(rule: CatalogueModuleRule) -> bool:
    """Return whether one module rule tree has no expandable course/module content."""
    if rule.node_type in (ModuleRuleType.ANY_COURSE_UNIT_RULE, ModuleRuleType.ANY_MODULE_RULE):
        return True
    if rule.node_type is ModuleRuleType.COMPOSITE_RULE:
        return not rule.children or all(
            _module_content_unexpandable(child) for child in rule.children
        )
    if rule.node_type in (ModuleRuleType.CREDITS_RULE, ModuleRuleType.COURSE_UNIT_COUNT_RULE):
        return all(_module_content_unexpandable(child) for child in rule.children)
    return False


def _module_rule_references(rule: CatalogueModuleRule) -> tuple[set[str], set[str]]:
    """Return one module rule tree's explicit referenced course and module group IDs."""
    courses: set[str] = set()
    modules: set[str] = set()
    stack: list[CatalogueModuleRule] = [rule]
    while stack:
        node = stack.pop()
        referenced = node.referenced_group_id
        if referenced is not None and referenced.strip():
            if node.node_type is ModuleRuleType.COURSE_UNIT_RULE:
                courses.add(referenced)
            elif node.node_type is ModuleRuleType.MODULE_RULE:
                modules.add(referenced)
        stack.extend(node.children)
    return courses, modules


def _stable_digest(payload: str) -> str:
    """Return a fixed-length stable digest of one source-key payload."""
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:40]


def _opaque_work_key(module_group_id: str, source_path: tuple[str | int, ...]) -> str:
    """Return the stable work identity of one opaque source block."""
    payload = json.dumps(
        [module_group_id, list(source_path)], separators=(",", ":"), ensure_ascii=False
    )
    return _stable_digest(payload)


@dataclass(frozen=True)
class _UnresolvedValue:
    """One module-resolution failure ready to become an unresolved requirement use."""

    reason: UnresolvedPrerequisiteReason
    referenced_group_id: str | None
    detail: str | None


@dataclass(frozen=True)
class _CompiledOfficialOption:
    """One compiled official option staged with its source locators."""

    option_index: int
    use_id: str
    referenced_group_ids: tuple[str, ...]


_SourceKey = tuple[str, str]


_SourceVisit = tuple[str, str, bool, bool]


@dataclass(frozen=True)
class _SourceIndex:
    """One request-local source dependency graph and its strongly connected components."""

    components: dict[_SourceKey, int]

    def component(self, kind: str, group_id: str) -> int | None:
        """Return one course or module source's component, or `None` when absent."""
        return self.components.get((kind, group_id))

    def cycle_ancestors(
        self,
        *,
        kind: str,
        group_id: str,
        course_group_ids: tuple[str, ...],
        module_group_ids: tuple[str, ...],
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """Return the ordered ancestor identities that can close a cycle in this fragment."""
        component = self.component(kind, group_id)
        if component is None:
            return (course_group_ids, module_group_ids)
        return (
            tuple(
                value for value in course_group_ids if self.component("course", value) == component
            ),
            tuple(
                value for value in module_group_ids if self.component("module", value) == component
            ),
        )


@dataclass(frozen=True)
class _Fragment:
    """One memoized compiled source fragment and the request-local facts it produced."""

    use_id: str | None
    diagnostic_ids: tuple[str, ...]
    module_summaries: dict[str, ModuleSummary]
    coverage_by_group_id: dict[str, InferredCoverageRecord]


_IGNORED_DIAGNOSTIC_KINDS = frozenset(kind.value for kind in PrerequisiteIgnoredPartKind) | {
    "module_cycle",
    "course_cycle",
}


@dataclass
class _CompilationContext:
    """Per-compilation mutable traversal state. Never stored on the compiler instance."""

    courses_by_group_id: dict[str, CatalogueCourse]
    modules_by_group_id: dict[str, CatalogueModule]
    missing_course_group_ids: set[str]
    missing_module_group_ids: set[str]
    curriculum: CurriculumGraphRead
    academic_year_start: int
    include_recommended: bool
    include_inferred: bool
    active_only: bool
    inferred_sets: InferredSetRead
    equivalence_groups: EquivalenceGroupRead
    inferred_read_cache: dict[str, InferredSetReadResult]
    equivalence_read_cache: dict[str, tuple[CurrentEquivalenceGroup, ...]]
    summaries_by_group_id: dict[str, CourseSummary]
    coverage_by_group_id: dict[str, InferredCoverageRecord]
    root_group_id: str
    builder: PrerequisiteStructureBuilder
    module_summaries: dict[str, ModuleSummary] = field(default_factory=dict)
    pending_diagnostics: list[str] = field(default_factory=list)
    source_index: _SourceIndex | None = None
    course_body_memo: dict[tuple[object, ...], _Fragment] = field(default_factory=dict)
    module_body_memo: dict[tuple[object, ...], _Fragment] = field(default_factory=dict)
    rule_memo: dict[tuple[object, ...], _Fragment] = field(default_factory=dict)
    member_group_ids_memo: dict[str, tuple[str, ...]] = field(default_factory=dict)
    direct_only: bool = False
    retained_group_ids: frozenset[str] = frozenset()


def _diagnostic_kind(builder: PrerequisiteStructureBuilder, diagnostic_id: str) -> str:
    """Return one interned diagnostic's kind."""
    return builder.diagnostic(diagnostic_id).kind


def _reachable_uses(
    builder: PrerequisiteStructureBuilder, roots: tuple[str | None, ...]
) -> tuple[str, ...]:
    """Return every use reachable from the supplied roots in deterministic order."""
    seen: set[str] = set()
    stack = [root for root in roots if root is not None]
    while stack:
        use_id = stack.pop()
        if use_id in seen:
            continue
        seen.add(use_id)
        stack.extend(builder.use(use_id).children)
    return tuple(sorted(seen))


def _module_member_group_ids(context: _CompilationContext, use_id: str) -> tuple[str, ...]:
    """Return one module body's explicit official member course IDs, memoized per native use."""
    cached = context.member_group_ids_memo.get(use_id)
    if cached is not None:
        return cached
    builder = context.builder
    result = module_member_group_ids(
        use_id,
        piece_of_use=lambda current: builder.piece(builder.piece_id_of_use(current)),
        children_of_use=lambda current: builder.use(current).children,
    )
    context.member_group_ids_memo[use_id] = result
    return result


def _contains_missing_module(builder: PrerequisiteStructureBuilder, use_id: str) -> bool:
    """Return whether one compiled option contains a MISSING_MODULE occurrence."""
    for reachable in _reachable_uses(builder, (use_id,)):
        piece = builder.piece(builder.piece_id_of_use(reachable))
        if (
            piece.kind == "unresolved"
            and piece.reason == UnresolvedPrerequisiteReason.MISSING_MODULE.value
        ):
            return True
    return False


def _mandatory_children_inherit(kind: str) -> bool:
    """Return whether one piece kind passes its mandatory position to its ordered children."""
    return kind in ("and", "expanded_course", "module_block", "credits", "course_count")


def _mandatory_child_pairs(
    builder: PrerequisiteStructureBuilder, use_id: str, mandatory: bool
) -> tuple[tuple[str, bool], ...]:
    """Return each of one use's child use slots with its own mandatory flag."""
    piece = builder.piece(builder.piece_id_of_use(use_id))
    children = builder.use(use_id).children
    if _mandatory_children_inherit(piece.kind):
        return tuple((child, mandatory) for child in children)
    return tuple((child, False) for child in children)


def _strongly_connected_components(
    edges: dict[_SourceKey, set[_SourceKey]],
) -> dict[_SourceKey, int]:
    """Return one Tarjan component ID per source node without recursive Python calls."""
    indices: dict[_SourceKey, int] = {}
    low: dict[_SourceKey, int] = {}
    on_stack: set[_SourceKey] = set()
    stack: list[_SourceKey] = []
    components: dict[_SourceKey, int] = {}
    next_index = 0
    next_component = 0
    for start in sorted(edges):
        if start in indices:
            continue
        work: list[tuple[_SourceKey, int]] = [(start, 0)]
        while work:
            node, child_index = work[-1]
            if child_index == 0:
                indices[node] = next_index
                low[node] = next_index
                next_index += 1
                stack.append(node)
                on_stack.add(node)
            children = sorted(edges.get(node, ()))
            if child_index < len(children):
                child = children[child_index]
                work[-1] = (node, child_index + 1)
                if child not in indices:
                    work.append((child, 0))
                elif child in on_stack:
                    low[node] = min(low[node], indices[child])
                continue
            work.pop()
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[node])
            if low[node] == indices[node]:
                while True:
                    member = stack.pop()
                    on_stack.discard(member)
                    components[member] = next_component
                    if member == node:
                        break
                next_component += 1
    return components


def _mandatory_expanded_heads(
    context: _CompilationContext, root_use_id: str | None
) -> frozenset[str]:
    """Return mandatory expanded-course heads outside every module boundary.

    A module body is its own calculation context: its members keep their exact rules but never
    join the ordinary suppression set, so an independent occurrence of a member course elsewhere
    expands with its own prerequisites.
    """
    if root_use_id is None:
        return frozenset()
    builder = context.builder
    heads: set[str] = set()
    seen: set[tuple[str, bool]] = set()
    stack: list[tuple[str, bool]] = [(builder.piece_id_of_use(root_use_id), True)]
    while stack:
        piece_id, mandatory = stack.pop()
        marker = (piece_id, mandatory)
        if marker in seen:
            continue
        seen.add(marker)
        piece = builder.piece(piece_id)
        if piece.kind == "module_block":
            continue
        if piece.kind == "expanded_course" and mandatory and piece.children:
            head = builder.piece(piece.children[0])
            if head.course_group_id is not None:
                heads.add(head.course_group_id)
        child_mandatory = mandatory and _mandatory_children_inherit(piece.kind)
        stack.extend((child, child_mandatory) for child in piece.children)
    return frozenset(heads)


def _prune_redundant_expansions(
    context: _CompilationContext,
    root_use_id: str,
    mandatory_heads: frozenset[str],
) -> str:
    """Collapse a non-mandatory repeated expanded occurrence in a mandatory position to a leaf.

    Module boundaries are returned unchanged: their member rules are not ordinary duplicates, so
    an independent occurrence of a member elsewhere keeps its own closure.
    """
    if not mandatory_heads:
        return root_use_id
    builder = context.builder
    memo: dict[tuple[str, bool], str] = {}

    def walk(use_id: str, *, mandatory: bool) -> str:
        key = (use_id, mandatory)
        cached = memo.get(key)
        if cached is not None:
            return cached
        piece = builder.piece(builder.piece_id_of_use(use_id))
        if piece.kind == "module_block":
            memo[key] = use_id
            return use_id
        pairs = _mandatory_child_pairs(builder, use_id, mandatory)
        if piece.kind == "expanded_course" and pairs:
            head_use, head_mandatory = pairs[0]
            (descendants_use, descendants_mandatory) = pairs[1]
            head = builder.piece(builder.piece_id_of_use(head_use))
            if head.course_group_id in mandatory_heads and not mandatory:
                memo[key] = head_use
                return head_use
            pruned_descendants = walk(descendants_use, mandatory=descendants_mandatory)
            if pruned_descendants == descendants_use:
                memo[key] = use_id
                return use_id
            result = builder.reintern(use_id, children=(head_use, pruned_descendants))
            memo[key] = result
            return result
        pruned = tuple(walk(child, mandatory=child_mandatory) for child, child_mandatory in pairs)
        if pruned == builder.use(use_id).children:
            memo[key] = use_id
            return use_id
        result = builder.reintern(use_id, children=pruned)
        memo[key] = result
        return result

    return walk(root_use_id, mandatory=True)


def is_course_activity_eligible(
    structure: PrerequisiteSolverStructure,
    group_id: str,
    exception_group_ids: Collection[str],
    *,
    for_calculation: bool = False,
) -> bool:
    """Return whether one canonical course is eligible under the structure's activity scope."""
    summary = next((course for course in structure.courses if course.group_id == group_id), None)
    if summary is None:
        raise ValueError(f"course {group_id} is missing from the calculation structure courses")
    if for_calculation and group_id in structure.excluded_group_ids:
        return False
    return not structure.active_only or summary.is_active or group_id in exception_group_ids


class PrerequisiteGraphCompiler:
    """Compile one selected canonical course into its native calculation structure."""

    def __init__(
        self,
        curriculum: CurriculumGraphRead,
        inferred_sets: InferredSetRead,
        equivalence_groups: EquivalenceGroupRead,
    ) -> None:
        self._curriculum = curriculum
        self._inferred_sets = inferred_sets
        self._equivalence_groups = equivalence_groups

    def _course(self, group_id: str, *, context: _CompilationContext) -> CatalogueCourse | None:
        """Return one canonical course, reading a cache miss and retaining successful absence."""
        self._load_courses((group_id,), context=context)
        return context.courses_by_group_id.get(group_id)

    def _module(self, group_id: str, *, context: _CompilationContext) -> CatalogueModule | None:
        """Return one canonical module, reading it on a cache miss and caching every returned row."""
        self._load_modules((group_id,), context=context)
        return context.modules_by_group_id.get(group_id)

    def _load_courses(
        self,
        group_ids: Collection[str],
        *,
        context: _CompilationContext | DirectPrerequisiteReadContext,
    ) -> None:
        """Batch uncached requested courses and retain successful misses for this request."""
        missing = tuple(
            sorted(
                group_id
                for group_id in set(group_ids)
                if group_id
                and group_id not in context.courses_by_group_id
                and group_id not in context.missing_course_group_ids
            )
        )
        if not missing:
            return
        curriculum = (
            context.curriculum if isinstance(context, _CompilationContext) else self._curriculum
        )
        for course in curriculum.get_courses(missing):
            context.courses_by_group_id[course.group_id] = course
        context.missing_course_group_ids.update(
            group_id for group_id in missing if group_id not in context.courses_by_group_id
        )

    def _load_modules(
        self,
        group_ids: Collection[str],
        *,
        context: _CompilationContext | DirectPrerequisiteReadContext,
    ) -> None:
        """Batch uncached requested modules and retain successful misses for this request."""
        missing = tuple(
            sorted(
                group_id
                for group_id in set(group_ids)
                if group_id
                and group_id not in context.modules_by_group_id
                and group_id not in context.missing_module_group_ids
            )
        )
        if not missing:
            return
        curriculum = (
            context.curriculum if isinstance(context, _CompilationContext) else self._curriculum
        )
        for module in curriculum.get_modules(missing):
            context.modules_by_group_id[module.group_id] = module
        context.missing_module_group_ids.update(
            group_id for group_id in missing if group_id not in context.modules_by_group_id
        )

    def compile_structure(
        self,
        target_group_id: str,
        *,
        include_recommended: bool = False,
        include_inferred: bool = False,
        active_only: bool = False,
        retained_group_ids: Collection[str] = (),
        excluded_group_ids: Collection[str] = (),
        completed_node_keys: Collection[str] = (),
        excluded_node_keys: Collection[str] = (),
    ) -> PrerequisiteSolverStructure:
        """Build one root's native calculation structure without projecting a drawing graph."""
        if not target_group_id.strip():
            raise ValueError("target_group_id must not be blank")
        retained_inputs = tuple(retained_group_ids)
        excluded_inputs = tuple(excluded_group_ids)
        read_context = DirectPrerequisiteReadContext()
        self._load_courses((target_group_id, *retained_inputs), context=read_context)
        courses_by_group_id = read_context.courses_by_group_id
        for group_id in retained_inputs:
            if group_id not in courses_by_group_id:
                raise ValueError(f"unknown retained canonical course ID {group_id}")
        target = courses_by_group_id.get(target_group_id)
        if target is None:
            raise ValueError(f"unknown canonical target course {target_group_id}")
        if target.representative is None:
            raise ValueError(f"target course {target_group_id} has no selected representative")
        context = _CompilationContext(
            courses_by_group_id=courses_by_group_id,
            modules_by_group_id={},
            missing_course_group_ids=read_context.missing_course_group_ids,
            missing_module_group_ids=read_context.missing_module_group_ids,
            curriculum=self._curriculum,
            academic_year_start=target.activity_as_of_academic_year_start,
            include_recommended=include_recommended,
            include_inferred=include_inferred,
            active_only=active_only,
            inferred_sets=self._inferred_sets,
            equivalence_groups=self._equivalence_groups,
            inferred_read_cache={},
            equivalence_read_cache={},
            summaries_by_group_id={},
            coverage_by_group_id={},
            root_group_id=target_group_id,
            retained_group_ids=frozenset(retained_inputs),
            builder=PrerequisiteStructureBuilder(),
        )
        self._prefetch_inputs((context,), (target,))
        structure, _, _ = self._build_structure(
            target,
            context=context,
            excluded_inputs=excluded_inputs,
            completed_node_keys=tuple(completed_node_keys),
            excluded_node_keys=tuple(excluded_node_keys),
        )
        return structure

    def compile(
        self,
        target_group_id: str,
        *,
        include_recommended: bool = False,
        include_inferred: bool = False,
        active_only: bool = False,
        retained_group_ids: Collection[str] = (),
        excluded_group_ids: Collection[str] = (),
        completed_node_keys: Collection[str] = (),
        excluded_node_keys: Collection[str] = (),
    ) -> PrerequisiteGraphCompilation:
        """Build the native structure and its pure drawing projection for one root."""
        structure = self.compile_structure(
            target_group_id,
            include_recommended=include_recommended,
            include_inferred=include_inferred,
            active_only=active_only,
            retained_group_ids=retained_group_ids,
            excluded_group_ids=excluded_group_ids,
            completed_node_keys=completed_node_keys,
            excluded_node_keys=excluded_node_keys,
        )
        from course_explorer.prerequisite.projection import project_prerequisite_graph

        return project_prerequisite_graph(structure)

    def compile_direct_many(
        self,
        target_group_ids: Collection[str],
        *,
        include_inferred: bool = False,
        active_only: bool = False,
        retained_group_ids: Collection[str] = (),
        read_context: DirectPrerequisiteReadContext | None = None,
    ) -> tuple[DirectPrerequisiteCompilation, ...]:
        """Compile only the candidates' own direct options, without course ancestors."""
        targets = tuple(sorted(set(target_group_ids)))
        if not targets:
            return ()
        retained_inputs = tuple(retained_group_ids)
        context = read_context if read_context is not None else DirectPrerequisiteReadContext()
        shared_courses = context.courses_by_group_id
        shared_modules = context.modules_by_group_id
        shared_inferred = context.inferred_read_cache
        shared_equivalence = context.equivalence_read_cache
        self._load_courses((*targets, *retained_inputs), context=context)
        for group_id in retained_inputs:
            if group_id not in shared_courses:
                raise ValueError(f"unknown retained canonical course ID {group_id}")
        represented: list[CatalogueCourse] = []
        contexts: list[_CompilationContext] = []
        for target_group_id in targets:
            target = shared_courses.get(target_group_id)
            if target is None:
                raise ValueError(f"unknown canonical target course {target_group_id}")
            if target.representative is None:
                continue
            represented.append(target)
            contexts.append(
                _CompilationContext(
                    courses_by_group_id=shared_courses,
                    modules_by_group_id=shared_modules,
                    missing_course_group_ids=context.missing_course_group_ids,
                    missing_module_group_ids=context.missing_module_group_ids,
                    curriculum=self._curriculum,
                    academic_year_start=target.activity_as_of_academic_year_start,
                    include_recommended=True,
                    include_inferred=include_inferred,
                    active_only=active_only,
                    inferred_sets=self._inferred_sets,
                    equivalence_groups=self._equivalence_groups,
                    inferred_read_cache=shared_inferred,
                    equivalence_read_cache=shared_equivalence,
                    summaries_by_group_id={},
                    coverage_by_group_id={},
                    root_group_id=target_group_id,
                    direct_only=True,
                    retained_group_ids=frozenset(retained_inputs),
                    builder=PrerequisiteStructureBuilder(),
                )
            )
        self._prefetch_inputs(contexts, represented)
        compilations: list[DirectPrerequisiteCompilation] = []
        for target, context in zip(represented, contexts, strict=True):
            structure, required, recommended = self._build_structure(
                target,
                context=context,
                excluded_inputs=(),
            )
            compilations.append(
                DirectPrerequisiteCompilation(
                    solver=structure,
                    required_use_id=required,
                    recommended_use_id=recommended,
                )
            )
        return tuple(compilations)

    def _prefetch_inputs(
        self,
        contexts: Sequence[_CompilationContext],
        targets: Sequence[CatalogueCourse],
    ) -> None:
        """Warm the shared invocation dictionaries with a bounded superset of direct inputs."""
        if not contexts:
            return
        years = sorted({context.academic_year_start for context in contexts})
        include_inferred = contexts[0].include_inferred

        def load_courses(group_ids: Collection[str]) -> None:
            self._load_courses(group_ids, context=contexts[0])

        def load_modules(group_ids: Collection[str]) -> None:
            self._load_modules(group_ids, context=contexts[0])

        courses_by_group_id = contexts[0].courses_by_group_id
        modules_by_group_id = contexts[0].modules_by_group_id

        level_courses: set[str] = set()
        module_frontier: set[str] = set()
        for context, target in zip(contexts, targets, strict=True):
            representative = target.representative
            if representative is None:
                continue
            for option in representative.prerequisite_options:
                if (
                    option.requirement_kind is PrerequisiteRequirementKind.RECOMMENDED
                    and not context.include_recommended
                ):
                    continue
                for member in option.members:
                    if member.member_type is PrerequisiteMemberType.COURSE:
                        level_courses.add(member.referenced_group_id)
                    else:
                        module_frontier.add(member.referenced_group_id)
            if context.include_inferred and target.is_active:
                inferred = self._read_inferred_expression(target, context=context)
                if inferred is not None:
                    required_roots, recommended_roots = _inferred_option_roots(inferred)
                    roots = required_roots + (
                        recommended_roots if context.include_recommended else ()
                    )
                    level_courses |= (
                        set().union(*(expression_course_leaf_group_ids(root) for root in roots))
                        if roots
                        else set()
                    )
        load_courses(level_courses)
        load_modules(module_frontier)

        pending_modules = set(module_frontier)
        inspected_modules: set[str] = set()
        while pending_modules:
            new_modules = pending_modules - inspected_modules
            if not new_modules:
                break
            inspected_modules |= new_modules
            next_courses: set[str] = set()
            next_modules: set[str] = set()
            for module_group_id in sorted(new_modules):
                module = modules_by_group_id.get(module_group_id)
                if module is None:
                    continue
                for year in years:
                    candidates = module_version_candidates(
                        module.versions, academic_year_start=year, allow_nearest=True
                    )
                    if len(candidates) != 1 or candidates[0].rule is None:
                        continue
                    referenced_courses, referenced_modules = _module_rule_references(
                        candidates[0].rule
                    )
                    next_courses |= referenced_courses
                    next_modules |= referenced_modules
            load_modules(next_modules)
            load_courses(next_courses)
            level_courses |= next_courses
            pending_modules = next_modules - inspected_modules

        read_context = contexts[0]
        substitution_members: set[str] = set()
        for course_group_id in sorted(level_courses):
            course = courses_by_group_id.get(course_group_id)
            if course is None or course.representative is None:
                continue
            for option in course.representative.substitution_options:
                for member in option.members:
                    substitution_members.add(member.course_group_id)

        def warm_equivalence(group_ids: Collection[str]) -> set[str]:
            """Bulk-read missing equivalence keys and gather their returned exact members."""
            missing = sorted(
                group_id
                for group_id in set(group_ids)
                if group_id and group_id not in read_context.equivalence_read_cache
            )
            members: set[str] = set()
            if not missing:
                return members
            read = self._equivalence_groups.read_for_members(missing)
            for group_id in missing:
                groups = read[group_id]
                read_context.equivalence_read_cache[group_id] = groups
                for group in groups:
                    for member in group.members:
                        members.add(member.course_group_id)
            return members

        equivalence_members: set[str] = set()
        substitution_equivalence_members: set[str] = set()
        if include_inferred:
            equivalence_members = warm_equivalence(
                group_id
                for group_id in sorted(level_courses)
                if courses_by_group_id.get(group_id) is not None
                and courses_by_group_id[group_id].representative is not None
            )
            load_courses(substitution_members)
            substitution_equivalence_members = warm_equivalence(
                group_id
                for group_id in sorted(substitution_members)
                if group_id in courses_by_group_id
            )
        load_courses(substitution_members | equivalence_members | substitution_equivalence_members)

    def _build_source_index(
        self, target: CatalogueCourse, *, context: _CompilationContext
    ) -> _SourceIndex:
        """Build the enabled source-reference graph and its components for one compilation.

        With inferred prerequisites enabled each offered equivalence also records the edge back,
        so a course and its offered equivalents share a component. With inferred prerequisites
        off no equivalence edge exists.
        """
        edges: dict[_SourceKey, set[_SourceKey]] = {}
        pending: list[_SourceVisit] = [("course", target.group_id, False, False)]
        visited: set[_SourceVisit] = set()
        while pending:
            visit = pending.pop()
            if visit in visited:
                continue
            visited.add(visit)
            kind, group_id, allow_substitutions, allow_equivalences = visit
            if kind == "course":
                successors, equivalents = self._index_course_sources(
                    group_id,
                    root_group_id=target.group_id,
                    context=context,
                    allow_substitutions=allow_substitutions,
                    allow_equivalences=allow_equivalences,
                )
            else:
                successors = self._index_module_sources(group_id, context=context)
                equivalents = ()
            edges.setdefault((kind, group_id), set()).update(
                (successor_kind, successor_group_id)
                for successor_kind, successor_group_id, _, _ in successors
            )
            for candidate_id in equivalents:
                edges.setdefault(("course", candidate_id), set()).add(("course", group_id))
            pending.extend(successor for successor in successors if successor not in visited)
        return _SourceIndex(components=_strongly_connected_components(edges))

    def _index_course_sources(
        self,
        group_id: str,
        *,
        root_group_id: str,
        context: _CompilationContext,
        allow_substitutions: bool,
        allow_equivalences: bool,
    ) -> tuple[set[_SourceVisit], tuple[str, ...]]:
        """Return one course body's enabled source references and its offered equivalents."""
        successors: set[_SourceVisit] = set()
        course = self._course(group_id, context=context)
        if course is None or course.representative is None:
            return successors, ()
        is_root = group_id == root_group_id
        if not course.is_active and not is_root:
            return successors, ()
        representative = course.representative
        if is_root or not context.direct_only:
            for option in representative.prerequisite_options:
                if (
                    option.requirement_kind is PrerequisiteRequirementKind.RECOMMENDED
                    and not context.include_recommended
                ):
                    continue
                for member in option.members:
                    if member.referenced_group_id == group_id:
                        continue
                    if member.member_type is PrerequisiteMemberType.COURSE:
                        if self._course(member.referenced_group_id, context=context) is not None:
                            successors.add(("course", member.referenced_group_id, True, True))
                    elif self._module(member.referenced_group_id, context=context) is not None:
                        successors.add(("module", member.referenced_group_id, True, True))
            if context.include_inferred and course.is_active:
                inferred = self._read_inferred_expression(course, context=context)
                if inferred is not None:
                    successors.update(
                        self._index_expression_courses(
                            inferred, owner_group_id=group_id, context=context
                        )
                    )
        if not is_root and allow_substitutions:
            for option in representative.substitution_options:
                members = tuple(option.members)
                if not members:
                    continue
                if any(
                    self._course(member.course_group_id, context=context) is None
                    for member in members
                ):
                    continue
                for member in members:
                    if member.course_group_id != group_id:
                        successors.add(("course", member.course_group_id, False, True))
        equivalents: tuple[str, ...] = ()
        if not is_root and context.include_inferred and allow_equivalences:
            equivalents = tuple(
                candidate_id
                for _, candidate_id in self._equivalence_candidates(group_id, context=context)
                if candidate_id != root_group_id
                and self._course(candidate_id, context=context) is not None
            )
            successors.update(
                ("course", candidate_id, False, False) for candidate_id in equivalents
            )
        return successors, equivalents

    def _index_expression_courses(
        self,
        expression: PrerequisiteExpression,
        *,
        owner_group_id: str,
        context: _CompilationContext,
    ) -> set[_SourceVisit]:
        """Return every enabled inferred expression course leaf another course owns."""
        successors: set[_SourceVisit] = set()
        if (
            expression.inferred_category is InferredPrerequisiteCategory.RECOMMENDED
            and not context.include_recommended
        ):
            return successors
        if isinstance(expression, CourseRequirement):
            if (
                expression.course_group_id != owner_group_id
                and self._course(expression.course_group_id, context=context) is not None
            ):
                successors.add(("course", expression.course_group_id, True, True))
            return successors
        if isinstance(expression, (AndRequirement, OrRequirement)):
            for child in expression.children:
                successors.update(
                    self._index_expression_courses(
                        child, owner_group_id=owner_group_id, context=context
                    )
                )
        return successors

    def _index_module_sources(
        self, group_id: str, *, context: _CompilationContext
    ) -> set[_SourceVisit]:
        """Return one selected module version's enabled referenced sources."""
        successors: set[_SourceVisit] = set()
        module = self._module(group_id, context=context)
        if module is None:
            return successors
        selected = self._select_module_version(
            module, academic_year_start=context.academic_year_start
        )
        if isinstance(selected, _UnresolvedValue):
            return successors
        version, _ = selected
        if version.rule is None:
            return successors
        referenced_courses, referenced_modules = _module_rule_references(version.rule)
        for course_group_id in referenced_courses:
            if self._course(course_group_id, context=context) is not None:
                successors.add(("course", course_group_id, True, True))
        for module_group_id in referenced_modules:
            if self._module(module_group_id, context=context) is not None:
                successors.add(("module", module_group_id, True, True))
        return successors

    def _build_structure(
        self,
        target: CatalogueCourse,
        *,
        context: _CompilationContext,
        excluded_inputs: tuple[str, ...],
        completed_node_keys: tuple[str, ...] = (),
        excluded_node_keys: tuple[str, ...] = (),
    ) -> tuple[PrerequisiteSolverStructure, str | None, str | None]:
        """Build one root's native structure plus its separate required/recommended pools."""
        target_group_id = target.group_id
        root_summary = course_summary(target)
        context.summaries_by_group_id[target_group_id] = root_summary
        representative = target.representative
        if representative is None:
            raise ValueError(f"target course {target_group_id} has no selected representative")
        context.source_index = self._build_source_index(target, context=context)
        root_source_path = (target_group_id, representative.sisu_course_unit_id, "body")

        required_pool, recommended_pool = self._compile_category_pools(
            target,
            context=context,
            ancestor_course_group_ids=(target_group_id,),
            ancestor_module_group_ids=(),
            treat_inactive_as_active=True,
            source_path=root_source_path,
        )
        pools = tuple(pool for pool in (required_pool, recommended_pool) if pool is not None)
        probe: str | None
        if len(pools) == 1:
            probe = pools[0]
        elif pools:
            probe = self._structure_use(
                context,
                kind="and",
                children=pools,
                origin=PrerequisiteOrigin.COMPOSED,
                source_key=(*root_source_path, "probe"),
            )
        else:
            probe = None
        mandatory_heads = _mandatory_expanded_heads(context, probe)
        if required_pool is not None:
            required_pool = _prune_redundant_expansions(context, required_pool, mandatory_heads)
        if recommended_pool is not None:
            recommended_pool = _prune_redundant_expansions(
                context, recommended_pool, mandatory_heads
            )
        pools = tuple(pool for pool in (required_pool, recommended_pool) if pool is not None)
        if not pools:
            requirements = None
        elif len(pools) == 1:
            requirements = pools[0]
        else:
            requirements = self._structure_use(
                context,
                kind="and",
                children=pools,
                origin=PrerequisiteOrigin.COMPOSED,
                source_key=(*root_source_path, "root_pools"),
            )

        represented: set[str] = {target_group_id}
        builder = context.builder
        if requirements is not None:
            for use_id in _reachable_uses(builder, (requirements,)):
                piece = builder.piece(builder.piece_id_of_use(use_id))
                if piece.kind == "course" and piece.course_group_id is not None:
                    represented.add(piece.course_group_id)
        for group_id in represented:
            if group_id not in context.summaries_by_group_id:
                course = self._course(group_id, context=context)
                if course is None or course.representative is None:
                    raise ValueError(
                        f"represented course {group_id} has no selected representative"
                    )
                context.summaries_by_group_id[group_id] = course_summary(course)

        represented_exclusions = set(frozenset(excluded_inputs) & represented)
        root_diagnostics = tuple(sorted(set(context.pending_diagnostics)))
        reachable = _reachable_uses(builder, (requirements, required_pool, recommended_pool))
        reachable_modules = {
            piece.module_group_id
            for use_id in reachable
            for piece in (builder.piece(builder.piece_id_of_use(use_id)),)
            if piece.module_group_id is not None
        }
        reachable_modules.update(
            builder.diagnostic(diagnostic_id).module_group_id
            for diagnostic_id in root_diagnostics
            if builder.diagnostic(diagnostic_id).module_group_id is not None
        )
        structure = builder.finish(
            root_group_id=target_group_id,
            academic_year_start=target.activity_as_of_academic_year_start,
            root_use_id=requirements,
            extra_root_use_ids=(required_pool, recommended_pool),
            root_diagnostic_ids=root_diagnostics,
            courses=tuple(
                context.summaries_by_group_id[group_id] for group_id in sorted(represented)
            ),
            modules=tuple(
                context.module_summaries[group_id]
                for group_id in sorted(reachable_modules)
                if group_id in context.module_summaries
            ),
            include_recommended=context.include_recommended,
            include_inferred=context.include_inferred,
            active_only=context.active_only,
            inferred_coverage=tuple(
                context.coverage_by_group_id[group_id]
                for group_id in sorted(context.coverage_by_group_id)
                if group_id in represented or group_id == target_group_id
            ),
            excluded_group_ids=tuple(sorted(represented_exclusions)),
            completed_node_keys=tuple(sorted(set(completed_node_keys))),
            excluded_node_keys=tuple(sorted(set(excluded_node_keys))),
        )
        return structure, required_pool, recommended_pool

    def _structure_use(
        self,
        context: _CompilationContext,
        *,
        kind: str,
        children: tuple[str, ...],
        origin: PrerequisiteOrigin,
        source_key: tuple[str | int, ...],
        official_kind: OfficialPrerequisiteKind | None = None,
        inferred_category: InferredPrerequisiteCategory | None = None,
        inference: InferenceNodeMetadata | None = None,
        module_rule: bool = False,
        manual_credits_min: Decimal | None = None,
        diagnostics: tuple[str, ...] = (),
        member_group_ids: tuple[str, ...] = (),
        **payload: object,
    ) -> str:
        """Intern one structural piece and its source use from already-built child uses."""
        builder = context.builder
        child_pieces = tuple(builder.piece_id_of_use(child) for child in children)
        piece_id = builder.intern_piece(
            kind=kind,  # type: ignore[arg-type]
            children=child_pieces,
            manual_credits_min=manual_credits_min,
            module_rule=module_rule,
            cycle_closing=bool(payload.pop("cycle_closing", False)),
            **payload,
        )
        fact_id = builder.intern_fact(
            origin=origin,
            official_kind=official_kind,
            inferred_category=inferred_category,
            inference=inference,
        )
        return builder.intern_use(
            piece_id=piece_id,
            fact_id=fact_id,
            children=children,
            source_key=source_key,
            diagnostic_ids=diagnostics,
            member_group_ids=member_group_ids,
        )

    def _course_use(
        self,
        context: _CompilationContext,
        *,
        group_id: str,
        origin: PrerequisiteOrigin,
        official_kind: OfficialPrerequisiteKind | None,
        inferred_category: InferredPrerequisiteCategory | None,
        inference: InferenceNodeMetadata | None,
        source_key: tuple[str | int, ...],
        diagnostics: tuple[str, ...] = (),
        cycle_closing: bool = False,
    ) -> str:
        """Intern one canonical course leaf use."""
        return self._structure_use(
            context,
            kind="course",
            children=(),
            origin=origin,
            official_kind=official_kind,
            inferred_category=inferred_category,
            inference=inference,
            source_key=source_key,
            module_rule=official_kind is OfficialPrerequisiteKind.MODULE_RULE,
            course_group_id=group_id,
            diagnostics=diagnostics,
            cycle_closing=cycle_closing,
        )

    def _unresolved_use(
        self,
        context: _CompilationContext,
        *,
        reason: UnresolvedPrerequisiteReason,
        referenced_group_id: str | None,
        detail: str | None,
        official_kind: OfficialPrerequisiteKind | None,
        source_key: tuple[str | int, ...],
        origin: PrerequisiteOrigin = PrerequisiteOrigin.OFFICIAL,
        inferred_category: InferredPrerequisiteCategory | None = None,
        inference: InferenceNodeMetadata | None = None,
        diagnostics: tuple[str, ...] = (),
    ) -> str:
        """Intern one explicit unresolved requirement use."""
        return self._structure_use(
            context,
            kind="unresolved",
            children=(),
            origin=origin,
            official_kind=official_kind,
            inferred_category=inferred_category,
            inference=inference,
            source_key=source_key,
            module_rule=official_kind is OfficialPrerequisiteKind.MODULE_RULE,
            reason=reason.value,
            referenced_group_id=referenced_group_id,
            detail=detail,
            diagnostics=diagnostics,
        )

    def _take_pending(
        self, context: _CompilationContext, offset: int, *, keep_kinds: frozenset[str] | None = None
    ) -> tuple[str, ...]:
        """Remove and return pending diagnostics added since `offset`, optionally filtered."""
        pending = context.pending_diagnostics[offset:]
        del context.pending_diagnostics[offset:]
        if keep_kinds is None:
            return tuple(dict.fromkeys(pending))
        builder = context.builder
        kept = tuple(
            diagnostic_id
            for diagnostic_id in pending
            if _diagnostic_kind(builder, diagnostic_id) in keep_kinds
        )
        return tuple(dict.fromkeys(kept))

    def _fragment(self, context: _CompilationContext, offset: int, use_id: str | None) -> _Fragment:
        """Capture one compiled fragment's diagnostics, module summaries and coverage records."""
        reachable = _reachable_uses(context.builder, (use_id,)) if use_id is not None else ()
        module_group_ids = {
            piece.module_group_id
            for use in reachable
            for piece in (context.builder.piece(context.builder.piece_id_of_use(use)),)
            if piece.module_group_id is not None
        }
        course_group_ids = {
            piece.course_group_id
            for use in reachable
            for piece in (context.builder.piece(context.builder.piece_id_of_use(use)),)
            if piece.course_group_id is not None
        }
        return _Fragment(
            use_id=use_id,
            diagnostic_ids=tuple(dict.fromkeys(context.pending_diagnostics[offset:])),
            module_summaries={
                group_id: context.module_summaries[group_id]
                for group_id in module_group_ids
                if group_id in context.module_summaries
            },
            coverage_by_group_id={
                group_id: context.coverage_by_group_id[group_id]
                for group_id in course_group_ids
                if group_id in context.coverage_by_group_id
            },
        )

    @staticmethod
    def _apply_fragment(context: _CompilationContext, fragment: _Fragment) -> None:
        """Replay one memoized fragment's request-local facts into the current context."""
        context.pending_diagnostics.extend(fragment.diagnostic_ids)
        context.module_summaries.update(fragment.module_summaries)
        for group_id, record in fragment.coverage_by_group_id.items():
            context.coverage_by_group_id.setdefault(group_id, record)

    @staticmethod
    def _cycle_ancestors(
        context: _CompilationContext,
        *,
        kind: str,
        group_id: str,
        ancestor_course_group_ids: tuple[str, ...],
        ancestor_module_group_ids: tuple[str, ...],
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """Filter one fragment's ancestors to the sources that can close a cycle with it."""
        index = context.source_index
        if index is None:
            return (ancestor_course_group_ids, ancestor_module_group_ids)
        return index.cycle_ancestors(
            kind=kind,
            group_id=group_id,
            course_group_ids=ancestor_course_group_ids,
            module_group_ids=ancestor_module_group_ids,
        )

    def _compile_course_requirements(
        self,
        course: CatalogueCourse,
        *,
        context: _CompilationContext,
        ancestor_course_group_ids: tuple[str, ...],
        ancestor_module_group_ids: tuple[str, ...],
        treat_inactive_as_active: bool = False,
        allow_substitutions: bool = True,
        allow_equivalences: bool = True,
    ) -> str | None:
        """Pool one active course's enabled official and inferred options per category."""
        owner = ancestor_course_group_ids[-1]
        representative = course.representative
        if representative is None:
            raise ValueError(f"course {course.group_id} has no selected representative")
        ancestor_courses, ancestor_modules = self._cycle_ancestors(
            context,
            kind="course",
            group_id=course.group_id,
            ancestor_course_group_ids=ancestor_course_group_ids,
            ancestor_module_group_ids=ancestor_module_group_ids,
        )
        cache_key = (
            "course",
            course.group_id,
            representative.sisu_course_unit_id,
            owner,
            allow_substitutions,
            allow_equivalences,
            ancestor_courses,
            ancestor_modules,
        )
        cached = context.course_body_memo.get(cache_key)
        if cached is not None:
            self._apply_fragment(context, cached)
            return cached.use_id
        offset = len(context.pending_diagnostics)
        body_source_path = (course.group_id, representative.sisu_course_unit_id, "body")
        required_pool, recommended_pool = self._compile_category_pools(
            course,
            context=context,
            ancestor_course_group_ids=ancestor_course_group_ids,
            ancestor_module_group_ids=ancestor_module_group_ids,
            treat_inactive_as_active=treat_inactive_as_active,
            source_path=body_source_path,
        )
        pools = tuple(pool for pool in (required_pool, recommended_pool) if pool is not None)
        if not pools:
            result = None
        elif len(pools) == 1:
            result = pools[0]
        else:
            result = self._structure_use(
                context,
                kind="and",
                children=pools,
                origin=PrerequisiteOrigin.COMPOSED,
                source_key=(*body_source_path, "course_pools"),
            )
        context.course_body_memo[cache_key] = self._fragment(context, offset, result)
        return result

    def _compile_category_pools(
        self,
        course: CatalogueCourse,
        *,
        context: _CompilationContext,
        ancestor_course_group_ids: tuple[str, ...],
        ancestor_module_group_ids: tuple[str, ...],
        treat_inactive_as_active: bool = False,
        source_path: tuple[str | int, ...],
    ) -> tuple[str | None, str | None]:
        """Produce one active course's separate required and recommended option pools."""
        if not course.is_active and not treat_inactive_as_active:
            return (None, None)
        official_required = self._compile_official_options(
            course,
            PrerequisiteRequirementKind.COMPULSORY,
            context=context,
            ancestor_course_group_ids=ancestor_course_group_ids,
            ancestor_module_group_ids=ancestor_module_group_ids,
            source_path=source_path,
        )
        official_recommended = (
            self._compile_official_options(
                course,
                PrerequisiteRequirementKind.RECOMMENDED,
                context=context,
                ancestor_course_group_ids=ancestor_course_group_ids,
                ancestor_module_group_ids=ancestor_module_group_ids,
                source_path=source_path,
            )
            if context.include_recommended
            else ()
        )
        inferred_required: tuple[str, ...] = ()
        inferred_recommended: tuple[str, ...] = ()
        if context.include_inferred and course.is_active:
            inferred = self._read_inferred_expression(course, context=context)
            if inferred is not None:
                current = context.inferred_read_cache[course.group_id].current_set
                if current is None:
                    raise ValueError("current inferred read must expose a current set")
                inferred_path = (*source_path, "inferred", str(current.set_id))
                required_roots, recommended_roots = _inferred_option_roots(inferred)
                inferred_required = self._expand_inferred_options(
                    required_roots,
                    context=context,
                    ancestor_course_group_ids=ancestor_course_group_ids,
                    ancestor_module_group_ids=ancestor_module_group_ids,
                    source_path=inferred_path,
                )
                if context.include_recommended:
                    inferred_recommended = self._expand_inferred_options(
                        recommended_roots,
                        context=context,
                        ancestor_course_group_ids=ancestor_course_group_ids,
                        ancestor_module_group_ids=ancestor_module_group_ids,
                        source_path=inferred_path,
                    )
        required_root = self._finish_official_options(
            official_required,
            official_kind=OfficialPrerequisiteKind.COMPULSORY,
            has_inferred_alternatives=bool(inferred_required),
            context=context,
            source_path=source_path,
        )
        recommended_root = self._finish_official_options(
            official_recommended,
            official_kind=OfficialPrerequisiteKind.RECOMMENDED,
            has_inferred_alternatives=bool(inferred_recommended),
            context=context,
            source_path=source_path,
        )
        return (
            self._pool_category(
                required_root,
                inferred_required,
                OfficialPrerequisiteKind.COMPULSORY,
                context=context,
                source_path=source_path,
            ),
            self._pool_category(
                recommended_root,
                inferred_recommended,
                OfficialPrerequisiteKind.RECOMMENDED,
                context=context,
                source_path=source_path,
            ),
        )

    def _expand_inferred_options(
        self,
        roots: tuple[PrerequisiteExpression, ...],
        *,
        context: _CompilationContext,
        ancestor_course_group_ids: tuple[str, ...],
        ancestor_module_group_ids: tuple[str, ...],
        source_path: tuple[str | int, ...],
    ) -> tuple[str, ...]:
        """Expand each enabled inferred option, omitting one that disappears as a self occurrence."""
        return tuple(
            expanded
            for index, root in enumerate(roots)
            for expanded in (
                self._expand_inferred_expression(
                    root,
                    context=context,
                    ancestor_course_group_ids=ancestor_course_group_ids,
                    ancestor_module_group_ids=ancestor_module_group_ids,
                    source_path=(*source_path, index),
                ),
            )
            if expanded is not None
        )

    def _pool_category(
        self,
        official_root: str | None,
        inferred_options: tuple[str, ...],
        official_kind: OfficialPrerequisiteKind,
        *,
        context: _CompilationContext,
        source_path: tuple[str | int, ...],
    ) -> str | None:
        """Pool one category's complete official and inferred options into one flat OR."""
        if not inferred_options:
            return official_root
        builder = context.builder
        branches: list[str] = []
        if official_root is not None:
            piece = builder.piece(builder.piece_id_of_use(official_root))
            use = builder.use(official_root)
            fact = next(fact for fact in builder._facts.values() if fact.fact_id == use.fact_id)
            if (
                piece.kind == "or"
                and fact.origin is PrerequisiteOrigin.OFFICIAL
                and fact.official_kind is official_kind
            ):
                branches.extend(use.children)
            else:
                branches.append(official_root)
        branches.extend(inferred_options)
        if len(branches) == 1:
            return branches[0]
        return self._structure_use(
            context,
            kind="or",
            children=tuple(branches),
            origin=PrerequisiteOrigin.COMPOSED,
            source_key=(*source_path, official_kind.value, "pool"),
        )

    def _compile_official_options(
        self,
        course: CatalogueCourse,
        requirement_kind: PrerequisiteRequirementKind,
        *,
        context: _CompilationContext,
        ancestor_course_group_ids: tuple[str, ...],
        ancestor_module_group_ids: tuple[str, ...],
        source_path: tuple[str | int, ...],
    ) -> tuple[_CompiledOfficialOption, ...]:
        """Compile one official compulsory/recommended OR-of-AND group into staged options."""
        representative = course.representative
        if representative is None:
            raise ValueError(f"course {course.group_id} has no selected representative")
        options = tuple(
            option
            for option in representative.prerequisite_options
            if option.requirement_kind is requirement_kind
        )
        if not options:
            return ()
        option_members = tuple(member for option in options for member in option.members)
        self._load_courses(
            (
                member.referenced_group_id
                for member in option_members
                if member.member_type is PrerequisiteMemberType.COURSE
            ),
            context=context,
        )
        self._load_modules(
            (
                member.referenced_group_id
                for member in option_members
                if member.member_type is PrerequisiteMemberType.MODULE
            ),
            context=context,
        )
        official_kind = _REQUIREMENT_KIND_TO_OFFICIAL[requirement_kind]
        option_indices = tuple(option.option_index for option in options)
        if len(set(option_indices)) != len(option_indices):
            raise ValueError(
                f"course {course.group_id} has duplicate {requirement_kind.value} option indices"
            )
        compiled_options: list[_CompiledOfficialOption] = []
        for option in sorted(options, key=lambda candidate: candidate.option_index):
            member_indices = tuple(member.member_index for member in option.members)
            if len(set(member_indices)) != len(member_indices):
                raise ValueError(
                    f"course {course.group_id} has duplicate prerequisite member indices"
                )
            members = sorted(option.members, key=lambda candidate: candidate.member_index)
            if not members:
                context.pending_diagnostics.append(
                    self._ignored_diagnostic(
                        context,
                        kind=PrerequisiteIgnoredPartKind.EMPTY_OPTION,
                        official_kind=official_kind,
                        referenced_group_ids=(),
                        detail=f"{requirement_kind.value} option {option.option_index} is empty",
                    )
                )
                continue
            branch_context = replace(
                context,
                coverage_by_group_id={},
                module_summaries={},
                pending_diagnostics=[],
            )
            option_source_path = (*source_path, requirement_kind.value, option.option_index)
            compiled = tuple(
                child
                for child in (
                    self._compile_prerequisite_member(
                        member,
                        official_kind,
                        context=branch_context,
                        ancestor_course_group_ids=ancestor_course_group_ids,
                        ancestor_module_group_ids=ancestor_module_group_ids,
                        source_path=(*option_source_path, member.member_index),
                    )
                    for member in members
                )
                if child is not None
            )
            if not compiled:
                context.pending_diagnostics.extend(
                    self._take_pending(
                        branch_context,
                        0,
                        keep_kinds=_IGNORED_DIAGNOSTIC_KINDS,
                    )
                )
                context.module_summaries.update(branch_context.module_summaries)
                continue
            for group_id, record in branch_context.coverage_by_group_id.items():
                context.coverage_by_group_id.setdefault(group_id, record)
            context.module_summaries.update(branch_context.module_summaries)
            context.pending_diagnostics.extend(branch_context.pending_diagnostics)
            if len(compiled) == 1:
                option_use = compiled[0]
            else:
                option_use = self._structure_use(
                    context,
                    kind="and",
                    children=compiled,
                    origin=PrerequisiteOrigin.OFFICIAL,
                    official_kind=official_kind,
                    source_key=option_source_path,
                )
            compiled_options.append(
                _CompiledOfficialOption(
                    option_index=option.option_index,
                    use_id=option_use,
                    referenced_group_ids=tuple(member.referenced_group_id for member in members),
                )
            )
        return tuple(compiled_options)

    def _finish_official_options(
        self,
        options: tuple[_CompiledOfficialOption, ...],
        *,
        official_kind: OfficialPrerequisiteKind,
        has_inferred_alternatives: bool,
        context: _CompilationContext,
        source_path: tuple[str | int, ...],
    ) -> str | None:
        """Drop a whole missing-module option when a usable alternative exists, then pool the rest."""
        builder = context.builder
        missing_options = tuple(
            option for option in options if _contains_missing_module(builder, option.use_id)
        )
        missing_ids = {option.option_index for option in missing_options}
        usable_options = tuple(
            option for option in options if option.option_index not in missing_ids
        )
        if missing_options and (usable_options or has_inferred_alternatives):
            for option in missing_options:
                context.pending_diagnostics.append(
                    self._ignored_diagnostic(
                        context,
                        kind=PrerequisiteIgnoredPartKind.MISSING_MODULE_ALTERNATIVE,
                        official_kind=official_kind,
                        referenced_group_ids=option.referenced_group_ids,
                        detail=(
                            f"option {option.option_index} dropped: missing module; "
                            "another alternative is available"
                        ),
                    )
                )
            surviving = usable_options
        else:
            surviving = options
        if not surviving:
            return None
        if len(surviving) == 1:
            return surviving[0].use_id
        return self._structure_use(
            context,
            kind="or",
            children=tuple(option.use_id for option in surviving),
            origin=PrerequisiteOrigin.OFFICIAL,
            official_kind=official_kind,
            source_key=(*source_path, official_kind.value, "options"),
        )

    def _compile_prerequisite_member(
        self,
        member: CataloguePrerequisiteMember,
        official_kind: OfficialPrerequisiteKind,
        *,
        context: _CompilationContext,
        ancestor_course_group_ids: tuple[str, ...],
        ancestor_module_group_ids: tuple[str, ...],
        source_path: tuple[str | int, ...],
    ) -> str | None:
        """Compile one official member into a course/expanded leaf or explicit unresolved node."""
        if member.member_type is PrerequisiteMemberType.COURSE:
            if member.referenced_group_id == ancestor_course_group_ids[-1]:
                return None
            relative = self._course(member.referenced_group_id, context=context)
            if relative is None or relative.representative is None:
                return self._unresolved_use(
                    context,
                    reason=UnresolvedPrerequisiteReason.MISSING_COURSE,
                    referenced_group_id=member.referenced_group_id,
                    detail=None,
                    official_kind=official_kind,
                    source_key=source_path,
                )
            return self._expand_course_requirement(
                group_id=member.referenced_group_id,
                origin=PrerequisiteOrigin.OFFICIAL,
                official_kind=official_kind,
                inferred_category=None,
                inference=None,
                context=context,
                ancestor_course_group_ids=ancestor_course_group_ids,
                ancestor_module_group_ids=ancestor_module_group_ids,
                source_path=source_path,
            )
        if self._module(member.referenced_group_id, context=context) is None:
            return self._unresolved_use(
                context,
                reason=UnresolvedPrerequisiteReason.MISSING_MODULE,
                referenced_group_id=member.referenced_group_id,
                detail=None,
                official_kind=official_kind,
                source_key=source_path,
            )
        return self._expand_module_requirement(
            module_group_id=member.referenced_group_id,
            official_kind=official_kind,
            context=context,
            ancestor_course_group_ids=ancestor_course_group_ids,
            ancestor_module_group_ids=ancestor_module_group_ids,
            source_path=source_path,
        )

    @staticmethod
    def _select_module_version(
        module: CatalogueModule, *, academic_year_start: int
    ) -> tuple[CatalogueModuleVersion, bool] | _UnresolvedValue:
        """Return one exact stored module version and whether nearest-year fallback chose it."""
        candidates = module_version_candidates(
            module.versions, academic_year_start=academic_year_start
        )
        if len(candidates) == 1:
            return (candidates[0], False)
        if not candidates:
            fallback = module_version_candidates(
                module.versions, academic_year_start=academic_year_start, allow_nearest=True
            )
            if fallback:
                return (fallback[0], True)
        return _UnresolvedValue(
            reason=(
                UnresolvedPrerequisiteReason.AMBIGUOUS_MODULE_VERSION
                if len(candidates) > 1
                else UnresolvedPrerequisiteReason.MISSING_MODULE
            ),
            referenced_group_id=module.group_id,
            detail=None,
        )

    def _resolve_module_version(
        self,
        module_group_id: str,
        *,
        official_kind: OfficialPrerequisiteKind,
        context: _CompilationContext,
        source_path: tuple[str | int, ...],
    ) -> CatalogueModuleVersion | _UnresolvedValue:
        """Select one exact stored module version for the root's academic year, or report why not."""
        module = self._module(module_group_id, context=context)
        if module is None:
            return _UnresolvedValue(
                reason=UnresolvedPrerequisiteReason.MISSING_MODULE,
                referenced_group_id=module_group_id,
                detail=None,
            )
        year = context.academic_year_start
        selected = self._select_module_version(module, academic_year_start=year)
        if isinstance(selected, _UnresolvedValue):
            return selected
        version, used_fallback = selected
        if used_fallback:
            context.pending_diagnostics.append(
                self._ignored_diagnostic(
                    context,
                    kind=PrerequisiteIgnoredPartKind.MODULE_VERSION_FALLBACK,
                    official_kind=official_kind,
                    referenced_group_ids=(module.group_id,),
                    detail=f"requested year {year}; selected {version.sisu_module_id}",
                    module_group_id=module.group_id,
                )
            )
        return version

    def _expand_module_requirement(
        self,
        *,
        module_group_id: str,
        official_kind: OfficialPrerequisiteKind,
        context: _CompilationContext,
        ancestor_course_group_ids: tuple[str, ...],
        ancestor_module_group_ids: tuple[str, ...],
        source_path: tuple[str | int, ...],
    ) -> str | None:
        """Inline one module reference as a native module-block over its compiled rule."""
        offset = len(context.pending_diagnostics)
        if module_group_id in ancestor_module_group_ids:
            _, cycle_modules = self._cycle_ancestors(
                context,
                kind="module",
                group_id=module_group_id,
                ancestor_course_group_ids=ancestor_course_group_ids,
                ancestor_module_group_ids=ancestor_module_group_ids,
            )
            cycle_path = " -> ".join(cycle_modules + (module_group_id,))
            diagnostic = self._ignored_diagnostic(
                context,
                kind="module_cycle",
                official_kind=official_kind,
                referenced_group_ids=(module_group_id,),
                detail=f"module cycle: {cycle_path}",
                module_group_id=module_group_id,
            )
            return self._unresolved_use(
                context,
                reason=UnresolvedPrerequisiteReason.MODULE_CYCLE,
                referenced_group_id=module_group_id,
                detail=f"module cycle: {cycle_path}",
                official_kind=official_kind,
                source_key=source_path,
                diagnostics=(diagnostic,),
            )
        version = self._resolve_module_version(
            module_group_id,
            official_kind=official_kind,
            context=context,
            source_path=source_path,
        )
        if isinstance(version, _UnresolvedValue):
            return self._unresolved_use(
                context,
                reason=version.reason,
                referenced_group_id=version.referenced_group_id,
                detail=version.detail,
                official_kind=official_kind,
                source_key=source_path,
            )
        module_summary = ModuleSummary(
            group_id=module_group_id,
            sisu_module_id=version.sisu_module_id,
            module_type=version.module_type,
            code=version.code,
            name_fi=version.name_fi,
            name_en=version.name_en,
        )
        context.module_summaries[module_group_id] = module_summary
        module_source_path = ("module", module_group_id, version.sisu_module_id)
        work_path = (version.sisu_module_id,)
        if version.rule is None:
            context.pending_diagnostics.append(
                self._ignored_diagnostic(
                    context,
                    kind=PrerequisiteIgnoredPartKind.UNEXPANDABLE_CONTENT,
                    official_kind=official_kind,
                    referenced_group_ids=(module_summary.group_id,),
                    detail=f"module version {version.sisu_module_id} has no stored rule tree",
                    module_group_id=module_group_id,
                )
            )
            compiled = None
        else:
            referenced_courses, referenced_modules = _module_rule_references(version.rule)
            self._load_courses(
                referenced_courses - {ancestor_course_group_ids[-1]}, context=context
            )
            self._load_modules(referenced_modules, context=context)
            ancestor_courses, ancestor_modules = self._cycle_ancestors(
                context,
                kind="module",
                group_id=module_group_id,
                ancestor_course_group_ids=ancestor_course_group_ids,
                ancestor_module_group_ids=ancestor_module_group_ids,
            )
            cache_key = (
                "module",
                module_group_id,
                version.sisu_module_id,
                ancestor_course_group_ids[-1],
                True,
                True,
                ancestor_courses,
                ancestor_modules,
            )
            cached = context.module_body_memo.get(cache_key)
            if cached is not None:
                self._apply_fragment(context, cached)
                compiled = cached.use_id
            else:
                body_offset = len(context.pending_diagnostics)
                compiled = self._compile_module_rule(
                    version.rule,
                    module_group_id=module_group_id,
                    context=context,
                    ancestor_course_group_ids=ancestor_course_group_ids,
                    ancestor_module_group_ids=ancestor_module_group_ids + (module_group_id,),
                    source_path=module_source_path,
                    work_path=work_path,
                )
                context.module_body_memo[cache_key] = self._fragment(context, body_offset, compiled)
        if compiled is None:
            credited_unexpandable = version.target_credits_min is not None and (
                version.rule is None or _module_content_unexpandable(version.rule)
            )
            if credited_unexpandable:
                compiled = self._structure_use(
                    context,
                    kind="opaque_credits",
                    children=(),
                    origin=PrerequisiteOrigin.OFFICIAL,
                    official_kind=OfficialPrerequisiteKind.MODULE_RULE,
                    source_key=module_source_path,
                    module_rule=True,
                    manual_credits_min=version.target_credits_min,
                    work_key=_opaque_work_key(module_group_id, (version.sisu_module_id,)),
                    credits_min=version.target_credits_min,
                    credits_max=version.target_credits_max,
                )
            else:
                return None
        member_group_ids = _module_member_group_ids(context, compiled)
        diagnostics = self._take_pending(context, offset)
        context.module_summaries[module_group_id] = module_summary
        return self._structure_use(
            context,
            kind="module_block",
            children=(compiled,),
            origin=PrerequisiteOrigin.OFFICIAL,
            official_kind=official_kind,
            source_key=source_path,
            module_group_id=module_group_id,
            credits_min=version.target_credits_min,
            credits_max=version.target_credits_max,
            manual_credits_min=version.target_credits_min,
            diagnostics=diagnostics,
            member_group_ids=member_group_ids,
        )

    def _ignored_diagnostic(
        self,
        context: _CompilationContext,
        *,
        kind: PrerequisiteIgnoredPartKind | str,
        official_kind: OfficialPrerequisiteKind,
        referenced_group_ids: tuple[str, ...] = (),
        detail: str | None = None,
        module_group_id: str | None = None,
    ) -> str:
        """Intern one ignored-source diagnostic anchored by the caller's use."""
        builder = context.builder
        fact_id = builder.intern_fact(
            origin=PrerequisiteOrigin.OFFICIAL, official_kind=official_kind
        )
        return builder.intern_diagnostic(
            kind=kind.value if isinstance(kind, PrerequisiteIgnoredPartKind) else kind,
            fact_id=fact_id,
            referenced_group_ids=referenced_group_ids,
            detail=detail,
            module_group_id=module_group_id,
        )

    def _compile_module_rule(
        self,
        rule: CatalogueModuleRule,
        *,
        module_group_id: str,
        context: _CompilationContext,
        ancestor_course_group_ids: tuple[str, ...],
        ancestor_module_group_ids: tuple[str, ...],
        source_path: tuple[str | int, ...],
        work_path: tuple[str | int, ...],
    ) -> str | None:
        """Compile one stored typed module-rule node with a source-local fragment memo."""
        ancestor_courses, ancestor_modules = self._cycle_ancestors(
            context,
            kind="module",
            group_id=module_group_id,
            ancestor_course_group_ids=ancestor_course_group_ids,
            ancestor_module_group_ids=ancestor_module_group_ids,
        )
        cache_key = (
            "rule",
            module_group_id,
            source_path[2],
            *tuple(source_path[3:]),
            ancestor_course_group_ids[-1],
            True,
            True,
            ancestor_courses,
            ancestor_modules,
        )
        cached = context.rule_memo.get(cache_key)
        if cached is not None:
            self._apply_fragment(context, cached)
            return cached.use_id
        offset = len(context.pending_diagnostics)
        result = self._dispatch_module_rule(
            rule,
            module_group_id=module_group_id,
            context=context,
            ancestor_course_group_ids=ancestor_course_group_ids,
            ancestor_module_group_ids=ancestor_module_group_ids,
            source_path=source_path,
            work_path=work_path,
        )
        context.rule_memo[cache_key] = self._fragment(context, offset, result)
        return result

    def _dispatch_module_rule(
        self,
        rule: CatalogueModuleRule,
        *,
        module_group_id: str,
        context: _CompilationContext,
        ancestor_course_group_ids: tuple[str, ...],
        ancestor_module_group_ids: tuple[str, ...],
        source_path: tuple[str | int, ...],
        work_path: tuple[str | int, ...],
    ) -> str | None:
        """Compile one stored typed module-rule node into exact native structure."""
        match rule.node_type:
            case ModuleRuleType.COMPOSITE_RULE:
                return self._compile_composite_rule(
                    rule,
                    module_group_id=module_group_id,
                    context=context,
                    ancestor_course_group_ids=ancestor_course_group_ids,
                    ancestor_module_group_ids=ancestor_module_group_ids,
                    source_path=source_path,
                    work_path=work_path,
                )
            case ModuleRuleType.CREDITS_RULE | ModuleRuleType.COURSE_UNIT_COUNT_RULE:
                return self._compile_bounded_rule(
                    rule,
                    module_group_id=module_group_id,
                    context=context,
                    ancestor_course_group_ids=ancestor_course_group_ids,
                    ancestor_module_group_ids=ancestor_module_group_ids,
                    source_path=source_path,
                    work_path=work_path,
                )
            case ModuleRuleType.COURSE_UNIT_RULE:
                return self._compile_course_unit_rule(
                    rule,
                    module_group_id=module_group_id,
                    context=context,
                    ancestor_course_group_ids=ancestor_course_group_ids,
                    ancestor_module_group_ids=ancestor_module_group_ids,
                    source_path=source_path,
                )
            case ModuleRuleType.MODULE_RULE:
                return self._compile_module_reference_rule(
                    rule,
                    module_group_id=module_group_id,
                    context=context,
                    ancestor_course_group_ids=ancestor_course_group_ids,
                    ancestor_module_group_ids=ancestor_module_group_ids,
                    source_path=source_path,
                )
            case ModuleRuleType.ANY_COURSE_UNIT_RULE | ModuleRuleType.ANY_MODULE_RULE:
                return self._compile_unrestricted_rule(
                    rule,
                    module_group_id=module_group_id,
                    context=context,
                    ancestor_course_group_ids=ancestor_course_group_ids,
                    ancestor_module_group_ids=ancestor_module_group_ids,
                    source_path=source_path,
                )
            case _:
                raise ValueError(f"unsupported module rule node type {rule.node_type.value}")

    def _compile_rule_children(
        self,
        rule: CatalogueModuleRule,
        *,
        module_group_id: str,
        context: _CompilationContext,
        ancestor_course_group_ids: tuple[str, ...],
        ancestor_module_group_ids: tuple[str, ...],
        source_path: tuple[str | int, ...],
        work_path: tuple[str | int, ...],
    ) -> tuple[str, ...]:
        """Compile one rule's child rules, dropping any child that compiled to nothing."""
        return tuple(
            child
            for child in (
                self._compile_module_rule(
                    child_rule,
                    module_group_id=module_group_id,
                    context=context,
                    ancestor_course_group_ids=ancestor_course_group_ids,
                    ancestor_module_group_ids=ancestor_module_group_ids,
                    source_path=(*source_path, child_rule.sibling_position),
                    work_path=(*work_path, child_rule.sibling_position),
                )
                for child_rule in rule.children
            )
            if child is not None
        )

    def _compile_composite_rule(
        self,
        rule: CatalogueModuleRule,
        *,
        module_group_id: str,
        context: _CompilationContext,
        ancestor_course_group_ids: tuple[str, ...],
        ancestor_module_group_ids: tuple[str, ...],
        source_path: tuple[str | int, ...],
        work_path: tuple[str | int, ...],
    ) -> str | None:
        """Compile one CompositeRule into an all-mandatory AND or a bounded cardinality node."""
        offending = _unexpected_rule_field(rule, "require_min", "require_max", "all_mandatory")
        if offending is not None:
            return self._malformed_module_rule(
                context,
                module_group_id,
                rule,
                f"CompositeRule carries unexpected {offending}",
                source_path=source_path,
            )
        if not rule.children:
            context.pending_diagnostics.append(
                self._ignored_diagnostic(
                    context,
                    kind=PrerequisiteIgnoredPartKind.UNEXPANDABLE_CONTENT,
                    official_kind=OfficialPrerequisiteKind.MODULE_RULE,
                    detail="blank CompositeRule has no contents",
                    module_group_id=module_group_id,
                )
            )
            return None
        if rule.all_mandatory is True:
            compiled = self._compile_rule_children(
                rule,
                module_group_id=module_group_id,
                context=context,
                ancestor_course_group_ids=ancestor_course_group_ids,
                ancestor_module_group_ids=ancestor_module_group_ids,
                source_path=source_path,
                work_path=work_path,
            )
            if not compiled:
                return None
            if len(compiled) == 1:
                expression = compiled[0]
            else:
                expression = self._structure_use(
                    context,
                    kind="and",
                    children=compiled,
                    origin=PrerequisiteOrigin.OFFICIAL,
                    official_kind=OfficialPrerequisiteKind.MODULE_RULE,
                    source_key=source_path,
                    module_rule=True,
                )
            if rule.require_min is not None or rule.require_max is not None:
                diagnostic = self._ignored_diagnostic(
                    context,
                    kind=PrerequisiteIgnoredPartKind.ALL_MANDATORY_BOUNDS,
                    official_kind=OfficialPrerequisiteKind.MODULE_RULE,
                    detail=(
                        "all-mandatory composite ignored bounds"
                        f" require_min={rule.require_min} require_max={rule.require_max}"
                    ),
                    module_group_id=module_group_id,
                )
                expression = context.builder.reintern(
                    expression,
                    children=context.builder.use(expression).children,
                    diagnostic_ids=(
                        *context.builder.use(expression).diagnostic_ids,
                        diagnostic,
                    ),
                )
            return expression
        if rule.require_min is None:
            return self._malformed_module_rule(
                context,
                module_group_id,
                rule,
                "CompositeRule requires explicit require_min unless all-mandatory",
                source_path=source_path,
            )
        if rule.require_min > len(rule.children):
            return self._malformed_module_rule(
                context,
                module_group_id,
                rule,
                "CompositeRule require_min exceeds child count",
                source_path=source_path,
            )
        if rule.require_max is not None and rule.require_max > len(rule.children):
            return self._malformed_module_rule(
                context,
                module_group_id,
                rule,
                "CompositeRule require_max exceeds child count",
                source_path=source_path,
            )
        if rule.require_max is not None and rule.require_min > rule.require_max:
            return self._malformed_module_rule(
                context,
                module_group_id,
                rule,
                "CompositeRule require_min exceeds require_max",
                source_path=source_path,
            )
        compiled = self._compile_rule_children(
            rule,
            module_group_id=module_group_id,
            context=context,
            ancestor_course_group_ids=ancestor_course_group_ids,
            ancestor_module_group_ids=ancestor_module_group_ids,
            source_path=source_path,
            work_path=work_path,
        )
        return self._structure_use(
            context,
            kind="cardinality",
            children=compiled,
            origin=PrerequisiteOrigin.OFFICIAL,
            official_kind=OfficialPrerequisiteKind.MODULE_RULE,
            source_key=source_path,
            module_rule=True,
            require_min=rule.require_min,
            require_max=rule.require_max,
        )

    def _compile_bounded_rule(
        self,
        rule: CatalogueModuleRule,
        *,
        module_group_id: str,
        context: _CompilationContext,
        ancestor_course_group_ids: tuple[str, ...],
        ancestor_module_group_ids: tuple[str, ...],
        source_path: tuple[str | int, ...],
        work_path: tuple[str | int, ...],
    ) -> str | None:
        """Compile one CreditsRule/CourseUnitCountRule into a numeric range or opaque obligation."""
        if rule.node_type is ModuleRuleType.CREDITS_RULE:
            lower_name, upper_name = "credits_min", "credits_max"
        else:
            lower_name, upper_name = "count_min", "count_max"
        offending = _unexpected_rule_field(rule, lower_name, upper_name)
        if offending is not None:
            return self._malformed_module_rule(
                context,
                module_group_id,
                rule,
                f"{rule.node_type.value} carries unexpected {offending}",
                source_path=source_path,
            )
        lower = getattr(rule, lower_name)
        if lower is None:
            return self._malformed_module_rule(
                context,
                module_group_id,
                rule,
                f"{rule.node_type.value} requires {lower_name}",
                source_path=source_path,
            )
        upper = getattr(rule, upper_name)
        if upper is not None and lower > upper:
            return self._malformed_module_rule(
                context,
                module_group_id,
                rule,
                f"{rule.node_type.value} {lower_name} exceeds {upper_name}",
                source_path=source_path,
            )
        if len(rule.children) != 1:
            return self._malformed_module_rule(
                context,
                module_group_id,
                rule,
                f"{rule.node_type.value} requires exactly one child",
                source_path=source_path,
            )
        child_rule = rule.children[0]
        disclosure_offset = len(context.pending_diagnostics)
        child = self._compile_module_rule(
            child_rule,
            module_group_id=module_group_id,
            context=context,
            ancestor_course_group_ids=ancestor_course_group_ids,
            ancestor_module_group_ids=ancestor_module_group_ids,
            source_path=(*source_path, child_rule.sibling_position),
            work_path=(*work_path, child_rule.sibling_position),
        )
        if child is None:
            real_unexpandable = _module_content_unexpandable(child_rule) or any(
                _diagnostic_kind(context.builder, diagnostic_id)
                in (
                    PrerequisiteIgnoredPartKind.FREE_CHOICE.value,
                    PrerequisiteIgnoredPartKind.UNEXPANDABLE_CONTENT.value,
                )
                for diagnostic_id in context.pending_diagnostics[disclosure_offset:]
            )
            if not real_unexpandable:
                return None
            if rule.node_type is ModuleRuleType.CREDITS_RULE:
                return self._structure_use(
                    context,
                    kind="opaque_credits",
                    children=(),
                    origin=PrerequisiteOrigin.OFFICIAL,
                    official_kind=OfficialPrerequisiteKind.MODULE_RULE,
                    source_key=source_path,
                    module_rule=True,
                    manual_credits_min=rule.credits_min,
                    work_key=_opaque_work_key(module_group_id, work_path),
                    credits_min=rule.credits_min,
                    credits_max=rule.credits_max,
                )
            if rule.count_min == 0 and rule.count_max is None:
                context.pending_diagnostics.append(
                    self._ignored_diagnostic(
                        context,
                        kind=PrerequisiteIgnoredPartKind.UNEXPANDABLE_CONTENT,
                        official_kind=OfficialPrerequisiteKind.MODULE_RULE,
                        detail=f"{rule.node_type.value} count_min=0 over unexpandable content",
                        module_group_id=module_group_id,
                    )
                )
                return None
            return self._unresolved_use(
                context,
                reason=UnresolvedPrerequisiteReason.UNKNOWN_COURSE_COUNT,
                referenced_group_id=module_group_id,
                detail=(
                    f"{rule.node_type.value} count_min={rule.count_min} "
                    f"count_max={rule.count_max} over unknown content"
                ),
                official_kind=OfficialPrerequisiteKind.MODULE_RULE,
                source_key=source_path,
            )
        if rule.node_type is ModuleRuleType.CREDITS_RULE:
            return self._structure_use(
                context,
                kind="credits",
                children=(child,),
                origin=PrerequisiteOrigin.OFFICIAL,
                official_kind=OfficialPrerequisiteKind.MODULE_RULE,
                source_key=source_path,
                module_rule=True,
                credits_min=rule.credits_min,
                credits_max=rule.credits_max,
            )
        return self._structure_use(
            context,
            kind="course_count",
            children=(child,),
            origin=PrerequisiteOrigin.OFFICIAL,
            official_kind=OfficialPrerequisiteKind.MODULE_RULE,
            source_key=source_path,
            module_rule=True,
            count_min=rule.count_min,
            count_max=rule.count_max,
        )

    def _compile_course_unit_rule(
        self,
        rule: CatalogueModuleRule,
        *,
        module_group_id: str,
        context: _CompilationContext,
        ancestor_course_group_ids: tuple[str, ...],
        ancestor_module_group_ids: tuple[str, ...],
        source_path: tuple[str | int, ...],
    ) -> str | None:
        """Compile one CourseUnitRule into a course leaf, dropping the immediate self course."""
        offending = _unexpected_rule_field(rule, "referenced_group_id")
        if offending is not None:
            return self._malformed_module_rule(
                context,
                module_group_id,
                rule,
                f"CourseUnitRule carries unexpected {offending}",
                source_path=source_path,
            )
        if rule.children:
            return self._malformed_module_rule(
                context,
                module_group_id,
                rule,
                "CourseUnitRule forbids child rules",
                source_path=source_path,
            )
        course_group_id = rule.referenced_group_id
        if course_group_id is None or not course_group_id.strip():
            return self._malformed_module_rule(
                context,
                module_group_id,
                rule,
                "CourseUnitRule requires a nonblank referenced course ID",
                source_path=source_path,
            )
        if course_group_id == ancestor_course_group_ids[-1]:
            return None
        relative = self._course(course_group_id, context=context)
        if relative is None or relative.representative is None:
            return self._unresolved_use(
                context,
                reason=UnresolvedPrerequisiteReason.MISSING_COURSE,
                referenced_group_id=course_group_id,
                detail=None,
                official_kind=OfficialPrerequisiteKind.MODULE_RULE,
                source_key=source_path,
            )
        return self._expand_course_requirement(
            group_id=course_group_id,
            origin=PrerequisiteOrigin.OFFICIAL,
            official_kind=OfficialPrerequisiteKind.MODULE_RULE,
            inferred_category=None,
            inference=None,
            context=context,
            ancestor_course_group_ids=ancestor_course_group_ids,
            ancestor_module_group_ids=ancestor_module_group_ids,
            source_path=source_path,
        )

    def _compile_module_reference_rule(
        self,
        rule: CatalogueModuleRule,
        *,
        module_group_id: str,
        context: _CompilationContext,
        ancestor_course_group_ids: tuple[str, ...],
        ancestor_module_group_ids: tuple[str, ...],
        source_path: tuple[str | int, ...],
    ) -> str | None:
        """Compile one ModuleRule reference by inlining its resolved module version."""
        offending = _unexpected_rule_field(rule, "referenced_group_id")
        if offending is not None:
            return self._malformed_module_rule(
                context,
                module_group_id,
                rule,
                f"ModuleRule carries unexpected {offending}",
                source_path=source_path,
            )
        if rule.children:
            return self._malformed_module_rule(
                context,
                module_group_id,
                rule,
                "ModuleRule forbids child rules",
                source_path=source_path,
            )
        module_reference = rule.referenced_group_id
        if module_reference is None or not module_reference.strip():
            return self._malformed_module_rule(
                context,
                module_group_id,
                rule,
                "ModuleRule requires a nonblank referenced module ID",
                source_path=source_path,
            )
        return self._expand_module_requirement(
            module_group_id=module_reference,
            official_kind=OfficialPrerequisiteKind.MODULE_RULE,
            context=context,
            ancestor_course_group_ids=ancestor_course_group_ids,
            ancestor_module_group_ids=ancestor_module_group_ids,
            source_path=source_path,
        )

    def _compile_unrestricted_rule(
        self,
        rule: CatalogueModuleRule,
        *,
        module_group_id: str,
        context: _CompilationContext,
        ancestor_course_group_ids: tuple[str, ...],
        ancestor_module_group_ids: tuple[str, ...],
        source_path: tuple[str | int, ...],
    ) -> str | None:
        """Ignore one well-shaped ANY_COURSE_UNIT/ANY_MODULE rule in calculation."""
        offending = _unexpected_rule_field(rule)
        if offending is not None:
            return self._malformed_module_rule(
                context,
                module_group_id,
                rule,
                f"{rule.node_type.value} carries unexpected {offending}",
                source_path=source_path,
            )
        if rule.children:
            return self._malformed_module_rule(
                context,
                module_group_id,
                rule,
                f"{rule.node_type.value} forbids child rules",
                source_path=source_path,
            )
        context.pending_diagnostics.append(
            self._ignored_diagnostic(
                context,
                kind=PrerequisiteIgnoredPartKind.FREE_CHOICE,
                official_kind=OfficialPrerequisiteKind.MODULE_RULE,
                detail=f"{rule.node_type.value} ignored in calculation",
                module_group_id=module_group_id,
            )
        )
        return None

    def _malformed_module_rule(
        self,
        context: _CompilationContext,
        module_group_id: str,
        rule: CatalogueModuleRule,
        detail: str,
        *,
        source_path: tuple[str | int, ...],
    ) -> str:
        """Build one explicit malformed module-rule use naming its owning module."""
        return self._unresolved_use(
            context,
            reason=UnresolvedPrerequisiteReason.MALFORMED_RULE,
            referenced_group_id=module_group_id,
            detail=f"{rule.node_type.value}: {detail}",
            official_kind=OfficialPrerequisiteKind.MODULE_RULE,
            source_key=source_path,
        )

    def _expand_course_requirement(
        self,
        *,
        group_id: str,
        origin: PrerequisiteOrigin,
        official_kind: OfficialPrerequisiteKind | None,
        inferred_category: InferredPrerequisiteCategory | None,
        inference: InferenceNodeMetadata | None,
        context: _CompilationContext,
        ancestor_course_group_ids: tuple[str, ...],
        ancestor_module_group_ids: tuple[str, ...],
        source_path: tuple[str | int, ...],
        allow_substitutions: bool = True,
        allow_equivalences: bool = True,
    ) -> str | None:
        """Recursively expand one course occurrence with children, alternatives, and cycles.

        An occurrence that is offered equivalences and is equivalent to a course above it on the
        path is ignored like a self occurrence when inferred prerequisites are enabled.
        """
        offset = len(context.pending_diagnostics)
        course = self._course(group_id, context=context)
        if course is None:
            raise ValueError(f"expanded course {group_id} is not canonical")
        if not course.is_active:
            if context.active_only and group_id not in context.retained_group_ids:
                return None
            return self._course_use(
                context,
                group_id=group_id,
                origin=origin,
                official_kind=official_kind,
                inferred_category=inferred_category,
                inference=inference,
                source_key=source_path,
                diagnostics=self._take_pending(context, offset),
            )
        if group_id in ancestor_course_group_ids:
            fact_id = context.builder.intern_fact(
                origin=origin,
                official_kind=official_kind,
                inferred_category=inferred_category,
                inference=inference,
            )
            diagnostic = context.builder.intern_diagnostic(
                kind="course_cycle",
                fact_id=fact_id,
                referenced_group_ids=(group_id,),
            )
            return self._course_use(
                context,
                group_id=group_id,
                origin=origin,
                official_kind=official_kind,
                inferred_category=inferred_category,
                inference=inference,
                source_key=source_path,
                diagnostics=(*self._take_pending(context, offset), diagnostic),
                cycle_closing=True,
            )
        # An equivalent of an ancestor is the self occurrence form when equivalence is enabled.
        if (
            context.include_inferred
            and allow_equivalences
            and self._has_ancestor_equivalent(
                group_id,
                context=context,
                ancestor_course_group_ids=ancestor_course_group_ids,
            )
        ):
            return None
        if course.representative is None:
            raise ValueError(f"represented course {course.group_id} has no selected representative")
        local_key = (
            course.group_id,
            course.representative.sisu_course_unit_id,
            "body",
        )
        descendants = ancestor_course_group_ids + (group_id,)
        child_requirements = (
            None
            if context.direct_only
            else self._compile_course_requirements(
                course,
                context=context,
                ancestor_course_group_ids=descendants,
                ancestor_module_group_ids=ancestor_module_group_ids,
            )
        )
        substitution_branches: tuple[str, ...] = ()
        if allow_substitutions and course.representative.substitution_options:
            substitution_branches = self._compile_substitution_branches(
                course,
                context=context,
                ancestor_course_group_ids=descendants,
                ancestor_module_group_ids=ancestor_module_group_ids,
                source_path=(*source_path, "substitutions"),
            )
        equivalence_branches: tuple[str, ...] = ()
        if context.include_inferred and allow_equivalences:
            equivalence_branches = self._compile_equivalence_branches(
                group_id,
                official_kind=official_kind,
                inferred_category=inferred_category,
                context=context,
                ancestor_course_group_ids=descendants,
                ancestor_module_group_ids=ancestor_module_group_ids,
                source_path=(*source_path, "equivalences"),
            )
        head = self._course_use(
            context,
            group_id=group_id,
            origin=origin,
            official_kind=official_kind,
            inferred_category=inferred_category,
            inference=inference,
            source_key=local_key,
            diagnostics=self._take_pending(context, offset),
        )
        if child_requirements is None:
            branch = head
        else:
            branch = self._structure_use(
                context,
                kind="expanded_course",
                children=(head, child_requirements),
                origin=PrerequisiteOrigin.COMPOSED,
                source_key=local_key,
            )
        branches = (branch, *substitution_branches, *equivalence_branches)
        if len(branches) == 1:
            return branch
        return self._structure_use(
            context,
            kind="course_alternatives",
            children=branches,
            origin=PrerequisiteOrigin.COMPOSED,
            source_key=local_key,
        )

    def _read_equivalence_groups(
        self, member_group_id: str, *, context: _CompilationContext
    ) -> tuple[CurrentEquivalenceGroup, ...]:
        """Return one canonical member's exact current groups, reading the protocol at most once."""
        cached = context.equivalence_read_cache.get(member_group_id)
        if cached is not None:
            return cached
        groups = context.equivalence_groups.read_for_member(member_group_id)
        context.equivalence_read_cache[member_group_id] = groups
        return groups

    def _has_ancestor_equivalent(
        self,
        group_id: str,
        *,
        context: _CompilationContext,
        ancestor_course_group_ids: tuple[str, ...],
    ) -> bool:
        """Return whether an offered equivalent of this occurrence already sits above it.

        An equivalent of the occurrence already lies on the same path, so the occurrence adds no
        requirement to it.
        """
        return any(
            candidate_id in ancestor_course_group_ids
            for _, candidate_id in self._equivalence_candidates(group_id, context=context)
        )

    def _equivalence_candidates(
        self, group_id: str, *, context: _CompilationContext
    ) -> tuple[tuple[CurrentEquivalenceGroup, str], ...]:
        """Return one represented member's exact equivalent candidates in stored group/member order."""
        return tuple(
            (group, member.course_group_id)
            for group in self._read_equivalence_groups(group_id, context=context)
            for member in group.members
            if member.course_group_id != group_id
        )

    def _compile_equivalence_branches(
        self,
        group_id: str,
        *,
        official_kind: OfficialPrerequisiteKind | None,
        inferred_category: InferredPrerequisiteCategory | None,
        context: _CompilationContext,
        ancestor_course_group_ids: tuple[str, ...],
        ancestor_module_group_ids: tuple[str, ...],
        source_path: tuple[str | int, ...],
    ) -> tuple[str, ...]:
        """Compile one represented course occurrence's exact inferred equivalent-member branches."""
        derived_category = (
            InferredPrerequisiteCategory.RECOMMENDED
            if official_kind is OfficialPrerequisiteKind.RECOMMENDED
            or inferred_category is InferredPrerequisiteCategory.RECOMMENDED
            else InferredPrerequisiteCategory.REQUIRED
        )
        branches: list[str] = []
        for group, candidate_id in self._equivalence_candidates(group_id, context=context):
            expanded = self._expand_course_requirement(
                group_id=candidate_id,
                origin=PrerequisiteOrigin.INFERRED,
                official_kind=None,
                inferred_category=derived_category,
                inference=group.inference,
                context=context,
                ancestor_course_group_ids=ancestor_course_group_ids,
                ancestor_module_group_ids=ancestor_module_group_ids,
                source_path=(
                    *source_path,
                    str(group.group_id),
                    candidate_id,
                ),
                allow_substitutions=False,
                allow_equivalences=False,
            )
            if expanded is not None:
                branches.append(expanded)
        return tuple(branches)

    def _compile_substitution_branches(
        self,
        course: CatalogueCourse,
        *,
        context: _CompilationContext,
        ancestor_course_group_ids: tuple[str, ...],
        ancestor_module_group_ids: tuple[str, ...],
        source_path: tuple[str | int, ...],
    ) -> tuple[str, ...]:
        """Compile one course's surviving directional substitution option branches in source order."""
        representative = course.representative
        if representative is None:
            raise ValueError(f"course {course.group_id} has no selected representative")
        options = representative.substitution_options
        option_indices = tuple(option.option_index for option in options)
        if len(set(option_indices)) != len(option_indices):
            raise ValueError(f"course {course.group_id} has duplicate substitution option indices")
        branches: list[str] = []
        for option in sorted(options, key=lambda candidate: candidate.option_index):
            member_indices = tuple(member.member_index for member in option.members)
            if len(set(member_indices)) != len(member_indices):
                raise ValueError(
                    f"course {course.group_id} has duplicate substitution member indices"
                )
            members = sorted(option.members, key=lambda candidate: candidate.member_index)
            if not members:
                context.pending_diagnostics.append(
                    self._ignored_diagnostic(
                        context,
                        kind=PrerequisiteIgnoredPartKind.EMPTY_OPTION,
                        official_kind=OfficialPrerequisiteKind.SUBSTITUTION,
                        detail=f"substitution option {option.option_index} is empty",
                    )
                )
                continue
            self._load_courses((member.course_group_id for member in members), context=context)
            missing = tuple(
                member.course_group_id
                for member in members
                if self._course(member.course_group_id, context=context) is None
            )
            if missing:
                context.pending_diagnostics.append(
                    self._ignored_diagnostic(
                        context,
                        kind=PrerequisiteIgnoredPartKind.MISSING_SUBSTITUTION_COURSE,
                        official_kind=OfficialPrerequisiteKind.SUBSTITUTION,
                        referenced_group_ids=tuple(member.course_group_id for member in members),
                        detail=(
                            f"substitution option {option.option_index} dropped: missing "
                            + ", ".join(missing)
                        ),
                    )
                )
                continue
            option_source_path = (*source_path, option.option_index)
            compiled = tuple(
                child
                for child in (
                    self._compile_substitution_member(
                        member,
                        context=context,
                        ancestor_course_group_ids=ancestor_course_group_ids,
                        ancestor_module_group_ids=ancestor_module_group_ids,
                        source_path=(*option_source_path, member.member_index),
                    )
                    for member in members
                )
                if child is not None
            )
            if not compiled:
                continue
            if len(compiled) == 1:
                branches.append(compiled[0])
            else:
                branches.append(
                    self._structure_use(
                        context,
                        kind="and",
                        children=compiled,
                        origin=PrerequisiteOrigin.OFFICIAL,
                        official_kind=OfficialPrerequisiteKind.SUBSTITUTION,
                        source_key=option_source_path,
                    )
                )
        return tuple(branches)

    def _compile_substitution_member(
        self,
        member: CatalogueSubstitutionMember,
        *,
        context: _CompilationContext,
        ancestor_course_group_ids: tuple[str, ...],
        ancestor_module_group_ids: tuple[str, ...],
        source_path: tuple[str | int, ...],
    ) -> str | None:
        """Compile one substitution member course without chaining that member's own options."""
        if member.course_group_id == ancestor_course_group_ids[-1]:
            return None
        course = self._course(member.course_group_id, context=context)
        if course is None or course.representative is None:
            return self._unresolved_use(
                context,
                reason=UnresolvedPrerequisiteReason.MISSING_COURSE,
                referenced_group_id=member.course_group_id,
                detail=None,
                official_kind=OfficialPrerequisiteKind.SUBSTITUTION,
                source_key=source_path,
            )
        return self._expand_course_requirement(
            group_id=member.course_group_id,
            origin=PrerequisiteOrigin.OFFICIAL,
            official_kind=OfficialPrerequisiteKind.SUBSTITUTION,
            inferred_category=None,
            inference=None,
            context=context,
            ancestor_course_group_ids=ancestor_course_group_ids,
            ancestor_module_group_ids=ancestor_module_group_ids,
            source_path=source_path,
            allow_substitutions=False,
        )

    def _read_inferred_expression(
        self, course: CatalogueCourse, *, context: _CompilationContext
    ) -> PrerequisiteExpression | None:
        """Read one active course's inferred expression once, or contribute nothing when absent."""
        cached = context.inferred_read_cache.get(course.group_id)
        if cached is None:
            cached = context.inferred_sets.read(course.group_id)
            context.inferred_read_cache[course.group_id] = cached
        if cached.state in (
            InferredReadState.UNAVAILABLE,
            InferredReadState.STALE_ACTIVITY_CONTEXT,
        ):
            return None
        current = cached.current_set
        if current is None:
            raise ValueError("current inferred read must expose a current set")
        context.coverage_by_group_id[course.group_id] = InferredCoverageRecord(
            target_group_id=course.group_id,
            coverage_state=current.coverage_state,
            coverage=current.coverage,
        )
        return current.expression

    def _expand_inferred_expression(
        self,
        expression: PrerequisiteExpression,
        *,
        context: _CompilationContext,
        ancestor_course_group_ids: tuple[str, ...],
        ancestor_module_group_ids: tuple[str, ...],
        source_path: tuple[str | int, ...],
    ) -> str | None:
        """Copy one stored inferred AND/OR/course structure, expanding its course leaves."""
        if (
            expression.origin is PrerequisiteOrigin.INFERRED
            and expression.inferred_category is InferredPrerequisiteCategory.RECOMMENDED
            and not context.include_recommended
        ):
            return None
        if isinstance(expression, CourseRequirement):
            if expression.course_group_id == ancestor_course_group_ids[-1]:
                return None
            return self._expand_course_requirement(
                group_id=expression.course_group_id,
                origin=expression.origin,
                official_kind=expression.official_kind,
                inferred_category=expression.inferred_category,
                inference=expression.inference,
                context=context,
                ancestor_course_group_ids=ancestor_course_group_ids,
                ancestor_module_group_ids=ancestor_module_group_ids,
                source_path=source_path,
            )
        if isinstance(expression, (AndRequirement, OrRequirement)):
            expanded_children = tuple(
                child
                for child in (
                    self._expand_inferred_expression(
                        child,
                        context=context,
                        ancestor_course_group_ids=ancestor_course_group_ids,
                        ancestor_module_group_ids=ancestor_module_group_ids,
                        source_path=(*source_path, index),
                    )
                    for index, child in enumerate(expression.children)
                )
                if child is not None
            )
            if not expanded_children:
                return None
            if len(expanded_children) == 1:
                return expanded_children[0]
            kind = "and" if isinstance(expression, AndRequirement) else "or"
            return self._structure_use(
                context,
                kind=kind,
                children=expanded_children,
                origin=expression.origin,
                official_kind=expression.official_kind,
                inferred_category=expression.inferred_category,
                inference=expression.inference,
                source_key=source_path,
            )
        raise ValueError(
            f"inferred sets support only course/and/or nodes, not {type(expression).__name__}"
        )
