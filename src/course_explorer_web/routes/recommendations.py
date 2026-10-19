"""POST adapter for complete next-course and similarity recommendation reports."""

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, ConfigDict

from course_explorer.config import load_web_settings
from course_explorer.recommendations import commands
from course_explorer.search.lookup import DisplayLanguage

router = APIRouter()


class RecommendationsRequest(BaseModel):
    """Recommendation command inputs, with JSON arrays represented as tuples."""

    model_config = ConfigDict(extra="forbid")
    selected_courses: tuple[str, ...] = ()
    completed_courses: tuple[str, ...] = ()
    basis: str = "completed"
    mode: str = "all"
    display_language: DisplayLanguage
    include_inferred: bool = False
    active_only: bool = True


@router.post("/api/recommendations")
def recommendations(request: RecommendationsRequest) -> Response:
    """Refuse a site without embedding features. Return the command's serialized report."""
    settings = load_web_settings()
    if not settings.embeddings_enabled:
        raise HTTPException(status_code=403, detail="Feature disabled")
    values = request.model_dump()
    values["include_inferred"] = request.include_inferred and settings.inference_enabled
    report = commands.run_recommendations_command(**values)
    return Response(content=report.model_dump_json(), media_type="application/json")
