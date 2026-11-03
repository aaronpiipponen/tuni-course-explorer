"""Opt-in disposable-PostgreSQL proofs for the dataset roles, copies, promotion and cleanup owners.

One disposable initial database at the repository head is seeded with two canonical courses and one
completed official embedding chunk (a genuine label-free 1024-dim unit vector). Setup enrolls it.
One full worker input dump/restore round trip preserves verification and the vector. Three
successive returns drive real chain rotation. Promotion copies and builds a selected candidate at
the real process boundary, and a failed promotion restores the previous selection. This module also
proves that a local stage writes Working alone and that a stale Working head refuses. The cleanup
proof creates three uniquely named
disposable databases under synthetic chain receipts, deletes one non-selected dataset through the
public cleanup delegate, and checks the absence of its database and dump beside the preserved
selection. Only exact test-named databases and exact scratch directories are created and removed.
Translation output is synthetic.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import socket
import subprocess
import uuid
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import httpx
import pytest
from alembic.config import Config as AlembicConfig
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, select, text

from course_explorer import administration
from course_explorer.administration import (
    administrative_json,
    atomic_write_private_text,
    sha256_file,
    utc_now,
)
from course_explorer.config import (
    load_administrative_dataset_settings,
    load_database_settings,
    load_local_lifecycle_settings,
    load_raw_database_settings,
    load_translation_settings,
)
from course_explorer.datasets import (
    DatabaseSchemaMismatchError,
    DatasetPointer,
    DatasetReceipt,
    read_dataset_receipt,
    read_dataset_verification,
    resolve_dataset_role,
    resolve_selected_dataset,
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
from course_explorer.embeddings import commands as embedding_commands
from course_explorer.enums import (
    CourseEmbeddingStatus,
    TeachingTextField,
    TeachingTextLanguage,
    TeachingTextOrigin,
    TranslationMethod,
)
from course_explorer.serving_artifacts import (
    CATALOGUE_FILE,
    ServingArtifacts,
    serving_artifact_root,
    serving_database_root,
    serving_key,
)
from course_explorer.serving_build import build_serving_artifacts, dataset_settings
from course_explorer.teaching_text.service import DerivedTranslationInput, teaching_text_sha256
from course_explorer_admin import (
    commands,
    lifecycle,
    mechanics,
    provisioning_worker,
    worker_session,
)
from course_explorer_admin import datasets as datasets_module
from course_explorer_admin.datasets import (
    admin_state_root,
    copy_to_working,
    initialize_selected_dataset,
    require_droppable_database,
    retain_returned_dataset,
)
from course_explorer_admin.lifecycle import (
    EmbeddingOptions,
    InferenceProgress,
    LifecycleContext,
    LifecycleSession,
    LifecycleState,
)
from course_explorer_admin.local_stages import EmbeddingStage, require_working_database_schema
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
from course_explorer_web.dataset import resolve_serving_dataset
from tests.admin._rebuild_support import (
    _ADMIN_UNIT,
    _OWNED_PROCESS,
    _UNIT,
    _WEB_HOST,
    _WEB_PORT,
    _WEB_WORKERS,
    _RebuildProcessBoundary,
    bind_promotion_http,
)
from tests.config._support import (
    INFERENCE_CONTROLLER_KEYS,
    LOCAL_LIFECYCLE_KEYS,
    TRANSLATION_CONTROLLER_KEYS,
    TRANSLATION_KEYS,
)
from tests.datasets._support import INITIAL_ID, sample_verification
from tests.embeddings._http_support import embedding_response, vector
from tests.inference._scheduling_support import reconcile, seed_courses

pytestmark = [
    pytest.mark.integration,
]


WORKER_PREFIX = "course_tests_worker"
SERVER_PREFIX = "course_tests"


@pytest.fixture()
def isolated_database_cluster(monkeypatch: pytest.MonkeyPatch) -> None:
    """Run the Compose maintenance boundary on its own extension-enabled project and volume."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    project = f"tce-tests-{uuid.uuid4().hex[:12]}"
    monkeypatch.setenv("COMPOSE_PROJECT_NAME", project)
    monkeypatch.setenv("POSTGRES_PORT", str(port))
    monkeypatch.setenv("POSTGRES_DB", f"{SERVER_PREFIX}_bootstrap")
    runner = mechanics.SubprocessRunner()
    root = administration.repository_root()
    image = provisioning_worker._db_image_name(runner, root)
    if not provisioning_worker._db_image_present(runner, root, image):
        raise RuntimeError(
            "the prepared database image is missing; prepare it with "
            "`uv run python -m course_explorer_admin.compose --non-interactive -- build db`"
        )
    prefix = mechanics.compose_prefix(non_interactive=True, interpreter=True)
    try:
        runner.run(
            (*prefix, "up", "-d", "--wait", "--no-build", "--pull", "never", "db"),
            cwd=root,
            timeout=600,
        )
        yield
    finally:
        runner.run(
            (*prefix, "down", "-v", "--remove-orphans"),
            cwd=root,
            timeout=600,
        )


def _digest(seed: str) -> str:
    return hashlib.sha256(seed.encode()).hexdigest()


def _compose_exec(runner: mechanics.ProcessRunner, *argv: str, stdin_path: Path | None = None):
    return runner.run(
        (*mechanics.compose_prefix(interpreter=True), "exec", "-T", "db", *argv),
        cwd=administration.repository_root(),
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
        embedding = vector(1.0)
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
    isolated_database_cluster: None,
) -> None:
    """Setup, one full snapshot round trip, vector/verification preservation, and real rotation."""
    runner = mechanics.SubprocessRunner()
    repository = administration.repository_root()
    worker_checkout = tmp_path / "prepared-worker"
    # The in-process worker uses this scratch worker root.
    worker_checkout.mkdir()

    admin_state = f"data/admin-tests/{uuid.uuid4().hex}"
    initial = f"course_tests_initial_{uuid.uuid4().hex[:8]}"
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
    working_database: str | None = None
    try:
        _compose_exec(
            runner, "createdb", "--username", "course_explorer", "--template", "template0", initial
        )
        runner.run(
            ("uv", "run", "--offline", "--no-sync", "python", "-m", "alembic", "upgrade", "head"),
            cwd=repository,
            env={"POSTGRES_DB": initial},
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

        # The Selected dataset resolves through the pointer, and a real copy becomes Working.
        assert load_database_settings(role="selected").postgres_db == initial
        working0 = copy_to_working(receipt0.dataset_id, runner=runner)
        working_database = working0.database_name
        assert working0.kind == "copied"
        assert working0.predecessor_id == receipt0.dataset_id
        assert resolve_dataset_role(root, "working").dataset_id == working0.dataset_id
        previous_id, previous_database = working0.dataset_id, working0.database_name

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

        # Selected keeps its initial database while Working keeps its current dataset and
        # predecessor. The first Working copy and the first return are older ancestors.
        assert _database_exists(runner, initial)
        assert resolve_selected_dataset(root).dataset_id == receipt0.dataset_id
        assert working_database is not None
        assert not _database_exists(runner, working_database)
        assert not _database_exists(runner, f"{SERVER_PREFIX}_{sessions[0]}")
        assert _database_exists(runner, f"{SERVER_PREFIX}_{sessions[1]}")
        assert _database_exists(runner, f"{SERVER_PREFIX}_{sessions[2]}")
        assert _database_exists(runner, f"{WORKER_PREFIX}_{sessions[2]}")
        assert resolve_dataset_role(root, "working").dataset_id == sessions[2]
    finally:
        names = [
            initial,
            *((working_database,) if working_database is not None else ()),
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


def test_copy_to_working_preserves_the_served_source(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    isolated_database_cluster: None,
) -> None:
    """One verified copy runs while the served source holds an open connection and changes nothing."""
    runner = mechanics.SubprocessRunner()
    repository = administration.repository_root()
    admin_state = f"data/admin-tests/{uuid.uuid4().hex}"
    source_database = f"course_copy_test_{uuid.uuid4().hex[:8]}"
    prefix = f"course_copy_test_{uuid.uuid4().hex[:6]}"
    monkeypatch.setenv("POSTGRES_DB", source_database)
    monkeypatch.setenv("ADMIN_STATE_ROOT", admin_state)
    monkeypatch.setenv("ADMIN_DATASET_DATABASE_PREFIX", prefix)
    monkeypatch.setenv("ADMIN_WORKER_DATABASE_PREFIX", f"{prefix}_worker")
    monkeypatch.setenv("ADMIN_DATABASE_OPERATION_TIMEOUT_SECONDS", "3600")
    for keys in (LOCAL_LIFECYCLE_KEYS, TRANSLATION_CONTROLLER_KEYS, INFERENCE_CONTROLLER_KEYS):
        for key, value in keys.items():
            monkeypatch.setenv(key, value)
    monkeypatch.setenv("INGESTION_CONTROLLER_STATE_ROOT", f"{admin_state}/ingestion")
    monkeypatch.setenv("EMBEDDING_CONTROLLER_STATE_ROOT", f"{admin_state}/embedding")
    monkeypatch.setenv("TRANSLATION_CONTROLLER_STATE_ROOT", f"{admin_state}/translation")
    monkeypatch.setenv("INFERENCE_CONTROLLER_STATE_ROOT", f"{admin_state}/inference")
    admin = load_administrative_dataset_settings()
    root = admin_state_root(admin)
    working_database: str | None = None
    engine: Engine | None = None
    held = None
    try:
        _compose_exec(
            runner,
            "createdb",
            "--username",
            "course_explorer",
            "--template",
            "template0",
            source_database,
        )
        runner.run(
            ("uv", "run", "--offline", "--no-sync", "python", "-m", "alembic", "upgrade", "head"),
            cwd=repository,
            env={"POSTGRES_DB": source_database},
            timeout=600,
        )
        settings = load_raw_database_settings().model_copy(update={"postgres_db": source_database})
        engine = create_database_engine(settings)
        factory = create_session_factory(engine)
        seed_courses(factory, [("copy-target", "TEST.001", True)])
        _seed_embedding(factory)
        source_verification = read_dataset_verification(settings)
        # Keep one explicit source connection open across the copy: a template copy would fail.
        held = engine.connect()
        assert held.execute(text("SELECT count(*) FROM courses")).scalar_one() == 1

        selected = initialize_selected_dataset(runner=runner)
        selected_pointer = (root / "selected-dataset.json").read_bytes()
        selected_artifact = serving_database_root(root, source_database)
        selected_artifact.mkdir(mode=0o700, parents=True)
        artifact_file = selected_artifact / "keep.txt"
        artifact_file.write_text("selected-artifact", encoding="utf-8")

        working = copy_to_working(selected.dataset_id, runner=runner)
        working_database = working.database_name

        assert working.kind == "copied"
        assert working.dataset_id != selected.dataset_id
        assert working.database_name != selected.database_name
        assert working.predecessor_id == selected.dataset_id
        assert working.dump_sha256 == sha256_file(
            datasets_module.retained_dump_path(root, working.dataset_id)
        )
        assert (root / "selected-dataset.json").read_bytes() == selected_pointer
        assert resolve_dataset_role(root, "working").dataset_id == working.dataset_id
        assert resolve_selected_dataset(root).dataset_id == selected.dataset_id
        assert _database_exists(runner, source_database)
        assert _database_exists(runner, working_database)
        assert artifact_file.read_text(encoding="utf-8") == "selected-artifact"
        assert not serving_database_root(root, working_database).exists()
        assert {path.name for path in (root / "datasets").iterdir()} == {
            selected.dataset_id,
            working.dataset_id,
        }

        working_settings = load_raw_database_settings().model_copy(
            update={"postgres_db": working_database}
        )
        working_engine = create_database_engine(working_settings)
        try:
            working_factory = create_session_factory(working_engine)
            with session_scope(working_factory) as copied:
                copy_chunk = copied.scalar(select(CourseEmbeddingChunk))
                assert copy_chunk is not None
                assert list(copy_chunk.embedding) == [1.0] + [0.0] * 1023
                assert copied.scalar(select(Course).where(Course.group_id == "copy-target"))
            assert read_dataset_verification(working_settings) == working.verification
        finally:
            working_engine.dispose()
        assert source_verification.catalogue == working.verification.catalogue
        assert source_verification.embeddings.total_chunk_count == 1
        assert working.verification.embeddings.total_chunk_count == 1
    finally:
        if held is not None:
            held.close()
        if engine is not None:
            engine.dispose()
        errors: list[Exception] = []
        for name in (source_database, working_database):
            if name is None:
                continue
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
            raise ExceptionGroup("copy test cleanup failed", errors)


_MANUAL_CLEANUP_TARGETS = ("initial", "returned")


@pytest.mark.parametrize("target_kind", _MANUAL_CLEANUP_TARGETS)
def test_manual_dataset_cleanup_drops_one_retained_database(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    target_kind: str,
    isolated_database_cluster: None,
) -> None:
    """One non-selected dataset is dropped through the public cleanup delegate, keeping its history.

    The chain receipts, the pointer and the dumps are synthetic and live under a temporary state root,
    while the three databases are real, uniquely named and disposable. Every created name is checked
    before it is created, and only those exact names are dropped again.
    """
    prefix = f"cleanup_test_{uuid.uuid4().hex[:6]}"
    initial_database = f"{prefix}_initial"
    predecessor_id = "b" * 32
    selected_id = "c" * 32
    predecessor_database = f"{prefix}_{predecessor_id}"
    selected_database = f"{prefix}_{selected_id}"
    created_names = (initial_database, predecessor_database, selected_database)
    assert all("_test" in name for name in created_names)
    assert all(len(name.encode("ascii")) <= 63 for name in created_names)
    for name in created_names:
        require_droppable_database(name)

    admin_state = f"data/admin-tests/{uuid.uuid4().hex}"
    # The initial retained database is deletable because the site serves the protected
    # disposable database.
    monkeypatch.setenv("POSTGRES_DB", "course_explorer_test")
    monkeypatch.setenv("ADMIN_STATE_ROOT", admin_state)
    monkeypatch.setenv("ADMIN_DATASET_DATABASE_PREFIX", prefix)
    monkeypatch.setenv("ADMIN_WORKER_DATABASE_PREFIX", f"{prefix}_worker")
    monkeypatch.setenv("ADMIN_DATABASE_OPERATION_TIMEOUT_SECONDS", "600")
    runner = mechanics.SubprocessRunner()
    settings = load_administrative_dataset_settings()
    root = admin_state_root(settings)
    assert root == tmp_path / admin_state

    def _receipt(
        dataset_id: str,
        database_name: str,
        *,
        kind: Literal["initial", "returned"],
        predecessor: str | None,
        dump_sha256: str | None,
    ) -> DatasetReceipt:
        return DatasetReceipt(
            schema_version=1,
            dataset_id=dataset_id,
            database_name=database_name,
            predecessor_id=predecessor,
            kind=kind,
            dump_sha256=dump_sha256,
            verification=sample_verification(),
        )

    chain = (
        _receipt(
            selected_id,
            selected_database,
            kind="returned",
            predecessor=predecessor_id,
            dump_sha256="a" * 64,
        ),
        _receipt(
            predecessor_id,
            predecessor_database,
            kind="returned",
            predecessor=INITIAL_ID,
            dump_sha256="b" * 64,
        ),
        _receipt(INITIAL_ID, initial_database, kind="initial", predecessor=None, dump_sha256=None),
    )
    receipt_bytes: dict[Path, bytes] = {}
    for receipt in chain:
        directory = root / "datasets" / receipt.dataset_id
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        atomic_write_private_text(directory / "receipt.json", administrative_json(receipt))
        receipt_bytes[directory / "receipt.json"] = (directory / "receipt.json").read_bytes()
    dumps: dict[str, Path] = {}
    for receipt in chain[:2]:
        dump = root / "datasets" / receipt.dataset_id / "database.dump"
        dump.write_bytes(f"dump-{receipt.dataset_id}".encode())
        dumps[receipt.dataset_id] = dump
    orphan_dump = root / "datasets" / ("f" * 32) / "database.dump"
    orphan_dump.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    orphan_dump.write_bytes(b"orphan-capture")
    atomic_write_private_text(
        root / "selected-dataset.json",
        administrative_json(DatasetPointer(schema_version=1, dataset_id=selected_id)),
    )
    pointer_bytes = (root / "selected-dataset.json").read_bytes()
    artifacts: dict[str, Path] = {}
    for name in created_names:
        namespace = serving_database_root(root, name)
        namespace.mkdir(mode=0o700, parents=True)
        (namespace / "keep.txt").write_text(f"artifact-{name}", encoding="utf-8")
        artifacts[name] = namespace

    def _root_files() -> list[str]:
        return sorted(path.relative_to(root).as_posix() for path in root.rglob("*"))

    try:
        for name in created_names:
            _compose_exec(
                runner, "createdb", "--username", "course_explorer", "--template", "template0", name
            )
            assert _database_exists(runner, name)

        # The inventory follows the receipts, reports the chain order and creates nothing.
        files_before_listing = _root_files()
        inventory = commands.run_administrative_dataset_list(runner=runner)
        assert _root_files() == files_before_listing
        assert [entry.dataset_id for entry in inventory.datasets] == [
            selected_id,
            predecessor_id,
            INITIAL_ID,
        ]
        assert [entry.kind for entry in inventory.datasets] == ["returned", "returned", "initial"]
        assert [entry.selected for entry in inventory.datasets] == [True, False, False]
        assert [entry.database_name for entry in inventory.datasets] == [
            selected_database,
            predecessor_database,
            initial_database,
        ]
        assert [entry.dump_path for entry in inventory.datasets] == [
            f"{admin_state}/datasets/{selected_id}/database.dump",
            f"{admin_state}/datasets/{predecessor_id}/database.dump",
            None,
        ]
        assert [entry.database_presence for entry in inventory.datasets] == [
            "present",
            "present",
            "present",
        ]
        assert inventory.mode == "enrolled"
        assert orphan_dump.read_bytes() == b"orphan-capture"

        target_id = INITIAL_ID if target_kind == "initial" else predecessor_id
        target_database = initial_database if target_kind == "initial" else predecessor_database
        report = commands.run_administrative_dataset_delete(target_id, runner=runner)
        assert report.dataset_id == target_id
        assert report.database_name == target_database
        assert not _database_exists(runner, target_database)
        assert _database_exists(runner, selected_database)
        if target_kind == "returned":
            assert not dumps[target_id].exists()
        assert not artifacts[target_database].exists()
        assert artifacts[selected_database].is_dir()
        other_database = predecessor_database if target_kind == "initial" else initial_database
        assert artifacts[other_database].is_dir()
        assert dumps[selected_id].read_bytes() == f"dump-{selected_id}".encode()
        assert (root / "selected-dataset.json").read_bytes() == pointer_bytes
        for path, payload in receipt_bytes.items():
            assert path.read_bytes() == payload
        assert resolve_selected_dataset(root).dataset_id == selected_id
        assert read_dataset_receipt(root, INITIAL_ID).database_name == initial_database
        assert orphan_dump.read_bytes() == b"orphan-capture"

        # A repeated explicit deletion reports the same target over the already absent resources.
        assert commands.run_administrative_dataset_delete(target_id, runner=runner) == report
        assert not _database_exists(runner, target_database)
        assert dumps[selected_id].read_bytes() == f"dump-{selected_id}".encode()

        # The deleted dataset has a receipt and no database or dump, so the listing omits it. The
        # other non-selected dataset has its database, so the listing includes it.
        remaining = commands.run_administrative_dataset_list(runner=runner)
        other_id = predecessor_id if target_kind == "initial" else INITIAL_ID
        assert [entry.dataset_id for entry in remaining.datasets] == [selected_id, other_id]
    finally:
        errors: list[Exception] = []
        for name in created_names:
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
            raise ExceptionGroup("manual dataset cleanup test cleanup failed", errors)


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


def selected_row_content(engine: Engine) -> dict[str, list[str]]:
    """Return one ordered JSONB row projection per application table.

    The projection is the whole stored row as JSON text, ordered by that text, so a comparison
    detects changed row content. The SQL ordering normalizes row order. Callers compare the complete
    mapping and separately require the catalogue tables to be nonempty.
    """
    content: dict[str, list[str]] = {}
    with engine.connect() as connection:
        for table in Base.metadata.sorted_tables:
            rows = (
                connection.execute(
                    text(f'SELECT to_jsonb(t)::text FROM "{table.name}" AS t ORDER BY 1')
                )
                .scalars()
                .all()
            )
            content[table.name] = list(rows)
    return content


def selected_artifact_state(
    state_root: Path, database_name: str
) -> tuple[tuple[str, ...], tuple[tuple[str, str], ...]]:
    """Return one serving namespace's relative names and each family's current link target."""
    namespace = serving_database_root(state_root, database_name)
    paths = sorted(namespace.rglob("*"))
    names = tuple(path.relative_to(namespace).as_posix() for path in paths)
    links = tuple(
        (path.relative_to(namespace).as_posix(), os.readlink(path))
        for path in paths
        if path.name == "current" and path.is_symlink()
    )
    return names, links


def test_selected_migration_preserves_work_and_frozen_receipt(
    database: tuple[Engine, object], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The explicit migration owner applies the current head without touching other state."""
    from course_explorer_admin.lifecycle import InferenceProgress, LifecycleState

    engine, factory = database
    runner = mechanics.SubprocessRunner()
    admin_state = f"data/admin-tests/{uuid.uuid4().hex}"
    dataset_id = "0" * 32
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
    working_database: str | None = None
    try:
        # The immutable snapshot fact is the genuine head verification before any migration.
        verification = read_dataset_verification(raw)
        seed_courses(factory, [("dataset-target", "TEST.001", True)])
        markers = reconcile(factory)
        assert any(marker.group_id == "dataset-target" for marker in markers)

        directory = root / "datasets" / dataset_id
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        receipt_path = directory / "receipt.json"
        atomic_write_private_text(
            receipt_path,
            administrative_json(
                DatasetReceipt(
                    schema_version=1,
                    dataset_id=dataset_id,
                    database_name="course_explorer_test",
                    predecessor_id=None,
                    kind="initial",
                    dump_sha256=None,
                    verification=verification,
                )
            ),
        )
        atomic_write_private_text(
            root / "selected-dataset.json",
            administrative_json(DatasetPointer(schema_version=1, dataset_id=dataset_id)),
        )
        dump = directory / "database.dump"
        dump.write_bytes(b"frozen-dump-sentinel")
        receipt_bytes = receipt_path.read_bytes()
        pointer_bytes = (root / "selected-dataset.json").read_bytes()
        dump_bytes = dump.read_bytes()

        working = copy_to_working(dataset_id, runner=runner)
        working_database = working.database_name
        working_receipt_path = root / "datasets" / working.dataset_id / "receipt.json"
        working_dump = root / "datasets" / working.dataset_id / "database.dump"
        working_receipt_bytes = working_receipt_path.read_bytes()
        working_dump_bytes = working_dump.read_bytes()
        working_pointer_bytes = (root / "working-dataset.json").read_bytes()

        projections_before = _sql_projections(engine)

        # A genuinely non-idle stage state refuses before any apply.
        inference_root = root / "inference" / "current"
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
            commands.run_administrative_migration(role="working", runner=runner)

        # Selected applies the head while the stages are busy, and the explicit Working migration
        # applies it when they are idle. Neither rewrites a receipt or a pointer.
        applied = commands.run_administrative_migration(role="selected", runner=runner)
        assert applied.alembic_revision == verification.alembic_revision
        (inference_root / "state.json").unlink()
        working_applied = commands.run_administrative_migration(role="working", runner=runner)
        assert working_applied.alembic_revision == verification.alembic_revision

        # Configured-database migration refuses an enrolled deployment, while an empty state root
        # keeps the bootstrap adapter.
        with pytest.raises(ValueError):
            commands.run_administrative_database_migration(runner=runner)
        bootstrap_state = f"{admin_state}-bootstrap"
        monkeypatch.setenv("ADMIN_STATE_ROOT", bootstrap_state)
        raw_applied = commands.run_administrative_database_migration(runner=runner)
        assert raw_applied.alembic_revision == verification.alembic_revision
        monkeypatch.setenv("ADMIN_STATE_ROOT", admin_state)

        assert _sql_projections(engine) == projections_before
        # The frozen Selected and Working receipts, pointers and dumps are identical.
        assert (directory / "receipt.json").read_bytes() == receipt_bytes
        assert (root / "selected-dataset.json").read_bytes() == pointer_bytes
        assert dump.read_bytes() == dump_bytes
        assert working_receipt_path.read_bytes() == working_receipt_bytes
        assert working_dump.read_bytes() == working_dump_bytes
        assert (root / "working-dataset.json").read_bytes() == working_pointer_bytes
        assert read_dataset_receipt(root, dataset_id).database_name == "course_explorer_test"
        # A fresh snapshot capture uses the migrated head.
        snapshot_dump = root / "capture.dump"
        dump_database(
            runner=runner,
            root=administration.repository_root(),
            settings=raw,
            destination=snapshot_dump,
            include_embeddings=True,
        )
        assert snapshot_dump.is_file()
    finally:
        # Ensure the disposable test database is left at the current repository head.
        runner.run(
            ("uv", "run", "--offline", "--no-sync", "python", "-m", "alembic", "upgrade", "head"),
            cwd=administration.repository_root(),
            env={
                "POSTGRES_DB": "course_explorer_test",
                "ADMIN_STATE_ROOT": admin_state,
            },
            timeout=600,
        )
        if working_database is not None:
            _drop(runner, working_database)
        if root.exists():
            shutil.rmtree(root)
        if "bootstrap_state" in locals():
            bootstrap_root = administration.repository_root() / bootstrap_state
            if bootstrap_root.exists():
                shutil.rmtree(bootstrap_root)


def test_local_stage_writes_working_without_changing_selected(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    isolated_database_cluster: None,
) -> None:
    """One real embedding stage changes Working chunks and leaves Selected rows, artifacts and identity."""
    runner = mechanics.SubprocessRunner()
    repository = administration.repository_root()
    admin_state = f"data/admin-tests/{uuid.uuid4().hex}"
    initial = f"course_tests_local_{uuid.uuid4().hex[:8]}"
    monkeypatch.setenv("POSTGRES_DB", initial)
    monkeypatch.setenv("ADMIN_STATE_ROOT", admin_state)
    monkeypatch.setenv("ADMIN_DATASET_DATABASE_PREFIX", SERVER_PREFIX)
    monkeypatch.setenv("ADMIN_WORKER_DATABASE_PREFIX", WORKER_PREFIX)
    monkeypatch.setenv("ADMIN_DATABASE_OPERATION_TIMEOUT_SECONDS", "3600")
    for keys in (
        LOCAL_LIFECYCLE_KEYS,
        TRANSLATION_CONTROLLER_KEYS,
        INFERENCE_CONTROLLER_KEYS,
    ):
        for key, value in keys.items():
            monkeypatch.setenv(key, value)
    for key, value in {
        "INGESTION_CONTROLLER_STATE_ROOT": f"{admin_state}/ingestion",
        "EMBEDDING_CONTROLLER_STATE_ROOT": f"{admin_state}/embedding",
        "TRANSLATION_CONTROLLER_STATE_ROOT": f"{admin_state}/translation",
        "INFERENCE_CONTROLLER_STATE_ROOT": f"{admin_state}/inference",
        "COURSE_EXPLORER_WEB_GENERATION": "serving-generation-1",
    }.items():
        monkeypatch.setenv(key, value)
    admin = load_administrative_dataset_settings()
    root = admin_state_root(admin)
    working_database: str | None = None
    selected_engine: Engine | None = None
    working_engine: Engine | None = None
    try:
        _compose_exec(
            runner, "createdb", "--username", "course_explorer", "--template", "template0", initial
        )
        runner.run(
            ("uv", "run", "--offline", "--no-sync", "python", "-m", "alembic", "upgrade", "head"),
            cwd=repository,
            env={"POSTGRES_DB": initial},
            timeout=600,
        )
        settings = load_raw_database_settings().model_copy(update={"postgres_db": initial})
        engine = create_database_engine(settings)
        factory = create_session_factory(engine)
        seed_courses(factory, [("dataset-target", "TEST.001", True)])
        _seed_embedding(factory)
        engine.dispose()

        selected = initialize_selected_dataset(runner=runner)
        working = copy_to_working(selected.dataset_id, runner=runner)
        working_database = working.database_name
        selected_settings = load_database_settings(role="selected")
        state_root = administration.repository_root() / selected_settings.admin_state_root
        build_serving_artifacts(selected_settings, embedding=None)
        artifact_state = selected_artifact_state(state_root, selected_settings.postgres_db)
        selected_pointer = (state_root / "selected-dataset.json").read_bytes()

        selected_engine = create_database_engine(selected_settings)
        selected_content = selected_row_content(selected_engine)
        for table in ("courses", "course_versions", "course_texts", "course_embedding_chunks"):
            assert selected_content[table]
        serving_before = resolve_serving_dataset()
        assert serving_before.settings.postgres_db == selected_settings.postgres_db

        # Only the Working teaching text changes, so its real reconciliation has pending work.
        changed_text = "Muutettu sisalto TEST.001"
        working_engine = create_database_engine(load_database_settings(role="working"))
        with session_scope(create_session_factory(working_engine)) as working_session:
            text_row = working_session.scalar(
                select(CourseText)
                .join(CourseVersion, CourseVersion.id == CourseText.course_version_id)
                .where(CourseVersion.code == "TEST.001")
            )
            assert text_row is not None
            text_row.content_fi = changed_text
        working_engine.dispose()
        working_engine = None

        def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content)
            data = [
                {"index": index, "embedding": vector(0.0, 1.0)}
                for index, _text in enumerate(payload["input"])
            ]
            return embedding_response(data, model=payload["model"])

        real_provider = embedding_commands.EmbeddingProvider

        def provider(settings: object, **kwargs: object) -> object:
            return real_provider(
                settings,
                transport=httpx.MockTransport(handler),
                **kwargs,  # type: ignore[arg-type]
            )

        monkeypatch.setattr(embedding_commands, "EmbeddingProvider", provider)

        stage = EmbeddingStage()
        options = EmbeddingOptions(kind="embedding")
        session_id = uuid.uuid4().hex
        session = LifecycleSession(
            schema_version=1,
            session_id=session_id,
            stage="embedding",
            revision="a" * 40,
            identity_sha256=stage.identity_sha256(options),
            options=options,
            created_at=utc_now(),
        )
        stage_root = tmp_path / "embedding-stage"
        (stage_root / session_id).mkdir(mode=0o700, parents=True)
        atomic_write_private_text(
            stage_root / session_id / "session.json", administrative_json(session)
        )
        lifecycle.write_lifecycle_state(
            stage_root,
            LifecycleState(
                schema_version=1,
                session_id=session_id,
                lifecycle="running",
                requested_action="run",
                progress=stage.initial_progress(options),
                work_complete=False,
                active_seconds=0.0,
                running_since=utc_now(),
            ),
        )
        context = LifecycleContext(root=stage_root, session=session, runner=runner)
        assert stage.run(context) is True

        # The stage stored the changed Working text and one completed unit vector for it.
        working_engine = create_database_engine(load_database_settings(role="working"))
        with session_scope(create_session_factory(working_engine)) as working_session:
            stored_text = working_session.scalar(
                select(CourseText)
                .join(CourseVersion, CourseVersion.id == CourseText.course_version_id)
                .where(CourseVersion.code == "TEST.001")
            )
            assert stored_text is not None and stored_text.content_fi == changed_text
            chunk = working_session.scalar(
                select(CourseEmbeddingChunk)
                .join(CourseVersion, CourseVersion.id == CourseEmbeddingChunk.course_version_id)
                .where(
                    CourseVersion.code == "TEST.001",
                    CourseEmbeddingChunk.field == TeachingTextField.CONTENT,
                )
            )
            assert chunk is not None
            assert chunk.text == changed_text
            assert chunk.status is CourseEmbeddingStatus.COMPLETED
            assert chunk.embedding is not None

        # The Selected rows, artifacts, pointer and resolved serving identity equal the captured
        # values.
        assert selected_row_content(selected_engine) == selected_content
        assert selected_artifact_state(state_root, selected_settings.postgres_db) == artifact_state
        assert (state_root / "selected-dataset.json").read_bytes() == selected_pointer
        assert resolve_serving_dataset() == serving_before
        assert resolve_dataset_role(root, "selected").dataset_id == selected.dataset_id
        assert resolve_dataset_role(root, "working").dataset_id == working.dataset_id
    finally:
        if working_engine is not None:
            working_engine.dispose()
        if selected_engine is not None:
            selected_engine.dispose()
        errors: list[Exception] = []
        for name in (initial, working_database):
            if name is None:
                continue
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
            raise ExceptionGroup("local stage test cleanup failed", errors)


def test_stage_requires_working_schema_head(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    isolated_database_cluster: None,
) -> None:
    """The Working head check refuses a predecessor version while Selected is at head."""
    runner = mechanics.SubprocessRunner()
    repository = administration.repository_root()
    admin_state = f"data/admin-tests/{uuid.uuid4().hex}"
    initial = f"course_tests_head_{uuid.uuid4().hex[:8]}"
    monkeypatch.setenv("POSTGRES_DB", initial)
    monkeypatch.setenv("ADMIN_STATE_ROOT", admin_state)
    monkeypatch.setenv("ADMIN_DATASET_DATABASE_PREFIX", SERVER_PREFIX)
    monkeypatch.setenv("ADMIN_WORKER_DATABASE_PREFIX", WORKER_PREFIX)
    monkeypatch.setenv("ADMIN_DATABASE_OPERATION_TIMEOUT_SECONDS", "3600")
    for key, value in {
        "INGESTION_CONTROLLER_STATE_ROOT": f"{admin_state}/ingestion",
        "EMBEDDING_CONTROLLER_STATE_ROOT": f"{admin_state}/embedding",
        "TRANSLATION_CONTROLLER_STATE_ROOT": f"{admin_state}/translation",
        "INFERENCE_CONTROLLER_STATE_ROOT": f"{admin_state}/inference",
    }.items():
        monkeypatch.setenv(key, value)
    admin = load_administrative_dataset_settings()
    root = admin_state_root(admin)
    working_database: str | None = None
    selected_engine: Engine | None = None
    working_engine: Engine | None = None
    try:
        _compose_exec(
            runner, "createdb", "--username", "course_explorer", "--template", "template0", initial
        )
        runner.run(
            ("uv", "run", "--offline", "--no-sync", "python", "-m", "alembic", "upgrade", "head"),
            cwd=repository,
            env={"POSTGRES_DB": initial},
            timeout=600,
        )
        selected = initialize_selected_dataset(runner=runner)
        working = copy_to_working(selected.dataset_id, runner=runner)
        working_database = working.database_name
        assert load_database_settings(role="working").postgres_db == working.database_name
        assert resolve_dataset_role(root, "working").dataset_id == working.dataset_id

        script = ScriptDirectory.from_config(
            AlembicConfig(str(administration.repository_root() / "alembic.ini"))
        )
        heads = script.get_heads()
        assert len(heads) == 1
        head = heads[0]
        down_revision = script.get_revision(head).down_revision
        assert isinstance(down_revision, str)

        # The disposable Working database records the predecessor version directly. No downgrade
        # runs and no table changes.
        working_engine = create_database_engine(load_database_settings(role="working"))
        with working_engine.begin() as connection:
            connection.execute(
                text("UPDATE alembic_version SET version_num = :version"),
                {"version": down_revision},
            )
        working_engine.dispose()
        working_engine = None

        selected_engine = create_database_engine(load_database_settings(role="selected"))
        with selected_engine.connect() as connection:
            assert (
                connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
                == head
            )

        with pytest.raises(DatabaseSchemaMismatchError):
            require_working_database_schema()

        with selected_engine.connect() as connection:
            assert (
                connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
                == head
            )
        assert resolve_dataset_role(root, "working").dataset_id == working.dataset_id
    finally:
        if working_engine is not None:
            working_engine.dispose()
        if selected_engine is not None:
            selected_engine.dispose()
        errors: list[Exception] = []
        for name in (initial, working_database):
            if name is None:
                continue
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
            raise ExceptionGroup("schema head test cleanup failed", errors)


PROMOTION_PREFIX = "course_tests_promotion"
_PROMOTION_SESSION_ID = "d" * 32
PROMOTION_UNIT = _UNIT
PROMOTION_ADMIN_UNIT = _ADMIN_UNIT
PROMOTION_HOST = _WEB_HOST
PROMOTION_PORT = _WEB_PORT
PROMOTION_WORKERS = _WEB_WORKERS


def _bind_promotion_environment(
    monkeypatch: pytest.MonkeyPatch, *, prefix: str
) -> tuple[Path, str]:
    """Bind one promotion site unit, timing policy, admin root and source database name."""
    admin_state = f"data/admin-tests/{uuid.uuid4().hex}"
    initial = f"{prefix}_{uuid.uuid4().hex[:8]}"
    monkeypatch.setenv("POSTGRES_DB", initial)
    monkeypatch.setenv("ADMIN_STATE_ROOT", admin_state)
    monkeypatch.setenv("ADMIN_DATASET_DATABASE_PREFIX", prefix)
    monkeypatch.setenv("ADMIN_WORKER_DATABASE_PREFIX", f"{prefix}_w")
    monkeypatch.setenv("ADMIN_DATABASE_OPERATION_TIMEOUT_SECONDS", "3600")
    for keys in (
        LOCAL_LIFECYCLE_KEYS,
        TRANSLATION_CONTROLLER_KEYS,
        INFERENCE_CONTROLLER_KEYS,
    ):
        for key, value in keys.items():
            monkeypatch.setenv(key, value)
    for key, value in {
        "INGESTION_CONTROLLER_STATE_ROOT": f"{admin_state}/ingestion",
        "EMBEDDING_CONTROLLER_STATE_ROOT": f"{admin_state}/embedding",
        "TRANSLATION_CONTROLLER_STATE_ROOT": f"{admin_state}/translation",
        "INFERENCE_CONTROLLER_STATE_ROOT": f"{admin_state}/inference",
        "ADMIN_SITE_WEB_SERVICE_UNIT": PROMOTION_UNIT,
        "ADMIN_SITE_ADMIN_SERVICE_UNIT": PROMOTION_ADMIN_UNIT,
        "ADMIN_SITE_WEB_SERVICE_SCOPE": "user",
        "WEB_HOST": PROMOTION_HOST,
        "WEB_PORT": str(PROMOTION_PORT),
        "WEB_WORKERS": str(PROMOTION_WORKERS),
        "WEB_EMBEDDINGS_ENABLED": "false",
        "ADMIN_STOP_TIMEOUT_SECONDS": "77",
        "ADMIN_STARTUP_ATTEMPTS": "3",
        "ADMIN_POLL_INTERVAL_SECONDS": "0.01",
    }.items():
        monkeypatch.setenv(key, value)
    return admin_state_root(load_administrative_dataset_settings()), initial


def _retained_copy(source_dataset_id: str, runner: mechanics.ProcessRunner) -> DatasetReceipt:
    """Create one verified copy of an enrolled dataset without changing the Working pointer."""
    settings = load_administrative_dataset_settings()
    root = admin_state_root(settings)
    with mechanics.exclusive_action_lock(root, controller_name="datasets"):
        return datasets_module._copy_dataset_locked(settings, root, source_dataset_id, runner)


def _write_busy_stage(admin_root: Path) -> None:
    """Publish one non-idle inference state without a live recorded process."""
    state_root = admin_root / "inference" / "current"
    state_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    lifecycle.write_lifecycle_state(
        state_root,
        LifecycleState(
            session_id=_PROMOTION_SESSION_ID,
            lifecycle="running",
            requested_action="run",
            progress=InferenceProgress(kind="inference"),
            work_complete=False,
            active_seconds=0.0,
        ),
    )


def _receipt_ids(admin_root: Path) -> set[str]:
    """Return the dataset ids that hold a receipt under one scratch admin root."""
    datasets = admin_root / "datasets"
    if not datasets.is_dir():
        return set()
    return {path.parent.name for path in datasets.glob("*/receipt.json")}


def _promotion_copy(admin_root: Path, before: set[str]) -> DatasetReceipt:
    """Return the one receipt a failed or completed promotion created."""
    (dataset_id,) = _receipt_ids(admin_root) - before
    return read_dataset_receipt(admin_root, dataset_id)


def _drop_promotion_databases(
    runner: mechanics.ProcessRunner, admin_root: Path, initial: str
) -> None:
    """Drop every database this test's scratch receipts name, then remove the scratch root.

    The configured initial database is tracked separately. Every other created database, including
    one a failed promotion left behind, comes from its scratch receipt.
    """
    errors: list[Exception] = []
    names = {initial}
    if (admin_root / "datasets").is_dir():
        for receipt_path in sorted((admin_root / "datasets").glob("*/receipt.json")):
            receipt = read_dataset_receipt(admin_root, receipt_path.parent.name)
            names.add(receipt.database_name)
    for name in sorted(names):
        try:
            _drop(runner, name)
        except Exception as exc:
            errors.append(exc)
    if admin_root.exists():
        try:
            shutil.rmtree(admin_root)
        except Exception as exc:
            errors.append(exc)
    if errors:
        raise ExceptionGroup("promotion test cleanup failed", errors)


def _catalogue_artifact(state_root: Path, settings: object) -> bytes:
    """Read one built catalogue artifact once for an independent scripted response."""
    family = serving_artifact_root(state_root, serving_key(settings)) / "current"
    return (family / CATALOGUE_FILE).read_bytes()


def _served_catalogue(artifact: bytes, identity: str) -> bytes:
    """Append one synthetic serving identity to an artifact with a literal JSON suffix."""
    return artifact[:-1] + b',"dataset_identity":"' + identity.encode() + b'"}'


def _serve_catalogue(
    artifact: bytes, identity: Callable[[], str]
) -> Callable[[httpx.Request], httpx.Response]:
    """Answer both serving reads from one artifact and the current identity."""

    def handler(request: httpx.Request) -> httpx.Response:
        current = identity()
        if request.url.path == "/api/features":
            return httpx.Response(
                200,
                json={
                    "embeddings_enabled": False,
                    "inference_enabled": False,
                    "dataset_identity": current,
                },
            )
        return httpx.Response(200, content=_served_catalogue(artifact, current))

    return handler


def _scripted_serving(
    identities: Sequence[str], bodies: Sequence[bytes]
) -> Callable[[httpx.Request], httpx.Response]:
    """Answer each serving read from the next ordered identity or body.

    The workflow reads the previous identity once, then one identity and one catalogue body per
    proof attempt. Each list is consumed strictly in order, so a success script and a failed-catalogue
    script describe their own exact exchange rather than repeating a last entry.
    """
    remaining_identities = iter(identities)
    remaining_bodies = iter(bodies)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/features":
            return httpx.Response(
                200,
                json={
                    "embeddings_enabled": False,
                    "inference_enabled": False,
                    "dataset_identity": next(remaining_identities),
                },
            )
        return httpx.Response(200, content=next(remaining_bodies))

    return handler


@pytest.mark.parametrize("source_choice", ["working", "retained"])
def test_promotion_builds_a_copy_before_serving_it(
    monkeypatch: pytest.MonkeyPatch,
    source_choice: str,
    isolated_database_cluster: None,
) -> None:
    """A confirmed promotion publishes only a built copy and leaves every other dataset alone."""
    runner = mechanics.SubprocessRunner()
    repository = administration.repository_root()
    admin_root, initial = _bind_promotion_environment(monkeypatch, prefix=PROMOTION_PREFIX)
    working_pointer: bytes | None = None
    try:
        _compose_exec(
            runner, "createdb", "--username", "course_explorer", "--template", "template0", initial
        )
        runner.run(
            ("uv", "run", "--offline", "--no-sync", "python", "-m", "alembic", "upgrade", "head"),
            cwd=repository,
            env={"POSTGRES_DB": initial},
            timeout=600,
        )
        settings = load_raw_database_settings().model_copy(update={"postgres_db": initial})
        engine = create_database_engine(settings)
        seed_courses(
            create_session_factory(engine),
            [("promotion-target", "TEST.001", True), ("promotion-source", "TEST.002", False)],
        )
        engine.dispose()

        selected = initialize_selected_dataset(runner=runner)
        old_settings = load_database_settings(role="selected")
        build_serving_artifacts(old_settings, embedding=None)
        artifact = _catalogue_artifact(admin_root, old_settings)
        old_artifacts = selected_artifact_state(admin_root, old_settings.postgres_db)

        working = copy_to_working(selected.dataset_id, runner=runner)
        working_pointer = (admin_root / "working-dataset.json").read_bytes()
        if source_choice == "retained":
            source = _retained_copy(working.dataset_id, runner)
        else:
            source = working
        _write_busy_stage(admin_root)

        boundary = _RebuildProcessBoundary(
            root=repository,
            unit=_UNIT,
            listeners=((f"127.0.0.1:{PROMOTION_PORT}", _OWNED_PROCESS),),
            real_compose=True,
        )
        bind_promotion_http(
            monkeypatch,
            _serve_catalogue(artifact, lambda: "after" if boundary.restarted else "before"),
        )

        receipt = commands.run_administrative_dataset_promotion(
            source.dataset_id, confirm_restart=True, runner=boundary
        )

        assert receipt.kind == "copied"
        assert receipt.predecessor_id == source.dataset_id
        assert resolve_dataset_role(admin_root, "selected").dataset_id == receipt.dataset_id
        assert resolve_dataset_role(admin_root, "working").dataset_id == working.dataset_id
        assert working_pointer is not None
        assert (admin_root / "working-dataset.json").read_bytes() == working_pointer

        new_settings = dataset_settings(receipt.dataset_id)
        opened = ServingArtifacts.open(new_settings, embedding=None)
        assert opened.root.parent.parent == serving_database_root(admin_root, receipt.database_name)
        assert selected_artifact_state(admin_root, old_settings.postgres_db) == old_artifacts
        assert _database_exists(runner, initial)
        assert _database_exists(runner, source.database_name)
        assert _database_exists(runner, receipt.database_name)
        assert boundary.restart_commands == [("systemctl", "--user", "restart", PROMOTION_UNIT)]
        assert boundary.restarted is True
    finally:
        _drop_promotion_databases(runner, admin_root, initial)


_PROMOTION_FAILURES = (
    ("build", 0, OSError),
    ("restart", 1, subprocess.CalledProcessError),
    ("feature-proof", 0, RuntimeError),
    ("rollback", 2, ExceptionGroup),
)


@pytest.mark.parametrize(("failure", "restart_failures", "expected_error"), _PROMOTION_FAILURES)
def test_failed_promotion_preserves_the_previous_selection(
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
    restart_failures: int,
    expected_error: type[BaseException],
    isolated_database_cluster: None,
) -> None:
    """A failed promotion keeps every created resource and restores the previous selection.

    A build failure switches and restarts nothing. A restart or feature-proof failure restores the
    previous pointer and proves its serving readiness. A second failed restart raises both errors.
    """
    runner = mechanics.SubprocessRunner()
    repository = administration.repository_root()
    admin_root, initial = _bind_promotion_environment(monkeypatch, prefix=PROMOTION_PREFIX)
    serving_root = admin_root / "serving"
    try:
        _compose_exec(
            runner, "createdb", "--username", "course_explorer", "--template", "template0", initial
        )
        runner.run(
            ("uv", "run", "--offline", "--no-sync", "python", "-m", "alembic", "upgrade", "head"),
            cwd=repository,
            env={"POSTGRES_DB": initial},
            timeout=600,
        )
        settings = load_raw_database_settings().model_copy(update={"postgres_db": initial})
        engine = create_database_engine(settings)
        seed_courses(
            create_session_factory(engine),
            [("promotion-target", "TEST.001", True), ("promotion-source", "TEST.002", False)],
        )
        engine.dispose()

        selected = initialize_selected_dataset(runner=runner)
        old_settings = load_database_settings(role="selected")
        build_serving_artifacts(old_settings, embedding=None)
        artifact = _catalogue_artifact(admin_root, old_settings)
        old_artifacts = selected_artifact_state(admin_root, old_settings.postgres_db)
        selected_pointer = (admin_root / "selected-dataset.json").read_bytes()
        working = copy_to_working(selected.dataset_id, runner=runner)
        working_pointer = (admin_root / "working-dataset.json").read_bytes()
        source = _retained_copy(working.dataset_id, runner)
        before = _receipt_ids(admin_root)

        if failure == "build":
            serving_root.chmod(0o500)
        boundary = _RebuildProcessBoundary(
            root=repository,
            unit=_UNIT,
            listeners=((f"127.0.0.1:{PROMOTION_PORT}", _OWNED_PROCESS),),
            restart_failures=restart_failures,
            real_compose=True,
        )
        if failure == "feature-proof":
            # The catalogue is wrong on every configured proof attempt while the identity does
            # change, so only catalogue equality can reject this promotion. The rollback then
            # proves the previous artefact with its own literal suffix.
            bad_catalogue = b'{"courses":[]}'
            attempts = load_local_lifecycle_settings().startup_attempts
            bind_promotion_http(
                monkeypatch,
                _scripted_serving(
                    ["before", *(["after"] * attempts), "rollback"],
                    [*([bad_catalogue] * attempts), _served_catalogue(artifact, "rollback")],
                ),
            )
        else:
            bind_promotion_http(monkeypatch, _serve_catalogue(artifact, lambda: "rollback"))

        with pytest.raises(expected_error) as failed:
            commands.run_administrative_dataset_promotion(
                source.dataset_id, confirm_restart=True, runner=boundary
            )
        if failure == "rollback":
            assert len(failed.value.exceptions) == 2

        copy = _promotion_copy(admin_root, before)
        assert (admin_root / "selected-dataset.json").read_bytes() == selected_pointer
        assert resolve_dataset_role(admin_root, "selected").dataset_id == selected.dataset_id
        assert (admin_root / "working-dataset.json").read_bytes() == working_pointer
        assert resolve_dataset_role(admin_root, "working").dataset_id == working.dataset_id
        assert (admin_root / "datasets" / copy.dataset_id / "database.dump").is_file()
        assert _database_exists(runner, copy.database_name)
        assert _database_exists(runner, initial)

        if failure == "build":
            assert boundary.restart_commands == []
            assert not serving_database_root(admin_root, copy.database_name).exists()
        else:
            assert len(boundary.restart_commands) == 2
            assert serving_database_root(admin_root, copy.database_name).is_dir()
        assert selected_artifact_state(admin_root, old_settings.postgres_db) == old_artifacts
        assert _database_exists(runner, old_settings.postgres_db)
    finally:
        if serving_root.exists():
            serving_root.chmod(0o700)
        _drop_promotion_databases(runner, admin_root, initial)
