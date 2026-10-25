"""Reusable read-only composition for the minimal official catalogue and transient course summaries.

Bulk summary resolution uses the shared official identity resolver, preserving order and repeats
without exposing representative provenance. The catalogue command reads the official course summary
projection and the projected module identities once, or takes both from a supplied lookup projection,
selects each canonical module's strict academic-year candidates through the shared eligibility rule,
and returns only canonical identity, code, localized names, credits and the activity flag for courses
and the module kind for modules. A module candidate additionally carries the exact version identity,
validity bounds and curriculum-period memberships the version selector needs, because more than one
eligible version of one canonical module must stay distinguishable. Reports are request-local values
consumed by CLI and web callers. Neither command carries teaching text, descriptions, prerequisites,
inferred analysis or course representative source identity.
"""

from __future__ import annotations

from collections.abc import Collection
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from course_explorer.config import (
    DatabaseSettings,
    load_database_settings,
    load_normalization_settings,
    load_search_settings,
)
from course_explorer.curriculum import (
    CatalogueCurriculumPeriod,
    CourseSummary,
    module_version_candidates,
)
from course_explorer.curriculum_repository import CurriculumRepository
from course_explorer.db.session import database_context as _database_context
from course_explorer.enums import ModuleType
from course_explorer.search.lookup import CourseLookupService
from course_explorer.search.projection import LookupProjectionCache, build_lookup_rows


class CourseSummariesReport(BaseModel):
    """Transient ordered official summaries resolved for browser-owned course identities."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    results: tuple[CourseSummary, ...]


class NarrowingCourse(BaseModel):
    """One official course identity with only the values a local narrowing filter consumes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    group_id: str
    code: str
    name_fi: str | None = None
    name_en: str | None = None
    credits_min: Decimal
    credits_max: Decimal | None = None
    is_active: bool


class NarrowingModuleVersion(BaseModel):
    """One eligible official module version's exact identity, validity and localized names."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    sisu_module_id: str
    module_type: ModuleType
    code: str | None = None
    name_fi: str | None = None
    name_en: str | None = None
    validity_start: date | None = None
    validity_end: date | None = None
    curriculum_periods: tuple[CatalogueCurriculumPeriod, ...]


class NarrowingModule(BaseModel):
    """One canonical module with every eligible version candidate for the current academic year."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    group_id: str
    candidates: tuple[NarrowingModuleVersion, ...]


class CatalogueReport(BaseModel):
    """The minimal official catalogue every browser narrowing surface filters locally."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    courses: tuple[NarrowingCourse, ...]
    modules: tuple[NarrowingModule, ...]


def run_course_summaries_command(
    identifiers: Collection[str], *, database_settings: DatabaseSettings | None = None
) -> CourseSummariesReport:
    """Resolve canonical IDs/exact codes through the sole lookup owner into official summaries."""
    materialized = tuple(identifiers)
    if not materialized:
        return CourseSummariesReport(results=())
    search_settings = load_search_settings()
    resolved_settings = (
        database_settings if database_settings is not None else load_database_settings()
    )
    with _database_context(resolved_settings) as factory:
        lookup = CourseLookupService(CurriculumRepository(factory), search_settings)
        resolved = lookup.resolve_courses(materialized)
    return CourseSummariesReport(results=tuple(record.summary for record in resolved))


def run_catalogue_command(
    *,
    database_settings: DatabaseSettings | None = None,
    projection_cache: LookupProjectionCache | None = None,
) -> CatalogueReport:
    """Read the minimal official catalogue at the configured current academic year.

    A supplied projection cache answers both the course rows and the module identities it retains.
    Otherwise the course summaries and the module lookup are read once from the one repository.
    """
    academic_year_start = load_normalization_settings().current_academic_year_start
    resolved_settings = (
        database_settings if database_settings is not None else load_database_settings()
    )
    with _database_context(resolved_settings) as factory:
        repository = CurriculumRepository(factory)
        if projection_cache is not None:
            projection = projection_cache.get(repository)
            rows = projection.courses
            module_lookup = projection.modules
        else:
            rows = build_lookup_rows(
                tuple(
                    record.summary
                    for record in repository.list_represented_summaries(active_only=None)
                )
            )
            module_lookup = repository.list_module_lookup()
        courses = tuple(
            sorted(
                (
                    NarrowingCourse(
                        group_id=row.summary.group_id,
                        code=row.summary.code,
                        name_fi=row.summary.name_fi,
                        name_en=row.summary.name_en,
                        credits_min=row.summary.credits_min,
                        credits_max=row.summary.credits_max,
                        is_active=row.summary.is_active,
                    )
                    for row in rows
                ),
                key=lambda course: course.group_id,
            )
        )
        modules = []
        for module in module_lookup:
            candidates = module_version_candidates(
                module.versions, academic_year_start=academic_year_start
            )
            if not candidates:
                continue
            modules.append(
                NarrowingModule(
                    group_id=module.group_id,
                    candidates=tuple(
                        NarrowingModuleVersion(
                            sisu_module_id=version.sisu_module_id,
                            module_type=version.module_type,
                            code=version.code,
                            name_fi=version.name_fi,
                            name_en=version.name_en,
                            validity_start=version.validity_start,
                            validity_end=version.validity_end,
                            curriculum_periods=version.curriculum_periods,
                        )
                        for version in candidates
                    ),
                )
            )
    return CatalogueReport(
        courses=courses,
        modules=tuple(sorted(modules, key=lambda module: module.group_id)),
    )
