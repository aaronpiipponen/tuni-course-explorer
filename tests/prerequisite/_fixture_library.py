"""Test support for the fixture-only native prerequisite projector.

The fixture library compiles the identity, projection, record-view and bundle units over an ordered
record bundle. `project_records` sends one bundle to it and materializes the returned record view
through the product materializer. Only the test support under `tests/prerequisite/` imports this
module.
"""

from __future__ import annotations

import ctypes
from pathlib import Path
from typing import TYPE_CHECKING, cast

from course_explorer import administration, native_library
from course_explorer.prerequisite import native_compiler
from course_explorer.prerequisite.projection import PrerequisiteGraphCompilation

if TYPE_CHECKING:
    from course_explorer.prerequisite.graph import DirectPrerequisiteCompilation

FIXTURE_LIBRARY = "libcourse_prerequisite_fixtures.so"
BUILD_GUIDANCE = (
    "run `./.venv/bin/python scripts/build_native.py --fixtures` to build the fixture library"
)


def library_path() -> Path:
    """Return the fixture library path beside the serving libraries."""
    return administration.repository_root() / "native" / FIXTURE_LIBRARY


def _configure(library: ctypes.CDLL):
    """Declare the fixture library's C calls and return its version function."""
    library.course_prerequisite_version.restype = ctypes.c_int32
    library.course_prerequisite_project_records.restype = ctypes.c_void_p
    library.course_prerequisite_project_records.argtypes = [ctypes.c_char_p, ctypes.c_int]
    library.course_prerequisite_structures.restype = ctypes.POINTER(native_compiler._Structure)
    library.course_prerequisite_structures.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_int32),
    ]
    library.course_prerequisite_free_bundle.argtypes = [ctypes.c_void_p]
    library.course_prerequisite_last_error.restype = ctypes.c_char_p
    return library.course_prerequisite_version


def _load() -> ctypes.CDLL:
    return native_library.load(
        library_path(),
        native_compiler.FORMAT_VERSION,
        _configure,
        guidance=BUILD_GUIDANCE,
    )


def project_records(data: bytes) -> PrerequisiteGraphCompilation:
    """Materialize one caller-supplied record bundle through the fixture projector."""
    library = _load()
    pointer = library.course_prerequisite_project_records(data, len(data))
    bundle = native_compiler._materialize(pointer, lightweight=False, library=library)
    try:
        compilation = cast("DirectPrerequisiteCompilation", bundle.structures[0])
        return native_compiler._projection(
            bundle._records[0],
            compilation.solver,
            max_drawing_elements=None,
            include_display=True,
        )
    finally:
        bundle.close()
