"""POST adapter for official course substring lookup."""

from fastapi import APIRouter, Response
from pydantic import BaseModel, ConfigDict

from course_explorer.search import lookup_commands
from course_explorer.search.lookup import DisplayLanguage

router = APIRouter()


class CourseLookupRequest(BaseModel):
    """The course narrowing command inputs."""

    model_config = ConfigDict(extra="forbid")
    query: str
    display_language: DisplayLanguage
    include_inactive: bool = True


@router.post("/api/course-lookup")
def course_lookup(request: CourseLookupRequest) -> Response:
    """Return the command's serialized report."""
    report = lookup_commands.run_course_lookup_command(**request.model_dump())
    return Response(content=report.model_dump_json(), media_type="application/json")
