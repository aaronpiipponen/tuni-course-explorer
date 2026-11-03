"""Load and call the native fuzzy-name token coverage scorer.

The loader maps one shared library built by ``scripts/build_native.py``. A missing library or a
mismatched format version raises ``ValueError`` naming the build command, and a failed native call
raises ``ValueError`` with the library's last error message. The score array, the row positions and
the token table are passed as contiguous arrays without a copy of the table.
"""

from __future__ import annotations

import ctypes
from collections.abc import Callable, Sequence
from pathlib import Path

import numpy

from course_explorer import administration, native_library
from course_explorer.search.tokens import LookupTokenTable

# Format version the loaded lookup library must report.
FORMAT_VERSION = 1


def _library_path() -> Path:
    return administration.repository_root() / "native" / "libcourse_lookup.so"


def _configure(library: ctypes.CDLL) -> Callable[[], int]:
    library.course_lookup_version.restype = ctypes.c_int32
    library.course_lookup_token_coverage.restype = ctypes.c_int32
    library.course_lookup_token_coverage.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int32,
        ctypes.c_void_p,
        ctypes.c_int32,
        ctypes.c_void_p,
        ctypes.c_int32,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_int32,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_int32,
        ctypes.c_void_p,
        ctypes.c_double,
        ctypes.c_double,
    ]
    library.course_lookup_last_error.restype = ctypes.c_char_p
    return library.course_lookup_version


def _load() -> ctypes.CDLL:
    return native_library.load(_library_path(), FORMAT_VERSION, _configure)


def _pointer(array: numpy.ndarray) -> ctypes.c_void_p:
    return ctypes.c_void_p(array.ctypes.data)


def apply_token_coverage(
    scores: numpy.ndarray,
    positions: numpy.ndarray,
    table: LookupTokenTable,
    query_tokens: Sequence[str],
    *,
    threshold: float,
    token_weight: float,
) -> None:
    """Raise each candidate score by its weighted query-token coverage, in place."""
    codepoints: list[int] = []
    offsets = [0]
    for token in query_tokens:
        codepoints.extend(ord(character) for character in token)
        offsets.append(len(codepoints))
    query_codepoints = numpy.asarray(codepoints, dtype=numpy.int32)
    query_offsets = numpy.asarray(offsets, dtype=numpy.int32)
    library = _load()
    written = library.course_lookup_token_coverage(
        _pointer(positions),
        len(positions),
        _pointer(table.token_offsets),
        len(table.token_offsets) - 1,
        _pointer(table.token_indices),
        len(table.token_indices),
        _pointer(table.vocabulary_codepoints),
        _pointer(table.vocabulary_offsets),
        len(table.vocabulary_offsets) - 1,
        _pointer(query_codepoints),
        _pointer(query_offsets),
        len(query_tokens),
        _pointer(scores),
        threshold,
        token_weight,
    )
    if written < 0:
        message = library.course_lookup_last_error()
        raise ValueError(
            message.decode() if message is not None else "native fuzzy-name coverage failed"
        )
