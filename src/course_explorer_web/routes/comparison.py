"""POST adapter for read-only course comparison."""

from fastapi import APIRouter, Response
from pydantic import BaseModel, ConfigDict

from course_explorer.comparison import commands

router = APIRouter()


class ComparisonRequest(BaseModel):
    """The two comparison identities."""

    model_config = ConfigDict(extra="forbid")
    course_a: str
    course_b: str


@router.post("/api/comparison")
def comparison(request: ComparisonRequest) -> Response:
    """Return the command's serialized report."""
    report = commands.run_course_comparison_command(**request.model_dump())
    return Response(content=report.model_dump_json(), media_type="application/json")
