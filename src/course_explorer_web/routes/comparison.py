"""POST adapter for read-only course comparison."""

from fastapi import APIRouter, HTTPException, Response

from course_explorer.comparison import commands
from course_explorer_web.reports import dataset_report_response
from course_explorer_web.request_limits import BoundedRequest
from course_explorer_web.serving_cache import (
    preloaded_lookup_projection,
    preloaded_serving_settings,
    serving_caches,
)

router = APIRouter()


class ComparisonRequest(BoundedRequest):
    """The two comparison identities."""

    _identifier_fields = ("course_a", "course_b")

    course_a: str
    course_b: str


@router.post("/api/comparison")
def comparison(request: ComparisonRequest) -> Response:
    """Refuse a site without embedding features. Return the command's serialized report."""
    bundle = preloaded_serving_settings()
    if not bundle.web.embeddings_enabled:
        raise HTTPException(status_code=403, detail="Feature disabled")
    serving = bundle.dataset
    cache = serving_caches(serving)
    embeddings = cache.artifacts.embedding_reads()
    report = commands.run_course_comparison_command(
        **request.model_dump(),
        database_settings=serving.settings,
        search_settings=bundle.search,
        embedding_settings=bundle.embedding,
        hub=embeddings.hubs[0],
        outcomes_hub=embeddings.hubs[1],
        embedding_configuration_hash=bundle.embedding_configuration_hash,
        projection=preloaded_lookup_projection(),
        session_factory=cache.database.factory(),
    )
    return dataset_report_response(report, serving)
