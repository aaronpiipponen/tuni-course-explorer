"""Shared manifest fixture for the raw capture-repository provenance tests."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from course_explorer.enums import (
    IngestionRunStatus,
    SourceObjectType,
)
from course_explorer.ingestion.manifest import (
    CapturedObjectRecord,
    CapturedResponseRecord,
    CaptureManifest,
)


def capture_manifest(status: IngestionRunStatus = IngestionRunStatus.RUNNING) -> CaptureManifest:
    """Build one compact manifest-shaped provenance contract for repository tests."""
    run_id = uuid.uuid4()
    started_at = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)
    finished_at = started_at if status is not IngestionRunStatus.RUNNING else None
    response = CapturedResponseRecord(
        request_path="/api/course-units",
        request_params=(("id", "course-v1"),),
        response_path="responses/" + "a" * 64 + "-" + "b" * 64 + ".json.gz",
        body_sha256="b" * 64,
        body_size=1,
        object_type=SourceObjectType.COURSE_UNIT,
        objects=(
            CapturedObjectRecord(
                object_type=SourceObjectType.COURSE_UNIT,
                source_object_id="course-v1",
                source_group_id="course-group",
                response_item_index=0,
                source_hash="c" * 64,
            ),
        ),
    )
    module_response = CapturedResponseRecord(
        request_path="/api/modules",
        request_params=(("id", "module-v1"),),
        response_path="responses/" + "d" * 64 + "-" + "e" * 64 + ".json.gz",
        body_sha256="e" * 64,
        body_size=1,
        object_type=SourceObjectType.MODULE,
        objects=(
            CapturedObjectRecord(
                object_type=SourceObjectType.MODULE,
                source_object_id="module-v1",
                source_group_id="module-group",
                response_item_index=0,
                source_hash="f" * 64,
            ),
        ),
    )
    return CaptureManifest(
        format_version=2,
        run_id=run_id,
        status=status,
        started_at=started_at,
        finished_at=finished_at,
        raw_root_path="data/raw",
        periods=(),
        responses=(response, module_response),
        unresolved_course_group_ids=(),
        unresolved_module_group_ids=(),
        failure_type=None,
        course_version_limit=None,
        seed_course_version_ids=(),
        seed_selection_complete=False,
    )
