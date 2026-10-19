"""One owner of the selected-dataset PostgreSQL dump and restore command mechanics.

The translation controller and the selected-dataset setup/return path both need exactly one
pg_dump/pg_restore command owner, so this module owns the Compose dump/list/template0/restore logic
for both in one place. The caller supplies an already-validated ``DatabaseSettings``
and an explicit database/destination.
"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

from pydantic import TypeAdapter

from course_explorer.administration import sha256_file
from course_explorer.config import DatabaseSettings
from course_explorer.datasets import (
    DatasetDatabaseName,
    DatasetVerification,
    read_dataset_verification,
)
from course_explorer_admin import mechanics

_DATABASE_NAME_ADAPTER = TypeAdapter(DatasetDatabaseName)
_EMBEDDING_TABLE_DATA_PATTERN = re.compile(rb"TABLE DATA public course_embedding_chunks\b")


def database_dump_contains_embedding_data(listing: bytes) -> bool:
    """Return whether a pg_restore listing includes course embedding chunk table data."""
    return _EMBEDDING_TABLE_DATA_PATTERN.search(listing) is not None


def _require_valid_database_name(database_name: str) -> str:
    return _DATABASE_NAME_ADAPTER.validate_python(database_name)


def _require_embedding_data(listing: bytes, *, include_embeddings: bool) -> None:
    contains = database_dump_contains_embedding_data(listing)
    if include_embeddings and not contains:
        raise ValueError("database dump must include course embedding table data")
    if not include_embeddings and contains:
        raise ValueError("database dump must exclude course embedding table data")


def _compose_exec(*, settings: DatabaseSettings, argv: tuple[str, ...]) -> tuple[str, ...]:
    return (*mechanics.compose_prefix(), "exec", "-T", "db", *argv)


def dump_database(
    *,
    runner: mechanics.ProcessRunner,
    root: Path,
    settings: DatabaseSettings,
    destination: Path,
    include_embeddings: bool,
    timeout: float | None = None,
) -> str:
    """Dump one database to a fresh file and return its SHA-256.

    The dump always lands in a fresh invocation-owned temporary beside an absent destination, is
    listing-checked for the requested embedding-table policy, then published at mode 0600. A
    failure removes only that temporary.
    """
    if destination.exists() or destination.is_symlink():
        raise ValueError("database dump destination must not already exist")
    descriptor, temporary_name = tempfile.mkstemp(
        dir=destination.parent, prefix=f".{destination.name}-", suffix=".tmp"
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    exclusion: tuple[str, ...] = (
        () if include_embeddings else ("--exclude-table-data=course_embedding_chunks",)
    )
    try:
        runner.run(
            _compose_exec(
                settings=settings,
                argv=(
                    "pg_dump",
                    "--username",
                    settings.postgres_user,
                    "--dbname",
                    settings.postgres_db,
                    "--format=custom",
                    "--no-owner",
                    "--no-privileges",
                    *exclusion,
                ),
            ),
            cwd=root,
            stdout_path=temporary,
            timeout=timeout,
        )
        listing = runner.run(
            _compose_exec(settings=settings, argv=("pg_restore", "--list")),
            cwd=root,
            stdin_path=temporary,
            timeout=timeout,
        ).stdout
        _require_embedding_data(listing, include_embeddings=include_embeddings)
        os.chmod(temporary, 0o600)
        os.replace(temporary, destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return sha256_file(destination)


def database_exists(
    *,
    runner: mechanics.ProcessRunner,
    root: Path,
    settings: DatabaseSettings,
    database_name: str,
    timeout: float | None,
) -> bool:
    """Return whether the database service holds a database of this validated name."""
    count = (
        runner.run(
            _compose_exec(
                settings=settings,
                argv=(
                    "psql",
                    "--username",
                    settings.postgres_user,
                    "--dbname",
                    "postgres",
                    "--tuples-only",
                    "--no-align",
                    "--command",
                    f"SELECT count(*) FROM pg_database WHERE datname = '{database_name}'",
                ),
            ),
            cwd=root,
            timeout=timeout,
        )
        .stdout.decode("utf-8")
        .strip()
    )
    if count not in {"0", "1"}:
        raise ValueError("database existence probe returned an unexpected result")
    return count == "1"


def restore_database(
    *,
    runner: mechanics.ProcessRunner,
    root: Path,
    settings: DatabaseSettings,
    dump: Path,
    database_name: str,
    expected_sha256: str,
    include_embeddings: bool,
    expected_verification: DatasetVerification | None = None,
    timeout: float | None = None,
) -> DatasetVerification | None:
    """Restore one verified dump into a fresh or already-matching database.

    The dump must be a regular non-symlink file with the expected digest and the requested embedding
    policy, and the target name must be a validated lowercase identifier of at most 63 bytes. An
    absent target is created from ``template0`` and restored with exit-on-error/single-transaction/
    no-owner/no-privileges. A present target is refused unless a supplied expected verification
    matches a fresh owning verification. A mismatching target is left in place.
    """
    if dump.is_symlink() or not dump.is_file():
        raise ValueError("database dump must be a regular non-symlink file")
    if sha256_file(dump) != expected_sha256:
        raise ValueError("database dump checksum does not match")
    _require_valid_database_name(database_name)
    listing = runner.run(
        _compose_exec(settings=settings, argv=("pg_restore", "--list")),
        cwd=root,
        stdin_path=dump,
        timeout=timeout,
    ).stdout
    _require_embedding_data(listing, include_embeddings=include_embeddings)

    existing = database_exists(
        runner=runner, root=root, settings=settings, database_name=database_name, timeout=timeout
    )
    if not existing:
        runner.run(
            _compose_exec(
                settings=settings,
                argv=(
                    "createdb",
                    "--username",
                    settings.postgres_user,
                    "--template",
                    "template0",
                    database_name,
                ),
            ),
            cwd=root,
            timeout=timeout,
        )
        runner.run(
            _compose_exec(
                settings=settings,
                argv=(
                    "pg_restore",
                    "--username",
                    settings.postgres_user,
                    "--dbname",
                    database_name,
                    "--exit-on-error",
                    "--single-transaction",
                    "--no-owner",
                    "--no-privileges",
                ),
            ),
            cwd=root,
            stdin_path=dump,
            timeout=timeout,
        )

    if expected_verification is None:
        if existing:
            raise ValueError("database already exists and no expected verification was supplied")
        return None

    actual = read_dataset_verification(settings.model_copy(update={"postgres_db": database_name}))
    if actual != expected_verification:
        raise ValueError("restored database verification does not match the expected snapshot")
    return actual
