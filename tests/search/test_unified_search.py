"""Contracts for the unified single-query search composition.

The per-method matching algorithms are proved in `tests/search/test_search_service.py` and
`tests/search/test_course_lookup.py`. This file records dispatch, merge, tagging, tiering, activity,
score-separation, and report availability behavior through compact recording fakes over real
shared-summary DTOs.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from course_explorer.config import SearchSettings
from course_explorer.curriculum import (
    CourseSummary,
    RepresentedCourseSummary,
)
from course_explorer.embeddings.provider import EmbeddingContractError, EmbeddingRequestError
from course_explorer.search.lookup import FuzzyCourseResult
from course_explorer.search.service import CourseSearchResult
from course_explorer.search.unified import UnifiedCourseSearchService
from tests.support import settings_factory

DEFAULT_PRIORITY = ("exact_code", "substring", "fuzzy_name", "semantic")
HASH_A = "a" * 64
SENTINEL_ROWS = ("sentinel-row",)


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
        self.rows: list[object] = []
        self.row_requests: list[tuple[bool, object]] = []

    def lookup_rows(self, *, include_inactive, represented=None):
        self.row_requests.append((include_inactive, represented))
        return SENTINEL_ROWS

    def exact_code_search(self, query, *, display_language, include_inactive=True, rows=None):
        self.calls.append(("exact_code", query, display_language, include_inactive))
        self.rows.append(rows)
        return self._exact

    def substring_search(self, query, *, display_language, include_inactive=True, rows=None):
        self.calls.append(("substring", query, display_language, include_inactive))
        self.rows.append(rows)
        return self._substring

    def fuzzy_name_search(
        self, query, *, display_language, min_score=None, include_inactive=True, rows=None
    ):
        self.calls.append(("fuzzy_name", query, display_language, min_score, include_inactive))
        self.rows.append(rows)
        return self._fuzzy


class FakeSemantic:
    """Recording stand-in for the semantic service returning caller-supplied results or an error."""

    def __init__(
        self, results: tuple[CourseSearchResult, ...] = (), error: BaseException | None = None
    ) -> None:
        self._results = results
        self._error = error
        self.calls: list[tuple] = []
        self.represented: list[object] = []

    def search_courses(self, query, *, min_score=None, include_inactive=True, represented=None):
        self.calls.append(("semantic", query, min_score, include_inactive))
        self.represented.append(represented)
        if self._error is not None:
            raise self._error
        return self._results


def service(
    *,
    priority: tuple[str, ...] = DEFAULT_PRIORITY,
    exact: tuple[CourseSummary, ...] = (),
    substring: tuple[CourseSummary, ...] = (),
    fuzzy: tuple[FuzzyCourseResult, ...] = (),
    semantic: tuple[CourseSearchResult, ...] = (),
    semantic_error: BaseException | None = None,
    records: tuple[RepresentedCourseSummary, ...] = (),
) -> tuple[UnifiedCourseSearchService, FakeLookup, FakeSemantic, FakeCurriculum]:
    lookup = FakeLookup(exact=exact, substring=substring, fuzzy=fuzzy)
    semantic_service = FakeSemantic(semantic, semantic_error)
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

    report = composed.search(
        "comp.cs",
        display_language="fi",
        semantic_min_score=0.25,
        fuzzy_min_score=90,
        include_inactive=False,
    )
    results = report.results

    assert report.semantic_available is True
    # An explicit override replaces the configured threshold in the report.
    assert report.semantic_min_score == 0.25
    assert report.fuzzy_min_score == 90
    assert lookup.calls == [
        ("exact_code", "comp.cs", "fi", False),
        ("substring", "comp.cs", "fi", False),
        ("fuzzy_name", "comp.cs", "fi", 90, False),
    ]
    assert semantic.calls == [("semantic", "comp.cs", 0.25, False)]

    # Exactly one represented-summary read, performed once and shared with the semantic pairing.
    assert curriculum.calls == [True]
    assert len(lookup.row_requests) == 1
    assert lookup.row_requests[0][0] is False
    assert lookup.row_requests[0][1] is semantic.represented[0]
    # One row set serves the three lexical methods.
    assert len(lookup.rows) == 3
    assert all(entry is SENTINEL_ROWS for entry in lookup.rows)
    assert len(semantic.represented) == 1

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
    report = composed.search("q", display_language="en")
    assert report.semantic_available is True
    # With no override the report carries the configured thresholds.
    assert report.semantic_min_score == 0.30
    assert report.fuzzy_min_score == 80
    results = report.results

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
        result.course.group_id for result in fuzzy_order.search("q", display_language="en").results
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
    assert [
        result.course.group_id for result in reordered.search("q", display_language="en").results
    ] == [
        "group-sem",
        "group-exact-a",
    ]


def test_unified_search_returns_every_unique_match_without_a_cap() -> None:
    """No cap discards matches, and every unique exact match is returned once."""
    many = tuple(summary(f"group-{index:02d}") for index in range(15))
    composed, _, _, _ = service(exact=many)
    report = composed.search("q", display_language="fi")
    assert len(report.results) == 15
    # A successful semantic request that matched no course leaves semantic matching available.
    assert report.semantic_available is True


@pytest.mark.parametrize("populated", [True, False])
def test_unified_search_preserves_lexical_matches_when_embedding_is_unavailable(
    populated: bool,
) -> None:
    """An embedding request failure keeps the lexical matches and reports unavailability."""
    shared = summary("group-shared", code="COMP.CS.100")
    exact_only = summary("group-exact", code="COMP.CS.200")
    substring = summary("group-sub")

    composed, _, semantic, curriculum = service(
        exact=(shared, exact_only) if populated else (),
        substring=(substring,) if populated else (),
        fuzzy=(FuzzyCourseResult(course=shared, score=88.0),) if populated else (),
        semantic_error=EmbeddingRequestError("POST /v1/embeddings: transport ReadTimeout"),
    )

    report = composed.search("comp.cs", display_language="fi", semantic_min_score=0.25)

    assert report.semantic_available is False
    assert report.semantic_min_score == 0.25
    assert [result.course.group_id for result in report.results] == (
        ["group-shared", "group-exact", "group-sub"] if populated else []
    )
    assert all("semantic" not in result.match_sources for result in report.results)
    assert all(result.semantic_score is None for result in report.results)
    if populated:
        # Canonical merge and tier order are the available-semantic ones: the shared course keeps
        # its exact and fuzzy sources in one entry and stays ahead of the other exact match.
        assert report.results[0].match_sources == ("exact_code", "fuzzy_name")
        assert report.results[0].fuzzy_score == 88.0
    assert semantic.calls == [("semantic", "comp.cs", 0.25, True)]
    assert curriculum.calls == [None]


def test_unified_search_propagates_non_request_failures() -> None:
    """A non-request failure from the semantic seam propagates instead of a partial report."""
    error = EmbeddingContractError("POST /v1/embeddings: response violates embedding schema")
    composed, _, _, _ = service(semantic_error=error)

    with pytest.raises(EmbeddingContractError) as raised:
        composed.search("q", display_language="en")

    assert raised.value is error
