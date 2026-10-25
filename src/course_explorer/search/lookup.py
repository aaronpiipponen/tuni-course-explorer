"""Non-semantic official course lookup: fuzzy displayed name, exact multi-code, substring, and canonical id-or-code resolution.

This module owns the separately callable string-matching methods that compose into the
unified single-query entry point. The query methods consume the normalized lookup rows of one
activity scope, taken from the dataset projection when the caller supplies one and read once
otherwise. The id-or-code resolvers instead read a scoped subset through the represented-summary seam
and the whole-catalogue two-column `(group_id, code)` projection. Every method maps only represented
courses through the shared `CourseSummary` and returns every qualifying represented course. Matching
uses the caller-selected `display_language`.

The same normalization, official-name resolution and ordering also drive any caller that narrows
official courses or modules over a supplied projection.

`DisplayLanguage` is caller-owned because the shared summary retains both official
localized names. A requested official name is used first and the other official name is only a
fallback. A hidden second localized name is never matched when a requested name exists. The fuzzy
cutoff and token weight are config-owned. Whole-title WRatio and query-token coverage use a 0-100 scale, which must not be
blended with the semantic search score scale.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict
from rapidfuzz import fuzz, process

from course_explorer.config import SearchSettings
from course_explorer.curriculum import (
    CatalogueModuleVersionIdentity,
    CourseSummary,
    CurriculumRead,
    ModuleSummary,
    RepresentedCourseSummary,
)
from course_explorer.search.projection import (
    CourseLookupRow,
    LookupProjectionCache,
    build_lookup_rows,
    normalized_text,
)

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
    requested = summary.name_fi if display_language == "fi" else summary.name_en
    if requested is not None:
        return requested
    return summary.name_en if display_language == "fi" else summary.name_fi


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


def _row_display_name_key(row: CourseLookupRow, display_language: DisplayLanguage) -> str | None:
    """Return one row's normalized displayed official name with the other-language fallback."""
    requested = row.name_fi_key if display_language == "fi" else row.name_en_key
    if requested is not None:
        return requested
    return row.name_en_key if display_language == "fi" else row.name_fi_key


def _row_name_code_key(
    row: CourseLookupRow, display_language: DisplayLanguage
) -> tuple[bool, str, str, str]:
    """Order one row by its normalized displayed official name, code and canonical group."""
    display_name_key = _row_display_name_key(row, display_language)
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
    query: str, names: Sequence[str], *, threshold: float, token_weight: float
) -> list[float]:
    """Score normalized titles by WRatio and weighted mean query-token coverage."""
    scores = [0.0] * len(names)
    for _, score, index in process.extract(
        query, names, scorer=fuzz.WRatio, processor=None, score_cutoff=threshold, limit=None
    ):
        scores[index] = score
    query_tokens = re.findall(r"\w+", query)
    if not query_tokens or threshold > 100 * token_weight:
        return scores
    title_tokens = [tuple(re.findall(r"\w+", name)) for name in names]
    vocabulary = tuple({token for tokens in title_tokens for token in tokens})
    # Below this bound, even perfect matches for every other query token cannot reach the cutoff.
    token_cutoff = max(
        0.0, len(query_tokens) * threshold / token_weight - 100 * (len(query_tokens) - 1)
    )
    token_scores = {
        token: {
            word: score
            for word, score, _ in process.extract(
                token,
                vocabulary,
                scorer=fuzz.ratio,
                processor=None,
                score_cutoff=token_cutoff,
                limit=None,
            )
        }
        for token in dict.fromkeys(query_tokens)
    }
    for index, tokens in enumerate(title_tokens):
        if scores[index] > 100 * token_weight or not tokens:
            continue
        required = len(query_tokens) * max(threshold, scores[index]) / token_weight
        total = 0.0
        for position, token in enumerate(query_tokens):
            matches = token_scores[token]
            total += max(matches.get(word, 0.0) for word in tokens)
            if total + 100 * (len(query_tokens) - position - 1) < required:
                break
        else:
            scores[index] = max(scores[index], token_weight * total / len(query_tokens))
    return scores


def _scoped_rows(
    rows: Sequence[CourseLookupRow], include_inactive: bool
) -> tuple[CourseLookupRow, ...]:
    """Return the rows of one activity scope."""
    return tuple(row for row in rows if include_inactive or row.summary.is_active)


class CourseLookupService:
    """Fuzzy, exact multi-code, and substring lookup over the official course read seam."""

    def __init__(
        self,
        curriculum: CurriculumRead,
        search_settings: SearchSettings,
        *,
        projection_cache: LookupProjectionCache | None = None,
    ) -> None:
        self._curriculum = curriculum
        self._search_settings = search_settings
        self._projection_cache = projection_cache

    def lookup_rows(
        self,
        *,
        include_inactive: bool,
        represented: Sequence[RepresentedCourseSummary] | None = None,
    ) -> tuple[CourseLookupRow, ...]:
        """Return the normalized rows of one activity scope.

        A supplied projection cache answers first. Otherwise a supplied represented sequence is
        normalized without a read, and without either one represented-summary read supplies the rows.
        """
        if self._projection_cache is not None:
            rows = self._projection_cache.get(self._curriculum).courses
        elif represented is not None:
            rows = build_lookup_rows(tuple(record.summary for record in represented))
        else:
            rows = build_lookup_rows(
                tuple(
                    record.summary
                    for record in self._curriculum.list_represented_summaries(
                        active_only=None if include_inactive else True
                    )
                )
            )
        return _scoped_rows(rows, include_inactive)

    def fuzzy_name_search(
        self,
        query: str,
        *,
        display_language: DisplayLanguage,
        min_score: float | None = None,
        include_inactive: bool = True,
        rows: Sequence[CourseLookupRow] | None = None,
    ) -> tuple[FuzzyCourseResult, ...]:
        """Return every represented course whose displayed official name is similar enough.

        Supplied rows already belong to the requested activity scope, so they are searched as they are.
        """
        threshold = self._search_settings.fuzzy_search_min_score if min_score is None else min_score
        normalized_query = normalized_text(query)
        scoped = rows if rows is not None else self.lookup_rows(include_inactive=include_inactive)

        named: list[tuple[CourseLookupRow, str]] = []
        for row in scoped:
            display_name_key = _row_display_name_key(row, display_language)
            if display_name_key is None:
                continue
            named.append((row, display_name_key))
        scores = _fuzzy_name_scores(
            normalized_query,
            [name_key for _, name_key in named],
            threshold=threshold,
            token_weight=self._search_settings.fuzzy_token_match_weight,
        )
        scored = [
            (row, score)
            for (row, _name_key), score in zip(named, scores, strict=True)
            if score >= threshold
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
        rows: Sequence[CourseLookupRow] | None = None,
    ) -> tuple[CourseSummary, ...]:
        """Return represented courses whose official code exactly matches one input token (OR).

        Supplied rows already belong to the requested activity scope, so they are matched as they are.
        """
        tokens = {
            normalized
            for token in re.split(r"[,\s]+", query.strip())
            if (normalized := normalized_text(token))
        }
        scoped = rows if rows is not None else self.lookup_rows(include_inactive=include_inactive)

        matches = [row for row in scoped if row.code_key in tokens]
        matches.sort(key=lambda row: _alphabetical_key(row, display_language))
        return tuple(row.summary for row in matches)

    def substring_search(
        self,
        query: str,
        *,
        display_language: DisplayLanguage,
        include_inactive: bool = True,
        rows: Sequence[CourseLookupRow] | None = None,
    ) -> tuple[CourseSummary, ...]:
        """Return represented courses whose displayed name or official code contains the query.

        Supplied rows already belong to the requested activity scope, so they are matched as they are.
        """
        normalized_query = normalized_text(query)
        scoped = rows if rows is not None else self.lookup_rows(include_inactive=include_inactive)

        matches = [
            row
            for row in scoped
            if _substring_matches(
                normalized_query, _row_display_name_key(row, display_language), row.code_key
            )
        ]
        matches.sort(key=lambda row: _alphabetical_key(row, display_language))
        return tuple(row.summary for row in matches)

    def resolve_courses(self, identifiers: Collection[str]) -> tuple[RepresentedCourseSummary, ...]:
        """Resolve each input to exactly one canonical represented course record.

        An empty input returns `()` and reads nothing. Otherwise each input is matched first as an
        outer-trimmed exact canonical `group_id` through one scoped summary read, then as an exact
        official code through the whole-catalogue two-column code projection and a second scoped read
        of only the matching candidate identities. Results retain caller order, so a repeated input
        repeats the same record. A blank, unknown or ambiguous input raises `ValueError` naming it
        instead of guessing, and there is no fuzzy, name, substring or multi-code matching.
        """
        return self._resolve_represented_records(identifiers)

    def _resolve_represented_records(
        self, identifiers: Collection[str]
    ) -> tuple[RepresentedCourseSummary, ...]:
        """Resolve each identifier to exactly one represented record over scoped reads.

        Resolve identifiers by exact canonical `group_id` first, then exact current official code. Only inputs without a canonical match need the code projection: the whole
        catalogue's `(group_id, code)` pairs are compared through the one shared normalization to
        collect candidate canonical identities, and only those candidates' represented records are
        loaded. Matching then uses the current representative codes, so a stored version's
        code is not matched on its own. Already-read records are reused by group ID within the call,
        and an all-canonical call skips the code projection entirely.
        """
        materialized = tuple(identifiers)
        if not materialized:
            return ()

        active_only = None
        by_group_id: dict[str, RepresentedCourseSummary] = {}
        canonical_matches: dict[int, RepresentedCourseSummary] = {}
        remaining: list[tuple[int, str]] = []
        trimmed = tuple(identifier.strip() for identifier in materialized)
        for record in self._curriculum.get_represented_summaries(trimmed, active_only=active_only):
            by_group_id.setdefault(record.summary.group_id, record)
        for index, identifier in enumerate(materialized):
            canonical = by_group_id.get(trimmed[index])
            if canonical is not None:
                canonical_matches[index] = canonical
            else:
                remaining.append((index, identifier))

        by_normalized_code: dict[str, list[RepresentedCourseSummary]] = {}
        if remaining:
            requested_tokens = {normalized_text(identifier) for _, identifier in remaining}
            candidate_group_ids: list[str] = []
            seen_candidates: set[str] = set()
            for group_id, code in self._curriculum.list_course_code_identities(
                active_only=active_only
            ):
                if normalized_text(code) in requested_tokens and group_id not in seen_candidates:
                    seen_candidates.add(group_id)
                    candidate_group_ids.append(group_id)
            missing = [group_id for group_id in candidate_group_ids if group_id not in by_group_id]
            for record in self._curriculum.get_represented_summaries(
                missing, active_only=active_only
            ):
                by_group_id.setdefault(record.summary.group_id, record)
            for group_id in candidate_group_ids:
                record = by_group_id.get(group_id)
                if record is None:
                    # An unrepresented canonical course has no current representative code.
                    continue
                by_normalized_code.setdefault(normalized_text(record.summary.code), []).append(
                    record
                )

        resolved: list[RepresentedCourseSummary] = []
        for index, identifier in enumerate(materialized):
            canonical = canonical_matches.get(index)
            if canonical is not None:
                resolved.append(canonical)
                continue
            matches = by_normalized_code.get(normalized_text(identifier), [])
            if not matches:
                raise ValueError(f"unknown official course code {identifier!r}")
            if len(matches) > 1:
                group_ids = ", ".join(sorted(match.summary.group_id for match in matches))
                raise ValueError(
                    f"ambiguous official course code {identifier!r} matches canonical courses: "
                    f"{group_ids}"
                )
            resolved.append(matches[0])
        return tuple(resolved)
