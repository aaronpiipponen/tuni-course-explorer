"""Opt-in PostgreSQL proofs for the composed import boundary and retained verification."""

from __future__ import annotations

import contextlib
import gzip
import json
import os
from pathlib import Path

import pytest
from sqlalchemy import func, select

from course_explorer.administration import (
    administrative_json,
    atomic_write_private_text,
    session_directory,
    utc_now,
)
from course_explorer.config import CaptureSettings, NormalizationSettings
from course_explorer.db.models import IngestionRun, SourceSnapshot
from course_explorer.enums import SourceObjectType
from course_explorer.ingestion import commands as ingestion_commands
from course_explorer.ingestion.repository import CaptureRepository
from course_explorer_admin import lifecycle, local_stages, mechanics
from course_explorer_admin.lifecycle import (
    IngestionOptions,
    IngestionProgress,
    LifecycleContext,
    LifecycleSession,
    LifecycleState,
    read_lifecycle_state,
)
from course_explorer_admin.local_stages import IngestionStage
from course_explorer_admin.worker import run_lifecycle_worker
from tests.admin._lifecycle_support import LocalLifecycleRunner, configure_environment
from tests.ingestion._normalization_repository_support import (
    build_completed_fixture_store,
    normalized_database_digest,
)
from tests.support import settings_factory

pytestmark = [
    pytest.mark.integration,
]

SESSION_ID = "0" * 32
REVISION = "a" * 40
IDENTITY = "b" * 64


def _seed_ingestion_session(
    root: Path, store, *, options: IngestionOptions
) -> tuple[LifecycleSession, LifecycleState]:
    """Publish one current receipt/state naming this test process as the owned worker."""
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    directory = session_directory(root, SESSION_ID)
    directory.mkdir(mode=0o700, parents=False, exist_ok=False)
    session = LifecycleSession(
        schema_version=1,
        session_id=SESSION_ID,
        stage="ingestion",
        revision=REVISION,
        identity_sha256=IDENTITY,
        options=options,
        created_at=utc_now(),
    )
    atomic_write_private_text(directory / "session.json", administrative_json(session))
    process = mechanics.OwnedProcessRecord(
        schema_version=1,
        pid=os.getpid(),
        argv=mechanics.read_process_command_line(os.getpid()) or ("pytest",),
        boot_id=mechanics.current_boot_id(),
    )
    state = LifecycleState(
        schema_version=1,
        session_id=SESSION_ID,
        lifecycle="paused",
        requested_action="run",
        process=process,
        progress=IngestionProgress(
            kind="ingestion",
            stage="selecting",
            response_count=0,
            verified_response_count=0,
            normalized=False,
        ),
        work_complete=False,
        owned_services=(),
        active_seconds=0.0,
        running_since=None,
        error_type=None,
    )
    lifecycle.write_lifecycle_state(root, state)
    return session, state


def _clear_owned_process(root: Path) -> None:
    """Clear only the recorded owner so a foreground stop never waits on the pytest process."""
    state = read_lifecycle_state(root)
    assert state is not None
    lifecycle.write_lifecycle_state(root, state.model_copy(update={"process": None}))


def _provenance_counts(factory) -> tuple[int, int]:
    """Return scalar ingestion-run and source-snapshot row counts, never full rows."""
    with factory.begin() as session:
        runs = session.scalar(select(func.count()).select_from(IngestionRun))
        snapshots = session.scalar(select(func.count()).select_from(SourceSnapshot))
    return int(runs), int(snapshots)


def test_import_boundary_callbacks_gate_capture_to_normalization_atomically(
    database: tuple[object, object], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The real worker refuses normalization atomically, then a re-armed worker completes it."""
    _, factory = database
    capture_repository = CaptureRepository(factory)
    # The fixture store records a cwd-relative manifest path, so build and open it from tmp_path.
    monkeypatch.chdir(tmp_path)
    store = build_completed_fixture_store(tmp_path, capture_repository)
    before = normalized_database_digest(factory)

    capture_settings = settings_factory(CaptureSettings).model_copy(
        update={"raw_data_root": store.run_root.parent}
    )
    normalization_settings = settings_factory(NormalizationSettings)
    monkeypatch.setattr(
        ingestion_commands, "_database_context", lambda settings: contextlib.nullcontext(factory)
    )
    monkeypatch.setattr(ingestion_commands, "load_capture_settings", lambda: capture_settings)
    monkeypatch.setattr(
        ingestion_commands, "load_normalization_settings", lambda: normalization_settings
    )
    monkeypatch.setattr(local_stages, "load_capture_settings", lambda: capture_settings)

    options = IngestionOptions(kind="ingestion", manifest_path=store.manifest_relative_path)
    root = tmp_path / "lifecycle"
    _, seeded_state = _seed_ingestion_session(root, store, options=options)
    process = seeded_state.process
    assert process is not None

    configure_environment(monkeypatch)
    monkeypatch.setattr(local_stages, "stage_state_root", lambda stage: root)
    runner = LocalLifecycleRunner(root=root, running={"db"})

    # One unretained capture directory under the same raw root with one tiny file.
    older = store.run_root.parent / "older-run"
    older.mkdir()
    (older / "tiny.txt").write_text("older\n", encoding="utf-8")

    real_checkpoint = LifecycleContext.checkpoint
    requested = {"enabled": True, "done": False}

    def checkpoint_with_pause(self, progress) -> None:
        real_checkpoint(self, progress)
        if (
            requested["enabled"]
            and not requested["done"]
            and isinstance(progress, IngestionProgress)
            and progress.stage == "before_normalization"
        ):
            requested["done"] = True
            with mechanics.exclusive_action_lock(
                self.root, controller_name=self.session.stage, blocking=True
            ):
                current = read_lifecycle_state(self.root)
                assert current is not None
                lifecycle.write_lifecycle_state(
                    self.root, current.model_copy(update={"requested_action": "pause"})
                )

    monkeypatch.setattr(LifecycleContext, "checkpoint", checkpoint_with_pause)

    stage = IngestionStage()
    refused = run_lifecycle_worker(stage, root, SESSION_ID)
    assert refused.lifecycle == "paused"
    # The capture-to-normalization gate refused, so no normalized row was published.
    assert normalized_database_digest(factory) == before

    # Status never prunes. An ordinary idle stop deletes only the unretained capture and
    # preserves every retained byte and the pre-import database digest.
    retained_manifest_bytes = store.manifest_path.read_bytes()
    envelope_bytes = {
        path.name: path.read_bytes() for path in sorted((store.run_root / "responses").glob("*"))
    }
    status = local_stages.run_ingestion_command("status", runner=runner)
    assert status.lifecycle == "paused"
    assert store.run_root.is_dir() and older.is_dir()

    _clear_owned_process(root)
    stopped = local_stages.run_ingestion_command("stop", runner=runner)
    assert stopped.lifecycle == "idle"
    assert not older.exists()
    assert store.manifest_path.read_bytes() == retained_manifest_bytes
    assert {
        path.name: path.read_bytes() for path in sorted((store.run_root / "responses").glob("*"))
    } == envelope_bytes
    assert normalized_database_digest(factory) == before

    # Re-arm the retained state with its recorded owner and complete through the worker.
    requested["enabled"] = False
    state = read_lifecycle_state(root)
    assert state is not None
    lifecycle.write_lifecycle_state(
        root, state.model_copy(update={"requested_action": "run", "process": process})
    )
    completed = run_lifecycle_worker(stage, root, SESSION_ID)
    assert completed.lifecycle == "completed"
    final_state = read_lifecycle_state(root)
    assert final_state is not None
    assert isinstance(final_state.progress, IngestionProgress)
    assert final_state.progress.normalized is True
    after = normalized_database_digest(factory)
    counts = {entry[0]: len(entry) - 1 for entry in after}
    assert counts["course_versions"] == 6
    assert counts["module_versions"] == 3

    # The normalization result is idempotent: a repeat worker run writes the same rows.
    lifecycle.write_lifecycle_state(
        root, final_state.model_copy(update={"requested_action": "run"})
    )
    assert run_lifecycle_worker(stage, root, SESSION_ID).lifecycle == "completed"
    assert normalized_database_digest(factory) == after

    # A completed idle stop prunes the whole raw root while normalized and provenance rows stay.
    provenance_counts = _provenance_counts(factory)
    _clear_owned_process(root)
    final_stop = local_stages.run_ingestion_command("stop", runner=runner)
    assert final_stop.lifecycle == "idle"
    final_idle = read_lifecycle_state(root)
    assert final_idle is not None and final_idle.work_complete is True
    assert not store.run_root.exists()
    assert normalized_database_digest(factory) == after
    assert _provenance_counts(factory) == provenance_counts


def test_import_verification_prefix_resumes_from_retained_evidence(
    database: tuple[object, object], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A reopened current run re-checks its whole retained prefix before normalization."""
    _, factory = database
    capture_repository = CaptureRepository(factory)
    # The fixture store records a cwd-relative manifest path, so build and open it from tmp_path.
    monkeypatch.chdir(tmp_path)
    store = build_completed_fixture_store(tmp_path, capture_repository)
    total = len(store.manifest.responses)

    capture_settings = settings_factory(CaptureSettings).model_copy(
        update={"raw_data_root": store.run_root.parent}
    )
    normalization_settings = settings_factory(NormalizationSettings)
    monkeypatch.setattr(
        ingestion_commands, "_database_context", lambda settings: contextlib.nullcontext(factory)
    )
    monkeypatch.setattr(ingestion_commands, "load_capture_settings", lambda: capture_settings)
    monkeypatch.setattr(
        ingestion_commands, "load_normalization_settings", lambda: normalization_settings
    )

    # Corrupt an envelope in the retained prefix while leaving manifest hashes/bytes untouched.
    course_response = next(
        response
        for response in store.manifest.responses
        if response.object_type is SourceObjectType.COURSE_UNIT and response.objects
    )
    offset = store.manifest.responses.index(course_response) + 1
    envelope_path = store.run_root / course_response.response_path
    original_bytes = envelope_path.read_bytes()
    body = json.loads(gzip.decompress(original_bytes))
    body[0]["content"]["en"] = "corrupt prefix content"
    envelope_path.write_bytes(
        gzip.compress(
            json.dumps(body, sort_keys=True, separators=(",", ":")).encode(),
            compresslevel=9,
            mtime=0,
        )
    )

    before = normalized_database_digest(factory)
    with pytest.raises(ValueError):
        ingestion_commands.run_capture_command(
            resume_manifest=Path(store.manifest_relative_path),
            verification_start_index=offset,
        )
    # The reopened run refuses the durable offset and detects the corrupt prefix before any write.
    assert normalized_database_digest(factory) == before

    envelope_path.write_bytes(original_bytes)
    verification_boundaries: list[tuple[int, int | None]] = []

    def boundary(stage: str, completed: int, total: int | None) -> bool:
        if stage == "verification":
            verification_boundaries.append((completed, total))
        return True

    result = ingestion_commands.run_capture_command(
        resume_manifest=Path(store.manifest_relative_path),
        verification_start_index=offset,
        on_boundary=boundary,  # type: ignore[arg-type]
    )

    assert result is not None
    assert result.capture.response_count == total
    # One entry verification pass starts at zero. The completed store adds no parser/report pass.
    assert verification_boundaries == [(index, total) for index in range(total)]
    assert result.normalization.new_course_version_count == 6
