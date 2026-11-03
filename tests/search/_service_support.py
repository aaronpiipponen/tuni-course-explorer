"""Shared in-memory fixtures for the shared-summary and semantic-search service contracts.

The fake repository and provider record the calls the semantic service makes so the configured
threshold, current-vector filtering, and supplied-summary pairing can be proved. The catalogue
builders and official read double come from ``tests.support``.
"""

from __future__ import annotations

from course_explorer.config import SearchSettings
from course_explorer.curriculum import CatalogueCourse, CourseSummary, course_summary
from course_explorer.search.service import (
    CourseSearchService,
    SemanticCourseScore,
)
from tests.support import (
    DIMENSION,
    HASH_A,
    HASH_B,
    course,
    represented_rows,
    settings_factory,
    version,
)

__all__ = [
    "DIMENSION",
    "HASH_A",
    "HASH_B",
    "FakeProvider",
    "FakeRepository",
    "course",
    "search_settings",
    "service",
    "summary",
    "version",
]


def search_settings(min_score: float = 0.4) -> SearchSettings:
    return settings_factory(SearchSettings, SEMANTIC_SEARCH_MIN_SCORE=str(min_score))


class FakeRepository:
    """Recording semantic read seam returning caller-supplied scores."""

    def __init__(self, scores: tuple[SemanticCourseScore, ...] = ()) -> None:
        self._scores = scores
        self.calls: list[tuple] = []

    def search(
        self,
        query_embedding,
        *,
        hub,
        min_score,
        include_inactive,
    ):
        self.calls.append(
            (
                tuple(query_embedding),
                min_score,
                include_inactive,
                hub,
            )
        )
        return self._scores


class FakeProvider:
    """Recording provider returning one fixed configured-dimension vector."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    def embed(self, texts):
        self.calls.append(tuple(texts))
        return tuple((1.0,) + (0.0,) * (DIMENSION - 1) for _ in texts)


def service(
    courses: tuple[CatalogueCourse, ...],
    scores: tuple[SemanticCourseScore, ...] = (),
    *,
    configured_min_score: float = 0.4,
):
    """Build the service over the supplied fixtures and return it with their represented records."""
    repository = FakeRepository(scores)
    provider = FakeProvider()
    composed = CourseSearchService(
        repository,
        provider,
        (0.0,) * DIMENSION,
        search_settings(configured_min_score),
    )
    return composed, represented_rows(courses), repository, provider


def summary(course: CatalogueCourse) -> CourseSummary:
    return course_summary(course)
