"""Opt-in disposable-PostgreSQL round trip for the selected-dataset return and rotation owner.

One disposable initial database at the repository head is seeded with two canonical courses and one
completed official embedding chunk (a genuine label-free 1024-dim unit vector). Setup enrolls it.
One full worker input dump/restore round trip preserves verification and the vector. Three
successive returns drive real chain rotation. Only exact test-named databases and one exact scratch
directory are created and removed. Translation output is synthetic.
"""

from __future__ import annotations

import hashlib
import json
import math
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import Engine, select, text

from course_explorer.administration import (
    administrative_json,
    atomic_write_private_text,
    repository_root,
)
from course_explorer.config import (
    load_administrative_dataset_settings,
    load_database_settings,
    load_raw_database_settings,
    load_translation_settings,
)
from course_explorer.datasets import (
    DatasetReceipt,
    SelectedDatasetPointer,
    read_dataset_receipt,
    read_dataset_verification,
)
from course_explorer.db.models import (
    Base,
    Course,
    CourseEmbeddingChunk,
    CourseText,
    CourseVersion,
    DerivedCourseText,
    SourceSnapshot,
)
from course_explorer.db.session import create_database_engine, create_session_factory, session_scope
from course_explorer.enums import (
    CourseEmbeddingStatus,
    TeachingTextField,
    TeachingTextLanguage,
    TeachingTextOrigin,
    TranslationMethod,
)
from course_explorer.teaching_text.service import DerivedTranslationInput, teaching_text_sha256
from course_explorer_admin import commands, mechanics, worker_session
from course_explorer_admin.datasets import (
    admin_state_root,
    initialize_selected_dataset,
    retain_returned_dataset,
)
from course_explorer_admin.remote import (
    create_worker_dataset_session,
    export_worker_database,
    prepare_worker_database,
    worker_dataset_session_directory,
)
from course_explorer_admin.snapshots import database_dump_contains_embedding_data, dump_database
from course_explorer_admin.translation.controller import (
    TranslationControllerPolicy,
    TranslationControllerWorkerState,
)
from course_explorer_admin.translation.controller_worker import TranslationWorkerStage
from tests.config._support import (
    INFERENCE_CONTROLLER_KEYS,
    LOCAL_LIFECYCLE_KEYS,
    TRANSLATION_CONTROLLER_KEYS,
    TRANSLATION_KEYS,
)
from tests.inference._scheduling_support import reconcile, seed_courses

pytestmark = [
    pytest.mark.integration,
]

WORKER_PREFIX = "course_i542_worker_test"
SERVER_PREFIX = "course_i542_test"


def _digest(seed: str) -> str:
    return hashlib.sha256(seed.encode()).hexdigest()


def _compose_exec(runner: mechanics.ProcessRunner, *argv: str, stdin_path: Path | None = None):
    return runner.run(
        (*mechanics.compose_prefix(), "exec", "-T", "db", *argv),
        cwd=repository_root(),
        stdin_path=stdin_path,
        timeout=600,
    )


def _database_exists(runner: mechanics.ProcessRunner, name: str) -> bool:
    output = _compose_exec(
        runner,
        "psql",
        "--username",
        "course_explorer",
        "--dbname",
        "postgres",
        "--tuples-only",
        "--no-align",
        "--command",
        f"SELECT count(*) FROM pg_database WHERE datname = '{name}'",
    ).stdout
    return output.decode().strip() == "1"


def _drop(runner: mechanics.ProcessRunner, name: str) -> None:
    _compose_exec(runner, "dropdb", "--if-exists", "--username", "course_explorer", name)


def _seed_embedding(factory) -> None:
    with session_scope(factory) as session:
        version = session.scalar(select(CourseVersion).where(CourseVersion.code == "TEST.001"))
        assert version is not None
        snapshot = session.get(SourceSnapshot, version.source_snapshot_id)
        assert snapshot is not None
        embedding = [0.0] * 1024
        embedding[0] = 1.0
        session.add(
            CourseEmbeddingChunk(
                course_version_id=version.id,
                field=TeachingTextField.CONTENT,
                language=TeachingTextLanguage.FI,
                chunk_index=0,
                text_origin=TeachingTextOrigin.OFFICIAL,
                text="Sisalto TEST.001",
                representative_source_hash=snapshot.source_hash,
                effective_text_hash=_digest("effective"),
                source_text_hash=_digest("effective"),
                chunk_text_hash=_digest("chunk"),
                embedding_model="test-model",
                embedding_artifact_sha256="a" * 64,
                embedding_configuration_hash="b" * 64,
                status=CourseEmbeddingStatus.COMPLETED,
                embedding=embedding,
            )
        )


def test_full_snapshot_return_and_rotation_preserve_database_state(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Setup, one full snapshot round trip, vector/verification preservation, and real rotation."""
    runner = mechanics.SubprocessRunner()
    repository = repository_root()
    # The in-process worker uses the installed product code. Isolate its real Git-metadata
    # preflight from user work in the development checkout, without copying any source.
    worker_checkout = tmp_path / "prepared-worker"
    worker_checkout.mkdir()
    runner.run(("git", "init", "--initial-branch=prepared-test"), cwd=worker_checkout)
    runner.run(
        (
            "git",
            "-c",
            "user.name=Course Explorer Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "--allow-empty",
            "-m",
            "Prepared checkout metadata",
        ),
        cwd=worker_checkout,
    )

    class DatasetRunner(mechanics.SubprocessRunner):
        """Use real isolated Git metadata. Execute all data/code operations in their actual cwd."""

        def run(self, argv, *, cwd=None, **options):
            if argv[0] == "git" and cwd == repository:
                cwd = worker_checkout
            return super().run(argv, cwd=cwd, **options)

    runner = DatasetRunner()
    admin_state = f"data/admin-tests/{uuid.uuid4().hex}"
    initial = f"course_i542_test_initial_{uuid.uuid4().hex[:8]}"
    monkeypatch.setenv("SELECTED_DATASET_ENABLED", "0")
    monkeypatch.setenv("POSTGRES_DB", initial)
    monkeypatch.setenv("ADMIN_STATE_ROOT", admin_state)
    monkeypatch.setenv("ADMIN_DATASET_DATABASE_PREFIX", SERVER_PREFIX)
    monkeypatch.setenv("ADMIN_WORKER_DATABASE_PREFIX", WORKER_PREFIX)
    monkeypatch.setenv("ADMIN_DATABASE_OPERATION_TIMEOUT_SECONDS", "3600")
    # Point the stage roots at unique scratch directories under the same test admin state so no
    # real state can interfere.
    for keys in (
        LOCAL_LIFECYCLE_KEYS,
        TRANSLATION_CONTROLLER_KEYS,
        INFERENCE_CONTROLLER_KEYS,
    ):
        for key, value in keys.items():
            monkeypatch.setenv(key, value)
    # Translation policy/provenance loads are explicit and deterministic for the canonical worker.
    for key, value in TRANSLATION_KEYS.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("TRANSLATION_CONTROLLER_WORKER_PROJECT_ROOT", str(worker_checkout))
    monkeypatch.setenv("INGESTION_CONTROLLER_STATE_ROOT", f"{admin_state}/ingestion")
    monkeypatch.setenv("EMBEDDING_CONTROLLER_STATE_ROOT", f"{admin_state}/embedding")
    monkeypatch.setenv("TRANSLATION_CONTROLLER_STATE_ROOT", f"{admin_state}/translation")
    admin = load_administrative_dataset_settings()
    root = admin_state_root(admin)
    sessions: list[str] = []
    try:
        _compose_exec(
            runner, "createdb", "--username", "course_explorer", "--template", "template0", initial
        )
        runner.run(
            ("uv", "run", "--offline", "--no-sync", "python", "-m", "alembic", "upgrade", "head"),
            cwd=repository,
            env={"SELECTED_DATASET_ENABLED": "0", "POSTGRES_DB": initial},
            timeout=600,
        )
        settings = load_raw_database_settings().model_copy(update={"postgres_db": initial})
        engine = create_database_engine(settings)
        factory = create_session_factory(engine)
        seed_courses(
            factory, [("dataset-target", "TEST.001", True), ("dataset-source", "TEST.002", False)]
        )
        _seed_embedding(factory)
        with session_scope(factory) as session:
            assert (
                session.scalar(select(Course).where(Course.group_id == "dataset-target"))
                is not None
            )
            assert session.scalar(select(CourseEmbeddingChunk)) is not None
        # No local engine may hold a connection to the initial database while rotation drops it.
        engine.dispose()

        receipt0 = initialize_selected_dataset(runner=runner)
        assert receipt0.database_name == initial

        # The explicit exclusion path produces a dump without embedding table data.
        excluded = root / "excluded.dump"
        excluded.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        dump_database(
            runner=runner,
            root=repository,
            settings=settings,
            destination=excluded,
            include_embeddings=False,
        )
        listing = _compose_exec(runner, "pg_restore", "--list", stdin_path=excluded).stdout
        assert not database_dump_contains_embedding_data(listing)

        # The selected dataset resolves through the pointer after setup.
        monkeypatch.setenv("SELECTED_DATASET_ENABLED", "1")
        assert load_database_settings().postgres_db == initial

        previous_id, previous_database = receipt0.dataset_id, receipt0.database_name

        # First session: the canonical translation worker writes genuine S1 output, finalizes it
        # through the sole writer, returns the whole database with its vectors, and drops only its
        # own worker database after the verified server receipt proves the return.
        translation_id = uuid.uuid4().hex
        sessions.append(translation_id)
        translation_session = create_worker_dataset_session(
            "translation", session_id=translation_id, runner=runner
        )
        assert translation_session.input_snapshot.database_name == previous_database
        translation_directory = worker_dataset_session_directory(translation_id)
        atomic_write_private_text(
            translation_directory / "policy.json",
            administrative_json(
                TranslationControllerPolicy(
                    schema_version=2,
                    session_id=translation_id,
                    revision=translation_session.revision,
                    translation_model=load_translation_settings().provenance_model,
                )
            ),
        )
        prepared_status = worker_session.prepare_worker_session(
            TranslationWorkerStage(), translation_session, runner=runner
        )
        assert prepared_status.lifecycle == "prepared"
        assert prepared_status.desired_count == 2

        generated_at = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)
        synthetic = DerivedTranslationInput(
            sisu_course_unit_id="sisu-dataset-target",
            field=TeachingTextField.CONTENT,
            language=TeachingTextLanguage.EN,
            source_language=TeachingTextLanguage.FI,
            source_text="Sisalto TEST.001",
            text="Synthetic translated content",
            translation_method=TranslationMethod.MODEL,
            translation_model=load_translation_settings().provenance_model,
            generated_at=generated_at,
        )
        atomic_write_private_text(
            translation_directory / "output.json",
            json.dumps([synthetic.model_dump(mode="json")], ensure_ascii=False) + "\n",
        )
        atomic_write_private_text(
            translation_directory / "state.json",
            administrative_json(
                TranslationControllerWorkerState(
                    schema_version=2,
                    session_id=translation_id,
                    revision=translation_session.revision,
                    lifecycle="completed",
                    desired_count=2,
                    completed_count=1,
                    started_at=generated_at,
                    active_seconds=0.0,
                )
            ),
        )
        finalized = worker_session.finalize_worker_session(
            TranslationWorkerStage(), translation_id, runner=runner
        )
        assert finalized.lifecycle == "imported"
        assert finalized.completed_count == 1

        translation_snapshot = export_worker_database(translation_session, runner=runner)
        translation_return_dump = root / "sessions" / translation_id / "return.dump"
        translation_receipt = retain_returned_dataset(
            translation_session, translation_snapshot, translation_return_dump, runner=runner
        )
        assert translation_receipt.predecessor_id == previous_id
        assert read_dataset_receipt(root, translation_id) == translation_receipt
        atomic_write_private_text(
            translation_directory / "dataset-receipt.json",
            administrative_json(translation_receipt),
        )
        cleaned = worker_session.cleanup_worker_session(
            TranslationWorkerStage(), translation_id, runner=runner
        )
        assert cleaned.lifecycle == "cleaned"
        assert not _database_exists(runner, translation_session.database_name)

        returned_settings = load_raw_database_settings().model_copy(
            update={"postgres_db": translation_receipt.database_name}
        )
        returned_engine = create_database_engine(returned_settings)
        try:
            with session_scope(create_session_factory(returned_engine)) as returned:
                derived = returned.scalar(
                    select(DerivedCourseText)
                    .join(CourseVersion, CourseVersion.id == DerivedCourseText.course_version_id)
                    .where(
                        CourseVersion.sisu_course_unit_id == "sisu-dataset-target",
                        DerivedCourseText.field == TeachingTextField.CONTENT,
                        DerivedCourseText.language == TeachingTextLanguage.EN,
                    )
                )
                assert derived is not None
                assert derived.text == "Synthetic translated content"
                assert derived.source_text_hash == teaching_text_sha256("Sisalto TEST.001")
                assert derived.translation_method is TranslationMethod.MODEL
                assert derived.translation_model == load_translation_settings().provenance_model
                official = returned.scalar(
                    select(CourseText)
                    .join(CourseVersion, CourseVersion.id == CourseText.course_version_id)
                    .where(CourseVersion.code == "TEST.001")
                )
                assert official is not None
                assert official.content_fi == "Sisalto TEST.001"
                chunk = returned.scalar(select(CourseEmbeddingChunk))
                assert chunk is not None
                assert chunk.embedding is not None
                assert list(chunk.embedding) == [1.0] + [0.0] * 1023
                assert math.isclose(
                    sum(value * value for value in chunk.embedding), 1.0, rel_tol=1e-6
                )
        finally:
            returned_engine.dispose()
        previous_id, previous_database = (
            translation_receipt.dataset_id,
            translation_receipt.database_name,
        )

        # Two further inference returns drive the retained-dump rotation.
        for _ in range(2):
            session_id = uuid.uuid4().hex
            sessions.append(session_id)
            session = create_worker_dataset_session(
                "inference", session_id=session_id, runner=runner
            )
            assert session.input_snapshot.database_name == previous_database
            prepared = prepare_worker_database(session, runner=runner)
            assert prepared == session.input_snapshot.verification
            snapshot = export_worker_database(session, runner=runner)
            return_dump = root / "sessions" / session_id / "return.dump"
            receipt = retain_returned_dataset(session, snapshot, return_dump, runner=runner)
            assert receipt.predecessor_id == previous_id
            returned_settings = load_raw_database_settings().model_copy(
                update={"postgres_db": receipt.database_name}
            )
            returned_engine = create_database_engine(returned_settings)
            try:
                with session_scope(create_session_factory(returned_engine)) as returned:
                    chunk = returned.scalar(select(CourseEmbeddingChunk))
                    assert chunk is not None
                    assert chunk.embedding is not None
                    assert list(chunk.embedding) == [1.0] + [0.0] * 1023
                    assert math.isclose(
                        sum(value * value for value in chunk.embedding), 1.0, rel_tol=1e-6
                    )
            finally:
                returned_engine.dispose()
            assert read_dataset_receipt(root, session_id) == receipt
            previous_id, previous_database = receipt.dataset_id, receipt.database_name

        # After three returns only the last two dumps exist. The initial DB rotated out.
        assert not _database_exists(runner, initial)
        assert not _database_exists(runner, f"{SERVER_PREFIX}_{sessions[0]}")
        assert _database_exists(runner, f"{SERVER_PREFIX}_{sessions[2]}")
        assert _database_exists(runner, f"{WORKER_PREFIX}_{sessions[2]}")
    finally:
        names = [
            initial,
            *(f"{SERVER_PREFIX}_{session}" for session in sessions),
            *(f"{WORKER_PREFIX}_{session}" for session in sessions),
        ]
        errors: list[Exception] = []
        for name in names:
            try:
                _drop(runner, name)
            except Exception as exc:
                errors.append(exc)
        if root.exists():
            try:
                shutil.rmtree(root)
            except Exception as exc:
                errors.append(exc)
        if errors:
            raise ExceptionGroup("dataset test cleanup failed", errors)


def _sql_projections(engine: Engine) -> dict[str, tuple[int, str]]:
    """Return one (count, digest) SQL projection per application table."""
    projections: dict[str, tuple[int, str]] = {}
    with engine.connect() as connection:
        for table in Base.metadata.sorted_tables:
            if table.name == "inference_target_failures":
                continue
            rows = (
                connection.execute(
                    text(
                        "SELECT encode(sha256(convert_to(to_jsonb(t)::text, 'UTF8')), 'hex') "
                        f'FROM "{table.name}" AS t'
                    )
                )
                .scalars()
                .all()
            )
            ordered = sorted(rows)
            concatenated = "".join(ordered).encode("utf-8")
            projections[table.name] = (len(rows), hashlib.sha256(concatenated).hexdigest())
    return projections


def test_selected_migration_preserves_work_and_frozen_receipt(
    database: tuple[Engine, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The explicit migration owner applies the current head without touching other state."""
    from course_explorer_admin.lifecycle import InferenceProgress, LifecycleState

    engine, factory = database
    runner = mechanics.SubprocessRunner()
    admin_state = f"data/admin-tests/{uuid.uuid4().hex}"
    dataset_id = "0" * 32
    monkeypatch.setenv("SELECTED_DATASET_ENABLED", "0")
    monkeypatch.setenv("POSTGRES_DB", "course_explorer_test")
    monkeypatch.setenv("ADMIN_STATE_ROOT", admin_state)
    monkeypatch.setenv("ADMIN_DATABASE_OPERATION_TIMEOUT_SECONDS", "600")
    for keys in (LOCAL_LIFECYCLE_KEYS, TRANSLATION_CONTROLLER_KEYS, INFERENCE_CONTROLLER_KEYS):
        for key, value in keys.items():
            monkeypatch.setenv(key, value)
    monkeypatch.setenv("INGESTION_CONTROLLER_STATE_ROOT", f"{admin_state}/ingestion")
    monkeypatch.setenv("EMBEDDING_CONTROLLER_STATE_ROOT", f"{admin_state}/embedding")
    monkeypatch.setenv("TRANSLATION_CONTROLLER_STATE_ROOT", f"{admin_state}/translation")
    monkeypatch.setenv("INFERENCE_CONTROLLER_STATE_ROOT", f"{admin_state}/inference")
    settings = load_administrative_dataset_settings()
    root = admin_state_root(settings)
    raw = load_raw_database_settings().model_copy(update={"postgres_db": "course_explorer_test"})
    try:
        # The immutable snapshot fact is the genuine head verification before any migration.
        verification = read_dataset_verification(raw)
        seed_courses(factory, [("dataset-target", "TEST.001", True)])
        markers = reconcile(factory)
        assert any(marker.group_id == "dataset-target" for marker in markers)

        directory = root / "datasets" / dataset_id
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        atomic_write_private_text(
            directory / "receipt.json",
            administrative_json(
                DatasetReceipt(
                    schema_version=1,
                    dataset_id=dataset_id,
                    database_name="course_explorer_test",
                    predecessor_id=None,
                    kind="initial",
                    revision="a" * 40,
                    dump_sha256=None,
                    verification=verification,
                )
            ),
        )
        atomic_write_private_text(
            root / "selected-dataset.json",
            administrative_json(SelectedDatasetPointer(schema_version=1, dataset_id=dataset_id)),
        )
        dump = directory / "database.dump"
        dump.write_bytes(b"frozen-dump-sentinel")
        receipt_bytes = (directory / "receipt.json").read_bytes()
        pointer_bytes = (root / "selected-dataset.json").read_bytes()
        dump_bytes = dump.read_bytes()

        projections_before = _sql_projections(engine)

        # A genuinely non-idle stage state refuses before any apply.
        inference_root = Path(f"{admin_state}/inference/current")
        inference_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        atomic_write_private_text(
            inference_root / "state.json",
            administrative_json(
                LifecycleState(
                    session_id=dataset_id,
                    lifecycle="running",
                    requested_action="run",
                    progress=InferenceProgress(kind="inference"),
                    work_complete=False,
                    active_seconds=0.0,
                )
            ),
        )
        with pytest.raises(ValueError):
            commands.run_administrative_migration(runner=runner)
        (inference_root / "state.json").unlink()

        # The explicit owner applies the actual head and returns a fresh owning verification.
        applied = commands.run_administrative_migration(runner=runner)
        assert applied.alembic_revision == verification.alembic_revision
        assert _sql_projections(engine) == projections_before
        # The frozen receipt, pointer and dump bytes are identical.
        assert (directory / "receipt.json").read_bytes() == receipt_bytes
        assert (root / "selected-dataset.json").read_bytes() == pointer_bytes
        assert dump.read_bytes() == dump_bytes
        assert read_dataset_receipt(root, dataset_id).database_name == "course_explorer_test"
        # A fresh snapshot capture uses the migrated head.
        snapshot_dump = root / "capture.dump"
        dump_database(
            runner=runner,
            root=repository_root(),
            settings=raw,
            destination=snapshot_dump,
            include_embeddings=True,
        )
        assert snapshot_dump.is_file()
    finally:
        # Ensure the disposable test database is left at the current repository head.
        runner.run(
            ("uv", "run", "--offline", "--no-sync", "python", "-m", "alembic", "upgrade", "head"),
            cwd=repository_root(),
            env={
                "SELECTED_DATASET_ENABLED": "0",
                "POSTGRES_DB": "course_explorer_test",
                "ADMIN_STATE_ROOT": admin_state,
            },
            timeout=600,
        )
        if root.exists():
            shutil.rmtree(root)
