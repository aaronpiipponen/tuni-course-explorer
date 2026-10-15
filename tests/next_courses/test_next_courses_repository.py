"""Opt-in PostgreSQL proof that the real next-course command uses current direct options."""

from __future__ import annotations

import json
from contextlib import nullcontext
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import Engine

from course_explorer.ingestion.normalization import normalize_curriculum
from course_explorer.ingestion.normalization_repository import NormalizationRepository
from course_explorer.ingestion.repository import CaptureRepository
from course_explorer.next_courses import commands as command_module
from course_explorer.next_courses.commands import NextCoursesReport
from course_explorer.next_courses.service import NextCourseMode
from course_explorer.prerequisite.domain import (
    CourseRequirement,
    EquivalenceGroupMember,
    EquivalenceGroupPublication,
    InferenceNodeMetadata,
    InferredPrerequisiteCategory,
    InferredSetCoverage,
    InferredSetPublication,
    PrerequisiteOrigin,
)
from course_explorer.prerequisite.equivalence_repository import InferredEquivalenceRepository
from course_explorer.prerequisite.repository import InferredPrerequisiteRepository
from course_explorer.recommendations import commands as recommendations_commands
from course_explorer.recommendations.commands import RecommendationsReport
from tests.ingestion._normalization_repository_support import (
    GUIDE_URL,
    build_completed_fixture_store,
    fixture_bytes,
)
from tests.prerequisite._command_support import search_settings
from tests.search._repository_support import embedding_settings

pytestmark = [
    pytest.mark.integration,
]

GENERATED_AT = datetime(2026, 9, 14, 12, 0, tzinfo=UTC)
INPUT_HASH = "a" * 64
EQUIVALENCE_GROUP_ID = UUID("00000000-0000-0000-0000-0000000000aa")
BASIS = ("course-group-a", "course-sub-extra")


def _metadata() -> InferenceNodeMetadata:
    """Build one test-produced inferred node metadata payload without evidence."""
    return InferenceNodeMetadata(confidence=Decimal("0.9"), requirement_ids=("R1",))


def _course_option(*group_ids: str) -> dict[str, object]:
    """Build one course-unit prerequisite option."""
    return {
        "prerequisites": [
            {"type": "CourseUnit", "courseUnitGroupId": group_id} for group_id in group_ids
        ]
    }


def _module_option(module_group_id: str) -> dict[str, object]:
    """Build one module prerequisite option."""
    return {"prerequisites": [{"type": "Module", "moduleGroupId": module_group_id}]}


def _course(
    course_id: str,
    group_id: str,
    code: str,
    *,
    periods: tuple[str, ...],
    prerequisites: tuple[dict[str, object], ...] = (),
    recommended: tuple[dict[str, object], ...] = (),
    substitutions: tuple[object, ...] = (),
) -> dict[str, object]:
    """Build one source-shaped normalized course version."""
    return {
        "id": course_id,
        "groupId": group_id,
        "code": code,
        "name": {"fi": f"Nimi {code}", "en": f"Name {code}"},
        "credits": {"min": 5, "max": 5},
        "curriculumPeriodIds": list(periods),
        "documentState": "ACTIVE",
        "validityPeriod": {"startDate": "2025-01-01", "endDate": "2027-12-31"},
        "metadata": {"revision": 1, "modificationOrdinal": None},
        "content": {"fi": "Sisalto", "en": "Content"},
        "outcomes": {"fi": "Tulos", "en": "Outcome"},
        "prerequisites": {"fi": "Esitieto", "en": "Prerequisite"},
        "additional": {"fi": None, "en": None},
        "compulsoryFormalPrerequisites": list(prerequisites),
        "recommendedFormalPrerequisites": list(recommended),
        "substitutions": list(substitutions),
    }


def _courses_body() -> bytes:
    """Build the source-shaped course catalogue with the discovery routes under test."""
    courses = json.loads(fixture_bytes("courses.json"))
    courses.extend(
        [
            _course("course-sub-extra-v1", "course-sub-extra", "CS.SE", periods=("period-2026",)),
            _course(
                "course-sub-source-v1",
                "course-sub-source",
                "CS.SS",
                periods=("period-2026",),
                substitutions=(
                    [
                        {"courseUnitGroupId": "course-group-a", "credits": None},
                        {"courseUnitGroupId": "course-sub-extra", "credits": None},
                    ],
                ),
            ),
            _course(
                "course-equiv-source-v1",
                "course-equiv-source",
                "CS.ES",
                periods=("period-2026",),
            ),
            _course("course-unrelated-v1", "course-unrelated", "CS.UN", periods=("period-2026",)),
            _course(
                "course-next-direct-v1",
                "course-next-direct",
                "CS.ND",
                periods=("period-2026",),
                prerequisites=(_course_option("course-group-a"),),
            ),
            _course(
                "course-next-recommended-v1",
                "course-next-recommended",
                "CS.NR",
                periods=("period-2026",),
                recommended=(_course_option("course-group-a"),),
            ),
            _course(
                "course-next-module-v1",
                "course-next-module",
                "CS.NM",
                periods=("period-2026",),
                prerequisites=(_module_option("module-group-study"),),
            ),
            _course(
                "course-next-sub-v1",
                "course-next-sub",
                "CS.NS",
                periods=("period-2026",),
                prerequisites=(_course_option("course-sub-source"),),
            ),
            _course(
                "course-next-equiv-v1",
                "course-next-equiv",
                "CS.NE",
                periods=("period-2026",),
                prerequisites=(_course_option("course-equiv-source"),),
            ),
            _course(
                "course-next-inferred-v1",
                "course-next-inferred",
                "CS.NI",
                periods=("period-2026",),
            ),
            _course(
                "course-next-unrelated-v1",
                "course-next-unrelated",
                "CS.NU",
                periods=("period-2026",),
                prerequisites=(_course_option("course-unrelated"),),
            ),
            _course(
                "course-next-inactive-v1",
                "course-next-inactive",
                "CS.NX",
                periods=("period-2020",),
                prerequisites=(_course_option("course-group-a"),),
            ),
            # A stale stored version references the basis course while the current representative
            # does not. The reverse read overselects it, but the compiler must drop it.
            _course(
                "course-next-stale-v1",
                "course-next-stale",
                "CS.NS1",
                periods=("period-2025",),
                prerequisites=(_course_option("course-group-a"),),
            ),
            _course(
                "course-next-stale-v2",
                "course-next-stale",
                "CS.NS2",
                periods=("period-2026",),
                prerequisites=(_course_option("course-unrelated"),),
            ),
        ]
    )
    return json.dumps(courses, sort_keys=True, separators=(",", ":")).encode()


@pytest.fixture
def discovery_catalogue(
    database: tuple[Engine, object], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> object:
    """Normalize and publish the real local catalogue used by command-composition proofs."""
    _, factory = database
    capture_repository = CaptureRepository(factory)
    store = build_completed_fixture_store(
        tmp_path, capture_repository, courses_body=_courses_body()
    )
    normalize_curriculum(
        store,
        NormalizationRepository(factory),
        current_academic_year_start=2026,
        activity_window_years=3,
        course_guide_base_url=GUIDE_URL,
    )

    inferred_repository = InferredPrerequisiteRepository(factory)
    inferred_repository.publish(
        InferredSetPublication(
            target_group_id="course-next-inferred",
            activity_as_of_academic_year_start=2026,
            activity_window_years=3,
            producer_kind="test",
            producer_name="test-fixture",
            producer_version="1",
            input_hash=INPUT_HASH,
            coverage_state="complete",
            coverage=InferredSetCoverage(
                eligible_source_count=1, processed_source_count=1, accepted_source_count=1
            ),
            expression=CourseRequirement(
                type="course",
                origin=PrerequisiteOrigin.INFERRED,
                inferred_category=InferredPrerequisiteCategory.REQUIRED,
                course_group_id="course-group-a",
                inference=_metadata(),
            ),
            generated_at=GENERATED_AT,
        )
    )
    InferredEquivalenceRepository(factory).publish(
        EquivalenceGroupPublication(
            group_id=EQUIVALENCE_GROUP_ID,
            members=tuple(
                EquivalenceGroupMember(
                    course_group_id=group_id,
                    activity_as_of_academic_year_start=2026,
                    activity_window_years=3,
                )
                for group_id in sorted(("course-group-a", "course-equiv-source"))
            ),
            producer_kind="test",
            producer_name="test-fixture",
            producer_version="1",
            input_hash=INPUT_HASH,
            inference=_metadata(),
            generated_at=GENERATED_AT,
        )
    )

    monkeypatch.setattr(command_module, "load_search_settings", search_settings)
    monkeypatch.setattr(recommendations_commands, "load_search_settings", search_settings)
    monkeypatch.setattr(recommendations_commands, "load_embedding_settings", embedding_settings)
    monkeypatch.setattr(recommendations_commands, "load_database_settings", lambda: object())
    monkeypatch.setattr(
        recommendations_commands, "database_context", lambda _settings: nullcontext(factory)
    )

    return factory


def test_real_next_course_command_uses_current_direct_routes(discovery_catalogue: object) -> None:
    """The real command includes current direct options and omits stale/unrelated targets."""
    all_mode = command_module.run_next_courses_command(
        completed_courses=BASIS, display_language="en", include_inferred=True, mode="all"
    )
    assert all_mode.mode is NextCourseMode.ALL
    assert [result.course.group_id for result in all_mode.results] == [
        "course-next-direct",
        "course-next-equiv",
        "course-next-inferred",
        "course-next-module",
        "course-next-recommended",
        "course-next-sub",
    ]
    by_id = {result.course.group_id: result for result in all_mode.results}
    assert by_id["course-next-direct"].required_coverage == 1.0
    assert by_id["course-next-recommended"].recommended_coverage == 1.0
    assert by_id["course-next-module"].required_coverage == 1.0
    assert by_id["course-next-sub"].required_coverage == 1.0
    assert "course-next-stale" not in by_id
    assert "course-next-unrelated" not in by_id
    assert "course-next-inactive" not in by_id


def test_real_next_course_command_preserves_official_wins_attribution(
    discovery_catalogue: object,
) -> None:
    """Official routes win while equivalence-only and inferred-only routes remain marked."""
    report = command_module.run_next_courses_command(
        completed_courses=BASIS, display_language="en", include_inferred=True, mode="all"
    )
    by_id = {result.course.group_id: result for result in report.results}
    assert by_id["course-next-direct"].depends_on_inferred is False
    assert by_id["course-next-equiv"].depends_on_inferred is True
    assert by_id["course-next-inferred"].depends_on_inferred is True


def test_real_at_least_one_command_preserves_coverage_order(discovery_catalogue: object) -> None:
    """At-least-one routes retain the complete coverage order."""
    report = command_module.run_next_courses_command(
        completed_courses=BASIS,
        display_language="en",
        include_inferred=True,
        mode="at_least_one",
    )
    assert [result.course.group_id for result in report.results] == [
        "course-next-direct",
        "course-next-equiv",
        "course-next-inferred",
        "course-next-module",
        "course-next-sub",
        "course-next-recommended",
    ]


def test_real_next_course_all_scope_includes_inactive_candidate(
    discovery_catalogue: object,
) -> None:
    """All-courses includes and labels the inactive candidate."""
    report = command_module.run_next_courses_command(
        completed_courses=BASIS,
        display_language="en",
        include_inferred=True,
        mode="all",
        active_only=False,
    )
    inactive = next(
        result for result in report.results if result.course.group_id == "course-next-inactive"
    )
    assert inactive.course.is_active is False


def test_real_next_course_command_rejects_partial_substitution(discovery_catalogue: object) -> None:
    """A multi-member official substitution is not covered by only one member."""
    partial_substitution = command_module.run_next_courses_command(
        completed_courses=("course-group-a",),
        display_language="en",
        include_inferred=True,
        mode="at_least_one",
    )
    assert "course-next-sub" not in {
        result.course.group_id for result in partial_substitution.results
    }


def test_real_next_course_report_round_trips_serialized_fields(discovery_catalogue: object) -> None:
    """The real report round-trips with the serialized fields."""
    all_mode = command_module.run_next_courses_command(
        completed_courses=BASIS, display_language="en", include_inferred=True, mode="all"
    )
    payload = json.loads(all_mode.model_dump_json())
    assert NextCoursesReport.model_validate_json(all_mode.model_dump_json()) == all_mode
    assert payload["mode"] == "all"
    assert payload["active_only"] is True
    assert payload["include_inferred"] is True
    first = payload["results"][0]
    assert set(first) == {
        "course",
        "required_coverage",
        "recommended_coverage",
        "depends_on_inferred",
    }


@pytest.mark.parametrize(
    "inputs",
    [
        dict(selected_courses=BASIS, completed_courses=(BASIS[0],)),
        dict(completed_courses=BASIS, include_inferred=True, mode="all"),
        dict(completed_courses=BASIS, include_inferred=True, mode="at_least_one"),
        dict(completed_courses=BASIS, include_inferred=True, mode="all", active_only=False),
        dict(selected_courses=BASIS, completed_courses=(BASIS[0],), basis="selected", mode="all"),
    ],
    ids=("completed-subset", "all", "at-least-one", "all-courses", "selected-basis"),
)
def test_recommendations_exclude_same_input_real_next_courses(
    discovery_catalogue: object, inputs: dict[str, object]
) -> None:
    """Recommendations are similarity-only and never repeat a directly produced next course."""
    call_kwargs = {"display_language": "en", **inputs}
    next_report = command_module.run_next_courses_command(**call_kwargs)
    recommendation_report = recommendations_commands.run_recommendations_command(**call_kwargs)
    assert (
        RecommendationsReport.model_validate_json(recommendation_report.model_dump_json())
        == recommendation_report
    )
    next_ids = {result.course.group_id for result in next_report.results}
    assert not next_ids & {
        result.course.group_id for result in recommendation_report.similarity_results
    }
    assert recommendation_report.similarity_results == ()
