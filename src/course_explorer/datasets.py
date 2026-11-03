"""Product owner for dataset-role pointers, receipt resolution, and fresh verification.

Development and administrative commands resolve the Selected dataset that the site serves and the
Working dataset that the pipeline stages use through the ignored pointers under the administration
state root and their dataset receipts. A deployment with no pointer serves its configured database.
This module mutates no database and starts no worker session: it strictly loads pointers and
receipts, decides whether a state root is bootstrap or enrolled, and opens one disposable engine for
a read-only verification that compares the Alembic head and counts every ORM table plus the four
coverage reads. The database dump/restore/rotation mechanics live in the sibling
``course_explorer_admin`` package, which owns every mutation.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Annotated, Literal

from alembic.config import Config as AlembicConfig
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from pydantic import BaseModel, ConfigDict, StringConstraints, model_validator
from sqlalchemy import Connection, func, select

from course_explorer import administration
from course_explorer.administration import load_private_model, session_directory
from course_explorer.config import DatabaseSettings
from course_explorer.curriculum import CatalogueSummary
from course_explorer.curriculum_repository import CurriculumRepository
from course_explorer.db.models import Base
from course_explorer.db.session import create_database_engine, create_session_factory
from course_explorer.embeddings.generation import CourseEmbeddingCoverageReport
from course_explorer.embeddings.repository import CourseEmbeddingRepository
from course_explorer.inference.diagnostics import InferenceCoverageSummary
from course_explorer.inference.scheduling_repository import InferenceSchedulingRepository
from course_explorer.teaching_text.repository import DerivedTranslationRepository
from course_explorer.teaching_text.service import TeachingTextCoverageReport, TeachingTextService

DatasetId = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{32}$")]
DatasetRevision = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{40}$")]
DatasetSha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
DatasetDatabaseName = Annotated[
    str, StringConstraints(pattern=r"^[a-z_][a-z0-9_]*$", max_length=63)
]
DatasetRole = Literal["selected", "working"]

_INITIAL_DATASET_ID = "0" * 32

_POINTER_FILENAMES: dict[DatasetRole, str] = {
    "selected": "selected-dataset.json",
    "working": "working-dataset.json",
}

_SETUP_GUIDANCE = (
    "no dataset is selected; run setup with `uv run python scripts/admin.py setup datasets`"
)

_WORKING_GUIDANCE = (
    "no dataset is copied to Working; copy a dataset to Working first with "
    "`uv run python scripts/admin.py datasets copy-to-working SOURCE_ID`"
)

_SCHEMA_MISMATCH_GUIDANCE = (
    "the received database does not match the executing checkout's single Alembic head; "
    "no processing or automatic migration occurred, so use compatible code and data through "
    "explicit setup and the existing dataset owners"
)


class DatabaseSchemaMismatchError(ValueError):
    """Received database does not match the executing checkout's migration head."""


class _DatasetModel(BaseModel):
    """Frozen, closed DTO base for the dataset-role contract."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class DatasetVerification(_DatasetModel):
    """One fresh, read-only identity/coverage snapshot of one database state."""

    schema_version: Literal[1] = 1
    alembic_revision: str
    table_row_counts: dict[str, int]
    catalogue: CatalogueSummary
    teaching_text: TeachingTextCoverageReport
    embeddings: CourseEmbeddingCoverageReport
    inference: InferenceCoverageSummary

    @model_validator(mode="after")
    def validate_counts(self) -> DatasetVerification:
        """Require a nonblank Alembic revision on one verification snapshot."""
        if not self.alembic_revision.strip():
            raise ValueError("verification requires a nonblank alembic revision")
        return self


class DatabaseSnapshot(_DatasetModel):
    """Immutable identity and description of one dump taken from one database."""

    schema_version: Literal[1] = 1
    session_id: DatasetId
    database_name: DatasetDatabaseName
    dump_sha256: DatasetSha256
    verification: DatasetVerification


class DatasetReceipt(_DatasetModel):
    """One enrolled dataset: an initial database, a verified return, or a verified copy."""

    schema_version: Literal[1] = 1
    dataset_id: DatasetId
    database_name: DatasetDatabaseName
    predecessor_id: DatasetId | None
    kind: Literal["initial", "returned", "copied"]
    dump_sha256: DatasetSha256 | None
    verification: DatasetVerification

    @model_validator(mode="after")
    def validate_kind_identity(self) -> DatasetReceipt:
        """Require the receipt fields that one enrollment kind carries."""
        if self.kind == "initial":
            if (
                self.dataset_id != _INITIAL_DATASET_ID
                or self.predecessor_id is not None
                or self.dump_sha256 is not None
            ):
                raise ValueError("an initial receipt has the zero id, no predecessor, and no dump")
        elif (
            self.dataset_id == _INITIAL_DATASET_ID
            or self.predecessor_id is None
            or self.dump_sha256 is None
        ):
            raise ValueError(
                "a returned or copied receipt names its source, predecessor, and dump hash"
            )
        return self


class DatasetPointer(_DatasetModel):
    """Strict pointer naming the dataset one role resolves."""

    schema_version: Literal[1] = 1
    dataset_id: DatasetId


class DatasetEnrollmentReport(_DatasetModel):
    """One transient report of deploy enrollment: a bootstrap root or an enrolled selection."""

    schema_version: Literal[1] = 1
    mode: Literal["bootstrap", "enrolled"]


def dataset_pointer_path(state_root: Path, role: DatasetRole) -> Path:
    """Return the one pointer file of a role under the administration state root."""
    return state_root / _POINTER_FILENAMES[role]


def dataset_state_refusal(state_root: Path) -> str | None:
    """Return the fixed refusal of a state tree that a symlink or non-directory would redirect.

    Read-only and side-effect free: it inspects the state root, every ancestor, the two known
    collection directories ``datasets`` and ``sessions``, and ``controller.lock`` without creating
    or resolving anything. A symlink or a non-directory anywhere in that shape returns one fixed
    message, so a redirected tree is never followed into ``data/backups`` or another location.
    Missing directories and an absent lock are acceptable for first enrollment. Every acceptable
    shape returns ``None``.
    """
    candidates = [state_root, *state_root.parents]
    candidates.extend((state_root / "datasets", state_root / "sessions"))
    for candidate in candidates:
        if candidate.is_symlink() or (candidate.exists() and not candidate.is_dir()):
            return "dataset state must not traverse a symlink or non-directory"
    lock = state_root / "controller.lock"
    if lock.is_symlink() or (lock.exists() and not lock.is_file()):
        return "dataset action lock must not be a symlink or non-directory"
    return None


def require_selected_dataset_root(state_root: Path) -> Path:
    """Refuse a state tree that a symlink or non-directory would redirect.

    The write refusal: the read-only predicate supplies the one fixed message, which fails the
    operation before any lock, receipt, dump, or database action, so a redirected tree can never be
    followed into ``data/backups`` or another location. The supplied path is returned, never a
    silently resolved substitute.
    """
    refusal = dataset_state_refusal(state_root)
    if refusal is not None:
        raise ValueError(refusal)
    return state_root


def _load_dataset_receipt(state_root: Path, dataset_id: str) -> DatasetReceipt:
    """Load one dataset receipt from its strict, confined directory.

    The caller's single state-tree guard covers the whole read.
    """
    directory = session_directory(state_root / "datasets", dataset_id)
    return load_private_model(directory / "receipt.json", DatasetReceipt)


def read_dataset_receipt(state_root: Path, dataset_id: str) -> DatasetReceipt:
    """Load one dataset receipt from its strict, confined directory after the state-tree guard."""
    require_selected_dataset_root(state_root)
    return _load_dataset_receipt(state_root, dataset_id)


_DATASET_CACHE_LOCK = threading.Lock()
_DATASET_CACHE: dict[DatasetRole, tuple[tuple[str, int, int, int, int], DatasetReceipt]] = {}


def clear_dataset_cache(role: DatasetRole | None = None) -> None:
    """Drop the memoized receipt of one role, or of both roles when no role is named."""
    with _DATASET_CACHE_LOCK:
        if role is None:
            _DATASET_CACHE.clear()
        else:
            _DATASET_CACHE.pop(role, None)


def has_dataset_enrollment_records(state_root: Path) -> bool:
    """Return whether dataset or session records prove an enrolled state root.

    One read-only scan establishes enrollment from a receipt file or a retained dump in any dataset
    directory and from a recorded session. Empty collection directories, unrelated stage
    directories, the action lock and the role pointers establish none, so a caller decides pointer
    presence itself. It writes nothing and parses no pointer.
    """
    datasets = state_root / "datasets"
    if datasets.is_dir():
        for directory in datasets.iterdir():
            if (directory / "receipt.json").exists() or (directory / "database.dump").exists():
                return True
    sessions = state_root / "sessions"
    if sessions.is_dir():
        for directory in sessions.iterdir():
            if (directory / "session.json").exists():
                return True
    return False


def _read_pointer(
    state_root: Path, role: DatasetRole
) -> tuple[DatasetPointer, tuple[int, int]] | None:
    """Read one role pointer and its stat identity, or return ``None`` when it is absent.

    The caller's single state-tree guard covers the whole read.
    """
    pointer_path = dataset_pointer_path(state_root, role)
    if not pointer_path.exists() and not pointer_path.is_symlink():
        return None
    pointer_stat = pointer_path.stat()
    pointer = load_private_model(pointer_path, DatasetPointer)
    return pointer, (pointer_stat.st_mtime_ns, pointer_stat.st_size)


def _require_distinct_roles(selected: DatasetReceipt, working: DatasetReceipt) -> None:
    """Refuse a Working pointer that aliases the Selected dataset or database."""
    if working.dataset_id == selected.dataset_id or working.database_name == selected.database_name:
        raise ValueError("the Working dataset must differ from the Selected dataset")


def _read_role_receipt(
    state_root: Path, role: DatasetRole, pointer_read: tuple[DatasetPointer, tuple[int, int]]
) -> DatasetReceipt:
    """Validate one present role's receipt, reusing its memoized model for unchanged files."""
    global _DATASET_CACHE
    pointer, pointer_stat = pointer_read
    receipt_path = session_directory(state_root / "datasets", pointer.dataset_id) / "receipt.json"
    if receipt_path.is_symlink() or not receipt_path.is_file():
        raise ValueError(f"state file must be a regular non-symlink file: {receipt_path.name}")
    receipt_stat = receipt_path.stat()
    key = (
        str(state_root),
        pointer_stat[0],
        pointer_stat[1],
        receipt_stat.st_mtime_ns,
        receipt_stat.st_size,
    )
    with _DATASET_CACHE_LOCK:
        retained = _DATASET_CACHE.get(role)
    if retained is not None and retained[0] == key:
        return retained[1]
    receipt = _load_dataset_receipt(state_root, pointer.dataset_id)
    if receipt.dataset_id != pointer.dataset_id:
        raise ValueError("dataset receipt identity does not match the pointer")
    with _DATASET_CACHE_LOCK:
        _DATASET_CACHE[role] = (key, receipt)
    return receipt


def read_dataset_role(state_root: Path, role: DatasetRole) -> DatasetReceipt | None:
    """Resolve one role's receipt, returning ``None`` only for an absent role in a valid state.

    A missing Selected pointer is bootstrap only when the Working pointer is absent too and no
    dataset receipt, retained dump or recorded session exists. Otherwise it raises the enrollment
    guidance without parsing the orphan pointer. A Working read resolves the current Selected
    receipt first and refuses a Working dataset that aliases its id or database, whether the Working
    receipt is memoized or freshly read. A missing Selected pointer, malformed pointer or
    mismatching receipt therefore fails even when Working was cached. A missing Working pointer
    returns ``None``. A redirected tree, malformed pointer or mismatching receipt fails through the
    shared state guards. Reads create nothing and own no database.
    """
    require_selected_dataset_root(state_root)
    selected_pointer = _read_pointer(state_root, "selected")
    if selected_pointer is None:
        working_pointer = dataset_pointer_path(state_root, "working")
        if working_pointer.exists() or has_dataset_enrollment_records(state_root):
            raise FileNotFoundError(_SETUP_GUIDANCE)
        return None
    selected = _read_role_receipt(state_root, "selected", selected_pointer)
    if role == "selected":
        return selected
    working_pointer = _read_pointer(state_root, "working")
    if working_pointer is None:
        return None
    receipt = _read_role_receipt(state_root, "working", working_pointer)
    _require_distinct_roles(selected, receipt)
    return receipt


def resolve_dataset_role(state_root: Path, role: DatasetRole) -> DatasetReceipt:
    """Resolve one role's receipt or raise fixed guidance for an absent role.

    Missing Working raises the copy guidance, and missing Selected raises the enrollment guidance.
    """
    receipt = read_dataset_role(state_root, role)
    if receipt is not None:
        return receipt
    if role == "working":
        raise FileNotFoundError(_WORKING_GUIDANCE)
    raise FileNotFoundError(_SETUP_GUIDANCE)


def resolve_selected_dataset(state_root: Path) -> DatasetReceipt:
    """Resolve the Selected dataset receipt from the pointer under ``state_root``.

    The receipt is memoized with the Working receipt by the state root, the pointer's modification
    time and size and the receipt's modification time and size, so an unchanged pointer and receipt
    reuse the parsed model and either file's rewrite re-reads it. A missing pointer in a bootstrap
    root raises ``FileNotFoundError`` with setup guidance. A symlinked/redirected root tree, a
    malformed pointer, a missing/mismatching receipt, or an invalid receipt fails loudly.
    """
    return resolve_dataset_role(state_root, "selected")


def require_database_schema(connection: Connection) -> str:
    """Require one connection to be at the executing checkout's single Alembic head.

    The repository must expose exactly one migration head, and any other head count raises
    ``ValueError``. A connection whose current heads differ (or that carries no version) raises
    :class:`DatabaseSchemaMismatchError` with fixed safe guidance. It returns the repository head.
    """
    repository_heads = ScriptDirectory.from_config(
        AlembicConfig(str(administration.repository_root() / "alembic.ini"))
    ).get_heads()
    if len(repository_heads) != 1:
        raise ValueError("repository must expose exactly one Alembic head")
    expected_head = repository_heads[0]
    current_heads = MigrationContext.configure(connection).get_current_heads()
    if current_heads != (expected_head,):
        raise DatabaseSchemaMismatchError(_SCHEMA_MISMATCH_GUIDANCE)
    return expected_head


def read_dataset_verification(settings: DatabaseSettings) -> DatasetVerification:
    """Open one engine, read the head and coverage, and dispose it.

    The current Alembic head must be the single repository head, every ORM table is counted by its
    own aggregate count query, and the four coverage owners are called once with shared
    repositories. It counts tables and calls the four coverage owners only.
    """
    engine = create_database_engine(settings)
    try:
        with engine.connect() as connection:
            expected_head = require_database_schema(connection)
            table_row_counts = {
                table.name: int(
                    connection.execute(select(func.count()).select_from(table)).scalar_one()
                )
                for table in Base.metadata.sorted_tables
            }
        factory = create_session_factory(engine)
        curriculum = CurriculumRepository(factory)
        return DatasetVerification(
            alembic_revision=expected_head,
            table_row_counts=table_row_counts,
            catalogue=curriculum.summary(),
            teaching_text=TeachingTextService(
                curriculum, DerivedTranslationRepository(factory)
            ).coverage(),
            embeddings=CourseEmbeddingRepository(factory).coverage(),
            inference=InferenceSchedulingRepository(factory).read_coverage(),
        )
    finally:
        engine.dispose()


__all__ = [
    "DatabaseSchemaMismatchError",
    "DatasetDatabaseName",
    "DatasetEnrollmentReport",
    "DatasetId",
    "DatasetPointer",
    "DatasetReceipt",
    "DatasetRevision",
    "DatasetRole",
    "DatasetSha256",
    "DatasetVerification",
    "DatabaseSnapshot",
    "clear_dataset_cache",
    "dataset_pointer_path",
    "dataset_state_refusal",
    "has_dataset_enrollment_records",
    "read_dataset_receipt",
    "read_dataset_role",
    "read_dataset_verification",
    "require_database_schema",
    "require_selected_dataset_root",
    "resolve_dataset_role",
    "resolve_selected_dataset",
]
