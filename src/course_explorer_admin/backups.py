"""Sole owner of the operator-held backup files under ``data/backups``.

The backup root is the fixed repository-relative ``data/backups``, outside the dataset chain and
outside automatic rotation. This module lists the regular files beneath that root and deletes one
named file. A symlinked or non-directory path, a symlinked or non-file entry, an unconfined name
and an absent file all refuse before any other file is touched.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from course_explorer.administration import repository_root


class _BackupModel(BaseModel):
    """Frozen, closed DTO base for the backup-file contract."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class BackupFile(_BackupModel):
    """One regular file under the backup root, described by file metadata alone."""

    name: str
    size_bytes: int
    modified_at: datetime


class BackupListReport(_BackupModel):
    """One listing of the backup files in lexical relative-name order."""

    schema_version: Literal[1] = 1
    backups: tuple[BackupFile, ...]


class BackupDeletionReport(_BackupModel):
    """One explicit deletion of a single backup file."""

    schema_version: Literal[1] = 1
    name: str


def _backup_root() -> Path:
    """Resolve the fixed backup root and refuse a symlinked or non-directory path.

    The root is the repository-relative ``data/backups``. The root and its ``data`` parent are
    inspected before a listing or a deletion, so a symlinked directory cannot redirect a walk or a
    delete outside the root. Neither directory is created here.
    """
    root = repository_root() / "data" / "backups"
    for candidate in (root.parent, root):
        if candidate.is_symlink() or (candidate.exists() and not candidate.is_dir()):
            raise ValueError("backup root must not traverse a symlink or non-directory")
    return root


def _regular_files(root: Path) -> list[Path]:
    """Return every regular file beneath ``root`` in lexical relative-name order.

    A symlinked entry and a non-file entry refuse the walk, and a directory that a symlink replaces
    is never entered. A filesystem traversal error propagates to the caller.
    """

    def refuse(error: OSError) -> None:
        raise error

    files: list[Path] = []
    for directory, directory_names, file_names in root.walk(on_error=refuse):
        for name in directory_names:
            if (directory / name).is_symlink():
                raise ValueError("backup listing refuses a symlinked entry")
        for name in file_names:
            path = directory / name
            if path.is_symlink() or not path.is_file():
                raise ValueError("backup listing refuses a non-file entry")
            files.append(path)
    return sorted(files, key=lambda path: path.relative_to(root).as_posix())


def list_backups() -> BackupListReport:
    """List the regular files under the backup root in lexical relative-name order.

    File metadata supplies the size and the timezone-aware UTC modification time of each entry, and
    no file content is read. An absent root reports no backups and creates nothing.
    """
    root = _backup_root()
    if not root.exists():
        return BackupListReport(backups=())
    entries = []
    for path in _regular_files(root):
        status = path.stat()
        entries.append(
            BackupFile(
                name=path.relative_to(root).as_posix(),
                size_bytes=status.st_size,
                modified_at=datetime.fromtimestamp(status.st_mtime, tz=UTC),
            )
        )
    return BackupListReport(backups=tuple(entries))


def _confined_backup_file(name: str) -> Path:
    """Resolve one relative backup name to its confined file and refuse anything else.

    The name is the relative POSIX name a listing reports. An empty or absolute name, a backslash, a
    NUL, an empty, dot or dot-dot segment, a symlinked or non-directory parent, and a missing,
    symlinked or non-file target all raise :class:`ValueError` before any deletion.
    """
    if not name or name.startswith("/") or "\\" in name or "\x00" in name:
        raise ValueError("backup name must be a nonblank relative POSIX path")
    segments = name.split("/")
    if any(segment in {"", ".", ".."} for segment in segments):
        raise ValueError("backup name must not contain an empty, dot or dot-dot segment")
    directory = _backup_root()
    for segment in segments[:-1]:
        directory = directory / segment
        if directory.is_symlink() or not directory.is_dir():
            raise ValueError("backup path must not traverse a symlink or non-directory")
    target = directory / segments[-1]
    if target.is_symlink() or not target.is_file():
        raise ValueError("backup target must be an existing regular non-symlink file")
    return target


def delete_backup(name: str) -> BackupDeletionReport:
    """Delete the one backup file the relative name identifies and report that name.

    The file must exist inside the fixed root, so an absent or unconfined name raises instead of
    reporting a completed deletion. No directory, sibling or content outside the root is removed.
    """
    _confined_backup_file(name).unlink()
    return BackupDeletionReport(name=name)
