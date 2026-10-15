"""Reusable read-only composition for narrowing lookups and transient official course summaries.

The substring commands validate caller input before any settings load or I/O, compose their shared
repository-backed lookup service inside one engine lifetime, call the substring lookup once, and
return transient reports. Bulk summary resolution uses the same official identity resolver, preserving
order and repeats without exposing representative provenance. Reports are request-local values
consumed by CLI and web callers. Narrowing is a plain case-insensitive substring lookup over
official identity.
"""

from __future__ import annotations

from collections.abc import Collection
from typing import get_args

from pydantic import BaseModel, ConfigDict

from course_explorer.config import (
    load_database_settings,
    load_normalization_settings,
    load_search_settings,
)
from course_explorer.curriculum import CourseSummary, ModuleSummary
from course_explorer.curriculum_repository import CurriculumRepository
from course_explorer.db.session import database_context as _database_context
from course_explorer.search.lookup import (
    CourseLookupService,
    DisplayLanguage,
    ModuleLookupService,
    _normalized,
)


class CourseSummariesReport(BaseModel):
    """Transient ordered official summaries resolved for browser-owned course identities."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    results: tuple[CourseSummary, ...]


def run_course_summaries_command(identifiers: Collection[str]) -> CourseSummariesReport:
    """Resolve canonical IDs/exact codes through the sole lookup owner into official summaries."""
    materialized = tuple(identifiers)
    if not materialized:
        return CourseSummariesReport(results=())
    search_settings = load_search_settings()
    with _database_context(load_database_settings()) as factory:
        lookup = CourseLookupService(CurriculumRepository(factory), search_settings)
        resolved = lookup.resolve_courses(materialized)
    return CourseSummariesReport(results=tuple(record.summary for record in resolved))


class CourseLookupReport(BaseModel):
    """One transient course substring lookup result and its effective request policy."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    query: str
    display_language: DisplayLanguage
    include_inactive: bool
    results: tuple[CourseSummary, ...]


class ModuleLookupReport(BaseModel):
    """One transient module substring lookup result and its effective academic-year policy."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    query: str
    display_language: DisplayLanguage
    academic_year_start: int
    results: tuple[ModuleSummary, ...]


def _validate_lookup_input(query: str, display_language: DisplayLanguage) -> None:
    """Reject a normalized-empty query or unsupported locale before any settings or I/O."""
    if not _normalized(query):
        raise ValueError("lookup query must be nonblank")
    if display_language not in get_args(DisplayLanguage):
        raise ValueError(f"display_language must be one of {get_args(DisplayLanguage)}")


def run_course_lookup_command(
    query: str,
    *,
    display_language: DisplayLanguage,
    include_inactive: bool = True,
) -> CourseLookupReport:
    """Compose one course substring lookup and return its report."""
    _validate_lookup_input(query, display_language)
    search_settings = load_search_settings()
    with _database_context(load_database_settings()) as factory:
        lookup = CourseLookupService(CurriculumRepository(factory), search_settings)
        results = lookup.substring_search(
            query, display_language=display_language, include_inactive=include_inactive
        )
    return CourseLookupReport(
        query=query,
        display_language=display_language,
        include_inactive=include_inactive,
        results=results,
    )


def run_module_lookup_command(
    query: str, *, display_language: DisplayLanguage
) -> ModuleLookupReport:
    """Compose one programme/module substring lookup at the configured current academic year."""
    _validate_lookup_input(query, display_language)
    academic_year_start = load_normalization_settings().current_academic_year_start
    with _database_context(load_database_settings()) as factory:
        lookup = ModuleLookupService(
            CurriculumRepository(factory), academic_year_start=academic_year_start
        )
        results = lookup.substring_search(query, display_language=display_language)
    return ModuleLookupReport(
        query=query,
        display_language=display_language,
        academic_year_start=academic_year_start,
        results=results,
    )
