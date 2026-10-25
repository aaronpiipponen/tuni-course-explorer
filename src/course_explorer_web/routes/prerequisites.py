"""POST adapter for the read-only prerequisite graph command."""

from fastapi import APIRouter, Response

from course_explorer.config import load_search_settings, load_web_settings
from course_explorer.prerequisite import commands
from course_explorer_web.dataset import resolve_serving_dataset
from course_explorer_web.reports import dataset_report_response
from course_explorer_web.routes.prerequisite_inputs import PrerequisiteGraphRequest
from course_explorer_web.serving import MEASURE_GRAPH_HEADER
from course_explorer_web.serving_cache import serving_caches

router = APIRouter()


@router.post("/api/prerequisites")
def prerequisites(request: PrerequisiteGraphRequest) -> Response:
    """Forward the structural graph inputs under this site's drawing and inference policy."""
    settings = load_web_settings()
    serving = resolve_serving_dataset()
    cache = serving_caches(serving, settings)
    values = request.model_dump()
    values["include_inferred"] = request.include_inferred and settings.inference_enabled
    report = commands.run_prerequisite_command(
        **values,
        max_drawing_elements=settings.prerequisite_graph_max_elements,
        database_settings=serving.settings,
        source_cache=cache.prerequisite_sources,
    )
    response = dataset_report_response(
        report,
        serving,
        max_compact_nodes=load_search_settings().prerequisite_path_max_compact_nodes,
    )
    if request.target_code in _root_identifiers(report):
        response.headers[MEASURE_GRAPH_HEADER] = "1"
    return response


def _root_identifiers(report: commands.PrerequisiteGraphReport) -> frozenset[str]:
    """Return the root's canonical id and its exact official code, the measured target spellings.

    The admission cache is keyed by the request's target string, so measuring only these two exact
    spellings bounds it to two entries per course and flag combination.
    """
    root_id = report.solver.root_group_id
    codes = {course.code for course in report.solver.courses if course.group_id == root_id}
    return frozenset({root_id, *codes})
