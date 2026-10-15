"""Opt-in PostgreSQL proofs for transactional normalization and exact reruns."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import func, select

from course_explorer.db.models import (
    Course,
    CourseText,
    CourseVersion,
    CourseVersionCurriculumPeriod,
    CurriculumPeriod,
    ModuleRuleNode,
    ModuleVersion,
    ModuleVersionCurriculumPeriod,
    OfficialPrerequisiteOption,
    OfficialPrerequisiteOptionMember,
    OfficialSubstitutionOption,
    OfficialSubstitutionOptionMember,
    SourceSnapshot,
)
from course_explorer.ingestion.normalization import normalize_curriculum
from course_explorer.ingestion.normalization_repository import NormalizationRepository
from course_explorer.ingestion.repository import CaptureRepository
from tests.ingestion._normalization_repository_support import (
    GUIDE_URL,
    build_completed_fixture_store,
    fixture_bytes,
    normalized_database_digest,
)

pytestmark = [
    pytest.mark.integration,
]


def test_normalization_round_trip_is_idempotent_and_preserves_official_structure(
    database: tuple[object, object], tmp_path: Path
) -> None:
    """Normalizing the same official structure twice is idempotent and preserves every row."""
    _, factory = database
    capture_repository = CaptureRepository(factory)
    normalization_repository = NormalizationRepository(factory)
    store = build_completed_fixture_store(
        tmp_path,
        capture_repository,
        unresolved_course_group_ids=("typed-unresolved-course",),
        unresolved_module_group_ids=("typed-unresolved-module",),
        duplicate_first_course_response=True,
    )

    first = normalize_curriculum(
        store,
        normalization_repository,
        current_academic_year_start=2026,
        activity_window_years=3,
        course_guide_base_url=GUIDE_URL,
    )
    assert first.run_id == store.manifest.run_id
    with factory.begin() as session:
        membership_years = session.execute(
            select(CourseVersion.sisu_course_unit_id, CurriculumPeriod.academic_year_start)
            .join(
                CourseVersionCurriculumPeriod,
                CourseVersionCurriculumPeriod.course_version_id == CourseVersion.id,
            )
            .join(
                CurriculumPeriod,
                CurriculumPeriod.id == CourseVersionCurriculumPeriod.curriculum_period_id,
            )
            .order_by(CourseVersion.sisu_course_unit_id, CurriculumPeriod.academic_year_start)
        ).all()
        assert membership_years == [
            ("course-a-v2", 2026),
            ("course-a-v2", 2027),
            ("course-a-z1", 2025),
            ("course-a-z1", 2026),
            ("course-future-v1", 2027),
            ("course-inactive-v1", 2020),
            ("course-tie-a", 2020),
            ("course-tie-b", 2020),
        ]
        module_membership_years = session.execute(
            select(ModuleVersion.sisu_module_id, CurriculumPeriod.academic_year_start)
            .join(
                ModuleVersionCurriculumPeriod,
                ModuleVersionCurriculumPeriod.module_version_id == ModuleVersion.id,
            )
            .join(
                CurriculumPeriod,
                CurriculumPeriod.id == ModuleVersionCurriculumPeriod.curriculum_period_id,
            )
            .order_by(ModuleVersion.sisu_module_id, CurriculumPeriod.academic_year_start)
        ).all()
        assert module_membership_years == [
            ("module-group-degree-v1", 2026),
            ("module-group-grouping-v1", 2027),
            ("module-group-study-v1", 2025),
            ("module-group-study-v1", 2026),
        ]
        course_a = session.scalar(select(Course).where(Course.group_id == "course-group-a"))
        assert course_a is not None
        assert (course_a.activity_as_of_academic_year_start, course_a.activity_window_years) == (
            2026,
            3,
        )
        courses = {
            course.group_id: course
            for course in session.scalars(
                select(Course).where(
                    Course.group_id.in_(
                        (
                            "course-group-a",
                            "course-group-inactive",
                            "course-group-future",
                            "course-group-tie",
                        )
                    )
                )
            )
        }
        assert {
            group_id: (
                course.first_listed_academic_year_start,
                course.last_listed_academic_year_start,
                course.is_active,
                course.activity_as_of_academic_year_start,
                course.activity_window_years,
            )
            for group_id, course in courses.items()
        } == {
            "course-group-a": (2025, 2027, True, 2026, 3),
            "course-group-inactive": (2020, 2020, False, 2026, 3),
            "course-group-future": (2027, 2027, False, 2026, 3),
            "course-group-tie": (2020, 2020, False, 2026, 3),
        }
        prerequisite_options = session.scalars(
            select(OfficialPrerequisiteOption)
            .join(CourseVersion)
            .where(CourseVersion.sisu_course_unit_id == "course-a-z1")
            .order_by(
                OfficialPrerequisiteOption.requirement_kind, OfficialPrerequisiteOption.option_index
            )
        ).all()
        assert [
            (option.requirement_kind.value, option.option_index) for option in prerequisite_options
        ] == [
            ("compulsory", 0),
            ("compulsory", 1),
            ("recommended", 0),
        ]
        prerequisite_members = session.scalars(
            select(OfficialPrerequisiteOptionMember).where(
                OfficialPrerequisiteOptionMember.prerequisite_option_id.in_(
                    [option.id for option in prerequisite_options]
                )
            )
        ).all()
        prerequisite_members = sorted(
            prerequisite_members,
            key=lambda member: (
                next(
                    index
                    for index, option in enumerate(prerequisite_options)
                    if option.id == member.prerequisite_option_id
                ),
                member.member_index,
            ),
        )
        assert [
            (member.member_index, member.member_type.value) for member in prerequisite_members
        ] == [
            (0, "course"),
            (1, "module"),
            (0, "course"),
            (0, "module"),
        ]
        substitutions = session.scalars(
            select(OfficialSubstitutionOption)
            .join(CourseVersion)
            .where(CourseVersion.sisu_course_unit_id == "course-a-z1")
            .order_by(OfficialSubstitutionOption.option_index)
        ).all()
        assert [option.option_index for option in substitutions] == [0, 1]
        substitution_members = session.scalars(
            select(OfficialSubstitutionOptionMember).where(
                OfficialSubstitutionOptionMember.substitution_option_id.in_(
                    [option.id for option in substitutions]
                )
            )
        ).all()
        substitution_members = sorted(
            substitution_members,
            key=lambda member: (
                next(
                    index
                    for index, option in enumerate(substitutions)
                    if option.id == member.substitution_option_id
                ),
                member.member_index,
            ),
        )
        assert [member.credits for member in substitution_members] == [None, 2.5, 5]
        nodes = session.scalars(
            select(ModuleRuleNode)
            .join(ModuleVersion)
            .where(ModuleVersion.sisu_module_id == "module-group-grouping-v1")
            .order_by(ModuleRuleNode.parent_node_id, ModuleRuleNode.sibling_position)
        ).all()
        root = next(node for node in nodes if node.parent_node_id is None)
        assert root.sibling_position == 0
        assert [node.sibling_position for node in nodes if node.parent_node_id == root.id] == [
            0,
            1,
            2,
            3,
        ]
        credits_node = next(node for node in nodes if node.node_type.value == "CreditsRule")
        count_node = next(node for node in nodes if node.node_type.value == "CourseUnitCountRule")
        course_node = next(node for node in nodes if node.node_type.value == "CourseUnitRule")
        assert credits_node.parent_node_id == root.id and credits_node.sibling_position == 0
        assert count_node.parent_node_id == credits_node.id and count_node.sibling_position == 0
        assert course_node.parent_node_id == count_node.id and course_node.sibling_position == 0
        assert {node.node_type.value for node in nodes} == {
            "CompositeRule",
            "CreditsRule",
            "CourseUnitCountRule",
            "CourseUnitRule",
            "ModuleRule",
            "AnyCourseUnitRule",
            "AnyModuleRule",
        }
    first_digest = normalized_database_digest(factory)
    second = normalize_curriculum(
        store,
        normalization_repository,
        current_academic_year_start=2026,
        activity_window_years=3,
        course_guide_base_url=GUIDE_URL,
    )
    assert second.run_id == store.manifest.run_id

    assert first.new_course_version_count == 6
    assert first.new_module_version_count == 3
    assert first.active_course_count == 1
    assert first.representative_changed_course_count == 3
    assert first.unresolved_course_group_count == 1
    assert first.unresolved_module_group_count == 1
    assert first.unrestricted_rule_count == 2
    assert second.unchanged_course_version_count == 6
    assert second.unchanged_module_version_count == 3
    assert second.new_course_version_count == second.changed_course_version_count == 0
    assert normalized_database_digest(factory) == first_digest

    with factory.begin() as session:
        course = session.scalar(select(Course).where(Course.group_id == "course-group-a"))
        assert course is not None and course.is_active
        unbounded = session.scalar(
            select(CourseVersion.credits_max).where(
                CourseVersion.sisu_course_unit_id == "course-a-v2"
            )
        )
        assert unbounded is None
        assert session.scalar(
            select(ModuleRuleNode).where(ModuleRuleNode.node_type == "AnyModuleRule")
        )


def test_normalization_replaces_changed_versions_and_reports_representative_change(
    database: tuple[object, object], tmp_path: Path
) -> None:
    """Changed source hashes rewrite dependent normalized rows and reselect the representative."""
    _, factory = database
    capture_repository = CaptureRepository(factory)
    normalization_repository = NormalizationRepository(factory)
    first_store = build_completed_fixture_store(tmp_path, capture_repository)
    normalize_curriculum(
        first_store,
        normalization_repository,
        current_academic_year_start=2026,
        activity_window_years=3,
        course_guide_base_url=GUIDE_URL,
    )
    with factory.begin() as session:
        first_version_ids = {
            row.sisu_course_unit_id: row.id for row in session.scalars(select(CourseVersion))
        }
        first_module_ids = {
            row.sisu_module_id: row.id for row in session.scalars(select(ModuleVersion))
        }
        unchanged_text_content = session.scalar(
            select(CourseText.content_en).where(
                CourseText.course_version_id == first_version_ids["course-a-v2"]
            )
        )
        old_prerequisite_ids = set(
            session.scalars(
                select(OfficialPrerequisiteOption.id)
                .join(CourseVersion)
                .where(CourseVersion.sisu_course_unit_id == "course-a-z1")
            )
        )
        old_rule_ids = set(
            session.scalars(
                select(ModuleRuleNode.id)
                .join(ModuleVersion)
                .where(ModuleVersion.sisu_module_id == "module-group-grouping-v1")
            )
        )

    changed_courses: list[dict[str, Any]] = copy.deepcopy(json.loads(fixture_bytes("courses.json")))
    changed_courses[0]["code"] = "CS.A1-CHANGED"
    changed_courses[0]["content"]["en"] = "Changed content"
    changed_courses[0]["metadata"]["modificationOrdinal"] = 10
    changed_courses.append(
        {
            **copy.deepcopy(changed_courses[1]),
            "id": "course-a-v3",
            "code": "CS.A3",
            "metadata": {"revision": 3, "modificationOrdinal": 11},
            "curriculumPeriodIds": ["period-2026"],
        }
    )
    changed_modules: list[dict[str, Any]] = copy.deepcopy(json.loads(fixture_bytes("modules.json")))
    changed_modules[2]["rule"]["rules"][2]["localId"] = "changed-any-course"
    changed_store = build_completed_fixture_store(
        tmp_path,
        capture_repository,
        courses_body=json.dumps(changed_courses, sort_keys=True, separators=(",", ":")).encode(),
        modules_body=json.dumps(changed_modules, sort_keys=True, separators=(",", ":")).encode(),
    )
    report = normalize_curriculum(
        changed_store,
        normalization_repository,
        current_academic_year_start=2026,
        activity_window_years=3,
        course_guide_base_url=GUIDE_URL,
    )

    assert report.changed_course_version_count == 1
    assert report.new_course_version_count == 1
    assert report.changed_module_version_count == 1
    assert report.representative_changed_course_count == 1
    with factory.begin() as session:
        assert (
            session.scalar(
                select(CourseVersion.code).where(CourseVersion.sisu_course_unit_id == "course-a-z1")
            )
            == "CS.A1-CHANGED"
        )
        assert session.scalar(
            select(CourseVersion.id).where(CourseVersion.sisu_course_unit_id == "course-a-v3")
        )
        new_prerequisite_ids = set(
            session.scalars(
                select(OfficialPrerequisiteOption.id)
                .join(CourseVersion)
                .where(CourseVersion.sisu_course_unit_id == "course-a-z1")
            )
        )
        assert new_prerequisite_ids.isdisjoint(old_prerequisite_ids)
        new_rule_ids = set(
            session.scalars(
                select(ModuleRuleNode.id)
                .join(ModuleVersion)
                .where(ModuleVersion.sisu_module_id == "module-group-grouping-v1")
            )
        )
        assert new_rule_ids.isdisjoint(old_rule_ids)
        assert (
            session.scalar(
                select(ModuleRuleNode.local_id).where(
                    ModuleRuleNode.local_id == "changed-any-course"
                )
            )
            == "changed-any-course"
        )
        assert (
            session.scalar(
                select(func.count(SourceSnapshot.id)).where(
                    SourceSnapshot.source_object_id == "course-a-z1"
                )
            )
            == 2
        )

        # Exact versions and module versions keep their exact primary keys. Only the
        # changed course-a-z1 and the added course-a-v3 differ.
        assert {
            row.sisu_course_unit_id: row.id
            for row in session.scalars(
                select(CourseVersion).where(
                    CourseVersion.sisu_course_unit_id.notin_(("course-a-z1", "course-a-v3"))
                )
            )
        } == {
            source_id: version_id
            for source_id, version_id in first_version_ids.items()
            if source_id != "course-a-z1"
        }
        assert {
            row.sisu_module_id: row.id
            for row in session.scalars(
                select(ModuleVersion).where(
                    ModuleVersion.sisu_module_id != "module-group-grouping-v1"
                )
            )
        } == {
            source_id: version_id
            for source_id, version_id in first_module_ids.items()
            if source_id != "module-group-grouping-v1"
        }
        # The untouched exact course keeps its exact text content, while the changed version's
        # dependent payload is rewritten with this fixture's content.
        assert (
            session.scalar(
                select(CourseText.content_en).where(
                    CourseText.course_version_id == first_version_ids["course-a-v2"]
                )
            )
            == unchanged_text_content
        )
        assert (
            session.scalar(
                select(CourseText.content_en).where(
                    CourseText.course_version_id == first_version_ids["course-a-z1"]
                )
            )
            == "Changed content"
        )
