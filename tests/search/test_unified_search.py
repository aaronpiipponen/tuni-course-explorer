"""Contracts for the unified single-query search composition.

The per-method matching algorithms are proved in `tests/search/test_search_service.py` and
`tests/search/test_course_lookup.py`. This file records dispatch, merge, tagging, tiering, activity, and
score-separation behavior through compact recording fakes over real shared-summary DTOs.
"""

from __future__ import annotations

from decimal import Decimal

from course_explorer.config import SearchSettings
from course_explorer.curriculum import (
    CourseSummary,
    RepresentedCourseSummary,
)
from course_explorer.search.lookup import FuzzyCourseResult
from course_explorer.search.service import CourseSearchResult
from course_explorer.search.unified import UnifiedCourseSearchService
from tests.support import settings_factory

DEFAULT_PRIORITY = ("exact_code", "substring", "fuzzy_name", "semantic")
HASH_A = "a" * 64


def search_settings(priority: tuple[str, ...] = DEFAULT_PRIORITY) -> SearchSettings:
    """Build one required search policy with the given config-owned tier order."""
    return settings_factory(SearchSettings, SEARCH_TIER_PRIORITY=priority)


def summary(group_id: str, *, is_active: bool = True, code: str | None = None) -> CourseSummary:
    """Build one distinct shared official summary keyed by canonical group."""
    return CourseSummary(
        group_id=group_id,
        name_fi=f"Nimi {group_id}",
        name_en=f"Name {group_id}",
        code=code if code is not None else f"CODE.{group_id}",
        credits_min=Decimal("5"),
        credits_max=None,
        is_active=is_active,
        official_url=f"https://example.test/{group_id}",
    )


def represented(course_summary: CourseSummary) -> RepresentedCourseSummary:
    """Wrap one shared summary with a synthetic exact representative identity."""
    return RepresentedCourseSummary(
        summary=course_summary,
        sisu_course_unit_id=f"source-{course_summary.group_id}",
        source_hash=HASH_A,
    )


class FakeCurriculum:
    """Recording stand-in for the one represented-summary read the unified service owns."""

    def __init__(self, records: tuple[RepresentedCourseSummary, ...] = ()) -> None:
        self._records = records
        self.calls: list[bool | None] = []

    def list_represented_summaries(
        self, *, active_only: bool | None = None
    ) -> tuple[RepresentedCourseSummary, ...]:
        self.calls.append(active_only)
        return self._records


class FakeLookup:
    """Recording stand-in for the lookup service returning caller-supplied results."""

    def __init__(
        self,
        *,
        exact: tuple[CourseSummary, ...] = (),
        substring: tuple[CourseSummary, ...] = (),
        fuzzy: tuple[FuzzyCourseResult, ...] = (),
    ) -> None:
        self._exact = exact
        self._substring = substring
        self._fuzzy = fuzzy
        self.calls: list[tuple] = []
        self.represented: list[object] = []

    def exact_code_search(
        self, query, *, display_language, include_inactive=True, represented=None
    ):
        self.calls.append(("exact_code", query, display_language, include_inactive))
        self.represented.append(represented)
        return self._exact

    def substring_search(self, query, *, display_language, include_inactive=True, represented=None):
        self.calls.append(("substring", query, display_language, include_inactive))
        self.represented.append(represented)
        return self._substring

    def fuzzy_name_search(
        self, query, *, display_language, min_score=None, include_inactive=True, represented=None
    ):
        self.calls.append(("fuzzy_name", query, display_language, min_score, include_inactive))
        self.represented.append(represented)
        return self._fuzzy


class FakeSemantic:
    """Recording stand-in for the semantic service returning caller-supplied results."""

    def __init__(self, results: tuple[CourseSearchResult, ...] = ()) -> None:
        self._results = results
        self.calls: list[tuple] = []
        self.represented: list[object] = []

    def search_courses(self, query, *, min_score=None, include_inactive=True, represented=None):
        self.calls.append(("semantic", query, min_score, include_inactive))
        self.represented.append(represented)
        return self._results


def service(
    *,
    priority: tuple[str, ...] = DEFAULT_PRIORITY,
    exact: tuple[CourseSummary, ...] = (),
    substring: tuple[CourseSummary, ...] = (),
    fuzzy: tuple[FuzzyCourseResult, ...] = (),
    semantic: tuple[CourseSearchResult, ...] = (),
    records: tuple[RepresentedCourseSummary, ...] = (),
) -> tuple[UnifiedCourseSearchService, FakeLookup, FakeSemantic, FakeCurriculum]:
    lookup = FakeLookup(exact=exact, substring=substring, fuzzy=fuzzy)
    semantic_service = FakeSemantic(semantic)
    curriculum = FakeCurriculum(records)
    composed = UnifiedCourseSearchService(
        curriculum, semantic_service, lookup, search_settings(priority)
    )
    return composed, lookup, semantic_service, curriculum


def test_unified_search_dispatches_every_method_merges_sources_and_preserves_scores() -> None:
    """Every method receives identical query/language/scope/override once. Merged scores stay separate."""
    shared = summary("group-shared", code="COMP.CS.100")
    exact_only = summary("group-exact", code="COMP.CS.200")

    composed, lookup, semantic, curriculum = service(
        exact=(shared, exact_only),
        substring=(),
        fuzzy=(FuzzyCourseResult(course=shared, score=88.0),),
        semantic=(CourseSearchResult(course=shared, score=0.71),),
    )

    results = composed.search(
        "comp.cs",
        display_language="fi",
        semantic_min_score=0.25,
        fuzzy_min_score=90,
        include_inactive=False,
    )

    assert lookup.calls == [
        ("exact_code", "comp.cs", "fi", False),
        ("substring", "comp.cs", "fi", False),
        ("fuzzy_name", "comp.cs", "fi", 90, False),
    ]
    assert semantic.calls == [("semantic", "comp.cs", 0.25, False)]

    # Exactly one represented-summary read, performed once and shared with all four methods.
    assert curriculum.calls == [True]
    assert len(lookup.represented) == 3
    assert len(semantic.represented) == 1
    assert all(entry is lookup.represented[0] for entry in lookup.represented)
    assert semantic.represented[0] is lookup.represented[0]

    assert [result.course.group_id for result in results] == ["group-shared", "group-exact"]
    merged = results[0]
    assert merged.match_sources == ("exact_code", "fuzzy_name", "semantic")
    assert merged.fuzzy_score == 88.0
    assert merged.semantic_score == 0.71
    assert results[1].match_sources == ("exact_code",)
    assert results[1].fuzzy_score is None
    assert results[1].semantic_score is None
    assert merged.course == shared


def test_unified_search_uses_configured_tiers_then_activity_and_method_order() -> None:
    """Default tier order, activity, primary-method position, and config reordering all hold."""
    active_exact = summary("group-exact-a", is_active=True)
    inactive_exact = summary("group-exact-i", is_active=False)
    substring = summary("group-sub")
    semantic = summary("group-sem")

    composed, _, _, _ = service(
        exact=(inactive_exact, active_exact),
        substring=(substring,),
        semantic=(CourseSearchResult(course=semantic, score=0.5),),
    )
    results = composed.search("q", display_language="en")

    # Exact tier first (active before inactive, then primary-method position), then substring, then semantic.
    assert [result.course.group_id for result in results] == [
        "group-exact-a",
        "group-exact-i",
        "group-sub",
        "group-sem",
    ]

    # Within the fuzzy tier, the source service's relevance order is preserved.
    fuzzy_high = summary("group-fuzzy-high")
    fuzzy_low = summary("group-fuzzy-low")
    fuzzy_order, _, _, _ = service(
        fuzzy=(
            FuzzyCourseResult(course=fuzzy_high, score=95.0),
            FuzzyCourseResult(course=fuzzy_low, score=85.0),
        )
    )
    assert [
        result.course.group_id for result in fuzzy_order.search("q", display_language="en")
    ] == [
        "group-fuzzy-high",
        "group-fuzzy-low",
    ]

    # Changing only the configured priority changes primary tiers and output order.
    reordered, _, _, _ = service(
        priority=("semantic", "substring", "exact_code", "fuzzy_name"),
        exact=(active_exact,),
        semantic=(CourseSearchResult(course=semantic, score=0.5),),
    )
    assert [result.course.group_id for result in reordered.search("q", display_language="en")] == [
        "group-sem",
        "group-exact-a",
    ]


def test_unified_search_returns_every_unique_match_without_a_cap() -> None:
    """No cap discards matches, and every unique exact match is returned once."""
    many = tuple(summary(f"group-{index:02d}") for index in range(15))
    composed, _, _, _ = service(exact=many)
    results = composed.search("q", display_language="fi")
    assert len(results) == 15
