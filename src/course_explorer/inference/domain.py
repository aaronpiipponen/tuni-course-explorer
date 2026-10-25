"""Strict v2 complete-target-result domain contract for prerequisite inference.

One model call owns one complete target result: required and recommended OR-of-AND option sets,
course-wide equivalence proposals, and target-level routing metadata. These models are the only
accepted shape for untrusted model JSON. They reject duplicate, contradictory, or non-finite
output. Required and recommended output form one
indivisible result, so the target's direct option sets and its suppressed candidates are validated
together, so a direct prerequisite excludes a broad or transitive foundation.

Only the v2 schema is supported. Its emitted JSON Schema includes the model and enum descriptions
and the explicit root description below, and that emitted text participates in request/work
identity.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from enum import StrEnum

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from course_explorer.hashing import parse_strict_json
from course_explorer.inference.failures import TargetResultError
from course_explorer.prerequisite._helpers import _unique_ids
from course_explorer.validation import require_text as _require_text


class _InferenceModel(BaseModel):
    """Frozen, closed, strict DTO base for the untrusted model-output boundary."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


def _validate_confidence(value: object) -> Decimal:
    """Accept only a finite numeric confidence in ``[0, 1]``. Quoted strings never pass."""
    if isinstance(value, bool):
        raise ValueError("confidence must be a number, not a boolean")
    if isinstance(value, Decimal):
        confidence = value
    elif isinstance(value, int | float):
        try:
            confidence = Decimal(str(value))
        except InvalidOperation as exc:  # pragma: no cover - str() of a finite number parses
            raise ValueError("confidence must be a finite number") from exc
    else:
        raise ValueError("confidence must be a number")
    if not confidence.is_finite():
        raise ValueError("confidence must be finite")
    if not Decimal(0) <= confidence <= Decimal(1):
        raise ValueError("confidence must be between 0 and 1")
    return confidence


class DirectnessOutcome(StrEnum):
    """Closed directness classification retained for one candidate course."""

    DIRECT_PREREQUISITE = "direct_prerequisite"
    TOO_BASIC_TRANSITIVE = "too_basic_transitive"
    REVERSE_PREREQUISITE = "reverse_prerequisite"
    OVERLAP = "overlap"
    RELATED = "related"
    UNRELATED = "unrelated"


class RoutingFlag(StrEnum):
    """Closed target-level ambiguity flags retained with each complete result."""

    DIRECTNESS_AMBIGUITY = "directness_ambiguity"
    ALTERNATIVE_PATH_AMBIGUITY = "alternative_path_ambiguity"
    BREADTH_AMBIGUITY = "breadth_ambiguity"
    SUBSTITUTE_OVERLAP_AMBIGUITY = "substitute_overlap_ambiguity"
    INSUFFICIENT_COURSE_INFORMATION = "insufficient_course_information"


class OptionFlag(StrEnum):
    """Closed per-option uncertainty flags for the v2 complete-target schema.

    These are finding-level flags (zero or more per required/recommended option), distinct from the
    target-level :class:`RoutingFlag` vocabulary. Each flag records uncertainty the model states
    about the finding, retained as evidence beside the finding's confidence.
    """

    REQUIREDNESS_UNCERTAIN = "requiredness_uncertain"
    MEMBER_UNCERTAIN = "member_uncertain"
    DIRECTNESS_UNCERTAIN = "directness_uncertain"


class EquivalenceFlag(StrEnum):
    """Closed per-equivalence-group uncertainty flags for the v2 complete-target schema."""

    MEMBER_UNCERTAIN = "member_uncertain"
    GROUP_SCOPE_UNCERTAIN = "group_scope_uncertain"


class InferenceSuppressedCandidate(_InferenceModel):
    """One candidate classified as non-direct with its retained raw outcome and evidence."""

    course_code: str
    outcome: DirectnessOutcome
    evidence: str

    @field_validator("course_code")
    @classmethod
    def validate_course_code(cls, value: str) -> str:
        """Require a meaningful suppressed canonical code."""
        return _require_text(value, "suppressed course_code")

    @field_validator("outcome")
    @classmethod
    def validate_outcome(cls, value: DirectnessOutcome) -> DirectnessOutcome:
        """Reject a direct prerequisite recorded as suppressed."""
        if value is DirectnessOutcome.DIRECT_PREREQUISITE:
            raise ValueError("a suppressed candidate cannot be a direct prerequisite")
        return value

    @field_validator("evidence")
    @classmethod
    def validate_evidence(cls, value: str) -> str:
        """Require the raw suppression evidence. ``too_basic_transitive`` is first-class."""
        return _require_text(value, "evidence")


class InferenceRoutingMetadata(_InferenceModel):
    """Target-level confidence, closed ambiguity flags, and suppressed candidate evidence."""

    confidence: Decimal = Field(ge=0, le=1)
    flags: tuple[RoutingFlag, ...]
    suppressed: tuple[InferenceSuppressedCandidate, ...]

    @field_validator("confidence", mode="before")
    @classmethod
    def validate_routing_confidence(cls, value: object) -> Decimal:
        """Accept only numeric, finite, in-range confidence."""
        return _validate_confidence(value)

    @field_validator("flags")
    @classmethod
    def validate_flags(cls, value: tuple[RoutingFlag, ...]) -> tuple[RoutingFlag, ...]:
        """Reject a repeated ambiguity flag."""
        return _unique_ids(value, "flags")

    @field_validator("suppressed")
    @classmethod
    def validate_suppressed(
        cls, value: tuple[InferenceSuppressedCandidate, ...]
    ) -> tuple[InferenceSuppressedCandidate, ...]:
        """Reject a repeated suppressed course code."""
        codes = tuple(candidate.course_code for candidate in value)
        _unique_ids(codes, "suppressed course codes")
        return value


class InferenceCourseOptionV2(_InferenceModel):
    """One v2 AND option carrying zero-or-more option-uncertainty flags."""

    # `finding_flags` (not `flags`) keeps finding-level uncertainty distinct from the target-level
    # `routing.flags`. Required, not defaulted, so every option carries an explicit, possibly empty,
    # `finding_flags` array on the v2 wire shape.

    course_codes: tuple[str, ...]
    evidence: str
    confidence: Decimal = Field(ge=0, le=1)
    finding_flags: tuple[OptionFlag, ...]

    @field_validator("course_codes")
    @classmethod
    def validate_course_codes(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Require a nonempty, unique, meaningful canonical code tuple."""
        if not value:
            raise ValueError("course_codes must not be empty")
        for code in value:
            _require_text(code, "course code")
        return _unique_ids(value, "course_codes")

    @field_validator("evidence")
    @classmethod
    def validate_evidence(cls, value: str) -> str:
        """Require evidence because confidence never substitutes for it."""
        return _require_text(value, "evidence")

    @field_validator("confidence", mode="before")
    @classmethod
    def validate_option_confidence(cls, value: object) -> Decimal:
        """Accept only numeric, finite, in-range confidence."""
        return _validate_confidence(value)

    @field_validator("finding_flags")
    @classmethod
    def validate_finding_flags(cls, value: tuple[OptionFlag, ...]) -> tuple[OptionFlag, ...]:
        """Reject a repeated finding flag while allowing zero or several distinct flags."""
        return _unique_ids(value, "finding_flags")

    @property
    def code_signature(self) -> frozenset[str]:
        """Return the order-independent member identity used for duplicate detection."""
        return frozenset(self.course_codes)


class InferenceRequirementSetV2(_InferenceModel):
    """One v2 top-level AND requirement whose options carry finding-level flags."""

    requirement_id: str
    options: tuple[InferenceCourseOptionV2, ...]

    @field_validator("requirement_id")
    @classmethod
    def validate_requirement_id(cls, value: str) -> str:
        """Require a meaningful stable requirement identifier."""
        return _require_text(value, "requirement_id")

    @field_validator("options")
    @classmethod
    def validate_options(
        cls, value: tuple[InferenceCourseOptionV2, ...]
    ) -> tuple[InferenceCourseOptionV2, ...]:
        """Require nonempty options and reject a logically duplicate alternative."""
        if not value:
            raise ValueError("options must not be empty")
        signatures = [option.code_signature for option in value]
        if len(signatures) != len(set(signatures)):
            raise ValueError("options must not repeat a logically duplicate group")
        return value

    @property
    def group_signature(self) -> frozenset[frozenset[str]]:
        """Return the order-independent option identity used for duplicate detection."""
        return frozenset(option.code_signature for option in self.options)


class InferenceEquivalenceProposalV2(_InferenceModel):
    """One v2 equivalence group carrying zero-or-more equivalence-uncertainty flags."""

    members: tuple[str, ...]
    evidence: str
    confidence: Decimal = Field(ge=0, le=1)
    finding_flags: tuple[EquivalenceFlag, ...]

    @field_validator("members")
    @classmethod
    def validate_members(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Require at least two unique meaningful canonical members."""
        if len(value) < 2:
            raise ValueError("equivalence proposals must have at least two members")
        for member in value:
            _require_text(member, "equivalence member")
        return _unique_ids(value, "members")

    @field_validator("evidence")
    @classmethod
    def validate_evidence(cls, value: str) -> str:
        """Require evidence for the proposed interchangeability."""
        return _require_text(value, "evidence")

    @field_validator("confidence", mode="before")
    @classmethod
    def validate_equivalence_confidence(cls, value: object) -> Decimal:
        """Accept only numeric, finite, in-range confidence."""
        return _validate_confidence(value)

    @field_validator("finding_flags")
    @classmethod
    def validate_finding_flags(
        cls, value: tuple[EquivalenceFlag, ...]
    ) -> tuple[EquivalenceFlag, ...]:
        """Reject a repeated equivalence flag while allowing zero or several distinct flags."""
        return _unique_ids(value, "finding_flags")


# The explicit root JSON-Schema description emitted by the v2 model. The generated schema text,
# including the model and enum descriptions and this root description, participates in request/work
# identity.
_V2_RESULT_WIRE_DESCRIPTION = (
    "One indivisible v2 complete target result: required and recommended option sets, equivalence\n"
    "groups, and routing metadata.\n\n"
    "Every option and equivalence group carries an explicit ``finding_flags`` array, which may be\n"
    "empty, and required, recommended, suppressed, and equivalence identities are validated as one\n"
    "complete target result."
)


class InferenceTargetResultV2(_InferenceModel):
    """One indivisible complete target result: required, recommended, equivalence, routing.

    This is the only accepted complete-target-result contract. Required and recommended option
    sets carry per-finding ``finding_flags``. The model enforces category, duplicate, and
    direct-versus-suppressed completeness in one indivisible result. The class docstring is Python
    documentation, while the explicit root JSON-Schema description above is emitted schema text that
    participates in request/work identity.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        json_schema_extra={"description": _V2_RESULT_WIRE_DESCRIPTION},
    )

    required: tuple[InferenceRequirementSetV2, ...]
    recommended: tuple[InferenceRequirementSetV2, ...]
    equivalence: tuple[InferenceEquivalenceProposalV2, ...]
    routing: InferenceRoutingMetadata

    @model_validator(mode="after")
    def validate_complete_result(self) -> InferenceTargetResultV2:
        """Enforce category, duplicate, and direct-versus-suppressed completeness rules."""
        for label, sets in (("required", self.required), ("recommended", self.recommended)):
            ids = tuple(requirement.requirement_id for requirement in sets)
            _unique_ids(ids, f"{label} requirement_id values")
            signatures = [requirement.group_signature for requirement in sets]
            if len(signatures) != len(set(signatures)):
                raise ValueError(f"{label} must not repeat a logically duplicate group")

        required_codes = {
            code
            for requirement in self.required
            for option in requirement.options
            for code in option.course_codes
        }
        recommended_codes = {
            code
            for requirement in self.recommended
            for option in requirement.options
            for code in option.course_codes
        }
        overlap = required_codes & recommended_codes
        if overlap:
            raise ValueError("a course cannot be both a required and a recommended option")
        suppressed_codes = {candidate.course_code for candidate in self.routing.suppressed}
        contradictory = (required_codes | recommended_codes) & suppressed_codes
        if contradictory:
            raise ValueError("a suppressed candidate cannot also be a direct option")

        # A member may belong to several distinct proposed groups. Exact duplicates are rejected
        # by comparing canonical group signatures instead of merging memberships.
        group_signatures = [frozenset(proposal.members) for proposal in self.equivalence]
        if len(group_signatures) != len(set(group_signatures)):
            raise ValueError("equivalence must not repeat a logically duplicate group")
        return self


def target_result_model(schema_version: str) -> type[InferenceTargetResultV2]:
    """Return the strict complete-target model for the ``v2`` schema version."""
    if schema_version != "v2":
        raise ValueError("inference schema version must be 'v2'")
    return InferenceTargetResultV2


def validate_target_result_acceptance(
    result: InferenceTargetResultV2,
    *,
    target_group_id: str,
    course_groups_by_code: Mapping[str, frozenset[str]],
) -> dict[str, str]:
    """Validate one structurally parsed result against the accepted output contract.

    This is the one shared pre-success acceptance owner for both the writer and proposal
    composition. It enforces zero/one requirement set per category, resolves every code the result
    actually names to exactly one supplied canonical group, and rejects the target appearing as its
    own direct or suppressed source while allowing an equivalence group to include it. It returns the
    used-code to unique canonical-group mapping. Only actually used codes are resolved. Unused
    ambiguous codes are never inspected and the catalogue is never enumerated.
    """
    if len(result.required) > 1 or len(result.recommended) > 1:
        raise TargetResultError("multiple_requirement_sets")
    direct_codes = {
        code
        for requirement in (*result.required, *result.recommended)
        for option in requirement.options
        for code in option.course_codes
    }
    suppressed_codes = {candidate.course_code for candidate in result.routing.suppressed}
    equivalence_codes = {member for proposal in result.equivalence for member in proposal.members}
    resolved: dict[str, str] = {}
    for code in sorted(direct_codes | suppressed_codes | equivalence_codes):
        groups = course_groups_by_code.get(code, frozenset())
        if not groups:
            raise TargetResultError("invalid_result")
        if len(groups) != 1:
            raise TargetResultError("ambiguous_code")
        resolved[code] = next(iter(groups))
    for code in direct_codes | suppressed_codes:
        if resolved[code] == target_group_id:
            raise TargetResultError("target_direct_source")
    return resolved


def parse_target_result(raw_json: str, schema_version: str) -> InferenceTargetResultV2:
    """Validate one complete target-result JSON document against the named schema version.

    Only the ``v2`` schema is accepted. Any other version fails loudly. A model-output parse or schema rejection is a target-scoped
    :class:`TargetResultError` raised outside the untrusted catch so no raw parse or Pydantic context
    is reachable. The schema-version lookup error propagates normally.
    """
    model = target_result_model(schema_version)
    if not isinstance(raw_json, str) or not raw_json.strip():
        raise TargetResultError("invalid_result")
    parse_failed = False
    first_pass: object = None
    try:
        first_pass = parse_strict_json(raw_json, decimal_numbers=True)
    except ValueError:
        parse_failed = True
    if parse_failed:
        raise TargetResultError("invalid_result")
    if not isinstance(first_pass, dict):
        raise TargetResultError("invalid_result")
    schema_failed = False
    result: InferenceTargetResultV2 | None = None
    try:
        result = model.model_validate_json(raw_json, strict=True)
    except ValidationError:
        schema_failed = True
    if schema_failed:
        raise TargetResultError("invalid_result")
    assert result is not None
    return result


def _numeric_confidence_schema() -> dict[str, object]:
    """Return the exact closed numeric JSON Schema for one confidence value."""
    return {"type": "number", "minimum": 0, "maximum": 1}


def _replace_confidence_alternatives(node: object) -> object:
    """Recursively replace Decimal confidence unions with exact numeric JSON Schema."""
    if isinstance(node, dict):
        replaced: dict[str, object] = {}
        for key, value in node.items():
            if key == "confidence" and isinstance(value, dict):
                alternatives = value.get("anyOf")
                if isinstance(alternatives, list) and any(
                    isinstance(alternative, dict) and alternative.get("type") == "number"
                    for alternative in alternatives
                ):
                    replaced[key] = _numeric_confidence_schema()
                    continue
            replaced[key] = _replace_confidence_alternatives(value)
        return replaced
    if isinstance(node, list):
        return [_replace_confidence_alternatives(item) for item in node]
    return node


def target_result_json_schema(schema_version: str) -> dict[str, object]:
    """Return a closed JSON Schema with numeric-only confidence.

    This applies the v2 numeric-confidence rewriting. The emitted bytes participate in request/work
    identity.
    """
    schema = target_result_model(schema_version).model_json_schema(mode="validation")
    rewritten = _replace_confidence_alternatives(schema)
    if not isinstance(rewritten, dict) or rewritten.get("type") != "object":
        raise ValueError("target-result JSON Schema must describe a top-level object")
    return rewritten
