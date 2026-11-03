"""POST adapter for read-only next-course discovery."""

from fastapi import APIRouter, Response

from course_explorer.next_courses import commands
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


class NextCoursesRequest(BoundedRequest):
    """Next-course command inputs, with JSON arrays represented as tuples."""

    _course_list_fields = ("selected_courses", "completed_courses")

    selected_courses: tuple[str, ...] = ()
    completed_courses: tuple[str, ...] = ()
    basis: str = "completed"
    mode: str = "all"
    display_language: DisplayLanguage
    include_inferred: bool = False
    active_only: bool = ACTIVE_ONLY_DEFAULT


@router.post("/api/next-courses")
def next_courses(request: NextCoursesRequest) -> Response:
    """Forward every supplied value under this site's inference policy. Return the report."""
    bundle = preloaded_serving_settings()
    settings = bundle.web
    serving = bundle.dataset
    cache = serving_caches(serving)
    values = request.model_dump()
    values["include_inferred"] = request.include_inferred and settings.inference_enabled
    report = commands.run_next_courses_command(
        **values,
        database_settings=serving.settings,
        report_cache=cache.next_course_reports,
        projection=preloaded_lookup_projection(),
        session_factory=cache.database.factory(),
    )
    return dataset_report_response(report, serving)
