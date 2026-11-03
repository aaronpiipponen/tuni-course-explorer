"""Shared in-memory fixtures for the non-semantic official lookup contracts.

The fake curriculum returns the supplied represented-summary activity profiles so the lookup service
can be exercised without a database. The catalogue builders and official read double come from
``tests.support``.
"""

from __future__ import annotations

from datetime import date

from course_explorer.config import SearchSettings
from course_explorer.curriculum import (
    CatalogueCourse,
    CatalogueCurriculumPeriod,
    CatalogueModuleLookup,
    CatalogueModuleVersionIdentity,
)
from course_explorer.enums import ModuleType
from course_explorer.search.lookup import CourseLookupService
from course_explorer.search.projection import build_lookup_projection
from tests.support import FakeCurriculum, course, represented_rows, settings_factory, version

__all__ = [
    "course",
    "module_lookup",
    "module_version",
    "search_settings",
    "service",
    "version",
]


def module_version(
    sisu_module_id: str,
    *,
    module_type: ModuleType = ModuleType.STUDY_MODULE,
    code: str | None = None,
    name_fi: str | None = None,
    name_en: str | None = None,
    curriculum_periods: tuple[CatalogueCurriculumPeriod, ...] = (),
    validity_start: date | None = None,
    validity_end: date | None = None,
) -> CatalogueModuleVersionIdentity:
    """Build one projected module-version identity fixture."""
    return CatalogueModuleVersionIdentity(
        sisu_module_id=sisu_module_id,
        module_type=module_type,
        code=code,
        name_fi=name_fi,
        name_en=name_en,
        validity_start=validity_start,
        validity_end=validity_end,
        curriculum_periods=curriculum_periods,
    )


def module_lookup(
    group_id: str, *versions: CatalogueModuleVersionIdentity
) -> CatalogueModuleLookup:
    """Build one canonical module lookup fixture from its projected versions."""
    return CatalogueModuleLookup(group_id=group_id, versions=versions)


def search_settings(fuzzy_min_score: float = 80) -> SearchSettings:
    """Build one required search configuration. The semantic threshold is irrelevant here."""
    return settings_factory(SearchSettings, FUZZY_SEARCH_MIN_SCORE=str(fuzzy_min_score))


def service(
    courses: tuple[CatalogueCourse, ...],
    fuzzy_min_score: float = 80,
    *,
    active_courses: tuple[CatalogueCourse, ...] | None = None,
) -> tuple[CourseLookupService, FakeCurriculum]:
    summaries_by_activity = {None: represented_rows(courses)}
    if active_courses is not None:
        summaries_by_activity[True] = represented_rows(active_courses)
    curriculum = FakeCurriculum(courses, summaries_by_activity=summaries_by_activity)
    projection = build_lookup_projection(curriculum)
    return CourseLookupService(search_settings(fuzzy_min_score), projection=projection), curriculum
