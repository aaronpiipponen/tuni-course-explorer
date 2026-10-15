"""Unified single-query search composition over the match services.

This module owns the one product-facing ``UnifiedCourseSearchService`` plus its result and report
contracts. It performs exactly one projected represented-course summary read per query and runs the
separately callable exact-code, substring, fuzzy-name, and semantic services
exactly once for every valid query, merges their results to one entry per canonical
``course.group_id``, retains every match source, keeps the fuzzy (`0-100`) and semantic
(`[-1, 1]`) score scales in distinct fields, and orders merged courses by the config-owned
``SearchSettings.search_tier_priority`` then active-before-inactive then the primary method's own
result position.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from course_explorer.config import SearchMethod, SearchSettings
from course_explorer.curriculum import (
    CourseSummary,
    CurriculumRead,
    RepresentedCourseSummary,
)
from course_explorer.search.lookup import (
    CourseLookupService,
    DisplayLanguage,
    FuzzyCourseResult,
)
from course_explorer.search.service import CourseSearchResult, CourseSearchService


class _UnifiedModel(BaseModel):
    """Frozen, closed DTO base for the unified-search contract."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class UnifiedCourseSearchResult(_UnifiedModel):
    """One canonical course with every match source and the per-method scores."""

    course: CourseSummary
    match_sources: tuple[SearchMethod, ...]
    fuzzy_score: float | None = None
    semantic_score: float | None = None


class UnifiedSearchReport(_UnifiedModel):
    """One unified query's effective policy and merged, tier-ordered canonical results."""

    display_language: DisplayLanguage
    semantic_min_score: float
    fuzzy_min_score: float
    include_inactive: bool
    tier_priority: tuple[SearchMethod, ...]
    results: tuple[UnifiedCourseSearchResult, ...]


class UnifiedCourseSearchService:
    """Run every match method once and merge their results under config-owned tiering."""

    def __init__(
        self,
        curriculum: CurriculumRead,
        semantic_search: CourseSearchService,
        course_lookup: CourseLookupService,
        search_settings: SearchSettings,
    ) -> None:
        self._curriculum = curriculum
        self._semantic_search = semantic_search
        self._course_lookup = course_lookup
        self._search_settings = search_settings

    def search(
        self,
        query: str,
        *,
        display_language: DisplayLanguage,
        semantic_min_score: float | None = None,
        fuzzy_min_score: float | None = None,
        include_inactive: bool = True,
    ) -> tuple[UnifiedCourseSearchResult, ...]:
        """Dispatch all four methods, merge by canonical group, and order under configured tiers."""
        represented: tuple[RepresentedCourseSummary, ...] = (
            self._curriculum.list_represented_summaries(
                active_only=None if include_inactive else True
            )
        )
        exact_matches = self._course_lookup.exact_code_search(
            query,
            display_language=display_language,
            include_inactive=include_inactive,
            represented=represented,
        )
        substring_matches = self._course_lookup.substring_search(
            query,
            display_language=display_language,
            include_inactive=include_inactive,
            represented=represented,
        )
        fuzzy_matches = self._course_lookup.fuzzy_name_search(
            query,
            display_language=display_language,
            min_score=fuzzy_min_score,
            include_inactive=include_inactive,
            represented=represented,
        )
        semantic_matches = self._semantic_search.search_courses(
            query,
            min_score=semantic_min_score,
            include_inactive=include_inactive,
            represented=represented,
        )

        return self._merge(exact_matches, substring_matches, fuzzy_matches, semantic_matches)

    def _merge(
        self,
        exact_matches: tuple[CourseSummary, ...],
        substring_matches: tuple[CourseSummary, ...],
        fuzzy_matches: tuple[FuzzyCourseResult, ...],
        semantic_matches: tuple[CourseSearchResult, ...],
    ) -> tuple[UnifiedCourseSearchResult, ...]:
        """Deduplicate per canonical group while keeping every ordered source and score."""
        priority = self._search_settings.search_tier_priority
        summaries: dict[str, CourseSummary] = {}
        sources: dict[str, dict[SearchMethod, int]] = {}
        fuzzy_scores: dict[str, float] = {}
        semantic_scores: dict[str, float] = {}

        def register(
            group_id: str, summary: CourseSummary, method: SearchMethod, position: int
        ) -> None:
            summaries.setdefault(group_id, summary)
            sources.setdefault(group_id, {})[method] = position

        for position, summary in enumerate(exact_matches):
            register(summary.group_id, summary, "exact_code", position)
        for position, summary in enumerate(substring_matches):
            register(summary.group_id, summary, "substring", position)
        for position, fuzzy in enumerate(fuzzy_matches):
            register(fuzzy.course.group_id, fuzzy.course, "fuzzy_name", position)
            fuzzy_scores[fuzzy.course.group_id] = fuzzy.score
        for position, semantic in enumerate(semantic_matches):
            register(semantic.course.group_id, semantic.course, "semantic", position)
            semantic_scores[semantic.course.group_id] = semantic.score

        tier_position = {method: index for index, method in enumerate(priority)}
        merged: list[tuple[tuple[object, ...], UnifiedCourseSearchResult]] = []
        for group_id, summary in summaries.items():
            group_sources = sources[group_id]
            ordered_sources = tuple(sorted(group_sources, key=tier_position.__getitem__))
            primary = ordered_sources[0]
            result = UnifiedCourseSearchResult(
                course=summary,
                match_sources=ordered_sources,
                fuzzy_score=fuzzy_scores.get(group_id),
                semantic_score=semantic_scores.get(group_id),
            )
            key = (tier_position[primary], not summary.is_active, group_sources[primary])
            merged.append((key, result))

        merged.sort(key=lambda item: item[0])
        return tuple(result for _, result in merged)
