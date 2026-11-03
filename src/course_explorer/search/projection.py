"""Immutable normalized lookup projection over the represented course and module reads.

The projection retains the normalized keys the lexical matchers compare, the identity maps the
id-or-code resolver uses, and the per-language fuzzy-name token tables, name lists and row positions.
The supervisor builds one projection before it forks the workers, and every worker reads the
inherited pages.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy

from course_explorer.curriculum import (
    CatalogueModuleLookup,
    CourseSummary,
    CurriculumRead,
    RepresentedCourseSummary,
)
from course_explorer.search.tokens import LookupTokenTable, build_token_table


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
    """One dataset's normalized course rows, module identities, identity maps and name lists.

    ``by_group_id`` holds every represented record by canonical group, and ``active_by_group_id``
    the active-only subset, so the id-or-code resolver and the semantic pairing answer without a
    database read or a rebuild. A code shared by more than one group is ambiguous.
    ``name_keys`` and ``name_positions`` hold each display language's normalized displayed-name list
    and the row position of every name, and the ``active_`` pair holds the active-only lists.
    ``token_tables`` holds one fuzzy-name token table per display language, aligned with ``courses``.
    """

    courses: tuple[CourseLookupRow, ...]
    active_courses: tuple[CourseLookupRow, ...]
    modules: tuple[CatalogueModuleLookup, ...]
    by_group_id: dict[str, RepresentedCourseSummary] = field(default_factory=dict)
    active_by_group_id: dict[str, RepresentedCourseSummary] = field(default_factory=dict)
    by_code: dict[str, tuple[str, ...]] = field(default_factory=dict)
    token_tables: dict[str, LookupTokenTable] = field(default_factory=dict)
    name_keys: dict[str, tuple[str, ...]] = field(default_factory=dict)
    name_positions: dict[str, numpy.ndarray] = field(default_factory=dict)
    active_name_keys: dict[str, tuple[str, ...]] = field(default_factory=dict)
    active_name_positions: dict[str, numpy.ndarray] = field(default_factory=dict)


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


def official_name(name_fi: str | None, name_en: str | None, display_language: str) -> str | None:
    """Return the requested official name, or the other official name when it is absent."""
    requested = name_fi if display_language == "fi" else name_en
    if requested is not None:
        return requested
    return name_en if display_language == "fi" else name_fi


def build_lookup_projection(curriculum: CurriculumRead) -> LookupProjection:
    """Read the represented summaries and the module projection once and index their identities."""
    represented = curriculum.list_represented_summaries(active_only=None)
    courses = build_lookup_rows(tuple(record.summary for record in represented))
    active_courses = tuple(row for row in courses if row.summary.is_active)
    groups_by_code: dict[str, list[str]] = {}
    for row in courses:
        groups_by_code.setdefault(row.code_key, []).append(row.summary.group_id)
    name_keys: dict[str, tuple[str, ...]] = {}
    name_positions: dict[str, numpy.ndarray] = {}
    active_name_keys: dict[str, tuple[str, ...]] = {}
    active_name_positions: dict[str, numpy.ndarray] = {}
    for language in ("fi", "en"):
        named = tuple(
            (position, key)
            for position, row in enumerate(courses)
            if (key := official_name(row.name_fi_key, row.name_en_key, language)) is not None
        )
        name_keys[language] = tuple(key for _position, key in named)
        name_positions[language] = numpy.asarray(
            [position for position, _key in named], dtype=numpy.int32
        )
        active = tuple(
            (position, key) for position, key in named if courses[position].summary.is_active
        )
        active_name_keys[language] = tuple(key for _position, key in active)
        active_name_positions[language] = numpy.asarray(
            [position for position, _key in active], dtype=numpy.int32
        )
    return LookupProjection(
        courses=courses,
        active_courses=active_courses,
        modules=curriculum.list_module_lookup(),
        by_group_id={record.summary.group_id: record for record in represented},
        active_by_group_id={
            record.summary.group_id: record for record in represented if record.summary.is_active
        },
        by_code={code: tuple(groups) for code, groups in groups_by_code.items()},
        token_tables={
            language: build_token_table(
                tuple(official_name(row.name_fi_key, row.name_en_key, language) for row in courses)
            )
            for language in ("fi", "en")
        },
        name_keys=name_keys,
        name_positions=name_positions,
        active_name_keys=active_name_keys,
        active_name_positions=active_name_positions,
    )
