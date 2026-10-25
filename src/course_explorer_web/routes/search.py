"""POST adapter for the unified course-search command."""

from fastapi import APIRouter, Response
from pydantic import BaseModel, ConfigDict

from course_explorer.config import load_web_settings
from course_explorer.search import commands
from course_explorer.search.lookup import DisplayLanguage
from course_explorer_web.dataset import resolve_serving_dataset
from course_explorer_web.reports import dataset_report_response
from course_explorer_web.serving import INCLUDE_INACTIVE_DEFAULT
from course_explorer_web.serving_cache import serving_caches

router = APIRouter()


class SearchRequest(BaseModel):
    """The public unified-search command inputs."""

    model_config = ConfigDict(extra="forbid")
    query: str
    display_language: DisplayLanguage
    semantic_min_score: float | None = None
    fuzzy_min_score: float | None = None
    include_inactive: bool = INCLUDE_INACTIVE_DEFAULT


@router.post("/api/search")
def search(request: SearchRequest) -> Response:
    """Return the command's serialized report, composing semantic matching for this site."""
    settings = load_web_settings()
    serving = resolve_serving_dataset()
    cache = serving_caches(serving, settings)
    report = commands.run_search_command(
        **request.model_dump(),
        include_semantic=settings.embeddings_enabled,
        database_settings=serving.settings,
        projection_cache=cache.lookup_projection,
    )
    return dataset_report_response(report, serving)
