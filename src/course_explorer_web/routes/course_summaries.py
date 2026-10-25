"""POST adapter for browser-state official course summary resolution."""

from fastapi import APIRouter, Response
from pydantic import BaseModel, ConfigDict

from course_explorer.search import lookup_commands
from course_explorer_web.dataset import resolve_serving_dataset
from course_explorer_web.reports import dataset_report_response

router = APIRouter()


class CourseSummariesRequest(BaseModel):
    """Canonical course identities or exact official codes to resolve."""

    model_config = ConfigDict(extra="forbid")
    identifiers: tuple[str, ...] = ()


@router.post("/api/course-summaries")
def course_summaries(request: CourseSummariesRequest) -> Response:
    """Return the command's serialized report over the resolved serving dataset."""
    serving = resolve_serving_dataset()
    report = lookup_commands.run_course_summaries_command(
        request.identifiers, database_settings=serving.settings
    )
    return dataset_report_response(report, serving)
