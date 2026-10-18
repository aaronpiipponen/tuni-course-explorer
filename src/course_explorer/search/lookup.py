"""Non-semantic official course lookup: fuzzy displayed name, exact multi-code, substring, and canonical id-or-code resolution.

This module owns the separately callable string-matching methods that compose into the
unified single-query entry point. The query methods read the projected represented-course summary
seam once, unless their caller supplies the sequence a unified search already read. The id-or-code
resolvers instead read a scoped subset through the same seam and the whole-catalogue two-column
`(group_id, code)` projection. Every method maps only represented courses through the shared
`CourseSummary` and returns every qualifying represented course. Matching uses the caller-selected
`display_language`.

The same normalization, official-name resolution and ordering also drive the programme/module
substring lookup over the narrow projected module identity read. Modules have no activity flag and
no result cap.

`DisplayLanguage` is caller-owned because the shared summary retains both official
localized names. A requested official name is used first and the other official name is only a
fallback. A hidden second localized name is never matched when a requested name exists. The fuzzy
cutoff and token weight are config-owned. Whole-title WRatio and query-token coverage use a 0-100 scale, which must not be
blended with the semantic search score scale.
"""

from __future__ import annotations

import re
import unicodedata
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
    module_version_candidates,
)
from course_explorer.enums import ModuleType

DisplayLanguage = Literal["fi", "en"]


class FuzzyCourseResult(BaseModel):
    """One shared official course summary with its RapidFuzz displayed-name similarity score."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    course: CourseSummary
    score: float


def _normalized(value: str) -> str:
    """Apply NFKC, casefolding, and outer trimming only, without other text rewriting."""
    return unicodedata.normalize("NFKC", value).casefold().strip()


def official_display_name(
    summary: CourseSummary | ModuleSummary | CatalogueModuleVersionIdentity,
    display_language: DisplayLanguage,
) -> str | None:
    """Resolve one displayed official name with an explicit other-language fallback."""
    requested = summary.name_fi if display_language == "fi" else summary.name_en
    if requested is not None:
        return requested
    return summary.name_en if display_language == "fi" else summary.name_fi


def name_code_key(
    summary: CourseSummary | ModuleSummary, display_name: str | None
) -> tuple[bool, str, str, str]:
    """Order a course or module by displayed official name then code without fabricating either."""
    code = summary.code if summary.code is not None else ""
    return (
        display_name is None,
        _normalized(display_name) if display_name is not None else "",
        _normalized(code),
        summary.group_id,
    )


def _alphabetical_key(
    course: CourseSummary, display_name: str | None
) -> tuple[bool, bool, str, str, str]:
    """Order active named courses by displayed official name without fabricating a name."""
    return (not course.is_active, *name_code_key(course, display_name))


def _substring_matches(normalized_query: str, display_name: str | None, code: str | None) -> bool:
    """Return whether the normalized query is contained in the displayed name or official code."""
    if code is not None and normalized_query in _normalized(code):
        return True
    return display_name is not None and normalized_query in _normalized(display_name)


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


class CourseLookupService:
    """Fuzzy, exact multi-code, and substring lookup over the official course read seam."""

    def __init__(self, curriculum: CurriculumRead, search_settings: SearchSettings) -> None:
        self._curriculum = curriculum
        self._search_settings = search_settings

    def _represented_summaries(
        self,
        include_inactive: bool,
        represented: Sequence[RepresentedCourseSummary] | None = None,
    ) -> list[RepresentedCourseSummary]:
        """Return represented summaries, reading once only when the caller supplied none."""
        if represented is not None:
            return list(represented)
        return list(
            self._curriculum.list_represented_summaries(
                active_only=None if include_inactive else True
            )
        )

    def fuzzy_name_search(
        self,
        query: str,
        *,
        display_language: DisplayLanguage,
        min_score: float | None = None,
        include_inactive: bool = True,
        represented: Sequence[RepresentedCourseSummary] | None = None,
    ) -> tuple[FuzzyCourseResult, ...]:
        """Return every represented course whose displayed official name is similar enough."""
        threshold = self._search_settings.fuzzy_search_min_score if min_score is None else min_score
        normalized_query = _normalized(query)

        named: list[tuple[CourseSummary, str]] = []
        for record in self._represented_summaries(include_inactive, represented):
            course = record.summary
            display_name = official_display_name(course, display_language)
            if display_name is None:
                continue
            named.append((course, display_name))
        scores = _fuzzy_name_scores(
            normalized_query,
            [_normalized(name) for _, name in named],
            threshold=threshold,
            token_weight=self._search_settings.fuzzy_token_match_weight,
        )
        scored = [
            (course, name, score)
            for (course, name), score in zip(named, scores, strict=True)
            if score >= threshold
        ]

        scored.sort(
            key=lambda item: (
                not item[0].is_active,
                -item[2],
                _normalized(item[1]),
                _normalized(item[0].code),
                item[0].group_id,
            )
        )
        return tuple(FuzzyCourseResult(course=course, score=score) for course, _, score in scored)

    def exact_code_search(
        self,
        query: str,
        *,
        display_language: DisplayLanguage,
        include_inactive: bool = True,
        represented: Sequence[RepresentedCourseSummary] | None = None,
    ) -> tuple[CourseSummary, ...]:
        """Return represented courses whose official code exactly matches one input token (OR)."""
        tokens = {
            normalized
            for token in re.split(r"[,\s]+", query.strip())
            if (normalized := _normalized(token))
        }

        matches = [
            record.summary
            for record in self._represented_summaries(include_inactive, represented)
            if _normalized(record.summary.code) in tokens
        ]
        matches.sort(
            key=lambda course: _alphabetical_key(
                course, official_display_name(course, display_language)
            )
        )
        return tuple(matches)

    def substring_search(
        self,
        query: str,
        *,
        display_language: DisplayLanguage,
        include_inactive: bool = True,
        represented: Sequence[RepresentedCourseSummary] | None = None,
    ) -> tuple[CourseSummary, ...]:
        """Return represented courses whose displayed name or official code contains the query."""
        normalized_query = _normalized(query)

        matches = []
        for record in self._represented_summaries(include_inactive, represented):
            course = record.summary
            if _substring_matches(
                normalized_query, official_display_name(course, display_language), course.code
            ):
                matches.append(course)
        matches.sort(
            key=lambda course: _alphabetical_key(
                course, official_display_name(course, display_language)
            )
        )
        return tuple(matches)

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
            requested_tokens = {_normalized(identifier) for _, identifier in remaining}
            candidate_group_ids: list[str] = []
            seen_candidates: set[str] = set()
            for group_id, code in self._curriculum.list_course_code_identities(
                active_only=active_only
            ):
                if _normalized(code) in requested_tokens and group_id not in seen_candidates:
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
                by_normalized_code.setdefault(_normalized(record.summary.code), []).append(record)

        resolved: list[RepresentedCourseSummary] = []
        for index, identifier in enumerate(materialized):
            canonical = canonical_matches.get(index)
            if canonical is not None:
                resolved.append(canonical)
                continue
            matches = by_normalized_code.get(_normalized(identifier), [])
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


class ModuleLookupService:
    """Substring lookup over the narrow canonical module identity projection.

    It reads `list_module_lookup()` once, selects each canonical module's eligible version through
    the shared `module_version_candidates` rule, matches the displayed official name or code, and
    returns one shared `ModuleSummary` per matching module in canonical order. A module with no
    eligible version is absent, exactly like an unrepresented course. A module with more than one
    eligible versions fail loudly when any eligible version matches, so no version is silently guessed.
    Modules have no activity scope and the result is never capped.
    """

    def __init__(self, curriculum: CurriculumRead, *, academic_year_start: int) -> None:
        self._curriculum = curriculum
        self._academic_year_start = academic_year_start

    def substring_search(
        self, query: str, *, display_language: DisplayLanguage
    ) -> tuple[ModuleSummary, ...]:
        """Return every eligible canonical module whose displayed name or code contains the query."""
        normalized_query = _normalized(query)

        scored: list[tuple[str | None, ModuleSummary]] = []
        for module in self._curriculum.list_module_lookup():
            candidates = module_version_candidates(
                module.versions, academic_year_start=self._academic_year_start
            )
            if not candidates:
                continue
            matching = tuple(
                version
                for version in candidates
                if _substring_matches(
                    normalized_query, official_display_name(version, display_language), version.code
                )
            )
            if not matching:
                continue
            if len(candidates) > 1:
                raise ValueError(
                    f"ambiguous module {module.group_id}: multiple versions for academic year "
                    f"{self._academic_year_start}"
                )
            version = matching[0]
            summary = ModuleSummary(
                group_id=module.group_id,
                sisu_module_id=version.sisu_module_id,
                module_type=version.module_type,
                code=version.code,
                name_fi=version.name_fi,
                name_en=version.name_en,
            )
            scored.append((official_display_name(summary, display_language), summary))

        scored.sort(
            key=lambda item: (
                item[1].module_type is not ModuleType.DEGREE_PROGRAMME,
                *name_code_key(item[1], item[0]),
            )
        )
        return tuple(summary for _, summary in scored)
