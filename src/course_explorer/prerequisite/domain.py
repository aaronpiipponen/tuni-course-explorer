"""Product-neutral prerequisite expression and inferred-set contracts.

This module owns the one closed vocabulary official-compilation, inferred publication,
satisfaction, discovery coverage, and graph projection share: strict frozen Pydantic nodes with
official/inferred/composed provenance, explicit composed AND/OR roles, an explicit
per-occurrence inferred required/recommended category, and the current inferred-set
publication/read DTOs. It keeps official university facts separate from
derived inferred claims.
"""

from __future__ import annotations

from collections.abc import Collection
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal, Protocol, Self
from uuid import UUID

from pydantic import (
    Field,
    TypeAdapter,
    field_serializer,
    field_validator,
    model_validator,
)

from course_explorer.enums import (
    InferredCoverageState,
    InferredProducerKind,
)
from course_explorer.prerequisite._helpers import (
    _nonblank,
    _PrerequisiteModel,
    _unique_ids,
    _validate_origin_shape,
)
from course_explorer.validation import require_aware, require_sha256


def _decimal_json(value: Decimal) -> str:
    """Encode a Decimal as canonical plain fixed-point text without binary float.

    Trailing fractional zeroes are removed and canonical zero is `"0"`, so `Decimal("0.90")`
    becomes `"0.9"` and `Decimal("5.00")` becomes `"5"`. Parsing those strings back yields an
    equal Decimal.
    """
    if value == 0:
        return "0"
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


class PrerequisiteOrigin(StrEnum):
    """Whether an expression node is official fact, inferred claim, or a composed join."""

    OFFICIAL = "official"
    INFERRED = "inferred"
    COMPOSED = "composed"


class OfficialPrerequisiteKind(StrEnum):
    """Official provenance category of one expression node."""

    COMPULSORY = "compulsory"
    RECOMMENDED = "recommended"
    MODULE_RULE = "module_rule"
    SUBSTITUTION = "substitution"


class InferredPrerequisiteCategory(StrEnum):
    """Explicit required/recommended category of one inferred expression occurrence.

    The category is occurrence-local provenance, distinct from the official
    `OfficialPrerequisiteKind`. Every inferred occurrence declares exactly one value so an inferred
    recommendation is visible and counted only under both toggles while an inferred required
    prerequisite needs only inference enabled.
    """

    REQUIRED = "required"
    RECOMMENDED = "recommended"


class ComposedAndRole(StrEnum):
    """Compiler-owned semantic role of one composed AND expression."""

    LOGICAL = "logical"
    EXPANDED_COURSE = "expanded_course"


class ComposedOrRole(StrEnum):
    """Compiler-owned semantic role of one composed OR expression."""

    LOGICAL = "logical"
    COURSE_ALTERNATIVES = "course_alternatives"


class InferenceEvidenceKind(StrEnum):
    """Opaque evidence family referenced by an inferred node.

    The only family is the expression proposal an inference target pass produces.
    """

    EXPRESSION_PROPOSAL = "expression_proposal"


class UnresolvedPrerequisiteReason(StrEnum):
    """Explicit reason an official requirement could not resolve to course leaves."""

    MISSING_COURSE = "missing_course"
    MISSING_MODULE = "missing_module"
    AMBIGUOUS_MODULE_VERSION = "ambiguous_module_version"
    MALFORMED_RULE = "malformed_rule"
    COURSE_CYCLE = "course_cycle"
    MODULE_CYCLE = "module_cycle"
    UNKNOWN_COURSE_COUNT = "unknown_course_count"
    UNKNOWN_CREDIT_EXTENT = "unknown_credit_extent"


class InferredPublicationAction(StrEnum):
    """Result of one repository publication attempt."""

    CREATED = "created"
    REPLACED = "replaced"
    UNCHANGED = "unchanged"


class InferredReadState(StrEnum):
    """Availability of a current inferred set for one canonical target."""

    UNAVAILABLE = "unavailable"
    STALE_ACTIVITY_CONTEXT = "stale_activity_context"
    CURRENT = "current"


_MODULE_OFFICIAL_KINDS = frozenset(
    {
        OfficialPrerequisiteKind.COMPULSORY,
        OfficialPrerequisiteKind.RECOMMENDED,
        OfficialPrerequisiteKind.MODULE_RULE,
    }
)


class InferenceEvidenceReference(_PrerequisiteModel):
    """One typed opaque reference to evidence owned by the inference stage."""

    kind: InferenceEvidenceKind
    reference_id: str

    @field_validator("reference_id")
    @classmethod
    def reject_blank_reference(cls, value: str) -> str:
        """Require a nonblank opaque evidence identity."""
        return _nonblank(value, "evidence reference_id")


class InferenceNodeMetadata(_PrerequisiteModel):
    """Visible evidence metadata attached to one inferred expression node.

    Confidence is retained provenance: no display, filter, or calculation consumes the value, and
    graph and path services apply no second confidence threshold after publication.
    """

    confidence: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    requirement_ids: tuple[str, ...] = ()
    evidence: tuple[InferenceEvidenceReference, ...] = ()

    @field_validator("requirement_ids")
    @classmethod
    def reject_blank_or_duplicate_requirements(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Require distinct nonblank requirement identities."""
        for requirement_id in value:
            _nonblank(requirement_id, "requirement_id")
        return _unique_ids(value, "requirement IDs")

    @field_validator("evidence")
    @classmethod
    def reject_duplicate_evidence(
        cls, value: tuple[InferenceEvidenceReference, ...]
    ) -> tuple[InferenceEvidenceReference, ...]:
        """Require distinct evidence references within one metadata object."""
        seen: set[tuple[InferenceEvidenceKind, str]] = set()
        for reference in value:
            key = (reference.kind, reference.reference_id)
            if key in seen:
                raise ValueError("evidence references must be unique within one metadata object")
            seen.add(key)
        return value

    @field_serializer("confidence")
    def serialize_confidence(self, value: Decimal) -> str:
        """Encode confidence as canonical fixed-point text."""
        return _decimal_json(value)


class _RequirementBase(_PrerequisiteModel):
    """Shared provenance base for every concrete prerequisite expression node kind.

    `inferred_category` is the explicit required/recommended category of one inferred occurrence.
    It is forbidden for official and composed nodes, always serialized (as `null` when absent), and
    never defaulted for inferred nodes: a missing category is a validation failure rather than an
    implicit required classification.
    """

    origin: PrerequisiteOrigin
    official_kind: OfficialPrerequisiteKind | None = None
    inferred_category: InferredPrerequisiteCategory | None = None
    inference: InferenceNodeMetadata | None = None

    @model_validator(mode="after")
    def validate_provenance_shape(self) -> Self:
        """Enforce exactly one provenance shape consistent with the declared origin."""
        _validate_origin_shape(
            self.origin, self.official_kind, self.inferred_category, self.inference
        )
        return self


def _require_official(
    node: _RequirementBase,
    *,
    allowed_kinds: frozenset[OfficialPrerequisiteKind] | None = None,
) -> None:
    """Reject a non-official origin, and any kind outside an optional allowed set.

    This is a local expression boundary: the official-only node kinds pass the one set they accept,
    while the common provenance shape already pins the exhaustive origin/kind cardinality.
    """
    if node.origin is not PrerequisiteOrigin.OFFICIAL:
        raise ValueError(f"{type(node).__name__} must be official")
    if allowed_kinds is not None and node.official_kind not in allowed_kinds:
        raise ValueError(f"{type(node).__name__} does not allow official_kind {node.official_kind}")


class CourseRequirement(_RequirementBase):
    """One canonical course leaf, official or inferred."""

    type: Literal["course"]
    course_group_id: str

    @field_validator("course_group_id")
    @classmethod
    def reject_blank_group(cls, value: str) -> str:
        """Require a nonblank canonical course identity."""
        return _nonblank(value, "course_group_id")

    @model_validator(mode="after")
    def validate_kind(self) -> Self:
        """Allow official (any kind) or inferred course leaves only."""
        if self.origin is PrerequisiteOrigin.COMPOSED:
            raise ValueError("CourseRequirement does not support composed origin")
        return self


class ModuleRequirement(_RequirementBase):
    """One canonical module leaf. Official-only.

    The compiler consumes it at compile time and inlines the module's rules as the authoritative
    calculation structure, so the compiled tree carries the inlined rule in its place. The selected module's
    identity is recorded beside that inlined expression as request-local display metadata, so the
    drawing graph can present the module or degree as one node with its official member cards
    without adding a separate expression node kind or a stored payload field.
    """

    type: Literal["module"]
    module_group_id: str

    @field_validator("module_group_id")
    @classmethod
    def reject_blank_group(cls, value: str) -> str:
        """Require a nonblank canonical module identity."""
        return _nonblank(value, "module_group_id")

    @model_validator(mode="after")
    def validate_kind(self) -> Self:
        """Allow official compulsory/recommended/module-rule module references only."""
        _require_official(self, allowed_kinds=_MODULE_OFFICIAL_KINDS)
        return self


class OpaqueCreditRequirement(_RequirementBase):
    """One compiled childless opaque obligation costing its real source credit minimum.

    It represents an official module or credit block whose contents cannot be expanded into course
    leaves while the source supplies a credit requirement. The calculation charges its
    `credits_min` once and `credits_max` is descriptive.
    It is official-only and never storable in the inferred store.
    """

    type: Literal["opaque_credits"]
    work_key: str
    credits_min: Decimal = Field(ge=0)
    credits_max: Decimal | None = Field(default=None, ge=0)

    @field_validator("work_key")
    @classmethod
    def reject_blank_work_key(cls, value: str) -> str:
        """Require a nonblank request-local opaque work identity."""
        return _nonblank(value, "work_key")

    @model_validator(mode="after")
    def validate_kind(self) -> Self:
        """Allow official module-rule provenance only, through the shared boundary."""
        _require_official(self, allowed_kinds=frozenset({OfficialPrerequisiteKind.MODULE_RULE}))
        return self

    @field_serializer("credits_min")
    def serialize_credits_min(self, value: Decimal) -> str:
        """Encode the credit minimum as canonical fixed-point text."""
        return _decimal_json(value)

    @field_serializer("credits_max")
    def serialize_credits_max(self, value: Decimal | None) -> str | None:
        """Encode the credit maximum as canonical fixed-point text, or null."""
        return None if value is None else _decimal_json(value)


class ModuleBlockRequirement(_RequirementBase):
    """One compiled module boundary wrapping the inlined rule of a module reference.

    The wrapper makes the selected module an actual calculation boundary so node actions can address
    it without turning the module into a stored expression kind. Its `child` keeps its own
    provenance. The boundary never relabels it. It is official-only and never storable in the
    inferred store.
    """

    type: Literal["module_block"]
    module_group_id: str
    child: PrerequisiteExpression

    @field_validator("module_group_id")
    @classmethod
    def reject_blank_group(cls, value: str) -> str:
        """Require a nonblank canonical module identity."""
        return _nonblank(value, "module_group_id")

    @model_validator(mode="after")
    def validate_kind(self) -> Self:
        """Allow official compulsory/recommended/module-rule module references only."""
        _require_official(self, allowed_kinds=_MODULE_OFFICIAL_KINDS)
        return self


class AndRequirement(_RequirementBase):
    """Ordered conjunction of at least one prerequisite expression.

    `composed_role` is the compiler-owned semantic discriminator for a composed conjunction:
    `LOGICAL` is an ordinary join of independently required contributions, while
    `EXPANDED_COURSE` marks the exact wrapper that expands one active required course into its
    head course leaf plus recursively compiled descendants. It is a field discriminator, not a
    separate `PrerequisiteExpression` node kind, and is omitted from serialized output when `None`
    so official and inferred AND payloads serialize byte-for-byte identically.
    """

    type: Literal["and"]
    composed_role: ComposedAndRole | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    children: tuple[PrerequisiteExpression, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_kind(self) -> Self:
        """Allow official (any kind), inferred, or composed conjunctions with an explicit role."""
        if self.origin is PrerequisiteOrigin.COMPOSED:
            if self.composed_role is None:
                raise ValueError("composed AndRequirement requires composed_role")
        elif self.composed_role is not None:
            raise ValueError("non-composed AndRequirement forbids composed_role")
        if self.composed_role is ComposedAndRole.EXPANDED_COURSE and not (
            len(self.children) == 2 and isinstance(self.children[0], CourseRequirement)
        ):
            raise ValueError(
                "expanded-course AndRequirement requires exactly two children with a "
                "CourseRequirement head"
            )
        return self


class OrRequirement(_RequirementBase):
    """Ordered disjunction of at least one prerequisite expression.

    `composed_role` is the compiler-owned semantic discriminator for a composed disjunction:
    `LOGICAL` is an ordinary caller-constructed mixed logical OR, while `COURSE_ALTERNATIVES`
    marks the compiler's exact effective course-alternative OR whose first child is the
    represented course branch and whose following children are official substitution or inferred
    equivalent-member alternatives. It is a field discriminator, not a separate
    `PrerequisiteExpression` node kind, and is omitted from serialized output when `None` so
    official and inferred OR payloads (and their payload hashes) serialize byte-for-byte identically.
    """

    type: Literal["or"]
    composed_role: ComposedOrRole | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    children: tuple[PrerequisiteExpression, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_kind(self) -> Self:
        """Allow official (any kind), inferred, or composed disjunctions with an explicit role."""
        if self.origin is PrerequisiteOrigin.COMPOSED:
            if self.composed_role is None:
                raise ValueError("composed OrRequirement requires composed_role")
        elif self.composed_role is not None:
            raise ValueError("non-composed OrRequirement forbids composed_role")
        return self


class CardinalityRequirement(_RequirementBase):
    """Official k-of-n requirement over ordered course-leaf children.

    An emptied child tuple is valid: dropped or ignored source positions may leave a surviving
    positive minimum that the real fold reports as no-solution, and an above-count maximum is
    unreachable. Only the nonnegative/order/provenance constraints stay at this boundary. Source
    malformation is rejected by the compiler, not by a child-count bound check.
    """

    type: Literal["cardinality"]
    require_min: int = Field(ge=0)
    require_max: int | None = Field(default=None, ge=0)
    children: tuple[PrerequisiteExpression, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def validate_bounds(self) -> Self:
        """Require official module-rule provenance and ordered bounds only."""
        _require_official(self, allowed_kinds=frozenset({OfficialPrerequisiteKind.MODULE_RULE}))
        if self.require_max is not None and self.require_min > self.require_max:
            raise ValueError("cardinality require_min must not exceed require_max")
        return self


class CreditRequirement(_RequirementBase):
    """Official credit-range requirement over one ordered child expression."""

    type: Literal["credits"]
    credits_min: Decimal = Field(ge=0)
    credits_max: Decimal | None = Field(default=None, ge=0)
    child: PrerequisiteExpression

    @model_validator(mode="after")
    def validate_bounds(self) -> Self:
        """Require official module-rule provenance and ordered credit bounds."""
        _require_official(self, allowed_kinds=frozenset({OfficialPrerequisiteKind.MODULE_RULE}))
        if self.credits_max is not None and self.credits_min > self.credits_max:
            raise ValueError("credits_min must not exceed credits_max")
        return self

    @field_serializer("credits_min")
    def serialize_credits_min(self, value: Decimal) -> str:
        """Encode the credit minimum as canonical fixed-point text."""
        return _decimal_json(value)

    @field_serializer("credits_max")
    def serialize_credits_max(self, value: Decimal | None) -> str | None:
        """Encode the credit maximum as canonical fixed-point text, or null."""
        return None if value is None else _decimal_json(value)


class CourseCountRequirement(_RequirementBase):
    """Official course-count requirement over one ordered child expression."""

    type: Literal["course_count"]
    count_min: int = Field(ge=0)
    count_max: int | None = Field(default=None, ge=0)
    child: PrerequisiteExpression

    @model_validator(mode="after")
    def validate_bounds(self) -> Self:
        """Require official module-rule provenance and ordered count bounds."""
        _require_official(self, allowed_kinds=frozenset({OfficialPrerequisiteKind.MODULE_RULE}))
        if self.count_max is not None and self.count_min > self.count_max:
            raise ValueError("count_min must not exceed count_max")
        return self


class UnresolvedRequirement(_RequirementBase):
    """Official requirement that cannot resolve to course leaves without more context."""

    type: Literal["unresolved"]
    reason: UnresolvedPrerequisiteReason
    referenced_group_id: str | None = None
    detail: str | None = None

    @field_validator("referenced_group_id", "detail")
    @classmethod
    def reject_blank_optional_text(cls, value: str | None) -> str | None:
        """Reject a provided-but-blank diagnostic field."""
        if value is not None:
            _nonblank(value, "unresolved diagnostic text")
        return value

    @model_validator(mode="after")
    def validate_kind(self) -> Self:
        """Allow official (any kind) unresolved requirements only."""
        _require_official(self)
        return self


PrerequisiteExpression = Annotated[
    CourseRequirement
    | ModuleRequirement
    | OpaqueCreditRequirement
    | ModuleBlockRequirement
    | AndRequirement
    | OrRequirement
    | CardinalityRequirement
    | CreditRequirement
    | CourseCountRequirement
    | UnresolvedRequirement,
    Field(discriminator="type"),
]

AndRequirement.model_rebuild()
OrRequirement.model_rebuild()
CardinalityRequirement.model_rebuild()
CreditRequirement.model_rebuild()
CourseCountRequirement.model_rebuild()
UnresolvedRequirement.model_rebuild()
ModuleBlockRequirement.model_rebuild()

_EXPRESSION_ADAPTER: TypeAdapter[PrerequisiteExpression] = TypeAdapter(PrerequisiteExpression)


def parse_prerequisite_expression(value: object) -> PrerequisiteExpression:
    """Strictly validate one persisted or submitted expression payload."""
    return _EXPRESSION_ADAPTER.validate_python(value)


def dump_prerequisite_expression(expression: PrerequisiteExpression) -> dict[str, object]:
    """Serialize one expression with the canonical Decimal string encoding."""
    dumped = _EXPRESSION_ADAPTER.dump_python(expression, mode="json")
    if not isinstance(dumped, dict):
        raise ValueError("prerequisite expression must serialize to a JSON object")
    return dumped


def expression_course_leaf_group_ids(expression: PrerequisiteExpression | None) -> set[str]:
    """Return the distinct canonical course-leaf IDs one expression references."""
    leaves: set[str] = set()
    if expression is None:
        return leaves
    stack: list[PrerequisiteExpression] = [expression]
    while stack:
        node = stack.pop()
        if isinstance(node, CourseRequirement):
            leaves.add(node.course_group_id)
        elif isinstance(node, (AndRequirement, OrRequirement, CardinalityRequirement)):
            stack.extend(node.children)
        elif isinstance(node, (CreditRequirement, CourseCountRequirement)):
            stack.append(node.child)
        elif isinstance(node, ModuleBlockRequirement):
            stack.append(node.child)
    return leaves


class PrerequisiteNodeProblem(_PrerequisiteModel):
    """One located prerequisite node failure with an explainable reason.

    `node_id` is the drawn box a reader sees, `support_id` the scoped calculation support that
    failed and `fact_id` its provenance fact when one applies. `state` is the local outcome
    (`no_solution`, `unresolved`, or `shortfall`). `reason` and `detail` stay short and factual.
    A synthetic root failure has null support/fact and the root course node ID.
    """

    node_id: str
    support_id: str | None = None
    fact_id: str | None = None
    state: Literal["no_solution", "unresolved", "shortfall"]
    reason: str
    referenced_group_id: str | None = None
    detail: str | None = None

    @field_validator("node_id", "reason")
    @classmethod
    def reject_blank_problem_text(cls, value: str) -> str:
        """Require nonblank located identity and reason text."""
        return _nonblank(value, "node problem text")

    @field_validator("support_id", "fact_id", "referenced_group_id", "detail")
    @classmethod
    def reject_blank_optional_text(cls, value: str | None) -> str | None:
        """Reject a provided-but-blank optional diagnostic field."""
        if value is not None:
            _nonblank(value, "node problem optional text")
        return value


class InferredSetCoverage(_PrerequisiteModel):
    """Ordered source-count coverage of one inferred publication attempt."""

    eligible_source_count: int = Field(ge=0)
    processed_source_count: int = Field(ge=0)
    accepted_source_count: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_order(self) -> Self:
        """Require accepted <= processed <= eligible."""
        if self.accepted_source_count > self.processed_source_count:
            raise ValueError("accepted_source_count must not exceed processed_source_count")
        if self.processed_source_count > self.eligible_source_count:
            raise ValueError("processed_source_count must not exceed eligible_source_count")
        return self


class _InferredSetFields(_PrerequisiteModel):
    """Shared field and validation policy for published and stored current inferred sets."""

    target_group_id: str
    activity_as_of_academic_year_start: int = Field(gt=0)
    activity_window_years: int = Field(gt=0)
    producer_kind: InferredProducerKind
    producer_name: str
    producer_version: str
    input_hash: str
    coverage_state: InferredCoverageState
    coverage: InferredSetCoverage
    expression: PrerequisiteExpression | None
    generated_at: datetime

    @field_validator("target_group_id")
    @classmethod
    def reject_blank_target(cls, value: str) -> str:
        """Require a nonblank canonical target identity."""
        return _nonblank(value, "target_group_id")

    @field_validator("producer_name", "producer_version")
    @classmethod
    def reject_blank_producer(cls, value: str) -> str:
        """Require nonblank producer identity fields."""
        return _nonblank(value, "producer field")

    @field_validator("input_hash")
    @classmethod
    def require_input_sha256(cls, value: str) -> str:
        """Require a lowercase 64-character SHA-256 input hash."""
        return require_sha256(value, "input_hash")

    @field_validator("generated_at")
    @classmethod
    def require_aware_generated_at(cls, value: datetime) -> datetime:
        """Require a timezone-aware generation timestamp."""
        return require_aware(value, "generated_at")

    @model_validator(mode="after")
    def validate_coverage_state(self) -> Self:
        """Tie partial/complete state to the processed/eligible source counts."""
        if self.coverage_state is InferredCoverageState.PARTIAL:
            if self.coverage.processed_source_count >= self.coverage.eligible_source_count:
                raise ValueError("partial coverage requires processed < eligible")
        elif self.coverage.processed_source_count != self.coverage.eligible_source_count:
            raise ValueError("complete coverage requires processed == eligible")
        return self


class InferredSetPublication(_InferredSetFields):
    """One requested atomic publication of a current inferred set for an active target."""


class CurrentInferredSet(_InferredSetFields):
    """One stored current inferred set with its payload identity and publication time."""

    set_id: UUID
    payload_hash: str
    published_at: datetime

    @field_validator("payload_hash")
    @classmethod
    def require_payload_sha256(cls, value: str) -> str:
        """Require a lowercase 64-character SHA-256 payload hash."""
        return require_sha256(value, "payload_hash")

    @field_validator("published_at")
    @classmethod
    def require_aware_published_at(cls, value: datetime) -> datetime:
        """Require a timezone-aware publication timestamp."""
        return require_aware(value, "published_at")


class InferredSetPublicationResult(_PrerequisiteModel):
    """Outcome of one publication attempt with the resulting current set."""

    action: InferredPublicationAction
    current_set: CurrentInferredSet


class InferredSetReadResult(_PrerequisiteModel):
    """Availability of a current inferred set, exposing only state-relevant fields."""

    target_group_id: str
    state: InferredReadState
    current_set: CurrentInferredSet | None = None
    stored_activity_as_of_academic_year_start: int | None = None
    stored_activity_window_years: int | None = None


class InferredActivityReconciliation(_PrerequisiteModel):
    """Sorted canonical targets whose final inferred sets an activity pass removed."""

    removed_target_group_ids: tuple[str, ...]


class EquivalenceGroupMember(_PrerequisiteModel):
    """One canonical course member of one target-independent equivalence group.

    Only canonical identity plus the publication-time activity context are carried. Course
    `is_active`, names, and credits stay owned by the curriculum read seam, so activity
    reconciliation always compares against the live canonical course row.
    """

    course_group_id: str
    activity_as_of_academic_year_start: int = Field(gt=0)
    activity_window_years: int = Field(gt=0)

    @field_validator("course_group_id")
    @classmethod
    def reject_blank_member(cls, value: str) -> str:
        """Require a nonblank canonical course identity."""
        return _nonblank(value, "member course_group_id")


class _EquivalenceGroupFields(_PrerequisiteModel):
    """Shared field and validation policy for published and stored current groups.

    Membership is symmetric only inside one exact group: it is sorted and unique so one
    semantic payload has one spelling, and no merge, transitive, or
    ordering relation exists between groups. `group_id` is the caller-supplied stable identity that
    replacement and reconciliation preserve.
    """

    group_id: UUID
    members: tuple[EquivalenceGroupMember, ...] = Field(min_length=2)
    producer_kind: InferredProducerKind
    producer_name: str
    producer_version: str
    input_hash: str
    inference: InferenceNodeMetadata
    generated_at: datetime

    @field_validator("members")
    @classmethod
    def require_sorted_unique_members(
        cls, value: tuple[EquivalenceGroupMember, ...]
    ) -> tuple[EquivalenceGroupMember, ...]:
        """Require members unique and sorted by canonical course identity."""
        _unique_ids(
            tuple(member.course_group_id for member in value),
            "equivalence group members",
            sorted_required=True,
        )
        return value

    @field_validator("producer_name", "producer_version")
    @classmethod
    def reject_blank_producer(cls, value: str) -> str:
        """Require nonblank producer identity fields."""
        return _nonblank(value, "producer field")

    @field_validator("input_hash")
    @classmethod
    def require_input_sha256(cls, value: str) -> str:
        """Require a lowercase 64-character SHA-256 input hash."""
        return require_sha256(value, "input_hash")

    @field_validator("generated_at")
    @classmethod
    def require_aware_generated_at(cls, value: datetime) -> datetime:
        """Require a timezone-aware generation timestamp."""
        return require_aware(value, "generated_at")


class EquivalenceGroupPublication(_EquivalenceGroupFields):
    """One requested atomic publication of a target-independent equivalence group."""


class CurrentEquivalenceGroup(_EquivalenceGroupFields):
    """One stored current equivalence group with its payload identity and publication time."""

    payload_hash: str
    published_at: datetime

    @field_validator("payload_hash")
    @classmethod
    def require_payload_sha256(cls, value: str) -> str:
        """Require a lowercase 64-character SHA-256 payload hash."""
        return require_sha256(value, "payload_hash")

    @field_validator("published_at")
    @classmethod
    def require_aware_published_at(cls, value: datetime) -> datetime:
        """Require a timezone-aware publication timestamp."""
        return require_aware(value, "published_at")


class EquivalenceGroupPublicationResult(_PrerequisiteModel):
    """Outcome of one equivalence-group publication attempt with the current group."""

    action: InferredPublicationAction
    current_group: CurrentEquivalenceGroup


class EquivalenceActivityReconciliation(_PrerequisiteModel):
    """Sorted disjoint survivor and removed group identities from one reconciliation pass."""

    updated_group_ids: tuple[UUID, ...]
    removed_group_ids: tuple[UUID, ...]


class EquivalenceGroupRead(Protocol):
    """Read-only boundary the graph compiler depends on instead of ORM models."""

    def read_for_member(self, member_group_id: str) -> tuple[CurrentEquivalenceGroup, ...]: ...

    def read_for_members(
        self, member_group_ids: Collection[str]
    ) -> dict[str, tuple[CurrentEquivalenceGroup, ...]]: ...


class EquivalenceGroupPublisher(Protocol):
    """Publication boundary the inference publication service depends on."""

    def publish(
        self, publication: EquivalenceGroupPublication
    ) -> EquivalenceGroupPublicationResult: ...


class InferredSetRead(Protocol):
    """Read-only boundary the graph compiler depends on instead of ORM models."""

    def read(self, target_group_id: str) -> InferredSetReadResult: ...


class InferredSetPublisher(Protocol):
    """Publication boundary the inference publication service depends on."""

    def publish(self, publication: InferredSetPublication) -> InferredSetPublicationResult: ...
