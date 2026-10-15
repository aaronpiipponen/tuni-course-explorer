"""Database provenance persistence for immutable curriculum capture manifests."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from course_explorer.db.models import IngestionRun, SourceSnapshot
from course_explorer.db.session import session_scope
from course_explorer.ingestion.manifest import CapturedResponseRecord, CaptureManifest


class CapturePersistence(Protocol):
    """Persistence boundary used by the capture service and tests."""

    def ensure_run(self, manifest: CaptureManifest, manifest_path: str) -> None: ...

    def register_responses(
        self, run_id: UUID, responses: Sequence[CapturedResponseRecord]
    ) -> None: ...

    def verify_run(self, manifest: CaptureManifest, manifest_path: str) -> None: ...


class CaptureRepository(CapturePersistence):
    """Idempotently reconcile current-run manifest evidence with ingestion_runs and source_snapshots."""

    def __init__(self, factory: sessionmaker[Session]):
        self._factory = factory

    def ensure_run(self, manifest: CaptureManifest, manifest_path: str) -> None:
        """Insert one run or reconcile its mutable lifecycle fields."""
        with session_scope(self._factory) as session:
            run = session.get(IngestionRun, manifest.run_id)
            if run is None:
                session.add(
                    IngestionRun(
                        id=manifest.run_id,
                        status=manifest.status,
                        started_at=manifest.started_at,
                        finished_at=manifest.finished_at,
                        raw_root_path=manifest.raw_root_path,
                        manifest_path=manifest_path,
                    )
                )
                return
            self._validate_run_identity(run, manifest, manifest_path)
            run.status = manifest.status
            run.finished_at = manifest.finished_at

    @staticmethod
    def _validate_run_identity(
        run: IngestionRun, manifest: CaptureManifest, manifest_path: str
    ) -> None:
        if (
            run.started_at != manifest.started_at
            or run.raw_root_path != manifest.raw_root_path
            or run.manifest_path != manifest_path
        ):
            raise ValueError("ingestion run immutable identity does not match manifest")

    def register_responses(self, run_id: UUID, responses: Sequence[CapturedResponseRecord]) -> None:
        """Insert or exactly reconcile one response checkpoint in one transaction."""
        responses = tuple(responses)
        if not responses:
            return
        response_paths = tuple(response.response_path for response in responses)
        if len(response_paths) != len(set(response_paths)):
            raise ValueError("checkpoint contains duplicate response paths")
        expected = {
            (response.response_path, record.response_item_index): (response, record)
            for response in responses
            for record in response.objects
        }
        with session_scope(self._factory) as session:
            if session.get(IngestionRun, run_id) is None:
                raise ValueError("cannot register response for missing ingestion run")
            actual = tuple(
                session.scalars(
                    select(SourceSnapshot).where(
                        SourceSnapshot.ingestion_run_id == run_id,
                        SourceSnapshot.response_path.in_(response_paths),
                    )
                )
            )
            actual_keys = {
                (snapshot.response_path, snapshot.response_item_index) for snapshot in actual
            }
            for snapshot in actual:
                key = (snapshot.response_path, snapshot.response_item_index)
                expected_entry = expected.get(key)
                if expected_entry is None:
                    raise ValueError(
                        "database contains snapshot not present in manifest checkpoint"
                    )
                response, record = expected_entry
                if not _snapshot_matches(snapshot, record, response.response_path):
                    raise ValueError("source snapshot provenance conflicts with manifest")

            for response in responses:
                for record in response.objects:
                    key = (response.response_path, record.response_item_index)
                    if key not in actual_keys:
                        session.add(
                            SourceSnapshot(
                                ingestion_run_id=run_id,
                                object_type=record.object_type,
                                source_object_id=record.source_object_id,
                                source_group_id=record.source_group_id,
                                response_path=response.response_path,
                                response_item_index=record.response_item_index,
                                source_hash=record.source_hash,
                            )
                        )

    def verify_run(self, manifest: CaptureManifest, manifest_path: str) -> None:
        """Require exact run lifecycle and object-snapshot equality."""
        with session_scope(self._factory) as session:
            run = session.get(IngestionRun, manifest.run_id)
            if run is None:
                raise ValueError("manifest ingestion run is missing from database")
            self._validate_run_identity(run, manifest, manifest_path)
            if run.status is not manifest.status or run.finished_at != manifest.finished_at:
                raise ValueError("database run lifecycle does not match manifest")

            actual = [
                (
                    snapshot.object_type.value,
                    snapshot.source_object_id,
                    snapshot.source_group_id,
                    snapshot.response_path,
                    snapshot.response_item_index,
                    snapshot.source_hash,
                )
                for snapshot in session.scalars(
                    select(SourceSnapshot).where(SourceSnapshot.ingestion_run_id == manifest.run_id)
                )
            ]
            expected = [
                (
                    record.object_type.value,
                    record.source_object_id,
                    record.source_group_id,
                    response.response_path,
                    record.response_item_index,
                    record.source_hash,
                )
                for response in manifest.responses
                for record in response.objects
            ]
            if sorted(actual) != sorted(expected):
                raise ValueError("database source snapshots do not exactly match manifest")


def _snapshot_matches(
    snapshot: SourceSnapshot, record: CapturedResponseRecord, response_path: str
) -> bool:
    return (
        snapshot.object_type is record.object_type
        and snapshot.source_object_id == record.source_object_id
        and snapshot.source_group_id == record.source_group_id
        and snapshot.response_path == response_path
        and snapshot.response_item_index == record.response_item_index
        and snapshot.source_hash == record.source_hash
    )
