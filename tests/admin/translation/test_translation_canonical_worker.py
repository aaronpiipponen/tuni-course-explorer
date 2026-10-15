"""Canonical shared-dataset worker contracts.

These contracts cover the shared canonical worker lifecycle: the policy/composite loader,
non-destructive reusable prepare, the shared run/action/status path, one-time translation import
finalize, and receipt-and-server-proof-gated cleanup with verified import/return authority. They
reuse the stage-local fixture owners in ``_worker_support``. The disposable SQL proof lives in
``tests/admin/test_dataset_database.py``, and this file covers the
restore and repository boundaries.
"""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from pathlib import Path

import pytest

from course_explorer import administration
from course_explorer.administration import administrative_json, atomic_write_private_text
from course_explorer.config import load_administrative_dataset_settings, load_translation_settings
from course_explorer.datasets import DatabaseSnapshot, DatasetReceipt
from course_explorer.teaching_text.service import TranslationImportReport
from course_explorer_admin import datasets as datasets_module
from course_explorer_admin import remote, worker_session
from course_explorer_admin.remote import WorkerDatasetSession, worker_dataset_session_directory
from course_explorer_admin.translation import controller_worker as worker_module
from course_explorer_admin.translation.controller import (
    TranslationControllerImportReceipt,
    TranslationControllerPolicy,
    load_translation_controller_import_receipt,
)
from tests.admin.translation import _worker_support
from tests.config._support import ADMIN_DATASET_KEYS
from tests.datasets._support import sample_verification

SESSION_ID = "0123456789abcdef0123456789abcdef"
REVISION = "a" * 40
SOURCE_ID = "f" * 32
STARTED_AT = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
SNAPSHOT_HASH = "a" * 64


class FakeSelection:
    """Selection double carrying the item count the publisher reads."""

    def __init__(self, count: int) -> None:
        self.items = tuple(object() for _ in range(count))


class FakeEngine:
    """Engine double that records disposal calls."""

    def __init__(self) -> None:
        self.disposed = False

    def dispose(self) -> None:
        self.disposed = True


class RecordingRepository:
    """Repository double recording every upsert input and returning the count report."""

    instances: list[RecordingRepository] = []

    def __init__(self, factory: object) -> None:
        self.factory = factory
        self.calls: list[tuple[object, ...]] = []
        RecordingRepository.instances.append(self)

    def upsert(self, translations) -> TranslationImportReport:
        inputs = tuple(translations)
        self.calls.append(inputs)
        count = len(inputs)
        return TranslationImportReport(
            requested_count=count,
            inserted_count=count,
            updated_count=0,
            unchanged_count=0,
        )


def configure_canonical(monkeypatch: pytest.MonkeyPatch, root: Path) -> None:
    """Point every canonical loader at one temporary repository with deterministic settings."""
    _worker_support.configure(monkeypatch, root)
    for key, value in ADMIN_DATASET_KEYS.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(administration, "repository_root", lambda: root)
    monkeypatch.setattr(remote, "repository_root", lambda: root)
    monkeypatch.setattr(datasets_module, "repository_root", lambda: root)
    # The canonical worker run is invoked with the raw session database pinned and the selected
    # dataset explicitly disabled. The test sets exactly that environment.
    monkeypatch.setenv(
        "POSTGRES_DB", load_administrative_dataset_settings().database_name(SESSION_ID, worker=True)
    )
    monkeypatch.setenv("SELECTED_DATASET_ENABLED", "0")


def canonical_session() -> WorkerDatasetSession:
    """Return one genuine canonical translation session record for this fixture."""
    settings = load_administrative_dataset_settings()
    return WorkerDatasetSession(
        schema_version=1,
        session_id=SESSION_ID,
        revision=REVISION,
        branch="course-search",
        database_name=settings.database_name(SESSION_ID, worker=True),
        stage="translation",
        source_dataset_id=SOURCE_ID,
        course_limit=10,
        input_snapshot=DatabaseSnapshot(
            schema_version=1,
            session_id=SESSION_ID,
            revision=REVISION,
            database_name="course_explorer",
            dump_sha256="c" * 64,
            verification=sample_verification(),
        ),
    )


def write_policy(directory: Path, model: str) -> None:
    atomic_write_private_text(
        directory / "policy.json",
        administrative_json(
            TranslationControllerPolicy(
                schema_version=2,
                session_id=SESSION_ID,
                revision=REVISION,
                translation_model=model,
            )
        ),
    )


def seed_canonical(
    monkeypatch: pytest.MonkeyPatch, root: Path
) -> tuple[Path, WorkerDatasetSession]:
    """Write one canonical session and policy directly, without capture or admission."""
    configure_canonical(monkeypatch, root)
    session = canonical_session()
    directory = worker_dataset_session_directory(SESSION_ID)
    directory.mkdir(mode=0o700, parents=True)
    atomic_write_private_text(directory / "session.json", administrative_json(session))
    write_policy(directory, load_translation_settings().provenance_model)
    return directory, session


def test_canonical_prepare_reuses_full_restore_and_preserves_partial_evidence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Canonical prepare restores once, acknowledges a prepared session without rewriting, and
    refuses partial or mismatched-policy evidence before any database work."""
    directory, session = seed_canonical(monkeypatch, tmp_path)
    restore_calls: list[WorkerDatasetSession] = []
    selection_calls: list[int] = []

    def fake_restore(recorded, *, runner):
        restore_calls.append(recorded)
        return sample_verification()

    def fake_selection(*args, **kwargs):
        selection_calls.append(1)
        return FakeSelection(2)

    monkeypatch.setattr(remote, "prepare_worker_database", fake_restore)
    monkeypatch.setattr(worker_module, "select_translation_work", fake_selection)

    status = worker_session.prepare_worker_session(
        worker_module.TranslationWorkerStage(), session, runner=_worker_support.FakeRunner()
    )
    assert status.lifecycle == "prepared"
    assert status.desired_count == 2
    assert restore_calls == [session]
    assert len(selection_calls) == 1
    control_before = (directory / "control.json").read_bytes()
    state_before = (directory / "state.json").read_bytes()

    repeated = worker_session.prepare_worker_session(
        worker_module.TranslationWorkerStage(), session, runner=_worker_support.FakeRunner()
    )
    assert repeated.lifecycle == "prepared"
    assert repeated.desired_count == 2
    assert restore_calls == [session]
    assert len(selection_calls) == 1
    assert (directory / "control.json").read_bytes() == control_before
    assert (directory / "state.json").read_bytes() == state_before

    write_policy(directory, "foreign-model")
    with pytest.raises(ValueError):
        worker_session.prepare_worker_session(
            worker_module.TranslationWorkerStage(), session, runner=_worker_support.FakeRunner()
        )
    assert restore_calls == [session]
    write_policy(directory, load_translation_settings().provenance_model)

    (directory / "state.json").unlink()
    with pytest.raises(ValueError):
        worker_session.prepare_worker_session(
            worker_module.TranslationWorkerStage(), session, runner=_worker_support.FakeRunner()
        )
    assert restore_calls == [session]
    assert (directory / "control.json").read_bytes() == control_before


def test_canonical_worker_shares_control_and_finalizes_without_relaunch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Canonical run/action/status share the pending-control path, finalize imports once, a matching
    receipt skips the upsert, status is imported, run refuses, and resume never republishes run."""
    directory, session = seed_canonical(monkeypatch, tmp_path)
    _worker_support.write_control(directory, "run")
    _worker_support.write_state(directory, schema_version=2, lifecycle="prepared", desired_count=1)
    _worker_support.FakeOwnedRuntime.instances = []
    monkeypatch.setattr(worker_module, "OwnedWorkerRuntime", _worker_support.FakeOwnedRuntime)
    observed: list[str] = []

    def fake_run(**kwargs):
        observed.append(_worker_support.load_control(directory).requested_action)
        return _worker_support.report(desired=1, generated=1, output=1)

    monkeypatch.setattr(worker_module, "run_translation_command", fake_run)

    assert (
        worker_session.run_worker_session(
            worker_module.TranslationWorkerStage(), SESSION_ID, runner=_worker_support.FakeRunner()
        )
        == 0
    )
    assert observed == ["run"]
    assert _worker_support.FakeOwnedRuntime.instances[0].started
    state = json.loads((directory / "state.json").read_text(encoding="utf-8"))
    assert state["lifecycle"] == "completed"
    assert state["completed_count"] == 1
    # The run published its own runner ownership record. In a real run that process exits.
    _worker_support.script_owned_process_is_alive(monkeypatch, set())

    digest = _worker_support.write_output(directory, [_worker_support.entry("Name")])
    engines: list[FakeEngine] = []

    def fake_engine(settings):
        engine = FakeEngine()
        engines.append(engine)
        return engine

    RecordingRepository.instances = []
    monkeypatch.setattr(worker_module, "create_database_engine", fake_engine)
    monkeypatch.setattr(worker_module, "create_session_factory", lambda engine: object())
    monkeypatch.setattr(worker_module, "DerivedTranslationRepository", RecordingRepository)

    # Two concurrent public finalize callers: the first holds the instance lock while blocked inside
    # the external repository upsert. The second waits at the same lock and then reuses the retained
    # receipt without a second upsert.
    original_upsert = RecordingRepository.upsert
    upsert_entered = threading.Event()
    release_upsert = threading.Event()

    def gated_upsert(self, translations):
        upsert_entered.set()
        release_upsert.wait(timeout=10)
        return original_upsert(self, translations)

    monkeypatch.setattr(RecordingRepository, "upsert", gated_upsert)

    results: list = []
    errors: list[Exception] = []

    def finalize_call() -> None:
        try:
            results.append(
                worker_session.finalize_worker_session(
                    worker_module.TranslationWorkerStage(),
                    SESSION_ID,
                    runner=_worker_support.FakeRunner(),
                )
            )
        except Exception as exc:
            errors.append(exc)

    first = threading.Thread(target=finalize_call)
    first.start()
    assert upsert_entered.wait(timeout=10)
    second = threading.Thread(target=finalize_call)
    second.start()
    release_upsert.set()
    first.join(timeout=15)
    second.join(timeout=15)
    assert not first.is_alive() and not second.is_alive()
    assert errors == []
    assert len(results) == 2
    finalized = results[0]
    assert finalized.lifecycle == "imported"
    assert finalized.completed_count == 1
    assert finalized.remaining_count == 0
    assert finalized.projected_remaining_seconds == 0.0
    assert finalized.output_sha256 == digest
    assert results[1].lifecycle == "imported"
    assert results[1].output_sha256 == digest
    assert len(RecordingRepository.instances) == 1
    assert len(RecordingRepository.instances[0].calls) == 1
    assert len(RecordingRepository.instances[0].calls[0]) == 1
    assert engines[0].disposed
    receipt = load_translation_controller_import_receipt(directory / "import-receipt.json")
    assert receipt.output_count == 1
    assert receipt.output_sha256 == digest
    assert receipt.import_report.requested_count == 1

    assert (
        worker_session.read_worker_status(
            worker_module.TranslationWorkerStage(), SESSION_ID
        ).lifecycle
        == "imported"
    )

    with pytest.raises(ValueError):
        worker_session.run_worker_session(
            worker_module.TranslationWorkerStage(), SESSION_ID, runner=_worker_support.FakeRunner()
        )

    control_before = (directory / "control.json").read_bytes()
    resumed = worker_session.request_worker_action(
        worker_module.TranslationWorkerStage(),
        SESSION_ID,
        "resume",
        runner=_worker_support.FakeRunner(),
    )
    assert resumed.lifecycle == "imported"
    assert (directory / "control.json").read_bytes() == control_before

    # Zero output uses the genuine empty-tuple repository contract, not a fabricated report.
    zero_root = tmp_path / "zero"
    zero_root.mkdir()
    zero_directory, _zero_session = seed_canonical(monkeypatch, zero_root)
    _worker_support.write_control(zero_directory, "run")
    _worker_support.write_state(
        zero_directory, schema_version=2, lifecycle="completed", desired_count=0, completed_count=0
    )
    RecordingRepository.instances = []
    zero_status = worker_session.finalize_worker_session(
        worker_module.TranslationWorkerStage(), SESSION_ID, runner=_worker_support.FakeRunner()
    )
    assert zero_status.lifecycle == "imported"
    assert zero_status.desired_count == 0 and zero_status.completed_count == 0
    assert RecordingRepository.instances[0].calls == [()]
    zero_receipt = load_translation_controller_import_receipt(
        zero_directory / "import-receipt.json"
    )
    assert zero_receipt.output_count == 0
    assert zero_receipt.output_sha256 is None
    assert zero_receipt.import_report.requested_count == 0


def test_canonical_cleanup_requires_server_proof_and_retains_retry_authority(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Translation-import-only cleanup deletes nothing. Matching server proof permits the exact drop. A cleaned
    retry converges from the retained proof without finalize or upsert."""
    directory, session = seed_canonical(monkeypatch, tmp_path)
    _worker_support.write_control(directory, "run")
    _worker_support.write_state(
        directory, schema_version=2, lifecycle="completed", desired_count=1, completed_count=1
    )
    digest = _worker_support.write_output(directory, [_worker_support.entry("Name")])
    atomic_write_private_text(
        directory / "import-receipt.json",
        administrative_json(
            TranslationControllerImportReceipt(
                schema_version=1,
                session_id=SESSION_ID,
                revision=REVISION,
                output_count=1,
                output_sha256=digest,
                import_report=TranslationImportReport(
                    requested_count=1, inserted_count=1, updated_count=0, unchanged_count=0
                ),
            )
        ),
    )

    state_before = (directory / "state.json").read_bytes()
    output_before = (directory / "output.json").read_bytes()
    runner = _worker_support.FakeRunner()
    with pytest.raises(ValueError):
        worker_session.cleanup_worker_session(
            worker_module.TranslationWorkerStage(), SESSION_ID, runner=runner
        )
    assert not any("dropdb" in call for call in runner.calls)
    assert (directory / "state.json").read_bytes() == state_before
    assert (directory / "output.json").read_bytes() == output_before

    settings = load_administrative_dataset_settings()
    server_database = settings.database_name(SESSION_ID, worker=False)
    atomic_write_private_text(
        directory / "dataset-receipt.json",
        administrative_json(
            DatasetReceipt(
                schema_version=1,
                dataset_id=SESSION_ID,
                database_name=server_database,
                predecessor_id=SOURCE_ID,
                kind="returned",
                revision=REVISION,
                dump_sha256=SNAPSHOT_HASH,
                verification=sample_verification(),
            )
        ),
    )
    atomic_write_private_text(
        directory / "return.json",
        administrative_json(
            DatabaseSnapshot(
                schema_version=1,
                session_id=SESSION_ID,
                revision=REVISION,
                database_name=session.database_name,
                dump_sha256=SNAPSHOT_HASH,
                verification=sample_verification(),
            )
        ),
    )

    runner = _worker_support.FakeRunner()
    status = worker_session.cleanup_worker_session(
        worker_module.TranslationWorkerStage(), SESSION_ID, runner=runner
    )
    assert status.lifecycle == "cleaned"
    dropdb = [call for call in runner.calls if "dropdb" in call]
    assert len(dropdb) == 1
    assert "--if-exists" in dropdb[0]
    assert session.database_name in dropdb[0]
    assert not (directory / "output.json").exists()
    assert not (directory / "input.dump").exists()
    assert not (directory / "return.dump").exists()
    for retained in (
        "session.json",
        "policy.json",
        "control.json",
        "state.json",
        "import-receipt.json",
        "dataset-receipt.json",
        "return.json",
    ):
        assert (directory / retained).is_file()

    # A cleaned retry needs no finalize or upsert: the retained proof alone converges.
    monkeypatch.setattr(
        worker_module,
        "create_database_engine",
        lambda settings: pytest.fail("cleanup must not open a database engine"),
    )
    runner = _worker_support.FakeRunner()
    retried = worker_session.cleanup_worker_session(
        worker_module.TranslationWorkerStage(), SESSION_ID, runner=runner
    )
    assert retried.lifecycle == "cleaned"
    assert any("dropdb" in call for call in runner.calls)
    assert (directory / "state.json").is_file()
