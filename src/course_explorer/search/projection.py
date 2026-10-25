"""Immutable normalized lookup projection over the represented course and module reads.

The projection retains the normalized keys the lexical matchers compare, so one serving dataset builds
them once and every query reuses them. It holds no title tokens, code-identity pairs, chunk vectors or
source hashes. One instance belongs to one serving dataset identity.
"""

from __future__ import annotations

import threading
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass

from course_explorer.curriculum import CatalogueModuleLookup, CourseSummary, CurriculumRead


def normalized_text(value: str) -> str:
    """Apply NFKC, casefolding, and outer trimming only, without other text rewriting."""
    return unicodedata.normalize("NFKC", value).casefold().strip()


@dataclass(frozen=True)
class CourseLookupRow:
    """One official course summary with the normalized keys the matchers compare."""

    summary: CourseSummary
    code_key: str
    name_fi_key: str | None
    name_en_key: str | None


@dataclass(frozen=True)
class LookupProjection:
    """One dataset's normalized course rows and projected module identities."""

    courses: tuple[CourseLookupRow, ...]
    modules: tuple[CatalogueModuleLookup, ...]


def build_lookup_rows(records: Sequence[CourseSummary]) -> tuple[CourseLookupRow, ...]:
    """Build one normalized row per supplied summary, without reading anything."""
    return tuple(
        CourseLookupRow(
            summary=record,
            code_key=normalized_text(record.code),
            name_fi_key=None if record.name_fi is None else normalized_text(record.name_fi),
            name_en_key=None if record.name_en is None else normalized_text(record.name_en),
        )
        for record in records
    )


def build_lookup_projection(curriculum: CurriculumRead) -> LookupProjection:
    """Read the represented summaries and the module projection once and normalize the courses."""
    return LookupProjection(
        courses=build_lookup_rows(
            tuple(
                record.summary for record in curriculum.list_represented_summaries(active_only=None)
            )
        ),
        modules=curriculum.list_module_lookup(),
    )


class LookupProjectionCache:
    """The projection one serving dataset built on its first read.

    The cache ignores the supplied curriculum after that read, so it validates no dataset identity and
    holds no engine. Reads are serialized by one lock because the synchronous handlers run in a worker
    thread pool. Its retained size is the dataset projection itself.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._projection: LookupProjection | None = None

    def get(self, curriculum: CurriculumRead) -> LookupProjection:
        """Return the projection this instance built, building it on the first call."""
        with self._lock:
            if self._projection is None:
                self._projection = build_lookup_projection(curriculum)
            return self._projection
