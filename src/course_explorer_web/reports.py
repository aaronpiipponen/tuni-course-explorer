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

    Only the report's declared fields, the opaque identity and the named metadata leave the server.
    """
    payload = report.model_dump(mode="json")
    payload["dataset_identity"] = serving.identity
    payload.update(metadata)
    return Response(
        content=json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        media_type="application/json",
    )
