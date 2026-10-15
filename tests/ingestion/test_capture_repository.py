"""Opt-in PostgreSQL proofs for raw capture-repository provenance reconciliation."""

from __future__ import annotations

import pytest
from sqlalchemy import Engine, select

from course_explorer.db.models import (
    IngestionRun,
    SourceSnapshot,
)
from course_explorer.db.session import session_scope
from course_explorer.enums import (
    IngestionRunStatus,
    SourceObjectType,
)
from course_explorer.ingestion.repository import CaptureRepository
from tests.ingestion._capture_repository_support import capture_manifest

pytestmark = [
    pytest.mark.integration,
]


def test_capture_repository_reconciles_manifest_without_duplicate_snapshots(
    database: tuple[Engine, object],
) -> None:
    """Repository inserts exact provenance once and reconciles completed lifecycle."""
    _, factory = database
    repository = CaptureRepository(factory)
    manifest = capture_manifest(IngestionRunStatus.COMPLETED)
    manifest_path = "data/raw/run/manifest.json"

    repository.ensure_run(manifest, manifest_path)
    repository.register_responses(manifest.run_id, manifest.responses)
    repository.register_responses(manifest.run_id, manifest.responses)
    repository.verify_run(manifest, manifest_path)

    with session_scope(factory) as session:
        run = session.get(IngestionRun, manifest.run_id)
        snapshots = list(
            session.scalars(
                select(SourceSnapshot).where(SourceSnapshot.ingestion_run_id == manifest.run_id)
            )
        )
    assert run is not None
    assert run.status is IngestionRunStatus.COMPLETED
    assert run.raw_root_path == "data/raw"
    assert run.manifest_path == manifest_path
    assert len(snapshots) == 2
    assert snapshots[0].response_path == manifest.responses[0].response_path
    assert snapshots[0].response_item_index == 0
    assert snapshots[0].source_hash == "c" * 64

    with session_scope(factory) as session:
        session.delete(snapshots[0])
    repository.register_responses(manifest.run_id, (manifest.responses[0],))
    repository.verify_run(manifest, manifest_path)


def test_capture_repository_rejects_conflicting_or_missing_provenance(
    database: tuple[Engine, object],
) -> None:
    """Conflicting positions and extra database rows fail exact reconciliation."""
    _, factory = database
    repository = CaptureRepository(factory)
    manifest = capture_manifest()
    manifest_path = "data/raw/run/manifest.json"
    repository.ensure_run(manifest, manifest_path)
    response = manifest.responses[0]
    repository.register_responses(manifest.run_id, (response,))
    conflicting = response.model_copy(
        update={"objects": (response.objects[0].model_copy(update={"source_hash": "d" * 64}),)}
    )
    with pytest.raises(ValueError):
        repository.register_responses(manifest.run_id, (conflicting,))

    with session_scope(factory) as session:
        session.add(
            SourceSnapshot(
                ingestion_run_id=manifest.run_id,
                object_type=SourceObjectType.MODULE,
                source_object_id="extra-module",
                source_group_id="extra-group",
                response_path="responses/" + "e" * 64 + "-" + "f" * 64 + ".json.gz",
                response_item_index=1,
                source_hash="e" * 64,
            )
        )
    with pytest.raises(ValueError):
        repository.verify_run(manifest, manifest_path)
