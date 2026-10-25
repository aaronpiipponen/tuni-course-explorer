"""Closed text-free controller contracts for remote translation.

This module owns the durable session/state schemas and the strict loaders for one remote
translation session. The neutral SSH/WSL transport lives in ``course_explorer_admin.transport`` and
the shared process/file mechanics live in ``course_explorer_admin.mechanics`` and
``course_explorer.administration``. The neutral control intent lives in ``course_explorer_admin.remote``.
Every DTO is frozen and closed.
Worker state and the local ownership record carry the validated process identifiers of
processes this controller owns. State directories are mode 0700 and every artifact is published
atomically at mode 0600.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator

from course_explorer.administration import load_private_model
from course_explorer.config import load_administrative_dataset_settings
from course_explorer.datasets import DatasetId
from course_explorer.teaching_text.service import TranslationImportReport
from course_explorer.validation import (
    require_error_type,
    require_finite_nonnegative,
    require_sha256,
)
from course_explorer_admin.remote import (  # noqa: F401 - re-exported neutral control contract
    WorkerControl as TranslationControllerControl,
)
from course_explorer_admin.remote import (
    WorkerControllerStatus,
    WorkerDatasetSession,
    _ControllerModel,
    _require_session_id,
    load_worker_dataset_session,
    worker_dataset_session_directory,
)


class TranslationControllerPolicy(_ControllerModel):
    """Immutable canonical worker policy for one shared-dataset translation session.

    The canonical session identity lives in the neutral ``WorkerDatasetSession`` and the derived
    database name in the administrative settings. This policy carries only the translation-owned
    model provenance. Database name and course limit come from the neutral session and
    administrative settings.
    """

    schema_version: Literal[2]
    session_id: DatasetId
    translation_model: str

    @field_validator("translation_model")
    @classmethod
    def validate_translation_model(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("translation model must not be blank")
        return value


class TranslationControllerWorkerState(_ControllerModel):
    """Text-free worker lifecycle state with the exact per-lifecycle nullability matrix.

    The unloaded-checkpoint matrix: a paused session carries no runner or runtime process, terminal states
    carry no processes, and only starting/running carry the display process identifiers of the
    invocation that is executing.
    """

    schema_version: Literal[2]
    session_id: str
    lifecycle: Literal[
        "prepared",
        "starting",
        "running",
        "paused",
        "stopped",
        "completed",
        "failed",
        "cleaned",
    ]
    desired_count: int = Field(ge=0)
    completed_count: int = Field(ge=0)
    started_at: datetime
    active_seconds: float
    running_since: datetime | None = None
    runner_pid: int | None = None
    runtime_pid: int | None = None
    error_type: str | None = None

    @field_validator("session_id")
    @classmethod
    def validate_session_id(cls, value: str) -> str:
        return _require_session_id(value)

    @field_validator("started_at")
    @classmethod
    def validate_started_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("started_at must be timezone-aware")
        return value

    @field_validator("running_since")
    @classmethod
    def validate_running_since(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("running_since must be timezone-aware when set")
        return value

    @field_validator("active_seconds")
    @classmethod
    def validate_active_seconds(cls, value: float) -> float:
        return require_finite_nonnegative(value, "active_seconds")

    @field_validator("runner_pid", "runtime_pid")
    @classmethod
    def validate_pid(cls, value: int | None) -> int | None:
        if value is not None and value <= 0:
            raise ValueError("process identifiers must be positive when set")
        return value

    @field_validator("error_type")
    @classmethod
    def validate_error_type(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return require_error_type(value, max_length=64)

    @model_validator(mode="after")
    def validate_lifecycle_matrix(self) -> TranslationControllerWorkerState:
        """Enforce each lifecycle's process/running/error pattern.

        Only starting/running carry processes, paused/terminal are process-free, and only failed
        carries a safe error type.
        """
        if self.completed_count > self.desired_count:
            raise ValueError("completed_count must not exceed desired_count")
        runtime_pid = self.runtime_pid is not None
        running_since = self.running_since is not None
        error_type = self.error_type is not None
        if self.lifecycle in {"prepared", "paused", "stopped", "completed", "cleaned"}:
            if self.runner_pid is not None or runtime_pid or running_since or error_type:
                raise ValueError("unloaded state records no processes, running time, or error")
        elif self.lifecycle == "starting":
            if self.runner_pid is None or runtime_pid or running_since or error_type:
                raise ValueError("starting state requires only a runner process")
        elif self.lifecycle == "running":
            if self.runner_pid is None or not runtime_pid or not running_since or error_type:
                raise ValueError("running state requires runner, runtime, and a running timestamp")
        elif self.lifecycle == "failed":
            if self.runner_pid is not None or runtime_pid or running_since or not error_type:
                raise ValueError("failed state requires only a safe error type")
        return self


class TranslationControllerStatus(WorkerControllerStatus):
    """Text-free translation operator status adding its output hash and import report.

    The shared stage-neutral fields, validators and derived rate/ETA live in
    ``WorkerControllerStatus``. This subclass adds only the translation-owned output identity and
    authoritative import report. Every other field, default, and read comes from
    ``WorkerControllerStatus``.
    """

    output_sha256: str | None = None
    import_report: TranslationImportReport | None = None

    @field_validator("output_sha256")
    @classmethod
    def validate_output_sha256(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return require_sha256(value, "hash")


class TranslationControllerImportReceipt(_ControllerModel):
    """Text-free evidence that one returned output was imported into the authoritative store."""

    schema_version: Literal[1]
    session_id: str
    output_count: int = Field(ge=0)
    output_sha256: str | None = None
    import_report: TranslationImportReport

    @field_validator("session_id")
    @classmethod
    def validate_session_id(cls, value: str) -> str:
        return _require_session_id(value)

    @field_validator("output_sha256")
    @classmethod
    def validate_output_sha256(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return require_sha256(value, "hash")


def load_translation_controller_policy(path: Path) -> TranslationControllerPolicy:
    """Load the immutable canonical worker policy from its strict file."""
    return load_private_model(path, TranslationControllerPolicy)


def load_translation_dataset_session(
    session_id: str,
) -> tuple[WorkerDatasetSession, TranslationControllerPolicy, Path]:
    """Load one canonical translation session, its policy, and its shared session directory.

    Both hosts consume this loader: the session record comes from the neutral canonical owner, the
    policy from its sibling strict file, and the directory from the confined administrative
    session path. It requires a translation-stage session whose derived worker database name is the
    configured one and whose requested, session, and policy identities agree, so a foreign or
    mismatched session is refused before it can be prepared, run, or cleaned as this one.
    """
    settings = load_administrative_dataset_settings()
    directory = worker_dataset_session_directory(session_id)
    session = load_worker_dataset_session(session_id)
    policy = load_translation_controller_policy(directory / "policy.json")
    if session.session_id != session_id or policy.session_id != session_id:
        raise ValueError(
            "canonical session or policy identity does not match the requested session"
        )
    if session.stage != "translation":
        raise ValueError("canonical session is not a translation session")
    if session.database_name != settings.database_name(session_id, worker=True):
        raise ValueError("canonical session database name is not the configured derived name")
    return session, policy, directory


def load_translation_controller_worker_state(path: Path) -> TranslationControllerWorkerState:
    """Load the current worker lifecycle state from its strict file."""
    return load_private_model(path, TranslationControllerWorkerState)


def load_translation_controller_import_receipt(
    path: Path,
) -> TranslationControllerImportReceipt:
    """Load one import receipt from its strict file."""
    return load_private_model(path, TranslationControllerImportReceipt)
