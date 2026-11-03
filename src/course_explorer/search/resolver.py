"""Resolve caller identifiers to canonical represented course records.

The resolver matches an exact canonical ``group_id`` first and then an exact current official code.
A supplied lookup projection answers both from the dataset projection without a database read.
Otherwise only the inputs without a canonical match need the whole-catalogue ``(group_id, code)``
projection, and only the matching candidate identities are loaded. Results keep caller order, and a
blank, unknown or ambiguous input raises ``ValueError``.
"""

from __future__ import annotations

from collections.abc import Collection

from course_explorer.curriculum import CurriculumRead, RepresentedCourseSummary
from course_explorer.search.projection import (
    LookupProjection,
    normalized_text,
)


class CourseResolver:
    """Resolve canonical ids and exact official codes to represented records."""

    def __init__(
        self, curriculum: CurriculumRead, *, projection: LookupProjection | None = None
    ) -> None:
        self._curriculum = curriculum
        self._projection = projection

    def resolve_courses(self, identifiers: Collection[str]) -> tuple[RepresentedCourseSummary, ...]:
        """Resolve each input to exactly one canonical represented course record.

        An empty input returns `()` and reads nothing. A supplied projection answers the canonical
        identities and the current representative codes without a database read. Otherwise each
        input is matched first as an outer-trimmed exact canonical `group_id` through one scoped
        summary read, then as an exact official code through the whole-catalogue two-column code
        projection and a second scoped read of only the matching candidate identities. Results
        retain caller order, so a repeated input repeats the same record. A blank, unknown or
        ambiguous input raises `ValueError` naming it.
        """
        materialized = tuple(identifiers)
        if not materialized:
            return ()

        active_only = None
        canonical_matches: dict[int, RepresentedCourseSummary] = {}
        remaining: list[tuple[int, str]] = []
        trimmed = tuple(identifier.strip() for identifier in materialized)
        if self._projection is not None:
            by_group_id = self._projection.by_group_id
            for index, identifier in enumerate(materialized):
                canonical = by_group_id.get(trimmed[index])
                if canonical is not None:
                    canonical_matches[index] = canonical
                else:
                    remaining.append((index, identifier))
            by_normalized_code: dict[str, list[RepresentedCourseSummary]] = {}
            if remaining:
                for token in {normalized_text(identifier) for _, identifier in remaining}:
                    matches = self._projection.by_code.get(token)
                    if matches:
                        by_normalized_code[token] = [by_group_id[group] for group in matches]
        else:
            by_group_id = {}
            for record in self._curriculum.get_represented_summaries(
                trimmed, active_only=active_only
            ):
                by_group_id.setdefault(record.summary.group_id, record)
            for index, identifier in enumerate(materialized):
                canonical = by_group_id.get(trimmed[index])
                if canonical is not None:
                    canonical_matches[index] = canonical
                else:
                    remaining.append((index, identifier))

            by_normalized_code = {}
            if remaining:
                requested_tokens = {normalized_text(identifier) for _, identifier in remaining}
                candidate_group_ids: list[str] = []
                seen_candidates: set[str] = set()
                for group_id, code in self._curriculum.list_course_code_identities(
                    active_only=active_only
                ):
                    if (
                        normalized_text(code) in requested_tokens
                        and group_id not in seen_candidates
                    ):
                        seen_candidates.add(group_id)
                        candidate_group_ids.append(group_id)
                missing = [
                    group_id for group_id in candidate_group_ids if group_id not in by_group_id
                ]
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
