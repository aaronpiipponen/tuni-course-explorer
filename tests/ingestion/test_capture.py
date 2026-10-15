"""Immutable capture, resume, closure, and replay tests."""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from course_explorer.enums import (
    IngestionRunStatus,
    SourceObjectType,
)
from course_explorer.ingestion.capture import capture_curriculum
from course_explorer.ingestion.manifest import RawCaptureStore
from tests.ingestion._capture_support import (
    FixtureSource,
    RecordingCapturePersistence,
    fixture,
    new_store,
    parsed,
)


def test_capture_writes_deterministic_gzip_manifest_and_replays_raw_positions(
    tmp_path: Path,
) -> None:
    """Exact bytes, canonical paths, atomic manifests, and raw positions survive replay."""
    store = new_store(tmp_path)
    repository = RecordingCapturePersistence()
    report = capture_curriculum(FixtureSource(), store, repository, checkpoint_response_count=100)

    assert report.status is IngestionRunStatus.COMPLETED
    assert report.manifest_path == store.manifest_relative_path
    assert store.run_root.name == f"20260910T120000000000Z-{store.manifest.run_id}"
    assert not tuple(store.run_root.glob(".manifest-*.tmp"))
    assert all(
        response.object_type is None
        for response in store.manifest.responses
        if response.request_path
        in {"/api/curriculum-periods", "/api/course-unit-search", "/api/module-search"}
    )
    assert any(
        response.object_type is SourceObjectType.COURSE_UNIT and not response.objects
        for response in store.manifest.responses
    )
    assert any(
        response.object_type is SourceObjectType.MODULE and not response.objects
        for response in store.manifest.responses
    )
    exact = next(
        response
        for response in store.manifest.responses
        if response.response_path.startswith("responses/")
        and response.objects
        and response.objects[0].source_object_id == "course-b-v1"
    )
    assert gzip.decompress((store.run_root / exact.response_path).read_bytes()) == fixture(
        "exact-courses.json"
    )
    assert [item.value["id"] for item in store.iter_objects(SourceObjectType.COURSE_UNIT)][:2] == [
        "course-b-v1",
        "course-a-v1",
    ]
    assert store.manifest.raw_root_path == Path(store.manifest.raw_root_path).as_posix()
    assert all(
        not Path(response.response_path).is_absolute()
        and Path(response.response_path).as_posix() == response.response_path
        for response in store.manifest.responses
    )

    # Response replay exposes the verified bytes through the same completed store.
    responses = tuple(store.iter_responses(request_path="/api/curriculum-periods"))
    assert len(responses) == 1
    assert json.loads(responses[0].body) == parsed("periods.json")


def test_capture_closes_each_typed_group_once_and_records_unresolved_groups(
    tmp_path: Path,
) -> None:
    """Typed closure follows cycles once and retains empty groups by type."""
    source = FixtureSource()
    store = new_store(tmp_path)
    persistence = RecordingCapturePersistence()
    capture_curriculum(source, store, persistence, checkpoint_response_count=2)

    assert [value for method, value in source.calls if method == "course_group"] == [
        "course-group-empty",
        "course-group-ref",
        "course-group-ref-2",
    ]
    assert [value for method, value in source.calls if method == "module_group"] == [
        "module-group-cycle",
        "module-group-empty",
    ]
    assert store.manifest.unresolved_course_group_ids == ("course-group-empty",)
    assert store.manifest.unresolved_module_group_ids == ("module-group-empty",)
    assert any(size > 1 for size in persistence.register_calls)


def test_capture_pause_stops_before_network_pull_and_keeps_running_manifest(tmp_path: Path) -> None:
    """A rejected boundary before the first request returns ``None`` without a failed manifest."""
    store = new_store(tmp_path)
    source = FixtureSource()
    persistence = RecordingCapturePersistence()
    calls: list[tuple[str, int, int | None]] = []
    report = capture_curriculum(
        source,
        store,
        persistence,
        checkpoint_response_count=100,
        on_boundary=lambda stage, completed, total: (
            calls.append((stage, completed, total)) or False
        ),
    )
    assert report is None
    assert store.manifest.status is IngestionRunStatus.RUNNING
    assert store.manifest.failure_type is None
    # The network pull never ran because its boundary was rejected first.
    assert source.calls == []

    # The same store resumes normally and completes with the collected evidence.
    resumed_source = FixtureSource()
    resumed = RawCaptureStore.open(tmp_path / "raw", store.manifest_path)
    completed_report = capture_curriculum(
        resumed_source, resumed, persistence, checkpoint_response_count=100
    )
    assert completed_report is not None
    assert completed_report.status is IngestionRunStatus.COMPLETED


def test_completed_capture_rejects_unexpected_response_file(tmp_path: Path) -> None:
    """A completed capture refuses a regular non-envelope file without deleting it."""
    store = new_store(tmp_path)
    persistence = RecordingCapturePersistence()
    capture_curriculum(FixtureSource(), store, persistence, checkpoint_response_count=100)
    manifest_bytes = store.manifest_path.read_bytes()
    unexpected = store.run_root / "responses" / "unexpected.txt"
    unexpected.write_text("orphan", encoding="utf-8")

    resumed = RawCaptureStore.open(tmp_path / "raw", store.manifest_path)
    with pytest.raises(ValueError):
        capture_curriculum(FixtureSource(), resumed, persistence, checkpoint_response_count=100)

    assert unexpected.read_text(encoding="utf-8") == "orphan"
    assert store.manifest_path.read_bytes() == manifest_bytes


def test_completed_manifest_checkpoint_can_stop_before_finalization(
    tmp_path: Path,
) -> None:
    """Completion publishes a durable capture checkpoint before the final directory check."""
    store = new_store(tmp_path)
    persistence = RecordingCapturePersistence()
    calls: list[tuple[str, int, int | None]] = []
    rejected = False

    def boundary(stage: str, completed: int, total: int | None) -> bool:
        nonlocal rejected
        calls.append((stage, completed, total))
        if (
            not rejected
            and stage == "capture"
            and store.manifest.status is IngestionRunStatus.COMPLETED
        ):
            rejected = True
            return False
        return True

    report = capture_curriculum(
        FixtureSource(),
        store,
        persistence,
        checkpoint_response_count=100,
        on_boundary=boundary,  # type: ignore[arg-type]
    )

    assert report is None
    assert rejected
    # Completed manifest bytes and matching provenance stay committed and verifiable.
    assert store.manifest.status is IngestionRunStatus.COMPLETED
    persistence.verify_run(store.manifest, store.manifest_relative_path)
    assert store.verify()

    # The same store continues into the retained verification/normalization path with no source work.
    resumed_source = FixtureSource()
    resumed = RawCaptureStore.open(tmp_path / "raw", store.manifest_path)
    completed_report = capture_curriculum(
        resumed_source, resumed, persistence, checkpoint_response_count=100
    )
    assert completed_report is not None
    assert completed_report.status is IngestionRunStatus.COMPLETED
    assert resumed_source.calls == []
