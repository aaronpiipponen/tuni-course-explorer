"""Shared opt-in PostgreSQL fixtures for the derived-translation repository contracts.

The fixed representative catalogue lets the real persistence and effective-text resolution
paths be exercised against a disposable database.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import Engine

from course_explorer.db.models import (
    Course,
    CourseText,
    CourseVersion,
    CourseVersionCurriculumPeriod,
    CurriculumPeriod,
    IngestionRun,
    SourceSnapshot,
)
from course_explorer.db.session import session_scope
from course_explorer.enums import (
    IngestionRunStatus,
    SourceObjectType,
    TeachingTextField,
    TeachingTextLanguage,
    TranslationMethod,
)
from course_explorer.teaching_text.service import DerivedTranslationInput

GENERATED_AT = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def seed_representative_catalogue(database: tuple[Engine, object]) -> tuple[str, str]:
    """Seed the fixed representative catalogue and return active/empty source IDs."""
    _, factory = database
    run_id = uuid.uuid4()
    period_2026 = "period-2026"
    period_2025 = "period-2025"
    period_2020 = "period-2020"
    group_specs = [
        ("course-active", True, "course-active-2026", (period_2026, period_2025)),
        ("course-inactive", False, "course-inactive-2020", (period_2020,)),
        ("course-empty", False, "course-empty-2020", (period_2020,)),
        ("course-no-period", False, "course-no-period-2020", ()),
    ]
    active_source = "course-active-2026"
    empty_source = "course-empty-2020"
    snapshots = [uuid.uuid4() for _ in group_specs]
    course_ids = [uuid.uuid4() for _ in group_specs]
    version_ids = [uuid.uuid4() for _ in group_specs]

    with session_scope(factory) as session:
        session.add(
            IngestionRun(
                id=run_id,
                status=IngestionRunStatus.COMPLETED,
                raw_root_path="data/raw/run",
                manifest_path="data/raw/run/manifest.json",
            )
        )
        session.add_all(
            [
                CurriculumPeriod(id=period_2026, academic_year_start=2026),
                CurriculumPeriod(id=period_2025, academic_year_start=2025),
                CurriculumPeriod(id=period_2020, academic_year_start=2020),
            ]
        )
        session.add_all(
            [
                SourceSnapshot(
                    id=snapshots[index],
                    ingestion_run_id=run_id,
                    object_type=SourceObjectType.COURSE_UNIT,
                    source_object_id=group_id,
                    source_group_id=source_id,
                    response_path="courses/teaching-text.json",
                    response_item_index=index,
                    source_hash="a" * 64,
                )
                for index, (group_id, _, source_id, _) in enumerate(group_specs)
            ]
        )
        session.flush()
        session.add_all(
            [
                Course(
                    id=course_ids[index],
                    group_id=group_id,
                    is_active=is_active,
                    activity_as_of_academic_year_start=2026,
                    activity_window_years=3,
                )
                for index, (group_id, is_active, _, _) in enumerate(group_specs)
            ]
        )
        session.flush()
        session.add_all(
            [
                CourseVersion(
                    id=version_ids[index],
                    course_id=course_ids[index],
                    sisu_course_unit_id=source_id,
                    code=f"CODE.{index}",
                    name_en=("Programming" if group_id == "course-inactive" else None),
                    name_fi=("Lineaarialgebra" if group_id == "course-active" else None),
                    credits_min=5,
                    credits_max=5,
                    official_url="https://example.test/course",
                    document_state="ACTIVE",
                    source_snapshot_id=snapshots[index],
                )
                for index, (group_id, _, source_id, _) in enumerate(group_specs)
            ]
        )
        session.flush()
        memberships = [
            CourseVersionCurriculumPeriod(
                course_version_id=version_ids[index], curriculum_period_id=period_id
            )
            for index, (_, _, _, periods) in enumerate(group_specs)
            for period_id in periods
        ]
        session.add_all(memberships)
        session.add(
            CourseText(
                course_version_id=version_ids[0],
                content_fi="Matriisit",
                outcomes_en="Use matrices",
            )
        )
    return active_source, empty_source


def manual_input(
    source_id: str,
    field: TeachingTextField,
    language: TeachingTextLanguage,
    source_language: TeachingTextLanguage,
    source_text: str,
    text: str,
) -> DerivedTranslationInput:
    """Build one manual translation input with timezone-aware provenance."""
    return DerivedTranslationInput(
        sisu_course_unit_id=source_id,
        field=field,
        language=language,
        source_language=source_language,
        source_text=source_text,
        text=text,
        translation_method=TranslationMethod.MANUAL,
        generated_at=GENERATED_AT,
    )
