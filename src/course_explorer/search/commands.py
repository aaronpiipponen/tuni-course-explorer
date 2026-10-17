"""Process composition for unified course search. The one validation boundary for caller input."""

from __future__ import annotations

from typing import Annotated, get_args

from pydantic import TypeAdapter, ValidationError

from course_explorer.config import (
    SearchSettings,
    load_database_settings,
    load_embedding_settings,
    load_search_settings,
)
from course_explorer.curriculum_repository import CurriculumRepository
from course_explorer.db.session import database_context as _database_context
from course_explorer.embeddings.provider import EmbeddingProvider
from course_explorer.search.lookup import CourseLookupService, DisplayLanguage
from course_explorer.search.repository import SemanticSearchRepository
from course_explorer.search.service import CourseSearchService
from course_explorer.search.unified import UnifiedCourseSearchService, UnifiedSearchReport

_SEMANTIC_SCORE_ADAPTER = TypeAdapter(
    Annotated[float, *SearchSettings.model_fields["semantic_search_min_score"].metadata]
)
_FUZZY_SCORE_ADAPTER = TypeAdapter(
    Annotated[float, *SearchSettings.model_fields["fuzzy_search_min_score"].metadata]
)


def run_search_command(
    query: str,
    *,
    display_language: DisplayLanguage,
    semantic_min_score: float | None = None,
    fuzzy_min_score: float | None = None,
    include_inactive: bool = True,
) -> UnifiedSearchReport:
    """Compose one unified search over the match services, the shared repositories, and provider.

    The embedding provider receives a query-local projection of the embedding settings that carries
    the search policy for the one query embedding request. Every other consumer receives the loaded
    embedding settings, so the vector identity and the hubs come from those settings.
    """
    if not query.strip():
        raise ValueError("search query must be nonblank")
    if display_language not in get_args(DisplayLanguage):
        raise ValueError(f"display_language must be one of {get_args(DisplayLanguage)}")
    try:
        if semantic_min_score is not None:
            _SEMANTIC_SCORE_ADAPTER.validate_python(semantic_min_score)
        if fuzzy_min_score is not None:
            _FUZZY_SCORE_ADAPTER.validate_python(fuzzy_min_score)
    except ValidationError as exc:
        raise ValueError(str(exc)) from exc
    embedding_settings = load_embedding_settings()
    search_settings = load_search_settings()
    query_embedding_settings = embedding_settings.model_copy(
        update={
            "embedding_request_timeout_seconds": (
                search_settings.search_embedding_request_timeout_seconds
            ),
            "embedding_max_attempts": search_settings.search_embedding_max_attempts,
        }
    )
    with _database_context(load_database_settings()) as factory:
        curriculum = CurriculumRepository(factory)
        repository = SemanticSearchRepository(factory)
        course_lookup = CourseLookupService(curriculum, search_settings)
        with EmbeddingProvider(query_embedding_settings) as provider:
            semantic_search = CourseSearchService(
                curriculum, repository, provider, embedding_settings, search_settings
            )
            unified_search = UnifiedCourseSearchService(
                curriculum, semantic_search, course_lookup, search_settings
            )
            return unified_search.search(
                query,
                display_language=display_language,
                semantic_min_score=semantic_min_score,
                fuzzy_min_score=fuzzy_min_score,
                include_inactive=include_inactive,
            )
