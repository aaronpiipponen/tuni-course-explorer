"""Process composition for unified course search and its caller-input validation boundary."""

from __future__ import annotations

from collections.abc import Sequence
from contextlib import ExitStack
from typing import Annotated, get_args

import httpx
from pydantic import TypeAdapter, ValidationError
from sqlalchemy.orm import Session, sessionmaker

from course_explorer.config import (
    DatabaseSettings,
    EmbeddingRuntimeSettings,
    SearchSettings,
    load_database_settings,
    load_embedding_runtime_settings,
    load_search_settings,
)
from course_explorer.db.session import database_context as _database_context
from course_explorer.embeddings.generation import embedding_configuration_sha256
from course_explorer.embeddings.provider import EmbeddingProvider
from course_explorer.embeddings.query_cache import SharedQueryEmbeddingCache
from course_explorer.search.lookup import CourseLookupService, DisplayLanguage
from course_explorer.search.projection import LookupProjection
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
    include_semantic: bool = True,
    database_settings: DatabaseSettings | None = None,
    search_settings: SearchSettings | None = None,
    embedding_settings: EmbeddingRuntimeSettings | None = None,
    hub: Sequence[float] | None = None,
    projection: LookupProjection,
    search_group_count: int | None = None,
    query_embedding_cache: SharedQueryEmbeddingCache | None = None,
    embedding_configuration_hash: str | None = None,
    embedding_client: httpx.Client | None = None,
    session_factory: sessionmaker[Session] | None = None,
) -> UnifiedSearchReport:
    """Compose one unified search over the match services, the shared repositories, and provider.

    The embedding provider receives a query-local projection of the embedding settings that carries
    the search policy for the one query embedding request. The hub is the opened serving artifact
    build's catalogue hub, and it is required with semantic search. An ``include_semantic`` of
    ``False`` serves the three lexical methods alone: the embedding settings, the semantic
    repository and the provider are never built, and the unified owner receives no semantic
    service. A supplied embedding client is the serving process's one client and is not closed
    here. Otherwise the command creates and closes its own. A supplied embedding configuration
    identity answers the query cache key. Otherwise it is hashed from the supplied settings.
    Supplied search, embedding and database settings are used as given, and each one the caller
    omits is loaded after the input validation. The required projection answers the lexical methods
    and the represented pairing from the caller's prebuilt dataset projection. A supplied session
    factory carries the serving engine and is never disposed here. Otherwise the command opens one
    engine lifetime from those settings.
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
    search_settings = search_settings or load_search_settings()
    resolved_settings = (
        database_settings if database_settings is not None else load_database_settings()
    )
    with _database_context(resolved_settings, factory=session_factory) as factory:
        course_lookup = CourseLookupService(search_settings, projection=projection)
        with ExitStack() as stack:
            semantic_search: CourseSearchService | None = None
            if include_semantic:
                embedding_settings = embedding_settings or load_embedding_runtime_settings()
                if hub is None:
                    raise ValueError("semantic search requires the serving artifact hub")
                query_embedding_settings = embedding_settings.model_copy(
                    update={
                        "embedding_request_timeout_seconds": (
                            search_settings.search_embedding_request_timeout_seconds
                        ),
                        "embedding_max_attempts": search_settings.search_embedding_max_attempts,
                    }
                )
                if search_group_count is None:
                    raise ValueError("semantic search requires the serving artifact group count")
                repository = SemanticSearchRepository(factory, group_count=search_group_count)
                cache_configuration = (
                    None
                    if query_embedding_cache is None
                    else (
                        embedding_configuration_hash
                        or embedding_configuration_sha256(embedding_settings)
                    )
                )
                provider = stack.enter_context(
                    EmbeddingProvider(
                        query_embedding_settings,
                        client=embedding_client,
                        query_cache=query_embedding_cache,
                        cache_configuration=cache_configuration,
                    )
                )
                semantic_search = CourseSearchService(repository, provider, hub, search_settings)
            unified_search = UnifiedCourseSearchService(
                semantic_search, course_lookup, search_settings
            )
            return unified_search.search(
                query,
                display_language=display_language,
                semantic_min_score=semantic_min_score,
                fuzzy_min_score=fuzzy_min_score,
                include_inactive=include_inactive,
            )
