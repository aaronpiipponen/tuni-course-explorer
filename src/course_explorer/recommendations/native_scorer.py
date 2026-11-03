"""Load and marshal the native recommendation scorer.

The loader maps one shared library built by ``scripts/build_native.py``. A missing library or a
mismatched format version raises ``ValueError`` naming the build command, and a failed native call
raises ``ValueError`` with the library's last error message. The function marshals the prepared
basis, the trimmed profile and the ordering keys, and reads each candidate's descriptive chunk rows
straight from the shared serving store. It returns the `SimilarityRecommendation` DTOs defined by
``course_explorer.recommendations.service``.
"""

from __future__ import annotations

import ctypes
from collections.abc import Callable, Sequence
from pathlib import Path

import numpy

from course_explorer import administration, native_library
from course_explorer.config import SearchSettings
from course_explorer.curriculum import RepresentedCourseSummary
from course_explorer.enums import TeachingTextOrigin
from course_explorer.recommendations.service import (
    ChunkRowSource,
    RecommendationBasis,
    SimilarityRecommendation,
    _name_key,
)
from course_explorer.search.lookup import DisplayLanguage

# Format version the loaded scorer library must report.
FORMAT_VERSION = 2


def _calibrated_relatedness(
    raw_percent: float, *, floor_percent: float, ceiling_percent: float
) -> float:
    """Map one raw profile-cosine percentage onto the displayed similarity scale.

    The recommendation floor keeps its own percentage and the configured ceiling reads as 100, so
    a close match lands in the high nineties while the weakest kept candidate stays low. The map is
    monotone, so it changes no recommendation order or cut.
    """
    ratio = min(
        1.0,
        max(0.0, (raw_percent - floor_percent) / (ceiling_percent - floor_percent)),
    )
    return floor_percent + (100.0 - floor_percent) * ratio


class ScoreRequest(ctypes.Structure):
    """The scorer request layout shared with the native library."""

    _fields_ = [
        ("dim", ctypes.c_int32),
        ("basis_rows", ctypes.c_int32),
        ("basis_courses", ctypes.c_int32),
        ("candidate_count", ctypes.c_int32),
        ("chunk_count", ctypes.c_int32),
        ("basis_derived", ctypes.c_int32),
        ("min_relatedness", ctypes.c_double),
        ("near_duplicate_percent", ctypes.c_double),
        ("overlap_floor", ctypes.c_double),
        ("overlap_ceiling", ctypes.c_double),
        ("overlap_weight", ctypes.c_double),
        ("basis_units", ctypes.c_void_p),
        ("basis_course_of_row", ctypes.c_void_p),
        ("profile", ctypes.c_void_p),
        ("hub", ctypes.c_void_p),
        ("outcomes_hub", ctypes.c_void_p),
        ("candidate_offsets", ctypes.c_void_p),
        ("chunk_embeddings", ctypes.c_void_p),
        ("chunk_field", ctypes.c_void_p),
        ("chunk_characters", ctypes.c_void_p),
        ("chunk_derived", ctypes.c_void_p),
        ("key_blob", ctypes.c_void_p),
        ("key_offsets", ctypes.c_void_p),
    ]


class ScoreResult(ctypes.Structure):
    """The scorer result layout shared with the native library."""

    _fields_ = [
        ("candidate_index", ctypes.c_int32),
        ("relatedness", ctypes.c_double),
        ("score", ctypes.c_double),
        ("overlap", ctypes.c_double),
        ("has_overlap", ctypes.c_uint8),
        ("uses_derived", ctypes.c_uint8),
    ]


def _library_path() -> Path:
    return administration.repository_root() / "native" / "libcourse_recommendation.so"


def _configure(library: ctypes.CDLL) -> Callable[[], int]:
    library.course_recommendation_version.restype = ctypes.c_int32
    library.course_recommendation_score.restype = ctypes.c_int32
    library.course_recommendation_score.argtypes = [
        ctypes.POINTER(ScoreRequest),
        ctypes.POINTER(ScoreResult),
        ctypes.c_int32,
    ]
    library.course_recommendation_last_error.restype = ctypes.c_char_p
    return library.course_recommendation_version


def _load() -> ctypes.CDLL:
    return native_library.load(_library_path(), FORMAT_VERSION, _configure)


def _pointer(array: numpy.ndarray | None) -> ctypes.c_void_p | None:
    return None if array is None else ctypes.c_void_p(array.ctypes.data)


def score_candidates(
    candidates: Sequence[RepresentedCourseSummary],
    chunk_rows: ChunkRowSource,
    *,
    display_language: DisplayLanguage,
    settings: SearchSettings,
    hub: Sequence[float],
    outcomes_hub: Sequence[float],
    basis: RecommendationBasis,
) -> tuple[SimilarityRecommendation, ...]:
    """Return the ranked recommendation DTOs from one native call."""
    if basis.profile is None:
        return ()
    dim = len(hub)
    position: dict[str, int] = {}
    for chunk in basis.basis_descriptive:
        position.setdefault(chunk.group_id, len(position))
    basis_course_of_row = numpy.asarray(
        [position[chunk.group_id] for chunk in basis.basis_descriptive], dtype=numpy.int32
    )
    basis_units = numpy.ascontiguousarray(basis.basis_units, dtype=numpy.float64)
    profile = numpy.ascontiguousarray(basis.profile, dtype=numpy.float64)
    hub_array = numpy.ascontiguousarray(hub, dtype=numpy.float64)
    outcomes_array = numpy.ascontiguousarray(outcomes_hub, dtype=numpy.float64)

    offsets = [0]
    index_rows: list[numpy.ndarray] = []
    for record in candidates:
        span = chunk_rows.chunk_span(
            (record.summary.group_id, record.sisu_course_unit_id, record.source_hash)
        )
        start, count = span if span is not None else (0, 0)
        index_rows.append(numpy.arange(start, start + count, dtype=numpy.intp))
        offsets.append(offsets[-1] + count)
    indices = (
        numpy.concatenate(index_rows)
        if index_rows and offsets[-1]
        else numpy.empty(0, dtype=numpy.intp)
    )
    embeddings, fields, characters, derived = chunk_rows.descriptive_rows(indices)
    embeddings = numpy.ascontiguousarray(embeddings, dtype=numpy.float64)
    offsets_array = numpy.asarray(offsets, dtype=numpy.int32)

    blob = bytearray()
    key_offsets: list[int] = []
    for record in candidates:
        missing, name, code, group = _name_key(record, display_language)
        name_bytes = name.encode()
        code_bytes = code.encode()
        group_bytes = group.encode()
        key_offsets.append(len(blob))
        blob.append(1 if missing else 0)
        blob += len(name_bytes).to_bytes(4, "little")
        blob += len(code_bytes).to_bytes(4, "little")
        blob += len(group_bytes).to_bytes(4, "little")
        blob += name_bytes + code_bytes + group_bytes
    key_offsets.append(len(blob))
    key_blob = (ctypes.c_char * len(blob)).from_buffer(blob)
    key_offsets_array = numpy.asarray(key_offsets, dtype=numpy.int64)

    request = ScoreRequest(
        dim=dim,
        basis_rows=len(basis.basis_descriptive),
        basis_courses=basis.course_count,
        candidate_count=len(candidates),
        chunk_count=int(offsets[-1]),
        basis_derived=1
        if any(chunk.text_origin is TeachingTextOrigin.DERIVED for chunk in basis.basis_descriptive)
        else 0,
        min_relatedness=float(settings.recommendation_min_relatedness),
        near_duplicate_percent=float(settings.recommendation_near_duplicate_percent),
        overlap_floor=float(settings.comparison_overlap_floor),
        overlap_ceiling=float(settings.comparison_overlap_ceiling),
        overlap_weight=float(settings.recommendation_overlap_penalty_weight),
        basis_units=_pointer(basis_units),
        basis_course_of_row=_pointer(basis_course_of_row),
        profile=_pointer(profile),
        hub=_pointer(hub_array),
        outcomes_hub=_pointer(outcomes_array),
        candidate_offsets=_pointer(offsets_array),
        chunk_embeddings=_pointer(embeddings),
        chunk_field=_pointer(fields),
        chunk_characters=_pointer(characters),
        chunk_derived=_pointer(derived),
        key_blob=ctypes.cast(key_blob, ctypes.c_void_p),
        key_offsets=_pointer(key_offsets_array),
    )
    library = _load()
    results = (ScoreResult * max(1, len(candidates)))()
    count = library.course_recommendation_score(ctypes.byref(request), results, len(candidates))
    if count < 0:
        message = library.course_recommendation_last_error()
        raise ValueError(message.decode() if message is not None else "native scorer failed")
    floor_percent = settings.recommendation_min_relatedness * 100
    ceiling_percent = settings.recommendation_relatedness_ceiling * 100
    output = []
    for index in range(count):
        result = results[index]
        record = candidates[result.candidate_index]
        output.append(
            SimilarityRecommendation(
                course=record.summary,
                relatedness=_calibrated_relatedness(
                    result.relatedness,
                    floor_percent=floor_percent,
                    ceiling_percent=ceiling_percent,
                ),
                score=result.score,
                overlap_with_basis=result.overlap if result.has_overlap else None,
                uses_derived_text=bool(result.uses_derived),
            )
        )
    return tuple(output)
