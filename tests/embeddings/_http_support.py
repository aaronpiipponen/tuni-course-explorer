"""Shared synthetic embedding-response builders for the model HTTP boundary tests."""

import json
from typing import Any

import httpx

from course_explorer.constants import COURSE_EMBEDDING_DIMENSION


def vector(*components: float) -> list[float]:
    """Build one full-length vector keeping its distinctive leading components."""
    return [*components, *([0.0] * (COURSE_EMBEDDING_DIMENSION - len(components)))]


def embedding_response(entries: list[dict[str, Any]], **extra: Any) -> httpx.Response:
    """Build one successful embedding response from its data entries and fields."""
    body = {"data": entries, **extra}
    return httpx.Response(200, content=json.dumps(body).encode())
