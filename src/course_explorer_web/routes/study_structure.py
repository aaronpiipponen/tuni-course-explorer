"""POST adapter for the official study-structure command."""

from fastapi import APIRouter, Response
from pydantic import BaseModel, ConfigDict

from course_explorer.study_structure import commands

router = APIRouter()


class StudyStructureRequest(BaseModel):
    """Canonical root identity accepted by the structure command."""

    model_config = ConfigDict(extra="forbid")
    root_group_id: str


@router.post("/api/study-structure")
def study_structure(request: StudyStructureRequest) -> Response:
    """Return the command's serialized report."""
    report = commands.run_study_structure_command(**request.model_dump())
    return Response(content=report.model_dump_json(), media_type="application/json")
