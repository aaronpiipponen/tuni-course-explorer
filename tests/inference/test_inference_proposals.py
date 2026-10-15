"""Proposal composition and equivalence-aggregation contract tests."""

from __future__ import annotations

from decimal import Decimal
from uuid import NAMESPACE_URL, UUID, uuid5

import pytest

from course_explorer.inference.context import (
    RequestCourseDescriptor,
    RequestCourseDescriptors,
    request_descriptors_from_packet,
)
from course_explorer.inference.domain import (
    DirectnessOutcome,
    InferenceRequirementSetV2,
    InferenceRoutingMetadata,
    InferenceSuppressedCandidate,
    InferenceTargetResultV2,
)
from course_explorer.inference.failures import TargetResultError
from course_explorer.inference.proposals import (
    AcceptedOptionFlags,
    aggregate_equivalence_candidates,
    compose_target_proposal,
)
from course_explorer.prerequisite.domain import (
    AndRequirement,
    CourseRequirement,
    InferenceEvidenceKind,
    InferredPrerequisiteCategory,
    OrRequirement,
    PrerequisiteOrigin,
)
from tests.inference._proposal_support import (
    _category_fixture,
    _codes,
    _course,
    _descriptors,
    _equivalence_fixture,
    _hash,
    _option,
    _records,
    _required_option_codes,
)
from tests.inference._target_support import target_packet


def test_compose_complete_category_pools_and_official_dedup() -> None:
    """The composer pools per-category options, applies direct-official dedup, and keeps flags."""
    target, candidates, result = _category_fixture()
    descriptors = _descriptors(target, candidates)
    work, attempt, run = _records(result, descriptors)
    referenced = {course.group_id: course for course in candidates}

    proposal = compose_target_proposal(
        work,
        attempt,
        run,
        descriptors,
        target,
        tuple(referenced[group_id] for group_id in sorted(referenced)),
        "v1",
    )

    assert proposal.proposal_id == uuid5(NAMESPACE_URL, proposal.identity_sha256)
    assert proposal.target_group_id == "T"
    assert proposal.source_attempt_id == attempt.attempt_id
    assert proposal.equivalence == ()
    reference_id = str(proposal.proposal_id)

    # The root mixed-category AND partitions into one pool per category, required first.
    expression = proposal.expression
    assert isinstance(expression, AndRequirement)
    assert expression.origin is PrerequisiteOrigin.INFERRED
    assert expression.inferred_category is InferredPrerequisiteCategory.REQUIRED
    assert expression.inference is not None
    assert expression.inference.confidence == Decimal("0.75")
    assert expression.inference.requirement_ids == ()
    assert [item.kind for item in expression.inference.evidence] == [
        InferenceEvidenceKind.EXPRESSION_PROPOSAL
    ]
    assert expression.inference.evidence[0].reference_id == reference_id
    required_pool, recommended_pool = expression.children
    assert required_pool.inferred_category is InferredPrerequisiteCategory.REQUIRED
    assert recommended_pool.inferred_category is InferredPrerequisiteCategory.RECOMMENDED

    options = _required_option_codes(expression)
    assert [_codes(option) for option in options] == [["D", "E"], ["G", "I"], ["X", "Y"]]
    assert options[0].inference.confidence == Decimal("0.8")
    assert options[0].inference.requirement_ids == ("required_1",)
    assert options[0].inference.evidence[0].reference_id == reference_id

    assert isinstance(recommended_pool, OrRequirement)
    assert [_codes(option) for option in recommended_pool.children] == [["N"], ["L"]]
    assert recommended_pool.children[0].inference.confidence == Decimal("0.5")

    # The surviving options keep their finding flags in surviving option order.
    from course_explorer.inference.domain import OptionFlag

    assert proposal.option_flags == (
        AcceptedOptionFlags(
            category=InferredPrerequisiteCategory.REQUIRED,
            requirement_id="required_1",
            members=("D", "E"),
            finding_flags=(OptionFlag.REQUIREDNESS_UNCERTAIN,),
        ),
        AcceptedOptionFlags(
            category=InferredPrerequisiteCategory.REQUIRED,
            requirement_id="required_1",
            members=("G", "I"),
            finding_flags=(),
        ),
        AcceptedOptionFlags(
            category=InferredPrerequisiteCategory.REQUIRED,
            requirement_id="required_1",
            members=("X", "Y"),
            finding_flags=(),
        ),
        AcceptedOptionFlags(
            category=InferredPrerequisiteCategory.RECOMMENDED,
            requirement_id="recommended_1",
            members=("N",),
            finding_flags=(OptionFlag.MEMBER_UNCERTAIN,),
        ),
        AcceptedOptionFlags(
            category=InferredPrerequisiteCategory.RECOMMENDED,
            requirement_id="recommended_1",
            members=("L",),
            finding_flags=(),
        ),
    )

    # An absent category contributes no node.
    single_category = result.model_copy(
        update={
            "required": (),
            "recommended": (
                InferenceRequirementSetV2(
                    requirement_id="recommended_1", options=(_option(("L-code",), "0.2"),)
                ),
            ),
        }
    )
    single_work, single_attempt, single_run = _records(single_category, descriptors)
    single = compose_target_proposal(
        single_work,
        single_attempt,
        single_run,
        descriptors,
        target,
        (referenced["L"],),
        "v1",
    )
    assert isinstance(single.expression, CourseRequirement)
    assert single.expression.inferred_category is InferredPrerequisiteCategory.RECOMMENDED


def test_reject_ambiguous_or_multi_set_without_inventing_grouping() -> None:
    """Ambiguous codes and multi-set results fail loudly. Suppression is non-direct."""
    target, candidates, result = _category_fixture()
    descriptors = _descriptors(target, candidates)
    work, attempt, run = _records(result, descriptors)

    ambiguous = RequestCourseDescriptors(
        target=RequestCourseDescriptor(
            group_id="T",
            course_code="T-code",
            representative_source_sha256=_hash("source-T"),
        ),
        candidates=(
            RequestCourseDescriptor(
                group_id="P",
                course_code="DUP",
                representative_source_sha256=_hash("source-P"),
            ),
            RequestCourseDescriptor(
                group_id="R",
                course_code="DUP",
                representative_source_sha256=_hash("source-R"),
            ),
        ),
    )

    def only_option(codes: tuple[str, ...]) -> InferenceTargetResultV2:
        return result.model_copy(
            update={
                "required": (
                    InferenceRequirementSetV2(
                        requirement_id="required_1", options=(_option(codes, "0.9"),)
                    ),
                ),
                "recommended": (),
            }
        )

    ambiguous_result = only_option(("DUP",))
    ambiguous_work, ambiguous_attempt, ambiguous_run = _records(ambiguous_result, descriptors)
    with pytest.raises(TargetResultError) as ambiguous_error:
        compose_target_proposal(
            ambiguous_work,
            ambiguous_attempt,
            ambiguous_run,
            ambiguous,
            target,
            (),
            "v1",
        )
    assert ambiguous_error.value.reason == "ambiguous_code"

    multi_set = result.model_copy(
        update={
            "required": (
                InferenceRequirementSetV2(
                    requirement_id="required_1", options=(_option(("D-code",), "0.9"),)
                ),
                InferenceRequirementSetV2(
                    requirement_id="required_2", options=(_option(("E-code",), "0.8"),)
                ),
            ),
            "recommended": (),
        }
    )
    multi_work, multi_attempt, multi_run = _records(multi_set, descriptors)
    referenced = {course.group_id: course for course in candidates}
    with pytest.raises(TargetResultError) as multi_error:
        compose_target_proposal(
            multi_work,
            multi_attempt,
            multi_run,
            descriptors,
            target,
            tuple(referenced[group_id] for group_id in sorted(referenced)),
            "v1",
        )
    assert multi_error.value.reason == "multiple_requirement_sets"

    # A too-basic suppressed candidate is retained as raw routing evidence, never a direct leaf.
    suppressed_candidate = _course("S")
    suppressed_result = result.model_copy(
        update={
            "required": (
                InferenceRequirementSetV2(
                    requirement_id="required_1", options=(_option(("D-code", "E-code"), "0.8"),)
                ),
            ),
            "recommended": (),
            "routing": InferenceRoutingMetadata(
                confidence=Decimal("0.7"),
                flags=(),
                suppressed=(
                    InferenceSuppressedCandidate(
                        course_code="S-code",
                        outcome=DirectnessOutcome.TOO_BASIC_TRANSITIVE,
                        evidence="general foundation below entry level",
                    ),
                ),
            ),
        }
    )
    suppressed_descriptors = _descriptors(target, (*candidates, suppressed_candidate))
    suppressed_work, suppressed_attempt, suppressed_run = _records(
        suppressed_result, suppressed_descriptors
    )
    suppressed_referenced = {
        course.group_id: course for course in (*candidates, suppressed_candidate)
    }
    suppressed = compose_target_proposal(
        suppressed_work,
        suppressed_attempt,
        suppressed_run,
        suppressed_descriptors,
        target,
        (suppressed_referenced["D"], suppressed_referenced["E"], suppressed_referenced["S"]),
        "v1",
    )
    assert isinstance(suppressed.expression, AndRequirement)
    assert _codes(suppressed.expression) == ["D", "E"]
    assert "S" not in _codes(suppressed.expression)


def test_equivalence_dedup_retains_exact_supporters() -> None:
    """Only the exact target+singleton substitute group drops. Larger and overlapping stay whole."""
    target, candidates, result = _equivalence_fixture()
    descriptors = _descriptors(target, candidates)
    work, attempt, run = _records(result, descriptors)
    referenced = {course.group_id: course for course in candidates}

    proposal = compose_target_proposal(
        work,
        attempt,
        run,
        descriptors,
        target,
        tuple(referenced[group_id] for group_id in sorted(referenced)),
        "v1",
    )

    assert [candidate.members for candidate in proposal.equivalence] == [
        ("A", "T", "X"),
        ("B", "C", "T"),
        ("T", "X"),
    ]
    assert proposal.equivalence[0].inference.confidence == Decimal("0.8")
    assert proposal.equivalence[0].inference.evidence[0].kind is (
        InferenceEvidenceKind.EXPRESSION_PROPOSAL
    )
    assert proposal.equivalence[0].inference.evidence[0].reference_id == str(proposal.proposal_id)

    # Exact duplicates across targets consolidate. Overlapping groups never merge.
    other = proposal.model_copy(
        update={"proposal_id": UUID(int=77), "identity_sha256": _hash("other")}
    )
    groups = aggregate_equivalence_candidates((proposal, other))
    assert [tuple(candidate.members for _, candidate in group) for group in groups] == [
        (("A", "T", "X"), ("A", "T", "X")),
        (("B", "C", "T"), ("B", "C", "T")),
        (("T", "X"), ("T", "X")),
    ]
    assert [proposal_id for proposal_id, _ in groups[0]] == sorted(
        (proposal.proposal_id, other.proposal_id)
    )


def test_descriptor_projection_is_exact_and_label_free() -> None:
    """The current descriptor projection reads code/group/source directly from a packet."""
    packet = target_packet(2)
    descriptors = request_descriptors_from_packet(packet)
    assert descriptors.target.group_id == packet.target.identity.group_id
    assert descriptors.target.course_code == packet.target.course_code
    assert (
        descriptors.target.representative_source_sha256
        == packet.target.identity.representative_source_sha256
    )
    assert tuple(candidate.group_id for candidate in descriptors.candidates) == tuple(
        candidate.course.identity.group_id for candidate in packet.candidates
    )
