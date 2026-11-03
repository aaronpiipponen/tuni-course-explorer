"""Dataset-role initialization, return, rotation, listing, and deletion contracts."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from course_explorer import administration
from course_explorer.administration import (
    administrative_json,
    atomic_write_private_text,
    sha256_file,
)
from course_explorer.config import load_administrative_dataset_settings
from course_explorer.datasets import (
    DatabaseSnapshot,
    DatasetPointer,
    DatasetReceipt,
    clear_dataset_cache,
    read_dataset_receipt,
    resolve_dataset_role,
)
from course_explorer.serving_artifacts import serving_database_root
from course_explorer_admin import datasets as datasets_admin
from course_explorer_admin import remote
from course_explorer_admin.lifecycle import (
    InferenceProgress,
    LifecycleState,
    stage_state_root,
    write_lifecycle_state,
)
from course_explorer_admin.remote import WorkerDatasetSession
from tests.config._support import (
    ADMIN_DATASET_KEYS,
    INFERENCE_CONTROLLER_KEYS,
    LOCAL_LIFECYCLE_KEYS,
    TRANSLATION_CONTROLLER_KEYS,
    set_database_environment,
)
from tests.datasets._support import INITIAL_ID, sample_verification

INITIAL_DATABASE = "course_initial_demo"


class FakeRunner:
    """Scripted local runner for Compose, Alembic, and database commands."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.envs: list[dict[str, str]] = []

    def run(self, argv, *, cwd=None, env=None, stdin_path=None, stdout_path=None, timeout=None):
        command = tuple(argv)
        self.calls.append(command)
        self.envs.append(dict(env or {}))
        output = b""
        if "ps" in command and "--services" in command:
            output = b"db\n"
        return subprocess.CompletedProcess(list(command), 0, stdout=output, stderr=b"")


class UnavailableRunner(FakeRunner):
    """Refuse the database existence probe the way a stopped service does."""

    def run(self, argv, *, cwd=None, env=None, stdin_path=None, stdout_path=None, timeout=None):
        command = tuple(argv)
        if "psql" in command:
            self.calls.append(command)
            raise subprocess.CalledProcessError(1, list(command))
        return super().run(
            argv,
            cwd=cwd,
            env=env,
            stdin_path=stdin_path,
            stdout_path=stdout_path,
            timeout=timeout,
        )


class RestoreStub:
    """Records restore calls and returns the expected verification or fails once."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.failure_database: str | None = None

    def __call__(self, **kwargs):
        database_name = kwargs["database_name"]
        self.calls.append((database_name, kwargs["expected_sha256"]))
        if database_name == self.failure_database:
            raise ValueError("restored database verification does not match the expected snapshot")
        return kwargs["expected_verification"]


@pytest.fixture()
def configured(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> tuple[Path, RestoreStub, list[str]]:
    """Wire an isolated admin root, synthetic settings, and recording restore and migration stubs."""
    migration_calls: list[str] = []
    set_database_environment(
        monkeypatch,
        POSTGRES_DB=INITIAL_DATABASE,
        ADMIN_STATE_ROOT="data/admin",
    )
    for key, value in ADMIN_DATASET_KEYS.items():
        monkeypatch.setenv(key, value)
    # The stage roots resolve from the process environment. This fixture leaves them absent
    # under the same temporary root.
    for key, value in {
        **LOCAL_LIFECYCLE_KEYS,
        **TRANSLATION_CONTROLLER_KEYS,
        **INFERENCE_CONTROLLER_KEYS,
    }.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(administration, "repository_root", lambda: tmp_path)
    monkeypatch.setattr(
        datasets_admin, "read_dataset_verification", lambda settings: sample_verification()
    )
    restore = RestoreStub()
    monkeypatch.setattr(datasets_admin, "restore_database", restore)
    monkeypatch.setattr(
        datasets_admin,
        "_run_migration_upgrade",
        lambda database_name: migration_calls.append(database_name),
    )
    return tmp_path / "data" / "admin", restore, migration_calls


def _dump(tmp_path: Path, name: str, payload: bytes) -> Path:
    path = tmp_path / name
    path.write_bytes(payload)
    return path


def _session(
    admin,
    *,
    session_id: str,
    source_id: str,
    source_database: str,
    dump: Path,
) -> WorkerDatasetSession:
    return WorkerDatasetSession(
        schema_version=1,
        session_id=session_id,
        database_name=admin.database_name(session_id, worker=True),
        stage="inference",
        source_dataset_id=source_id,
        course_limit=None,
        input_snapshot=DatabaseSnapshot(
            schema_version=1,
            session_id=session_id,
            database_name=source_database,
            dump_sha256=hashlib.sha256(dump.read_bytes()).hexdigest(),
            verification=sample_verification(),
        ),
    )


def _assign_working_copy(root: Path, admin, source: DatasetReceipt) -> DatasetReceipt:
    """Write one synthetic copied receipt and its Working pointer for an owner test."""
    dataset_id = "f" * 32
    receipt = DatasetReceipt(
        schema_version=1,
        dataset_id=dataset_id,
        database_name=admin.database_name(dataset_id, worker=False),
        predecessor_id=source.dataset_id,
        kind="copied",
        dump_sha256="f" * 64,
        verification=sample_verification(),
    )
    directory = root / "datasets" / dataset_id
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    atomic_write_private_text(directory / "receipt.json", administrative_json(receipt))
    atomic_write_private_text(
        root / "working-dataset.json",
        administrative_json(DatasetPointer(schema_version=1, dataset_id=dataset_id)),
    )
    clear_dataset_cache()
    return receipt


def _snapshot(admin, session: WorkerDatasetSession, dump: Path) -> DatabaseSnapshot:
    return DatabaseSnapshot(
        schema_version=1,
        session_id=session.session_id,
        database_name=admin.database_name(session.session_id, worker=True),
        dump_sha256=hashlib.sha256(dump.read_bytes()).hexdigest(),
        verification=sample_verification(),
    )


def test_initial_setup_keeps_its_data_and_is_idempotent(
    configured: tuple[Path, RestoreStub, list[str]],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Setup migrates and verifies once without a branch or clean-tree gate, then reuses its receipt
    across a pointer-only interruption."""
    root, _, migration_calls = configured
    runner = FakeRunner()
    observations = [sample_verification()]
    verifier_calls: list[object] = []

    def verify(_settings):
        verifier_calls.append(_settings)
        return observations[-1]

    monkeypatch.setattr(datasets_admin, "read_dataset_verification", verify)

    receipt = datasets_admin.initialize_selected_dataset(runner=runner)

    assert receipt.kind == "initial"
    assert receipt.dataset_id == INITIAL_ID
    assert receipt.database_name == INITIAL_DATABASE
    assert not any("createdb" in call for call in runner.calls)
    assert not any("pg_dump" in call for call in runner.calls)
    assert migration_calls == [INITIAL_DATABASE]
    assert read_dataset_receipt(root, INITIAL_ID) == receipt
    assert len(verifier_calls) == 1

    calls_before = len(runner.calls)
    assert datasets_admin.initialize_selected_dataset(runner=runner) == receipt
    assert len(runner.calls) == calls_before
    assert len(verifier_calls) == 1

    # Removing only the pointer simulates interruption between receipt and pointer publication. The
    # retained receipt is republished without re-running the migration or the changed verifier.
    receipt_path = root / "datasets" / INITIAL_ID / "receipt.json"
    receipt_bytes = receipt_path.read_bytes()
    pointer_path = root / "selected-dataset.json"
    pointer_bytes = pointer_path.read_bytes()
    pointer_path.unlink()
    observations.append(
        sample_verification().model_copy(update={"alembic_revision": "20260101_9999"})
    )

    # Pointer repair reads no checkout state, and enrollment compares dataset identity only.
    retry_runner = FakeRunner()
    assert datasets_admin.initialize_selected_dataset(runner=retry_runner) == receipt
    assert retry_runner.calls == []
    assert not any(
        "compose" in call or "alembic" in call or call[:2] == ("sudo", "docker")
        for call in retry_runner.calls
    )
    assert len(verifier_calls) == 1
    assert receipt_path.read_bytes() == receipt_bytes
    assert pointer_path.read_bytes() == pointer_bytes

    # The deploy enrollment owner reuses the same explicit receipt and performs no migration.
    calls_before = len(retry_runner.calls)
    assert datasets_admin.ensure_selected_dataset(runner=retry_runner) == receipt
    assert len(retry_runner.calls) == calls_before
    assert migration_calls == [INITIAL_DATABASE]

    # Auto-enrollment leaves the configured example database unenrolled without touching files.
    empty_root = "data/admin-example"
    monkeypatch.setenv("ADMIN_STATE_ROOT", empty_root)
    monkeypatch.setenv("POSTGRES_DB", INITIAL_DATABASE)
    monkeypatch.setenv("EXAMPLE_POSTGRES_DB", INITIAL_DATABASE)
    clear_dataset_cache()
    assert datasets_admin.ensure_selected_dataset(runner=retry_runner) is None
    assert not (tmp_path / empty_root).exists()
    assert migration_calls == [INITIAL_DATABASE]


def test_return_verifies_before_working_assignment_and_preserves_failed_evidence(
    configured: tuple[Path, RestoreStub, list[str]], tmp_path: Path
) -> None:
    """A verified return assigns the dataset to Working. A repeat reuses the receipt. A failed
    restore leaves Working untouched."""
    root, restore, migration_calls = configured
    runner = FakeRunner()
    admin = load_administrative_dataset_settings()
    initial = datasets_admin.initialize_selected_dataset(runner=runner)
    working = _assign_working_copy(root, admin, initial)

    session_a = "a" * 32
    dump_a = _dump(tmp_path, "a.dump", b"dump-a")
    a = _session(
        admin,
        session_id=session_a,
        source_id=working.dataset_id,
        source_database=working.database_name,
        dump=dump_a,
    )
    snapshot_a = _snapshot(admin, a, dump_a)
    returned_a = datasets_admin.retain_returned_dataset(a, snapshot_a, dump_a, runner=runner)
    assert returned_a.kind == "returned"
    assert returned_a.predecessor_id == working.dataset_id
    assert (root / "working-dataset.json").is_file()
    assert restore.calls == [(admin.database_name(session_a, worker=False), snapshot_a.dump_sha256)]

    assert datasets_admin.retain_returned_dataset(a, None, None, runner=runner) == returned_a
    assert len(restore.calls) == 1

    session_b = "b" * 32
    dump_b = datasets_admin.retained_dump_path(root, session_b)
    dump_b.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    dump_b.write_bytes(b"dump-b")
    b = _session(
        admin,
        session_id=session_b,
        source_id=session_a,
        source_database=returned_a.database_name,
        dump=dump_b,
    )
    snapshot_b = _snapshot(admin, b, dump_b)
    restore.failure_database = admin.database_name(session_b, worker=False)
    pointer_before = (root / "working-dataset.json").read_bytes()
    with pytest.raises(ValueError):
        datasets_admin.retain_returned_dataset(b, snapshot_b, dump_b, runner=runner)
    # The Working assignment is untouched and the failed return retains its dump without a receipt.
    assert (root / "working-dataset.json").read_bytes() == pointer_before
    pointer = read_dataset_receipt(root, session_a)
    assert pointer.dataset_id == session_a
    assert (root / "datasets" / session_b / "database.dump").is_file()
    assert not (root / "datasets" / session_b / "receipt.json").exists()


def test_cleanup_returned_worker_database_requires_both_authorities(
    configured: tuple[Path, RestoreStub, list[str]], tmp_path: Path
) -> None:
    """Exact worker-copy deletion requires a matching session, return snapshot, and receipt."""
    root, _, migration_calls = configured
    runner = FakeRunner()
    admin = load_administrative_dataset_settings()
    initial = datasets_admin.initialize_selected_dataset(runner=runner)

    session_id = "c" * 32
    assert remote.worker_dataset_session_directory(session_id) == root / "sessions" / session_id
    dump = _dump(tmp_path, "c.dump", b"dump-c")
    session = _session(
        admin,
        session_id=session_id,
        source_id=INITIAL_ID,
        source_database=initial.database_name,
        dump=dump,
    )
    directory = remote.worker_dataset_session_directory(session_id)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    atomic_write_private_text(directory / "session.json", administrative_json(session))
    snapshot = _snapshot(admin, session, dump)
    receipt = DatasetReceipt(
        schema_version=1,
        dataset_id=session_id,
        database_name=admin.database_name(session_id, worker=False),
        predecessor_id=INITIAL_ID,
        kind="returned",
        dump_sha256=snapshot.dump_sha256,
        verification=sample_verification(),
    )

    # A returned snapshot that names another session refuses before any drop.
    mismatched = snapshot.model_copy(update={"session_id": "e" * 32})
    atomic_write_private_text(directory / "return.json", administrative_json(mismatched))
    with pytest.raises(ValueError):
        remote.cleanup_returned_worker_database(session, receipt, runner=runner)
    assert not any("dropdb" in call for call in runner.calls)

    # Matching authorities drop exactly the derived worker database.
    atomic_write_private_text(directory / "return.json", administrative_json(snapshot))
    remote.cleanup_returned_worker_database(session, receipt, runner=runner)
    drops = [call for call in runner.calls if "dropdb" in call]
    assert len(drops) == 1
    assert drops[0][-1] == admin.database_name(session_id, worker=True)
    assert "--if-exists" in drops[0]


def test_create_worker_dataset_session_refuses_a_reservation_with_evidence(
    configured: tuple[Path, RestoreStub, list[str]], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A reservation that already carries session/input evidence is refused before capture."""
    root, _, _ = configured
    runner = FakeRunner()
    initial = datasets_admin.initialize_selected_dataset(runner=runner)
    _assign_working_copy(root, load_administrative_dataset_settings(), initial)
    monkeypatch.setattr(administration, "repository_root", lambda: tmp_path)
    monkeypatch.setattr(
        remote, "dump_database", lambda **_kwargs: pytest.fail("capture ran over existing evidence")
    )
    session_id = "d" * 32
    directory = remote.worker_dataset_session_directory(session_id)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    (directory / "session.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError):
        remote.create_worker_dataset_session("translation", session_id=session_id, runner=runner)


def test_rotation_keeps_the_retained_pair_and_only_deletes_verified_ancestors(
    configured: tuple[Path, RestoreStub, list[str]], tmp_path: Path
) -> None:
    """Rotation keeps both role pairs and drops only indexed older Working ancestors."""
    root, _, migration_calls = configured
    runner = FakeRunner()
    admin = load_administrative_dataset_settings()
    initial = datasets_admin.initialize_selected_dataset(runner=runner)
    working = _assign_working_copy(root, admin, initial)

    backups = tmp_path / "data" / "backups"
    backups.mkdir(parents=True)
    sentinel = backups / "keep.txt"
    sentinel.write_text("keep")

    source_id, source_database = working.dataset_id, working.database_name
    receipts: dict[str, DatasetReceipt] = {"initial": initial, "working": working}
    dumps: dict[str, Path] = {}
    for label in ("a", "b", "c"):
        session_id = label * 32
        dump = _dump(tmp_path, f"{label}.dump", f"dump-{label}".encode())
        dumps[label] = dump
        session = _session(
            admin,
            session_id=session_id,
            source_id=source_id,
            source_database=source_database,
            dump=dump,
        )
        snapshot = _snapshot(admin, session, dump)
        receipts[label] = datasets_admin.retain_returned_dataset(
            session, snapshot, dump, runner=runner
        )
        source_id, source_database = session_id, receipts[label].database_name

    dropped = {call[-1] for call in runner.calls if "dropdb" in call}
    # Selected keeps the initial dataset, and Working keeps its current dataset and predecessor.
    assert INITIAL_DATABASE not in dropped
    assert working.database_name in dropped
    assert admin.database_name("a" * 32, worker=False) in dropped
    assert admin.database_name("b" * 32, worker=False) not in dropped
    assert admin.database_name("c" * 32, worker=False) not in dropped
    assert not dropped & {"postgres", "template0", "template1", "course_explorer_test"}
    assert resolve_dataset_role(root, "selected").dataset_id == INITIAL_ID
    assert resolve_dataset_role(root, "working").dataset_id == "c" * 32
    for label in ("a", "b", "c"):
        assert read_dataset_receipt(root, label * 32) == receipts[label]
    assert not (root / "datasets" / ("a" * 32) / "database.dump").exists()
    assert (root / "datasets" / ("b" * 32) / "database.dump").is_file()
    assert (root / "datasets" / ("c" * 32) / "database.dump").is_file()
    assert sentinel.read_text() == "keep"

    # A collection symlink redirecting the receipt tree outside the state root is refused before
    # rotation touches another database, dump, receipt, or the pointer.
    redirected = backups / "redirected-datasets"
    (root / "datasets").rename(redirected)
    (root / "datasets").symlink_to(redirected, target_is_directory=True)
    redirected_dump = redirected / ("a" * 32) / "database.dump"
    redirected_dump.write_bytes(b"old-a-dump-sentinel")
    pointer_path = root / "selected-dataset.json"
    pointer_bytes = pointer_path.read_bytes()
    receipt_paths = {label: redirected / (label * 32) / "receipt.json" for label in ("a", "b", "c")}
    receipt_bytes = {label: path.read_bytes() for label, path in receipt_paths.items()}

    calls_before = len(runner.calls)
    with pytest.raises(ValueError):
        datasets_admin.retain_returned_dataset(session, None, None, runner=runner)

    assert len(runner.calls) == calls_before
    assert redirected_dump.read_bytes() == b"old-a-dump-sentinel"
    assert pointer_path.read_bytes() == pointer_bytes
    for label, path in receipt_paths.items():
        assert path.read_bytes() == receipt_bytes[label]
    assert sentinel.read_text() == "keep"


def _write_chain_file(root: Path, relative: str, payload: str) -> Path:
    """Write one owner-only state file inside the isolated administrative root."""
    path = root / relative
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    atomic_write_private_text(path, payload)
    return path


def _retained_dump(root: Path, dataset_id: str, payload: bytes) -> Path:
    """Write one retained dataset dump beside its receipt under the administrative root."""
    path = root / "datasets" / dataset_id / "database.dump"
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


@pytest.mark.parametrize(
    "case",
    [
        "selected-dataset",
        "outside-chain",
        "selected-database-name",
        "returned-non-derived-name",
        "protected-initial-database",
        "symlinked-dump",
        "artifact-namespace-symlink",
    ],
)
def test_dataset_cleanup_refuses_unowned_or_selected_resources(
    configured: tuple[Path, RestoreStub, list[str]], tmp_path: Path, case: str
) -> None:
    """One refused dataset cleanup per invocation: no drop, no removal, every retained byte kept."""
    root, _, migration_calls = configured
    runner = FakeRunner()
    settings = load_administrative_dataset_settings()
    selected_id = "a" * 32
    predecessor_id = "b" * 32
    selected_database = settings.database_name(selected_id, worker=False)
    initial_database = INITIAL_DATABASE
    predecessor: DatasetReceipt | None = None
    if case == "selected-database-name":
        # The initial receipt names the selected database, so its id is not the delete boundary.
        initial_database = selected_database
    elif case == "protected-initial-database":
        initial_database = "course_explorer_test"
    elif case == "symlinked-dump":
        initial_database = "course_initial_archive"
    elif case == "returned-non-derived-name":
        predecessor = DatasetReceipt(
            schema_version=1,
            dataset_id=predecessor_id,
            database_name="retained_manual_database",
            predecessor_id=INITIAL_ID,
            kind="returned",
            dump_sha256="d" * 64,
            verification=sample_verification(),
        )
    chain = [
        DatasetReceipt(
            schema_version=1,
            dataset_id=selected_id,
            database_name=selected_database,
            predecessor_id=INITIAL_ID if predecessor is None else predecessor_id,
            kind="returned",
            dump_sha256="e" * 64,
            verification=sample_verification(),
        ),
        *([] if predecessor is None else [predecessor]),
        DatasetReceipt(
            schema_version=1,
            dataset_id=INITIAL_ID,
            database_name=initial_database,
            predecessor_id=None,
            kind="initial",
            dump_sha256=None,
            verification=sample_verification(),
        ),
    ]
    receipt_bytes: dict[Path, bytes] = {}
    for receipt in chain:
        path = _write_chain_file(
            root,
            f"datasets/{receipt.dataset_id}/receipt.json",
            administrative_json(receipt),
        )
        receipt_bytes[path] = path.read_bytes()
    if predecessor is not None:
        receipt_bytes[_retained_dump(root, predecessor_id, b"predecessor-dump")] = (
            b"predecessor-dump"
        )
    selected_dump = _retained_dump(root, selected_id, b"selected-dump")
    receipt_bytes[selected_dump] = b"selected-dump"

    outside = tmp_path / "outside-dump-target"
    outside.write_bytes(b"outside-dump-target")
    if case == "symlinked-dump":
        symlinked = root / "datasets" / INITIAL_ID / "database.dump"
        symlinked.symlink_to(outside)
    if case == "artifact-namespace-symlink":
        namespace = serving_database_root(root, initial_database)
        namespace.parent.mkdir(mode=0o700, parents=True)
        namespace.symlink_to(outside, target_is_directory=True)
    unrelated = tmp_path / "unrelated.txt"
    unrelated.write_text("unrelated")
    pointer_path = _write_chain_file(
        root,
        "selected-dataset.json",
        administrative_json(DatasetPointer(schema_version=1, dataset_id=selected_id)),
    )
    pointer_bytes = pointer_path.read_bytes()
    target_id = {
        "selected-dataset": selected_id,
        "outside-chain": "c" * 32,
        "selected-database-name": INITIAL_ID,
        "returned-non-derived-name": predecessor_id,
        "protected-initial-database": INITIAL_ID,
        "symlinked-dump": INITIAL_ID,
        "artifact-namespace-symlink": INITIAL_ID,
    }[case]

    with pytest.raises(ValueError):
        datasets_admin.delete_retained_dataset(target_id, runner=runner)

    assert not any("dropdb" in call for call in runner.calls)
    assert pointer_path.read_bytes() == pointer_bytes
    for path, payload in receipt_bytes.items():
        assert path.read_bytes() == payload
    assert outside.read_bytes() == b"outside-dump-target"
    assert unrelated.read_text() == "unrelated"
    assert read_dataset_receipt(root, INITIAL_ID).database_name == initial_database


def _state_files(root: Path) -> list[str]:
    """Return every path under the state root as a repository-style relative name."""
    return sorted(path.relative_to(root).as_posix() for path in root.rglob("*"))


def test_dataset_listing_reports_unavailable_database_presence(
    configured: tuple[Path, RestoreStub, list[str]], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """One inventory reports available, unavailable and bootstrap probe states without writing."""
    root, _, _ = configured
    runner = FakeRunner()
    admin = load_administrative_dataset_settings()
    selected = datasets_admin.initialize_selected_dataset(runner=runner)
    working = _assign_working_copy(root, admin, selected)

    older_id = "e" * 32
    older = DatasetReceipt(
        schema_version=1,
        dataset_id=older_id,
        database_name=admin.database_name(older_id, worker=False),
        predecessor_id=working.dataset_id,
        kind="copied",
        dump_sha256="e" * 64,
        verification=sample_verification(),
    )
    directory = root / "datasets" / older_id
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    atomic_write_private_text(directory / "receipt.json", administrative_json(older))
    artifact = serving_database_root(root, older.database_name)
    artifact.mkdir(mode=0o700, parents=True)
    (artifact / "current.txt").write_text("build", encoding="utf-8")

    files_before = _state_files(root)
    inventory = datasets_admin.list_retained_datasets(runner=runner)
    assert _state_files(root) == files_before
    assert inventory.mode == "enrolled"
    assert inventory.database_probe == "available"
    assert inventory.bootstrap_database is None
    entries = {entry.dataset_id: entry for entry in inventory.datasets}
    assert set(entries) == {selected.dataset_id, working.dataset_id, older_id}
    assert entries[selected.dataset_id].selected is True
    assert entries[selected.dataset_id].working is False
    assert entries[selected.dataset_id].database_presence == "absent"
    assert entries[selected.dataset_id].predecessor_id is None
    assert entries[selected.dataset_id].receipt_schema_revision == (
        sample_verification().alembic_revision
    )
    assert entries[working.dataset_id].working is True
    assert entries[working.dataset_id].database_presence == "absent"
    # The artifact-only dataset is included without a retained dump or a present database, and its
    # own namespace existence is the reported artifact fact.
    assert entries[older_id].dump_path is None
    assert entries[older_id].selected is False
    assert entries[older_id].working is False
    assert entries[older_id].database_presence == "absent"
    assert entries[older_id].predecessor_id == working.dataset_id
    assert entries[older_id].artifacts_present is True
    assert entries[working.dataset_id].artifacts_present is False

    files_before = _state_files(root)
    unavailable = datasets_admin.list_retained_datasets(runner=UnavailableRunner())
    assert _state_files(root) == files_before
    assert unavailable.database_probe == "unavailable"
    assert {entry.dataset_id for entry in unavailable.datasets} == set(entries)
    assert all(entry.database_presence == "unavailable" for entry in unavailable.datasets)

    empty = "data/admin-empty"
    monkeypatch.setenv("ADMIN_STATE_ROOT", empty)
    empty_root = tmp_path / empty
    bootstrap = datasets_admin.list_retained_datasets(runner=runner)
    assert bootstrap.mode == "bootstrap"
    assert bootstrap.datasets == ()
    # The configured database joins the one probe without becoming a listed dataset row.
    assert bootstrap.bootstrap_database == INITIAL_DATABASE
    assert bootstrap.database_probe == "available"
    assert not empty_root.exists()

    # A stopped service reports the typed unavailable probe even with no receipt to probe.
    stopped = datasets_admin.list_retained_datasets(runner=UnavailableRunner())
    assert stopped.datasets == ()
    assert stopped.bootstrap_database == INITIAL_DATABASE
    assert stopped.database_probe == "unavailable"


def test_working_deletion_requires_idle_confirmation_and_clears_its_pointer(
    configured: tuple[Path, RestoreStub, list[str]], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Working deletion refuses a busy or unconfirmed target and clears only its pointer."""
    root, _, _ = configured
    runner = FakeRunner()
    admin = load_administrative_dataset_settings()
    selected = datasets_admin.initialize_selected_dataset(runner=runner)
    working = _assign_working_copy(root, admin, selected)
    working_dump = root / "datasets" / working.dataset_id / "database.dump"
    working_dump.write_bytes(b"working-dump")
    selected_artifact = serving_database_root(root, selected.database_name)
    selected_artifact.mkdir(mode=0o700, parents=True)
    (selected_artifact / "keep.txt").write_text("selected", encoding="utf-8")
    working_artifact = serving_database_root(root, working.database_name)
    working_artifact.mkdir(mode=0o700, parents=True)
    (working_artifact / "drop.txt").write_text("working", encoding="utf-8")
    backups = tmp_path / "data" / "backups"
    backups.mkdir(parents=True)
    (backups / "keep.dump").write_text("backup", encoding="utf-8")

    stage_root = stage_state_root("inference")
    stage_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    write_lifecycle_state(
        stage_root,
        LifecycleState(
            schema_version=1,
            session_id="a" * 32,
            lifecycle="running",
            requested_action="run",
            progress=InferenceProgress(kind="inference"),
            work_complete=False,
            active_seconds=0.0,
        ),
    )
    # The inventory and the destructive guard read the one shared busy predicate.
    assert datasets_admin.stage_is_busy("inference") is True
    assert datasets_admin.stage_is_busy("ingestion") is False
    busy_report = datasets_admin.list_retained_datasets(runner=runner)
    assert busy_report.stage_busy == {
        "ingestion": False,
        "embedding": False,
        "translation": False,
        "inference": True,
    }
    with pytest.raises(ValueError):
        datasets_admin.delete_retained_dataset(
            working.dataset_id, confirm_working=True, runner=runner
        )
    assert (root / "working-dataset.json").is_file()
    assert not any("dropdb" in call for call in runner.calls)

    (stage_root / "state.json").unlink()
    assert datasets_admin.stage_is_busy("inference") is False
    idle_report = datasets_admin.list_retained_datasets(runner=runner)
    assert not any(idle_report.stage_busy.values())
    with pytest.raises(ValueError):
        datasets_admin.delete_retained_dataset(working.dataset_id, runner=runner)
    assert (root / "working-dataset.json").is_file()

    report = datasets_admin.delete_retained_dataset(
        working.dataset_id, confirm_working=True, runner=runner
    )
    assert report.dataset_id == working.dataset_id
    assert report.database_name == working.database_name
    drops = [call for call in runner.calls if "dropdb" in call]
    assert [call[-1] for call in drops] == [working.database_name]
    assert not (root / "working-dataset.json").exists()
    assert not working_dump.exists()
    assert not working_artifact.exists()
    with pytest.raises(FileNotFoundError):
        resolve_dataset_role(root, "working")
    assert resolve_dataset_role(root, "selected").dataset_id == selected.dataset_id
    assert (root / "selected-dataset.json").is_file()
    assert selected_artifact.is_dir()
    assert (selected_artifact / "keep.txt").read_text(encoding="utf-8") == "selected"
    assert (backups / "keep.dump").read_text(encoding="utf-8") == "backup"


def _wait_until(predicate, *, timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("export child boundary did not reach the expected observation")


def test_worker_export_serializes_reconnect_and_reuses_completed_snapshot(
    configured: tuple[Path, RestoreStub, list[str]], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A reconnect during an in-flight worker export waits at the one authoritative lock and both
    callers return the validated snapshot with exactly one dump and byte-identical output."""
    _root, _, _ = configured
    admin = load_administrative_dataset_settings()
    session_id = "e" * 32
    dump = _dump(tmp_path, "e.dump", b"dump-e")
    session = _session(
        admin,
        session_id=session_id,
        source_id=INITIAL_ID,
        source_database=INITIAL_DATABASE,
        dump=dump,
    )
    directory = remote.worker_dataset_session_directory(session_id)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    atomic_write_private_text(directory / "session.json", administrative_json(session))

    env = dict(os.environ)
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2])
    children: list[subprocess.Popen[bytes]] = []
    for _ in range(2):
        children.append(
            subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "tests.admin._remote_support",
                    str(tmp_path),
                    "export",
                    session_id,
                ],
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        )
    try:
        # Both callers enter. Exactly one is inside the external dump boundary and the other waits.
        _wait_until(lambda: len(list(directory.glob("export-entry-*"))) == 2)
        _wait_until(lambda: (directory / "dump-started").is_file())
        (directory / "dump-release").write_text("1", encoding="utf-8")

        snapshots = []
        for child in children:
            out, err = child.communicate(timeout=60)
            assert child.returncode == 0, err.decode()
            snapshots.append(json.loads(out.decode()))
        assert snapshots[0] == snapshots[1]
        assert (directory / "dump-invocations").read_text(encoding="utf-8").splitlines() == ["dump"]
        assert sha256_file(directory / "return.dump") == snapshots[0]["dump_sha256"]
        assert (directory / "dump-done").is_file()
    finally:
        for child in children:
            if child.poll() is None:
                child.kill()
            child.wait()
