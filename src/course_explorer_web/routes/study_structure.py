"""POST adapter for the official study-structure batch command."""

from fastapi import APIRouter, Response
from pydantic import BaseModel, ConfigDict

from course_explorer.study_structure import commands
from course_explorer_web.dataset import resolve_serving_dataset
from course_explorer_web.reports import dataset_report_response

router = APIRouter()


class StudyStructureRequest(BaseModel):
    """Canonical root identities and explicit version selections accepted by the batch command."""

    model_config = ConfigDict(extra="forbid")
    root_group_ids: tuple[str, ...]
    module_versions: dict[str, str] = {}
    allow_unavailable: bool = False


@router.post("/api/study-structure")
def study_structure(request: StudyStructureRequest) -> Response:
    """Return the batch command's serialized report over the resolved serving dataset."""
    serving = resolve_serving_dataset()
    report = commands.run_study_structures_command(
        request.root_group_ids,
        allow_unavailable=request.allow_unavailable,
        module_versions=request.module_versions,
        database_settings=serving.settings,
    )
    return dataset_report_response(report, serving)
