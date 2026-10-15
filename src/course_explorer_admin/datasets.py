"""Sole writer of selected-dataset receipts/pointer and owner of server dataset rotation.

Initial setup enrolls the configured database through the migration head. A verified return restores
a returned worker dump into a derived server database and selects it. Rotation retains the selected
dataset plus its immediate predecessor and drops chain-proven older databases and their confined
dumps. It is the only module that writes a receipt or pointer and the only one that drops a server
dataset database. Lock ownership is shared within this package so rotation does not nest the action lock.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from course_explorer.administration import (
    administrative_json,
    atomic_write_private_text,
    repository_root,
    session_directory,
    sha256_file,
)
from course_explorer.config import (
    AdministrativeDatasetSettings,
    load_administrative_dataset_settings,
    load_raw_database_settings,
)
from course_explorer.datasets import (
    _INITIAL_DATASET_ID,
    DatabaseSnapshot,
    DatasetReceipt,
    DatasetVerification,
    SelectedDatasetPointer,
    read_dataset_receipt,
    read_dataset_verification,
    require_selected_dataset_root,
    resolve_selected_dataset,
)
from course_explorer_admin import mechanics
from course_explorer_admin.snapshots import restore_database

if TYPE_CHECKING:
    from course_explorer_admin.remote import WorkerDatasetSession

_PROTECTED_DATABASES = frozenset(
    {
        "postgres",
        "template0",
        "template1",
        "course_explorer_test",
        "course_explorer_translation_worker_proof",
    }
)


def admin_state_root(settings: AdministrativeDatasetSettings, *, base: Path | None = None) -> Path:
    """Resolve the repository-relative admin state root and refuse the backups boundary.

    The shared read-only state guard runs first, before the path is resolved or any action
    lock is created, so a symlinked root, collection, or lock can never redirect a dump, restore,
    rotation, or receipt/pointer write into ``data/backups`` or another location. ``base`` defaults
    to the repository root, so a caller can redirect every administrative path to another root.
    """
    repository = repository_root() if base is None else base
    root = repository / settings.admin_state_root
    require_selected_dataset_root(root)
    backups = (repository / "data" / "backups").resolve()
    resolved = root.resolve()
    if resolved == backups or backups in resolved.parents:
        raise ValueError("admin state root must not be inside data/backups")
    return root


def _dataset_directory(root: Path, dataset_id: str) -> Path:
    require_selected_dataset_root(root)
    return session_directory(root / "datasets", dataset_id)


def _write_receipt(root: Path, receipt: DatasetReceipt) -> None:
    directory = _dataset_directory(root, receipt.dataset_id)
    directory.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    directory.mkdir(mode=0o700, exist_ok=True)
    atomic_write_private_text(directory / "receipt.json", administrative_json(receipt))


def _write_pointer(root: Path, dataset_id: str) -> None:
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    atomic_write_private_text(
        root / "selected-dataset.json",
        administrative_json(SelectedDatasetPointer(schema_version=1, dataset_id=dataset_id)),
    )


def _read_required_receipt(root: Path, dataset_id: str) -> DatasetReceipt:
    receipt = read_dataset_receipt(root, dataset_id)
    if receipt.dataset_id != dataset_id:
        raise ValueError("dataset receipt identity does not match the requested dataset")
    return receipt


def read_optional_dataset_receipt(root: Path, dataset_id: str) -> DatasetReceipt | None:
    receipt_path = _dataset_directory(root, dataset_id) / "receipt.json"
    if receipt_path.is_symlink():
        raise ValueError("dataset receipt must not be a symlink")
    if not receipt_path.exists():
        return None
    return _read_required_receipt(root, dataset_id)


def require_droppable_database(database_name: str) -> None:
    """Refuse to drop a protected database name."""
    if database_name in _PROTECTED_DATABASES:
        raise ValueError("refuse to drop a protected database")


def _retain_dump(source: Path, destination: Path) -> None:
    """Copy one returned dump to its confined retention path, reusing an identical present file."""
    destination.parent.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    destination.parent.mkdir(mode=0o700, exist_ok=True)
    if destination.is_symlink() or (destination.exists() and not destination.is_file()):
        raise ValueError("retained dataset dump must be a regular non-symlink file")
    if destination.exists():
        if sha256_file(destination) != sha256_file(source):
            raise ValueError("retained dataset dump does not match the returned dump")
        return
    descriptor, temporary_name = tempfile.mkstemp(
        dir=destination.parent, prefix=f".{destination.name}-", suffix=".tmp"
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        shutil.copyfile(source, temporary)
        os.chmod(temporary, 0o600)
        os.replace(temporary, destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _run_migration_upgrade(
    runner: mechanics.ProcessRunner,
    *,
    database_name: str,
    admin_state_root: str,
    timeout: float,
) -> None:
    """Run the Alembic ``upgrade head`` against one explicitly named database."""
    runner.run(
        ("uv", "run", "--no-sync", "python", "-m", "alembic", "upgrade", "head"),
        cwd=repository_root(),
        env={
            "SELECTED_DATASET_ENABLED": "0",
            "POSTGRES_DB": database_name,
            "ADMIN_STATE_ROOT": admin_state_root,
        },
        timeout=timeout,
    )


def _require_stage_idle(stage: str) -> None:
    """Refuse when one stage root has a non-idle durable state or a live recorded process."""
    from course_explorer_admin import lifecycle

    state = lifecycle.read_lifecycle_state(lifecycle.stage_state_root(stage))  # type: ignore[arg-type]
    if state is None:
        return
    if state.lifecycle != "idle":
        raise ValueError(f"stage {stage} is not durably idle")
    if state.process is not None and mechanics.owned_process_is_alive(state.process):
        raise ValueError(f"stage {stage} still has a live recorded process")


def require_stages_idle() -> None:
    """Refuse unless all four stage roots are absent or durably idle with no live process.

    It is the one shared server-local idle guard: the guarded selected-dataset migration and the
    operator disposition surface both call it, so a protected mutation runs only when every stage is
    idle.
    """
    for stage in ("ingestion", "embedding", "translation", "inference"):
        _require_stage_idle(stage)


def migrate_selected_dataset(*, runner: mechanics.ProcessRunner) -> DatasetVerification:
    """Apply the Alembic head to the selected dataset as explicit maintenance.

    It resolves the selected receipt under the admin state root, requires every stage root to be
    absent or durably idle with no live recorded process, and requires the server ``db`` service
    already running. It runs the Alembic upgrade against the selected database and returns the
    owner's verification. Failure preserves data and files and propagates.
    """
    settings = load_administrative_dataset_settings()
    root = admin_state_root(settings)
    with mechanics.exclusive_action_lock(root, controller_name="datasets"):
        receipt = resolve_selected_dataset(root)
        require_stages_idle()
        running = mechanics.running_compose_services(
            lambda argv: runner.run(tuple(argv), cwd=repository_root()).stdout
        )
        if "db" not in running:
            raise RuntimeError("the server db service must already be running")
        _run_migration_upgrade(
            runner,
            database_name=receipt.database_name,
            admin_state_root=str(settings.admin_state_root),
            timeout=settings.database_operation_timeout_seconds,
        )
        return read_dataset_verification(
            load_raw_database_settings().model_copy(update={"postgres_db": receipt.database_name})
        )


def initialize_selected_dataset(*, runner: mechanics.ProcessRunner) -> DatasetReceipt:
    """Select a configured database as the initial selected dataset, once.

    An already-selected dataset is reused. Otherwise the raw configured database is migrated to the
    repository head and enrolled with the zero dataset id. An enrollment interrupted after the
    initial receipt but before the pointer is republished from that retained receipt alone: a
    matching zero-id initial receipt for the same database name proves the verification, so the
    pointer is written without re-migrating or re-verifying. A checkout revision change alone is
    not a mismatch.
    """
    settings = load_administrative_dataset_settings()
    root = admin_state_root(settings)
    with mechanics.exclusive_action_lock(root, controller_name="datasets"):
        try:
            existing = resolve_selected_dataset(root)
        except FileNotFoundError:
            existing = None
        if existing is not None:
            return existing
        raw = load_raw_database_settings()
        require_droppable_database(raw.postgres_db)
        _, revision = mechanics.require_prepared_checkout(runner, repository_root())
        retained = read_optional_dataset_receipt(root, _INITIAL_DATASET_ID)
        if retained is not None:
            if (
                retained.kind != "initial"
                or retained.dataset_id != _INITIAL_DATASET_ID
                or retained.database_name != raw.postgres_db
            ):
                raise ValueError("retained initial dataset receipt does not match this setup")
            _write_pointer(root, retained.dataset_id)
            return retained
        timeout = settings.database_operation_timeout_seconds
        mechanics.ensure_prepared_services(
            lambda argv: runner.run(tuple(argv), cwd=repository_root(), timeout=timeout).stdout,
            ("db",),
        )
        _run_migration_upgrade(
            runner,
            database_name=raw.postgres_db,
            admin_state_root=str(settings.admin_state_root),
            timeout=timeout,
        )
        receipt = DatasetReceipt(
            schema_version=1,
            dataset_id=_INITIAL_DATASET_ID,
            database_name=raw.postgres_db,
            predecessor_id=None,
            kind="initial",
            revision=revision,
            dump_sha256=None,
            verification=read_dataset_verification(raw),
        )
        _write_receipt(root, receipt)
        _write_pointer(root, receipt.dataset_id)
        return receipt


def _resolve_source_and_existing(
    root: Path, session: WorkerDatasetSession
) -> tuple[DatasetReceipt, DatasetReceipt | None]:
    """Return the session's source receipt and any returned receipt for this session."""
    current = resolve_selected_dataset(root)
    if current.dataset_id == session.session_id:
        if current.kind != "returned" or current.predecessor_id != session.source_dataset_id:
            raise ValueError("selected dataset is not this session's returned dataset")
        return _read_required_receipt(root, session.source_dataset_id), current
    if current.dataset_id == session.source_dataset_id:
        return current, read_optional_dataset_receipt(root, session.session_id)
    raise ValueError("current dataset is neither the session source nor its returned dataset")


def require_returned_dataset_receipt(
    receipt: DatasetReceipt, session: WorkerDatasetSession, *, server_database: str
) -> None:
    """Require one returned receipt to describe exactly this session's returned dataset."""
    if (
        receipt.kind != "returned"
        or receipt.dataset_id != session.session_id
        or receipt.database_name != server_database
        or receipt.predecessor_id != session.source_dataset_id
        or receipt.revision != session.revision
    ):
        raise ValueError("existing returned dataset receipt does not match the session")


def retain_returned_dataset(
    session: WorkerDatasetSession,
    snapshot: DatabaseSnapshot | None,
    dump: Path | None,
    *,
    runner: mechanics.ProcessRunner,
) -> DatasetReceipt:
    """Restore one verified returned worker snapshot and select it, then rotate older datasets.

    A matching receipt is reused, including a receipt-only retry whose snapshot and dump
    are both absent. A return requires both the snapshot and its dump, retains the dump,
    restores it into the derived server database with the snapshot's verification, and only after
    equality writes the returned receipt, selects it, and rotates older chain-proven datasets.
    """
    settings = load_administrative_dataset_settings()
    root = admin_state_root(settings)
    with mechanics.exclusive_action_lock(root, controller_name="datasets"):
        source, existing_receipt = _resolve_source_and_existing(root, session)
        if session.input_snapshot.database_name != source.database_name:
            raise ValueError("input snapshot database does not match the source dataset")
        if (
            session.input_snapshot.session_id != session.session_id
            or session.input_snapshot.revision != session.revision
        ):
            raise ValueError("input snapshot session identity does not match the session")
        if session.database_name != settings.database_name(session.session_id, worker=True):
            raise ValueError("session worker database name is not the configured derived name")
        server_database = settings.database_name(session.session_id, worker=False)

        if existing_receipt is not None:
            require_returned_dataset_receipt(
                existing_receipt, session, server_database=server_database
            )
            _write_pointer(root, existing_receipt.dataset_id)
            _rotate_locked(settings, root, runner)
            return existing_receipt

        if snapshot is None or dump is None:
            raise ValueError("a new dataset return requires the snapshot and its dump")
        if snapshot.session_id != session.session_id or snapshot.revision != session.revision:
            raise ValueError("returned snapshot session identity does not match the session")
        if snapshot.database_name != session.database_name:
            raise ValueError("returned snapshot database is not the derived worker database")

        retained = _dataset_directory(root, session.session_id) / "database.dump"
        _retain_dump(dump, retained)
        restore_database(
            runner=runner,
            root=repository_root(),
            settings=load_raw_database_settings(),
            dump=retained,
            database_name=server_database,
            expected_sha256=snapshot.dump_sha256,
            include_embeddings=True,
            expected_verification=snapshot.verification,
            timeout=settings.database_operation_timeout_seconds,
        )
        receipt = DatasetReceipt(
            schema_version=1,
            dataset_id=session.session_id,
            database_name=server_database,
            predecessor_id=source.dataset_id,
            kind="returned",
            revision=session.revision,
            dump_sha256=snapshot.dump_sha256,
            verification=snapshot.verification,
        )
        _write_receipt(root, receipt)
        _write_pointer(root, receipt.dataset_id)
        _rotate_locked(settings, root, runner)
        return receipt


def _walk_chain(root: Path) -> list[DatasetReceipt]:
    """Walk and validate the whole selected receipt chain before any deletion."""
    current = resolve_selected_dataset(root)
    chain = [current]
    seen = {current.dataset_id}
    node = current
    while node.predecessor_id is not None:
        if node.kind != "returned":
            raise ValueError("only a returned dataset receipt may name a predecessor")
        parent = _read_required_receipt(root, node.predecessor_id)
        if parent.dataset_id in seen:
            raise ValueError("dataset receipt chain contains a cycle")
        seen.add(parent.dataset_id)
        chain.append(parent)
        node = parent
    terminus = chain[-1]
    if terminus.kind != "initial" or terminus.dataset_id != _INITIAL_DATASET_ID:
        raise ValueError("dataset receipt chain must terminate at the zero-id initial receipt")
    return chain


def _rotate_locked(
    settings: AdministrativeDatasetSettings, root: Path, runner: mechanics.ProcessRunner
) -> None:
    chain = _walk_chain(root)
    older = chain[2:]
    for receipt in older:
        if receipt.kind == "returned":
            if receipt.database_name != settings.database_name(receipt.dataset_id, worker=False):
                raise ValueError(
                    "older returned dataset database is not the configured derived name"
                )
    raw = load_raw_database_settings()
    for receipt in older:
        require_droppable_database(receipt.database_name)
        runner.run(
            (
                *mechanics.compose_prefix(),
                "exec",
                "-T",
                "db",
                "dropdb",
                "--if-exists",
                "--username",
                raw.postgres_user,
                receipt.database_name,
            ),
            cwd=repository_root(),
            timeout=settings.database_operation_timeout_seconds,
        )
        dump_path = _dataset_directory(root, receipt.dataset_id) / "database.dump"
        if dump_path.is_symlink() or (dump_path.exists() and not dump_path.is_file()):
            raise ValueError("older retained dataset dump must be a regular non-symlink file")
        dump_path.unlink(missing_ok=True)
