"""POST adapter for the read-only minimum-new-credit route command."""

from fastapi import APIRouter, Response

from course_explorer.config import load_web_settings
from course_explorer.prerequisite import commands
from course_explorer_web.routes.prerequisite_inputs import PrerequisitesRequest

router = APIRouter()


@router.post("/api/minimum-route")
def minimum_route(request: PrerequisitesRequest) -> Response:
    """Forward every supplied route value under this site's inference policy. Return its result."""
    settings = load_web_settings()
    values = request.model_dump()
    values["include_inferred"] = request.include_inferred and settings.inference_enabled
    report = commands.run_minimum_route_command(**values)
    return Response(content=report.model_dump_json(), media_type="application/json")
