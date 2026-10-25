"""Shared fixtures for the inference proposal composition tests."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from course_explorer.curriculum import (
    CatalogueCourse,
    CatalogueCourseVersion,
    CataloguePrerequisiteMember,
    CataloguePrerequisiteOption,
    CatalogueSubstitutionMember,
    CatalogueSubstitutionOption,
    CatalogueTeachingText,
)
from course_explorer.enums import (
    InferenceWorkStatus,
    PrerequisiteMemberType,
    PrerequisiteRequirementKind,
)
from course_explorer.inference.context import (
    RequestCourseDescriptor,
    RequestCourseDescriptors,
)
from course_explorer.inference.domain import (
    InferenceCourseOptionV2,
    InferenceEquivalenceProposalV2,
    InferenceRequirementSetV2,
    InferenceRoutingMetadata,
    InferenceTargetResultV2,
    OptionFlag,
)
from course_explorer.inference.evidence import (
    InferenceCompletionFacts,
    InferenceCompletionPayload,
    InferenceModelAttemptRecord,
    InferencePipelineRunSpec,
    InferenceTargetWorkRecord,
    InferenceTargetWorkRequest,
    run_identity_sha256,
    work_key_sha256,
)
from course_explorer.prerequisite.domain import (
    AndRequirement,
    CourseRequirement,
    OrRequirement,
)
from tests.inference._fixture_support import fixture_sha256 as _hash

STARTED_AT = datetime(2026, 9, 29, 10, 0, tzinfo=UTC)
_MODEL_IDENTITY = "Qwen/Qwen3.8-27B-FP8@rev;artifact=x@rev/f.gguf;quant=IQ3_MIX;sha256=" + "9" * 64
_RUNTIME_IDENTITY = "llama.cpp@rev;alias=a;context=131072"


def _representative(
    group_id: str,
    prerequisite_options: tuple[CataloguePrerequisiteOption, ...],
    substitution_options: tuple[CatalogueSubstitutionOption, ...],
) -> CatalogueCourseVersion:
    """Build the selected representative of one fixture course with a labelled source digest."""
    return CatalogueCourseVersion(
        sisu_course_unit_id=f"sisu-{group_id}",
        source_hash=_hash(f"source-{group_id}"),
        code=f"{group_id}-code",
        credits_min=Decimal("5"),
        official_url=f"https://example.test/courses/{group_id}",
        document_state="ACTIVE",
        curriculum_period_ids=("period",),
        teaching_text=CatalogueTeachingText(),
        prerequisite_options=prerequisite_options,
        substitution_options=substitution_options,
    )


def _course(
    group_id: str,
    *,
    prerequisite_options: tuple[CataloguePrerequisiteOption, ...] = (),
    substitution_options: tuple[CatalogueSubstitutionOption, ...] = (),
) -> CatalogueCourse:
    """Build one active canonical course whose displayed code differs from its group ID."""
    return CatalogueCourse(
        group_id=group_id,
        is_active=True,
        activity_as_of_academic_year_start=2026,
        activity_window_years=3,
        representative=_representative(group_id, prerequisite_options, substitution_options),
    )


def _prerequisite_option(
    option_index: int,
    requirement_kind: PrerequisiteRequirementKind,
    members: tuple[tuple[PrerequisiteMemberType, str], ...],
) -> CataloguePrerequisiteOption:
    """Build one official prerequisite option from ordered (member type, group ID) pairs."""
    return CataloguePrerequisiteOption(
        option_index=option_index,
        requirement_kind=requirement_kind,
        members=tuple(
            CataloguePrerequisiteMember(
                member_index=index, member_type=member_type, referenced_group_id=group_id
            )
            for index, (member_type, group_id) in enumerate(members)
        ),
    )


def _descriptor(course: CatalogueCourse) -> RequestCourseDescriptor:
    representative = course.representative
    assert representative is not None
    return RequestCourseDescriptor(
        group_id=course.group_id,
        course_code=representative.code,
        representative_source_sha256=representative.source_hash,
    )


def _descriptors(
    target: CatalogueCourse, candidates: tuple[CatalogueCourse, ...]
) -> RequestCourseDescriptors:
    """Build the resolved request descriptors for one target and its ordered candidates."""
    return RequestCourseDescriptors(
        target=_descriptor(target),
        candidates=tuple(_descriptor(candidate) for candidate in candidates),
    )


def _records(
    result: InferenceTargetResultV2, descriptors: RequestCourseDescriptors
) -> tuple[InferenceTargetWorkRecord, InferenceModelAttemptRecord]:
    """Build the completed work and its completion for one result."""
    spec = InferencePipelineRunSpec(
        model_identity=_MODEL_IDENTITY,
        runtime_identity=_RUNTIME_IDENTITY,
        prompt_version="v9",
        schema_version="v2",
        pipeline_version="v1",
        configuration={"route": "local"},
    )
    run_identity = run_identity_sha256(spec)
    work_request = InferenceTargetWorkRequest(
        target_group_id="T",
        activity_as_of_academic_year_start=2026,
        activity_window_years=3,
    )
    work = InferenceTargetWorkRecord(
        work_id=UUID(int=2),
        created_by_run_id=UUID(int=1),
        target_course_id=UUID(int=99),
        request=work_request,
        work_key_sha256=work_key_sha256(work_request, run_identity, _hash("input")),
        status=InferenceWorkStatus.COMPLETED,
    )
    completion = InferenceModelAttemptRecord(
        attempt_id=UUID(int=3),
        target_work_id=work.work_id,
        payload=InferenceCompletionPayload(
            facts=InferenceCompletionFacts(
                target_teaching_text_sha256=_hash("text"),
                candidate_count=len(descriptors.candidates),
            ),
            descriptors=descriptors,
            result=result,
        ),
        finished_at=STARTED_AT,
    )
    return work, completion


def _option(
    codes: tuple[str, ...], confidence: str, flags: tuple[OptionFlag, ...] = ()
) -> InferenceCourseOptionV2:
    """Build one v2 inferred option with a stable evidence string."""
    return InferenceCourseOptionV2(
        course_codes=codes,
        evidence="direct entry knowledge",
        confidence=Decimal(confidence),
        finding_flags=flags,
    )


def _required_option_codes(expression: object) -> list[object]:
    """Return the required option nodes of a composed expression for assertion."""
    assert isinstance(expression, AndRequirement)
    required_pool = expression.children[0]
    assert isinstance(required_pool, OrRequirement)
    return list(required_pool.children)


def _codes(node: object) -> list[str]:
    """Return an option node's canonical course group IDs in order."""
    if isinstance(node, CourseRequirement):
        return [node.course_group_id]
    assert isinstance(node, AndRequirement)
    return [
        child.course_group_id for child in node.children if isinstance(child, CourseRequirement)
    ]


def _category_fixture() -> tuple[
    CatalogueCourse, tuple[CatalogueCourse, ...], InferenceTargetResultV2
]:
    """Build one target, its named candidates, and a two-category v2 result for dedup proofs."""
    target = _course(
        "T",
        prerequisite_options=(
            _prerequisite_option(
                0, PrerequisiteRequirementKind.COMPULSORY, ((PrerequisiteMemberType.COURSE, "A"),)
            ),
            _prerequisite_option(
                1, PrerequisiteRequirementKind.RECOMMENDED, ((PrerequisiteMemberType.COURSE, "J"),)
            ),
            _prerequisite_option(
                2, PrerequisiteRequirementKind.COMPULSORY, ((PrerequisiteMemberType.MODULE, "M"),)
            ),
            _prerequisite_option(
                3,
                PrerequisiteRequirementKind.COMPULSORY,
                ((PrerequisiteMemberType.COURSE, "G"), (PrerequisiteMemberType.COURSE, "H")),
            ),
            _prerequisite_option(
                4,
                PrerequisiteRequirementKind.COMPULSORY,
                ((PrerequisiteMemberType.COURSE, "X"), (PrerequisiteMemberType.MODULE, "M")),
            ),
            _prerequisite_option(
                5, PrerequisiteRequirementKind.COMPULSORY, ((PrerequisiteMemberType.COURSE, "Q"),)
            ),
        ),
    )
    codes = ("A", "D", "E", "G", "I", "X", "Y", "Q", "N", "J", "K", "L")
    candidates = tuple(_course(code) for code in codes)
    result = InferenceTargetResultV2(
        required=(
            InferenceRequirementSetV2(
                requirement_id="required_1",
                options=(
                    _option(("A-code",), "0.9"),
                    _option(("D-code", "E-code"), "0.8", (OptionFlag.REQUIREDNESS_UNCERTAIN,)),
                    _option(("G-code", "I-code"), "0.7"),
                    _option(("X-code", "Y-code"), "0.6"),
                ),
            ),
        ),
        recommended=(
            InferenceRequirementSetV2(
                requirement_id="recommended_1",
                options=(
                    _option(("Q-code", "N-code"), "0.5", (OptionFlag.MEMBER_UNCERTAIN,)),
                    _option(("Q-code",), "0.4"),
                    _option(("J-code", "K-code"), "0.3"),
                    _option(("L-code",), "0.2"),
                ),
            ),
        ),
        equivalence=(),
        routing=InferenceRoutingMetadata(confidence=Decimal("0.75"), flags=(), suppressed=()),
    )
    return target, candidates, result


def _equivalence_fixture() -> tuple[
    CatalogueCourse, tuple[CatalogueCourse, ...], InferenceTargetResultV2
]:
    """Build one target with a singleton and a multi-member substitution option and groups."""
    target = _course(
        "T",
        substitution_options=(
            CatalogueSubstitutionOption(
                option_index=0,
                members=(
                    CatalogueSubstitutionMember(member_index=0, course_group_id="A", credits=None),
                ),
            ),
            CatalogueSubstitutionOption(
                option_index=1,
                members=(
                    CatalogueSubstitutionMember(member_index=0, course_group_id="B", credits=None),
                    CatalogueSubstitutionMember(member_index=1, course_group_id="C", credits=None),
                ),
            ),
        ),
    )
    candidates = tuple(_course(code) for code in ("A", "B", "C", "X"))
    result = InferenceTargetResultV2(
        required=(),
        recommended=(),
        equivalence=(
            InferenceEquivalenceProposalV2(
                members=("T-code", "A-code"),
                evidence="interchangeable",
                confidence=Decimal("0.9"),
                finding_flags=(),
            ),
            InferenceEquivalenceProposalV2(
                members=("T-code", "A-code", "X-code"),
                evidence="interchangeable",
                confidence=Decimal("0.8"),
                finding_flags=(),
            ),
            InferenceEquivalenceProposalV2(
                members=("T-code", "B-code", "C-code"),
                evidence="interchangeable",
                confidence=Decimal("0.7"),
                finding_flags=(),
            ),
            InferenceEquivalenceProposalV2(
                members=("T-code", "X-code"),
                evidence="interchangeable",
                confidence=Decimal("0.6"),
                finding_flags=(),
            ),
        ),
        routing=InferenceRoutingMetadata(confidence=Decimal("0.5"), flags=(), suppressed=()),
    )
    return target, candidates, result
