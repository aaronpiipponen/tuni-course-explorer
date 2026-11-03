"""POST adapter for browser-state official course summary resolution."""

from fastapi import APIRouter, Response

from course_explorer.search import lookup_commands
from course_explorer_web.reports import dataset_report_response
from course_explorer_web.request_limits import BoundedRequest
from course_explorer_web.serving_cache import (
    preloaded_lookup_projection,
    preloaded_serving_settings,
    serving_caches,
)

router = APIRouter()


class CourseSummariesRequest(BoundedRequest):
    """Canonical course identities or exact official codes to resolve."""

    _course_list_fields = ("identifiers",)

    identifiers: tuple[str, ...] = ()


@router.post("/api/course-summaries")
def course_summaries(request: CourseSummariesRequest) -> Response:
    """Return the command's serialized report over the resolved serving dataset."""
    bundle = preloaded_serving_settings()
    serving = bundle.dataset
    cache = serving_caches(serving)
    report = lookup_commands.run_course_summaries_command(
        request.identifiers,
        database_settings=serving.settings,
        projection=preloaded_lookup_projection(),
        session_factory=cache.database.factory(),
    )
    return dataset_report_response(report, serving)
