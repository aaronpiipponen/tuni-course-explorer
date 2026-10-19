"""POST adapter for the read-only prerequisite graph command."""

from fastapi import APIRouter, Response

from course_explorer.config import load_web_settings
from course_explorer.prerequisite import commands
from course_explorer_web.routes.prerequisite_inputs import PrerequisitesRequest

router = APIRouter()


@router.post("/api/prerequisites")
def prerequisites(request: PrerequisitesRequest) -> Response:
    """Forward every supplied graph value under this site's drawing and inference policy."""
    settings = load_web_settings()
    values = request.model_dump()
    values["include_inferred"] = request.include_inferred and settings.inference_enabled
    report = commands.run_prerequisite_command(
        **values,
        max_drawing_elements=settings.prerequisite_graph_max_elements,
    )
    return Response(content=report.model_dump_json(), media_type="application/json")
