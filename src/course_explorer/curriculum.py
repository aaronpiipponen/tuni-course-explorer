"""Product-neutral immutable read DTOs for official normalized curriculum data."""

from __future__ import annotations

from collections.abc import Collection, Sequence
from datetime import date
from decimal import Decimal
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator

from course_explorer.enums import (
    ModuleRuleType,
    ModuleType,
    PrerequisiteMemberType,
    PrerequisiteRequirementKind,
)
from course_explorer.validation import SHA256_PATTERN as _HEX_256


class _CatalogueModel(BaseModel):
    """Frozen, closed DTO base for the official curriculum read contract."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class CatalogueTeachingText(_CatalogueModel):
    """Course content and learning outcomes, excluding prerequisite text."""

    content_fi: str | None = None
    content_en: str | None = None
    outcomes_fi: str | None = None
    outcomes_en: str | None = None


class CataloguePrerequisiteMember(_CatalogueModel):
    """One ordered canonical course or module member of an official prerequisite option."""

    member_index: int = Field(ge=0)
    member_type: PrerequisiteMemberType
    referenced_group_id: str


class CataloguePrerequisiteOption(_CatalogueModel):
    """One ordered AND option in an official compulsory/recommended prerequisite expression."""

    option_index: int = Field(ge=0)
    requirement_kind: PrerequisiteRequirementKind
    members: tuple[CataloguePrerequisiteMember, ...]


class CatalogueSubstitutionMember(_CatalogueModel):
    """One ordered course-group member of a directional official substitution option."""

    member_index: int = Field(ge=0)
    course_group_id: str
    credits: Decimal | None = None


class CatalogueSubstitutionOption(_CatalogueModel):
    """One ordered AND option in a directional official substitution expression."""

    option_index: int = Field(ge=0)
    members: tuple[CatalogueSubstitutionMember, ...]


class CatalogueCourseVersion(_CatalogueModel):
    """One exact official course version and its normalized official structures."""

    sisu_course_unit_id: str
    source_hash: str
    code: str
    name_fi: str | None = None
    name_en: str | None = None
    credits_min: Decimal
    credits_max: Decimal | None = None
    official_url: str
    document_state: str
    validity_start: date | None = None
    validity_end: date | None = None
    curriculum_period_ids: tuple[str, ...]
    teaching_text: CatalogueTeachingText
    prerequisite_text_fi: str | None = None
    prerequisite_text_en: str | None = None
    additional_info_fi: str | None = None
    additional_info_en: str | None = None
    prerequisite_options: tuple[CataloguePrerequisiteOption, ...]
    substitution_options: tuple[CatalogueSubstitutionOption, ...]


class CatalogueCourse(_CatalogueModel):
    """Canonical course identity, persisted activity context, and selected representative."""

    group_id: str
    first_listed_academic_year_start: int | None = None
    last_listed_academic_year_start: int | None = None
    is_active: bool
    activity_as_of_academic_year_start: int = Field(gt=0)
    activity_window_years: int = Field(gt=0)
    representative: CatalogueCourseVersion | None = None


class CatalogueCourseActivity(_CatalogueModel):
    """The four canonical activity columns a scoped membership read needs.

    Publication and group reconciliation compare only identity and the live activity snapshot, so
    this closed projection avoids loading a full official course and its representative structures.
    """

    group_id: str
    is_active: bool
    activity_as_of_academic_year_start: int = Field(gt=0)
    activity_window_years: int = Field(gt=0)

    @field_validator("group_id")
    @classmethod
    def reject_blank_group_id(cls, value: str) -> str:
        """Require a nonblank canonical course identity."""
        if not value.strip():
            raise ValueError("activity group_id must not be blank")
        return value


class CatalogueRepresentativeTeachingText(_CatalogueModel):
    """Official-only detached projection of one selected representative's identity and teaching text.

    The translation import validator consumes only the selected source identity, both official
    localized names, and the four official content/outcomes columns. This closed projection carries
    exactly those fields instead of a full `CatalogueCourseVersion`, so validation never
    materializes prerequisite, substitution, source-hash, code, period, or activity structures.
    """

    sisu_course_unit_id: str
    name_fi: str | None = None
    name_en: str | None = None
    teaching_text: CatalogueTeachingText


class CatalogueTeachingCourseVersion(CatalogueRepresentativeTeachingText):
    """One selected representative's teaching-text projection plus its source hash and code.

    Teaching-text consumers that also compare the selected source identity need the exact
    representative hash and code. This closed projection adds exactly those two fields and no
    official prerequisite, substitution, credit, period, or URL structure.
    """

    source_hash: str
    code: str


class CatalogueTeachingCourse(CatalogueCourseActivity):
    """Canonical activity context with the selected representative's teaching-text projection."""

    representative: CatalogueTeachingCourseVersion | None


class CatalogueTeachingTextInput(_CatalogueModel):
    """One canonical course's group ID plus its official selected representative text, if any.

    This is the input the shared teaching-text resolver consumes for a projected coverage read: it
    carries the identity and the official text the resolver reads.
    """

    group_id: str
    representative: CatalogueRepresentativeTeachingText | None


class CourseSummary(_CatalogueModel):
    """One shared product-neutral official summary reused by every course-returning service.

    Both localized official names are retained so this contract does not invent a UI locale or
    present a derived translation as official summary data. `course_summary()` maps it from the
    official read seam only.
    """

    group_id: str
    name_fi: str | None = None
    name_en: str | None = None
    code: str
    credits_min: Decimal
    credits_max: Decimal | None = None
    is_active: bool
    official_url: str

    @field_validator("group_id", "code", "official_url")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        """Require nonblank canonical identity and official locator values."""
        if not value.strip():
            raise ValueError("summary group_id, code, and official_url must not be blank")
        return value

    @field_validator("name_fi", "name_en")
    @classmethod
    def reject_blank_optional_name(cls, value: str | None) -> str | None:
        """Reject a provided-but-blank or missing localized name."""
        if value is not None and not value.strip():
            raise ValueError("summary localized names must be None or nonblank")
        return value


def is_within_activity_window(
    academic_year_start: int,
    *,
    current_academic_year_start: int,
    activity_window_years: int,
) -> bool:
    """Return whether one academic year lies in the inclusive configured activity window.

    The window starts at ``current_academic_year_start - activity_window_years + 1`` and ends at the
    current year. Normalization and the catalogue read share this one bound so a course's active
    status is decided identically everywhere.
    """
    return (
        current_academic_year_start - activity_window_years + 1
        <= academic_year_start
        <= current_academic_year_start
    )


def course_summary_from_fields(
    *,
    group_id: str,
    is_active: bool,
    name_fi: str | None,
    name_en: str | None,
    code: str,
    credits_min: Decimal,
    credits_max: Decimal | None,
    official_url: str,
) -> CourseSummary:
    """Build the one shared summary from its exact official fields.

    The field-to-summary mapping lives here so every read (a full `CatalogueCourse` or a
    column projection) produces the identical DTO from one source of truth.
    """
    return CourseSummary(
        group_id=group_id,
        name_fi=name_fi,
        name_en=name_en,
        code=code,
        credits_min=credits_min,
        credits_max=credits_max,
        is_active=is_active,
        official_url=official_url,
    )


def course_summary(course: CatalogueCourse) -> CourseSummary:
    """Copy only the selected representative's official summary fields into one shared DTO."""
    if course.representative is None:
        raise ValueError(f"course {course.group_id} has no selected representative")
    version = course.representative
    return course_summary_from_fields(
        group_id=course.group_id,
        is_active=course.is_active,
        name_fi=version.name_fi,
        name_en=version.name_en,
        code=version.code,
        credits_min=version.credits_min,
        credits_max=version.credits_max,
        official_url=version.official_url,
    )


class RepresentedCourseSummary(_CatalogueModel):
    """One represented course's shared summary plus the exact representative identity.

    Search pairs durable semantic scores with the current representative, so it needs only the
    summary and the representative's `sisu_course_unit_id`/`source_hash`. A column
    projection supplies exactly these fields without materializing a full `CatalogueCourse`.
    """

    summary: CourseSummary
    sisu_course_unit_id: str
    source_hash: str

    @field_validator("sisu_course_unit_id")
    @classmethod
    def reject_blank_source_id(cls, value: str) -> str:
        """Require a nonblank exact official representative identity."""
        if not value.strip():
            raise ValueError("represented summary sisu_course_unit_id must not be blank")
        return value

    @field_validator("source_hash")
    @classmethod
    def validate_source_hash(cls, value: str) -> str:
        """Require the exact 64-character lowercase hexadecimal source hash."""
        if _HEX_256.fullmatch(value) is None:
            raise ValueError(
                "represented summary source_hash must be 64 lowercase hexadecimal characters"
            )
        return value


class CatalogueModuleRule(_CatalogueModel):
    """Recursive typed official module-rule node, including unrestricted selections."""

    node_type: ModuleRuleType
    sibling_position: int = Field(ge=0)
    local_id: str | None = None
    require_min: int | None = Field(default=None, ge=0)
    require_max: int | None = Field(default=None, ge=0)
    all_mandatory: bool | None = None
    description: dict[str, str] | None = None
    credits_min: Decimal | None = None
    credits_max: Decimal | None = None
    count_min: int | None = Field(default=None, ge=0)
    count_max: int | None = Field(default=None, ge=0)
    referenced_group_id: str | None = None
    children: tuple[CatalogueModuleRule, ...] = ()


class CatalogueCurriculumPeriod(_CatalogueModel):
    """One official academic period membership with its explicit academic year."""

    id: str
    academic_year_start: int = Field(gt=0)

    @field_validator("id")
    @classmethod
    def reject_blank_id(cls, value: str) -> str:
        """Require a nonblank official period identity."""
        if not value.strip():
            raise ValueError("curriculum period id must not be blank")
        return value


class CatalogueModuleVersionIdentity(_CatalogueModel):
    """The official module-version identity, names, validity and memberships a lookup consumes.

    It carries exactly the fields module name/code lookup and module-version selection read, so a
    repository projection and a full `CatalogueModuleVersion` expose one shared identity shape.
    """

    sisu_module_id: str
    module_type: ModuleType
    code: str | None = None
    name_fi: str | None = None
    name_en: str | None = None
    validity_start: date | None = None
    validity_end: date | None = None
    curriculum_periods: tuple[CatalogueCurriculumPeriod, ...]


class CatalogueModuleVersion(CatalogueModuleVersionIdentity):
    """One exact official module version and its complete typed rule tree."""

    source_hash: str
    target_credits_min: Decimal | None = None
    target_credits_max: Decimal | None = None
    document_state: str
    rule: CatalogueModuleRule | None = None


class CatalogueModule(_CatalogueModel):
    """Canonical module identity with all exact versions sorted by source ID."""

    group_id: str
    versions: tuple[CatalogueModuleVersion, ...]


class CatalogueModuleLookup(_CatalogueModel):
    """Canonical module identity with only the projected versions a name lookup consumes."""

    group_id: str
    versions: tuple[CatalogueModuleVersionIdentity, ...]


class ModuleSummary(_CatalogueModel):
    """One canonical module's selected official version summary for a narrowing lookup.

    It carries only the official identity, module type, code and both localized names. Modules have
    no activity flag, official URL, rule tree or provenance hash, so none is invented here.
    """

    group_id: str
    sisu_module_id: str
    module_type: ModuleType
    code: str | None = None
    name_fi: str | None = None
    name_en: str | None = None


def module_version_candidates[T: CatalogueModuleVersionIdentity](
    versions: Sequence[T], *, academic_year_start: int, allow_nearest: bool = False
) -> tuple[T, ...]:
    """Return every module version usable for one academic year, preserving input order.

    An exact academic-year membership always wins. Only when none exists are membership-free
    versions whose own validity bounds contain the requested year considered. This selects the
    candidate set, never an arbitrary winner: an empty result is missing and more than one is
    ambiguous, so a version tied to another year is never a silent fallback. Only when that strict
    set is empty and `allow_nearest` is true does the single nearest dated version fall back: the
    greatest year before the requested year, otherwise the least year after it, breaking a
    same-year tie by the greatest `sisu_module_id`. Callers that need disclosure opt in. Strict
    callers keep the empty result.
    """
    exact_memberships = tuple(
        version
        for version in versions
        if any(
            period.academic_year_start == academic_year_start
            for period in version.curriculum_periods
        )
    )
    if exact_memberships:
        return exact_memberships
    validity_matches = tuple(
        version
        for version in versions
        if not version.curriculum_periods
        and (version.validity_start is None or version.validity_start.year <= academic_year_start)
        and (version.validity_end is None or academic_year_start <= version.validity_end.year)
    )
    if validity_matches or not allow_nearest:
        return validity_matches
    return _nearest_module_version(versions, academic_year_start=academic_year_start)


def _nearest_module_version[T: CatalogueModuleVersionIdentity](
    versions: Sequence[T], *, academic_year_start: int
) -> tuple[T, ...]:
    """Return the single nearest dated module version, or `()` when there are none.

    Each version's comparison year is its best preceding period year, otherwise its nearest following
    period year. A membership-free expired/future version uses its validity end/start year. The
    greatest preceding year wins, otherwise the least following year. A same-year tie picks the greatest
    `sisu_module_id`, matching the deterministic representative-ID tie.
    """
    if not versions:
        return ()
    ranked = tuple((_fallback_year(version, academic_year_start), version) for version in versions)
    earlier = tuple(year for year, _ in ranked if year < academic_year_start)
    best_year = max(earlier) if earlier else min(year for year, _ in ranked)
    tied = tuple(version for year, version in ranked if year == best_year)
    return (max(tied, key=lambda version: version.sisu_module_id),)


def _fallback_year(version: CatalogueModuleVersionIdentity, requested: int) -> int:
    """Return one module version's nearest comparison year for the fallback ranking."""
    period_years = tuple(period.academic_year_start for period in version.curriculum_periods)
    if period_years:
        earlier = tuple(year for year in period_years if year < requested)
        return max(earlier) if earlier else min(period_years)
    if version.validity_end is not None and version.validity_end.year < requested:
        return version.validity_end.year
    if version.validity_start is not None:
        return version.validity_start.year
    raise ValueError("a fallback module version requires a validity bound or a period membership")


class CatalogueSummary(_CatalogueModel):
    """Database-backed counts for the normalized official catalogue."""

    curriculum_period_count: int = Field(ge=0)
    canonical_course_count: int = Field(ge=0)
    active_course_count: int = Field(ge=0)
    course_version_count: int = Field(ge=0)
    canonical_module_count: int = Field(ge=0)
    module_version_count: int = Field(ge=0)


class CurriculumRead(Protocol):
    """Stable read-only handoff consumed by other curriculum features."""

    def list_courses(self, *, active_only: bool | None = None) -> tuple[CatalogueCourse, ...]: ...

    def list_teaching_courses(
        self, *, active_only: bool | None = None
    ) -> tuple[CatalogueTeachingCourse, ...]: ...

    def list_teaching_text_inputs(self) -> tuple[CatalogueTeachingTextInput, ...]: ...

    def list_modules(self) -> tuple[CatalogueModule, ...]: ...

    def list_module_lookup(self) -> tuple[CatalogueModuleLookup, ...]: ...

    def list_represented_summaries(
        self, *, active_only: bool | None = None
    ) -> tuple[RepresentedCourseSummary, ...]: ...

    def get_represented_summaries(
        self, group_ids: Collection[str], *, active_only: bool | None = None
    ) -> tuple[RepresentedCourseSummary, ...]: ...

    def list_course_code_identities(
        self, *, active_only: bool | None = None
    ) -> tuple[tuple[str, str], ...]: ...

    def summary(self) -> CatalogueSummary: ...


class CurriculumGraphRead(Protocol):
    """Read seam for root-specific graph compilation.

    Graph traversal discovers the courses and modules it references as it goes, so it requests
    exactly those canonical identities instead of the whole catalogue. Both methods return the
    identical DTOs `list_courses`/`list_modules` build, in `group_id` order. A requested identity
    absent from the database is omitted, which leaves the caller's
    `MISSING_COURSE`/`MISSING_MODULE` semantics untouched.
    """

    def get_courses(self, group_ids: Collection[str]) -> tuple[CatalogueCourse, ...]: ...

    def get_modules(self, group_ids: Collection[str]) -> tuple[CatalogueModule, ...]: ...


class CurriculumStructureRead(Protocol):
    """Read seam for projecting one programme/module's official structure.

    Structure projection discovers the modules and courses it references as it walks one selected
    version's rule tree, so it requests exactly those canonical identities instead of the whole
    catalogue. `get_modules` returns the identical full DTOs `list_modules` builds. The summary
    getter returns the shared official `CourseSummary` for the requested canonical courses, omitting
    any unknown or unrepresented identity and applying no activity filter.
    """

    def get_modules(self, group_ids: Collection[str]) -> tuple[CatalogueModule, ...]: ...

    def get_course_summaries(self, group_ids: Collection[str]) -> tuple[CourseSummary, ...]: ...


class CurriculumDiscoveryRead(CurriculumGraphRead, Protocol):
    """Read seam for next-course candidate discovery.

    Discovery asks two reverse questions that no forward graph read can answer cheaply: which
    canonical courses offer an official substitution option naming a chosen basis course, and which
    canonical courses carry a direct official prerequisite option referencing one of those source
    courses (directly or through a module that can contain one). Both return only sorted distinct
    canonical `group_id` strings (never payloads or ORM entities), and an empty scope returns `()`
    before any I/O. The results are candidate supersets across stored official versions, never
    completion state: the current compiler alone decides satisfaction, and old versions or partly
    matched substitutions may overselect.
    """

    def get_substitution_source_group_ids(
        self, member_group_ids: Collection[str]
    ) -> tuple[str, ...]: ...

    def get_prerequisite_candidate_group_ids(
        self, source_group_ids: Collection[str], *, active_only: bool
    ) -> tuple[str, ...]: ...
