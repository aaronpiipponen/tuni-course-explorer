"""POST adapter for the unified course-search command."""

from fastapi import APIRouter, Response

from course_explorer.search import commands
from course_explorer.search.lookup import DisplayLanguage
from course_explorer_web.reports import dataset_report_response
from course_explorer_web.request_limits import BoundedRequest
from course_explorer_web.serving import INCLUDE_INACTIVE_DEFAULT
from course_explorer_web.serving_cache import (
    preloaded_lookup_projection,
    preloaded_serving_settings,
    serving_caches,
)

router = APIRouter()


class SearchRequest(BoundedRequest):
    """The unified-search command inputs."""

    _query_fields = ("query",)

    query: str
    display_language: DisplayLanguage
    semantic_min_score: float | None = None
    fuzzy_min_score: float | None = None
    include_inactive: bool = INCLUDE_INACTIVE_DEFAULT


@router.post("/api/search")
def search(request: SearchRequest) -> Response:
    """Return the command's serialized report, composing semantic matching for this site."""
    bundle = preloaded_serving_settings()
    settings = bundle.web
    serving = bundle.dataset
    cache = serving_caches(serving)
    embeddings = cache.artifacts.embedding_reads() if settings.embeddings_enabled else None
    report = commands.run_search_command(
        **request.model_dump(),
        include_semantic=settings.embeddings_enabled,
        database_settings=serving.settings,
        search_settings=bundle.search,
        embedding_settings=bundle.embedding,
        hub=None if embeddings is None else embeddings.hubs[0],
        projection=preloaded_lookup_projection(),
        search_group_count=None if embeddings is None else embeddings.search.group_count,
        query_embedding_cache=cache.query_embeddings,
        embedding_configuration_hash=bundle.embedding_configuration_hash,
        embedding_client=bundle.search_embedding_client,
        session_factory=cache.database.factory(),
    )
    return dataset_report_response(report, serving)
