"""POST adapter for complete next-course and similarity recommendation reports."""

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, ConfigDict

from course_explorer.config import load_web_settings
from course_explorer.recommendations import commands
from course_explorer.search.lookup import DisplayLanguage
from course_explorer_web.dataset import resolve_serving_dataset
from course_explorer_web.reports import dataset_report_response
from course_explorer_web.serving import ACTIVE_ONLY_DEFAULT
from course_explorer_web.serving_cache import serving_caches

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
    active_only: bool = ACTIVE_ONLY_DEFAULT


@router.post("/api/recommendations")
def recommendations(request: RecommendationsRequest) -> Response:
    """Refuse a site without embedding features. Return the command's serialized report."""
    settings = load_web_settings()
    if not settings.embeddings_enabled:
        raise HTTPException(status_code=403, detail="Feature disabled")
    serving = resolve_serving_dataset()
    cache = serving_caches(serving, settings)
    values = request.model_dump()
    values["include_inferred"] = request.include_inferred and settings.inference_enabled
    report = commands.run_recommendations_command(
        **values,
        database_settings=serving.settings,
        source_cache=cache.prerequisite_sources,
        chunk_cache=cache.descriptive_chunks,
    )
    return dataset_report_response(report, serving)
