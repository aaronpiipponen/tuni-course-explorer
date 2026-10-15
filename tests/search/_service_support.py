"""Shared in-memory fixtures for the shared-summary and semantic-search service contracts.

The fake curriculum/repository/provider record the calls the semantic service makes so the
configured threshold, current-vector filtering, and supplied-summary reuse can be proved. The
catalogue builders and official read double come from ``tests.support``.
"""

from __future__ import annotations

from typing import Any

from course_explorer.config import EmbeddingSettings, SearchSettings
from course_explorer.curriculum import CatalogueCourse, CourseSummary, course_summary
from course_explorer.search.service import (
    CourseSearchService,
    SemanticCourseScore,
)
from tests.support import (
    DIMENSION,
    HASH_A,
    HASH_B,
    FakeCurriculum,
    course,
    represented_rows,
    settings_factory,
    version,
)

__all__ = [
    "DIMENSION",
    "HASH_A",
    "HASH_B",
    "FakeCurriculum",
    "FakeProvider",
    "FakeRepository",
    "course",
    "embedding_settings",
    "search_settings",
    "service",
    "summary",
    "version",
]


def embedding_settings(**overrides: Any) -> EmbeddingSettings:
    """Build one required embedding configuration. Batch/chunk values are irrelevant here."""
    values: dict[str, object] = {
        "EMBEDDING_CONTEXT_SIZE": 1024,
        "EMBEDDING_REQUEST_TIMEOUT_SECONDS": 30,
        "EMBEDDING_ARTIFACT_URL": "https://example.test/model.gguf",
        "EMBEDDING_ARTIFACT_PATH": "models/model.gguf",
        **overrides,
    }
    return settings_factory(EmbeddingSettings, **values)


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
        embedding_configuration_hash,
        include_inactive,
    ):
        self.calls.append(
            (
                tuple(query_embedding),
                min_score,
                embedding_configuration_hash,
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
    active_courses: tuple[CatalogueCourse, ...] | None = None,
):
    summaries_by_activity = {None: represented_rows(courses)}
    if active_courses is not None:
        summaries_by_activity[True] = represented_rows(active_courses)
    curriculum = FakeCurriculum(courses, summaries_by_activity=summaries_by_activity)
    repository = FakeRepository(scores)
    provider = FakeProvider()
    composed = CourseSearchService(
        curriculum,
        repository,
        provider,
        embedding_settings(),
        search_settings(configured_min_score),
    )
    return composed, curriculum, repository, provider


def summary(course: CatalogueCourse) -> CourseSummary:
    return course_summary(course)
