"""Authoritative prerequisite calculation tree and its minimized drawing-graph projection.

This module owns two product-neutral artifacts built by read-only services over the official
curriculum seam, the current inferred-set seam, and the global equivalence-group seam:
one root-specific recursive calculation tree
(`PrerequisiteExpression`) that holds the opened root's required and recommended
obligations, expanding a canonical course in every mandatory position, and one
deterministic drawing graph derived only from that tree.

The tree is the sole calculation authority. The mandatory-position rule is stated in
`docs/architecture/seams/prerequisites.md`. Every tree occurrence carries one producer-bound stable
action identity: course/module/opaque nodes use their canonical source identity and every structural
node uses a `requirement:` key derived once at creation from its complete reaching source lineage,
explicit role and ordered child source identities, never from filtered drawing positions or
expression bounds. The drawing graph deduplicates canonical course nodes by `group_id` and groups
equal-endpoint, equal-provenance-class relationships into one visible connection whose ordered
members keep every distinct provenance, terminal occurrence and condition chain, but keeps scoped
AND/OR/numeric/unresolved connectors and provenance intact. It
never merges similar connector subtrees or performs transitive reduction, and an ordinary expanded
course draws its head course connected to its own descendant condition tree rather than as an AND
sibling. Only backend-owned drawing normalization removes a node: a logical AND/OR occurrence that
loses every visible child, or that keeps exactly one, is elided and its same-operator nesting folded
into the surviving parent, while numeric/module/excluded-marked source nodes and genuine choices
stay. Every remaining drawing node is reachable from the explicitly opened root. Known official
module prerequisites are resolved against the root's
persisted academic-year context and inlined into course/logical/numeric/unresolved expressions.
The inlined calculation is authoritative, while each selected module boundary is recorded as
request-local display metadata so the drawing graph presents that module or degree as one node with
its official member course cards instead of drawing the module's inlined subtree.

With inference enabled, every accepted global equivalence group containing a prerequisite course
is consumed at that member's occurrence: the other exact members of each group become
provenance-distinct inferred alternatives beside the original branch and any official directional
substitution options, all inside one flat `COURSE_ALTERNATIVES` composed OR. Each offered member
expands its own ordinary prerequisites and real credits but never chains its own substitutions or
groups, so membership is non-transitive and overlapping groups are distinct. The selected root
itself and any other represented ancestor are never offered as alternatives, and a direct self
occurrence is dropped before traversal while genuine indirect cycles keep their
blocker. Reading a group is gated by `include_inferred`, so disabling inference performs no
equivalence read.

Official and inferred contributions of one category are pooled, never conjoined: each enabled
required/recommended category compiles to one flat OR of complete official and inferred AND
options, and the two category pools join only through one composed logical AND. Every drawing
course node also carries the drawing-only `display_as_inferred` marker projected from its final
visible occurrence provenance: an inferred-only node displays inferred, while any visible official
occurrence on a shared node wins and keeps the node official.

Compilation owns both visibility inputs. `include_recommended` and `include_inferred` are
independent per-call product inputs defaulting to false. Each disabled category's whole branch
is pruned before descendant traversal, so the tree contains only enabled categories and the
drawing graph is derived only from that filtered tree. Inferred occurrences carry their own
`InferredPrerequisiteCategory`: an inferred required occurrence needs only `include_inferred`,
while an inferred recommended occurrence needs both toggles and is pruned before its descendants
are compiled, read, or counted. `active_only` is the shared activity scope. Under
`Active courses only` the compiler drops a non-root inactive course occurrence from the compiled
expression unless its canonical ID is in `retained_group_ids`, so the drawing graph and the route
read one requirement set. That drop can leave the opened root with no requirements.
An explicitly opened root compiles its own enabled official structure in every scope.
Neither scope reads an inferred set for an inactive root.
`retained_group_ids` is the raw caller input of canonical IDs that the compiler retains in the
compiled expression, distinct from course completion.
`excluded_group_ids` is a caller-owned request set of represented canonical course IDs minus
the opened root. It never prunes a drawing course node or its
descendants, but it is copied onto the tree so the one shared eligibility predicate can deny those
courses to satisfaction and pathing. Every canonical drawing course node also aggregates independent
`via_inferred`/`via_recommended` path annotations over its visible root-to-occurrence routes and
records whether any reaching occurrence is official or inferred. Those annotations explain
visibility and provenance and never replace the exact expression, connector, or relationship-member provenance.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Collection, Iterator, Sequence
from dataclasses import dataclass, field, replace
from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import Field, field_validator, model_validator

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
    InferredCoverageState,
    ModuleRuleType,
    PrerequisiteMemberType,
    PrerequisiteRequirementKind,
)
from course_explorer.prerequisite._helpers import (
    _nonblank,
    _PrerequisiteModel,
    _validate_origin_shape,
)
from course_explorer.prerequisite.domain import (
    AndRequirement,
    CardinalityRequirement,
    ComposedAndRole,
    ComposedOrRole,
    CourseCountRequirement,
    CourseRequirement,
    CreditRequirement,
    CurrentEquivalenceGroup,
    EquivalenceGroupRead,
    InferenceNodeMetadata,
    InferredPrerequisiteCategory,
    InferredReadState,
    InferredSetCoverage,
    InferredSetRead,
    InferredSetReadResult,
    ModuleBlockRequirement,
    ModuleRequirement,
    OfficialPrerequisiteKind,
    OpaqueCreditRequirement,
    OrRequirement,
    PrerequisiteExpression,
    PrerequisiteGraphNodeState,
    PrerequisiteNodeOccurrence,
    PrerequisiteOrigin,
    UnresolvedPrerequisiteReason,
    UnresolvedRequirement,
    expression_course_leaf_group_ids,
)

_REQUIREMENT_KIND_TO_OFFICIAL: dict[PrerequisiteRequirementKind, OfficialPrerequisiteKind] = {
    PrerequisiteRequirementKind.COMPULSORY: OfficialPrerequisiteKind.COMPULSORY,
    PrerequisiteRequirementKind.RECOMMENDED: OfficialPrerequisiteKind.RECOMMENDED,
}


def _inference_key(metadata: InferenceNodeMetadata | None) -> str:
    """Return one canonical JSON key for optional inferred evidence metadata."""
    if metadata is None:
        return ""
    dumped = metadata.model_dump(mode="json")
    return json.dumps(dumped, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _provenance_key(
    origin: PrerequisiteOrigin,
    official_kind: OfficialPrerequisiteKind | None,
    inferred_category: InferredPrerequisiteCategory | None,
    inference: InferenceNodeMetadata | None,
) -> tuple[str, str, str, str]:
    """Return one comparable provenance key shared by nodes and relationship members.

    The inferred required/recommended category is part of the key, so an otherwise identical
    required and recommended inferred relationship never merges into one drawing member.
    """
    return (
        origin.value,
        "" if official_kind is None else official_kind.value,
        "" if inferred_category is None else inferred_category.value,
        _inference_key(inference),
    )


def _edge_semantic_key(
    source_node_id: str,
    target_node_id: str,
    origin: PrerequisiteOrigin,
    official_kind: OfficialPrerequisiteKind | None,
    inferred_category: InferredPrerequisiteCategory | None,
    inference: InferenceNodeMetadata | None,
) -> tuple[str, str, str, str, str, str]:
    """Return the complete key of one precise relationship member inside one visible connection.

    The first five entries are that connection's own key. The final inference key plus the ordered
    condition chain separate equally-classed members, so no evidence or gate chain is ever unioned.
    """
    return (
        source_node_id,
        target_node_id,
        *_provenance_key(origin, official_kind, inferred_category, inference),
    )


def _edge_sort_key(edge: PrerequisiteGraphEdge) -> tuple[str, str, str, str, str]:
    """Return the endpoint/class ordering key shared by derived and ignored drawing connections.

    Only the connection's own endpoints and its first member's provenance class order it. Member
    evidence never participates, so a connection keeps one deterministic place in the drawing.
    """
    first = edge.relationships[0]
    return (
        edge.source_node_id,
        edge.target_node_id,
        first.origin.value,
        "" if first.official_kind is None else first.official_kind.value,
        "" if first.inferred_category is None else first.inferred_category.value,
    )


class InferredCoverageRecord(_PrerequisiteModel):
    """One current inferred set's coverage seen during active-course traversal."""

    target_group_id: str
    coverage_state: InferredCoverageState
    coverage: InferredSetCoverage

    @field_validator("target_group_id")
    @classmethod
    def reject_blank_target(cls, value: str) -> str:
        """Require a nonblank canonical target identity."""
        return _nonblank(value, "target_group_id")


class PrerequisiteCompilationIssue(_PrerequisiteModel):
    """One explicit non-fatal compilation problem with its located occurrence identity."""

    reason: UnresolvedPrerequisiteReason
    course_group_path: tuple[str, ...]
    occurrence_id: str
    action_key: str
    origin: PrerequisiteOrigin
    official_kind: OfficialPrerequisiteKind | None = None

    @field_validator("course_group_path")
    @classmethod
    def require_group_path(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Require a nonempty path of nonblank canonical group IDs."""
        if not value:
            raise ValueError("course_group_path requires at least one group ID")
        for group_id in value:
            _nonblank(group_id, "course_group_path entry")
        return value

    @field_validator("occurrence_id", "action_key")
    @classmethod
    def reject_blank_location(cls, value: str) -> str:
        """Require a nonblank located occurrence and action identity."""
        return _nonblank(value, "compilation issue location")

    @model_validator(mode="after")
    def validate_provenance(self) -> PrerequisiteCompilationIssue:
        """Allow official leaf provenance and inferred leaf provenance only."""
        if self.origin is PrerequisiteOrigin.COMPOSED:
            raise ValueError("composed origin is invalid for a compilation issue")
        if self.origin is PrerequisiteOrigin.OFFICIAL:
            if self.official_kind is None:
                raise ValueError("official compilation issues require official_kind")
        elif self.official_kind is not None:
            raise ValueError("inferred compilation issues forbid official_kind")
        return self


class PrerequisiteModuleOccurrence(_PrerequisiteModel):
    """One selected module reference's request-local display boundary on a calculation tree.

    `occurrence_id` is the positional ID of the surviving expression the selected module's inlined
    rule occupies. The module's identity is descriptive reference metadata carried beside that
    expression, never a replacement for any expression/relationship-member provenance. `member_group_ids` are the
    represented explicit official course members of the inlined rule, including nested modules,
    canonical sorted unique. A member's ordinary prerequisites, substitutes, and inferred
    equivalents are excluded, and missing members stay only in the expression's
    diagnostics.
    """

    occurrence_id: str
    module: ModuleSummary
    official_kind: OfficialPrerequisiteKind
    member_group_ids: tuple[str, ...]
    credits_min: Decimal | None = Field(default=None, ge=0)
    credits_max: Decimal | None = Field(default=None, ge=0)


class PrerequisiteIgnoredPartKind(StrEnum):
    """Application handling of one official source part the calculation simplified or dropped.

    These describe compiler decisions about official source structure.
    """

    EMPTY_OPTION = "empty_option"
    MISSING_SUBSTITUTION_COURSE = "missing_substitution_course"
    MISSING_MODULE_ALTERNATIVE = "missing_module_alternative"
    MODULE_VERSION_FALLBACK = "module_version_fallback"
    FREE_CHOICE = "free_choice"
    UNEXPANDABLE_CONTENT = "unexpandable_content"
    ALL_MANDATORY_BOUNDS = "all_mandatory_bounds"


class PrerequisiteIgnoredPart(_PrerequisiteModel):
    """One request-local disclosure of an official source part the calculation ignored.

    `anchor_occurrence_id` is the final expression occurrence the record is bound to, or `None` for
    a root-level record. The full ancestor course/module group paths plus the referenced IDs and a
    short factual `detail` locate the ignored part without re-storing a raw rule tree or course text.
    The producer owns shape and ordering. There is no independent output validator.
    """

    part_id: str
    kind: PrerequisiteIgnoredPartKind
    anchor_occurrence_id: str | None
    action_key: str
    course_group_path: tuple[str, ...]
    module_group_path: tuple[str, ...]
    official_kind: OfficialPrerequisiteKind
    referenced_group_ids: tuple[str, ...] = ()
    detail: str | None = None
    module: ModuleSummary | None = None


class PrerequisiteCalculationTree(_PrerequisiteModel):
    """One root-specific authoritative expression tree with shared course summaries."""

    root: CourseSummary
    academic_year_start: int = Field(gt=0)
    requirements: PrerequisiteExpression | None
    courses: tuple[CourseSummary, ...]
    include_recommended: bool
    include_inferred: bool
    active_only: bool
    inferred_coverage: tuple[InferredCoverageRecord, ...]
    issues: tuple[PrerequisiteCompilationIssue, ...]
    excluded_group_ids: tuple[str, ...] = ()
    module_occurrences: tuple[PrerequisiteModuleOccurrence, ...] = ()
    ignored_parts: tuple[PrerequisiteIgnoredPart, ...] = ()
    node_occurrences: tuple[PrerequisiteNodeOccurrence, ...] = ()
    completed_node_keys: tuple[str, ...] = ()
    excluded_node_keys: tuple[str, ...] = ()


class PrerequisiteGraphConnectorKind(StrEnum):
    """Drawing-graph connector categories projected from expression node kinds."""

    AND = "and"
    OR = "or"
    CARDINALITY = "cardinality"
    CREDITS = "credits"
    COURSE_COUNT = "course_count"
    OPAQUE_CREDITS = "opaque_credits"
    INTERNAL_REQUIREMENT = "internal_requirement"
    UNRESOLVED = "unresolved"


class PrerequisiteGraphCourseNode(_PrerequisiteModel):
    """One canonical drawing-graph course node with shared summary, path flags, and provenance.

    `via_inferred`/`via_recommended` are independent visibility annotations OR-aggregated over
    every visible root-to-occurrence route that reaches the node's canonical course. Both may be
    true on a shared node. `has_official_provenance`/`has_inferred_provenance` record whether any
    expression occurrence reaching this canonical node is official or inferred. Both may be true on
    a shared mixed node. They are drawing annotations about occurrence provenance, distinct from the
    path-category `via_inferred`/`via_recommended` flags, and they never relabel connector or
    relationship-member
    `origin`/`official_kind`/`inference`. `display_as_inferred` is the one drawing-only course-card
    marker, derived once from those final aggregated provenance flags after every visible occurrence
    is known: it is true only for a non-root node that has inferred provenance and no official
    provenance, so an official occurrence always wins on a shared mixed node and `via_inferred`
    is an independent path annotation. `is_excluded` marks a canonical course named by the
    request's exclusion set. Exclusion is a calculation rule only, so the node and its descendants
    stay drawn and unpruned.
    """

    node_id: str
    action_key: str
    course: CourseSummary
    is_root: bool
    via_inferred: bool
    via_recommended: bool
    has_official_provenance: bool
    has_inferred_provenance: bool
    display_as_inferred: bool = False
    is_excluded: bool = False

    @model_validator(mode="after")
    def validate_node_id(self) -> PrerequisiteGraphCourseNode:
        """Require the canonical `course:<group_id>` node identity."""
        if self.node_id != f"course:{self.course.group_id}":
            raise ValueError("course node_id must be course:<group_id>")
        return self


class PrerequisiteGraphConnectorNode(_PrerequisiteModel):
    """One scoped logical, numeric, or unresolved drawing-graph connector."""

    node_id: str
    action_key: str
    kind: PrerequisiteGraphConnectorKind
    origin: PrerequisiteOrigin
    official_kind: OfficialPrerequisiteKind | None
    inferred_category: InferredPrerequisiteCategory | None
    inference: InferenceNodeMetadata | None
    require_min: int | None = Field(default=None, ge=0)
    require_max: int | None = Field(default=None, ge=0)
    credits_min: Decimal | None = Field(default=None, ge=0)
    credits_max: Decimal | None = Field(default=None, ge=0)
    count_min: int | None = Field(default=None, ge=0)
    count_max: int | None = Field(default=None, ge=0)
    referenced_group_id: str | None = None
    unresolved_reason: UnresolvedPrerequisiteReason | None = None
    detail: str | None = None
    member_group_ids: tuple[str, ...] = ()

    @field_validator("node_id")
    @classmethod
    def require_connector_prefix(cls, value: str) -> str:
        """Require the canonical `connector:<occurrence_id>` node identity."""
        _nonblank(value, "connector node_id")
        if not value.startswith("connector:") or not value[len("connector:") :].strip():
            raise ValueError("connector node_id must be connector:<occurrence_id>")
        return value

    @field_validator("referenced_group_id", "detail")
    @classmethod
    def reject_blank_optional_text(cls, value: str | None) -> str | None:
        """Reject a provided-but-blank diagnostic text field."""
        if value is not None:
            _nonblank(value, "connector diagnostic text")
        return value


class PrerequisiteGraphEdgeRelationship(_PrerequisiteModel):
    """One precise relationship carried by a visible drawing connection.

    A connection groups only equal endpoints and equal provenance class, so every member keeps its
    own full provenance, terminal occurrence IDs and ordered elided-gate condition chain. Gates and
    evidence are never unioned and members are never merged into one representative.
    """

    origin: PrerequisiteOrigin
    official_kind: OfficialPrerequisiteKind | None
    inferred_category: InferredPrerequisiteCategory | None
    inference: InferenceNodeMetadata | None
    occurrence_ids: tuple[str, ...]
    condition_occurrence_ids: tuple[str, ...] = ()

    @field_validator("occurrence_ids")
    @classmethod
    def require_sorted_unique_occurrences(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Require nonempty sorted unique occurrence IDs."""
        if not value:
            raise ValueError("edges require at least one occurrence ID")
        for occurrence_id in value:
            _nonblank(occurrence_id, "edge occurrence_id")
        if len(set(value)) != len(value):
            raise ValueError("edge occurrence IDs must be unique")
        if value != tuple(sorted(value)):
            raise ValueError("edge occurrence IDs must be sorted")
        return value

    @model_validator(mode="after")
    def validate_provenance(self) -> PrerequisiteGraphEdgeRelationship:
        """Require one valid provenance shape per relationship member."""
        _validate_origin_shape(
            self.origin, self.official_kind, self.inferred_category, self.inference
        )
        return self


class PrerequisiteGraphEdge(_PrerequisiteModel):
    """One directed drawing-graph connection grouping its equal-class relationship members."""

    source_node_id: str
    target_node_id: str
    relationships: tuple[PrerequisiteGraphEdgeRelationship, ...] = Field(min_length=1)

    @field_validator("source_node_id", "target_node_id")
    @classmethod
    def reject_blank_node(cls, value: str) -> str:
        """Require nonblank endpoint identities."""
        return _nonblank(value, "edge endpoint")


class PrerequisiteGraphModuleNode(_PrerequisiteModel):
    """One drawn module/degree node standing for an inlined module occurrence.

    `module` carries the selected exact version's official identity/type/names. No activity flag or
    URL is fabricated for a module. `member_courses` are the occurrence's official member course
    cards under the tree's activity scope, ordered by canonical group ID like `tree.courses`, and
    never its inferred alternatives or a member's own ancestor closure.
    """

    node_id: str
    occurrence_id: str
    action_key: str
    module: ModuleSummary
    official_kind: OfficialPrerequisiteKind
    member_courses: tuple[CourseSummary, ...]
    credits_min: Decimal | None = Field(default=None, ge=0)
    credits_max: Decimal | None = Field(default=None, ge=0)


class PrerequisiteGraphIgnoredNode(_PrerequisiteModel):
    """One explicit drawing annotation standing for a tree disclosure.

    `node_id` equals the tree record's `part_id`, so the drawing node references the one
    authoritative descriptive record rather than duplicating its payload. `action_key` is the
    stable source identity of the disappeared part. It is an application simplification annotation,
    never an official obligation.
    """

    node_id: str
    part_id: str
    action_key: str
    is_ignored: bool = True


class PrerequisiteDrawingGraph(_PrerequisiteModel):
    """One deterministic minimized drawing projection with shared canonical course nodes."""

    course_nodes: tuple[PrerequisiteGraphCourseNode, ...]
    connector_nodes: tuple[PrerequisiteGraphConnectorNode, ...]
    edges: tuple[PrerequisiteGraphEdge, ...]
    module_nodes: tuple[PrerequisiteGraphModuleNode, ...] = ()
    ignored_nodes: tuple[PrerequisiteGraphIgnoredNode, ...] = ()
    node_states: tuple[PrerequisiteGraphNodeState, ...] = ()


class PrerequisiteGraphCompilation(_PrerequisiteModel):
    """One calculation tree paired with the drawing graph derived only from it."""

    tree: PrerequisiteCalculationTree
    graph: PrerequisiteDrawingGraph


@dataclass(frozen=True)
class DirectPrerequisiteCompilation:
    """One candidate's request-local direct category roots for next-course discovery.

    `tree` is the same authoritative per-root calculation tree the ordinary compile builds. The
    `required` and `recommended` fields are the two separate per-category option-pool roots (or
    `None` when that category has no enabled contribution). They are request-local references used
    only by discovery eligibility/coverage. The drawing graph is projected elsewhere.
    """

    tree: PrerequisiteCalculationTree
    required: PrerequisiteExpression | None
    recommended: PrerequisiteExpression | None


@dataclass(frozen=True)
class _CompiledModuleBoundary:
    """One selected module reference bound to its surviving inlined expression object.

    The expression is a reference to the object already in the compiled tree, never a copy or a
    separately serialized expression. The boundary is joined to a final positional occurrence ID
    once compilation finishes.
    """

    expression: PrerequisiteExpression
    module: ModuleSummary
    official_kind: OfficialPrerequisiteKind
    member_group_ids: tuple[str, ...]
    credits_min: Decimal | None = None
    credits_max: Decimal | None = None


@dataclass(frozen=True)
class _CompiledCourseCycle:
    """One transient course-cycle record bound to its closing course expression occurrence.

    The cycle is located once `_build_tree` walks the final expression tree: the record carries the
    closing `CourseRequirement` object identity plus its diagnostic path and provenance, so a cycle
    is emitted as a public issue only at the actual surviving occurrence, never for every occurrence
    of the same canonical course.
    """

    expression: CourseRequirement
    course_group_path: tuple[str, ...]
    origin: PrerequisiteOrigin
    official_kind: OfficialPrerequisiteKind | None


@dataclass
class _CompiledIgnoredPart:
    """One transient ignored-part record bound to its surviving expression object.

    It carries the same descriptive fields as `PrerequisiteIgnoredPart` except the assigned
    `part_id`/`anchor_occurrence_id`, plus an optional `anchor` reference to the expression object
    already in the compiled tree. `action_key` is the stable source identity of the disappeared
    part, and `module` retains the selected module summary when a whole module disappeared. It is
    request-local UI/report fact, never a log, cache or payload.
    """

    kind: PrerequisiteIgnoredPartKind
    action_key: str
    course_group_path: tuple[str, ...]
    module_group_path: tuple[str, ...]
    official_kind: OfficialPrerequisiteKind
    referenced_group_ids: tuple[str, ...] = ()
    detail: str | None = None
    anchor: PrerequisiteExpression | None = None
    module: ModuleSummary | None = None


@dataclass
class _CompiledOfficialOption:
    """One compiled complete official option staged with its own output collectors.

    Whole-option deletion needs each option's expression and output collectors to travel
    together, so `_finish_official_options` can drop a missing-module option without leaving a ghost
    cycle, inferred-coverage row or module boundary. The ancestor paths and original ordered option
    member IDs locate a discarded option without reconstructing source identity.
    """

    option_index: int
    expression: PrerequisiteExpression
    context: _CompilationContext
    course_group_path: tuple[str, ...]
    module_group_path: tuple[str, ...]
    referenced_group_ids: tuple[str, ...]


@dataclass
class DirectPrerequisiteReadContext:
    """Request-local raw-input caches shared across direct-compile policies.

    It carries mutable read dictionaries and successful negative course/module lookups alongside
    inferred sets and equivalence groups, so an inference-enabled and an official-only direct compile over the same request reuse
    the same raw reads. Per-root/per-policy summaries, issues, coverage and module boundaries are
    always fresh and scoped to the caller's one database context.
    """

    courses_by_group_id: dict[str, CatalogueCourse] = field(default_factory=dict)
    modules_by_group_id: dict[str, CatalogueModule] = field(default_factory=dict)
    missing_course_group_ids: set[str] = field(default_factory=set)
    missing_module_group_ids: set[str] = field(default_factory=set)
    inferred_read_cache: dict[str, InferredSetReadResult] = field(default_factory=dict)
    equivalence_read_cache: dict[str, tuple[CurrentEquivalenceGroup, ...]] = field(
        default_factory=dict
    )


@dataclass
class _CompilationContext:
    """Per-`compile` mutable traversal state. Never stored on the compiler instance."""

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
    issues: list[_CompiledCourseCycle]
    module_boundaries: list[_CompiledModuleBoundary]
    ignored_parts: list[_CompiledIgnoredPart]
    root_group_id: str = ""
    action_key_by_expression_id: dict[int, str] = field(default_factory=dict)
    credit_extent_by_expression_id: dict[int, Decimal] = field(default_factory=dict)
    bound_expressions: list[PrerequisiteExpression] = field(default_factory=list)
    direct_only: bool = False
    retained_group_ids: frozenset[str] = frozenset()


def _iter_expression_occurrences(
    expression: PrerequisiteExpression, occurrence_id: str = "r"
) -> Iterator[tuple[str, PrerequisiteExpression]]:
    """Yield preorder occurrences lazily with an iterator stack proportional to depth."""
    yield occurrence_id, expression
    stack = [(occurrence_id, enumerate(_connector_children(expression)))]
    while stack:
        parent_id, children = stack[-1]
        entry = next(children, None)
        if entry is None:
            stack.pop()
            continue
        index, child = entry
        child_id = f"{parent_id}.{index}"
        yield child_id, child
        stack.append((child_id, enumerate(_connector_children(child))))


def _contains_missing_module(expression: PrerequisiteExpression) -> bool:
    """Return whether one compiled option contains a MISSING_MODULE occurrence."""
    return any(
        isinstance(node, UnresolvedRequirement)
        and node.reason is UnresolvedPrerequisiteReason.MISSING_MODULE
        for _, node in _iter_expression_occurrences(expression)
    )


def _iter_module_member_group_ids(expression: PrerequisiteExpression) -> Iterator[str]:
    """Yield one module boundary's explicit official member course IDs.

    A course leaf is a member. An expanded-course branch contributes only its head course, and a
    composed course-alternative OR contributes only its represented first branch, so a member's
    ordinary prerequisites, substitutes, and inferred equivalents stay excluded. Other
    logical/numeric nodes recurse through their connector children. Unresolved contributes nothing.
    """
    if isinstance(expression, CourseRequirement):
        yield expression.course_group_id
        return
    if is_expanded_course_branch(expression):
        yield expression.children[0].course_group_id
        return
    if (
        isinstance(expression, OrRequirement)
        and expression.origin is PrerequisiteOrigin.COMPOSED
        and expression.composed_role is ComposedOrRole.COURSE_ALTERNATIVES
    ):
        yield from _iter_module_member_group_ids(expression.children[0])
        return
    for child in _connector_children(expression):
        yield from _iter_module_member_group_ids(child)


def is_course_activity_eligible(
    tree: PrerequisiteCalculationTree,
    group_id: str,
    exception_group_ids: Collection[str],
    *,
    for_calculation: bool = False,
) -> bool:
    """Return whether one canonical course is eligible under the tree activity scope.

    Under all-course scope every represented course is eligible. Under active-only scope the
    represented courses are the active courses and the retained inactive courses, so an inactive
    course is eligible only when its canonical ID is in `exception_group_ids`: the chosen calculation
    basis for pathing and satisfaction. This is the one shared activity predicate. Every consumer must
    use it instead of re-deriving activity policy. `for_calculation=True` additionally denies any
    canonical ID in `tree.excluded_group_ids` before the activity or exception rules, so exclusion is
    binding for satisfaction and pathing.
    """
    summary = next((course for course in tree.courses if course.group_id == group_id), None)
    if summary is None:
        raise ValueError(f"course {group_id} is missing from the calculation tree courses")
    if for_calculation and group_id in tree.excluded_group_ids:
        return False
    return not tree.active_only or summary.is_active or group_id in exception_group_ids


def _collapse_single_child_wrapper(
    expression: PrerequisiteExpression,
) -> PrerequisiteExpression:
    """Replace a one-child AND/OR wrapper with its child. Any other expression is returned as-is.

    Collapsing exactly one child preserves logical meaning and provenance of the surviving subtree.
    """
    if isinstance(expression, (AndRequirement, OrRequirement)) and len(expression.children) == 1:
        return expression.children[0]
    return expression


def _expression_bound_key(context: _CompilationContext, expression: PrerequisiteExpression) -> str:
    """Return one expression's stable source action identity.

    Canonical course, module-boundary and opaque nodes carry their own source identity directly. Every
    other node carries the producer-bound source-lineage key recorded when it was created.
    """
    if isinstance(expression, CourseRequirement):
        return f"course:{expression.course_group_id}"
    if isinstance(expression, ModuleBlockRequirement):
        return f"module:{expression.module_group_id}"
    if isinstance(expression, OpaqueCreditRequirement):
        return f"opaque:{expression.work_key}"
    bound = context.action_key_by_expression_id.get(id(expression))
    if bound is None:
        raise ValueError("structural expression has no bound source action key")
    return bound


def _source_structural_key(
    source_path: tuple[str | int, ...],
    role: str,
    children: Sequence[PrerequisiteExpression],
    context: _CompilationContext,
) -> str:
    """Return one structural node's stable source-lineage action identity.

    The key is a digest of the complete reaching source lineage plus the node's explicit role and its
    ordered children's own bound source identities, so it never depends on filtered drawing positions,
    expression bounds, or object identity.
    """
    child_keys = [_expression_bound_key(context, child) for child in children]
    payload = json.dumps(
        [list(source_path), role, child_keys], separators=(",", ":"), ensure_ascii=False
    )
    return f"requirement:{_stable_digest(payload)}"


def _bind_expression(
    expression: PrerequisiteExpression,
    *,
    context: _CompilationContext,
    source_path: tuple[str | int, ...],
    role: str,
    children: Sequence[PrerequisiteExpression] = (),
    credits_min: Decimal | None = None,
) -> PrerequisiteExpression:
    """Bind one freshly created structural node's stable source action identity and known extent.

    The expression object is retained for the compile lifetime so an abandoned collapsed or dropped
    object's Python `id` can never later bind a different surviving node.
    """
    context.action_key_by_expression_id[id(expression)] = _source_structural_key(
        source_path, role, children, context
    )
    if credits_min is not None:
        context.credit_extent_by_expression_id[id(expression)] = credits_min
    context.bound_expressions.append(expression)
    return expression


def _stable_digest(payload: str) -> str:
    """Return a fixed-length stable digest of one source-key payload.

    Structural source keys nest their children's keys, so a fixed-length digest keeps the total key
    size linear in the tree instead of embedding whole subtrees. The digest is deterministic across
    processes and never used as a security boundary.
    """
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:40]


def _rule_action_key(module_group_id: str, source_path: tuple[str | int, ...]) -> str:
    """Return the stable source action identity of one module rule step or disappeared part."""
    payload = json.dumps(
        [module_group_id, list(source_path)], separators=(",", ":"), ensure_ascii=False
    )
    return f"requirement:{_stable_digest(payload)}"


def _part_action_key(*parts: object) -> str:
    """Return the stable source action identity of one disappeared official option/part.

    The key is derived from the opened root and the part's original source lineage and indices, so
    it is stable when a caller toggle shifts a part's drawing position.
    """
    payload = json.dumps(list(parts), separators=(",", ":"), ensure_ascii=False)
    return f"requirement:{_stable_digest(payload)}"


def _opaque_work_key(module_group_id: str, source_path: tuple[str | int, ...]) -> str:
    """Return the stable work identity of one opaque source block.

    The key is independent of the reaching lineage, so repeated identical selected-version/block
    work deduplicates while different blocks are distinct.
    """
    payload = json.dumps(
        [module_group_id, list(source_path)], separators=(",", ":"), ensure_ascii=False
    )
    return _stable_digest(payload)


def node_action(
    node: PrerequisiteNodeOccurrence | None,
    *,
    completed_node_keys: frozenset[str],
    excluded_node_keys: frozenset[str],
) -> Literal["excluded", "completed"] | None:
    """Return one node occurrence's caller action: exclusion first, completion second, or `None`.

    This is the one shared node guard every evaluator consults, so no competing key parser or state
    rule exists. A course key's completion is never graph-only: the caller rejects course keys in
    `completed_node_keys`, and canonical course completion and exclusion stay owned by the shared
    course state and the tree's represented exclusion set.
    """
    if node is None:
        return None
    if node.action_key in excluded_node_keys:
        return "excluded"
    if node.action_key in completed_node_keys:
        return "completed"
    return None


def _require_category_homogeneous(
    expression: PrerequisiteExpression, category: InferredPrerequisiteCategory
) -> None:
    """Reject one inferred option branch that switches to another required/recommended category.

    A stored per-category option pool is category-homogeneous: every node either declares its own
    option's category or is a composed wrapper over such nodes. An occurrence with a different
    category would make option membership ambiguous, so it fails loudly instead of being silently
    reclassified.
    """
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
    """Return one mixed-root category partition's complete options.

    A lone direct child is one option. A lone homogeneous OR supplies its ordered option children.
    Several same-category direct children form one transient composed AND option only when none is
    an OR, because distributing an OR child would silently choose a distribution the source never
    stated.
    """
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
    """Split one stored inferred root into its required and recommended complete options.

    The input is the stored published option pool, never compiled output. A homogeneous course or
    AND root is one complete option. A homogeneous top-level OR supplies its ordered option
    children. The mixed-category root AND partitions its direct children by their own occurrence
    category, forming one AND option from several same-category children only when none is an OR.
    Any structure this cannot split without guessing, such as a mixed-category OR, a nested
    category switch, a root AND whose children all disagree with its own category, or a
    non-course/AND/OR root, raises a content-free `ValueError`.
    """
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


def _pool_options(options: tuple[PrerequisiteExpression, ...]) -> PrerequisiteExpression | None:
    """Return one category pool: nothing, the single option, or one flat composed OR of options."""
    if not options:
        return None
    if len(options) == 1:
        return options[0]
    return OrRequirement(
        type="or",
        origin=PrerequisiteOrigin.COMPOSED,
        composed_role=ComposedOrRole.LOGICAL,
        children=options,
    )


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
    """Return whether one module rule tree has no expandable course/module content.

    A blank composite, an unrestricted any-course/any-module rule, and a bounded rule over such
    content are unexpandable. A course or module reference is expandable, even when it later turns
    out to be a self occurrence.
    """
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
    """Return one module rule tree's explicit referenced course and module group IDs.

    Only nonblank `COURSE_UNIT_RULE`/`MODULE_RULE` references are collected, and every child is
    visited so composite and bounded wrappers are traversed. This is a cache-warming superset: it
    never applies the compiler's shape checks and never decides whether a reference is well-formed.
    """
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


class PrerequisiteGraphCompiler:
    """Compile one selected canonical course into a calculation tree and drawing graph."""

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
        """Return one canonical course, reading a cache miss and retaining successful absence.

        A group absent from the database resolves to `None`, so an unknown identity yields
        `MISSING_COURSE` semantics rather than a compiler error.
        Reads are scoped to requested identities. Canonical `group_id` uniqueness is owned by the
        normalized read/database boundary rather than re-scanned here.
        """
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

    def compile_tree(
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
    ) -> PrerequisiteCalculationTree:
        """Build one root's authoritative calculation tree without projecting a drawing graph."""
        if not target_group_id.strip():
            raise ValueError("target_group_id must not be blank")
        retained_inputs = tuple(retained_group_ids)
        excluded_inputs = tuple(excluded_group_ids)
        read_context = DirectPrerequisiteReadContext()
        self._load_courses((target_group_id, *retained_inputs), context=read_context)
        courses_by_group_id = read_context.courses_by_group_id
        modules_by_group_id: dict[str, CatalogueModule] = {}

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
            modules_by_group_id=modules_by_group_id,
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
            issues=[],
            module_boundaries=[],
            ignored_parts=[],
            root_group_id=target_group_id,
            retained_group_ids=frozenset(retained_inputs),
        )
        self._prefetch_inputs((context,), (target,))
        tree, _, _ = self._build_tree(
            target,
            context=context,
            excluded_inputs=excluded_inputs,
            completed_node_keys=tuple(completed_node_keys),
            excluded_node_keys=tuple(excluded_node_keys),
        )
        return tree

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
        """Build the authoritative tree and its pure drawing projection for one root."""
        tree = self.compile_tree(
            target_group_id,
            include_recommended=include_recommended,
            include_inferred=include_inferred,
            active_only=active_only,
            retained_group_ids=retained_group_ids,
            excluded_group_ids=excluded_group_ids,
            completed_node_keys=completed_node_keys,
            excluded_node_keys=excluded_node_keys,
        )
        return PrerequisiteGraphCompilation(tree=tree, graph=project_prerequisite_graph(tree))

    def compile_direct_many(
        self,
        target_group_ids: Collection[str],
        *,
        include_inferred: bool = False,
        active_only: bool = False,
        retained_group_ids: Collection[str] = (),
        read_context: DirectPrerequisiteReadContext | None = None,
    ) -> tuple[DirectPrerequisiteCompilation, ...]:
        """Compile only the candidates' own direct options, without course ancestors.

        Targets are deduplicated and sorted. An empty request returns `()` before any read. One
        scoped `get_courses` loads the targets and retained IDs that the supplied (or fresh) read
        context does not already hold, and course/module/inferred/equivalence reads are cached in
        that context across roots while summaries, issues, coverage and module boundaries stay fresh
        per target. Unknown target IDs fail. An automatically discovered target with no selected
        representative is omitted, like an unrepresented search course. Recommended prerequisites
        are always enabled, exclusions never apply, and no drawing graph is projected. A supplied
        context reuses its raw reads across policies. Compiled outputs never cross that boundary.
        """
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
                    issues=[],
                    module_boundaries=[],
                    ignored_parts=[],
                    root_group_id=target_group_id,
                    direct_only=True,
                    retained_group_ids=frozenset(retained_inputs),
                )
            )
        self._prefetch_inputs(contexts, represented)
        compilations: list[DirectPrerequisiteCompilation] = []
        for target, context in zip(represented, contexts, strict=True):
            tree, required, recommended = self._build_tree(
                target,
                context=context,
                excluded_inputs=(),
            )
            compilations.append(
                DirectPrerequisiteCompilation(tree=tree, required=required, recommended=recommended)
            )
        return tuple(compilations)

    def _prefetch_inputs(
        self,
        contexts: Sequence[_CompilationContext],
        targets: Sequence[CatalogueCourse],
    ) -> None:
        """Warm the shared invocation dictionaries with a bounded superset of direct inputs.

        This is only a cache warmer for the invocation-local dictionaries and read caches.
        Every miss falls through to the
        ordinary on-demand `_course`/`_module` reads. Each frontier issues one bulk `get_courses` and
        one bulk `get_modules` call over all roots, overselecting where a compiled fact
        would need shape checks.
        """
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
            # Only canonical substitution members are read for equivalence: a substitution option
            # may name an identity that is not a canonical course, which the compiler resolves as
            # MISSING_COURSE without ever reading its groups.
            load_courses(substitution_members)
            substitution_equivalence_members = warm_equivalence(
                group_id
                for group_id in sorted(substitution_members)
                if group_id in courses_by_group_id
            )
        load_courses(substitution_members | equivalence_members | substitution_equivalence_members)

    def _build_tree(
        self,
        target: CatalogueCourse,
        *,
        context: _CompilationContext,
        excluded_inputs: tuple[str, ...],
        completed_node_keys: tuple[str, ...] = (),
        excluded_node_keys: tuple[str, ...] = (),
    ) -> tuple[
        PrerequisiteCalculationTree,
        PrerequisiteExpression | None,
        PrerequisiteExpression | None,
    ]:
        """Build one root's authoritative tree plus its separate required/recommended pools.

        The explicitly opened root compiles its own enabled official structure in every activity
        scope. `_mandatory_expanded_heads` classifies the combined pools, then
        `_prune_redundant_expansions` rebuilds each pool. The returned per-category pools are those
        pruned objects, so a returned pool is the tree's own child or, with one pool, the tree's own
        `requirements`. The joined `requirements` is the sole calculation authority for graph
        projection and pathing.
        The caller's graph marks are echoed on the tree and never change the compiled expression.
        A well-formed course action key in `excluded_node_keys` also enters the represented course
        exclusion set so the one shared activity/exclusion predicate denies it everywhere.
        """
        target_group_id = target.group_id
        root_summary = course_summary(target)
        context.summaries_by_group_id[target_group_id] = root_summary
        representative = target.representative
        if representative is None:
            raise ValueError(f"target course {target_group_id} has no selected representative")
        root_source_path = (target_group_id, representative.sisu_course_unit_id)

        required_pool, recommended_pool = self._compile_category_pools(
            target,
            context=context,
            ancestor_course_group_ids=(target_group_id,),
            ancestor_module_group_ids=(),
            treat_inactive_as_active=True,
            source_path=root_source_path,
        )
        pools = tuple(pool for pool in (required_pool, recommended_pool) if pool is not None)
        probe: PrerequisiteExpression | None
        if len(pools) == 1:
            probe = pools[0]
        elif pools:
            probe = AndRequirement(
                type="and",
                origin=PrerequisiteOrigin.COMPOSED,
                composed_role=ComposedAndRole.LOGICAL,
                children=pools,
            )
        else:
            probe = None
        mandatory_heads = _mandatory_expanded_heads(probe)
        if required_pool is not None:
            required_pool = _prune_redundant_expansions(required_pool, mandatory_heads, context)
        if recommended_pool is not None:
            recommended_pool = _prune_redundant_expansions(
                recommended_pool, mandatory_heads, context
            )
        pools = tuple(pool for pool in (required_pool, recommended_pool) if pool is not None)
        requirements: PrerequisiteExpression | None
        if not pools:
            requirements = None
        elif len(pools) == 1:
            requirements = pools[0]
        else:
            requirements = _bind_expression(
                AndRequirement(
                    type="and",
                    origin=PrerequisiteOrigin.COMPOSED,
                    composed_role=ComposedAndRole.LOGICAL,
                    children=pools,
                ),
                context=context,
                source_path=root_source_path,
                role="root_pools",
                children=pools,
            )
        represented = {target_group_id}
        module_occurrences: list[PrerequisiteModuleOccurrence] = []
        if requirements is not None:
            boundaries_by_expression_id: dict[int, list[_CompiledModuleBoundary]] = {}
            for boundary in context.module_boundaries:
                boundaries_by_expression_id.setdefault(id(boundary.expression), []).append(boundary)
            for occurrence_id, expression in _iter_expression_occurrences(requirements):
                if isinstance(expression, CourseRequirement):
                    represented.add(expression.course_group_id)
                matched = boundaries_by_expression_id.get(id(expression))
                if matched is None:
                    continue
                # Several collapsed nested boundaries can share one surviving expression object.
                # The compiler appended inner modules before their containing module, so reverse
                # that local order to record the outer module first at this occurrence.
                for boundary in reversed(matched):
                    module_occurrences.append(
                        PrerequisiteModuleOccurrence(
                            occurrence_id=occurrence_id,
                            module=boundary.module,
                            official_kind=boundary.official_kind,
                            member_group_ids=boundary.member_group_ids,
                            credits_min=boundary.credits_min,
                            credits_max=boundary.credits_max,
                        )
                    )

        # Ignored-part disclosures become positional records here: root-unbound records in collector
        # order first, then each bound record at every final occurrence whose object it anchors.
        bound_parts_by_expression_id: dict[int, list[_CompiledIgnoredPart]] = {}
        root_unbound_parts: list[_CompiledIgnoredPart] = []
        for part in context.ignored_parts:
            if part.anchor is None:
                root_unbound_parts.append(part)
            else:
                bound_parts_by_expression_id.setdefault(id(part.anchor), []).append(part)
        ignored_parts: list[PrerequisiteIgnoredPart] = []

        def emit_ignored(part: _CompiledIgnoredPart, occurrence_id: str | None) -> None:
            ignored_parts.append(
                PrerequisiteIgnoredPart(
                    part_id=f"ignored:{len(ignored_parts)}",
                    kind=part.kind,
                    anchor_occurrence_id=occurrence_id,
                    action_key=part.action_key,
                    course_group_path=part.course_group_path,
                    module_group_path=part.module_group_path,
                    official_kind=part.official_kind,
                    referenced_group_ids=part.referenced_group_ids,
                    detail=part.detail,
                    module=part.module,
                )
            )

        for part in root_unbound_parts:
            emit_ignored(part, None)
        if requirements is not None:
            for occurrence_id, expression in _iter_expression_occurrences(requirements):
                for part in bound_parts_by_expression_id.get(id(expression), ()):
                    emit_ignored(part, occurrence_id)
        for group_id in represented:
            if group_id not in context.summaries_by_group_id:
                course = self._course(group_id, context=context)
                if course is None or course.representative is None:
                    raise ValueError(
                        f"represented course {group_id} has no selected representative"
                    )
                context.summaries_by_group_id[group_id] = course_summary(course)

        # Transient cycle records are located only at the final surviving occurrence of their
        # closing course expression, so a dropped branch contributes no public issue.
        issues: list[PrerequisiteCompilationIssue] = []
        node_occurrences: list[PrerequisiteNodeOccurrence] = [
            PrerequisiteNodeOccurrence(occurrence_id="root", action_key=f"course:{target_group_id}")
        ]
        if requirements is not None:
            occurrences_by_expression_id: dict[int, list[str]] = {}
            for occurrence_id, expression in _iter_expression_occurrences(requirements):
                occurrences_by_expression_id.setdefault(id(expression), []).append(occurrence_id)
                node_occurrences.append(
                    PrerequisiteNodeOccurrence(
                        occurrence_id=occurrence_id,
                        action_key=_expression_bound_key(context, expression),
                        manual_credits_min=context.credit_extent_by_expression_id.get(
                            id(expression)
                        ),
                    )
                )
            for cycle in context.issues:
                cycle_key = _expression_bound_key(context, cycle.expression)
                for occurrence_id in occurrences_by_expression_id.get(id(cycle.expression), ()):
                    issues.append(
                        PrerequisiteCompilationIssue(
                            reason=UnresolvedPrerequisiteReason.COURSE_CYCLE,
                            course_group_path=cycle.course_group_path,
                            occurrence_id=occurrence_id,
                            action_key=cycle_key,
                            origin=cycle.origin,
                            official_kind=cycle.official_kind,
                        )
                    )

        represented_exclusions = set(frozenset(excluded_inputs) & represented)
        for node_key in excluded_node_keys:
            if node_key.startswith("course:"):
                group_id = node_key[len("course:") :]
                if group_id in represented:
                    represented_exclusions.add(group_id)

        tree = PrerequisiteCalculationTree(
            root=root_summary,
            academic_year_start=target.activity_as_of_academic_year_start,
            requirements=requirements,
            courses=tuple(
                context.summaries_by_group_id[group_id] for group_id in sorted(represented)
            ),
            include_recommended=context.include_recommended,
            include_inferred=context.include_inferred,
            active_only=context.active_only,
            inferred_coverage=tuple(
                context.coverage_by_group_id[group_id]
                for group_id in sorted(context.coverage_by_group_id)
            ),
            issues=tuple(issues),
            excluded_group_ids=tuple(sorted(represented_exclusions)),
            module_occurrences=tuple(module_occurrences),
            ignored_parts=tuple(ignored_parts),
            node_occurrences=tuple(node_occurrences),
            completed_node_keys=tuple(sorted(set(completed_node_keys))),
            excluded_node_keys=tuple(sorted(set(excluded_node_keys))),
        )
        return tree, required_pool, recommended_pool

    def _compile_course_requirements(
        self,
        course: CatalogueCourse,
        *,
        context: _CompilationContext,
        ancestor_course_group_ids: tuple[str, ...],
        ancestor_module_group_ids: tuple[str, ...],
        treat_inactive_as_active: bool = False,
        source_path: tuple[str | int, ...],
    ) -> PrerequisiteExpression | None:
        """Pool one active course's enabled official and inferred options per category.

        Official and inferred contributions of one category become one flat OR of complete options.
        Required and recommended pools stay separate and join only with one composed logical AND.
        The separate per-category pools are produced by `_compile_category_pools`. This join keeps
        the ordinary recursive graph output byte-for-byte.
        """
        required_pool, recommended_pool = self._compile_category_pools(
            course,
            context=context,
            ancestor_course_group_ids=ancestor_course_group_ids,
            ancestor_module_group_ids=ancestor_module_group_ids,
            treat_inactive_as_active=treat_inactive_as_active,
            source_path=source_path,
        )
        pools = tuple(pool for pool in (required_pool, recommended_pool) if pool is not None)
        if not pools:
            return None
        if len(pools) == 1:
            return pools[0]
        return _bind_expression(
            AndRequirement(
                type="and",
                origin=PrerequisiteOrigin.COMPOSED,
                composed_role=ComposedAndRole.LOGICAL,
                children=pools,
            ),
            context=context,
            source_path=source_path,
            role="course_pools",
            children=pools,
        )

    def _compile_category_pools(
        self,
        course: CatalogueCourse,
        *,
        context: _CompilationContext,
        ancestor_course_group_ids: tuple[str, ...],
        ancestor_module_group_ids: tuple[str, ...],
        treat_inactive_as_active: bool = False,
        source_path: tuple[str | int, ...],
    ) -> tuple[PrerequisiteExpression | None, PrerequisiteExpression | None]:
        """Produce one active course's separate required and recommended option pools.

        Each visibility gate is applied before entering that category's expansion, so a hidden
        recommended or inferred parent prevents all descendant compilation, summary registration,
        inferred reads, and issue creation for that branch. `treat_inactive_as_active` is the
        root-only official-expansion exception: the explicitly opened root compiles its own official
        compulsory/recommended/substitution structure in every activity scope exactly like an active
        root, but never reads an inferred set when the root itself is inactive. Every recursive call
        keeps the default `False`, so no other inactive course gains descendants or substitutions.
        """
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
        inferred_required: tuple[PrerequisiteExpression, ...] = ()
        inferred_recommended: tuple[PrerequisiteExpression, ...] = ()
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
    ) -> tuple[PrerequisiteExpression, ...]:
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
        official_root: PrerequisiteExpression | None,
        inferred_options: tuple[PrerequisiteExpression, ...],
        official_kind: OfficialPrerequisiteKind,
        *,
        context: _CompilationContext,
        source_path: tuple[str | int, ...],
    ) -> PrerequisiteExpression | None:
        """Pool one category's complete official and inferred options into one flat OR.

        With no surviving inferred option the compiled official root is returned as-is, so an
        official-only tree carries its own option OR wrapper and provenance bytes. Otherwise an
        immediate official same-kind OR contributes its ordered complete children, while any other
        official root, including a composed `COURSE_ALTERNATIVES` OR from a collapsed singleton
        option, is one branch. Inferred options are appended in their source order.
        """
        if not inferred_options:
            return official_root
        branches: list[PrerequisiteExpression] = []
        if official_root is not None:
            if (
                isinstance(official_root, OrRequirement)
                and official_root.origin is PrerequisiteOrigin.OFFICIAL
                and official_root.official_kind is official_kind
            ):
                branches.extend(official_root.children)
            else:
                branches.append(official_root)
        branches.extend(inferred_options)
        pooled = _pool_options(tuple(branches))
        if pooled is None:
            return None
        if isinstance(pooled, (CourseRequirement, ModuleBlockRequirement, OpaqueCreditRequirement)):
            # `_pool_options` returned a single canonical leaf option as-is.
            return pooled
        if id(pooled) in context.action_key_by_expression_id:
            # `_pool_options` returned one of its already-bound structural branches as-is.
            return pooled
        return _bind_expression(
            pooled,
            context=context,
            source_path=(*source_path, official_kind.value, "pool"),
            role="category_pool",
            children=tuple(branches),
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
        """Compile one official compulsory/recommended OR-of-AND group into staged options.

        Each nonempty complete option compiles through a shallow branch-local copy of the context so
        a dropped option leaves no ghost issue, coverage row, module boundary or
        ignored record on a surviving route. Raw reads and the summary dictionary stay shared. An
        empty source option is disclosed as EMPTY_OPTION and dropped before any expression is built,
        and a self-emptied option disappears without an added annotation.
        """
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
                context.ignored_parts.append(
                    _CompiledIgnoredPart(
                        kind=PrerequisiteIgnoredPartKind.EMPTY_OPTION,
                        action_key=_part_action_key(
                            "empty_option",
                            context.root_group_id,
                            ancestor_course_group_ids,
                            requirement_kind.value,
                            option.option_index,
                        ),
                        course_group_path=ancestor_course_group_ids,
                        module_group_path=ancestor_module_group_ids,
                        official_kind=official_kind,
                        detail=f"{requirement_kind.value} option {option.option_index} is empty",
                    )
                )
                continue
            branch_context = replace(
                context,
                issues=[],
                module_boundaries=[],
                coverage_by_group_id={},
                ignored_parts=[],
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
                # The option disappears. An option emptied only by self occurrences adds no
                # annotation, but content the calculation ignored (for example a module whose whole
                # rule was ignored) keeps its disclosures at the owning course/root location.
                context.ignored_parts.extend(branch_context.ignored_parts)
                continue
            compiled_options.append(
                _CompiledOfficialOption(
                    option_index=option.option_index,
                    expression=_collapse_single_child_wrapper(
                        _bind_expression(
                            AndRequirement(
                                type="and",
                                origin=PrerequisiteOrigin.OFFICIAL,
                                official_kind=official_kind,
                                children=compiled,
                            ),
                            context=context,
                            source_path=option_source_path,
                            role="official_option",
                            children=compiled,
                        )
                    ),
                    context=branch_context,
                    course_group_path=ancestor_course_group_ids,
                    module_group_path=ancestor_module_group_ids,
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
    ) -> PrerequisiteExpression | None:
        """Drop a whole missing-module option when a usable alternative exists, then pool the rest.

        Only an option whose compiled expression contains a MISSING_MODULE occurrence may be
        dropped, and only when another non-missing official option or an enabled inferred option
        exists. Otherwise the missing option is unresolved rather than fabricating an empty
        satisfied category. Surviving options' issues, coverage, module boundaries and ignored
        records merge back in source option order. A dropped branch's collectors are discarded
        except its one disclosure.
        """
        missing_options = tuple(
            option for option in options if _contains_missing_module(option.expression)
        )
        missing_ids = {id(option) for option in missing_options}
        usable_options = tuple(option for option in options if id(option) not in missing_ids)
        if missing_options and (usable_options or has_inferred_alternatives):
            for option in missing_options:
                context.ignored_parts.append(
                    _CompiledIgnoredPart(
                        kind=PrerequisiteIgnoredPartKind.MISSING_MODULE_ALTERNATIVE,
                        action_key=_part_action_key(
                            "missing_module_alternative",
                            context.root_group_id,
                            option.course_group_path,
                            option.module_group_path,
                            option.option_index,
                        ),
                        course_group_path=option.course_group_path,
                        module_group_path=option.module_group_path,
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
        for option in surviving:
            context.issues.extend(option.context.issues)
            context.module_boundaries.extend(option.context.module_boundaries)
            context.ignored_parts.extend(option.context.ignored_parts)
            for group_id, record in option.context.coverage_by_group_id.items():
                context.coverage_by_group_id.setdefault(group_id, record)
        if not surviving:
            return None
        if len(surviving) == 1:
            return surviving[0].expression
        option_expressions = tuple(option.expression for option in surviving)
        return _collapse_single_child_wrapper(
            _bind_expression(
                OrRequirement(
                    type="or",
                    origin=PrerequisiteOrigin.OFFICIAL,
                    official_kind=official_kind,
                    children=option_expressions,
                ),
                context=context,
                source_path=(*source_path, official_kind.value, "options"),
                role="official_options",
                children=option_expressions,
            )
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
    ) -> PrerequisiteExpression | None:
        """Compile one official member into a course/expanded leaf or explicit unresolved node.

        A course member equal to its immediate owning course is the direct self
        occurrence: it returns `None` before expansion, summary registration, descendant or
        inferred reads, equivalence reads, or issue creation, so the caller drops it. Module
        members are never self-dropped here.
        """
        if member.member_type is PrerequisiteMemberType.COURSE:
            if member.referenced_group_id == ancestor_course_group_ids[-1]:
                return None
            relative = self._course(member.referenced_group_id, context=context)
            if relative is None or relative.representative is None:
                return _bind_expression(
                    UnresolvedRequirement(
                        type="unresolved",
                        origin=PrerequisiteOrigin.OFFICIAL,
                        official_kind=official_kind,
                        reason=UnresolvedPrerequisiteReason.MISSING_COURSE,
                        referenced_group_id=member.referenced_group_id,
                    ),
                    context=context,
                    source_path=source_path,
                    role="missing_course",
                )
            requirement = CourseRequirement(
                type="course",
                origin=PrerequisiteOrigin.OFFICIAL,
                official_kind=official_kind,
                course_group_id=member.referenced_group_id,
            )
            return self._expand_course_requirement(
                requirement,
                context=context,
                ancestor_course_group_ids=ancestor_course_group_ids,
                ancestor_module_group_ids=ancestor_module_group_ids,
                source_path=source_path,
            )
        if self._module(member.referenced_group_id, context=context) is None:
            return _bind_expression(
                UnresolvedRequirement(
                    type="unresolved",
                    origin=PrerequisiteOrigin.OFFICIAL,
                    official_kind=official_kind,
                    reason=UnresolvedPrerequisiteReason.MISSING_MODULE,
                    referenced_group_id=member.referenced_group_id,
                ),
                context=context,
                source_path=source_path,
                role="missing_module",
            )
        requirement = ModuleRequirement(
            type="module",
            origin=PrerequisiteOrigin.OFFICIAL,
            official_kind=official_kind,
            module_group_id=member.referenced_group_id,
        )
        return self._expand_module_requirement(
            requirement,
            context=context,
            ancestor_course_group_ids=ancestor_course_group_ids,
            ancestor_module_group_ids=ancestor_module_group_ids,
            source_path=source_path,
        )

    def _resolve_module_version(
        self,
        requirement: ModuleRequirement,
        *,
        context: _CompilationContext,
        course_group_path: tuple[str, ...],
        module_group_path: tuple[str, ...],
        source_path: tuple[str | int, ...],
    ) -> CatalogueModuleVersion | UnresolvedRequirement:
        """Select one exact stored module version for the root's academic year, or report why not.

        The strict candidate set is obtained through the shared helper's default call. Only when it
        is empty does the graph opt into the nearest-dated fallback, recording a
        MODULE_VERSION_FALLBACK disclosure naming the requested year and selected version. An
        ambiguous candidate set is unresolved.
        """
        module = self._module(requirement.module_group_id, context=context)
        if module is None:
            return UnresolvedRequirement(
                type="unresolved",
                origin=PrerequisiteOrigin.OFFICIAL,
                official_kind=requirement.official_kind,
                reason=UnresolvedPrerequisiteReason.MISSING_MODULE,
                referenced_group_id=requirement.module_group_id,
            )
        year = context.academic_year_start
        candidates = module_version_candidates(module.versions, academic_year_start=year)
        if len(candidates) == 1:
            return candidates[0]
        if not candidates:
            fallback = module_version_candidates(
                module.versions, academic_year_start=year, allow_nearest=True
            )
            if fallback:
                selected = fallback[0]
                context.ignored_parts.append(
                    _CompiledIgnoredPart(
                        kind=PrerequisiteIgnoredPartKind.MODULE_VERSION_FALLBACK,
                        action_key=_part_action_key(
                            "module_version_fallback",
                            context.root_group_id,
                            source_path,
                        ),
                        course_group_path=course_group_path,
                        module_group_path=module_group_path,
                        official_kind=requirement.official_kind,
                        referenced_group_ids=(module.group_id,),
                        detail=(f"requested year {year}; selected {selected.sisu_module_id}"),
                    )
                )
                return selected
        return UnresolvedRequirement(
            type="unresolved",
            origin=PrerequisiteOrigin.OFFICIAL,
            official_kind=requirement.official_kind,
            reason=(
                UnresolvedPrerequisiteReason.AMBIGUOUS_MODULE_VERSION
                if len(candidates) > 1
                else UnresolvedPrerequisiteReason.MISSING_MODULE
            ),
            referenced_group_id=module.group_id,
        )

    def _expand_module_requirement(
        self,
        requirement: ModuleRequirement,
        *,
        context: _CompilationContext,
        ancestor_course_group_ids: tuple[str, ...],
        ancestor_module_group_ids: tuple[str, ...],
        source_path: tuple[str | int, ...],
    ) -> PrerequisiteExpression | None:
        """Inline one module reference as course/logical/numeric/unresolved without module nodes.

        `None` means the whole inlined contribution disappeared because a `CourseUnitRule` emitted
        the immediate owning course. Callers drop that absent child instead of fabricating a node.
        A selected version records its request-local display boundary beside the surviving
        expression, so the drawing graph can present the module or degree as one node. A cycle or a
        missing/ambiguous version has no selected identity and therefore records no boundary.
        Ignored records that this call has not bound are bound to the surviving inlined
        expression so their disclosure keeps a factual location. A stored version without a rule tree
        is the same whole-module unexpandable shape as a blank source composite.
        """
        offset = len(context.ignored_parts)
        if requirement.module_group_id in ancestor_module_group_ids:
            cycle_path = " -> ".join(ancestor_module_group_ids + (requirement.module_group_id,))
            return _bind_expression(
                UnresolvedRequirement(
                    type="unresolved",
                    origin=PrerequisiteOrigin.OFFICIAL,
                    official_kind=requirement.official_kind,
                    reason=UnresolvedPrerequisiteReason.MODULE_CYCLE,
                    referenced_group_id=requirement.module_group_id,
                    detail=f"module cycle: {cycle_path}",
                ),
                context=context,
                source_path=source_path,
                role="module_cycle",
            )
        version = self._resolve_module_version(
            requirement,
            context=context,
            course_group_path=ancestor_course_group_ids,
            module_group_path=ancestor_module_group_ids + (requirement.module_group_id,),
            source_path=source_path,
        )
        if isinstance(version, UnresolvedRequirement):
            return _bind_expression(
                version, context=context, source_path=source_path, role="module_version"
            )
        module_summary = ModuleSummary(
            group_id=requirement.module_group_id,
            sisu_module_id=version.sisu_module_id,
            module_type=version.module_type,
            code=version.code,
            name_fi=version.name_fi,
            name_en=version.name_en,
        )
        module_source_path = (*source_path, requirement.module_group_id, version.sisu_module_id)
        work_path = (version.sisu_module_id,)
        compiled: PrerequisiteExpression | None
        if version.rule is None:
            context.ignored_parts.append(
                _CompiledIgnoredPart(
                    kind=PrerequisiteIgnoredPartKind.UNEXPANDABLE_CONTENT,
                    action_key=_part_action_key(
                        context.root_group_id, "unexpandable_content", module_source_path
                    ),
                    course_group_path=ancestor_course_group_ids,
                    module_group_path=ancestor_module_group_ids + (requirement.module_group_id,),
                    official_kind=requirement.official_kind,
                    referenced_group_ids=(module_summary.group_id,),
                    detail=f"module version {version.sisu_module_id} has no stored rule tree",
                )
            )
            compiled = None
        else:
            referenced_courses, referenced_modules = _module_rule_references(version.rule)
            self._load_courses(
                referenced_courses - {ancestor_course_group_ids[-1]}, context=context
            )
            self._load_modules(referenced_modules, context=context)
            compiled = self._compile_module_rule(
                version.rule,
                module_group_id=requirement.module_group_id,
                context=context,
                ancestor_course_group_ids=ancestor_course_group_ids,
                ancestor_module_group_ids=ancestor_module_group_ids
                + (requirement.module_group_id,),
                source_path=module_source_path,
                work_path=work_path,
            )
        if compiled is None:
            credited_unexpandable = version.target_credits_min is not None and (
                version.rule is None or _module_content_unexpandable(version.rule)
            )
            for part in context.ignored_parts[offset:]:
                if (
                    not credited_unexpandable
                    and part.kind
                    in (
                        PrerequisiteIgnoredPartKind.UNEXPANDABLE_CONTENT,
                        PrerequisiteIgnoredPartKind.FREE_CHOICE,
                    )
                    and part.module_group_path
                    == ancestor_module_group_ids + (requirement.module_group_id,)
                ):
                    part.module = module_summary
                    break
            if credited_unexpandable:
                # A whole selected module whose entire contents are unexpandable but whose source
                # supplies whole-module target credits is an obligation, not an ignored part. A
                # self-deleted course is not this case.
                compiled = _bind_expression(
                    OpaqueCreditRequirement(
                        type="opaque_credits",
                        origin=PrerequisiteOrigin.OFFICIAL,
                        official_kind=OfficialPrerequisiteKind.MODULE_RULE,
                        work_key=_opaque_work_key(
                            requirement.module_group_id, (version.sisu_module_id,)
                        ),
                        credits_min=version.target_credits_min,
                        credits_max=version.target_credits_max,
                    ),
                    context=context,
                    source_path=module_source_path,
                    role="module_opaque",
                    credits_min=version.target_credits_min,
                )
            else:
                # The inlined rule disappeared, but its disclosures are preserved and left unbound so
                # an enclosing surviving module binds them to its own location, or the tree anchors
                # them to the root. A disappeared module never deletes what the calculation ignored.
                return None
        wrapped = ModuleBlockRequirement(
            type="module_block",
            origin=PrerequisiteOrigin.OFFICIAL,
            official_kind=requirement.official_kind,
            module_group_id=requirement.module_group_id,
            child=compiled,
        )
        self._record_module_boundary(
            wrapped,
            module_summary,
            requirement.official_kind,
            context=context,
            credits_min=version.target_credits_min,
            credits_max=version.target_credits_max,
        )
        if version.target_credits_min is not None:
            context.credit_extent_by_expression_id[id(wrapped)] = version.target_credits_min
        context.bound_expressions.append(wrapped)
        self._bind_ignored_parts(context, offset, wrapped)
        return wrapped

    @staticmethod
    def _bind_ignored_parts(
        context: _CompilationContext, offset: int, anchor: PrerequisiteExpression
    ) -> None:
        """Bind unbound ignored records added since `offset` to their surviving anchor."""
        for part in context.ignored_parts[offset:]:
            if part.anchor is None:
                part.anchor = anchor

    @staticmethod
    def _record_module_boundary(
        expression: PrerequisiteExpression,
        module: ModuleSummary,
        official_kind: OfficialPrerequisiteKind,
        *,
        context: _CompilationContext,
        credits_min: Decimal | None = None,
        credits_max: Decimal | None = None,
    ) -> None:
        """Retain one selected module reference's display boundary beside its inlined expression."""
        context.module_boundaries.append(
            _CompiledModuleBoundary(
                expression=expression,
                module=module,
                official_kind=official_kind,
                member_group_ids=tuple(sorted(set(_iter_module_member_group_ids(expression)))),
                credits_min=credits_min,
                credits_max=credits_max,
            )
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
    ) -> PrerequisiteExpression | None:
        """Compile one stored typed module-rule node into exact official expression structure.

        Every generated node keeps official `MODULE_RULE` provenance, and a source shape that does
        not match its declared kind becomes one explicit `MALFORMED_RULE` unresolved node instead of
        a guessed interpretation. `None` means this rule node compiled to nothing: a
        `CourseUnitRule` named the immediate owning course and was dropped before any lookup, read,
        summary registration, or issue creation, a `CourseUnitRule` named an unretained inactive
        course and was dropped before any descendant, substitution, or equivalence read, an
        unrestricted choice is ignored, or an enclosing connector that lost every child through such a
        drop also returns `None` instead of an empty node. `source_path` is the complete reaching
        lineage for actions and disclosures. `work_path` is the intrinsic selected-module rule
        lineage for opaque-work deduplication.
        """
        match rule.node_type:
            case ModuleRuleType.COMPOSITE_RULE:
                result = self._compile_composite_rule(
                    rule,
                    module_group_id=module_group_id,
                    context=context,
                    ancestor_course_group_ids=ancestor_course_group_ids,
                    ancestor_module_group_ids=ancestor_module_group_ids,
                    source_path=source_path,
                    work_path=work_path,
                )
            case ModuleRuleType.CREDITS_RULE | ModuleRuleType.COURSE_UNIT_COUNT_RULE:
                result = self._compile_bounded_rule(
                    rule,
                    module_group_id=module_group_id,
                    context=context,
                    ancestor_course_group_ids=ancestor_course_group_ids,
                    ancestor_module_group_ids=ancestor_module_group_ids,
                    source_path=source_path,
                    work_path=work_path,
                )
            case ModuleRuleType.COURSE_UNIT_RULE:
                result = self._compile_course_unit_rule(
                    rule,
                    module_group_id=module_group_id,
                    context=context,
                    ancestor_course_group_ids=ancestor_course_group_ids,
                    ancestor_module_group_ids=ancestor_module_group_ids,
                    source_path=source_path,
                )
            case ModuleRuleType.MODULE_RULE:
                result = self._compile_module_reference_rule(
                    rule,
                    module_group_id=module_group_id,
                    context=context,
                    ancestor_course_group_ids=ancestor_course_group_ids,
                    ancestor_module_group_ids=ancestor_module_group_ids,
                    source_path=source_path,
                )
            case ModuleRuleType.ANY_COURSE_UNIT_RULE | ModuleRuleType.ANY_MODULE_RULE:
                result = self._compile_unrestricted_rule(
                    rule,
                    module_group_id=module_group_id,
                    context=context,
                    ancestor_course_group_ids=ancestor_course_group_ids,
                    ancestor_module_group_ids=ancestor_module_group_ids,
                    source_path=source_path,
                )
            case _:
                raise ValueError(f"unsupported module rule node type {rule.node_type.value}")
        if (
            isinstance(result, UnresolvedRequirement)
            and id(result) not in context.action_key_by_expression_id
        ):
            _bind_expression(
                result,
                context=context,
                source_path=source_path,
                role="module_rule_unresolved",
            )
        return result

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
    ) -> tuple[PrerequisiteExpression, ...]:
        """Compile one rule's child rules, dropping any child that compiled to nothing.

        Each child's own `sibling_position` extends the parent's source path, never a
        post-filter enumeration index, so an ignored or dropped preceding sibling never renumbers a
        following child's stable identity.
        """
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
    ) -> PrerequisiteExpression | None:
        """Compile one CompositeRule into an all-mandatory AND or a bounded cardinality node.

        A blank source composite is an unexpandable block: it is disclosed and contributes
        nothing. A bounded composite whose source bounds are impossible is malformed,
        but a composite whose bounds are invalidated only by dropped children is a located
        cardinality node with the original bounds, so the fold reports a no-solution instead of the
        compiler raising or lowering the minimum.
        """
        offending = _unexpected_rule_field(rule, "require_min", "require_max", "all_mandatory")
        if offending is not None:
            return self._malformed_module_rule(
                module_group_id, rule, f"CompositeRule carries unexpected {offending}"
            )
        if not rule.children:
            context.ignored_parts.append(
                _CompiledIgnoredPart(
                    kind=PrerequisiteIgnoredPartKind.UNEXPANDABLE_CONTENT,
                    action_key=_rule_action_key(module_group_id, source_path),
                    course_group_path=ancestor_course_group_ids,
                    module_group_path=ancestor_module_group_ids,
                    official_kind=OfficialPrerequisiteKind.MODULE_RULE,
                    detail="blank CompositeRule has no contents",
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
                # Every child was the immediate owning course and was dropped.
                return None
            expression = _collapse_single_child_wrapper(
                _bind_expression(
                    AndRequirement(
                        type="and",
                        origin=PrerequisiteOrigin.OFFICIAL,
                        official_kind=OfficialPrerequisiteKind.MODULE_RULE,
                        children=compiled,
                    ),
                    context=context,
                    source_path=source_path,
                    role="module_all_mandatory",
                    children=compiled,
                )
            )
            if rule.require_min is not None or rule.require_max is not None:
                # "All mandatory" wins. The stray pick-N bounds are ignored, not enforced.
                context.ignored_parts.append(
                    _CompiledIgnoredPart(
                        kind=PrerequisiteIgnoredPartKind.ALL_MANDATORY_BOUNDS,
                        action_key=_rule_action_key(module_group_id, source_path),
                        course_group_path=ancestor_course_group_ids,
                        module_group_path=ancestor_module_group_ids,
                        official_kind=OfficialPrerequisiteKind.MODULE_RULE,
                        detail=(
                            "all-mandatory composite ignored bounds"
                            f" require_min={rule.require_min} require_max={rule.require_max}"
                        ),
                        anchor=expression,
                    )
                )
            return expression
        if rule.require_min is None:
            return self._malformed_module_rule(
                module_group_id,
                rule,
                "CompositeRule requires explicit require_min unless all-mandatory",
            )
        if rule.require_min > len(rule.children):
            return self._malformed_module_rule(
                module_group_id, rule, "CompositeRule require_min exceeds child count"
            )
        if rule.require_max is not None and rule.require_max > len(rule.children):
            return self._malformed_module_rule(
                module_group_id, rule, "CompositeRule require_max exceeds child count"
            )
        if rule.require_max is not None and rule.require_min > rule.require_max:
            return self._malformed_module_rule(
                module_group_id, rule, "CompositeRule require_min exceeds require_max"
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
        # Dropped children never lower the source minimum: a positive pick-N left without enough
        # survivors is a located cardinality node whose fold returns no-solution.
        return _bind_expression(
            CardinalityRequirement(
                type="cardinality",
                origin=PrerequisiteOrigin.OFFICIAL,
                official_kind=OfficialPrerequisiteKind.MODULE_RULE,
                require_min=rule.require_min,
                require_max=rule.require_max,
                children=compiled,
            ),
            context=context,
            source_path=source_path,
            role="module_cardinality",
            children=compiled,
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
    ) -> PrerequisiteExpression | None:
        """Compile one CreditsRule/CourseUnitCountRule into a numeric range or opaque obligation.

        A credit bound over wholly unexpandable content becomes one childless opaque obligation
        costing its real source minimum. A positive course-count bound over unknown contents becomes
        a located unknown-count unresolved node, because an unknown number of courses cannot be
        measured. Real expanded children keep their actual numeric range. The two source kinds differ
        only in their bound field names and the typed requirement they emit.
        """
        if rule.node_type is ModuleRuleType.CREDITS_RULE:
            lower_name, upper_name = "credits_min", "credits_max"
        else:
            lower_name, upper_name = "count_min", "count_max"
        offending = _unexpected_rule_field(rule, lower_name, upper_name)
        if offending is not None:
            return self._malformed_module_rule(
                module_group_id, rule, f"{rule.node_type.value} carries unexpected {offending}"
            )
        lower = getattr(rule, lower_name)
        if lower is None:
            return self._malformed_module_rule(
                module_group_id, rule, f"{rule.node_type.value} requires {lower_name}"
            )
        upper = getattr(rule, upper_name)
        if upper is not None and lower > upper:
            return self._malformed_module_rule(
                module_group_id, rule, f"{rule.node_type.value} {lower_name} exceeds {upper_name}"
            )
        if len(rule.children) != 1:
            return self._malformed_module_rule(
                module_group_id, rule, f"{rule.node_type.value} requires exactly one child"
            )
        child_rule = rule.children[0]
        disclosure_offset = len(context.ignored_parts)
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
            # An absent child is a real unexpandable obligation only when the source shape is
            # unexpandable or it emitted its own FREE_CHOICE/UNEXPANDABLE_CONTENT disclosure. A child
            # that vanished solely as a direct self occurrence contributes nothing and must
            # never be charged a whole-module target credit.
            real_unexpandable = _module_content_unexpandable(child_rule) or any(
                part.kind
                in (
                    PrerequisiteIgnoredPartKind.FREE_CHOICE,
                    PrerequisiteIgnoredPartKind.UNEXPANDABLE_CONTENT,
                )
                for part in context.ignored_parts[disclosure_offset:]
            )
            if not real_unexpandable:
                return None
            if rule.node_type is ModuleRuleType.CREDITS_RULE:
                # A real source credit minimum over wholly unexpandable content is an obligation,
                # not an ignored part: draw it childless and charge the source minimum once.
                return _bind_expression(
                    OpaqueCreditRequirement(
                        type="opaque_credits",
                        origin=PrerequisiteOrigin.OFFICIAL,
                        official_kind=OfficialPrerequisiteKind.MODULE_RULE,
                        work_key=_opaque_work_key(module_group_id, work_path),
                        credits_min=rule.credits_min,
                        credits_max=rule.credits_max,
                    ),
                    context=context,
                    source_path=source_path,
                    role="bounded_opaque",
                    credits_min=rule.credits_min,
                )
            if rule.count_min == 0 and rule.count_max is None:
                # Only a zero-minimum, unbounded unknown count is a real zero requirement. Any
                # positive minimum or finite maximum is a located unknown.
                context.ignored_parts.append(
                    _CompiledIgnoredPart(
                        kind=PrerequisiteIgnoredPartKind.UNEXPANDABLE_CONTENT,
                        action_key=_rule_action_key(module_group_id, source_path),
                        course_group_path=ancestor_course_group_ids,
                        module_group_path=ancestor_module_group_ids,
                        official_kind=OfficialPrerequisiteKind.MODULE_RULE,
                        detail=f"{rule.node_type.value} count_min=0 over unexpandable content",
                    )
                )
                return None
            return _bind_expression(
                UnresolvedRequirement(
                    type="unresolved",
                    origin=PrerequisiteOrigin.OFFICIAL,
                    official_kind=OfficialPrerequisiteKind.MODULE_RULE,
                    reason=UnresolvedPrerequisiteReason.UNKNOWN_COURSE_COUNT,
                    referenced_group_id=module_group_id,
                    detail=(
                        f"{rule.node_type.value} count_min={rule.count_min} "
                        f"count_max={rule.count_max} over unknown content"
                    ),
                ),
                context=context,
                source_path=source_path,
                role="bounded_unknown_count",
            )
        if rule.node_type is ModuleRuleType.CREDITS_RULE:
            return _bind_expression(
                CreditRequirement(
                    type="credits",
                    origin=PrerequisiteOrigin.OFFICIAL,
                    official_kind=OfficialPrerequisiteKind.MODULE_RULE,
                    credits_min=rule.credits_min,
                    credits_max=rule.credits_max,
                    child=child,
                ),
                context=context,
                source_path=source_path,
                role="credits",
                children=(child,),
                credits_min=rule.credits_min,
            )
        return _bind_expression(
            CourseCountRequirement(
                type="course_count",
                origin=PrerequisiteOrigin.OFFICIAL,
                official_kind=OfficialPrerequisiteKind.MODULE_RULE,
                count_min=rule.count_min,
                count_max=rule.count_max,
                child=child,
            ),
            context=context,
            source_path=source_path,
            role="course_count",
            children=(child,),
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
    ) -> PrerequisiteExpression | None:
        """Compile one CourseUnitRule into a course leaf, dropping the immediate self course."""
        offending = _unexpected_rule_field(rule, "referenced_group_id")
        if offending is not None:
            return self._malformed_module_rule(
                module_group_id, rule, f"CourseUnitRule carries unexpected {offending}"
            )
        if rule.children:
            return self._malformed_module_rule(
                module_group_id, rule, "CourseUnitRule forbids child rules"
            )
        course_group_id = rule.referenced_group_id
        if course_group_id is None or not course_group_id.strip():
            return self._malformed_module_rule(
                module_group_id, rule, "CourseUnitRule requires a nonblank referenced course ID"
            )
        if course_group_id == ancestor_course_group_ids[-1]:
            # The immediate owning course's own module rule is the direct self
            # occurrence: drop it before any lookup, read, registration, or cycle issue.
            return None
        relative = self._course(course_group_id, context=context)
        if relative is None or relative.representative is None:
            return UnresolvedRequirement(
                type="unresolved",
                origin=PrerequisiteOrigin.OFFICIAL,
                official_kind=OfficialPrerequisiteKind.MODULE_RULE,
                reason=UnresolvedPrerequisiteReason.MISSING_COURSE,
                referenced_group_id=course_group_id,
            )
        return self._expand_course_requirement(
            CourseRequirement(
                type="course",
                origin=PrerequisiteOrigin.OFFICIAL,
                official_kind=OfficialPrerequisiteKind.MODULE_RULE,
                course_group_id=course_group_id,
            ),
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
    ) -> PrerequisiteExpression | None:
        """Compile one ModuleRule reference by inlining its resolved module version."""
        offending = _unexpected_rule_field(rule, "referenced_group_id")
        if offending is not None:
            return self._malformed_module_rule(
                module_group_id, rule, f"ModuleRule carries unexpected {offending}"
            )
        if rule.children:
            return self._malformed_module_rule(
                module_group_id, rule, "ModuleRule forbids child rules"
            )
        module_reference = rule.referenced_group_id
        if module_reference is None or not module_reference.strip():
            return self._malformed_module_rule(
                module_group_id, rule, "ModuleRule requires a nonblank referenced module ID"
            )
        return self._expand_module_requirement(
            ModuleRequirement(
                type="module",
                origin=PrerequisiteOrigin.OFFICIAL,
                official_kind=OfficialPrerequisiteKind.MODULE_RULE,
                module_group_id=module_reference,
            ),
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
    ) -> PrerequisiteExpression | None:
        """Ignore one well-shaped ANY_COURSE_UNIT/ANY_MODULE rule in calculation.

        Unrestricted choice has no source course or credit content, so it contributes nothing: it is
        disclosed as an ignored part and never becomes a successful zero-credit alternative or a
        selectable position. The malformed shapes keep their explicit unresolved node.
        """
        offending = _unexpected_rule_field(rule)
        if offending is not None:
            return self._malformed_module_rule(
                module_group_id, rule, f"{rule.node_type.value} carries unexpected {offending}"
            )
        if rule.children:
            return self._malformed_module_rule(
                module_group_id, rule, f"{rule.node_type.value} forbids child rules"
            )
        context.ignored_parts.append(
            _CompiledIgnoredPart(
                kind=PrerequisiteIgnoredPartKind.FREE_CHOICE,
                action_key=_rule_action_key(module_group_id, source_path),
                course_group_path=ancestor_course_group_ids,
                module_group_path=ancestor_module_group_ids,
                official_kind=OfficialPrerequisiteKind.MODULE_RULE,
                detail=f"{rule.node_type.value} ignored in calculation",
            )
        )
        return None

    @staticmethod
    def _malformed_module_rule(
        module_group_id: str,
        rule: CatalogueModuleRule,
        detail: str,
    ) -> UnresolvedRequirement:
        """Build one explicit malformed module-rule node naming its owning module."""
        return UnresolvedRequirement(
            type="unresolved",
            origin=PrerequisiteOrigin.OFFICIAL,
            official_kind=OfficialPrerequisiteKind.MODULE_RULE,
            reason=UnresolvedPrerequisiteReason.MALFORMED_RULE,
            referenced_group_id=module_group_id,
            detail=f"{rule.node_type.value}: {detail}",
        )

    def _expand_course_requirement(
        self,
        requirement: CourseRequirement,
        *,
        context: _CompilationContext,
        ancestor_course_group_ids: tuple[str, ...],
        ancestor_module_group_ids: tuple[str, ...],
        source_path: tuple[str | int, ...],
        allow_substitutions: bool = True,
        allow_equivalences: bool = True,
    ) -> PrerequisiteExpression | None:
        """Recursively expand one course occurrence with children, alternatives, and cycles.

        Under active-only scope a non-root inactive course whose canonical ID is not in
        `context.retained_group_ids` returns `None`, so the caller drops the whole branch. An active
        course expands its children, substitutions and equivalences, while a retained inactive course
        is a childless leaf. The mandatory-position rule is stated in
        `docs/architecture/seams/prerequisites.md`.
        `allow_substitutions` and `allow_equivalences` control only this head occurrence's
        official substitution options and inferred equivalent-member alternatives. Ordinary
        descendant course occurrences keep normal expansion either way. The course's own branch is
        gathered first, surviving official substitution branches second, and inferred equivalent
        branches last, and all of them form one flat `COURSE_ALTERNATIVES` composed OR.
        Ignored records that this call has not bound are bound to this represented head
        `CourseRequirement` so a dropped-option disclosure keeps its owning course location.
        """
        offset = len(context.ignored_parts)
        course = self._course(requirement.course_group_id, context=context)
        if course is None:
            raise ValueError(f"expanded course {requirement.course_group_id} is not canonical")
        if not course.is_active:
            if (
                context.active_only
                and requirement.course_group_id not in context.retained_group_ids
            ):
                return None
            return requirement
        if requirement.course_group_id in ancestor_course_group_ids:
            context.issues.append(
                _CompiledCourseCycle(
                    expression=requirement,
                    course_group_path=ancestor_course_group_ids + (requirement.course_group_id,),
                    origin=requirement.origin,
                    official_kind=requirement.official_kind,
                )
            )
            return requirement
        if course.representative is None:
            raise ValueError(f"represented course {course.group_id} has no selected representative")
        descendants = ancestor_course_group_ids + (requirement.course_group_id,)
        descendant_source_path = (*source_path, "descendants")
        child_requirements = (
            None
            if context.direct_only
            else self._compile_course_requirements(
                course,
                context=context,
                ancestor_course_group_ids=descendants,
                ancestor_module_group_ids=ancestor_module_group_ids,
                source_path=descendant_source_path,
            )
        )
        branch: PrerequisiteExpression = requirement
        if child_requirements is not None:
            branch = _bind_expression(
                AndRequirement(
                    type="and",
                    origin=PrerequisiteOrigin.COMPOSED,
                    composed_role=ComposedAndRole.EXPANDED_COURSE,
                    children=(requirement, child_requirements),
                ),
                context=context,
                source_path=source_path,
                role="expanded_course",
                children=(requirement, child_requirements),
            )
        branches: list[PrerequisiteExpression] = [branch]
        if allow_substitutions and course.representative.substitution_options:
            branches.extend(
                self._compile_substitution_branches(
                    course,
                    context=context,
                    ancestor_course_group_ids=descendants,
                    ancestor_module_group_ids=ancestor_module_group_ids,
                    source_path=(*source_path, "substitutions"),
                )
            )
        if context.include_inferred and allow_equivalences:
            branches.extend(
                self._compile_equivalence_branches(
                    requirement,
                    context=context,
                    ancestor_course_group_ids=descendants,
                    ancestor_module_group_ids=ancestor_module_group_ids,
                    source_path=(*source_path, "equivalences"),
                )
            )
        if len(branches) == 1:
            self._bind_ignored_parts(context, offset, requirement)
            return branch
        self._bind_ignored_parts(context, offset, requirement)
        return _bind_expression(
            OrRequirement(
                type="or",
                origin=PrerequisiteOrigin.COMPOSED,
                composed_role=ComposedOrRole.COURSE_ALTERNATIVES,
                children=tuple(branches),
            ),
            context=context,
            source_path=source_path,
            role="course_alternatives",
            children=tuple(branches),
        )

    def _read_equivalence_groups(
        self, member_group_id: str, *, context: _CompilationContext
    ) -> tuple[CurrentEquivalenceGroup, ...]:
        """Return one canonical member's exact current groups, reading the protocol at most once.

        The single per-compilation cache serves every occurrence of the same canonical member so
        a cache miss performs one `read_for_member` call. Direct bulk prefetch may warm it first. The
        repository's sorted tuple is returned as-is. The compiler merges no groups,
        deduplicates members across group identities, or computes a transitive closure.
        """
        cached = context.equivalence_read_cache.get(member_group_id)
        if cached is not None:
            return cached
        groups = context.equivalence_groups.read_for_member(member_group_id)
        context.equivalence_read_cache[member_group_id] = groups
        return groups

    def _compile_equivalence_branches(
        self,
        requirement: CourseRequirement,
        *,
        context: _CompilationContext,
        ancestor_course_group_ids: tuple[str, ...],
        ancestor_module_group_ids: tuple[str, ...],
        source_path: tuple[str | int, ...],
    ) -> tuple[PrerequisiteExpression, ...]:
        """Compile one represented course occurrence's exact inferred equivalent-member branches.

        Every accepted group containing the represented canonical course is read in repository
        UUID order and each group's already-sorted members are offered in that order, minus the
        represented member itself and any member already on the ancestor path (the selected root
        or another represented ancestor), which is skipped without a cycle issue. Each offered
        member is an inferred course occurrence carrying the group's inference evidence and a
        category derived from the represented leaf, expanded with both alternative flags false so
        its own substitutions and groups never chain into transitive alternatives while its
        ordinary prerequisites and real credits stay.
        """
        derived_category = (
            InferredPrerequisiteCategory.RECOMMENDED
            if requirement.official_kind is OfficialPrerequisiteKind.RECOMMENDED
            or requirement.inferred_category is InferredPrerequisiteCategory.RECOMMENDED
            else InferredPrerequisiteCategory.REQUIRED
        )
        branches: list[PrerequisiteExpression] = []
        for group in self._read_equivalence_groups(requirement.course_group_id, context=context):
            for member in group.members:
                if member.course_group_id == requirement.course_group_id:
                    continue
                if member.course_group_id in ancestor_course_group_ids:
                    continue
                expanded = self._expand_course_requirement(
                    CourseRequirement(
                        type="course",
                        origin=PrerequisiteOrigin.INFERRED,
                        inferred_category=derived_category,
                        course_group_id=member.course_group_id,
                        inference=group.inference,
                    ),
                    context=context,
                    ancestor_course_group_ids=ancestor_course_group_ids,
                    ancestor_module_group_ids=ancestor_module_group_ids,
                    source_path=(
                        *source_path,
                        str(group.group_id),
                        member.course_group_id,
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
    ) -> tuple[PrerequisiteExpression, ...]:
        """Compile one course's surviving directional substitution option branches in source order.

        A branch is one official `SUBSTITUTION` AND of its compiled members. A singleton AND
        collapses to its member. A member equal to the immediate owning course is dropped before
        expansion, so an option emptied only by that self occurrence disappears. A genuinely
        empty source option is disclosed as EMPTY_OPTION and dropped, and a populated option naming
        any nonexistent canonical course is dropped whole as MISSING_SUBSTITUTION_COURSE without any
        descendant or equivalence expansion. The represented course and other options remain.
        """
        representative = course.representative
        if representative is None:
            raise ValueError(f"course {course.group_id} has no selected representative")
        options = representative.substitution_options
        option_indices = tuple(option.option_index for option in options)
        if len(set(option_indices)) != len(option_indices):
            raise ValueError(f"course {course.group_id} has duplicate substitution option indices")
        branches: list[PrerequisiteExpression] = []
        for option in sorted(options, key=lambda candidate: candidate.option_index):
            member_indices = tuple(member.member_index for member in option.members)
            if len(set(member_indices)) != len(member_indices):
                raise ValueError(
                    f"course {course.group_id} has duplicate substitution member indices"
                )
            members = sorted(option.members, key=lambda candidate: candidate.member_index)
            if not members:
                context.ignored_parts.append(
                    _CompiledIgnoredPart(
                        kind=PrerequisiteIgnoredPartKind.EMPTY_OPTION,
                        action_key=_part_action_key(
                            "empty_substitution",
                            context.root_group_id,
                            ancestor_course_group_ids,
                            option.option_index,
                        ),
                        course_group_path=ancestor_course_group_ids,
                        module_group_path=ancestor_module_group_ids,
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
                context.ignored_parts.append(
                    _CompiledIgnoredPart(
                        kind=PrerequisiteIgnoredPartKind.MISSING_SUBSTITUTION_COURSE,
                        action_key=_part_action_key(
                            "missing_substitution_course",
                            context.root_group_id,
                            ancestor_course_group_ids,
                            option.option_index,
                        ),
                        course_group_path=ancestor_course_group_ids,
                        module_group_path=ancestor_module_group_ids,
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
                # Every source member compiled to nothing, as a self occurrence or an unretained
                # inactive course, so the option disappears.
                continue
            branches.append(
                _collapse_single_child_wrapper(
                    _bind_expression(
                        AndRequirement(
                            type="and",
                            origin=PrerequisiteOrigin.OFFICIAL,
                            official_kind=OfficialPrerequisiteKind.SUBSTITUTION,
                            children=compiled,
                        ),
                        context=context,
                        source_path=option_source_path,
                        role="substitution_option",
                        children=compiled,
                    )
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
    ) -> PrerequisiteExpression | None:
        """Compile one substitution member course without chaining that member's own options.

        A member equal to the immediate owning course is the direct self occurrence and
        returns `None` before expansion, summary registration, or issue creation.
        """
        if member.course_group_id == ancestor_course_group_ids[-1]:
            return None
        course = self._course(member.course_group_id, context=context)
        if course is None or course.representative is None:
            return _bind_expression(
                UnresolvedRequirement(
                    type="unresolved",
                    origin=PrerequisiteOrigin.OFFICIAL,
                    official_kind=OfficialPrerequisiteKind.SUBSTITUTION,
                    reason=UnresolvedPrerequisiteReason.MISSING_COURSE,
                    referenced_group_id=member.course_group_id,
                ),
                context=context,
                source_path=source_path,
                role="missing_substitution_course",
            )
        requirement = CourseRequirement(
            type="course",
            origin=PrerequisiteOrigin.OFFICIAL,
            official_kind=OfficialPrerequisiteKind.SUBSTITUTION,
            course_group_id=member.course_group_id,
        )
        return self._expand_course_requirement(
            requirement,
            context=context,
            ancestor_course_group_ids=ancestor_course_group_ids,
            ancestor_module_group_ids=ancestor_module_group_ids,
            source_path=source_path,
            allow_substitutions=False,
        )

    def _read_inferred_expression(
        self, course: CatalogueCourse, *, context: _CompilationContext
    ) -> PrerequisiteExpression | None:
        """Read one active course's inferred expression once, or contribute nothing when absent.

        An unavailable or stale-activity inferred set contributes no expression, without coverage
        or an issue: the graph uses the contributions that exist. Only a current set records
        its real coverage, and a current set must expose a valid payload. The read result is
        cached on the first miss so subsequent occurrences of the same course reuse the one read.
        """
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
    ) -> PrerequisiteExpression | None:
        """Copy one stored inferred AND/OR/course structure, expanding its course leaves.

        The occurrence's own `inferred_category` is checked before any expansion: a recommended
        occurrence with `include_recommended=False` returns `None` before course expansion,
        descendant compilation, inferred reads, summary registration, or issue creation, so a
        hidden parent removes its whole subtree. Children keep their own categories. Only `None`
        children are dropped, and a connector that loses every child returns `None`. A course leaf
        equal to its immediate owning course is the direct self occurrence and returns
        `None` before expansion, so the connector filtering removes that branch.
        """
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
                expression,
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
            return _collapse_single_child_wrapper(
                _bind_expression(
                    expression.model_copy(update={"children": expanded_children}),
                    context=context,
                    source_path=source_path,
                    role="inferred_wrapper",
                    children=expanded_children,
                )
            )
        raise ValueError(
            f"inferred sets support only course/and/or nodes, not {type(expression).__name__}"
        )


_CONNECTOR_KINDS: dict[type[PrerequisiteExpression], PrerequisiteGraphConnectorKind] = {
    AndRequirement: PrerequisiteGraphConnectorKind.AND,
    OrRequirement: PrerequisiteGraphConnectorKind.OR,
    CardinalityRequirement: PrerequisiteGraphConnectorKind.CARDINALITY,
    CreditRequirement: PrerequisiteGraphConnectorKind.CREDITS,
    CourseCountRequirement: PrerequisiteGraphConnectorKind.COURSE_COUNT,
    OpaqueCreditRequirement: PrerequisiteGraphConnectorKind.OPAQUE_CREDITS,
    UnresolvedRequirement: PrerequisiteGraphConnectorKind.UNRESOLVED,
}


def _connector_children(
    expression: PrerequisiteExpression,
) -> tuple[PrerequisiteExpression, ...]:
    """Return one connector expression's ordered child occurrences."""
    if isinstance(expression, (AndRequirement, OrRequirement, CardinalityRequirement)):
        return expression.children
    if isinstance(expression, (CreditRequirement, CourseCountRequirement)):
        return (expression.child,)
    if isinstance(expression, ModuleBlockRequirement):
        return (expression.child,)
    return ()


def _connector_node(
    expression: PrerequisiteExpression, occurrence_id: str, action_key: str
) -> PrerequisiteGraphConnectorNode:
    """Map one non-course expression occurrence to its scoped connector node."""
    kind = _CONNECTOR_KINDS[type(expression)]
    fields: dict[str, object] = {
        "node_id": f"connector:{occurrence_id}",
        "action_key": action_key,
        "kind": kind,
        "origin": expression.origin,
        "official_kind": expression.official_kind,
        "inferred_category": expression.inferred_category,
        "inference": expression.inference,
    }
    if isinstance(expression, CardinalityRequirement):
        fields["require_min"] = expression.require_min
        fields["require_max"] = expression.require_max
    elif isinstance(expression, CreditRequirement):
        fields["credits_min"] = expression.credits_min
        fields["credits_max"] = expression.credits_max
    elif isinstance(expression, CourseCountRequirement):
        fields["count_min"] = expression.count_min
        fields["count_max"] = expression.count_max
    elif isinstance(expression, OpaqueCreditRequirement):
        fields["credits_min"] = expression.credits_min
        fields["credits_max"] = expression.credits_max
        fields["detail"] = expression.work_key
    elif isinstance(expression, UnresolvedRequirement):
        fields["unresolved_reason"] = expression.reason
        fields["referenced_group_id"] = expression.referenced_group_id
        fields["detail"] = expression.detail
    return PrerequisiteGraphConnectorNode(**fields)


def is_expanded_course_branch(expression: PrerequisiteExpression) -> bool:
    """Return whether an expression is the compiler's exact expanded-course composed AND.

    An active required course with ordinary prerequisites compiles to
    `AndRequirement(origin=COMPOSED, composed_role=EXPANDED_COURSE, children=(course_leaf,
    descendants))`. This is the one shared predicate satisfaction and pathing both recognize.
    Only the explicit compiler role identifies an expanded course, so an ordinary logical
    conjunction with an identical child shape never qualifies. Any other expression is not an
    expanded course, so the wrappers never leak into ordinary logical evaluation.
    """
    return (
        isinstance(expression, AndRequirement)
        and expression.origin is PrerequisiteOrigin.COMPOSED
        and expression.composed_role is ComposedAndRole.EXPANDED_COURSE
        and len(expression.children) == 2
        and isinstance(expression.children[0], CourseRequirement)
    )


def _mandatory_child_pairs(
    expression: PrerequisiteExpression, mandatory: bool
) -> tuple[tuple[PrerequisiteExpression, bool], ...]:
    """Return each of one expression's connector children with its own mandatory flag.

    A child of an `AndRequirement`, `ModuleBlockRequirement`, `CreditRequirement` or
    `CourseCountRequirement` inherits the parent's flag, and every `OrRequirement` child is
    non-mandatory. The mandatory-position classification is stated in
    `docs/architecture/seams/prerequisites.md`.
    """
    if isinstance(
        expression,
        (AndRequirement, ModuleBlockRequirement, CreditRequirement, CourseCountRequirement),
    ):
        return tuple((child, mandatory) for child in _connector_children(expression))
    return tuple((child, False) for child in _connector_children(expression))


def _mandatory_expanded_heads(expression: PrerequisiteExpression | None) -> frozenset[str]:
    """Return the canonical IDs of every expanded course that appears in a mandatory position.

    Every child occurrence is classified by `_mandatory_child_pairs`, the one owner of the
    mandatory-position rule. A `None` expression yields an empty set.
    """
    if expression is None:
        return frozenset()
    heads: set[str] = set()
    stack: list[tuple[PrerequisiteExpression, bool]] = [(expression, True)]
    while stack:
        node, mandatory = stack.pop()
        if is_expanded_course_branch(node) and mandatory:
            heads.add(node.children[0].course_group_id)
        stack.extend(_mandatory_child_pairs(node, mandatory))
    return frozenset(heads)


def _prune_redundant_expansions(
    expression: PrerequisiteExpression,
    mandatory_heads: frozenset[str],
    context: _CompilationContext,
) -> PrerequisiteExpression:
    """Collapse a non-mandatory repeated expanded occurrence of a course in a mandatory position to a
    bare leaf.

    `mandatory_heads` is the canonical-ID set that `_mandatory_expanded_heads` collects and that
    `_mandatory_child_pairs` classifies. A rebuilt node carries the bound action key, credit extent,
    module boundary and ignored-part anchors of its source object, so occurrence identity is stable.
    The mandatory-position rule is stated in `docs/architecture/seams/prerequisites.md`.
    """
    if not mandatory_heads:
        return expression
    boundaries_by_expression_id: dict[int, list[int]] = {}
    for index, boundary in enumerate(context.module_boundaries):
        boundaries_by_expression_id.setdefault(id(boundary.expression), []).append(index)
    parts_by_anchor_id: dict[int, list[_CompiledIgnoredPart]] = {}
    for part in context.ignored_parts:
        if part.anchor is not None:
            parts_by_anchor_id.setdefault(id(part.anchor), []).append(part)

    def rekey(old: PrerequisiteExpression, new: PrerequisiteExpression) -> None:
        """Move one rebuilt object's bound identity, extent and anchored records onto its copy."""
        action_key = context.action_key_by_expression_id.pop(id(old), None)
        if action_key is not None:
            context.action_key_by_expression_id[id(new)] = action_key
        credit_extent = context.credit_extent_by_expression_id.pop(id(old), None)
        if credit_extent is not None:
            context.credit_extent_by_expression_id[id(new)] = credit_extent
        context.bound_expressions.append(new)
        for index in boundaries_by_expression_id.pop(id(old), ()):
            context.module_boundaries[index] = replace(
                context.module_boundaries[index], expression=new
            )
        for part in parts_by_anchor_id.pop(id(old), ()):
            part.anchor = new

    def rebuild(node: PrerequisiteExpression, update: dict[str, object]) -> PrerequisiteExpression:
        new = node.model_copy(update=update)
        rekey(node, new)
        return new

    def walk(node: PrerequisiteExpression, *, mandatory: bool) -> PrerequisiteExpression:
        pairs = _mandatory_child_pairs(node, mandatory)
        if is_expanded_course_branch(node):
            (head, _), (descendants, descendant_mandatory) = pairs
            if head.course_group_id in mandatory_heads and not mandatory:
                return head
            pruned_descendants = walk(descendants, mandatory=descendant_mandatory)
            if pruned_descendants is descendants:
                return node
            return rebuild(node, {"children": (head, pruned_descendants)})
        children = tuple(child for child, _ in pairs)
        pruned = tuple(walk(child, mandatory=child_mandatory) for child, child_mandatory in pairs)
        if all(new is old for new, old in zip(pruned, children, strict=True)):
            return node
        if isinstance(node, (CreditRequirement, CourseCountRequirement, ModuleBlockRequirement)):
            return rebuild(node, {"child": pruned[0]})
        return rebuild(node, {"children": pruned})

    return walk(expression, mandatory=True)


def _course_path_flags(expression: PrerequisiteExpression) -> tuple[bool, bool]:
    """Return the head course's path-category pair for compiler-generated wrappers.

    A bare course leaf carries its own pair: inferred origin for the inferred flag, and official
    `RECOMMENDED` or inferred `RECOMMENDED` category for the recommended flag. An expanded required
    course is the compiler's role-tagged `AndRequirement(origin=COMPOSED,
    composed_role=EXPANDED_COURSE, children=(course_leaf, descendants))`, and the flat effective
    course-alternative OR is the compiler's role-tagged `OrRequirement(origin=COMPOSED,
    composed_role=COURSE_ALTERNATIVES, children=(represented_branch, alternatives...))` whose first
    child is the represented occurrence. Those composed wrappers avoid repeating the
    head course's provenance, so forwarding it here keeps official descendants, substitutes, and
    inferred equivalents beneath a bare inferred/recommended occurrence on that parent's visible
    path. Only the exact compiler roles identify a wrapper. An ordinary logical composed AND or OR
    returns `(False, False)`, and this never relabels a wrapper, descendant, connector, or
    relationship member.
    """
    if isinstance(expression, CourseRequirement):
        return (
            expression.origin is PrerequisiteOrigin.INFERRED,
            expression.official_kind is OfficialPrerequisiteKind.RECOMMENDED
            or expression.inferred_category is InferredPrerequisiteCategory.RECOMMENDED,
        )
    if is_expanded_course_branch(expression):
        return _course_path_flags(expression.children[0])
    if (
        isinstance(expression, OrRequirement)
        and expression.origin is PrerequisiteOrigin.COMPOSED
        and expression.composed_role is ComposedOrRole.COURSE_ALTERNATIVES
    ):
        return _course_path_flags(expression.children[0])
    return (False, False)


def _longest_module_prefix(anchor: str, module_occurrence_ids: frozenset[str]) -> str | None:
    """Return the longest drawn module occurrence ID containing one anchor occurrence.

    Containment is matched on dot-separated occurrence segments, so `r.10` is never treated as
    inside `r.1`.
    """
    best: str | None = None
    for module_id in module_occurrence_ids:
        if anchor == module_id or anchor.startswith(f"{module_id}."):
            if best is None or len(module_id) > len(best):
                best = module_id
    return best


def _ignored_anchor_parent(
    tree: PrerequisiteCalculationTree,
    part: PrerequisiteIgnoredPart,
    *,
    drawn_module_occurrence_ids: frozenset[str],
    standalone_group_ids: frozenset[str],
    connector_occurrence_ids: frozenset[str],
    expression_by_occurrence_id: dict[str, PrerequisiteExpression],
) -> str:
    """Resolve one disclosure's anchor to its drawn parent node ID.

    Priority: the already drawn containing outer module (longest boundary prefix), otherwise the
    anchored course/connector node, otherwise the seeded root. No course node is fabricated.
    """
    root_node_id = f"course:{tree.root.group_id}"
    anchor = part.anchor_occurrence_id
    if anchor is None:
        return root_node_id
    module_prefix = _longest_module_prefix(anchor, drawn_module_occurrence_ids)
    if module_prefix is not None:
        return f"module:{module_prefix}"
    expression = expression_by_occurrence_id.get(anchor)
    if (
        isinstance(expression, CourseRequirement)
        and expression.course_group_id in standalone_group_ids
    ):
        return f"course:{expression.course_group_id}"
    if anchor in connector_occurrence_ids:
        return f"connector:{anchor}"
    return root_node_id


@dataclass(frozen=True)
class _BranchEdge:
    """One pending drawing attachment with its source, endpoint and relationship provenance."""

    source_node_id: str
    target_node_id: str
    expression: PrerequisiteExpression
    occurrence_ids: tuple[str, ...]
    condition_occurrence_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class _DrawingBranch:
    """One surviving drawing branch: its endpoint, inbound provenance and pending attachments.

    `occurrence_ids` are the terminal tree occurrences the branch's endpoint stands for and
    `condition_occurrence_ids` the ordered elided ancestor gates on its inbound relationship. `edges`
    are the endpoint's own outgoing attachments plus every attachment its visible descendants own, so a
    logical connector a same-operator parent folds into itself exposes the descendant edges too.
    `elided_gate_ids` are that connector's own occurrence IDs. A branch with no endpoint contributes
    nothing to the drawing.
    """

    node_id: str | None = None
    expression: PrerequisiteExpression | None = None
    occurrence_ids: tuple[str, ...] = ()
    condition_occurrence_ids: tuple[str, ...] = ()
    edges: tuple[_BranchEdge, ...] = ()
    elided_gate_ids: tuple[str, ...] = ()


_EMPTY_BRANCH = _DrawingBranch()


def _is_logical_connector(expression: PrerequisiteExpression) -> bool:
    """Return whether one expression is an ordinary logical AND/OR connector occurrence."""
    return isinstance(
        expression, (AndRequirement, OrRequirement)
    ) and not is_expanded_course_branch(expression)


def _same_logical_operator(parent: PrerequisiteExpression, child: PrerequisiteExpression) -> bool:
    """Return whether one logical child connector uses its parent connector's own operator."""
    return (isinstance(parent, AndRequirement) and isinstance(child, AndRequirement)) or (
        isinstance(parent, OrRequirement) and isinstance(child, OrRequirement)
    )


def _attachments(source_node_id: str, branch: _DrawingBranch) -> tuple[_BranchEdge, ...]:
    """Return one endpoint's inbound attachment plus its own and descendant outgoing attachments.

    `branch.edges` holds the endpoint's direct attachments and every attachment a surviving
    descendant owns, so this forwards both. A same-operator parent folding the endpoint reparents
    only the direct ones (`_fold_logical_branch`) and leaves descendant attachments untouched.
    """
    if branch.node_id is None or branch.expression is None:
        return ()
    return (
        _BranchEdge(
            source_node_id=source_node_id,
            target_node_id=branch.node_id,
            expression=branch.expression,
            occurrence_ids=branch.occurrence_ids,
            condition_occurrence_ids=branch.condition_occurrence_ids,
        ),
        *branch.edges,
    )


def _fold_logical_branch(source_node_id: str, branch: _DrawingBranch) -> tuple[_BranchEdge, ...]:
    """Return one folded logical connector's attachments reparented onto its surviving parent.

    Only the folded endpoint's own direct outgoing attachments move to the parent: an edge whose
    source is the folded `branch.node_id` owns the child relationship the fold replaces, so it gains
    the folded connector's inbound conditions and elided gate chain. Every other edge belongs to a
    surviving descendant, keeping its source, endpoints, conditions,
    terminals and provenance. This compares attachment ownership. It is not a validation step.
    """
    folded: list[_BranchEdge] = []
    for edge in branch.edges:
        if edge.source_node_id != branch.node_id:
            folded.append(edge)
            continue
        folded.append(
            replace(
                edge,
                source_node_id=source_node_id,
                condition_occurrence_ids=(
                    *branch.condition_occurrence_ids,
                    *branch.elided_gate_ids,
                    *edge.condition_occurrence_ids,
                ),
            )
        )
    return tuple(folded)


def _elide_gate(branch: _DrawingBranch, occurrence_id: str) -> _DrawingBranch:
    """Return one branch with an elided ancestor gate prepended to its inbound condition chain."""
    if branch.node_id is None:
        return branch
    return replace(
        branch,
        condition_occurrence_ids=(occurrence_id, *branch.condition_occurrence_ids),
    )


def project_prerequisite_graph(
    tree: PrerequisiteCalculationTree,
    *,
    node_states: Collection[PrerequisiteGraphNodeState] = (),
) -> PrerequisiteDrawingGraph:
    """Derive the minimized deterministic drawing graph from the sole calculation tree.

    The backend owns drawing compaction, and the tree is the only visibility input. Under active-only
    scope the compiled expression contains the active courses and the retained inactive courses, so
    the projection draws every represented course node. A logical AND/OR occurrence that loses every
    drawn child disappears, one with exactly one drawn branch forwards that branch, and a
    same-operator nesting folds into its surviving parent unless it is a module boundary, a numeric
    constraint, an expanded-course boundary or a manually marked source node. Unary and folded
    branches hold their terminal occurrence IDs and the ordered elided gate IDs, so route lighting and
    provenance are exact. A connector with no children at all (`unresolved`, `opaque_credits`) is
    drawn as a diagnostic leaf, and module/numeric constraints hold their own identity and bounds. A
    module occurrence reached outside another module becomes one module node whose inlined expression
    is traversed only to decide visibility and aggregate course provenance.
    Every emitted node is reachable from the explicitly opened root. `node_states` is supplied by the
    feature command once, so the compiler convenience projection carries empty evaluation facts.
    Written relationships that share endpoints and provenance class become one visible connection
    whose ordered members keep their own terminals, gates and evidence. A consumer lights that
    connection when any single member is independently satisfied.
    """
    module_occurrence_by_id: dict[str, PrerequisiteModuleOccurrence] = {}
    for occurrence in tree.module_occurrences:
        module_occurrence_by_id.setdefault(occurrence.occurrence_id, occurrence)
    occurrence_by_id: dict[str, PrerequisiteNodeOccurrence] = {
        occurrence.occurrence_id: occurrence for occurrence in tree.node_occurrences
    }
    module_nodes: dict[str, PrerequisiteGraphModuleNode] = {}
    summaries_by_group_id = {course.group_id: course for course in tree.courses}
    course_nodes: dict[str, PrerequisiteGraphCourseNode] = {
        tree.root.group_id: PrerequisiteGraphCourseNode(
            node_id=f"course:{tree.root.group_id}",
            action_key=f"course:{tree.root.group_id}",
            course=tree.root,
            is_root=True,
            via_inferred=False,
            via_recommended=False,
            has_official_provenance=False,
            has_inferred_provenance=False,
            is_excluded=tree.root.group_id in tree.excluded_group_ids,
        )
    }
    # Standalone course nodes are emitted only for occurrences reached outside a module boundary. A
    # module-contained occurrence aggregates into this map so a member independently reached
    # outside keeps its one canonical node with the union of both occurrences' flags.
    standalone_group_ids: set[str] = {tree.root.group_id}
    connector_nodes: dict[str, PrerequisiteGraphConnectorNode] = {}
    connection_members: dict[
        tuple[str, str, str, str, str],
        dict[tuple[tuple[str, str, str, str, str, str], tuple[str, ...]], list[str]],
    ] = {}
    relationship_by_member: dict[
        tuple[tuple[str, str, str, str, str, str], tuple[str, ...]],
        PrerequisiteGraphEdgeRelationship,
    ] = {}
    marked_action_keys = frozenset((*tree.completed_node_keys, *tree.excluded_node_keys))

    def bound_action_key(occurrence_id: str) -> str:
        """Return one tree occurrence's authoritative producer-bound source action identity."""
        occurrence = occurrence_by_id.get(occurrence_id)
        if occurrence is None:
            raise ValueError(f"occurrence {occurrence_id!r} has no node occurrence metadata")
        return occurrence.action_key

    def register_relationship(
        source_node_id: str,
        target_node_id: str,
        relationship: PrerequisiteGraphEdgeRelationship,
    ) -> None:
        """Group one relationship member into its visible connection, merging equal members."""
        semantic_key = _edge_semantic_key(
            source_node_id,
            target_node_id,
            relationship.origin,
            relationship.official_kind,
            relationship.inferred_category,
            relationship.inference,
        )
        member_key = (semantic_key, relationship.condition_occurrence_ids)
        connection_members.setdefault(semantic_key[:5], {}).setdefault(member_key, []).extend(
            relationship.occurrence_ids
        )
        relationship_by_member.setdefault(member_key, relationship)

    def build_connections() -> tuple[PrerequisiteGraphEdge, ...]:
        """Emit one drawing connection per endpoint/class with its ordered relationship members."""
        return tuple(
            PrerequisiteGraphEdge(
                source_node_id=connection_key[0],
                target_node_id=connection_key[1],
                relationships=tuple(
                    relationship_by_member[member_key].model_copy(
                        update={"occurrence_ids": tuple(sorted(occurrence_ids))}
                    )
                    for member_key, occurrence_ids in sorted(members.items())
                ),
            )
            for connection_key, members in sorted(connection_members.items())
        )

    def register_edge(edge: _BranchEdge) -> None:
        """Adapt one pending branch attachment to its exact relationship member record."""
        register_relationship(
            edge.source_node_id,
            edge.target_node_id,
            PrerequisiteGraphEdgeRelationship(
                origin=edge.expression.origin,
                official_kind=edge.expression.official_kind,
                inferred_category=edge.expression.inferred_category,
                inference=edge.expression.inference,
                occurrence_ids=edge.occurrence_ids,
                condition_occurrence_ids=edge.condition_occurrence_ids,
            ),
        )

    def course_occurrence(
        expression: CourseRequirement,
        occurrence_id: str,
        *,
        child_inferred: bool,
        child_recommended: bool,
    ) -> str:
        """Aggregate one visible course occurrence into its canonical node and return its node id."""
        group_id = expression.course_group_id
        occurrence_official = expression.origin is PrerequisiteOrigin.OFFICIAL
        occurrence_inferred = expression.origin is PrerequisiteOrigin.INFERRED
        existing = course_nodes.get(group_id)
        if existing is None:
            course_nodes[group_id] = PrerequisiteGraphCourseNode(
                node_id=f"course:{group_id}",
                action_key=f"course:{group_id}",
                course=summaries_by_group_id[group_id],
                is_root=group_id == tree.root.group_id,
                via_inferred=child_inferred,
                via_recommended=child_recommended,
                has_official_provenance=occurrence_official,
                has_inferred_provenance=occurrence_inferred,
                is_excluded=group_id in tree.excluded_group_ids,
            )
        elif child_inferred or child_recommended or occurrence_official or occurrence_inferred:
            course_nodes[group_id] = existing.model_copy(
                update={
                    "via_inferred": existing.via_inferred or child_inferred,
                    "via_recommended": existing.via_recommended or child_recommended,
                    "has_official_provenance": (
                        existing.has_official_provenance or occurrence_official
                    ),
                    "has_inferred_provenance": (
                        existing.has_inferred_provenance or occurrence_inferred
                    ),
                }
            )
        return course_nodes[group_id].node_id

    def synthetic_connector(
        kind: PrerequisiteGraphConnectorKind,
        occurrence_id: str,
        expression: PrerequisiteExpression,
        *,
        action_key: str | None = None,
        referenced_group_id: str | None = None,
        detail: str | None = None,
        member_group_ids: tuple[str, ...] = (),
    ) -> str:
        """Emit one non-calculation drawing connector (internal requirement or numeric option)."""
        node_id = f"connector:{occurrence_id}"
        connector_nodes[occurrence_id] = PrerequisiteGraphConnectorNode(
            node_id=node_id,
            action_key=(action_key if action_key is not None else bound_action_key(occurrence_id)),
            kind=kind,
            origin=expression.origin,
            official_kind=expression.official_kind,
            inferred_category=expression.inferred_category,
            inference=expression.inference,
            referenced_group_id=referenced_group_id,
            detail=detail,
            member_group_ids=member_group_ids,
        )
        return node_id

    def build_course(
        expression: CourseRequirement,
        occurrence_id: str,
        *,
        child_inferred: bool,
        child_recommended: bool,
    ) -> _DrawingBranch:
        """Draw one canonical course occurrence represented in the calculation tree."""
        group_id = expression.course_group_id
        standalone_group_ids.add(group_id)
        return _DrawingBranch(
            node_id=course_occurrence(
                expression,
                occurrence_id,
                child_inferred=child_inferred,
                child_recommended=child_recommended,
            ),
            expression=expression,
            occurrence_ids=(occurrence_id,),
        )

    def build_connector(
        expression: PrerequisiteExpression,
        occurrence_id: str,
        *,
        child_inferred: bool,
        child_recommended: bool,
    ) -> _DrawingBranch:
        """Project one non-course expression with backend-owned logical normalization."""
        children = _connector_children(expression)
        if not children:
            # A childless diagnostic leaf (opaque credits or unresolved) is visible.
            connector_nodes[occurrence_id] = _connector_node(
                expression,
                occurrence_id,
                bound_action_key(occurrence_id),
            )
            return _DrawingBranch(
                node_id=f"connector:{occurrence_id}",
                expression=expression,
                occurrence_ids=(occurrence_id,),
            )
        outcomes = tuple(
            (
                build(
                    child,
                    f"{occurrence_id}.{index}",
                    via_inferred=child_inferred,
                    via_recommended=child_recommended,
                ),
                child,
            )
            for index, child in enumerate(children)
        )
        visible = tuple((branch, child) for branch, child in outcomes if branch.node_id is not None)
        logical = _is_logical_connector(expression)
        marked = logical and bound_action_key(occurrence_id) in marked_action_keys
        if logical and not marked:
            if not visible:
                return _EMPTY_BRANCH
            if len(visible) == 1:
                return _elide_gate(visible[0][0], occurrence_id)
        node_id = f"connector:{occurrence_id}"
        connector_nodes[occurrence_id] = _connector_node(
            expression,
            occurrence_id,
            bound_action_key(occurrence_id),
        )
        flatten = logical and not marked
        edges: list[_BranchEdge] = []
        for branch, _child in visible:
            if (
                flatten
                and branch.elided_gate_ids
                and _same_logical_operator(expression, branch.expression)
            ):
                # Fold one nested same-operator connector into its surviving parent: the folded node
                # is never emitted and its own occurrence joins the elided gate chain. Only the
                # folded endpoint's direct attachments move. Descendant attachments stay owned by
                # their surviving nodes.
                edges.extend(_fold_logical_branch(node_id, branch))
                continue
            edges.extend(_attachments(node_id, branch))
        return _DrawingBranch(
            node_id=node_id,
            expression=expression,
            occurrence_ids=(occurrence_id,),
            edges=tuple(edges),
            elided_gate_ids=(occurrence_id,) if flatten else (),
        )

    def build(
        expression: PrerequisiteExpression,
        occurrence_id: str,
        *,
        via_inferred: bool,
        via_recommended: bool,
    ) -> _DrawingBranch:
        """Project one tree occurrence, eliding only duplicate logical drawing structure."""
        node_inferred = via_inferred or expression.origin is PrerequisiteOrigin.INFERRED
        node_recommended = (
            via_recommended
            or expression.official_kind is OfficialPrerequisiteKind.RECOMMENDED
            or expression.inferred_category is InferredPrerequisiteCategory.RECOMMENDED
        )
        branch_inferred, branch_recommended = _course_path_flags(expression)
        child_inferred = node_inferred or branch_inferred
        child_recommended = node_recommended or branch_recommended
        occurrence = module_occurrence_by_id.get(occurrence_id)
        if occurrence is not None:
            return build_module(
                expression,
                occurrence,
                occurrence_id,
                via_inferred=child_inferred,
                via_recommended=child_recommended,
            )
        if isinstance(expression, ModuleBlockRequirement):
            # A module boundary without a surviving selected identity (for example a hand-built tree)
            # is transparent for drawing, so its child condition tree continues from the same parent.
            return _elide_gate(
                build(
                    expression.child,
                    f"{occurrence_id}.0",
                    via_inferred=child_inferred,
                    via_recommended=child_recommended,
                ),
                occurrence_id,
            )
        if isinstance(expression, CourseRequirement):
            return build_course(
                expression,
                occurrence_id,
                child_inferred=child_inferred,
                child_recommended=child_recommended,
            )
        if is_expanded_course_branch(expression):
            # An expanded course draws its canonical head course and connects that head to its own
            # descendant condition tree, never as an AND connector with head and descendants as
            # siblings.
            head, descendants = expression.children
            head_branch = build(
                head,
                f"{occurrence_id}.0",
                via_inferred=child_inferred,
                via_recommended=child_recommended,
            )
            if head_branch.node_id is None:
                return _EMPTY_BRANCH
            descendants_branch = build(
                descendants,
                f"{occurrence_id}.1",
                via_inferred=child_inferred,
                via_recommended=child_recommended,
            )
            return replace(
                head_branch,
                expression=head,
                edges=_attachments(head_branch.node_id, descendants_branch),
            )
        return build_connector(
            expression,
            occurrence_id,
            child_inferred=child_inferred,
            child_recommended=child_recommended,
        )

    def build_module_body(
        expression: PrerequisiteExpression,
        occurrence_id: str,
        *,
        members: frozenset[str],
        via_inferred: bool,
        via_recommended: bool,
    ) -> _DrawingBranch:
        """Project one module's inlined expression as cards plus external obligations."""
        node_inferred = via_inferred or expression.origin is PrerequisiteOrigin.INFERRED
        node_recommended = (
            via_recommended
            or expression.official_kind is OfficialPrerequisiteKind.RECOMMENDED
            or expression.inferred_category is InferredPrerequisiteCategory.RECOMMENDED
        )
        branch_inferred, branch_recommended = _course_path_flags(expression)
        child_inferred = node_inferred or branch_inferred
        child_recommended = node_recommended or branch_recommended
        if isinstance(expression, ModuleBlockRequirement):
            return _elide_gate(
                build_module_body(
                    expression.child,
                    f"{occurrence_id}.0",
                    members=members,
                    via_inferred=child_inferred,
                    via_recommended=child_recommended,
                ),
                occurrence_id,
            )
        if is_expanded_course_branch(expression):
            head, descendants = expression.children
            head_occurrence_id = f"{occurrence_id}.0"
            if head.course_group_id in members:
                # The member head is a card: suppress its link but continue its own prerequisites.
                course_occurrence(
                    head,
                    head_occurrence_id,
                    child_inferred=child_inferred,
                    child_recommended=child_recommended,
                )
                return _elide_gate(
                    _elide_gate(
                        build_module_body(
                            descendants,
                            f"{occurrence_id}.1",
                            members=members,
                            via_inferred=child_inferred,
                            via_recommended=child_recommended,
                        ),
                        head_occurrence_id,
                    ),
                    occurrence_id,
                )
            # An outside head switches to ordinary projection, exposing its whole real condition tree.
            branch = build(
                expression,
                occurrence_id,
                via_inferred=child_inferred,
                via_recommended=child_recommended,
            )
            if branch.node_id is None:
                return _EMPTY_BRANCH
            return replace(branch, expression=head)
        if isinstance(expression, CourseRequirement):
            if expression.course_group_id in members:
                course_occurrence(
                    expression,
                    occurrence_id,
                    child_inferred=child_inferred,
                    child_recommended=child_recommended,
                )
                return _EMPTY_BRANCH
            return build(
                expression,
                occurrence_id,
                via_inferred=child_inferred,
                via_recommended=child_recommended,
            )
        children = _connector_children(expression)
        if not children:
            # A childless diagnostic leaf (opaque credits or unresolved) is visible.
            connector_nodes[occurrence_id] = _connector_node(
                expression,
                occurrence_id,
                bound_action_key(occurrence_id),
            )
            return _DrawingBranch(
                node_id=f"connector:{occurrence_id}",
                expression=expression,
                occurrence_ids=(occurrence_id,),
            )
        outcomes = tuple(
            (
                build_module_body(
                    child,
                    f"{occurrence_id}.{index}",
                    members=members,
                    via_inferred=child_inferred,
                    via_recommended=child_recommended,
                ),
                child,
                f"{occurrence_id}.{index}",
            )
            for index, child in enumerate(children)
        )
        visible = tuple(outcome for outcome in outcomes if outcome[0].node_id is not None)
        if not visible:
            # A wholly internal choice or numeric position contributes only member cards, so it is
            # compact inside the module node instead of drawing a connector.
            return _EMPTY_BRANCH
        conjunction = isinstance(expression, AndRequirement)
        marked = conjunction and bound_action_key(occurrence_id) in marked_action_keys
        if conjunction and not marked and len(visible) == 1:
            # A mandatory chain elides its internal members to cards and collapses to its one real
            # external obligation. The conjunction has no choice to preserve.
            return _elide_gate(visible[0][0], occurrence_id)
        node_id = f"connector:{occurrence_id}"
        connector_nodes[occurrence_id] = _connector_node(
            expression,
            occurrence_id,
            bound_action_key(occurrence_id),
        )
        flatten = conjunction and not marked
        edges: list[_BranchEdge] = []
        for branch, _child, _child_occurrence_id in visible:
            if (
                flatten
                and branch.elided_gate_ids
                and _same_logical_operator(expression, branch.expression)
            ):
                # Fold one nested same-operator connector as above: only the folded endpoint's direct
                # attachments move, so course-owned descendant attachments keep their exact parentage.
                edges.extend(_fold_logical_branch(node_id, branch))
                continue
            edges.extend(_attachments(node_id, branch))
        if not conjunction:
            # A source choice or numeric position with external content keeps every option. An
            # internal-only option with represented members draws a childless INTERNAL_REQUIREMENT
            # connector at its actual source occurrence, so a visible internal alternative is never
            # collapsed into one mandatory external edge. An option with no represented member
            # contributes no drawing node at all.
            for branch, child, child_occurrence_id in outcomes:
                if branch.node_id is not None:
                    continue
                member_ids = tuple(sorted(set(_iter_module_member_group_ids(child))))
                if not member_ids:
                    continue
                option_id = synthetic_connector(
                    PrerequisiteGraphConnectorKind.INTERNAL_REQUIREMENT,
                    child_occurrence_id,
                    child,
                    member_group_ids=member_ids,
                )
                edges.append(
                    _BranchEdge(
                        source_node_id=node_id,
                        target_node_id=option_id,
                        expression=child,
                        occurrence_ids=(child_occurrence_id,),
                        condition_occurrence_ids=(child_occurrence_id,),
                    )
                )
        return _DrawingBranch(
            node_id=node_id,
            expression=expression,
            occurrence_ids=(occurrence_id,),
            edges=tuple(edges),
            elided_gate_ids=(occurrence_id,) if flatten else (),
        )

    def build_module(
        expression: PrerequisiteExpression,
        occurrence: PrerequisiteModuleOccurrence,
        occurrence_id: str,
        *,
        via_inferred: bool,
        via_recommended: bool,
    ) -> _DrawingBranch:
        """Emit one module node with its cards plus any external obligation it must satisfy."""
        members = frozenset(occurrence.member_group_ids)
        if isinstance(expression, ModuleBlockRequirement):
            body = expression.child
            body_occurrence_id = f"{occurrence_id}.0"
        else:
            body = expression
            body_occurrence_id = occurrence_id
        body_branch = build_module_body(
            body,
            body_occurrence_id,
            members=members,
            via_inferred=via_inferred,
            via_recommended=via_recommended,
        )
        member_courses = tuple(
            summaries_by_group_id[group_id] for group_id in occurrence.member_group_ids
        )
        # The module node is always retained even when it has no member card, so exclusions,
        # shortfalls and impossible internal requirements attach to their actual containing module.
        node_id = f"module:{occurrence_id}"
        module_nodes[occurrence_id] = PrerequisiteGraphModuleNode(
            node_id=node_id,
            occurrence_id=occurrence_id,
            action_key=f"module:{occurrence.module.group_id}",
            module=occurrence.module,
            official_kind=occurrence.official_kind,
            member_courses=member_courses,
            credits_min=occurrence.credits_min,
            credits_max=occurrence.credits_max,
        )
        return _DrawingBranch(
            node_id=node_id,
            expression=expression,
            occurrence_ids=(occurrence_id,),
            edges=_attachments(node_id, body_branch),
        )

    if tree.requirements is not None:
        root_branch = build(tree.requirements, "r", via_inferred=False, via_recommended=False)
        for edge in _attachments(f"course:{tree.root.group_id}", root_branch):
            register_edge(edge)

    # The drawing-only course-card marker is derived once from each node's final aggregated
    # provenance, after every visible occurrence has been visited, so an official occurrence
    # encountered after an inferred one always wins. The root is never its own prerequisite and is
    # false even when a synthetic self occurrence touched its raw provenance.
    course_nodes = {
        group_id: node.model_copy(
            update={
                "display_as_inferred": (
                    not node.is_root
                    and node.has_inferred_provenance
                    and not node.has_official_provenance
                )
            }
        )
        for group_id, node in course_nodes.items()
    }

    # The visible connections are emitted before connector endpoint pruning: only endpoints a
    # surviving root relationship actually references keep their connector node.
    base_connections = build_connections()

    # A connector reached only by a folded or elided logical branch is provisional and never emitted:
    # every remaining drawing node is an edge endpoint of the surviving root relationships.
    referenced_node_ids = {
        endpoint
        for edge in base_connections
        for endpoint in (edge.source_node_id, edge.target_node_id)
    }
    connector_nodes = {
        occurrence_id: node
        for occurrence_id, node in connector_nodes.items()
        if node.node_id in referenced_node_ids
    }

    # Each retained tree disclosure becomes one explicit drawing annotation node referencing the
    # tree's descriptive record, plus one annotation relationship from its resolved drawn parent. A
    # dropped missing-substitution record is in `tree.ignored_parts` for the reasons panel but
    # draws no annotation, because it explains a removed unavailable alternative rather than an
    # obligation. Annotations register through the same connection accumulator as ordinary branches.
    expression_by_occurrence_id = (
        dict(_iter_expression_occurrences(tree.requirements))
        if tree.requirements is not None
        else {}
    )
    drawn_module_occurrence_ids = frozenset(module_nodes)
    connector_occurrence_ids = frozenset(connector_nodes)
    ignored_nodes: list[PrerequisiteGraphIgnoredNode] = []
    for part in tree.ignored_parts:
        if part.kind is PrerequisiteIgnoredPartKind.MISSING_SUBSTITUTION_COURSE:
            continue
        parent_node_id = _ignored_anchor_parent(
            tree,
            part,
            drawn_module_occurrence_ids=drawn_module_occurrence_ids,
            standalone_group_ids=frozenset(standalone_group_ids),
            connector_occurrence_ids=connector_occurrence_ids,
            expression_by_occurrence_id=expression_by_occurrence_id,
        )
        if part.module is not None and part.kind in (
            PrerequisiteIgnoredPartKind.UNEXPANDABLE_CONTENT,
            PrerequisiteIgnoredPartKind.FREE_CHOICE,
        ):
            # A disappeared selected module keeps one childless display module node. Its disclosure
            # hangs from that module rather than from the generic resolved parent. The node serves
            # display only and stays out of the calculation occurrence index.
            display_module_id = f"module:{part.part_id}"
            module_nodes[part.part_id] = PrerequisiteGraphModuleNode(
                node_id=display_module_id,
                occurrence_id=part.part_id,
                action_key=f"module:{part.module.group_id}",
                module=part.module,
                official_kind=part.official_kind,
                member_courses=(),
            )
            register_relationship(
                parent_node_id,
                display_module_id,
                PrerequisiteGraphEdgeRelationship(
                    origin=PrerequisiteOrigin.OFFICIAL,
                    official_kind=part.official_kind,
                    inferred_category=None,
                    inference=None,
                    occurrence_ids=(part.part_id,),
                ),
            )
            parent_node_id = display_module_id
        ignored_nodes.append(
            PrerequisiteGraphIgnoredNode(
                node_id=part.part_id, part_id=part.part_id, action_key=part.action_key
            )
        )
        register_relationship(
            parent_node_id,
            part.part_id,
            PrerequisiteGraphEdgeRelationship(
                origin=PrerequisiteOrigin.OFFICIAL,
                official_kind=part.official_kind,
                inferred_category=None,
                inference=None,
                occurrence_ids=(part.part_id,),
            ),
        )

    edges = tuple(sorted(build_connections(), key=_edge_sort_key))
    return PrerequisiteDrawingGraph(
        course_nodes=tuple(
            sorted(
                (
                    node
                    for group_id, node in course_nodes.items()
                    if group_id in standalone_group_ids
                ),
                key=lambda node: node.node_id,
            )
        ),
        connector_nodes=tuple(sorted(connector_nodes.values(), key=lambda node: node.node_id)),
        edges=edges,
        module_nodes=tuple(sorted(module_nodes.values(), key=lambda node: node.node_id)),
        ignored_nodes=tuple(ignored_nodes),
        node_states=tuple(sorted(node_states, key=lambda state: state.action_key)),
    )
