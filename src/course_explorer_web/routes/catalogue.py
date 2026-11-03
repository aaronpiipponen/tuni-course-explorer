"""POST adapter for the minimal official catalogue every narrowing surface filters locally."""

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, ConfigDict

from course_explorer_web.accept_encoding import accepts_encoding
from course_explorer_web.serving_cache import preloaded_serving_settings, serving_caches

router = APIRouter()


class CatalogueRequest(BaseModel):
    """The closed empty catalogue request."""

    model_config = ConfigDict(extra="forbid")


@router.post("/api/catalogue")
def catalogue(request: Request, body: CatalogueRequest) -> Response:
    """Return the minimal official catalogue from the current serving artifact build.

    A gzip-capable client receives the compressed artifact body with its encoding header. An
    identity client receives the plain body. The serving identity is appended to either body.
    """
    bundle = preloaded_serving_settings()
    serving = bundle.dataset
    cache = serving_caches(serving)
    if accepts_encoding(request.headers.get("accept-encoding", ""), "gzip"):
        return Response(
            content=cache.catalogue_gzip,
            media_type="application/json",
            headers={"Content-Encoding": "gzip", "Vary": "Accept-Encoding"},
        )
    # The identity response needs no Vary here. GZipMiddleware adds it, and a second value would
    # duplicate the header.
    return Response(
        content=cache.catalogue_body,
        media_type="application/json",
    )
