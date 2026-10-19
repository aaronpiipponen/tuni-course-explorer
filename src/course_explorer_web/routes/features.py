"""POST adapter for the site's two served feature switches."""

from fastapi import APIRouter, Response
from pydantic import BaseModel, ConfigDict

from course_explorer.config import load_web_settings

router = APIRouter()


class FeaturesRequest(BaseModel):
    """The closed empty feature-report request."""

    model_config = ConfigDict(extra="forbid")


class WebFeaturesReport(BaseModel):
    """The site's served embedding and inference feature switches."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    embeddings_enabled: bool
    inference_enabled: bool


@router.post("/api/features")
def features(request: FeaturesRequest) -> Response:
    """Return the two configured feature switches as the report."""
    settings = load_web_settings()
    report = WebFeaturesReport(
        embeddings_enabled=settings.embeddings_enabled,
        inference_enabled=settings.inference_enabled,
    )
    return Response(content=report.model_dump_json(), media_type="application/json")
