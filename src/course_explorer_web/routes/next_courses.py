"""POST adapter for read-only next-course discovery."""

from fastapi import APIRouter, Response
from pydantic import BaseModel, ConfigDict

from course_explorer.config import load_web_settings
from course_explorer.next_courses import commands
from course_explorer.search.lookup import DisplayLanguage

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
    active_only: bool = True


@router.post("/api/next-courses")
def next_courses(request: NextCoursesRequest) -> Response:
    """Forward every supplied value under this site's inference policy. Return the report."""
    settings = load_web_settings()
    values = request.model_dump()
    values["include_inferred"] = request.include_inferred and settings.inference_enabled
    report = commands.run_next_courses_command(**values)
    return Response(content=report.model_dump_json(), media_type="application/json")
