"""Load one native library and check its format version.

The serving libraries and the test-only fixture library are built into ``native/`` by
``scripts/build_native.py`` and mapped once per process. A missing library, an unmappable file or a
mismatched format version raises ``ValueError`` naming the build command. The caller's configure
callback declares the C signatures the library needs and returns its version function.
"""

from __future__ import annotations

import ctypes
from collections.abc import Callable
from pathlib import Path

# The build command named by every load failure.
BUILD_GUIDANCE = "run `./.venv/bin/python scripts/build_native.py` to build the native libraries"

_LIBRARIES: dict[Path, ctypes.CDLL] = {}


def load(
    path: Path,
    version: int,
    configure: Callable[[ctypes.CDLL], Callable[[], int]],
    *,
    guidance: str = BUILD_GUIDANCE,
) -> ctypes.CDLL:
    """Return the mapped library at ``path`` after declaring its C calls and checking
    ``version``."""
    library = _LIBRARIES.get(path)
    if library is not None:
        return library
    if not path.is_file():
        raise ValueError(f"native library {path} is missing; {guidance}")
    try:
        library = ctypes.CDLL(str(path))
    except OSError as exc:
        raise ValueError(f"native library {path} cannot be loaded: {exc}; {guidance}") from exc
    native_version = configure(library)
    if native_version() != version:
        raise ValueError(f"native library {path} has a mismatched format version; {guidance}")
    _LIBRARIES[path] = library
    return library
