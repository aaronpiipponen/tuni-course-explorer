"""POST adapter for read-only course comparison."""

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, ConfigDict

from course_explorer.comparison import commands
from course_explorer.config import load_web_settings

router = APIRouter()


class ComparisonRequest(BaseModel):
    """The two comparison identities."""

    model_config = ConfigDict(extra="forbid")
    course_a: str
    course_b: str


@router.post("/api/comparison")
def comparison(request: ComparisonRequest) -> Response:
    """Refuse a site without embedding features. Return the command's serialized report."""
    if not load_web_settings().embeddings_enabled:
        raise HTTPException(status_code=403, detail="Feature disabled")
    report = commands.run_course_comparison_command(**request.model_dump())
    return Response(content=report.model_dump_json(), media_type="application/json")
