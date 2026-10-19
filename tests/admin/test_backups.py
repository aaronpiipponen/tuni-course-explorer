"""Backup-file listing and explicit cleanup contracts."""

from __future__ import annotations

import os
from datetime import UTC
from pathlib import Path

import pytest

from course_explorer_admin import backups


@pytest.fixture()
def backup_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Point the backup owner at one isolated repository root and return its backup directory."""
    monkeypatch.setattr(backups, "repository_root", lambda: tmp_path)
    return tmp_path / "data" / "backups"


@pytest.mark.parametrize(
    "case",
    [
        "regular-file",
        "nested-file",
        "absent-root",
        "unconfined-name",
        "symlink",
        "non-file",
    ],
)
def test_backup_cleanup_unlinks_only_confined_listed_files(
    backup_root: Path, tmp_path: Path, case: str
) -> None:
    """One listing/deletion target per invocation: exactly that file, or a refusal and no delete."""
    outside = tmp_path / "outside.dump"
    outside.write_bytes(b"outside-sentinel")

    if case == "regular-file":
        backup_root.mkdir(parents=True)
        target = backup_root / "before-inference.dump"
        target.write_bytes(b"backup-payload")
        sibling = backup_root / "other.dump"
        sibling.write_bytes(b"sibling-payload")
        listing = backups.list_backups()
        assert [entry.name for entry in listing.backups] == [
            "before-inference.dump",
            "other.dump",
        ]
        assert listing.backups[0].size_bytes == len(b"backup-payload")
        assert listing.backups[0].modified_at.tzinfo is UTC
        assert backups.delete_backup("before-inference.dump").name == "before-inference.dump"
        assert not target.exists()
        assert sibling.read_bytes() == b"sibling-payload"
        assert outside.read_bytes() == b"outside-sentinel"
        return

    if case == "nested-file":
        backup_root.mkdir(parents=True)
        nested = backup_root / "2026" / "deep.dump"
        nested.parent.mkdir()
        nested.write_bytes(b"nested-payload")
        assert [entry.name for entry in backups.list_backups().backups] == ["2026/deep.dump"]
        assert backups.delete_backup("2026/deep.dump").name == "2026/deep.dump"
        assert not nested.exists()
        assert nested.parent.is_dir()
        return

    if case == "absent-root":
        # No backup is listed, the absent root is not created, and naming a file refuses.
        assert backups.list_backups().backups == ()
        assert not (tmp_path / "data").exists()
        with pytest.raises(ValueError):
            backups.delete_backup("missing.dump")
        assert not (tmp_path / "data").exists()
        return

    if case == "unconfined-name":
        backup_root.mkdir(parents=True)
        listed = backup_root / "kept.dump"
        listed.write_bytes(b"kept-payload")
        for name in (
            "",
            "/absolute.dump",
            ".",
            "..",
            "../outside.dump",
            "nested/../../outside.dump",
            "nested/",
            "nested//deep.dump",
            "nested\\deep.dump",
            "nested\x00deep.dump",
        ):
            with pytest.raises(ValueError):
                backups.delete_backup(name)
        assert listed.read_bytes() == b"kept-payload"
        assert outside.read_bytes() == b"outside-sentinel"
        return

    if case == "symlink":
        backup_root.mkdir(parents=True)
        link = backup_root / "link.dump"
        link.symlink_to(outside)
        with pytest.raises(ValueError):
            backups.list_backups()
        with pytest.raises(ValueError):
            backups.delete_backup("link.dump")
        link.unlink()
        # A symlinked ancestor refuses both operations instead of redirecting them.
        redirected = tmp_path / "redirected"
        redirected.mkdir()
        redirected_file = redirected / "outside.dump"
        redirected_file.write_bytes(b"redirected-sentinel")
        backup_root.rmdir()
        backup_root.symlink_to(redirected, target_is_directory=True)
        with pytest.raises(ValueError):
            backups.list_backups()
        with pytest.raises(ValueError):
            backups.delete_backup("outside.dump")
        assert outside.read_bytes() == b"outside-sentinel"
        assert redirected_file.read_bytes() == b"redirected-sentinel"
        return

    # A special file refuses the listing, and a directory is not a deletable target.
    backup_root.mkdir(parents=True)
    directory = backup_root / "folder"
    directory.mkdir()
    inner = directory / "inside.dump"
    inner.write_bytes(b"inside-payload")
    os.mkfifo(backup_root / "pipe.dump")
    with pytest.raises(ValueError):
        backups.list_backups()
    with pytest.raises(ValueError):
        backups.delete_backup("folder")
    with pytest.raises(ValueError):
        backups.delete_backup("pipe.dump")
    assert inner.read_bytes() == b"inside-payload"
    assert outside.read_bytes() == b"outside-sentinel"
