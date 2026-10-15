"""Contracts for derived translation storage and effective teaching text."""

from __future__ import annotations

import pytest

from course_explorer.curriculum import CatalogueCourse, CatalogueTeachingCourse
from course_explorer.enums import (
    TeachingTextField,
    TeachingTextLanguage,
    TranslationMethod,
)
from course_explorer.teaching_text.service import (
    StaleDerivedText,
    TeachingTextOrigin,
    TeachingTextService,
    teaching_text_sha256,
)
from tests.embeddings._repository_support import embedding_settings
from tests.teaching_text._support import (
    GENERATED_AT,
    FakeCurriculum,
    FakeTranslations,
    build,
    course,
    translation,
    version,
)


def test_teaching_text_sha256_preserves_exact_official_bytes() -> None:
    """Hashing preserves exact UTF-8 bytes, including a trailing space."""
    assert teaching_text_sha256("Matriisit") == (
        "d6863e19bde25c03f00c9570b8b9fc9eea96e562ce16cbefead9767c3a11ebd8"
    )
    assert teaching_text_sha256("Matriisit ") == (
        "636907f86438d4f6fe5860cce9dc48fb53453a8bf01193328385a55c54620403"
    )


def test_effective_text_prefers_official_and_uses_current_derived_fallback() -> None:
    """Official target wins, a current-hash derived target supplies provenance, prereqs absent."""
    representative = version(
        "course-a-v1",
        name_fi="Lineaarialgebra",
        content_fi="Matriisit",
        outcomes_en="Use matrices",
    )
    rows = (
        translation(
            "course-a-v1",
            TeachingTextField.NAME,
            TeachingTextLanguage.EN,
            TeachingTextLanguage.FI,
            "Lineaarialgebra",
            "Linear algebra",
        ),
        translation(
            "course-a-v1",
            TeachingTextField.CONTENT,
            TeachingTextLanguage.EN,
            TeachingTextLanguage.FI,
            "Matriisit",
            "Matrices",
        ),
        translation(
            "course-a-v1",
            TeachingTextField.NAME,
            TeachingTextLanguage.FI,
            TeachingTextLanguage.EN,
            "Unrelated English",
            "Wrong derived Finnish",
        ),
    )
    catalogue = build((course("course-a", representative),), rows)

    resolved = catalogue.courses[0]
    assert [(cell.field, cell.language) for cell in resolved.texts] == [
        (TeachingTextField.NAME, TeachingTextLanguage.FI),
        (TeachingTextField.NAME, TeachingTextLanguage.EN),
        (TeachingTextField.CONTENT, TeachingTextLanguage.FI),
        (TeachingTextField.CONTENT, TeachingTextLanguage.EN),
        (TeachingTextField.OUTCOMES, TeachingTextLanguage.EN),
    ]
    by_key = {(cell.field, cell.language): cell for cell in resolved.texts}
    official_name = by_key[(TeachingTextField.NAME, TeachingTextLanguage.FI)]
    assert official_name.origin is TeachingTextOrigin.OFFICIAL
    assert official_name.text == "Lineaarialgebra"
    assert official_name.text_hash == official_name.source_text_hash
    assert official_name.translation_method is None
    assert official_name.translation_generated_at is None
    derived_name = by_key[(TeachingTextField.NAME, TeachingTextLanguage.EN)]
    assert derived_name.origin is TeachingTextOrigin.DERIVED
    assert derived_name.text == "Linear algebra"
    assert derived_name.text_hash == teaching_text_sha256("Linear algebra")
    assert derived_name.source_text_hash == teaching_text_sha256("Lineaarialgebra")
    assert derived_name.translation_method is TranslationMethod.MANUAL
    assert derived_name.translation_generated_at == GENERATED_AT
    assert by_key[(TeachingTextField.CONTENT, TeachingTextLanguage.EN)].origin is (
        TeachingTextOrigin.DERIVED
    )


def test_supplied_catalogue_reuses_resolution_without_another_course_read() -> None:
    """A supplied course tuple reuses one read and yields the identical catalogue and coverage."""
    from course_explorer.inference.operational import prepare_operational_catalogue

    class CountingCurriculum(FakeCurriculum):
        def __init__(self, courses: tuple[CatalogueCourse, ...]) -> None:
            super().__init__(courses)
            self.reads = 0

        def list_teaching_courses(
            self, *, active_only: bool | None = None
        ) -> tuple[CatalogueTeachingCourse, ...]:
            self.reads += 1
            return super().list_teaching_courses(active_only=active_only)

    courses = (
        course(
            "course-a", version("course-a-2026", name_fi="Lineaarialgebra", content_fi="Matriisit")
        ),
        course("course-b", None),
        course("course-c", version("course-c-2026", name_en="Programming"), is_active=False),
    )
    curriculum = CountingCurriculum(courses)
    service = TeachingTextService(curriculum, FakeTranslations(()))

    default = service.build_catalogue()
    assert curriculum.reads == 1
    supplied = service.build_catalogue(courses=courses)
    assert curriculum.reads == 1  # no second course read
    assert supplied == default
    # The real unrepresented course is in the canonical set with no fabricated effective text.
    assert supplied.canonical_group_ids == ("course-a", "course-b", "course-c")
    assert supplied.coverage.unrepresented_group_ids == ("course-b",)
    assert {resolved.group_id for resolved in supplied.courses} == {"course-a", "course-c"}
    # An ordinary missing teaching-text cell is absent rather than fabricated.
    resolved_c = next(item for item in supplied.courses if item.group_id == "course-c")
    assert [(cell.field, cell.language) for cell in resolved_c.texts] == [
        (TeachingTextField.NAME, TeachingTextLanguage.EN)
    ]

    embedding = embedding_settings()
    counting = CountingCurriculum(courses)
    operational = prepare_operational_catalogue(
        counting, TeachingTextService(counting, FakeTranslations(())), embedding
    )
    # Operational preparation reads the canonical catalogue exactly once, then reuses that tuple.
    assert counting.reads == 1
    assert set(operational.courses_by_group) == {"course-a", "course-b", "course-c"}
    assert set(operational.effective_by_group) == {"course-a", "course-c"}


def test_effective_text_rejects_duplicate_persisted_keys() -> None:
    """Ambiguous duplicate persisted keys fail instead of silently choosing one row."""
    representative = version("course-a-v1", name_fi="Lineaarialgebra")
    duplicate = (
        translation(
            "course-a-v1",
            TeachingTextField.NAME,
            TeachingTextLanguage.EN,
            TeachingTextLanguage.FI,
            "Lineaarialgebra",
            "Linear algebra",
        ),
        translation(
            "course-a-v1",
            TeachingTextField.NAME,
            TeachingTextLanguage.EN,
            TeachingTextLanguage.FI,
            "Lineaarialgebra",
            "Linear algebra (duplicate)",
        ),
    )
    with pytest.raises(ValueError):
        build((course("course-a", representative),), duplicate)


def test_projected_coverage_matches_shared_resolution_without_full_course_reads() -> None:
    """The projected coverage read equals the shared resolver and never materializes full courses."""
    official = version("course-official", name_fi="Lineaarialgebra", content_fi="Matriisit")
    derived = version("course-derived", content_fi="Ohjelmointi")
    stale = version("course-stale")
    name_only = version("course-name-only", name_fi="Vain nimi")
    empty = version("course-empty")
    rows = (
        translation(
            "course-derived",
            TeachingTextField.CONTENT,
            TeachingTextLanguage.EN,
            TeachingTextLanguage.FI,
            "Ohjelmointi",
            "Programming",
        ),
        translation(
            "course-stale",
            TeachingTextField.CONTENT,
            TeachingTextLanguage.EN,
            TeachingTextLanguage.FI,
            "Vanha sisältö",
            "Old content",
        ),
    )
    courses = (
        course("course-official", official),
        course("course-derived", derived),
        course("course-stale", stale),
        course("course-name-only", name_only),
        course("course-empty", empty),
        course("course-unrepresented", None),
    )
    shared = (
        TeachingTextService(FakeCurriculum(courses), FakeTranslations(rows))
        .build_catalogue()
        .coverage
    )
    projected_service = TeachingTextService(FakeCurriculum(courses), FakeTranslations(rows))
    projected = projected_service.coverage()
    assert projected == shared
    assert projected.canonical_course_count == 6
    assert projected.no_representative_course_count == 1
    assert projected.stale_texts == (
        StaleDerivedText(
            group_id="course-stale",
            sisu_course_unit_id="course-stale",
            field=TeachingTextField.CONTENT,
            language=TeachingTextLanguage.EN,
            source_language=TeachingTextLanguage.FI,
            stored_source_text_hash=teaching_text_sha256("Vanha sisältö"),
            current_source_text_hash=None,
        ),
    )
    # An official source makes the stale derived row current in both the projected
    # coverage and the full resolver, so the shared accumulator is the single source of truth.
    updated_courses = tuple(
        course("course-stale", version("course-stale", content_fi="Vanha sisältö"))
        if item.group_id == "course-stale"
        else item
        for item in courses
    )
    shared_after = (
        TeachingTextService(FakeCurriculum(updated_courses), FakeTranslations(rows))
        .build_catalogue()
        .coverage
    )
    projected_after = TeachingTextService(
        FakeCurriculum(updated_courses), FakeTranslations(rows)
    ).coverage()
    assert projected_after == shared_after
    assert projected_after.stale_texts == ()
