"""POST adapter for the unified course-search command."""

from fastapi import APIRouter, Response
from pydantic import BaseModel, ConfigDict

from course_explorer.config import load_web_settings
from course_explorer.search import commands
from course_explorer.search.lookup import DisplayLanguage

router = APIRouter()


class SearchRequest(BaseModel):
    """The public unified-search command inputs."""

    model_config = ConfigDict(extra="forbid")
    query: str
    display_language: DisplayLanguage
    semantic_min_score: float | None = None
    fuzzy_min_score: float | None = None
    include_inactive: bool = True


@router.post("/api/search")
def search(request: SearchRequest) -> Response:
    """Return the command's serialized report, composing semantic matching for this site."""
    report = commands.run_search_command(
        **request.model_dump(),
        include_semantic=load_web_settings().embeddings_enabled,
    )
    return Response(content=report.model_dump_json(), media_type="application/json")
