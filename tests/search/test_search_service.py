"""Contracts for the shared course summary and semantic search service."""

from __future__ import annotations

from decimal import Decimal

import pytest

from course_explorer.curriculum import RepresentedCourseSummary, course_summary
from course_explorer.search.service import SemanticCourseScore
from tests.search._service_support import (
    DIMENSION,
    HASH_A,
    HASH_B,
    course,
    service,
    summary,
    version,
)


def test_course_summary_preserves_localized_official_fields_and_rejects_no_representative() -> None:
    """The shared summary copies both official names and canonical activity. No representative fails."""
    representative = version(
        "course-a-v1",
        name_fi="Lineaarialgebra",
        name_en="Linear algebra",
        code="MATH.1",
        source_hash=HASH_B,
    )
    course_a = course("course-a", representative, is_active=False)

    result = summary(course_a)

    assert result.group_id == "course-a"
    assert result.name_fi == "Lineaarialgebra"
    assert result.name_en == "Linear algebra"
    assert result.code == "MATH.1"
    assert result.credits_min == Decimal("5")
    assert result.credits_max is None
    assert result.is_active is False
    assert result.official_url == "https://example.test/course-a-v1"

    with pytest.raises(ValueError):
        summary(course("course-b", None))


def test_search_uses_config_threshold_current_vectors_and_active_first_order() -> None:
    """Configured threshold, one provider call, current identity filtering, and ordering all hold."""
    active = course(
        "group-active",
        version("source-active", name_fi="Aktiivinen", code="A.1"),
        is_active=True,
    )
    inactive = course(
        "group-inactive",
        version("source-inactive", name_fi="Vanha", code="I.1", source_hash=HASH_B),
        is_active=False,
    )
    obsolete = course(
        "group-obsolete",
        version("source-current", name_fi="Nykyinen", code="O.1", source_hash=HASH_A),
        is_active=True,
    )
    scores = (
        # Stale identity for a current group is ignored rather than paired with current summary.
        SemanticCourseScore(
            group_id="group-obsolete",
            sisu_course_unit_id="source-old",
            representative_source_hash=HASH_B,
            score=0.99,
        ),
        SemanticCourseScore(
            group_id="group-active",
            sisu_course_unit_id="source-active",
            representative_source_hash=HASH_A,
            score=0.55,
        ),
        SemanticCourseScore(
            group_id="group-inactive",
            sisu_course_unit_id="source-inactive",
            representative_source_hash=HASH_B,
            score=0.95,
        ),
        # Score for a group with no current representative is ignored.
        SemanticCourseScore(
            group_id="group-missing",
            sisu_course_unit_id="source-missing",
            representative_source_hash=HASH_A,
            score=0.9,
        ),
    )
    composed, records, repository, provider = service((active, inactive, obsolete), scores)

    results = composed.search_courses(
        "tensorit", represented={record.summary.group_id: record for record in records}
    )

    assert provider.calls == [("tensorit",)]
    assert len(repository.calls) == 1
    vector, threshold, include_inactive, hub = repository.calls[0]
    assert len(vector) == DIMENSION
    assert threshold == 0.4
    assert include_inactive is True
    assert [result.course.group_id for result in results] == ["group-active", "group-inactive"]
    assert [result.score for result in results] == [0.55, 0.95]
    assert results[0].course.code == "A.1"
    assert results[1].course.code == "I.1"


def test_search_override_and_active_only_are_forwarded_without_result_cap() -> None:
    """An override and active-only scope forward exactly, and every qualifying result is returned."""
    courses = tuple(
        course(f"group-{index}", version(f"source-{index}", code=f"C.{index}"))
        for index in range(5)
    )
    scores = tuple(
        SemanticCourseScore(
            group_id=f"group-{index}",
            sisu_course_unit_id=f"source-{index}",
            representative_source_hash=HASH_A,
            score=0.9 - index * 0.05,
        )
        for index in range(5)
    )
    composed, records, repository, _ = service(courses, scores)

    results = composed.search_courses(
        "query",
        represented={record.summary.group_id: record for record in records},
        min_score=0.2,
        include_inactive=False,
    )

    assert repository.calls[0][1] == 0.2
    assert repository.calls[0][2] is False
    assert len(results) == 5


def test_search_pairs_supplied_represented_summaries_by_exact_identity() -> None:
    """A supplied represented sequence is matched by exact identity."""
    active = course("group-active", version("source-active", code="A.1"))
    supplied = (
        RepresentedCourseSummary(
            summary=course_summary(active),
            sisu_course_unit_id="source-active",
            source_hash=HASH_A,
        ),
    )
    scores = (
        SemanticCourseScore(
            group_id="group-active",
            sisu_course_unit_id="source-active",
            representative_source_hash=HASH_A,
            score=0.7,
        ),
        SemanticCourseScore(
            group_id="group-active",
            sisu_course_unit_id="source-stale",
            representative_source_hash=HASH_B,
            score=0.99,
        ),
    )
    composed, _, _, _ = service((active,), scores)

    results = composed.search_courses(
        "query", represented={record.summary.group_id: record for record in supplied}
    )

    assert [result.course.group_id for result in results] == ["group-active"]
    assert [result.score for result in results] == [0.7]
