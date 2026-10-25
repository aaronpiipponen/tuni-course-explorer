"""Worker-side selected dataset session core, neutral worker control DTO, and its confined CLI.

One immutable :class:`WorkerDatasetSession` names the selected source dataset, the derived worker
database, and the full input snapshot. The neutral :class:`WorkerControl`
is the one cooperative control-intent record shared by the stage controllers. The server creates the
session and dumps the selected dataset. The worker prepares the derived database from that dump,
exports a verified full return snapshot, and the server returns it through the sole retention writer
in ``course_explorer_admin.datasets``. A returned worker database is dropped only through
``cleanup_returned_worker_database`` after both the server dataset receipt and the recorded return
snapshot agree. This module exposes the ``prepare``/``export``/``cleanup`` subcommands.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    computed_field,
    field_validator,
    model_validator,
)

from course_explorer.administration import (
    administrative_json,
    atomic_write_private_text,
    load_private_model,
    repository_root,
    session_directory,
    sha256_file,
)
from course_explorer.config import (
    AdministrativeDatasetSettings,
    WorkerConnectionSettings,
    load_administrative_dataset_settings,
    load_database_settings,
    load_raw_database_settings,
    load_worker_connection_settings,
)
from course_explorer.datasets import (
    DatabaseSnapshot,
    DatasetDatabaseName,
    DatasetId,
    DatasetReceipt,
    DatasetVerification,
    read_dataset_verification,
    resolve_selected_dataset,
)
from course_explorer.validation import require_error_type, require_finite_nonnegative
from course_explorer_admin import mechanics
from course_explorer_admin.datasets import (
    admin_state_root,
    read_optional_dataset_receipt,
    require_droppable_database,
    require_returned_dataset_receipt,
    retain_returned_dataset,
    retained_dump_path,
)
from course_explorer_admin.snapshots import dump_database, restore_database

if TYPE_CHECKING:
    from course_explorer_admin.transport import SshWslTransport

_STAGE = Literal["translation", "inference"]

_SESSION_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")


class _ControllerModel(BaseModel):
    """Frozen, closed DTO base for the text-free worker-controller contracts."""

    model_config = ConfigDict(extra="forbid", frozen=True)


def _require_session_id(value: str) -> str:
    if _SESSION_ID_PATTERN.fullmatch(value) is None:
        raise ValueError("session id must be 32 lowercase hexadecimal characters")
    return value


class WorkerControllerStatus(_ControllerModel):
    """Text-free stage-neutral operator status with derived remaining count, rate, and ETA.

    ``idle`` marks an absent session, which differs from complete coverage: a stopped partial
    session carries partial counts with its terminal lifecycle. Session identity is present for
    every non-idle lifecycle and absent only for idle. The top-level desired/completed counts
    are the owning stage's eligible/retained counts, never pools, skips, or attempts.
    """

    session_id: str | None = None
    lifecycle: Literal[
        "idle",
        "prepared",
        "starting",
        "running",
        "paused",
        "interrupted",
        "stopped",
        "completed",
        "failed",
        "cleaned",
        "imported",
    ]
    course_limit: int | None = Field(default=None, gt=0)
    desired_count: int | None = Field(default=None, ge=0)
    completed_count: int | None = Field(default=None, ge=0)
    active_seconds: float
    error_type: str | None = None
    reboot_due: bool = False

    @field_validator("session_id")
    @classmethod
    def validate_session_id(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return _require_session_id(value)

    @field_validator("error_type")
    @classmethod
    def validate_error_type(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return require_error_type(value, max_length=64)

    @field_validator("active_seconds")
    @classmethod
    def validate_active_seconds(cls, value: float) -> float:
        return require_finite_nonnegative(value, "active_seconds")

    @model_validator(mode="before")
    @classmethod
    def drop_derived_fields(cls, values: object) -> object:
        """Ignore derived status fields when strictly reloading a printed status."""
        if isinstance(values, Mapping):
            return {
                key: value
                for key, value in values.items()
                if key
                not in {
                    "remaining_count",
                    "items_per_second",
                    "projected_remaining_seconds",
                }
            }
        return values

    @model_validator(mode="after")
    def validate_counts(self) -> WorkerControllerStatus:
        if (
            self.desired_count is not None
            and self.completed_count is not None
            and self.completed_count > self.desired_count
        ):
            raise ValueError("completed_count must not exceed desired_count")
        if self.session_id is None:
            if self.lifecycle != "idle":
                raise ValueError("only idle status may omit session identity")
        return self

    @computed_field
    @property
    def remaining_count(self) -> int | None:
        """Derive the remaining desired-item count, or ``None`` when unknown."""
        if self.desired_count is None or self.completed_count is None:
            return None
        return self.desired_count - self.completed_count

    @computed_field
    @property
    def items_per_second(self) -> float | None:
        """Derive measured throughput once the desired, completed, and active-time inputs are known.

        An unknown desired count makes throughput unknown too, and an unknown completed count can
        never be turned into a measured rate.
        """
        if (
            self.desired_count is None
            or self.completed_count is None
            or self.completed_count <= 0
            or self.active_seconds <= 0
        ):
            return None
        return self.completed_count / self.active_seconds

    @computed_field
    @property
    def projected_remaining_seconds(self) -> float | None:
        """Derive remaining seconds from measured throughput, zero for terminal states.

        Unknown counts are reported as unknown: the terminal zero-ETA shortcut applies only once both
        counts are genuinely known.
        """
        if self.desired_count is None or self.completed_count is None:
            return None
        if self.lifecycle in {"completed", "imported"}:
            return 0.0
        rate = self.items_per_second
        if rate is None:
            return None
        remaining = self.desired_count - self.completed_count
        return remaining / rate


class WorkerDatasetSession(BaseModel):
    """Frozen, closed identity of one prepared worker dataset session."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    session_id: DatasetId
    database_name: DatasetDatabaseName
    stage: Literal["translation", "inference"]
    source_dataset_id: DatasetId
    course_limit: int | None = Field(default=None, gt=0)
    input_snapshot: DatabaseSnapshot


class WorkerControl(BaseModel):
    """One requested cooperative control action for a running worker session.

    This is control intent only, never work/checkpoint authority: it carries the exact session
    identity and one requested action, with no progress, text, path, host, or credential.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1]
    session_id: DatasetId
    requested_action: Literal["run", "pause", "stop"]


def _session_directory(settings: AdministrativeDatasetSettings, session_id: str) -> Path:
    """Return the confined local session directory under the configured admin state root."""
    root = admin_state_root(settings)
    return session_directory(root / "sessions", session_id)


def worker_dataset_session_directory(session_id: str) -> Path:
    """Return the one canonical shared session directory for a validated session id."""
    return _session_directory(load_administrative_dataset_settings(), session_id)


def remote_worker_session_directory(
    connection: WorkerConnectionSettings, session_id: str
) -> PurePosixPath:
    """Return the worker-side session directory as a POSIX path under the configured project root.

    This is the one owner of the remote path expression: it builds the remote path from the
    configured project root, the admin state root and the session identity. The caller supplies
    the already-validated session identity.
    """
    settings = load_administrative_dataset_settings()
    return PurePosixPath(
        str(connection.worker_project_root / settings.admin_state_root / "sessions" / session_id)
    )


def _require_session_identity(
    session: WorkerDatasetSession, settings: AdministrativeDatasetSettings
) -> None:
    if session.database_name != settings.database_name(session.session_id, worker=True):
        raise ValueError("session worker database name is not the configured derived name")


def load_worker_dataset_session(session_id: str) -> WorkerDatasetSession:
    """Load one recorded canonical worker dataset session from its confined directory."""
    settings = load_administrative_dataset_settings()
    directory = _session_directory(settings, session_id)
    recorded = load_private_model(directory / "session.json", WorkerDatasetSession)
    if recorded.session_id != session_id:
        raise ValueError("session file identity does not match the requested session")
    return recorded


def create_worker_dataset_session(
    stage: _STAGE,
    *,
    session_id: str,
    course_limit: int | None = None,
    runner: mechanics.ProcessRunner,
) -> WorkerDatasetSession:
    """Snapshot the selected dataset into one fresh worker session."""
    settings = load_administrative_dataset_settings()
    root = admin_state_root(settings)
    with mechanics.exclusive_action_lock(root, controller_name="datasets"):
        database = load_database_settings()
        source = resolve_selected_dataset(root)
        if database.postgres_db != source.database_name:
            raise ValueError("resolved database does not match the selected dataset")
        directory = session_directory(root / "sessions", session_id)
        directory.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        for name in ("session.json", "input.dump"):
            existing = directory / name
            if existing.exists() or existing.is_symlink():
                raise ValueError("canonical worker session evidence already exists")
        input_dump = directory / "input.dump"
        dump_sha256 = dump_database(
            runner=runner,
            root=repository_root(),
            settings=database,
            destination=input_dump,
            include_embeddings=True,
            timeout=settings.database_operation_timeout_seconds,
        )
        session = WorkerDatasetSession(
            schema_version=1,
            session_id=session_id,
            database_name=settings.database_name(session_id, worker=True),
            stage=stage,
            source_dataset_id=source.dataset_id,
            course_limit=course_limit,
            input_snapshot=DatabaseSnapshot(
                schema_version=1,
                session_id=session_id,
                database_name=database.postgres_db,
                dump_sha256=dump_sha256,
                verification=read_dataset_verification(database),
            ),
        )
        atomic_write_private_text(directory / "session.json", administrative_json(session))
        return session


def prepare_worker_database(
    session: WorkerDatasetSession, *, runner: mechanics.ProcessRunner
) -> DatasetVerification:
    """Restore the uploaded full input snapshot into the derived worker database."""
    settings = load_administrative_dataset_settings()
    root = admin_state_root(settings)
    with mechanics.exclusive_action_lock(root, controller_name="datasets"):
        recorded = load_worker_dataset_session(session.session_id)
        if recorded != session:
            raise ValueError("uploaded session file does not match the requested session")
        _require_session_identity(session, settings)
        directory = _session_directory(settings, session.session_id)
        dump = directory / "input.dump"
        verification = restore_database(
            runner=runner,
            root=repository_root(),
            settings=load_raw_database_settings(),
            dump=dump,
            database_name=session.database_name,
            expected_sha256=session.input_snapshot.dump_sha256,
            include_embeddings=True,
            expected_verification=session.input_snapshot.verification,
            timeout=settings.database_operation_timeout_seconds,
        )
        if verification is None:
            raise ValueError("worker restore did not return the expected verification")
        return verification


def export_worker_database(
    session: WorkerDatasetSession, *, runner: mechanics.ProcessRunner
) -> DatabaseSnapshot:
    """Verify the quiescent worker database and publish one full return snapshot and dump."""
    settings = load_administrative_dataset_settings()
    root = admin_state_root(settings)
    with mechanics.exclusive_action_lock(root, controller_name="datasets", blocking=True):
        recorded = load_worker_dataset_session(session.session_id)
        if recorded != session:
            raise ValueError("uploaded session file does not match the requested session")
        _require_session_identity(session, settings)
        directory = _session_directory(settings, session.session_id)
        return_json = directory / "return.json"
        return_dump = directory / "return.dump"
        if return_json.is_symlink() or return_dump.is_symlink():
            raise ValueError("returned dataset artifacts must not be symlinks")
        if return_json.exists():
            if not return_json.is_file() or not return_dump.is_file():
                raise ValueError("incomplete returned dataset export must be completed explicitly")
            snapshot = load_private_model(return_json, DatabaseSnapshot)
            if (
                snapshot.session_id != session.session_id
                or snapshot.database_name != session.database_name
            ):
                raise ValueError("existing return snapshot identity does not match the session")
            if sha256_file(return_dump) != snapshot.dump_sha256:
                raise ValueError("existing return dump does not match its snapshot")
            return snapshot
        if return_dump.exists():
            raise ValueError("incomplete returned dataset export must be completed explicitly")

        worker_settings = load_raw_database_settings().model_copy(
            update={"postgres_db": session.database_name}
        )
        verification = read_dataset_verification(worker_settings)
        dump_sha256 = dump_database(
            runner=runner,
            root=repository_root(),
            settings=worker_settings,
            destination=return_dump,
            include_embeddings=True,
            timeout=settings.database_operation_timeout_seconds,
        )
        snapshot = DatabaseSnapshot(
            schema_version=1,
            session_id=session.session_id,
            database_name=session.database_name,
            dump_sha256=dump_sha256,
            verification=verification,
        )
        atomic_write_private_text(return_json, administrative_json(snapshot))
        return snapshot


def return_worker_database(
    session: WorkerDatasetSession,
    *,
    transport: SshWslTransport,
    runner: mechanics.ProcessRunner,
) -> DatasetReceipt:
    """Export (or reuse) the worker snapshot, download it, and retain it through the sole writer."""
    settings = load_administrative_dataset_settings()
    root = admin_state_root(settings)
    if read_optional_dataset_receipt(root, session.session_id) is not None:
        return retain_returned_dataset(session, None, None, runner=runner)

    connection = load_worker_connection_settings()
    worker_root = connection.worker_project_root
    remote_session = remote_worker_session_directory(connection, session.session_id)
    payload = transport.run(
        (
            "uv",
            "run",
            "--no-sync",
            "--offline",
            "--no-python-downloads",
            "python",
            "-m",
            "course_explorer_admin.remote",
            "export",
            session.session_id,
        ),
        cwd=PurePosixPath(str(worker_root)),
        env={
            "SELECTED_DATASET_ENABLED": "0",
            "POSTGRES_DB": session.database_name,
            "ADMIN_STATE_ROOT": str(settings.admin_state_root),
        },
        timeout=settings.database_operation_timeout_seconds,
    )
    snapshot = DatabaseSnapshot.model_validate_json(payload.decode("utf-8"))
    if snapshot.session_id != session.session_id or snapshot.database_name != session.database_name:
        raise ValueError("exported snapshot identity does not match the session")

    retained = retained_dump_path(root, session.session_id)
    retained.parent.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    retained.parent.mkdir(mode=0o700, exist_ok=True)
    if retained.is_symlink() or (retained.exists() and not retained.is_file()):
        raise ValueError("local returned dataset dump must be a regular non-symlink file")
    if retained.exists():
        if sha256_file(retained) != snapshot.dump_sha256:
            raise ValueError("local returned dataset dump does not match the snapshot")
    else:
        transport.download(
            remote_session / "return.dump",
            retained,
            timeout=settings.database_operation_timeout_seconds,
        )
    return retain_returned_dataset(session, snapshot, retained, runner=runner)


def cleanup_returned_worker_database(
    session: WorkerDatasetSession,
    receipt: DatasetReceipt,
    *,
    runner: mechanics.ProcessRunner,
) -> None:
    """Drop one exact returned worker database only after both authorities agree.

    The recorded canonical session, the derived worker database name, the server receipt
    predicate, and the strict returned snapshot must all match before the single exact
    ``dropdb --if-exists`` runs. No dump, import, selection, service start, signal, or artifact
    deletion happens here.
    """
    settings = load_administrative_dataset_settings()
    recorded = load_worker_dataset_session(session.session_id)
    if recorded != session:
        raise ValueError("recorded session file does not match the requested session")
    _require_session_identity(session, settings)
    require_returned_dataset_receipt(
        receipt, session, server_database=settings.database_name(session.session_id, worker=False)
    )
    directory = _session_directory(settings, session.session_id)
    snapshot = load_private_model(directory / "return.json", DatabaseSnapshot)
    if (
        snapshot.session_id != session.session_id
        or snapshot.database_name != session.database_name
        or snapshot.dump_sha256 != receipt.dump_sha256
        or snapshot.verification != receipt.verification
    ):
        raise ValueError("returned snapshot does not match the dataset receipt")
    require_droppable_database(session.database_name)
    runner.run(
        (
            *mechanics.compose_prefix(),
            "exec",
            "-T",
            "db",
            "dropdb",
            "--if-exists",
            "--username",
            load_raw_database_settings().postgres_user,
            session.database_name,
        ),
        cwd=repository_root(),
        timeout=settings.database_operation_timeout_seconds,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Expose the ``prepare``/``export``/``cleanup`` subcommands."""
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("prepare", "export", "cleanup"):
        subparsers.add_parser(name).add_argument("session_id")
    args = parser.parse_args(argv)
    try:
        session = load_worker_dataset_session(args.session_id)
        runner = mechanics.SubprocessRunner()
        if args.command == "prepare":
            verification = prepare_worker_database(session, runner=runner)
            print(administrative_json(verification), end="")
            return 0
        if args.command == "export":
            snapshot = export_worker_database(session, runner=runner)
            print(administrative_json(snapshot), end="")
            return 0
        directory = worker_dataset_session_directory(args.session_id)
        receipt = load_private_model(directory / "dataset-receipt.json", DatasetReceipt)
        cleanup_returned_worker_database(session, receipt, runner=runner)
        print(administrative_json(receipt), end="")
        return 0
    except Exception as exc:
        # Never print a raw traceback, untrusted text, or settings. Only the safe class name.
        print(type(exc).__name__, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
