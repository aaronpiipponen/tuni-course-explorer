"""POST adapter for read-only next-course discovery."""

from fastapi import APIRouter, Response
from pydantic import BaseModel, ConfigDict

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
    """Return the command's serialized report."""
    report = commands.run_next_courses_command(**request.model_dump())
    return Response(content=report.model_dump_json(), media_type="application/json")
