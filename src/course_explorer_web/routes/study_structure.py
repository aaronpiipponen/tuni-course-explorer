"""POST adapter for the official study-structure batch command."""

from fastapi import APIRouter, Response

from course_explorer.study_structure import commands
from course_explorer_web.reports import dataset_report_response
from course_explorer_web.request_limits import BoundedRequest
from course_explorer_web.serving_cache import preloaded_serving_settings, serving_caches

router = APIRouter()


class StudyStructureRequest(BoundedRequest):
    """Canonical root identities and explicit version selections accepted by the batch command."""

    _course_list_fields = ("root_group_ids",)
    _identifier_map_fields = ("module_versions",)

    root_group_ids: tuple[str, ...]
    module_versions: dict[str, str] = {}
    allow_unavailable: bool = False


@router.post("/api/study-structure")
def study_structure(request: StudyStructureRequest) -> Response:
    """Return the batch command's serialized report over the resolved serving dataset."""
    bundle = preloaded_serving_settings()
    serving = bundle.dataset
    cache = serving_caches(serving)
    report = commands.run_study_structures_command(
        request.root_group_ids,
        allow_unavailable=request.allow_unavailable,
        module_versions=request.module_versions,
        fragment_store=cache.artifacts.study_fragments,
        database_settings=serving.settings,
        academic_year_start=bundle.academic_year_start,
        session_factory=cache.database.factory(),
    )
    return dataset_report_response(report, serving)
