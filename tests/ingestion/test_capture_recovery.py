"""Capture recovery, resume, publication-failure, and discovery tests."""

from __future__ import annotations

import hashlib
from pathlib import Path
from uuid import uuid4

import pytest

from course_explorer.enums import (
    IngestionRunStatus,
    SourceObjectType,
)
from course_explorer.ingestion import manifest as manifest_module
from course_explorer.ingestion.capture import capture_curriculum
from course_explorer.ingestion.manifest import RawCaptureStore
from course_explorer.ingestion.source import CapturedResponse
from tests.ingestion._capture_support import (
    FailingPersistence,
    FixtureFailure,
    FixtureSource,
    PersistenceFailure,
    RecordingCapturePersistence,
    fixture,
    new_store,
    parsed,
)


def test_failed_capture_resume_reuses_verification_and_fetches_only_missing_evidence(
    tmp_path: Path,
) -> None:
    """A reopened failed resume re-checks its retained prefix and fetches only missing evidence."""
    store = new_store(tmp_path)
    persistence = RecordingCapturePersistence()
    with pytest.raises(FixtureFailure):
        capture_curriculum(
            FixtureSource(fail_method="module_exact"),
            store,
            persistence,
            checkpoint_response_count=100,
        )
    failed_responses = len(store.manifest.responses)
    store = RawCaptureStore.open(tmp_path / "raw", store.manifest_path)
    verification_boundaries: list[tuple[int, int | None]] = []

    def boundary(stage: str, completed: int, total: int | None) -> bool:
        if stage == "verification":
            verification_boundaries.append((completed, total))
        return True

    resumed_source = FixtureSource()
    report = capture_curriculum(
        resumed_source,
        store,
        persistence,
        checkpoint_response_count=100,
        verification_start_index=failed_responses - 1,
        on_boundary=boundary,  # type: ignore[arg-type]
    )

    assert report.status is IngestionRunStatus.COMPLETED
    assert len(store.manifest.responses) > failed_responses
    # A reopened store ignores the durable offset and re-checks its retained prefix from zero.
    assert verification_boundaries[0] == (0, failed_responses)
    assert not [value for method, value in resumed_source.calls if method == "course_exact"]
    assert [value for method, value in resumed_source.calls if method == "module_exact"] == [
        ["module-direct-v1"]
    ]
    assert [method for method, _ in resumed_source.calls].count("course_search") == 1
    assert [method for method, _ in resumed_source.calls].count("degree_search") == 1
    assert [method for method, _ in resumed_source.calls].count("study_search") == 1


def test_capture_store_checkpoints_multiple_responses_with_one_manifest_publication_and_adopts_batch_orphans(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed batch publication leaves exact orphans that one retry adopts atomically."""
    inputs = (
        (
            CapturedResponse(
                "/api/course-units", (("id", "course-batch"),), fixture("exact-courses.json")
            ),
            SourceObjectType.COURSE_UNIT,
            tuple(parsed("exact-courses.json")),
        ),
        (
            CapturedResponse(
                "/api/modules", (("id", "module-batch"),), fixture("exact-modules.json")
            ),
            SourceObjectType.MODULE,
            tuple(parsed("exact-modules.json")),
        ),
        (
            CapturedResponse("/api/course-units", (("id", "empty"),), fixture("empty.json")),
            SourceObjectType.COURSE_UNIT,
            (),
        ),
    )
    store = new_store(tmp_path)
    original_manifest = store.manifest
    real_replace = manifest_module.os.replace
    manifest_attempts = 0

    def fail_first_manifest_replace(source, destination, *args, **kwargs):
        nonlocal manifest_attempts
        if Path(destination) == store.manifest_path:
            manifest_attempts += 1
            if manifest_attempts == 1:
                raise OSError("publication interrupted")
        return real_replace(source, destination, *args, **kwargs)

    with monkeypatch.context() as failing:
        failing.setattr(manifest_module.os, "replace", fail_first_manifest_replace)
        with pytest.raises(OSError):
            store.checkpoint_responses(inputs)
    assert store.manifest == original_manifest
    assert len(tuple((store.run_root / "responses").iterdir())) == 3

    reopened = RawCaptureStore.open(tmp_path / "raw", store.manifest_path)
    records = reopened.checkpoint_responses(inputs)
    assert len(records) == 3
    assert len(reopened.manifest.responses) == 3

    with pytest.raises(ValueError):
        reopened.checkpoint_responses(
            (
                (
                    CapturedResponse("/api/course-units", (("id", "course-batch"),), b"[1]"),
                    SourceObjectType.COURSE_UNIT,
                    (),
                ),
            )
        )


def test_resume_adopts_matching_orphan_and_rejects_changed_or_corrupt_evidence(
    tmp_path: Path,
) -> None:
    """Orphan adoption is exact. Changed or corrupt evidence is never overwritten."""
    captured = CapturedResponse("/api/test", (("id", "one"),), b"[]")
    staging = RawCaptureStore.create(tmp_path / "staging-raw", run_id=uuid4())
    staging.checkpoint_responses(((captured, None, ()),))
    staging_envelope = next((staging.run_root / "responses").iterdir())

    store = new_store(tmp_path)
    destination = store.run_root / "responses"
    destination.mkdir()
    adopted_path = destination / staging_envelope.name
    adopted_path.write_bytes(staging_envelope.read_bytes())

    adopted = store.checkpoint_responses(((captured, None, ()),))[0]
    assert adopted.response_path == adopted_path.relative_to(store.run_root).as_posix()
    assert adopted_path.read_bytes() == staging_envelope.read_bytes()
    adopted_path.write_bytes(b"corrupt")
    with pytest.raises(ValueError):
        store.verify()


def test_capture_marks_failure_and_reraises_the_source_exception(tmp_path: Path) -> None:
    """Partial failure is visible in manifest and the source error escapes."""
    store = new_store(tmp_path)
    with pytest.raises(FixtureFailure):
        capture_curriculum(
            FixtureSource(fail_method="course_search"),
            store,
            RecordingCapturePersistence(),
            checkpoint_response_count=100,
        )
    assert store.manifest.status is IngestionRunStatus.FAILED
    assert (
        store.manifest.failure_type == f"{FixtureFailure.__module__}.{FixtureFailure.__qualname__}"
    )
    assert "method" not in store.manifest.failure_type


def test_capture_reports_failure_state_persistence_with_the_source_error(tmp_path: Path) -> None:
    """Failure-state persistence errors join the capture error."""
    store = new_store(tmp_path)
    persistence = FailingPersistence()

    with pytest.raises(ExceptionGroup) as error:
        capture_curriculum(
            FixtureSource(fail_method="course_search"),
            store,
            persistence,
            checkpoint_response_count=100,
        )
    assert {type(exception) for exception in error.value.exceptions} == {
        FixtureFailure,
        PersistenceFailure,
    }


def test_manifest_open_defers_verification_and_discovery_locates_direct_runs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Open binds the manifest without verifying envelopes. Discovery lists strict candidates."""
    # Discovery returns paths relative to the current working directory, exactly like
    # ``RawCaptureStore.manifest_relative_path``, so the caller can pass one straight back.
    monkeypatch.chdir(tmp_path)

    store = new_store(tmp_path)
    capture_curriculum(
        FixtureSource(), store, RecordingCapturePersistence(), checkpoint_response_count=100
    )
    opened_manifest = store.manifest_path.read_bytes()
    reopened = RawCaptureStore.open(Path("raw"), store.manifest_path)
    assert reopened.manifest_sha256 == hashlib.sha256(opened_manifest).hexdigest()
    assert reopened.manifest_sha256 == store.manifest_sha256
    envelope = next((store.run_root / "responses").iterdir())
    envelope.write_bytes(b"corrupt")
    # Opening succeeded above. The corrupt envelope only fails the explicit verification pass.
    with pytest.raises(ValueError):
        RawCaptureStore.open(Path("raw"), store.manifest_path).verify()
    empty_root = Path("no-runs")
    assert manifest_module.discover_capture_manifests(empty_root) == ()

    discovered = manifest_module.discover_capture_manifests(Path("raw"))
    assert discovered == (Path(reopened.manifest_relative_path),)

    symlinked = Path("raw") / "linked-run"
    symlinked.symlink_to(store.run_root)
    with pytest.raises(ValueError):
        manifest_module.discover_capture_manifests(Path("raw"))
    symlinked.unlink()

    bad_run = Path("raw") / "broken-run"
    bad_run.mkdir()
    (bad_run / "manifest.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError):
        manifest_module.discover_capture_manifests(Path("raw"))
