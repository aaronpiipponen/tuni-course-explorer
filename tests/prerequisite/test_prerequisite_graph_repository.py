"""Opt-in PostgreSQL proof that graph compilation consumes real test-published inferred sets."""

import json
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import Engine, update

from course_explorer.db.models import InferredPrerequisiteSet
from course_explorer.enums import (
    InferredCoverageState,
    InferredProducerKind,
)
from course_explorer.ingestion.normalization import normalize_curriculum
from course_explorer.ingestion.normalization_repository import NormalizationRepository
from course_explorer.ingestion.repository import CaptureRepository
from course_explorer.prerequisite.commands import (
    run_minimum_route_command,
    run_prerequisite_command,
)
from course_explorer.prerequisite.domain import (
    AndRequirement,
    CourseRequirement,
    InferenceNodeMetadata,
    InferredPrerequisiteCategory,
    InferredSetCoverage,
    InferredSetPublication,
    PrerequisiteOrigin,
)
from course_explorer.prerequisite.repository import InferredPrerequisiteRepository
from tests.ingestion._normalization_repository_support import (
    GUIDE_URL,
    build_completed_fixture_store,
)
from tests.prerequisite._command_support import search_settings

pytestmark = [
    pytest.mark.integration,
]

GENERATED_AT = datetime(2026, 9, 14, 12, 0, tzinfo=UTC)
INPUT_HASH = "a" * 64


def _inferred_metadata() -> InferenceNodeMetadata:
    """Build one test-produced inferred node metadata payload without evidence."""
    return InferenceNodeMetadata(confidence=Decimal("0.9"), requirement_ids=("R1",))


def test_inferred_recommended_toggle_matrix_flows_through_postgresql_and_command(
    database: tuple[Engine, object],
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Real normalized curriculum plus a published mixed-category set reach command/path/JSON."""
    _, factory = database
    capture_repository = CaptureRepository(factory)
    store = build_completed_fixture_store(tmp_path, capture_repository)
    normalize_curriculum(
        store,
        NormalizationRepository(factory),
        current_academic_year_start=2026,
        activity_window_years=3,
        course_guide_base_url=GUIDE_URL,
    )

    repository = InferredPrerequisiteRepository(factory)
    target_expression = AndRequirement(
        type="and",
        origin=PrerequisiteOrigin.INFERRED,
        inferred_category=InferredPrerequisiteCategory.REQUIRED,
        inference=_inferred_metadata(),
        children=(
            CourseRequirement(
                type="course",
                origin=PrerequisiteOrigin.INFERRED,
                inferred_category=InferredPrerequisiteCategory.REQUIRED,
                course_group_id="course-group-inactive",
                inference=_inferred_metadata(),
            ),
            CourseRequirement(
                type="course",
                origin=PrerequisiteOrigin.INFERRED,
                inferred_category=InferredPrerequisiteCategory.RECOMMENDED,
                course_group_id="course-group-tie",
                inference=_inferred_metadata(),
            ),
        ),
    )
    repository.publish(
        InferredSetPublication(
            target_group_id="course-group-a",
            activity_as_of_academic_year_start=2026,
            activity_window_years=3,
            producer_kind=InferredProducerKind.TEST,
            producer_name="test-fixture",
            producer_version="1",
            input_hash=INPUT_HASH,
            coverage_state=InferredCoverageState.COMPLETE,
            coverage=InferredSetCoverage(
                eligible_source_count=2,
                processed_source_count=2,
                accepted_source_count=2,
            ),
            expression=target_expression,
            generated_at=GENERATED_AT,
        )
    )

    # The real command composes the real repository/compiler/path over the test factory and
    # serializes both persisted inferred categories on the graph report. Both fixture sources are
    # inactive under the default all-course scope but remain eligible leaves, so neither is activated
    # or published.
    monkeypatch.setattr(
        "course_explorer.prerequisite.commands.load_search_settings", search_settings
    )
    report = run_prerequisite_command("CS.A2", include_inferred=True, include_recommended=True)
    assert report.compilation.tree.root.group_id == "course-group-a"
    assert report.compilation.tree.root.code == "CS.A2"
    assert "path" not in type(report).model_fields
    serialized_edges = json.loads(report.model_dump_json())["compilation"]["graph"]["edges"]
    assert {
        member["inferred_category"]
        for edge in serialized_edges
        for member in edge["relationships"]
        if member["origin"] == PrerequisiteOrigin.INFERRED.value
    } == {"required", "recommended"}

    # The separate explicit route operation owns the new-credit and new-course result.
    route = run_minimum_route_command("CS.A2", include_inferred=True, include_recommended=True)
    assert route.total_new_credits == Decimal("4")
    assert [entry.course.group_id for entry in route.new_courses] == [
        "course-group-inactive",
        "course-group-tie",
    ]

    # A corrupt stored expression fails both real preparations loudly rather than degrading to an
    # official-only report.
    with factory.begin() as session:
        session.execute(update(InferredPrerequisiteSet).values(expression={"type": "unsupported"}))
    with pytest.raises(ValueError):
        run_prerequisite_command("CS.A2", include_inferred=True, include_recommended=True)
    with pytest.raises(ValueError):
        run_minimum_route_command("CS.A2", include_inferred=True, include_recommended=True)
