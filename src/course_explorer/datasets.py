"""Product owner for selected-dataset metadata, default resolution, and fresh verification.

Development and administrative commands resolve the selected dataset through the ignored
``data/admin/selected-dataset.json`` pointer and its dataset receipt. A deployment that sets
``SELECTED_DATASET_ENABLED=0`` names its own database. This module mutates no
database and starts no worker session: it strictly loads the pointer/receipt chain and opens one
disposable engine for a read-only verification that compares the Alembic head and counts every ORM
table plus the four coverage reads. The database dump/restore/rotation mechanics live in
the sibling ``course_explorer_admin`` package, which owns every mutation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

from alembic.config import Config as AlembicConfig
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from pydantic import BaseModel, ConfigDict, StringConstraints, model_validator
from sqlalchemy import Connection, func, select

from course_explorer.administration import load_private_model, repository_root, session_directory
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

_INITIAL_DATASET_ID = "0" * 32

_SETUP_GUIDANCE = (
    "no dataset is selected; run setup with `uv run python scripts/admin.py setup datasets`"
)

_SCHEMA_MISMATCH_GUIDANCE = (
    "the received database does not match the executing checkout's single Alembic head; "
    "no processing or automatic migration occurred, so use compatible code and data through "
    "explicit setup and the existing dataset owners"
)


class DatabaseSchemaMismatchError(ValueError):
    """Received database does not match the executing checkout's migration head."""


class _DatasetModel(BaseModel):
    """Frozen, closed DTO base for the selected-dataset contract."""

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
        if not self.alembic_revision.strip():
            raise ValueError("verification requires a nonblank alembic revision")
        if any(count < 0 for count in self.table_row_counts.values()):
            raise ValueError("table row counts must be nonnegative")
        return self


class DatabaseSnapshot(_DatasetModel):
    """Immutable identity and description of one dump taken from one database."""

    schema_version: Literal[1] = 1
    session_id: DatasetId
    revision: DatasetRevision
    database_name: DatasetDatabaseName
    dump_sha256: DatasetSha256
    verification: DatasetVerification


class DatasetReceipt(_DatasetModel):
    """One enrolled dataset: an initial database or a verified returned session."""

    schema_version: Literal[1] = 1
    dataset_id: DatasetId
    database_name: DatasetDatabaseName
    predecessor_id: DatasetId | None
    kind: Literal["initial", "returned"]
    revision: DatasetRevision
    dump_sha256: DatasetSha256 | None
    verification: DatasetVerification

    @model_validator(mode="after")
    def validate_initial_or_returned(self) -> DatasetReceipt:
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
            raise ValueError("a returned receipt names its session, predecessor, and dump hash")
        return self


class SelectedDatasetPointer(_DatasetModel):
    """Strict pointer naming the one dataset administrative commands select by default."""

    schema_version: Literal[1] = 1
    dataset_id: DatasetId


def require_selected_dataset_root(state_root: Path) -> Path:
    """Refuse a state tree that a symlink or non-directory would redirect.

    Read-only and side-effect free: it inspects the state root, every ancestor, the two known
    collection directories ``datasets`` and ``sessions``, and ``controller.lock`` without creating or
    resolving anything. A symlink or a non-directory anywhere in that shape
    fails with one fixed ``ValueError`` before any lock, receipt, dump, or database action, so a
    redirected tree can never be followed into ``data/backups`` or another location. Missing
    directories and an absent lock are allowed for first enrollment. The supplied path is returned,
    never a silently resolved substitute.
    """
    candidates = [state_root, *state_root.parents]
    candidates.extend((state_root / "datasets", state_root / "sessions"))
    for candidate in candidates:
        if candidate.is_symlink() or (candidate.exists() and not candidate.is_dir()):
            raise ValueError("selected dataset state must not traverse a symlink or non-directory")
    lock = state_root / "controller.lock"
    if lock.is_symlink() or (lock.exists() and not lock.is_file()):
        raise ValueError("selected dataset action lock must not be a symlink or non-directory")
    return state_root


def read_dataset_receipt(state_root: Path, dataset_id: str) -> DatasetReceipt:
    """Load one dataset receipt from its strict, confined directory."""
    require_selected_dataset_root(state_root)
    directory = session_directory(state_root / "datasets", dataset_id)
    return load_private_model(directory / "receipt.json", DatasetReceipt)


def resolve_selected_dataset(state_root: Path) -> DatasetReceipt:
    """Resolve the selected dataset receipt from the pointer under ``state_root``.

    A missing pointer raises ``FileNotFoundError`` with setup guidance. A symlinked/redirected root
    tree, a malformed pointer, a missing/mismatching receipt, or an invalid receipt fails loudly.
    """
    require_selected_dataset_root(state_root)
    pointer_path = state_root / "selected-dataset.json"
    if not pointer_path.exists() and not pointer_path.is_symlink():
        raise FileNotFoundError(_SETUP_GUIDANCE)
    pointer = load_private_model(pointer_path, SelectedDatasetPointer)
    receipt = read_dataset_receipt(state_root, pointer.dataset_id)
    if receipt.dataset_id != pointer.dataset_id:
        raise ValueError("selected dataset receipt identity does not match the pointer")
    return receipt


def require_database_schema(connection: Connection) -> str:
    """Require one connection to be at the executing checkout's single Alembic head.

    The repository must expose exactly one migration head. A connection whose current heads differ
    (or that carries no version) raises :class:`DatabaseSchemaMismatchError` with fixed safe
    guidance. It returns the repository head.
    """
    repository_heads = ScriptDirectory.from_config(
        AlembicConfig(str(repository_root() / "alembic.ini"))
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
    own aggregate count query, and the four coverage owners are called once with shared repositories.
    It counts tables and calls the four coverage owners only.
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
    "DatasetId",
    "DatasetReceipt",
    "DatasetRevision",
    "DatasetSha256",
    "DatasetVerification",
    "DatabaseSnapshot",
    "SelectedDatasetPointer",
    "read_dataset_receipt",
    "read_dataset_verification",
    "require_database_schema",
    "require_selected_dataset_root",
    "resolve_selected_dataset",
]
