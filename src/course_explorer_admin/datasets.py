"""Sole writer of dataset receipts and role pointers and owner of server dataset deletion.

Initial setup enrolls the configured database as Selected, and the explicit role commands apply the
migration head to a named dataset or to the configured bootstrap database. A verified return or an
explicit copy creates a new dataset receipt and publishes the Working pointer. An explicit promotion
copies, builds, verifies, switches, restarts and proves Selected, restoring the previous selection
when that switch or proof fails. Rotation after a return retains both role datasets with their
immediate predecessors and drops chain-proven older Working databases and their confined dumps.
Explicit cleanup removes one receipt-bearing dataset's database, dump and derived artifact
namespace, keeping its receipt. It is the only module that writes a receipt or role pointer and the
only one that drops a server dataset database. Lock ownership is shared within this package so
rotation does not nest the action lock.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import httpx
from pydantic import BaseModel, ConfigDict, TypeAdapter, ValidationError

from course_explorer import administration
from course_explorer.administration import (
    administrative_json,
    atomic_write_private_text,
    load_private_model,
    session_directory,
)
from course_explorer.config import (
    AdministrativeDatasetSettings,
    DatabaseSettings,
    embedding_configuration_for_site,
    load_administrative_dataset_settings,
    load_local_lifecycle_settings,
    load_raw_database_settings,
    load_web_settings,
)
from course_explorer.datasets import (
    _INITIAL_DATASET_ID,
    DatabaseSnapshot,
    DatasetDatabaseName,
    DatasetId,
    DatasetPointer,
    DatasetReceipt,
    DatasetRole,
    DatasetVerification,
    clear_dataset_cache,
    dataset_pointer_path,
    dataset_state_refusal,
    has_dataset_enrollment_records,
    read_dataset_receipt,
    read_dataset_role,
    read_dataset_verification,
    require_database_schema,
    require_selected_dataset_root,
    resolve_dataset_role,
)
from course_explorer.db.session import create_database_engine
from course_explorer.serving_artifacts import (
    CATALOGUE_FILE,
    catalogue_body,
    serving_artifact_root,
    serving_database_root,
    serving_key,
)
from course_explorer.serving_build import (
    build_serving_artifacts,
    dataset_settings,
    remove_serving_database_artifacts,
    require_removable_serving_database_artifacts,
)
from course_explorer_admin import mechanics
from course_explorer_admin.snapshots import (
    database_exists,
    dump_database,
    existing_databases,
    restore_database,
)

if TYPE_CHECKING:
    from course_explorer_admin.lifecycle import StageName
    from course_explorer_admin.remote import WorkerDatasetSession

# The four stage roots one guarded dataset action observes, in the order the inventory reports them.
_STAGE_NAMES: tuple[StageName, ...] = ("ingestion", "embedding", "translation", "inference")

# The coarse steps one promotion reports before each mutation, and its rollback before restoring.
PromotionStep = Literal["copy", "build", "switch", "restart", "prove", "rollback"]

_PROTECTED_DATABASES = frozenset(
    {
        "postgres",
        "template0",
        "template1",
        "course_explorer_test",
        "course_explorer_translation_worker_proof",
    }
)

_DATASET_ID_ADAPTER = TypeAdapter(DatasetId)
_DATABASE_NAME_ADAPTER = TypeAdapter(DatasetDatabaseName)


class _CleanupModel(BaseModel):
    """Frozen, closed DTO base for the explicit dataset cleanup contract."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class DatasetListEntry(_CleanupModel):
    """One receipt-bearing dataset, described by receipt, role and file facts."""

    dataset_id: DatasetId
    kind: Literal["initial", "returned", "copied"]
    database_name: DatasetDatabaseName
    predecessor_id: DatasetId | None
    receipt_schema_revision: str
    dump_path: str | None
    selected: bool
    working: bool
    database_presence: Literal["present", "absent", "unavailable"]
    artifacts_present: bool


class DatasetListReport(_CleanupModel):
    """One listing of every receipt-bearing dataset with its role and resource facts.

    ``mode`` is ``unavailable`` when the dataset state tree is redirected or not a directory, which
    makes the listing read none of it.
    """

    schema_version: Literal[1] = 1
    datasets: tuple[DatasetListEntry, ...]
    mode: Literal["bootstrap", "enrolled", "unavailable"]
    database_probe: Literal["available", "unavailable"]
    bootstrap_database: DatasetDatabaseName | None
    stage_busy: dict[str, bool]


class DatasetDeletionReport(_CleanupModel):
    """One explicit deletion of a single non-selected dataset."""

    schema_version: Literal[1] = 1
    dataset_id: DatasetId
    database_name: DatasetDatabaseName


def admin_state_path(settings: AdministrativeDatasetSettings) -> Path:
    """Return the repository-relative admin state root before any guard or action lock."""
    return administration.repository_root() / settings.admin_state_root


def admin_state_root(settings: AdministrativeDatasetSettings) -> Path:
    """Resolve the repository-relative admin state root and refuse the backups boundary.

    The shared read-only state guard runs first, before any action lock is created, so a symlinked
    root, collection, or lock can never redirect a dump, restore, rotation, or receipt/pointer write
    into ``data/backups`` or another location.
    """
    repository = administration.repository_root()
    root = admin_state_path(settings)
    require_selected_dataset_root(root)
    backups = (repository / "data" / "backups").resolve()
    resolved = root.resolve()
    if resolved == backups or backups in resolved.parents:
        raise ValueError("admin state root must not be inside data/backups")
    return root


def _dataset_directory(root: Path, dataset_id: str) -> Path:
    """Return one confined dataset directory of a root the caller already guarded."""
    return session_directory(root / "datasets", dataset_id)


def retained_dump_path(root: Path, dataset_id: str) -> Path:
    """Return the one confined retained dump path for a dataset identity."""
    return _dataset_directory(root, dataset_id) / "database.dump"


def _write_receipt(root: Path, receipt: DatasetReceipt) -> None:
    directory = _dataset_directory(root, receipt.dataset_id)
    directory.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    directory.mkdir(mode=0o700, exist_ok=True)
    atomic_write_private_text(directory / "receipt.json", administrative_json(receipt))


def _write_pointer(root: Path, role: DatasetRole, dataset_id: str) -> None:
    """Publish one role pointer atomically and drop its memoized receipt."""
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    atomic_write_private_text(
        dataset_pointer_path(root, role),
        administrative_json(DatasetPointer(schema_version=1, dataset_id=dataset_id)),
    )
    clear_dataset_cache(role)


def _clear_working_pointer(root: Path) -> None:
    """Remove the Working pointer after a successful Working deletion."""
    pointer = dataset_pointer_path(root, "working")
    if pointer.is_symlink() or (pointer.exists() and not pointer.is_file()):
        raise ValueError("Working dataset pointer must be a regular non-symlink file")
    pointer.unlink(missing_ok=True)
    clear_dataset_cache("working")


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


def _receipt_index(root: Path) -> dict[str, DatasetReceipt]:
    """Read every receipt-bearing dataset directory once for one action."""
    datasets = root / "datasets"
    if not datasets.exists():
        return {}
    if datasets.is_symlink() or not datasets.is_dir():
        raise ValueError("dataset collection must be a regular directory")
    receipts: dict[str, DatasetReceipt] = {}
    for directory in sorted(datasets.iterdir()):
        if directory.is_symlink() or not directory.is_dir():
            raise ValueError("dataset collection must hold only regular directories")
        try:
            identity = _DATASET_ID_ADAPTER.validate_python(directory.name)
        except ValidationError as exc:
            raise ValueError("dataset directory name must be a dataset id") from exc
        receipt_path = directory / "receipt.json"
        if receipt_path.is_symlink():
            raise ValueError("dataset receipt must not be a symlink")
        if not receipt_path.exists():
            continue
        receipt = load_private_model(receipt_path, DatasetReceipt)
        if receipt.dataset_id != identity:
            raise ValueError("dataset receipt identity does not match its directory")
        receipts[identity] = receipt
    return receipts


def require_droppable_database(database_name: str) -> None:
    """Refuse to drop a protected database name."""
    if database_name in _PROTECTED_DATABASES:
        raise ValueError("refuse to drop a protected database")


def _retain_dump(source: Path, destination: Path) -> None:
    """Copy one returned dump to its confined retention path, reusing a present file.

    An existing retained file is returned as it is, and the following restore validates its bytes
    against the supplied snapshot digest.
    """
    destination.parent.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    destination.parent.mkdir(mode=0o700, exist_ok=True)
    if destination.is_symlink() or (destination.exists() and not destination.is_file()):
        raise ValueError("retained dataset dump must be a regular non-symlink file")
    if source == destination:
        return
    if destination.exists():
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


def _run_migration_upgrade(database_name: str) -> None:
    """Apply the Alembic head to one explicitly named database on a caller-owned connection."""
    from alembic import command
    from alembic.config import Config as AlembicConfig

    settings = load_raw_database_settings().model_copy(update={"postgres_db": database_name})
    engine = create_database_engine(settings)
    try:
        with engine.connect() as connection:
            config = AlembicConfig(str(administration.repository_root() / "alembic.ini"))
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
    finally:
        engine.dispose()


def stage_is_busy(stage: StageName) -> bool:
    """Report whether one stage root is non-idle or records a live process.

    Absent state is idle. The destructive Working guards and the dataset inventory read this one
    predicate, so the console's busy observation and the owner's refusal cannot disagree.
    """
    from course_explorer_admin import lifecycle

    state = lifecycle.read_lifecycle_state(lifecycle.stage_state_root(stage))
    if state is None:
        return False
    if state.lifecycle != "idle":
        return True
    return state.process is not None and mechanics.owned_process_is_alive(state.process)


def _require_stage_idle(stage: StageName) -> None:
    """Refuse when one stage is busy."""
    if stage_is_busy(stage):
        raise ValueError(f"stage {stage} is not idle; ordinary-stop it before this action")


def require_stages_idle() -> None:
    """Refuse unless all four stage roots are absent or idle with no live recorded process.

    It is the one shared server-local idle guard: the guarded Working migration, the copy to
    Working and the operator disposition surface all call it, so a protected mutation runs only
    when every stage is idle.
    """
    for stage in _STAGE_NAMES:
        _require_stage_idle(stage)


def _migrate_database(
    settings: AdministrativeDatasetSettings,
    database_name: str,
    *,
    runner: mechanics.ProcessRunner,
) -> DatasetVerification:
    """Apply the Alembic head to one named database as explicit maintenance.

    The server ``db`` service must already be running, and the upgrade runs in this command's
    interpreter on a caller-owned connection. The caller owns the role-specific idle guard. Failure
    preserves data and files and propagates.
    """
    running = mechanics.running_compose_services(
        lambda argv: runner.run(tuple(argv), cwd=administration.repository_root()).stdout,
        interpreter=True,
    )
    if "db" not in running:
        raise RuntimeError("the server db service must already be running")
    _run_migration_upgrade(database_name)
    raw = load_raw_database_settings()
    return read_dataset_verification(raw.model_copy(update={"postgres_db": database_name}))


def migrate_dataset(role: DatasetRole, *, runner: mechanics.ProcessRunner) -> DatasetVerification:
    """Apply the Alembic head to one role's dataset as explicit maintenance.

    It resolves the named role under the action lock. A Working migration requires every stage
    idle before it can apply, and a Selected migration does not. Neither rewrites a receipt or
    changes a pointer.
    """
    settings = load_administrative_dataset_settings()
    root = admin_state_root(settings)
    with mechanics.exclusive_action_lock(root, controller_name="datasets"):
        receipt = resolve_dataset_role(root, role)
        if role == "working":
            require_stages_idle()
        return _migrate_database(settings, receipt.database_name, runner=runner)


def migrate_configured_database(*, runner: mechanics.ProcessRunner) -> DatasetVerification:
    """Apply the Alembic head to the configured database of a bootstrap deployment.

    It refuses a root that resolves a Selected dataset, so an enrolled deployment migrates through
    its explicit role. It runs the same shared migration path against the configured database.
    """
    settings = load_administrative_dataset_settings()
    root = admin_state_root(settings)
    with mechanics.exclusive_action_lock(root, controller_name="datasets"):
        if read_dataset_role(root, "selected") is not None:
            raise ValueError("configured database migration refuses an enrolled deployment")
        return _migrate_database(settings, load_raw_database_settings().postgres_db, runner=runner)


def _matching_initial_repair(root: Path, database_name: str) -> DatasetReceipt:
    """Return the sole matching initial receipt that an interrupted enrollment may republish."""
    working_pointer = dataset_pointer_path(root, "working")
    if working_pointer.exists():
        raise ValueError("retained dataset state includes a Working pointer")
    receipt = read_optional_dataset_receipt(root, _INITIAL_DATASET_ID)
    if receipt is None:
        raise ValueError("retained dataset state holds no initial receipt")
    receipts = _receipt_index(root)
    if set(receipts) != {_INITIAL_DATASET_ID}:
        raise ValueError("retained dataset state holds more than one enrolled dataset")
    if (
        receipt.kind != "initial"
        or receipt.dataset_id != _INITIAL_DATASET_ID
        or receipt.database_name != database_name
    ):
        raise ValueError("retained initial dataset receipt does not match this setup")
    sessions = root / "sessions"
    if sessions.is_dir() and any(
        (directory / "session.json").exists() for directory in sessions.iterdir()
    ):
        raise ValueError("retained dataset state includes a recorded session")
    return receipt


def _initialize_selected_dataset_locked(
    settings: AdministrativeDatasetSettings,
    root: Path,
    database_name: str,
    *,
    runner: mechanics.ProcessRunner,
) -> DatasetReceipt:
    """Enroll one database as the initial Selected dataset under the dataset action lock.

    An already-selected dataset is reused. An enrollment interrupted after the initial receipt but
    before the pointer is republished from that retained receipt alone when it is the sole enrolled
    dataset, matches the supplied database and leaves no Working pointer or recorded session. Any
    other retained state fails rather than being enrolled over. New enrollment migrates the named
    database to the repository head and publishes the zero-id receipt then Selected, with Working
    absent. The caller owns the action lock.
    """
    pointer = dataset_pointer_path(root, "selected")
    if pointer.exists() or pointer.is_symlink():
        return resolve_dataset_role(root, "selected")
    raw = load_raw_database_settings()
    working_pointer = dataset_pointer_path(root, "working")
    if has_dataset_enrollment_records(root) or working_pointer.exists():
        retained = _matching_initial_repair(root, database_name)
        _write_pointer(root, "selected", retained.dataset_id)
        return retained
    require_droppable_database(database_name)
    timeout = settings.database_operation_timeout_seconds
    mechanics.ensure_prepared_services(
        lambda argv: (
            runner.run(tuple(argv), cwd=administration.repository_root(), timeout=timeout).stdout
        ),
        ("db",),
        interpreter=True,
    )
    _run_migration_upgrade(database_name)
    receipt = DatasetReceipt(
        schema_version=1,
        dataset_id=_INITIAL_DATASET_ID,
        database_name=database_name,
        predecessor_id=None,
        kind="initial",
        dump_sha256=None,
        verification=read_dataset_verification(
            raw.model_copy(update={"postgres_db": database_name})
        ),
    )
    _write_receipt(root, receipt)
    _write_pointer(root, "selected", receipt.dataset_id)
    return receipt


def initialize_selected_dataset(*, runner: mechanics.ProcessRunner) -> DatasetReceipt:
    """Select a configured database as the initial selected dataset, once.

    The configured database name is enrolled through the one shared locked initial-enrollment core.
    """
    settings = load_administrative_dataset_settings()
    root = admin_state_root(settings)
    with mechanics.exclusive_action_lock(root, controller_name="datasets"):
        return _initialize_selected_dataset_locked(
            settings, root, load_raw_database_settings().postgres_db, runner=runner
        )


def create_empty_selected_dataset(
    database_name: str, *, runner: mechanics.ProcessRunner
) -> DatasetReceipt:
    """Create one absent named database and enroll it as the initial Selected dataset.

    The external name is validated against the shared dataset-name type and the protected-name
    owner. A state root that holds any pointer or enrollment record, the configured example name and
    an existing target database each refuse before mutation. The absent database is created from
    ``template0`` through the configured Compose service, then the shared locked initial-enrollment
    core migrates, verifies and publishes the zero-id receipt and Selected. A failed create or
    migration preserves anything it created for explicit maintenance.
    """
    try:
        name = _DATABASE_NAME_ADAPTER.validate_python(database_name)
    except ValidationError as exc:
        raise ValueError(
            "dataset database name must be a lowercase SQL identifier of at most 63 characters"
        ) from exc
    require_droppable_database(name)
    settings = load_administrative_dataset_settings()
    root = admin_state_root(settings)
    with mechanics.exclusive_action_lock(root, controller_name="datasets"):
        selected_pointer = dataset_pointer_path(root, "selected")
        working_pointer = dataset_pointer_path(root, "working")
        if (
            selected_pointer.exists()
            or selected_pointer.is_symlink()
            or working_pointer.exists()
            or working_pointer.is_symlink()
            or has_dataset_enrollment_records(root)
        ):
            raise ValueError(
                "named initial enrollment requires a state root with no dataset pointers or records"
            )
        raw = load_raw_database_settings()
        if name == raw.example_postgres_db:
            raise ValueError("the configured example database cannot be enrolled as a dataset")
        timeout = settings.database_operation_timeout_seconds
        if database_exists(
            runner=runner,
            root=administration.repository_root(),
            settings=raw,
            database_name=name,
            timeout=timeout,
        ):
            raise ValueError("the requested initial dataset database already exists")
        runner.run(
            (
                *mechanics.compose_prefix(interpreter=True),
                "exec",
                "-T",
                "db",
                "createdb",
                "--username",
                raw.postgres_user,
                "--template",
                "template0",
                name,
            ),
            cwd=administration.repository_root(),
            timeout=timeout,
        )
        return _initialize_selected_dataset_locked(settings, root, name, runner=runner)


def ensure_selected_dataset(*, runner: mechanics.ProcessRunner) -> DatasetReceipt | None:
    """Enroll the configured database as Selected unless it is the configured example database.

    It first reads the ordinary Selected role: a valid Selected is reused and an inconsistent
    enrollment raises. Only a bootstrap root compares the configured database with the configured
    example name, and a non-example name enrolls through the explicit owner. It performs no
    interrupted-enrollment repair.
    """
    settings = load_administrative_dataset_settings()
    root = admin_state_root(settings)
    existing = read_dataset_role(root, "selected")
    if existing is not None:
        return existing
    raw = load_raw_database_settings()
    if raw.postgres_db == raw.example_postgres_db:
        return None
    return initialize_selected_dataset(runner=runner)


def _resolve_source_and_existing(
    root: Path, session: WorkerDatasetSession
) -> tuple[DatasetReceipt, DatasetReceipt | None]:
    """Return the session's source receipt and any returned receipt for this session."""
    current = resolve_dataset_role(root, "working")
    if current.dataset_id == session.session_id:
        if current.kind != "returned" or current.predecessor_id != session.source_dataset_id:
            raise ValueError("Working dataset is not this session's returned dataset")
        return _read_required_receipt(root, session.source_dataset_id), current
    if current.dataset_id == session.source_dataset_id:
        return current, read_optional_dataset_receipt(root, session.session_id)
    raise ValueError("Working dataset is neither the session source nor its returned dataset")


def require_returned_dataset_receipt(
    receipt: DatasetReceipt, session: WorkerDatasetSession, *, server_database: str
) -> None:
    """Require one returned receipt to describe exactly this session's returned dataset."""
    if (
        receipt.kind != "returned"
        or receipt.dataset_id != session.session_id
        or receipt.database_name != server_database
        or receipt.predecessor_id != session.source_dataset_id
    ):
        raise ValueError("existing returned dataset receipt does not match the session")


def retain_returned_dataset(
    session: WorkerDatasetSession,
    snapshot: DatabaseSnapshot | None,
    dump: Path | None,
    *,
    runner: mechanics.ProcessRunner,
) -> DatasetReceipt:
    """Restore one verified returned worker snapshot, assign it to Working, then rotate.

    A matching receipt is reused, including a receipt-only retry whose snapshot and dump
    are both absent. A return requires both the snapshot and its dump, retains the dump,
    restores it into the derived server database with the snapshot's verification, and only after
    equality writes the returned receipt, assigns Working, and rotates older Working ancestors.
    """
    settings = load_administrative_dataset_settings()
    root = admin_state_root(settings)
    with mechanics.exclusive_action_lock(root, controller_name="datasets"):
        source, existing_receipt = _resolve_source_and_existing(root, session)
        if session.input_snapshot.database_name != source.database_name:
            raise ValueError("input snapshot database does not match the source dataset")
        if session.input_snapshot.session_id != session.session_id:
            raise ValueError("input snapshot session identity does not match the session")
        if session.database_name != settings.database_name(session.session_id, worker=True):
            raise ValueError("session worker database name is not the configured derived name")
        server_database = settings.database_name(session.session_id, worker=False)

        if existing_receipt is not None:
            require_returned_dataset_receipt(
                existing_receipt, session, server_database=server_database
            )
            _write_pointer(root, "working", existing_receipt.dataset_id)
            _rotate_locked(settings, root, runner)
            return existing_receipt

        if snapshot is None or dump is None:
            raise ValueError("a new dataset return requires the snapshot and its dump")
        if snapshot.session_id != session.session_id:
            raise ValueError("returned snapshot session identity does not match the session")
        if snapshot.database_name != session.database_name:
            raise ValueError("returned snapshot database is not the derived worker database")

        retained = retained_dump_path(root, session.session_id)
        _retain_dump(dump, retained)
        restore_database(
            runner=runner,
            root=administration.repository_root(),
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
            dump_sha256=snapshot.dump_sha256,
            verification=snapshot.verification,
        )
        _write_receipt(root, receipt)
        _write_pointer(root, "working", receipt.dataset_id)
        _rotate_locked(settings, root, runner)
        return receipt


def _copy_dataset_locked(
    settings: AdministrativeDatasetSettings,
    root: Path,
    source_dataset_id: str,
    runner: mechanics.ProcessRunner,
) -> DatasetReceipt:
    """Create one verified, unassigned copy of an enrolled source dataset.

    The source receipt must name an owned database. Its current schema head is read before a single
    dump, and the fresh derived database is restored from that dump. The restored database's own
    verification supplies the receipt, which names the source as predecessor. The caller owns the
    action lock and any role assignment.
    """
    source = _read_required_receipt(root, _require_dataset_id(source_dataset_id))
    _require_dataset_database_name(settings, source)
    raw = load_raw_database_settings()
    source_settings = raw.model_copy(update={"postgres_db": source.database_name})
    # The source's schema head is required before the copy mutates any resource.
    engine = create_database_engine(source_settings)
    try:
        with engine.connect() as connection:
            require_database_schema(connection)
    finally:
        engine.dispose()
    dataset_id = uuid.uuid4().hex
    database_name = settings.database_name(dataset_id, worker=False)
    directory = _dataset_directory(root, dataset_id)
    directory.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    directory.mkdir(mode=0o700, exist_ok=True)
    dump = retained_dump_path(root, dataset_id)
    digest = dump_database(
        runner=runner,
        root=administration.repository_root(),
        settings=source_settings,
        destination=dump,
        include_embeddings=True,
        timeout=settings.database_operation_timeout_seconds,
    )
    restored_settings = raw.model_copy(update={"postgres_db": database_name})
    restore_database(
        runner=runner,
        root=administration.repository_root(),
        settings=raw,
        dump=dump,
        database_name=database_name,
        expected_sha256=None,
        include_embeddings=True,
        expected_verification=None,
        timeout=settings.database_operation_timeout_seconds,
    )
    receipt = DatasetReceipt(
        schema_version=1,
        dataset_id=dataset_id,
        database_name=database_name,
        predecessor_id=source.dataset_id,
        kind="copied",
        dump_sha256=digest,
        verification=read_dataset_verification(restored_settings),
    )
    _write_receipt(root, receipt)
    return receipt


def copy_to_working(source_dataset_id: str, *, runner: mechanics.ProcessRunner) -> DatasetReceipt:
    """Copy one enrolled source dataset and publish the unassigned copy as Working.

    Every stage must be idle before any copy mutation. The source may be Selected, Working or any
    retained dataset whose database is present. The verified copy receives its own identity and
    database, no artifact bytes are read or written, and Working is published last.
    """
    settings = load_administrative_dataset_settings()
    root = admin_state_root(settings)
    with mechanics.exclusive_action_lock(root, controller_name="datasets"):
        require_stages_idle()
        receipt = _copy_dataset_locked(settings, root, source_dataset_id, runner)
        _write_pointer(root, "working", receipt.dataset_id)
        return receipt


def read_serving_identity(client: httpx.Client, port: int) -> str:
    """Read one running site's dataset identity through its feature report."""
    response = client.post(f"http://127.0.0.1:{port}/api/features", json={})
    response.raise_for_status()
    identity = response.json().get("dataset_identity")
    if not isinstance(identity, str) or not identity:
        raise ValueError("the feature report must carry a nonempty dataset identity")
    return identity


def prove_serving_database(
    settings: DatabaseSettings, *, previous_identity: str | None, port: int
) -> None:
    """Prove one database's catalogue and identity through its restarted site.

    The helper reads the settings' own catalogue artifact once and posts the site's two serving
    reads until the observed catalogue body equals that artifact with the reported identity
    appended. Absent connection and read timeouts mean the restarted process is not ready.
    Every other HTTP, parse or content error fails. ``previous_identity`` requires the observed
    identity to differ from it. ``None`` drops that condition, so a rollback proves the previous
    catalogue alone.
    """
    catalogue_artifact = (
        serving_artifact_root(
            administration.repository_root() / settings.admin_state_root, serving_key(settings)
        )
        / "current"
        / CATALOGUE_FILE
    )
    artifact_bytes = catalogue_artifact.read_bytes()
    lifecycle = load_local_lifecycle_settings()

    def read(client: httpx.Client) -> tuple[str, bool] | None:
        try:
            identity = read_serving_identity(client, port)
            catalogue = client.post(
                f"http://127.0.0.1:{port}/api/catalogue",
                json={},
                headers={"Accept-Encoding": "identity"},
            )
            catalogue.raise_for_status()
        except httpx.ConnectError, httpx.ReadTimeout:
            return None
        return identity, catalogue.content == catalogue_body(artifact_bytes, identity)

    def accepted(state: tuple[str, bool] | None) -> bool:
        return (
            state is not None
            and state[1]
            and (previous_identity is None or state[0] != previous_identity)
        )

    with httpx.Client(
        trust_env=False,
        timeout=lifecycle.stop_timeout_seconds,
        follow_redirects=False,
    ) as client:
        mechanics.await_state(
            lambda: read(client),
            accepted,
            attempts=lifecycle.startup_attempts,
            interval=lifecycle.poll_interval_seconds,
            sleep=time.sleep,
        )


def prove_serving_dataset(
    receipt: DatasetReceipt, *, previous_identity: str | None, port: int
) -> None:
    """Prove one receipt's catalogue and identity through its restarted site."""
    prove_serving_database(
        dataset_settings(receipt.dataset_id), previous_identity=previous_identity, port=port
    )


def copy_to_selected(
    source_dataset_id: str,
    *,
    confirm_restart: bool = False,
    on_progress: Callable[[PromotionStep], None] | None = None,
    runner: mechanics.ProcessRunner,
) -> DatasetReceipt:
    """Copy one enrolled dataset, build it, switch Selected, and prove the restarted site.

    The confirmation is required before any copy. Under the datasets action lock the previous
    Selected dataset, its served identity and the checkout's own web unit are read before the
    copy is made. The copy is built and verified before the Selected pointer names it, and the site
    is then restarted and proved to serve the copy's artifact and a changed identity.

    ``on_progress`` receives each coarse step immediately before that step's mutation, and
    ``rollback`` once before the previous pointer is restored. A caller that omits it gets the one
    ordinary final receipt.

    A failed build switches nothing and restarts nothing. A failed restart or proof restores the
    previous Selected pointer, restarts the site and proves the previous catalogue and feature
    readiness. The promotion failure is raised again after a successful rollback. A failed
    rollback raises an ``ExceptionGroup`` holding both errors. Every failure keeps the created
    dataset, its dump and its completed artifacts for manual deletion.
    """
    if not confirm_restart:
        raise ValueError("promotion restarts the serving web unit; confirm with --confirm-restart")
    settings = load_administrative_dataset_settings()
    root = admin_state_root(settings)
    with mechanics.exclusive_action_lock(root, controller_name="datasets"):
        previous = resolve_dataset_role(root, "selected")
        # The site unit and its served identity belong to this checkout and are read before the
        # copy, so a promotion cannot switch a unit it does not own or prove an unchanged identity.
        from course_explorer_admin import rebuild, server

        website = server.read_web_service(runner=runner)
        with httpx.Client(
            trust_env=False,
            timeout=load_local_lifecycle_settings().stop_timeout_seconds,
            follow_redirects=False,
        ) as client:
            previous_identity = read_serving_identity(client, website.port)
        _report(on_progress, "copy")
        copy = _copy_dataset_locked(settings, root, source_dataset_id, runner)
        _report(on_progress, "build")
        build_serving_artifacts(
            dataset_settings(copy.dataset_id),
            embedding=embedding_configuration_for_site(load_web_settings()),
        )
        _report(on_progress, "switch")
        _write_pointer(root, "selected", copy.dataset_id)
        try:
            _report(on_progress, "restart")
            rebuild.restart_web(website, runner=runner)
            _report(on_progress, "prove")
            prove_serving_dataset(copy, previous_identity=previous_identity, port=website.port)
        except Exception as error:
            _report(on_progress, "rollback")
            try:
                _write_pointer(root, "selected", previous.dataset_id)
                rebuild.restart_web(website, runner=runner)
                prove_serving_dataset(previous, previous_identity=None, port=website.port)
            except Exception as rollback_error:
                raise ExceptionGroup(
                    "promotion failed and the previous Selected dataset was not restored",
                    [error, rollback_error],
                ) from None
            raise
        return copy


def _report(on_progress: Callable[[PromotionStep], None] | None, step: PromotionStep) -> None:
    """Hand one coarse promotion step to the observer that supplied a callback."""
    if on_progress is not None:
        on_progress(step)


def _walk_chain(receipts: dict[str, DatasetReceipt], start: DatasetReceipt) -> list[DatasetReceipt]:
    """Walk and validate one receipt chain through the action's shared receipt index."""
    chain = [start]
    seen = {start.dataset_id}
    node = start
    while node.predecessor_id is not None:
        if node.kind not in {"returned", "copied"}:
            raise ValueError("only a returned or copied receipt may name a predecessor")
        parent = receipts.get(node.predecessor_id)
        if parent is None:
            raise ValueError("dataset receipt chain predecessor is missing")
        if parent.dataset_id in seen:
            raise ValueError("dataset receipt chain contains a cycle")
        seen.add(parent.dataset_id)
        chain.append(parent)
        node = parent
    terminus = chain[-1]
    if terminus.kind != "initial" or terminus.dataset_id != _INITIAL_DATASET_ID:
        raise ValueError("dataset receipt chain must terminate at the zero-id initial receipt")
    return chain


def _require_dataset_id(dataset_id: str) -> str:
    """Validate one supplied dataset id against the shared dataset identity type.

    A pydantic :class:`ValidationError` selects the configuration guidance at the operator surface,
    so a malformed id is reported as one ``ValueError`` and that surface prints the cleanup guidance
    for it.
    """
    try:
        return _DATASET_ID_ADAPTER.validate_python(dataset_id)
    except ValidationError as exc:
        raise ValueError("dataset id must be 32 lowercase hexadecimal characters") from exc


def _require_dataset_database_name(
    settings: AdministrativeDatasetSettings, receipt: DatasetReceipt
) -> None:
    """Refuse a returned or copied receipt whose database is not its configured derived name.

    An initial receipt carries the name of the configured database, so its own recorded name is
    authoritative and is never compared with the settings.
    """
    if receipt.kind in {"returned", "copied"}:
        if receipt.database_name != settings.database_name(receipt.dataset_id, worker=False):
            raise ValueError(
                "returned or copied dataset database is not the configured derived name"
            )


def _drop_dataset_resources_locked(
    settings: AdministrativeDatasetSettings,
    root: Path,
    receipt: DatasetReceipt,
    runner: mechanics.ProcessRunner,
) -> None:
    """Drop one dataset's server database and remove its dump and artifact namespace.

    The database name is checked against the protected list, and the confined dump and the derived
    artifact namespace are required to be regular owned paths, before the one Compose drop runs. A
    connected database may refuse the drop and that error propagates. The dump and artifact
    namespace are removed only after the database command succeeded, and the receipt, the pointers,
    the dataset directory and the session files stay.
    """
    require_droppable_database(receipt.database_name)
    dump_path = retained_dump_path(root, receipt.dataset_id)
    if dump_path.is_symlink() or (dump_path.exists() and not dump_path.is_file()):
        raise ValueError("retained dataset dump must be a regular non-symlink file")
    namespace = require_removable_serving_database_artifacts(root, receipt.database_name)
    raw = load_raw_database_settings()
    runner.run(
        (
            *mechanics.compose_prefix(interpreter=True),
            "exec",
            "-T",
            "db",
            "dropdb",
            "--if-exists",
            "--username",
            raw.postgres_user,
            receipt.database_name,
        ),
        cwd=administration.repository_root(),
        timeout=settings.database_operation_timeout_seconds,
    )
    dump_path.unlink(missing_ok=True)
    remove_serving_database_artifacts(namespace)


def _rotate_locked(
    settings: AdministrativeDatasetSettings, root: Path, runner: mechanics.ProcessRunner
) -> None:
    """Delete older proven Working ancestors outside both role pairs after a return."""
    selected = resolve_dataset_role(root, "selected")
    working = resolve_dataset_role(root, "working")
    receipts = _receipt_index(root)
    selected_chain = _walk_chain(receipts, selected)
    working_chain = _walk_chain(receipts, working)
    keep = {
        selected.dataset_id,
        *(receipt.dataset_id for receipt in selected_chain[:2]),
        working.dataset_id,
        *(receipt.dataset_id for receipt in working_chain[:2]),
    }
    older = [receipt for receipt in working_chain[2:] if receipt.dataset_id not in keep]
    for receipt in older:
        _require_dataset_database_name(settings, receipt)
    for receipt in older:
        _drop_dataset_resources_locked(settings, root, receipt, runner)


def _retained_dump_path(root: Path, receipt: DatasetReceipt) -> str | None:
    """Return the repository-relative retained dump path of one receipt, or ``None`` when absent."""
    dump_path = retained_dump_path(root, receipt.dataset_id)
    if dump_path.is_symlink() or (dump_path.exists() and not dump_path.is_file()):
        raise ValueError("retained dataset dump must be a regular non-symlink file")
    if not dump_path.exists():
        return None
    return dump_path.relative_to(administration.repository_root()).as_posix()


def _probe_database_names(
    settings: AdministrativeDatasetSettings,
    runner: mechanics.ProcessRunner,
    database_names: tuple[str, ...],
) -> tuple[Literal["available", "unavailable"], frozenset[str]]:
    """Probe every known database once, converting only service unavailability to a typed state."""
    try:
        held = existing_databases(
            runner=runner,
            root=administration.repository_root(),
            settings=load_raw_database_settings(),
            database_names=database_names,
            timeout=settings.database_operation_timeout_seconds,
        )
    except subprocess.CalledProcessError, FileNotFoundError:
        return "unavailable", frozenset()
    return "available", held


def list_retained_datasets(*, runner: mechanics.ProcessRunner) -> DatasetListReport:
    """List receipt-bearing datasets with their role, receipt and resource facts.

    Both roles and every retained branch are discovered from their receipts, so replacing Working
    from another source cannot hide an older manual copy. Role datasets are listed even when their
    resources are missing, and any other dataset is listed when it holds a retained dump, an
    artifact namespace or a present database. Each entry carries its receipt's predecessor and
    recorded migration head and whether its artifact namespace exists. One database probe answers
    every known name after the local facts are read, and a bootstrap root adds the configured
    database to that probe without listing it. Actual process or connection unavailability returns
    a typed unavailable probe with every known receipt listed and every presence unavailable. The
    report also carries the four stage busy facts and, in bootstrap, the configured database the
    site serves directly. A bootstrap root returns an empty role inventory instead of a setup
    failure, and a redirected or non-directory state tree reports the unavailable mode with no
    dataset and the four stage busy facts. The read creates no file, directory or lock.
    """
    settings = load_administrative_dataset_settings()
    if dataset_state_refusal(admin_state_path(settings)) is not None:
        return DatasetListReport(
            datasets=(),
            mode="unavailable",
            database_probe="unavailable",
            bootstrap_database=None,
            stage_busy={stage: stage_is_busy(stage) for stage in _STAGE_NAMES},
        )
    root = admin_state_root(settings)
    raw = load_raw_database_settings()
    selected = read_dataset_role(root, "selected")
    working = read_dataset_role(root, "working")
    receipts = _receipt_index(root)
    selected_chain = _walk_chain(receipts, selected) if selected is not None else []
    working_chain = _walk_chain(receipts, working) if working is not None else []
    ordered: list[DatasetReceipt] = []
    seen: set[str] = set()
    for receipt in (*selected_chain, *working_chain, *(receipts[key] for key in sorted(receipts))):
        if receipt.dataset_id in seen:
            continue
        seen.add(receipt.dataset_id)
        ordered.append(receipt)
    role_ids = {receipt.dataset_id for receipt in (selected, working) if receipt is not None}
    local = {receipt.dataset_id: _retained_dump_path(root, receipt) for receipt in ordered}
    bootstrap_database = None if selected is not None else raw.postgres_db
    probed = tuple(receipt.database_name for receipt in ordered)
    if bootstrap_database is not None:
        probed = (*probed, bootstrap_database)
    probe, held = _probe_database_names(settings, runner, probed)
    entries: list[DatasetListEntry] = []
    for receipt in ordered:
        dump_path = local[receipt.dataset_id]
        is_role = receipt.dataset_id in role_ids
        artifacts_present = serving_database_root(root, receipt.database_name).exists()
        if probe == "unavailable":
            presence: Literal["present", "absent", "unavailable"] = "unavailable"
            included = True
        else:
            presence = "present" if receipt.database_name in held else "absent"
            included = (
                is_role or dump_path is not None or artifacts_present or presence == "present"
            )
        if not included:
            continue
        entries.append(
            DatasetListEntry(
                dataset_id=receipt.dataset_id,
                kind=receipt.kind,
                database_name=receipt.database_name,
                predecessor_id=receipt.predecessor_id,
                receipt_schema_revision=receipt.verification.alembic_revision,
                dump_path=dump_path,
                selected=selected is not None and receipt.dataset_id == selected.dataset_id,
                working=working is not None and receipt.dataset_id == working.dataset_id,
                database_presence=presence,
                artifacts_present=artifacts_present,
            )
        )
    return DatasetListReport(
        datasets=tuple(entries),
        mode="bootstrap" if selected is None else "enrolled",
        database_probe=probe,
        bootstrap_database=bootstrap_database,
        stage_busy={stage: stage_is_busy(stage) for stage in _STAGE_NAMES},
    )


def delete_retained_dataset(
    dataset_id: str, *, confirm_working: bool = False, runner: mechanics.ProcessRunner
) -> DatasetDeletionReport:
    """Delete one named receipt-bearing dataset and keep its receipt.

    The input identity is validated before settings or file work. The owner resolves both roles and
    finds the target receipt again under the action lock. Selected is never deletable by id or
    database name. Working additionally requires the explicit ``confirm_working`` choice and all
    stages idle, and a successful Working deletion clears only the Working pointer. Any
    receipt-bearing branch is a target, including an older manual copy. The owner drops the exact
    database, removes its confined dump and its derived artifact namespace, leaving the receipt,
    every pointer except the cleared Working pointer, the dataset directory and the external backups
    in place. A repeated deletion of absent resources completes with the same report.
    """
    identity = _require_dataset_id(dataset_id)
    settings = load_administrative_dataset_settings()
    root = admin_state_root(settings)
    with mechanics.exclusive_action_lock(root, controller_name="datasets"):
        selected = read_dataset_role(root, "selected")
        working = read_dataset_role(root, "working")
        if selected is None:
            raise ValueError("no Selected dataset is enrolled")
        receipts = _receipt_index(root)
        target = receipts.get(identity)
        if target is None:
            raise ValueError("requested dataset is not an enrolled dataset")
        if target.dataset_id == selected.dataset_id:
            raise ValueError("refuse to delete the Selected dataset")
        if target.database_name == selected.database_name:
            raise ValueError("refuse to delete the Selected database")
        is_working = working is not None and target.dataset_id == working.dataset_id
        if is_working:
            if not confirm_working:
                raise ValueError("refuse to delete the Working dataset without confirmation")
            require_stages_idle()
        _require_dataset_database_name(settings, target)
        _drop_dataset_resources_locked(settings, root, target, runner)
        if is_working:
            _clear_working_pointer(root)
        return DatasetDeletionReport(
            dataset_id=target.dataset_id, database_name=target.database_name
        )
