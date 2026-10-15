"""Inference-owned accepted-result proposal composition and DTO contracts.

This module turns one already completed, validated schema-v2 completion into an immutable, versioned
per-target proposal. It is pure: it reads no configuration, calls no model or provider, writes no
database row, and never touches a final graph/path-owned store. It consumes the completion's
descriptor mapping and uncomposed result, composes the accepted required/recommended complete
OR-of-AND expression with its required option flags, applies only the direct-official
whole-option and target-substitution dedup, and retains exact equivalence-group candidates.

Official curriculum structure is read here only after the model output exists. It never enters the
request, selection input, or model call.
"""

from __future__ import annotations

from collections.abc import Collection
from decimal import Decimal
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import BaseModel, ConfigDict, field_validator

from course_explorer.curriculum import CatalogueCourse, CatalogueCourseVersion
from course_explorer.enums import (
    PrerequisiteMemberType,
    PrerequisiteRequirementKind,
)
from course_explorer.hashing import canonical_json_sha256
from course_explorer.inference.context import (
    RequestCourseDescriptors,
    resolve_result_codes,
)
from course_explorer.inference.domain import (
    EquivalenceFlag,
    InferenceTargetResultV2,
    OptionFlag,
)
from course_explorer.inference.evidence import (
    InferenceModelAttemptRecord,
    InferencePipelineRunRecord,
    InferenceTargetWorkRecord,
)
from course_explorer.prerequisite.domain import (
    AndRequirement,
    CourseRequirement,
    InferenceEvidenceKind,
    InferenceEvidenceReference,
    InferenceNodeMetadata,
    InferredPrerequisiteCategory,
    OrRequirement,
    PrerequisiteExpression,
    PrerequisiteOrigin,
)
from course_explorer.validation import (
    require_sha256 as _require_sha256,
)
from course_explorer.validation import (
    require_text as _require_text,
)


class _ProposalModel(BaseModel):
    """Frozen, closed, strict DTO base for the inference proposal boundary."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class AcceptedOptionFlags(_ProposalModel):
    """The accepted surviving option's category, requirement, members, and copied finding flags.

    ``members`` holds the sorted canonical members after the direct-official dedup. ``finding_flags``
    is the option's flag tuple copied as-is, so the emitted
    per-option uncertainty carries forward.
    """

    category: InferredPrerequisiteCategory
    requirement_id: str
    members: tuple[str, ...]
    finding_flags: tuple[OptionFlag, ...]

    @field_validator("requirement_id")
    @classmethod
    def validate_requirement_id(cls, value: str) -> str:
        """Require a meaningful stable requirement identifier."""
        return _require_text(value, "accepted option requirement_id")

    @field_validator("members")
    @classmethod
    def validate_members(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Require at least one unique nonblank sorted canonical member."""
        if not value:
            raise ValueError("an accepted option annotation requires at least one member")
        for member in value:
            _require_text(member, "accepted option member")
        if len(set(value)) != len(value):
            raise ValueError("accepted option members must be unique")
        if value != tuple(sorted(value)):
            raise ValueError("accepted option members must be sorted")
        return value

    @field_validator("finding_flags")
    @classmethod
    def validate_finding_flags(cls, value: tuple[OptionFlag, ...]) -> tuple[OptionFlag, ...]:
        """Reject a repeated finding flag while allowing zero or several distinct flags."""
        if len(set(value)) != len(value):
            raise ValueError("accepted option finding flags must not repeat")
        return value


class EquivalenceProposalCandidate(_ProposalModel):
    """One accepted exact course-wide equivalence group with its inference provenance."""

    members: tuple[str, ...]
    inference: InferenceNodeMetadata
    finding_flags: tuple[EquivalenceFlag, ...]

    @field_validator("members")
    @classmethod
    def validate_members(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Require at least two unique nonblank canonical members in sorted order."""
        if len(value) < 2:
            raise ValueError("an equivalence candidate requires at least two members")
        for member in value:
            _require_text(member, "equivalence candidate member")
        if len(set(value)) != len(value):
            raise ValueError("equivalence candidate members must be unique")
        if value != tuple(sorted(value)):
            raise ValueError("equivalence candidate members must be sorted")
        return value

    @field_validator("finding_flags")
    @classmethod
    def validate_finding_flags(
        cls, value: tuple[EquivalenceFlag, ...]
    ) -> tuple[EquivalenceFlag, ...]:
        """Reject a repeated equivalence flag."""
        if len(set(value)) != len(value):
            raise ValueError("equivalence candidate finding flags must not repeat")
        return value


class TargetProposal(_ProposalModel):
    """One immutable, versioned accepted target proposal composed from one validated completion."""

    proposal_id: UUID
    target_group_id: str
    source_attempt_id: UUID
    proposal_version: str
    identity_sha256: str
    expression: PrerequisiteExpression | None
    equivalence: tuple[EquivalenceProposalCandidate, ...]
    option_flags: tuple[AcceptedOptionFlags, ...]

    @field_validator("target_group_id", "proposal_version")
    @classmethod
    def validate_identity(cls, value: str) -> str:
        """Require a meaningful target identity or composition version."""
        return _require_text(value, "target proposal identity")

    @field_validator("identity_sha256")
    @classmethod
    def validate_sha256(cls, value: str) -> str:
        """Require every proposal digest to be a full lowercase digest."""
        return _require_sha256(value, "target proposal digest")


def official_snapshot_sha256(target: CatalogueCourse) -> str:
    """Hash the target's canonical identity, activity context, and direct official structures.

    The snapshot binds the proposal identity to the exact selected representative and its direct
    prerequisite/substitution options, so a changed official snapshot (including activity context)
    yields a distinct proposal without rerunning any model work. Ancestors are never read.
    """
    representative = target.representative
    if representative is None:
        raise ValueError(f"target {target.group_id} has no selected representative")
    return canonical_json_sha256(
        {
            "group_id": target.group_id,
            "activity_as_of_academic_year_start": target.activity_as_of_academic_year_start,
            "activity_window_years": target.activity_window_years,
            "representative_source_sha256": representative.source_hash,
            "prerequisite_options": [
                option.model_dump(mode="json") for option in representative.prerequisite_options
            ],
            "substitution_options": [
                option.model_dump(mode="json") for option in representative.substitution_options
            ],
        }
    )


def _proposal_identity_hash(
    work_key_sha256: str,
    attempt_id: UUID,
    official_snapshot_sha256_value: str,
    proposal_version: str,
) -> str:
    """Hash the one canonical proposal identity payload from its exact immutable field values.

    This is the single implementation shared by the DTO-level helper and the persistence owner's
    digest re-check, so the proposal identity formula never exists in two places.
    """
    _require_sha256(official_snapshot_sha256_value, "official_snapshot_sha256")
    _require_text(proposal_version, "proposal_version")
    return canonical_json_sha256(
        {
            "work_key_sha256": work_key_sha256,
            "attempt_id": str(attempt_id),
            "official_snapshot_sha256": official_snapshot_sha256_value,
            "proposal_version": proposal_version,
        }
    )


def proposal_identity_sha256(
    work: InferenceTargetWorkRecord,
    attempt: InferenceModelAttemptRecord,
    official_snapshot_sha256_value: str,
    proposal_version: str,
) -> str:
    """Hash one proposal's immutable identity: work key, completion, official snapshot, and version."""
    return _proposal_identity_hash(
        work.work_key_sha256,
        attempt.attempt_id,
        official_snapshot_sha256_value,
        proposal_version,
    )


def named_candidate_group_ids(
    result: InferenceTargetResultV2, descriptors: RequestCourseDescriptors
) -> tuple[str, ...]:
    """Return the sorted candidate group IDs the result actually names, excluding the target.

    The bounded command uses this same pure resolution to discover exactly which current courses it
    must read. It never enumerates the catalogue or reruns selection to compose a stored work unit.
    """
    mapping = resolve_result_codes(result, descriptors)
    return tuple(
        sorted({group_id for group_id in mapping.values()} - {descriptors.target.group_id})
    )


def _validate_target(
    target: CatalogueCourse,
    descriptors: RequestCourseDescriptors,
    work: InferenceTargetWorkRecord,
) -> None:
    """Require the current active target, activity context, and representative to match the work."""
    if target.group_id != descriptors.target.group_id:
        raise ValueError("the read target does not match the saved request target")
    if not target.is_active:
        raise ValueError(f"cannot compose a proposal for inactive target {target.group_id}")
    if (
        target.activity_as_of_academic_year_start != work.request.activity_as_of_academic_year_start
        or target.activity_window_years != work.request.activity_window_years
    ):
        raise ValueError("the current target activity context does not match the target work")
    representative = target.representative
    if representative is None:
        raise ValueError(f"target {target.group_id} has no selected representative")
    if representative.code != descriptors.target.course_code:
        raise ValueError("the target representative code does not match the saved request")
    if representative.source_hash != descriptors.target.representative_source_sha256:
        raise ValueError("the target representative source does not match the saved request")


def _validate_referenced_courses(
    mapping: dict[str, str],
    descriptors: RequestCourseDescriptors,
    referenced_courses: tuple[CatalogueCourse, ...],
) -> None:
    """Require exactly the used candidate courses, each matching its request identity."""
    descriptors_by_group = {
        descriptor.group_id: descriptor
        for descriptor in (descriptors.target, *descriptors.candidates)
    }
    expected = {
        group_id for group_id in mapping.values() if group_id != descriptors.target.group_id
    }
    courses_by_group: dict[str, CatalogueCourse] = {}
    for course in referenced_courses:
        if course.group_id in courses_by_group:
            raise ValueError(f"duplicate referenced course {course.group_id}")
        courses_by_group[course.group_id] = course
    if set(courses_by_group) != expected:
        raise ValueError("referenced courses must cover exactly the used candidate group IDs")
    for group_id, course in courses_by_group.items():
        descriptor = descriptors_by_group[group_id]
        representative = course.representative
        if representative is None:
            raise ValueError(f"referenced course {group_id} has no selected representative")
        if representative.code != descriptor.course_code:
            raise ValueError(f"referenced course {group_id} representative code changed")
        if representative.source_hash != descriptor.representative_source_sha256:
            raise ValueError(f"referenced course {group_id} representative source changed")


def _official_plain_options(
    representative: CatalogueCourseVersion,
) -> list[tuple[int, InferredPrerequisiteCategory, frozenset[str]]]:
    """Return the target's direct official plain-course options as (index, category, members)."""
    options: list[tuple[int, InferredPrerequisiteCategory, frozenset[str]]] = []
    for option in representative.prerequisite_options:
        if not option.members:
            continue
        if not all(
            member.member_type == PrerequisiteMemberType.COURSE for member in option.members
        ):
            continue
        category = (
            InferredPrerequisiteCategory.REQUIRED
            if option.requirement_kind == PrerequisiteRequirementKind.COMPULSORY
            else InferredPrerequisiteCategory.RECOMMENDED
        )
        options.append(
            (
                option.option_index,
                category,
                frozenset(member.referenced_group_id for member in option.members),
            )
        )
    return options


def _option_node(
    category: InferredPrerequisiteCategory,
    members: list[str],
    confidence: Decimal,
    requirement_id: str,
    reference: InferenceEvidenceReference,
) -> PrerequisiteExpression:
    """Build one inferred course or AND option with its own option-level provenance."""
    metadata = InferenceNodeMetadata(
        confidence=confidence,
        requirement_ids=(requirement_id,),
        evidence=(reference,),
    )
    if len(members) == 1:
        return CourseRequirement(
            type="course",
            origin=PrerequisiteOrigin.INFERRED,
            inferred_category=category,
            course_group_id=members[0],
            inference=metadata,
        )
    return AndRequirement(
        type="and",
        origin=PrerequisiteOrigin.INFERRED,
        inferred_category=category,
        children=tuple(
            CourseRequirement(
                type="course",
                origin=PrerequisiteOrigin.INFERRED,
                inferred_category=category,
                course_group_id=group_id,
                inference=metadata,
            )
            for group_id in members
        ),
        inference=metadata,
    )


def _wrapper_metadata(
    confidence: Decimal, reference: InferenceEvidenceReference
) -> InferenceNodeMetadata:
    """Build the target-level routing-confidence metadata carried by pool/root wrappers.

    The technical choice carries the model's actual target-level routing confidence as
    wrapper provenance, independent of pool-specific confidence and of the acceptance cutoff.
    """
    return InferenceNodeMetadata(
        confidence=confidence,
        requirement_ids=(),
        evidence=(reference,),
    )


def _dedup_option(
    category: InferredPrerequisiteCategory,
    requirement_id: str,
    mapped: list[str],
    option_confidence: Decimal,
    official_options: list[tuple[int, InferredPrerequisiteCategory, frozenset[str]]],
    reference: InferenceEvidenceReference,
) -> tuple[PrerequisiteExpression | None, tuple[str, ...]]:
    """Apply the direct-official whole-option/cross-category rule to one inferred option.

    Returns the surviving option node (or ``None`` when wholly absorbed) together with the sorted
    canonical members that survived, so composition can retain the accepted option's flags. The
    official membership decision is fixed.
    """
    mapped_set = set(mapped)
    same = [
        (index, members)
        for index, official_category, members in official_options
        if official_category is category and members <= mapped_set
    ]
    if same:
        return None, ()
    other = [
        (index, members)
        for index, official_category, members in official_options
        if official_category is not category and members <= mapped_set
    ]
    remainder = mapped
    if other:
        removed = set().union(*(members for _, members in other))
        remainder = [group_id for group_id in mapped if group_id not in removed]
        if not remainder:
            return None, ()
    return (
        _option_node(category, remainder, option_confidence, requirement_id, reference),
        tuple(sorted(remainder)),
    )


def _pool(
    options: list[PrerequisiteExpression],
    category: InferredPrerequisiteCategory,
    routing_confidence: Decimal,
    reference: InferenceEvidenceReference,
) -> PrerequisiteExpression | None:
    """Return nothing, one option, or one inferred target-confidence OR wrapper."""
    if not options:
        return None
    if len(options) == 1:
        return options[0]
    return OrRequirement(
        type="or",
        origin=PrerequisiteOrigin.INFERRED,
        inferred_category=category,
        children=tuple(options),
        inference=_wrapper_metadata(routing_confidence, reference),
    )


def _compose_expression(
    target: CatalogueCourse,
    result: InferenceTargetResultV2,
    mapping: dict[str, str],
    reference: InferenceEvidenceReference,
) -> tuple[PrerequisiteExpression | None, tuple[AcceptedOptionFlags, ...]]:
    """Compose the accepted required/recommended pools and their accepted-option flags.

    It loops the original required then recommended option order and appends each surviving node
    with its finding flags copied as-is. The composition applies the stored flags directly, with no
    union, cutoff, default, or sorting.
    """
    representative = target.representative
    official_options = _official_plain_options(representative)
    pools: dict[InferredPrerequisiteCategory, list[PrerequisiteExpression]] = {
        InferredPrerequisiteCategory.REQUIRED: [],
        InferredPrerequisiteCategory.RECOMMENDED: [],
    }
    option_flags: list[AcceptedOptionFlags] = []
    for category, requirement_sets in (
        (InferredPrerequisiteCategory.REQUIRED, result.required),
        (InferredPrerequisiteCategory.RECOMMENDED, result.recommended),
    ):
        if not requirement_sets:
            continue
        requirement_set = requirement_sets[0]
        for option in requirement_set.options:
            mapped = sorted({mapping[code] for code in option.course_codes})
            node, survivors = _dedup_option(
                category,
                requirement_set.requirement_id,
                mapped,
                option.confidence,
                official_options,
                reference,
            )
            if node is not None:
                pools[category].append(node)
                option_flags.append(
                    AcceptedOptionFlags(
                        category=category,
                        requirement_id=requirement_set.requirement_id,
                        members=survivors,
                        finding_flags=option.finding_flags,
                    )
                )
    required_pool = _pool(
        pools[InferredPrerequisiteCategory.REQUIRED],
        InferredPrerequisiteCategory.REQUIRED,
        result.routing.confidence,
        reference,
    )
    recommended_pool = _pool(
        pools[InferredPrerequisiteCategory.RECOMMENDED],
        InferredPrerequisiteCategory.RECOMMENDED,
        result.routing.confidence,
        reference,
    )
    if required_pool is not None and recommended_pool is not None:
        expression: PrerequisiteExpression | None = AndRequirement(
            type="and",
            origin=PrerequisiteOrigin.INFERRED,
            inferred_category=InferredPrerequisiteCategory.REQUIRED,
            children=(required_pool, recommended_pool),
            inference=_wrapper_metadata(result.routing.confidence, reference),
        )
    else:
        expression = required_pool if required_pool is not None else recommended_pool
    return expression, tuple(option_flags)


def _compose_equivalence(
    target: CatalogueCourse,
    result: InferenceTargetResultV2,
    mapping: dict[str, str],
    reference: InferenceEvidenceReference,
) -> tuple[EquivalenceProposalCandidate, ...]:
    """Keep exact groups, dropping only a target plus one direct singleton official substitute."""
    representative = target.representative
    singletons = [
        (option.option_index, option.members[0].course_group_id)
        for option in representative.substitution_options
        if len(option.members) == 1
    ]
    candidates: list[EquivalenceProposalCandidate] = []
    for proposal in result.equivalence:
        members = tuple(sorted({mapping[member] for member in proposal.members}))
        matched = next(
            (
                option_index
                for option_index, substitute in singletons
                if set(members) == {target.group_id, substitute}
            ),
            None,
        )
        if matched is not None:
            continue
        candidates.append(
            EquivalenceProposalCandidate(
                members=members,
                inference=InferenceNodeMetadata(
                    confidence=proposal.confidence,
                    requirement_ids=(),
                    evidence=(reference,),
                ),
                finding_flags=proposal.finding_flags,
            )
        )
    return tuple(candidates)


def compose_target_proposal(
    work: InferenceTargetWorkRecord,
    attempt: InferenceModelAttemptRecord,
    run: InferencePipelineRunRecord,
    descriptors: RequestCourseDescriptors,
    target: CatalogueCourse,
    referenced_courses: tuple[CatalogueCourse, ...],
    proposal_version: str,
) -> TargetProposal:
    """Compose one immutable accepted proposal from one completed validated completion.

    The composer is pure and label-safe: it reads the completion's uncomposed result once, resolves
    only the codes the result names, applies the direct-official dedup and
    target-substitution drop, retains the accepted options' flags, and returns the versioned proposal.
    It never parses a saved request, writes final stores, re-runs selection, or calls a model.
    """
    _require_text(proposal_version, "proposal_version")
    _validate_target(target, descriptors, work)
    result = attempt.payload.result
    if result is None:
        raise ValueError("proposal composition requires an uncomposed validated result")
    official_hash = official_snapshot_sha256(target)
    identity = proposal_identity_sha256(work, attempt, official_hash, proposal_version)
    proposal_id = uuid5(NAMESPACE_URL, identity)
    reference = InferenceEvidenceReference(
        kind=InferenceEvidenceKind.EXPRESSION_PROPOSAL,
        reference_id=str(proposal_id),
    )
    mapping = resolve_result_codes(result, descriptors)
    _validate_referenced_courses(mapping, descriptors, referenced_courses)
    expression, option_flags = _compose_expression(target, result, mapping, reference)
    equivalence = _compose_equivalence(target, result, mapping, reference)
    return TargetProposal(
        proposal_id=proposal_id,
        target_group_id=target.group_id,
        source_attempt_id=attempt.attempt_id,
        proposal_version=proposal_version,
        identity_sha256=identity,
        expression=expression,
        equivalence=equivalence,
        option_flags=option_flags,
    )


def aggregate_equivalence_candidates(
    proposals: Collection[TargetProposal],
) -> tuple[tuple[tuple[UUID, EquivalenceProposalCandidate], ...], ...]:
    """Group exact equivalence candidates across proposals without merging overlaps or winners.

    Every distinct sorted member tuple becomes one group holding all sorted ``(proposal_id,
    candidate)`` supporter records. The pure result is consumed by publication over its chosen
    current proposals. It publishes nothing and never selects a winning confidence.
    """
    groups: dict[tuple[str, ...], list[tuple[UUID, EquivalenceProposalCandidate]]] = {}
    for proposal in proposals:
        for candidate in proposal.equivalence:
            groups.setdefault(candidate.members, []).append((proposal.proposal_id, candidate))
    return tuple(
        tuple(sorted(supporters, key=lambda item: item[0]))
        for _, supporters in sorted(groups.items(), key=lambda item: item[0])
    )
