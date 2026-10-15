"""Shared in-memory fixtures for the non-semantic official lookup contracts.

The fake curriculum returns the supplied represented-summary activity profiles so the lookup service
can be exercised without a database. The catalogue builders and official read double come from
``tests.support``.
"""

from __future__ import annotations

from course_explorer.config import SearchSettings
from course_explorer.curriculum import CatalogueCourse
from course_explorer.search.lookup import CourseLookupService
from tests.support import FakeCurriculum, course, represented_rows, settings_factory, version

__all__ = ["course", "search_settings", "service", "version"]


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
    return CourseLookupService(curriculum, search_settings(fuzzy_min_score)), curriculum
