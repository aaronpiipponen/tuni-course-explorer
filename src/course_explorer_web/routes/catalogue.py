"""POST adapter for the minimal official catalogue every narrowing surface filters locally."""

from fastapi import APIRouter, Response
from pydantic import BaseModel, ConfigDict

from course_explorer.config import load_web_settings
from course_explorer.search import lookup_commands
from course_explorer_web.dataset import resolve_serving_dataset
from course_explorer_web.reports import dataset_report_response
from course_explorer_web.serving_cache import serving_caches

router = APIRouter()


class CatalogueRequest(BaseModel):
    """The closed empty catalogue request."""

    model_config = ConfigDict(extra="forbid")


@router.post("/api/catalogue")
def catalogue(request: CatalogueRequest) -> Response:
    """Return the minimal official catalogue over this site's serving dataset."""
    settings = load_web_settings()
    serving = resolve_serving_dataset()
    cache = serving_caches(serving, settings)
    report = lookup_commands.run_catalogue_command(
        database_settings=serving.settings, projection_cache=cache.lookup_projection
    )
    return dataset_report_response(report, serving)
