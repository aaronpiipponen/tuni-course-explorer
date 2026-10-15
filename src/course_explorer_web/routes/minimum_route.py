"""POST adapter for the read-only minimum-new-credit route command."""

from fastapi import APIRouter, Response

from course_explorer.prerequisite import commands
from course_explorer_web.routes.prerequisite_inputs import PrerequisitesRequest

router = APIRouter()


@router.post("/api/minimum-route")
def minimum_route(request: PrerequisitesRequest) -> Response:
    """Forward every supplied route value and return its result."""
    report = commands.run_minimum_route_command(**request.model_dump())
    return Response(content=report.model_dump_json(), media_type="application/json")
