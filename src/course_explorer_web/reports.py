"""Serialize one web command report with the serving dataset identity and web-only metadata."""

from __future__ import annotations

import json

from fastapi import Response
from pydantic import BaseModel

from course_explorer_web.dataset import ServingDataset


def dataset_report_response(
    report: BaseModel, serving: ServingDataset, **metadata: object
) -> Response:
    """Serialize a report in JSON mode with the dataset identity and supplied web-only metadata.

    The report is serialized once, and the identity and metadata are appended as one compact object
    body, so no second dump of the report is built. Only the report's declared fields, the opaque
    identity and the named metadata leave the server.
    """
    payload = report.model_dump_json()
    if not payload.endswith("}"):
        raise ValueError("a report serialized to a JSON object is required")
    fields = json.dumps(
        {"dataset_identity": serving.identity, **metadata},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    separator = b"" if payload == "{}" else b","
    content = payload[:-1].encode() + separator + fields[1:].encode()
    return Response(content=content, media_type="application/json")
