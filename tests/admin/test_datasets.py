"""Selected-dataset initialize/return/rotation contracts."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from course_explorer.administration import (
    administrative_json,
    atomic_write_private_text,
    sha256_file,
)
from course_explorer.config import load_administrative_dataset_settings
from course_explorer.datasets import (
    DatabaseSnapshot,
    DatasetReceipt,
    SelectedDatasetPointer,
    read_dataset_receipt,
)
from course_explorer_admin import datasets as datasets_admin
from course_explorer_admin import remote
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
def configured(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> tuple[Path, RestoreStub]:
    """Wire an isolated admin root, synthetic settings, and a recording restore stub."""
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
    monkeypatch.setattr(datasets_admin, "repository_root", lambda: tmp_path)
    monkeypatch.setattr(
        datasets_admin, "read_dataset_verification", lambda settings: sample_verification()
    )
    restore = RestoreStub()
    monkeypatch.setattr(datasets_admin, "restore_database", restore)
    return tmp_path / "data" / "admin", restore


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


def _snapshot(admin, session: WorkerDatasetSession, dump: Path) -> DatabaseSnapshot:
    return DatabaseSnapshot(
        schema_version=1,
        session_id=session.session_id,
        database_name=admin.database_name(session.session_id, worker=True),
        dump_sha256=hashlib.sha256(dump.read_bytes()).hexdigest(),
        verification=sample_verification(),
    )


def test_initial_setup_keeps_its_data_and_is_idempotent(
    configured: tuple[Path, RestoreStub], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Setup migrates and verifies once without a branch or clean-tree gate, then reuses its receipt
    across a pointer-only interruption."""
    root, _ = configured
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
    alembic = [index for index, call in enumerate(runner.calls) if "alembic" in call]
    assert alembic
    assert runner.envs[alembic[0]]["SELECTED_DATASET_ENABLED"] == "0"
    assert runner.envs[alembic[0]]["POSTGRES_DB"] == INITIAL_DATABASE
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


def test_return_verifies_before_selection_and_preserves_failed_evidence(
    configured: tuple[Path, RestoreStub], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A verified return selects the dataset. A re-return reuses it. A mismatch preserves the selection."""
    root, restore = configured
    runner = FakeRunner()
    admin = load_administrative_dataset_settings()
    initial = datasets_admin.initialize_selected_dataset(runner=runner)

    session_a = "a" * 32
    dump_a = _dump(tmp_path, "a.dump", b"dump-a")
    a = _session(
        admin,
        session_id=session_a,
        source_id=INITIAL_ID,
        source_database=initial.database_name,
        dump=dump_a,
    )
    snapshot_a = _snapshot(admin, a, dump_a)
    returned_a = datasets_admin.retain_returned_dataset(a, snapshot_a, dump_a, runner=runner)
    assert returned_a.kind == "returned"
    assert returned_a.predecessor_id == INITIAL_ID
    assert (root / "selected-dataset.json").is_file()
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
    pointer_before = (root / "selected-dataset.json").read_bytes()
    original_sha256_file = datasets_admin.sha256_file

    def guard_same_path(path: Path) -> str:
        if path == dump_b:
            raise AssertionError("a same-path retained dump must not be hashed")
        return original_sha256_file(path)

    monkeypatch.setattr(datasets_admin, "sha256_file", guard_same_path)
    with pytest.raises(ValueError):
        datasets_admin.retain_returned_dataset(b, snapshot_b, dump_b, runner=runner)
    # The selection is untouched and the failed return retains its dump without a receipt.
    assert (root / "selected-dataset.json").read_bytes() == pointer_before
    pointer = read_dataset_receipt(root, session_a)
    assert pointer.dataset_id == session_a
    assert (root / "datasets" / session_b / "database.dump").is_file()
    assert not (root / "datasets" / session_b / "receipt.json").exists()


def test_cleanup_returned_worker_database_requires_both_authorities(
    configured: tuple[Path, RestoreStub], tmp_path: Path
) -> None:
    """Exact worker-copy deletion requires a matching session, return snapshot, and receipt."""
    root, _ = configured
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

    # A returned snapshot that does not match the receipt refuses before any drop.
    mismatched = snapshot.model_copy(update={"dump_sha256": "b" * 64})
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
    configured: tuple[Path, RestoreStub], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A reservation that already carries session/input evidence is refused before capture."""
    _root, _ = configured
    runner = FakeRunner()
    datasets_admin.initialize_selected_dataset(runner=runner)
    monkeypatch.setattr(remote, "repository_root", lambda: tmp_path)
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
    configured: tuple[Path, RestoreStub], tmp_path: Path
) -> None:
    """Rotation keeps the current and immediate predecessor and drops only indexed older DBs."""
    root, _ = configured
    runner = FakeRunner()
    admin = load_administrative_dataset_settings()
    initial = datasets_admin.initialize_selected_dataset(runner=runner)

    backups = tmp_path / "data" / "backups"
    backups.mkdir(parents=True)
    sentinel = backups / "keep.txt"
    sentinel.write_text("keep")

    source_id, source_database = initial.dataset_id, initial.database_name
    receipts: dict[str, DatasetReceipt] = {"initial": initial}
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
    # After the third return the initial and first two ancestors are outside the retained pair.
    assert INITIAL_DATABASE in dropped
    assert admin.database_name("a" * 32, worker=False) in dropped
    assert admin.database_name("b" * 32, worker=False) not in dropped
    assert admin.database_name("c" * 32, worker=False) not in dropped
    assert not dropped & {"postgres", "template0", "template1", "course_explorer_test"}
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
        "served-database-with-selection-disabled",
        "returned-non-derived-name",
        "protected-initial-database",
        "symlinked-dump",
    ],
)
def test_dataset_cleanup_refuses_unowned_or_selected_resources(
    configured: tuple[Path, RestoreStub], tmp_path: Path, case: str
) -> None:
    """One refused dataset cleanup per invocation: no drop, no removal, every retained byte kept."""
    root, _ = configured
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
    elif case == "served-database-with-selection-disabled":
        # The receipt names the raw database, which the site serves while selection is disabled.
        initial_database = INITIAL_DATABASE
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
    unrelated = tmp_path / "unrelated.txt"
    unrelated.write_text("unrelated")
    pointer_path = _write_chain_file(
        root,
        "selected-dataset.json",
        administrative_json(SelectedDatasetPointer(schema_version=1, dataset_id=selected_id)),
    )
    pointer_bytes = pointer_path.read_bytes()
    target_id = {
        "selected-dataset": selected_id,
        "outside-chain": "c" * 32,
        "selected-database-name": INITIAL_ID,
        "served-database-with-selection-disabled": INITIAL_ID,
        "returned-non-derived-name": predecessor_id,
        "protected-initial-database": INITIAL_ID,
        "symlinked-dump": INITIAL_ID,
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


def _wait_until(predicate, *, timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("export child boundary did not reach the expected observation")


def test_worker_export_serializes_reconnect_and_reuses_completed_snapshot(
    configured: tuple[Path, RestoreStub], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A reconnect during an in-flight worker export waits at the one authoritative lock and both
    callers return the validated snapshot with exactly one dump and byte-identical output."""
    _root, _ = configured
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
