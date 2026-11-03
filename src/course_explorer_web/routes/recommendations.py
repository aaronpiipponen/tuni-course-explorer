"""POST adapter for complete next-course and similarity recommendation reports."""

from fastapi import APIRouter, HTTPException, Response

from course_explorer.recommendations import commands
from course_explorer.search.lookup import DisplayLanguage
from course_explorer_web.reports import dataset_report_response
from course_explorer_web.request_limits import BoundedRequest
from course_explorer_web.serving import ACTIVE_ONLY_DEFAULT
from course_explorer_web.serving_cache import (
    preloaded_lookup_projection,
    preloaded_serving_settings,
    serving_caches,
)

router = APIRouter()


class RecommendationsRequest(BoundedRequest):
    """Recommendation command inputs, with JSON arrays represented as tuples."""

    _course_list_fields = ("selected_courses", "completed_courses")

    selected_courses: tuple[str, ...] = ()
    completed_courses: tuple[str, ...] = ()
    basis: str = "completed"
    mode: str = "all"
    display_language: DisplayLanguage
    include_inferred: bool = False
    active_only: bool = ACTIVE_ONLY_DEFAULT


@router.post("/api/recommendations")
def recommendations(request: RecommendationsRequest) -> Response:
    """Refuse a site without embedding features. Return the command's serialized report."""
    bundle = preloaded_serving_settings()
    if not bundle.web.embeddings_enabled:
        raise HTTPException(status_code=403, detail="Feature disabled")
    settings = bundle.web
    serving = bundle.dataset
    cache = serving_caches(serving)
    embeddings = cache.artifacts.embedding_reads()
    values = request.model_dump()
    values["include_inferred"] = request.include_inferred and settings.inference_enabled
    report = commands.run_recommendations_command(
        **values,
        database_settings=serving.settings,
        search_settings=bundle.search,
        embedding_settings=bundle.embedding,
        hub=embeddings.hubs[0],
        outcomes_hub=embeddings.hubs[1],
        embedding_configuration_hash=bundle.embedding_configuration_hash,
        shared_store=embeddings.shared_store,
        next_course_cache=cache.next_course_reports,
        centroid_cache=cache.course_centroids,
        projection=preloaded_lookup_projection(),
        session_factory=cache.database.factory(),
    )
    return dataset_report_response(report, serving)
