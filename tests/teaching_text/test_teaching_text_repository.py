"""Opt-in PostgreSQL proofs for derived translation persistence and effective-text resolution."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import Engine, event, select

from course_explorer.curriculum_repository import CurriculumRepository
from course_explorer.db.models import (
    Course,
    CourseText,
    CourseVersion,
    CourseVersionCurriculumPeriod,
    DerivedCourseText,
    SourceSnapshot,
)
from course_explorer.db.session import session_scope
from course_explorer.enums import (
    SourceObjectType,
    TeachingTextField,
    TeachingTextLanguage,
    TranslationMethod,
)
from course_explorer.teaching_text.repository import DerivedTranslationRepository
from course_explorer.teaching_text.service import TeachingTextService, teaching_text_sha256
from tests.teaching_text._repository_support import (
    manual_input,
    seed_representative_catalogue,
)

pytestmark = [
    pytest.mark.integration,
]


def test_repository_upserts_reads_and_updates_self_written_translation(
    database: tuple[Engine, object],
) -> None:
    """Imports insert once, a rerun is a no-op, and update only changed translated text."""
    active_source, _ = seed_representative_catalogue(database)
    _, factory = database
    repository = DerivedTranslationRepository(factory)
    first = manual_input(
        active_source,
        TeachingTextField.CONTENT,
        TeachingTextLanguage.EN,
        TeachingTextLanguage.FI,
        "Matriisit",
        "Matrices",
    )
    second = manual_input(
        active_source,
        TeachingTextField.OUTCOMES,
        TeachingTextLanguage.FI,
        TeachingTextLanguage.EN,
        "Use matrices",
        "Käytä matriiseja",
    )

    report = repository.upsert((first, second))
    assert (report.requested_count, report.inserted_count, report.updated_count) == (2, 2, 0)
    assert report.unchanged_count == 0

    with session_scope(factory) as session:
        rows = list(session.scalars(select(DerivedCourseText).order_by(DerivedCourseText.field)))
        identity = {row.field: row.id for row in rows}
        active_version_id = rows[0].course_version_id
        official_before = (
            session.scalar(
                select(CourseVersion.name_fi).where(CourseVersion.id == active_version_id)
            ),
            session.scalar(
                select(CourseText.content_fi).where(
                    CourseText.course_version_id == active_version_id
                )
            ),
            session.scalar(
                select(CourseText.outcomes_en).where(
                    CourseText.course_version_id == active_version_id
                )
            ),
        )
        assert len(rows) == 2
        assert rows[0].source_text_hash == teaching_text_sha256("Matriisit")
        assert rows[1].source_text_hash == teaching_text_sha256("Use matrices")

    assert repository.upsert((first, second)).unchanged_count == 2

    changed = manual_input(
        active_source,
        TeachingTextField.CONTENT,
        TeachingTextLanguage.EN,
        TeachingTextLanguage.FI,
        "Matriisit",
        "Matrices revisited",
    )
    report = repository.upsert((changed, second))
    assert (report.requested_count, report.inserted_count, report.updated_count) == (2, 0, 1)
    assert report.unchanged_count == 1

    with session_scope(factory) as session:
        rows = list(session.scalars(select(DerivedCourseText)))
        assert len(rows) == 2
        assert {row.field: row.id for row in rows} == identity
        persisted = next(row for row in rows if row.field is TeachingTextField.CONTENT)
        assert persisted.text == "Matrices revisited"
        assert (
            session.scalar(
                select(CourseVersion.name_fi).where(CourseVersion.id == active_version_id)
            ),
            session.scalar(
                select(CourseText.content_fi).where(
                    CourseText.course_version_id == active_version_id
                )
            ),
            session.scalar(
                select(CourseText.outcomes_en).where(
                    CourseText.course_version_id == active_version_id
                )
            ),
        ) == official_before

    read = repository.list_for_course_versions((active_source,))
    assert [(row.field, row.language, row.text) for row in read] == [
        (TeachingTextField.CONTENT, TeachingTextLanguage.EN, "Matrices revisited"),
        (TeachingTextField.OUTCOMES, TeachingTextLanguage.FI, "Käytä matriiseja"),
    ]
    assert read[0].source_text_hash == teaching_text_sha256("Matriisit")
    assert read[0].translation_method is TranslationMethod.MANUAL
    assert read[0].translation_model is None
    assert repository.list_for_course_versions(()) == ()


def test_repository_rejects_unknown_nonrepresentative_official_target_and_wrong_source(
    database: tuple[Engine, object],
) -> None:
    """Unknown, persisted non-selected, official-target, and mismatched-source inputs all fail."""
    seed_representative_catalogue(database)
    _, factory = database
    repository = DerivedTranslationRepository(factory)

    with session_scope(factory) as session:
        active_course_id = session.scalar(
            select(Course.id).where(Course.group_id == "course-active")
        )
        active_run_id = session.scalar(
            select(SourceSnapshot.ingestion_run_id)
            .join(CourseVersion, CourseVersion.source_snapshot_id == SourceSnapshot.id)
            .where(CourseVersion.sisu_course_unit_id == "course-active-2026")
        )
        older_snapshot_id = uuid.uuid4()
        session.add(
            SourceSnapshot(
                id=older_snapshot_id,
                ingestion_run_id=active_run_id,
                object_type=SourceObjectType.COURSE_UNIT,
                source_object_id="course-active",
                source_group_id="course-active-2025",
                response_path="courses/teaching-text.json",
                response_item_index=4,
                source_hash="b" * 64,
            )
        )
        session.flush()
        older_version_id = uuid.uuid4()
        session.add(
            CourseVersion(
                id=older_version_id,
                course_id=active_course_id,
                sisu_course_unit_id="course-active-2025",
                code="CODE.0",
                name_fi="Lineaarialgebra",
                credits_min=5,
                credits_max=5,
                official_url="https://example.test/course",
                document_state="ARCHIVED",
                source_snapshot_id=older_snapshot_id,
            )
        )
        session.flush()
        session.add(
            CourseVersionCurriculumPeriod(
                course_version_id=older_version_id, curriculum_period_id="period-2025"
            )
        )

    with session_scope(factory) as session:
        assert (
            session.scalar(
                select(CourseVersion.sisu_course_unit_id).where(
                    CourseVersion.sisu_course_unit_id == "course-active-2025"
                )
            )
            == "course-active-2025"
        )

    def assert_no_rows() -> None:
        with session_scope(factory) as session:
            assert session.scalar(select(DerivedCourseText.id)) is None

    with pytest.raises(ValueError):
        repository.upsert(
            (
                manual_input(
                    "missing-version",
                    TeachingTextField.NAME,
                    TeachingTextLanguage.EN,
                    TeachingTextLanguage.FI,
                    "Lineaarialgebra",
                    "Linear algebra",
                ),
            )
        )
    assert_no_rows()

    with pytest.raises(ValueError):
        repository.upsert(
            (
                manual_input(
                    "course-active-2025",
                    TeachingTextField.NAME,
                    TeachingTextLanguage.EN,
                    TeachingTextLanguage.FI,
                    "Lineaarialgebra",
                    "Linear algebra",
                ),
            )
        )
    assert_no_rows()

    with pytest.raises(ValueError):
        repository.upsert(
            (
                manual_input(
                    "course-active-2026",
                    TeachingTextField.NAME,
                    TeachingTextLanguage.FI,
                    TeachingTextLanguage.EN,
                    "Linear algebra",
                    "Lineaarialgebra",
                ),
            )
        )
    assert_no_rows()

    with pytest.raises(ValueError):
        repository.upsert(
            (
                manual_input(
                    "course-active-2026",
                    TeachingTextField.OUTCOMES,
                    TeachingTextLanguage.FI,
                    TeachingTextLanguage.EN,
                    "Use matrices",
                    "Käytä matriiseja",
                ),
                manual_input(
                    "course-active-2026",
                    TeachingTextField.CONTENT,
                    TeachingTextLanguage.EN,
                    TeachingTextLanguage.FI,
                    "Wrong matrices",
                    "Matrices",
                ),
            )
        )
    assert_no_rows()


def test_real_repository_and_service_resolve_staleness_and_coverage(
    database: tuple[Engine, object],
) -> None:
    """Real seams resolve valid translations, then report and omit a stale cell."""
    active_source, empty_source = seed_representative_catalogue(database)
    engine, factory = database
    repository = DerivedTranslationRepository(factory)
    repository.upsert(
        (
            manual_input(
                active_source,
                TeachingTextField.CONTENT,
                TeachingTextLanguage.EN,
                TeachingTextLanguage.FI,
                "Matriisit",
                "Matrices",
            ),
            manual_input(
                active_source,
                TeachingTextField.OUTCOMES,
                TeachingTextLanguage.FI,
                TeachingTextLanguage.EN,
                "Use matrices",
                "Käytä matriiseja",
            ),
            manual_input(
                "course-inactive-2020",
                TeachingTextField.NAME,
                TeachingTextLanguage.FI,
                TeachingTextLanguage.EN,
                "Programming",
                "Ohjelmointi",
            ),
        )
    )
    service = TeachingTextService(CurriculumRepository(factory), repository)

    catalogue = service.build_catalogue()
    coverage = catalogue.coverage
    assert catalogue.canonical_group_ids == (
        "course-active",
        "course-empty",
        "course-inactive",
        "course-no-period",
    )
    assert coverage.unrepresented_group_ids == ("course-no-period",)
    active_hash = next(
        course.representative_source_hash
        for course in catalogue.courses
        if course.sisu_course_unit_id == active_source
    )
    assert active_hash == "a" * 64
    assert (
        coverage.canonical_course_count,
        coverage.representative_course_count,
        coverage.no_representative_course_count,
    ) == (4, 3, 1)
    assert (coverage.name_only_course_count, coverage.unembeddable_course_count) == (1, 1)
    assert coverage.stale_texts == ()
    # The projected coverage read agrees with the full resolved catalogue and never reads official
    # prerequisite/substitution structures.
    statements: list[str] = []

    def _capture(_conn, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", _capture)
    try:
        projected = service.coverage()
    finally:
        event.remove(engine, "before_cursor_execute", _capture)
    assert projected == coverage
    assert not any(
        "official_prerequisite_options" in statement or "official_substitution_options" in statement
        for statement in statements
    )
    counts = {(count.field, count.language): count for count in coverage.fields}
    assert (
        counts[(TeachingTextField.NAME, TeachingTextLanguage.FI)].official_count,
        counts[(TeachingTextField.NAME, TeachingTextLanguage.FI)].derived_count,
        counts[(TeachingTextField.NAME, TeachingTextLanguage.FI)].stale_count,
        counts[(TeachingTextField.NAME, TeachingTextLanguage.FI)].missing_count,
    ) == (1, 1, 0, 1)
    assert (
        counts[(TeachingTextField.NAME, TeachingTextLanguage.EN)].official_count,
        counts[(TeachingTextField.NAME, TeachingTextLanguage.EN)].derived_count,
        counts[(TeachingTextField.NAME, TeachingTextLanguage.EN)].stale_count,
        counts[(TeachingTextField.NAME, TeachingTextLanguage.EN)].missing_count,
    ) == (1, 0, 0, 2)
    assert (
        counts[(TeachingTextField.CONTENT, TeachingTextLanguage.FI)].official_count,
        counts[(TeachingTextField.CONTENT, TeachingTextLanguage.FI)].derived_count,
        counts[(TeachingTextField.CONTENT, TeachingTextLanguage.FI)].stale_count,
        counts[(TeachingTextField.CONTENT, TeachingTextLanguage.FI)].missing_count,
    ) == (1, 0, 0, 2)
    assert (
        counts[(TeachingTextField.CONTENT, TeachingTextLanguage.EN)].official_count,
        counts[(TeachingTextField.CONTENT, TeachingTextLanguage.EN)].derived_count,
        counts[(TeachingTextField.CONTENT, TeachingTextLanguage.EN)].stale_count,
        counts[(TeachingTextField.CONTENT, TeachingTextLanguage.EN)].missing_count,
    ) == (0, 1, 0, 2)
    assert (
        counts[(TeachingTextField.OUTCOMES, TeachingTextLanguage.FI)].official_count,
        counts[(TeachingTextField.OUTCOMES, TeachingTextLanguage.FI)].derived_count,
        counts[(TeachingTextField.OUTCOMES, TeachingTextLanguage.FI)].stale_count,
        counts[(TeachingTextField.OUTCOMES, TeachingTextLanguage.FI)].missing_count,
    ) == (0, 1, 0, 2)
    assert (
        counts[(TeachingTextField.OUTCOMES, TeachingTextLanguage.EN)].official_count,
        counts[(TeachingTextField.OUTCOMES, TeachingTextLanguage.EN)].derived_count,
        counts[(TeachingTextField.OUTCOMES, TeachingTextLanguage.EN)].stale_count,
        counts[(TeachingTextField.OUTCOMES, TeachingTextLanguage.EN)].missing_count,
    ) == (1, 0, 0, 2)

    active_course = next(
        course for course in catalogue.courses if course.sisu_course_unit_id == active_source
    )
    resolved_cells = {(cell.field, cell.language): cell for cell in active_course.texts}
    assert resolved_cells[(TeachingTextField.CONTENT, TeachingTextLanguage.EN)].text == "Matrices"
    assert resolved_cells[(TeachingTextField.OUTCOMES, TeachingTextLanguage.FI)].text == (
        "Käytä matriiseja"
    )

    with session_scope(factory) as session:
        text = session.get(
            CourseText,
            session.scalar(
                select(CourseVersion.id).where(CourseVersion.sisu_course_unit_id == active_source)
            ),
        )
        assert text is not None
        text.content_fi = "Muuttuneet matriisit"

    catalogue = service.build_catalogue()
    coverage = catalogue.coverage
    assert len(coverage.stale_texts) == 1
    assert service.coverage() == coverage
    stale = coverage.stale_texts[0]
    assert stale.sisu_course_unit_id == active_source
    assert stale.field is TeachingTextField.CONTENT
    assert stale.language is TeachingTextLanguage.EN
    assert stale.source_language is TeachingTextLanguage.FI
    assert stale.stored_source_text_hash == teaching_text_sha256("Matriisit")
    assert stale.current_source_text_hash == teaching_text_sha256("Muuttuneet matriisit")
    counts = {(count.field, count.language): count for count in coverage.fields}
    assert (
        counts[(TeachingTextField.CONTENT, TeachingTextLanguage.EN)].derived_count,
        counts[(TeachingTextField.CONTENT, TeachingTextLanguage.EN)].stale_count,
        counts[(TeachingTextField.CONTENT, TeachingTextLanguage.EN)].missing_count,
    ) == (0, 1, 2)
    assert coverage.name_only_course_count == 1
    assert coverage.unembeddable_course_count == 1
    assert (coverage.canonical_course_count, coverage.representative_course_count) == (4, 3)
    active_course = next(
        course for course in catalogue.courses if course.sisu_course_unit_id == active_source
    )
    assert (TeachingTextField.CONTENT, TeachingTextLanguage.EN) not in {
        (cell.field, cell.language) for cell in active_course.texts
    }
    empty_course = next(
        course for course in catalogue.courses if course.sisu_course_unit_id == empty_source
    )
    assert empty_course.texts == ()
