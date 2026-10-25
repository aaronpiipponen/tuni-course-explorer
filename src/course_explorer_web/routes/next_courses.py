"""POST adapter for read-only next-course discovery."""

from fastapi import APIRouter, Response
from pydantic import BaseModel, ConfigDict

from course_explorer.config import load_web_settings
from course_explorer.next_courses import commands
from course_explorer.search.lookup import DisplayLanguage
from course_explorer_web.dataset import resolve_serving_dataset
from course_explorer_web.reports import dataset_report_response
from course_explorer_web.serving import ACTIVE_ONLY_DEFAULT
from course_explorer_web.serving_cache import serving_caches

router = APIRouter()


class NextCoursesRequest(BaseModel):
    """Next-course command inputs, with JSON arrays represented as tuples."""

    model_config = ConfigDict(extra="forbid")
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
    settings = load_web_settings()
    serving = resolve_serving_dataset()
    cache = serving_caches(serving, settings)
    values = request.model_dump()
    values["include_inferred"] = request.include_inferred and settings.inference_enabled
    report = commands.run_next_courses_command(
        **values,
        database_settings=serving.settings,
        source_cache=cache.prerequisite_sources,
    )
    return dataset_report_response(report, serving)
