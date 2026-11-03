"""Contract proof that a missing or mismatched native prerequisite library fails the compile call."""

from __future__ import annotations

from pathlib import Path

import pytest

from course_explorer.prerequisite import native_compiler

pytestmark = pytest.mark.usefixtures("native_serving_libraries")


def test_missing_or_mismatched_native_library_fails_compilation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A missing library fails before any read, and a mismatched format version is refused."""
    serving_library = native_compiler._library_path()
    monkeypatch.setattr(native_compiler, "_library_path", lambda: tmp_path / "absent.so")
    with pytest.raises(ValueError):
        native_compiler.compile_direct_many(0, ("target",), (), active_only=False)

    # The loader caches by path, so the same library under another path is configured and
    # version-checked again even when another test already loaded the serving library.
    linked = tmp_path / "libcourse_prerequisite.so"
    linked.symlink_to(serving_library)
    monkeypatch.setattr(native_compiler, "_library_path", lambda: linked)
    monkeypatch.setattr(native_compiler, "FORMAT_VERSION", native_compiler.FORMAT_VERSION + 1)
    with pytest.raises(ValueError, match="mismatched format version"):
        native_compiler.compile_direct_many(0, ("target",), (), active_only=False)
