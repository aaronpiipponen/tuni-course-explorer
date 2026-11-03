"""Semantic course-search contracts and the one query-to-summary service.

This module owns the product-neutral semantic search DTOs, the repository read protocol, and the
single `CourseSearchService` that embeds one query through the sole `EmbeddingProvider`, reads
current completed compatible chunk scores, pairs current representative identities with the
official `CourseSummary` taken from the projected represented-summary read, and orders active
before inactive then by descending relevance.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from course_explorer.config import SearchSettings
from course_explorer.curriculum import CourseSummary, RepresentedCourseSummary
from course_explorer.embeddings.provider import EmbeddingProvider


class _SearchModel(BaseModel):
    """Frozen, closed DTO base for the semantic-search contract."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class SemanticCourseScore(_SearchModel):
    """One exact-version best-chunk cosine score read from durable compatible vectors."""

    group_id: str
    sisu_course_unit_id: str
    representative_source_hash: str
    score: float


class CourseSearchResult(_SearchModel):
    """One shared official course summary with the system-owned relevance score that selected it."""

    course: CourseSummary
    score: float


class SemanticSearchRead(Protocol):
    """Read boundary for current compatible best-chunk scores consumed by the service."""

    def search(
        self,
        query_embedding: Sequence[float],
        *,
        hub: Sequence[float],
        min_score: float,
        include_inactive: bool,
    ) -> tuple[SemanticCourseScore, ...]:
        """Return every exact-version best-chunk score at or above the threshold."""
        ...


class CourseSearchService:
    """Turn one query into ordered current-representative official summaries above a threshold."""

    def __init__(
        self,
        repository: SemanticSearchRead,
        provider: EmbeddingProvider,
        hub: Sequence[float],
        search_settings: SearchSettings,
    ) -> None:
        self._repository = repository
        self._provider = provider
        self._hub = hub
        self._search_settings = search_settings

    def search_courses(
        self,
        query: str,
        *,
        represented: Mapping[str, RepresentedCourseSummary],
        min_score: float | None = None,
        include_inactive: bool = True,
    ) -> tuple[CourseSearchResult, ...]:
        """Embed one query, filter current compatible scores, and pair them with official summaries."""
        threshold = (
            self._search_settings.semantic_search_min_score if min_score is None else min_score
        )
        query_vector = self._provider.embed((query,))[0]
        scores = self._repository.search(
            query_vector,
            hub=self._hub,
            min_score=threshold,
            include_inactive=include_inactive,
        )

        results = []
        for score in scores:
            record = represented.get(score.group_id)
            if record is None:
                continue
            if (
                record.sisu_course_unit_id != score.sisu_course_unit_id
                or record.source_hash != score.representative_source_hash
            ):
                continue
            results.append(CourseSearchResult(course=record.summary, score=score.score))

        results.sort(
            key=lambda result: (
                not result.course.is_active,
                -result.score,
                result.course.group_id,
            )
        )
        return tuple(results)
