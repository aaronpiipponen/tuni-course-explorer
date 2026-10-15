"""POST adapter for browser-state official course summary resolution."""

from fastapi import APIRouter, Response
from pydantic import BaseModel, ConfigDict

from course_explorer.search import lookup_commands

router = APIRouter()


class CourseSummariesRequest(BaseModel):
    """Canonical course identities or exact official codes to resolve."""

    model_config = ConfigDict(extra="forbid")
    identifiers: tuple[str, ...] = ()


@router.post("/api/course-summaries")
def course_summaries(request: CourseSummariesRequest) -> Response:
    """Return the command's serialized report."""
    report = lookup_commands.run_course_summaries_command(request.identifiers)
    return Response(content=report.model_dump_json(), media_type="application/json")
