"""POST adapter for official programme/module substring lookup."""

from fastapi import APIRouter, Response
from pydantic import BaseModel, ConfigDict

from course_explorer.search import lookup_commands
from course_explorer.search.lookup import DisplayLanguage

router = APIRouter()


class ModuleLookupRequest(BaseModel):
    """The module narrowing command inputs."""

    model_config = ConfigDict(extra="forbid")
    query: str
    display_language: DisplayLanguage


@router.post("/api/module-lookup")
def module_lookup(request: ModuleLookupRequest) -> Response:
    """Return the command's serialized report."""
    report = lookup_commands.run_module_lookup_command(**request.model_dump())
    return Response(content=report.model_dump_json(), media_type="application/json")
