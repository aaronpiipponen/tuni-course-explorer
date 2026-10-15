"""Validated normalization of the current Kori ingestion run's capture.

This module owns source-shaped validation, official-expression preservation, typed module-rule
conversion, and the DTO seam consumed by the transactional normalization repository. It never
fetches source data or writes files/database rows.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal, Protocol, Self
from urllib.parse import quote
from uuid import UUID

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, field_validator, model_validator

from course_explorer.config import validate_course_guide_base_url
from course_explorer.enums import (
    IngestionRunStatus,
    ModuleRuleType,
    ModuleType,
    PrerequisiteMemberType,
    PrerequisiteRequirementKind,
    SourceObjectType,
)
from course_explorer.ingestion.manifest import RawCaptureStore, ReplayedSourceObject


class _SourceModel(BaseModel):
    """Permit unrelated source fields while validating fields owned by normalization."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)


class _StrictSourceModel(_SourceModel):
    """Reject unknown fields in official semantic expression and rule nodes."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


def _nonblank(value: str, field_name: str) -> str:
    if not value.strip():
        raise ValueError(f"{field_name} must not be blank")
    return value


class _LocalizedText(_SourceModel):
    fi: str | None = None
    en: str | None = None


class _DecimalRange(_SourceModel):
    minimum: Decimal = Field(alias="min", ge=0)
    maximum: Decimal | None = Field(default=None, alias="max", ge=0)

    @model_validator(mode="after")
    def validate_order(self) -> Self:
        if self.maximum is not None and self.minimum > self.maximum:
            raise ValueError("decimal range minimum must not exceed maximum")
        return self


class _OptionalDecimalRange(_SourceModel):
    minimum: Decimal | None = Field(default=None, alias="min", ge=0)
    maximum: Decimal | None = Field(default=None, alias="max", ge=0)

    @model_validator(mode="after")
    def validate_order(self) -> Self:
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError("optional decimal range minimum must not exceed maximum")
        return self


class _IntegerRange(_SourceModel):
    minimum: int = Field(alias="min", ge=0)
    maximum: int | None = Field(default=None, alias="max", ge=0)

    @model_validator(mode="after")
    def validate_order(self) -> Self:
        if self.maximum is not None and self.minimum > self.maximum:
            raise ValueError("integer range minimum must not exceed maximum")
        return self


class _DateRange(_SourceModel):
    start_date: date | None = Field(default=None, alias="startDate")
    end_date: date | None = Field(default=None, alias="endDate")

    @model_validator(mode="after")
    def validate_order(self) -> Self:
        if (
            self.start_date is not None
            and self.end_date is not None
            and self.start_date > self.end_date
        ):
            raise ValueError("date range start must not exceed end")
        return self


class _SourceMetadata(_SourceModel):
    revision: int | None = Field(default=None, ge=0)
    modification_ordinal: int | None = Field(default=None, alias="modificationOrdinal", ge=0)


class _SourceActivePeriod(_SourceModel):
    start_date: date = Field(alias="startDate")


class _SourcePeriod(_SourceModel):
    id: str
    active_period: _SourceActivePeriod = Field(alias="activePeriod")

    _id = field_validator("id")(lambda value: _nonblank(value, "period id"))


class _CoursePrerequisite(_StrictSourceModel):
    type: Literal["CourseUnit"]
    course_group_id: str = Field(alias="courseUnitGroupId")

    _group_id = field_validator("course_group_id")(
        lambda value: _nonblank(value, "courseUnitGroupId")
    )


class _ModulePrerequisite(_StrictSourceModel):
    type: Literal["Module"]
    module_group_id: str = Field(alias="moduleGroupId")

    _group_id = field_validator("module_group_id")(lambda value: _nonblank(value, "moduleGroupId"))


_PrerequisiteMember = Annotated[
    _CoursePrerequisite | _ModulePrerequisite,
    Field(discriminator="type"),
]


class _PrerequisiteGroup(_StrictSourceModel):
    prerequisites: tuple[_PrerequisiteMember, ...]


class _SubstitutionMember(_StrictSourceModel):
    course_group_id: str = Field(alias="courseUnitGroupId")
    credits: Decimal | None = Field(default=None, ge=0)

    _group_id = field_validator("course_group_id")(
        lambda value: _nonblank(value, "courseUnitGroupId")
    )


class _CompositeRule(_StrictSourceModel):
    type: Literal["CompositeRule"]
    local_id: str | None = Field(default=None, alias="localId")
    rules: tuple[_SourceRule, ...]
    require: _IntegerRange | None = None
    description: _LocalizedText | None = None
    all_mandatory: bool | None = Field(default=None, alias="allMandatory")


class _CreditsRule(_StrictSourceModel):
    type: Literal["CreditsRule"]
    local_id: str | None = Field(default=None, alias="localId")
    credits: _DecimalRange
    rule: _SourceRule


class _CourseUnitCountRule(_StrictSourceModel):
    type: Literal["CourseUnitCountRule"]
    local_id: str | None = Field(default=None, alias="localId")
    count: _IntegerRange
    rule: _SourceRule


class _CourseUnitRule(_StrictSourceModel):
    type: Literal["CourseUnitRule"]
    local_id: str | None = Field(default=None, alias="localId")
    course_group_id: str = Field(alias="courseUnitGroupId")

    _group_id = field_validator("course_group_id")(
        lambda value: _nonblank(value, "courseUnitGroupId")
    )


class _ModuleRule(_StrictSourceModel):
    type: Literal["ModuleRule"]
    local_id: str | None = Field(default=None, alias="localId")
    module_group_id: str = Field(alias="moduleGroupId")

    _group_id = field_validator("module_group_id")(lambda value: _nonblank(value, "moduleGroupId"))


class _AnyCourseUnitRule(_StrictSourceModel):
    type: Literal["AnyCourseUnitRule"]
    local_id: str | None = Field(default=None, alias="localId")


class _AnyModuleRule(_StrictSourceModel):
    type: Literal["AnyModuleRule"]
    local_id: str | None = Field(default=None, alias="localId")


_SourceRule = Annotated[
    _CompositeRule
    | _CreditsRule
    | _CourseUnitCountRule
    | _CourseUnitRule
    | _ModuleRule
    | _AnyCourseUnitRule
    | _AnyModuleRule,
    Field(discriminator="type"),
]

_CompositeRule.model_rebuild()
_CreditsRule.model_rebuild()
_CourseUnitCountRule.model_rebuild()


class _SourceCourse(_SourceModel):
    id: str
    group_id: str = Field(alias="groupId")
    code: str | None
    name: _LocalizedText
    credits: _DecimalRange
    curriculum_period_ids: tuple[str, ...] = Field(alias="curriculumPeriodIds")
    document_state: str = Field(alias="documentState")
    validity_period: _DateRange = Field(alias="validityPeriod")
    metadata: _SourceMetadata | None = None
    content: _LocalizedText | None = None
    outcomes: _LocalizedText | None = None
    prerequisites: _LocalizedText | None = None
    additional: _LocalizedText | None = None
    compulsory_formal_prerequisites: tuple[_PrerequisiteGroup, ...] | None = Field(
        default=None, alias="compulsoryFormalPrerequisites"
    )
    recommended_formal_prerequisites: tuple[_PrerequisiteGroup, ...] | None = Field(
        default=None, alias="recommendedFormalPrerequisites"
    )
    substitutions: tuple[tuple[_SubstitutionMember, ...], ...] | None = None

    _id = field_validator("id", "group_id", "document_state")(
        lambda value: _nonblank(value, "course source field")
    )

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: str | None) -> str | None:
        return None if value is None else _nonblank(value, "course code")

    @field_validator("curriculum_period_ids")
    @classmethod
    def validate_period_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not item.strip() for item in value) or len(value) != len(set(value)):
            raise ValueError("course curriculum period IDs must be nonblank and unique")
        return value


class _SourceModule(_SourceModel):
    id: str
    group_id: str = Field(alias="groupId")
    type: ModuleType
    code: str | None = None
    name: _LocalizedText
    target_credits: _OptionalDecimalRange | None = Field(default=None, alias="targetCredits")
    curriculum_period_ids: tuple[str, ...] = Field(default=(), alias="curriculumPeriodIds")
    document_state: str = Field(alias="documentState")
    validity_period: _DateRange | None = Field(default=None, alias="validityPeriod")
    metadata: _SourceMetadata | None = None
    rule: _SourceRule | None

    _id = field_validator("id", "group_id", "document_state")(
        lambda value: _nonblank(value, "module source field")
    )

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: str | None) -> str | None:
        return None if value is None or not value.strip() else value

    @field_validator("curriculum_period_ids")
    @classmethod
    def validate_period_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not item.strip() for item in value) or len(value) != len(set(value)):
            raise ValueError("module curriculum period IDs must be nonblank and unique")
        return value


class _OutputModel(BaseModel):
    """Frozen DTO base that prevents accidental normalized-field expansion."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class NormalizedPeriod(_OutputModel):
    id: str
    academic_year_start: int


class SnapshotProvenance(_OutputModel):
    object_type: SourceObjectType
    source_object_id: str
    source_group_id: str
    response_path: str
    response_item_index: int
    source_hash: str


class NormalizedPrerequisiteMember(_OutputModel):
    member_index: int
    member_type: PrerequisiteMemberType
    referenced_group_id: str


class NormalizedPrerequisiteOption(_OutputModel):
    option_index: int
    requirement_kind: PrerequisiteRequirementKind
    members: tuple[NormalizedPrerequisiteMember, ...]


class NormalizedSubstitutionMember(_OutputModel):
    member_index: int
    course_group_id: str
    credits: Decimal | None


class NormalizedSubstitutionOption(_OutputModel):
    option_index: int
    members: tuple[NormalizedSubstitutionMember, ...]


class NormalizedModuleRule(_OutputModel):
    sibling_position: int
    local_id: str | None
    node_type: ModuleRuleType
    require_min: int | None
    require_max: int | None
    all_mandatory: bool | None
    description: dict[str, str] | None
    credits_min: Decimal | None
    credits_max: Decimal | None
    count_min: int | None
    count_max: int | None
    referenced_group_id: str | None
    children: tuple[NormalizedModuleRule, ...]


class NormalizedCourseVersion(_OutputModel):
    provenance: SnapshotProvenance
    group_id: str
    code: str
    name_fi: str | None
    name_en: str | None
    credits_min: Decimal
    credits_max: Decimal | None
    official_url: str
    document_state: str
    validity_start: date | None
    validity_end: date | None
    source_revision: int | None
    source_modification_ordinal: int | None
    curriculum_period_ids: tuple[str, ...]
    content_fi: str | None
    content_en: str | None
    outcomes_fi: str | None
    outcomes_en: str | None
    prerequisite_text_fi: str | None
    prerequisite_text_en: str | None
    additional_info_fi: str | None
    additional_info_en: str | None
    prerequisite_options: tuple[NormalizedPrerequisiteOption, ...]
    substitution_options: tuple[NormalizedSubstitutionOption, ...]


class NormalizedModuleVersion(_OutputModel):
    provenance: SnapshotProvenance
    group_id: str
    module_type: ModuleType
    code: str | None
    name_fi: str | None
    name_en: str | None
    target_credits_min: Decimal | None
    target_credits_max: Decimal | None
    document_state: str
    validity_start: date | None
    validity_end: date | None
    source_revision: int | None
    source_modification_ordinal: int | None
    curriculum_period_ids: tuple[str, ...]
    rule: NormalizedModuleRule | None


class NormalizationBatch(_OutputModel):
    run_id: UUID
    periods: tuple[NormalizedPeriod, ...]
    courses: tuple[NormalizedCourseVersion, ...]
    excluded_null_code_course_versions: tuple[SnapshotProvenance, ...]
    modules: tuple[NormalizedModuleVersion, ...]
    unresolved_course_group_ids: tuple[str, ...]
    unresolved_module_group_ids: tuple[str, ...]


class NormalizationReport(_OutputModel):
    """Counts and change classifications produced by one transactional apply."""

    run_id: UUID
    period_count: int = Field(ge=0)
    canonical_course_count: int = Field(ge=0)
    active_course_count: int = Field(ge=0)
    canonical_module_count: int = Field(ge=0)
    course_version_count: int = Field(ge=0)
    excluded_null_code_course_versions: tuple[SnapshotProvenance, ...]
    new_course_version_count: int = Field(ge=0)
    changed_course_version_count: int = Field(ge=0)
    unchanged_course_version_count: int = Field(ge=0)
    module_version_count: int = Field(ge=0)
    new_module_version_count: int = Field(ge=0)
    changed_module_version_count: int = Field(ge=0)
    unchanged_module_version_count: int = Field(ge=0)
    representative_changed_course_count: int = Field(ge=0)
    unresolved_course_group_count: int = Field(ge=0)
    unresolved_module_group_count: int = Field(ge=0)
    unrestricted_rule_count: int = Field(ge=0)


class NormalizationPersistence(Protocol):
    """Transactional writer used by current-run ingestion normalization."""

    def apply(
        self,
        batch: NormalizationBatch,
        *,
        current_academic_year_start: int,
        activity_window_years: int,
    ) -> NormalizationReport: ...


def _localized(value: _LocalizedText | None) -> tuple[str | None, str | None]:
    return (None, None) if value is None else (value.fi, value.en)


def _snapshot(replayed: ReplayedSourceObject) -> SnapshotProvenance:
    return SnapshotProvenance(
        object_type=replayed.record.object_type,
        source_object_id=replayed.record.source_object_id,
        source_group_id=replayed.record.source_group_id,
        response_path=replayed.response_path,
        response_item_index=replayed.record.response_item_index,
        source_hash=replayed.record.source_hash,
    )


def _prerequisite_options(
    groups: tuple[_PrerequisiteGroup, ...] | None,
    kind: PrerequisiteRequirementKind,
) -> tuple[NormalizedPrerequisiteOption, ...]:
    if groups is None:
        return ()
    return tuple(
        NormalizedPrerequisiteOption(
            option_index=index,
            requirement_kind=kind,
            members=tuple(
                NormalizedPrerequisiteMember(
                    member_index=member_index,
                    member_type=(
                        PrerequisiteMemberType.COURSE
                        if isinstance(member, _CoursePrerequisite)
                        else PrerequisiteMemberType.MODULE
                    ),
                    referenced_group_id=(
                        member.course_group_id
                        if isinstance(member, _CoursePrerequisite)
                        else member.module_group_id
                    ),
                )
                for member_index, member in enumerate(group.prerequisites)
            ),
        )
        for index, group in enumerate(groups)
    )


def _course_prerequisites(course: _SourceCourse) -> tuple[NormalizedPrerequisiteOption, ...]:
    compulsory = _prerequisite_options(
        course.compulsory_formal_prerequisites, PrerequisiteRequirementKind.COMPULSORY
    )
    recommended = _prerequisite_options(
        course.recommended_formal_prerequisites, PrerequisiteRequirementKind.RECOMMENDED
    )
    return compulsory + recommended


def _substitutions(course: _SourceCourse) -> tuple[NormalizedSubstitutionOption, ...]:
    if course.substitutions is None:
        return ()
    return tuple(
        NormalizedSubstitutionOption(
            option_index=option_index,
            members=tuple(
                NormalizedSubstitutionMember(
                    member_index=member_index,
                    course_group_id=member.course_group_id,
                    credits=member.credits,
                )
                for member_index, member in enumerate(option)
            ),
        )
        for option_index, option in enumerate(course.substitutions)
    )


def _module_rule(rule: _SourceRule, sibling_position: int) -> NormalizedModuleRule:
    node_type = ModuleRuleType(rule.type)
    require_min = require_max = None
    all_mandatory = None
    description = None
    credits_min = credits_max = None
    count_min = count_max = None
    referenced_group_id = None
    children: tuple[NormalizedModuleRule, ...] = ()

    if isinstance(rule, _CompositeRule):
        require_min = rule.require.minimum if rule.require is not None else None
        require_max = rule.require.maximum if rule.require is not None else None
        all_mandatory = rule.all_mandatory
        description = (
            None if rule.description is None else rule.description.model_dump(exclude_none=True)
        )
        children = tuple(_module_rule(child, index) for index, child in enumerate(rule.rules))
    elif isinstance(rule, _CreditsRule):
        credits_min = rule.credits.minimum
        credits_max = rule.credits.maximum
        children = (_module_rule(rule.rule, 0),)
    elif isinstance(rule, _CourseUnitCountRule):
        count_min = rule.count.minimum
        count_max = rule.count.maximum
        children = (_module_rule(rule.rule, 0),)
    elif isinstance(rule, _CourseUnitRule):
        referenced_group_id = rule.course_group_id
    elif isinstance(rule, _ModuleRule):
        referenced_group_id = rule.module_group_id

    return NormalizedModuleRule(
        sibling_position=sibling_position,
        local_id=rule.local_id,
        node_type=node_type,
        require_min=require_min,
        require_max=require_max,
        all_mandatory=all_mandatory,
        description=description,
        credits_min=credits_min,
        credits_max=credits_max,
        count_min=count_min,
        count_max=count_max,
        referenced_group_id=referenced_group_id,
        children=children,
    )


def _course_version(
    replayed: ReplayedSourceObject,
    course: _SourceCourse,
    course_guide_base_url: AnyHttpUrl,
    *,
    code: str,
) -> NormalizedCourseVersion:
    name_fi, name_en = _localized(course.name)
    content_fi, content_en = _localized(course.content)
    outcomes_fi, outcomes_en = _localized(course.outcomes)
    prerequisite_text_fi, prerequisite_text_en = _localized(course.prerequisites)
    additional_info_fi, additional_info_en = _localized(course.additional)
    return NormalizedCourseVersion(
        provenance=_snapshot(replayed),
        group_id=course.group_id,
        code=code,
        name_fi=name_fi,
        name_en=name_en,
        credits_min=course.credits.minimum,
        credits_max=course.credits.maximum,
        official_url=(
            f"{str(course_guide_base_url).rstrip('/')}/{quote(course.id, safe='')}/brochure"
        ),
        document_state=course.document_state,
        validity_start=course.validity_period.start_date,
        validity_end=course.validity_period.end_date,
        source_revision=None if course.metadata is None else course.metadata.revision,
        source_modification_ordinal=(
            None if course.metadata is None else course.metadata.modification_ordinal
        ),
        curriculum_period_ids=course.curriculum_period_ids,
        content_fi=content_fi,
        content_en=content_en,
        outcomes_fi=outcomes_fi,
        outcomes_en=outcomes_en,
        prerequisite_text_fi=prerequisite_text_fi,
        prerequisite_text_en=prerequisite_text_en,
        additional_info_fi=additional_info_fi,
        additional_info_en=additional_info_en,
        prerequisite_options=_course_prerequisites(course),
        substitution_options=_substitutions(course),
    )


def _module_version(
    replayed: ReplayedSourceObject, module: _SourceModule
) -> NormalizedModuleVersion:
    name_fi, name_en = _localized(module.name)
    return NormalizedModuleVersion(
        provenance=_snapshot(replayed),
        group_id=module.group_id,
        module_type=module.type,
        code=module.code,
        name_fi=name_fi,
        name_en=name_en,
        target_credits_min=(
            None if module.target_credits is None else module.target_credits.minimum
        ),
        target_credits_max=(
            None if module.target_credits is None else module.target_credits.maximum
        ),
        document_state=module.document_state,
        validity_start=None
        if module.validity_period is None
        else module.validity_period.start_date,
        validity_end=None if module.validity_period is None else module.validity_period.end_date,
        source_revision=None if module.metadata is None else module.metadata.revision,
        source_modification_ordinal=(
            None if module.metadata is None else module.metadata.modification_ordinal
        ),
        curriculum_period_ids=module.curriculum_period_ids,
        rule=None if module.rule is None else _module_rule(module.rule, 0),
    )


def walk_normalized_rule(rule: NormalizedModuleRule) -> Iterator[NormalizedModuleRule]:
    """Yield one normalized module-rule tree depth-first, deepest children last."""
    yield rule
    for child in rule.children:
        yield from walk_normalized_rule(child)


def _validate_reference_closure(
    courses: tuple[NormalizedCourseVersion, ...],
    modules: tuple[NormalizedModuleVersion, ...],
    excluded_course_group_ids: frozenset[str],
    unresolved_courses: tuple[str, ...],
    unresolved_modules: tuple[str, ...],
) -> None:
    represented_courses = {course.group_id for course in courses}
    resolved_courses = represented_courses | excluded_course_group_ids
    represented_modules = {module.group_id for module in modules}
    if resolved_courses & set(unresolved_courses) or represented_modules & set(unresolved_modules):
        raise ValueError("represented and unresolved typed group IDs overlap")
    for course in courses:
        references = {
            member.referenced_group_id
            for option in course.prerequisite_options
            for member in option.members
            if member.member_type is PrerequisiteMemberType.COURSE
        }
        references.update(
            member.course_group_id
            for option in course.substitution_options
            for member in option.members
        )
        invalid = references - resolved_courses - set(unresolved_courses)
        if invalid:
            raise ValueError(f"unresolved course references absent from closure: {sorted(invalid)}")
        module_references = {
            member.referenced_group_id
            for option in course.prerequisite_options
            for member in option.members
            if member.member_type is PrerequisiteMemberType.MODULE
        }
        invalid_modules = module_references - represented_modules - set(unresolved_modules)
        if invalid_modules:
            raise ValueError(
                f"unresolved module references absent from closure: {sorted(invalid_modules)}"
            )
    for module in modules:
        if module.rule is None:
            continue
        for node in walk_normalized_rule(module.rule):
            if node.node_type is ModuleRuleType.COURSE_UNIT_RULE:
                if node.referenced_group_id not in resolved_courses | set(unresolved_courses):
                    raise ValueError("module rule references absent from course closure")
            elif node.node_type is ModuleRuleType.MODULE_RULE:
                if node.referenced_group_id not in represented_modules | set(unresolved_modules):
                    raise ValueError("module rule references absent from module closure")


def parse_capture(
    store: RawCaptureStore, *, course_guide_base_url: AnyHttpUrl
) -> NormalizationBatch:
    """Parse the current run's completed verified capture into immutable normalized DTOs."""
    validated_course_guide_base_url = validate_course_guide_base_url(course_guide_base_url)
    if store.manifest.status is not IngestionRunStatus.COMPLETED:
        raise ValueError("normalization requires a completed capture manifest")

    period_responses = tuple(store.iter_responses(request_path="/api/curriculum-periods"))
    if len(period_responses) != 1:
        raise ValueError("capture must contain exactly one curriculum-periods response")
    try:
        raw_periods = json.loads(period_responses[0].body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("curriculum-periods response must be valid JSON") from exc
    if not isinstance(raw_periods, list):
        raise ValueError("curriculum-periods response must be a JSON list")
    source_periods = tuple(_SourcePeriod.model_validate(value) for value in raw_periods)
    period_years = {period.id: period.active_period.start_date.year for period in source_periods}
    if len(period_years) != len(source_periods):
        raise ValueError("curriculum-periods response contains duplicate IDs")
    selected_periods = {period.id: period.academic_year_start for period in store.manifest.periods}
    if any(period_years.get(identifier) != year for identifier, year in selected_periods.items()):
        raise ValueError("manifest period selection does not match captured period evidence")

    courses: list[NormalizedCourseVersion] = []
    excluded_null_code_course_versions: list[SnapshotProvenance] = []
    modules: list[NormalizedModuleVersion] = []
    seen: dict[tuple[SourceObjectType, str], tuple[str, str]] = {}
    for replayed in store.iter_objects():
        key = (replayed.record.object_type, replayed.record.source_object_id)
        identity = (replayed.record.source_group_id, replayed.record.source_hash)
        previous = seen.get(key)
        if previous is not None:
            if previous != identity:
                raise ValueError("repeated source object has conflicting identity or hash")
            continue
        seen[key] = identity
        if replayed.record.object_type is SourceObjectType.COURSE_UNIT:
            course = _SourceCourse.model_validate(replayed.value)
            if any(identifier not in period_years for identifier in course.curriculum_period_ids):
                raise ValueError("course membership references missing period evidence")
            if course.code is None:
                excluded_null_code_course_versions.append(_snapshot(replayed))
            else:
                courses.append(
                    _course_version(
                        replayed, course, validated_course_guide_base_url, code=course.code
                    )
                )
        elif replayed.record.object_type is SourceObjectType.MODULE:
            module = _SourceModule.model_validate(replayed.value)
            if any(identifier not in period_years for identifier in module.curriculum_period_ids):
                raise ValueError("module membership references missing period evidence")
            modules.append(_module_version(replayed, module))
        else:
            raise ValueError("unsupported captured source object type")

    unresolved_courses = store.manifest.unresolved_course_group_ids
    unresolved_modules = store.manifest.unresolved_module_group_ids
    normalized_courses = tuple(courses)
    normalized_modules = tuple(modules)
    _validate_reference_closure(
        normalized_courses,
        normalized_modules,
        frozenset(item.source_group_id for item in excluded_null_code_course_versions),
        unresolved_courses,
        unresolved_modules,
    )
    return NormalizationBatch(
        run_id=store.manifest.run_id,
        periods=tuple(
            NormalizedPeriod(id=period.id, academic_year_start=year)
            for period, year in ((period, period_years[period.id]) for period in source_periods)
        ),
        courses=normalized_courses,
        excluded_null_code_course_versions=tuple(excluded_null_code_course_versions),
        modules=normalized_modules,
        unresolved_course_group_ids=unresolved_courses,
        unresolved_module_group_ids=unresolved_modules,
    )


def normalize_curriculum(
    store: RawCaptureStore,
    repository: NormalizationPersistence,
    *,
    current_academic_year_start: int,
    activity_window_years: int,
    course_guide_base_url: AnyHttpUrl,
) -> NormalizationReport:
    """Parse the current run completely before its one normalized transaction."""
    batch = parse_capture(store, course_guide_base_url=course_guide_base_url)
    return repository.apply(
        batch,
        current_academic_year_start=current_academic_year_start,
        activity_window_years=activity_window_years,
    )
