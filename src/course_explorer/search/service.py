"""Semantic course-search contracts and the one query-to-summary service.

This module owns the product-neutral semantic search DTOs, the repository read protocol, and the
single `CourseSearchService` that embeds one query through the sole `EmbeddingProvider`, reads
current completed compatible chunk scores, pairs current representative identities with the
official `CourseSummary` taken from the projected represented-summary read, and orders active
before inactive then by descending relevance.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from course_explorer.config import EmbeddingSettings, SearchSettings
from course_explorer.curriculum import CourseSummary, CurriculumRead, RepresentedCourseSummary
from course_explorer.embeddings.generation import embedding_configuration_sha256
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
        min_score: float,
        embedding_configuration_hash: str,
        include_inactive: bool,
    ) -> tuple[SemanticCourseScore, ...]: ...


class CourseSearchService:
    """Turn one query into ordered current-representative official summaries above a threshold."""

    def __init__(
        self,
        curriculum: CurriculumRead,
        repository: SemanticSearchRead,
        provider: EmbeddingProvider,
        embedding_settings: EmbeddingSettings,
        search_settings: SearchSettings,
    ) -> None:
        self._curriculum = curriculum
        self._repository = repository
        self._provider = provider
        self._embedding_settings = embedding_settings
        self._search_settings = search_settings

    def search_courses(
        self,
        query: str,
        *,
        min_score: float | None = None,
        include_inactive: bool = True,
        represented: Sequence[RepresentedCourseSummary] | None = None,
    ) -> tuple[CourseSearchResult, ...]:
        """Embed one query, filter current compatible scores, and pair them with official summaries."""
        threshold = (
            self._search_settings.semantic_search_min_score if min_score is None else min_score
        )
        query_vector = self._provider.embed((query,))[0]
        configuration_hash = embedding_configuration_sha256(self._embedding_settings)
        scores = self._repository.search(
            query_vector,
            hub=self._embedding_settings.embedding_hub_vector,
            min_score=threshold,
            embedding_configuration_hash=configuration_hash,
            include_inactive=include_inactive,
        )

        if represented is None:
            records = self._curriculum.list_represented_summaries(
                active_only=None if include_inactive else True
            )
        else:
            records = represented
        by_group = {record.summary.group_id: record for record in records}
        results = []
        for score in scores:
            record = by_group.get(score.group_id)
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
