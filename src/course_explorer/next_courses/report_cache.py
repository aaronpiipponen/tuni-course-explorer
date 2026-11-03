"""Supervisor-shared reuse of successful next-course reports in one byte-bounded region.

The cache stores the complete report for one canonical request and the canonical key for each raw
request that resolved to it. Its canonical key carries every input that changes eligibility or
ordering, so the two discovery modes share the cache without sharing an entry. The alias lets a
repeated request answer before its inputs are resolved. Reports and keys are serialized into the
supervisor-owned shared region, so every forked worker reads and writes the same entries. The
region's clock eviction bounds it by bytes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

from course_explorer.next_courses.service import NextCourseMode
from course_explorer.prerequisite.commands import PrerequisiteCalculationBasis
from course_explorer.search.lookup import DisplayLanguage
from course_explorer.shared_cache import SharedByteCache

if TYPE_CHECKING:
    from course_explorer.next_courses.commands import NextCoursesReport


@dataclass(frozen=True, slots=True)
class NextCourseReportKey:
    """The canonical request identity that decides one cached next-course report."""

    selected_group_ids: tuple[str, ...]
    completed_group_ids: tuple[str, ...]
    basis: PrerequisiteCalculationBasis
    mode: NextCourseMode
    display_language: DisplayLanguage
    include_inferred: bool
    active_only: bool


@dataclass(frozen=True, slots=True)
class NextCourseRawKey:
    """The caller's raw request, before its identities are resolved to canonical groups."""

    selected_inputs: tuple[str, ...]
    completed_inputs: tuple[str, ...]
    basis: PrerequisiteCalculationBasis
    mode: NextCourseMode
    display_language: DisplayLanguage
    include_inferred: bool
    active_only: bool


class NextCourseReportCache:
    """Byte-bounded shared cache of successful next-course reports for one dataset."""

    def __init__(self, cache: SharedByteCache) -> None:
        self._cache = cache

    @classmethod
    def create(cls, size: int) -> NextCourseReportCache:
        """Create the supervisor's shared region of the requested byte size."""
        return cls(SharedByteCache.create(size))

    def get(self, key: NextCourseReportKey) -> NextCoursesReport | None:
        """Return the report for one canonical request."""
        payload = self._cache.get(_canonical_bytes(key))
        if payload is None:
            return None
        from course_explorer.next_courses.commands import NextCoursesReport

        return NextCoursesReport.model_validate_json(payload)

    def get_raw(self, raw: NextCourseRawKey) -> NextCoursesReport | None:
        """Return the canonical report for one raw request, or ``None`` when either entry is absent."""
        canonical = self._cache.get(_raw_bytes(raw))
        if canonical is None:
            return None
        payload = self._cache.get(canonical)
        if payload is None:
            return None
        from course_explorer.next_courses.commands import NextCoursesReport

        return NextCoursesReport.model_validate_json(payload)

    def put_raw(
        self,
        raw: NextCourseRawKey,
        canonical: NextCourseReportKey,
        report: NextCoursesReport,
    ) -> None:
        """Retain one report under its canonical key and record the raw request as its alias."""
        canonical_bytes = _canonical_bytes(canonical)
        self._cache.put(canonical_bytes, report.model_dump_json().encode())
        self._cache.put(_raw_bytes(raw), canonical_bytes)

    def close(self) -> None:
        """Release the supervisor's region."""
        self._cache.close()


def _canonical_bytes(key: NextCourseReportKey) -> bytes:
    return (
        b"c"
        + json.dumps(
            [
                list(key.selected_group_ids),
                list(key.completed_group_ids),
                str(key.basis),
                str(key.mode),
                key.display_language,
                key.include_inferred,
                key.active_only,
            ],
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode()
    )


def _raw_bytes(key: NextCourseRawKey) -> bytes:
    return (
        b"r"
        + json.dumps(
            [
                list(key.selected_inputs),
                list(key.completed_inputs),
                str(key.basis),
                str(key.mode),
                key.display_language,
                key.include_inferred,
                key.active_only,
            ],
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode()
    )
