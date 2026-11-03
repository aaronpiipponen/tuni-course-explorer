"""Non-semantic official course lookup: fuzzy displayed name, exact multi-code and substring.

This module owns the separately callable string-matching methods that compose into the unified
single-query entry point. Fuzzy name lookup scores one numpy score array over the projection's
per-language name lists and positions. The other query methods consume the normalized lookup rows of
one activity scope taken from the dataset projection. Every method maps only represented courses
through the shared `CourseSummary` and returns every qualifying represented course. Matching uses
the caller-selected `display_language`.

The same normalization, official-name resolution and ordering also drive any caller that narrows
official courses or modules over a supplied projection.

`DisplayLanguage` is caller-owned because the shared summary retains both official localized
names. A requested official name is used first and the other official name is only a fallback. A
hidden second localized name is never matched when a requested name exists. The fuzzy cutoff,
token weight and score tie-break weight are config-owned. Whole-name Jaro-Winkler similarity and
query-token coverage use a 0-100 scale, which must not be blended with the semantic search score
scale.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Literal

import numpy
from pydantic import BaseModel, ConfigDict
from rapidfuzz import process
from rapidfuzz.distance import JaroWinkler

from course_explorer.config import SearchSettings
from course_explorer.curriculum import (
    CatalogueModuleVersionIdentity,
    CourseSummary,
    ModuleSummary,
    RepresentedCourseSummary,
)
from course_explorer.search import native_lookup
from course_explorer.search.projection import (
    CourseLookupRow,
    LookupProjection,
    normalized_text,
    official_name,
)
from course_explorer.search.tokens import LookupTokenTable, title_tokens

DisplayLanguage = Literal["fi", "en"]


class FuzzyCourseResult(BaseModel):
    """One shared official course summary with its RapidFuzz displayed-name similarity score."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    course: CourseSummary
    score: float


def official_display_name(
    summary: CourseSummary | ModuleSummary | CatalogueModuleVersionIdentity,
    display_language: DisplayLanguage,
) -> str | None:
    """Resolve one displayed official name with an explicit other-language fallback."""
    return official_name(summary.name_fi, summary.name_en, display_language)


def _ordered_name_code_key(
    display_name: str | None, name_key: str | None, code_key: str, group_id: str
) -> tuple[bool, str, str, str]:
    """Order a course or module by displayed official name then code without fabricating either."""
    return (display_name is None, name_key or "", code_key, group_id)


def name_code_key(
    summary: CourseSummary | ModuleSummary, display_name: str | None
) -> tuple[bool, str, str, str]:
    """Order a course or module by displayed official name then code without fabricating either."""
    return _ordered_name_code_key(
        display_name,
        None if display_name is None else normalized_text(display_name),
        normalized_text(summary.code if summary.code is not None else ""),
        summary.group_id,
    )


def _row_name_code_key(
    row: CourseLookupRow, display_language: DisplayLanguage
) -> tuple[bool, str, str, str]:
    """Order one row by its normalized displayed official name, code and canonical group."""
    display_name_key = official_name(row.name_fi_key, row.name_en_key, display_language)
    return _ordered_name_code_key(
        display_name_key, display_name_key, row.code_key, row.summary.group_id
    )


def _alphabetical_key(
    row: CourseLookupRow, display_language: DisplayLanguage
) -> tuple[bool, bool, str, str, str]:
    """Order active named courses by displayed official name without fabricating a name."""
    return (not row.summary.is_active, *_row_name_code_key(row, display_language))


def _substring_matches(normalized_query: str, display_name_key: str | None, code_key: str) -> bool:
    """Return whether the normalized query is contained in the displayed name or official code."""
    if normalized_query in code_key:
        return True
    return display_name_key is not None and normalized_query in display_name_key


def _fuzzy_name_scores(
    query: str,
    names: Sequence[str],
    positions: numpy.ndarray,
    table: LookupTokenTable,
    *,
    threshold: float,
    token_weight: float,
    tie_break_weight: float,
) -> numpy.ndarray:
    """Score normalized titles by whole-name similarity and weighted query-token coverage.

    Whole-name similarity is Jaro-Winkler, which is symmetric and rewards a shared prefix. A partial
    whole-string ratio rises with the query length against a short title, so Jaro-Winkler supplies
    this signal and token coverage supplies the per-word typo tolerance. The stronger signal decides
    whether a title reaches the cutoff, and the weaker one adds a bounded share of the remaining
    distance to 100, so it orders matches without pushing one below the cutoff.
    """
    coverage = numpy.zeros(len(names), dtype=numpy.float64)
    query_tokens = title_tokens(query)
    if query_tokens and threshold <= 100 * token_weight:
        native_lookup.apply_token_coverage(
            coverage,
            positions,
            table,
            query_tokens,
            threshold=threshold,
            token_weight=token_weight,
        )
    similarity = (
        process.cdist(
            [query], names, scorer=JaroWinkler.normalized_similarity, dtype=numpy.float64
        )[0]
        * 100.0
    )
    stronger = numpy.maximum(coverage, similarity)
    weaker = numpy.minimum(coverage, similarity)
    scores = stronger + tie_break_weight * weaker * (100.0 - stronger) / 100.0
    scores[stronger < threshold] = 0.0
    return scores


class CourseLookupService:
    """Fuzzy, exact multi-code, and substring lookup over one supplied lookup projection."""

    def __init__(
        self,
        search_settings: SearchSettings,
        *,
        projection: LookupProjection,
    ) -> None:
        self._search_settings = search_settings
        self._projection = projection

    def represented_index(
        self, *, include_inactive: bool
    ) -> Mapping[str, RepresentedCourseSummary]:
        """Return the represented records of one activity scope keyed by canonical group.

        The projection's own identity map answers directly, so a semantic pairing reuses it instead
        of rebuilding a catalogue-sized map per query.
        """
        return (
            self._projection.by_group_id
            if include_inactive
            else self._projection.active_by_group_id
        )

    def lookup_rows(self, *, include_inactive: bool) -> tuple[CourseLookupRow, ...]:
        """Return the projection's normalized rows of one activity scope."""
        return self._projection.courses if include_inactive else self._projection.active_courses

    def fuzzy_name_search(
        self,
        query: str,
        *,
        display_language: DisplayLanguage,
        min_score: float | None = None,
        include_inactive: bool = True,
    ) -> tuple[FuzzyCourseResult, ...]:
        """Return every represented course whose displayed official name is similar enough.

        The lookup builds one numpy score array over the projection's searched name list, its
        positions and its token table, and `include_inactive` selects the full or the active list.
        A row without a displayed name is not scored.
        """
        threshold = self._search_settings.fuzzy_search_min_score if min_score is None else min_score
        normalized_query = normalized_text(query)
        if include_inactive:
            names = self._projection.name_keys[display_language]
            positions = self._projection.name_positions[display_language]
        else:
            names = self._projection.active_name_keys[display_language]
            positions = self._projection.active_name_positions[display_language]
        table = self._projection.token_tables[display_language]
        rows_by_position: Sequence[CourseLookupRow] = self._projection.courses
        scores = _fuzzy_name_scores(
            normalized_query,
            names,
            positions,
            table,
            threshold=threshold,
            token_weight=self._search_settings.fuzzy_token_match_weight,
            tie_break_weight=self._search_settings.fuzzy_score_tie_break_weight,
        )
        scored = [
            (rows_by_position[int(positions[index])], float(scores[index]))
            for index in numpy.flatnonzero(scores >= threshold)
        ]

        scored.sort(
            key=lambda item: (
                not item[0].summary.is_active,
                -item[1],
                _row_name_code_key(item[0], display_language),
            )
        )
        return tuple(FuzzyCourseResult(course=row.summary, score=score) for row, score in scored)

    def exact_code_search(
        self,
        query: str,
        *,
        display_language: DisplayLanguage,
        include_inactive: bool = True,
    ) -> tuple[CourseSummary, ...]:
        """Return represented courses whose official code exactly matches one input token (OR)."""
        tokens = {
            normalized
            for token in re.split(r"[,\s]+", query.strip())
            if (normalized := normalized_text(token))
        }
        scoped = self.lookup_rows(include_inactive=include_inactive)

        matches = [row for row in scoped if row.code_key in tokens]
        matches.sort(key=lambda row: _alphabetical_key(row, display_language))
        return tuple(row.summary for row in matches)

    def substring_search(
        self,
        query: str,
        *,
        display_language: DisplayLanguage,
        include_inactive: bool = True,
    ) -> tuple[CourseSummary, ...]:
        """Return represented courses whose displayed name or official code contains the query."""
        normalized_query = normalized_text(query)
        scoped = self.lookup_rows(include_inactive=include_inactive)

        matches = [
            row
            for row in scoped
            if _substring_matches(
                normalized_query,
                official_name(row.name_fi_key, row.name_en_key, display_language),
                row.code_key,
            )
        ]
        matches.sort(key=lambda row: _alphabetical_key(row, display_language))
        return tuple(row.summary for row in matches)
