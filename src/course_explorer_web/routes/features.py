"""POST adapter for the site's two served feature switches and its dataset identity."""

from fastapi import APIRouter, Response
from pydantic import BaseModel, ConfigDict

from course_explorer.config import load_web_settings
from course_explorer_web.dataset import resolve_serving_dataset

router = APIRouter()


class FeaturesRequest(BaseModel):
    """The closed empty feature-report request."""

    model_config = ConfigDict(extra="forbid")


class WebFeaturesReport(BaseModel):
    """The site's served feature switches and the identity of the dataset it serves."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    embeddings_enabled: bool
    inference_enabled: bool
    dataset_identity: str


@router.post("/api/features")
def features(request: FeaturesRequest) -> Response:
    """Return the two configured feature switches with the resolved dataset identity."""
    settings = load_web_settings()
    serving = resolve_serving_dataset()
    report = WebFeaturesReport(
        embeddings_enabled=settings.embeddings_enabled,
        inference_enabled=settings.inference_enabled,
        dataset_identity=serving.identity,
    )
    return Response(content=report.model_dump_json(), media_type="application/json")
