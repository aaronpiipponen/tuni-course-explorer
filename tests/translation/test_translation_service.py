"""Selector contracts for the translation-only worker."""

from __future__ import annotations

import pytest

from course_explorer.enums import (
    TeachingTextField,
    TeachingTextLanguage,
    TranslationMethod,
)
from course_explorer.teaching_text.service import DerivedTranslation, teaching_text_sha256
from tests.translation._service_support import (
    GENERATED_AT,
    counts_by_cell,
    course,
    keys,
    row,
    select,
    version,
)


def test_selector_partitions_every_representative_cell_and_orders_pending_work() -> None:
    """Every cell is classified once and pending work follows course, field, then language order."""
    courses = (
        course("course-a", version("course-a-v1", name_fi="Nimi")),
        course("course-b", version("course-b-v1", name_fi="Toinen")),
    )
    selection = select(courses)

    assert selection.canonical_course_count == 2
    assert selection.representative_course_count == 2
    assert selection.no_representative_course_count == 0
    assert selection.active_representative_count == 2
    assert selection.inactive_representative_count == 0
    for cell_counts in counts_by_cell(selection).values():
        assert sum(cell_counts) == 2
    assert keys(selection) == [
        ("course-a-v1", "name", "en"),
        ("course-b-v1", "name", "en"),
    ]
    counts = counts_by_cell(selection)
    assert counts[(TeachingTextField.NAME, TeachingTextLanguage.FI)] == (2, 0, 0, 0)
    assert counts[(TeachingTextField.NAME, TeachingTextLanguage.EN)] == (0, 0, 2, 0)
    assert counts[(TeachingTextField.CONTENT, TeachingTextLanguage.FI)] == (0, 0, 0, 2)
    assert sum(count.pending_count for count in selection.fields) == len(selection.items)


def test_selector_includes_inactive_name_only_and_both_directions_but_not_cross_field_sources() -> (
    None
):
    """Inactive courses participate and both directions queue, without inventing cross-field work."""
    courses = (
        course("course-fi", version("course-fi-v1", name_fi="Ohjelmointi"), is_active=False),
        course("course-en", version("course-en-v1", content_en="Use matrices")),
    )
    selection = select(courses)

    assert selection.active_representative_count == 1
    assert selection.inactive_representative_count == 1
    assert keys(selection) == [
        ("course-fi-v1", "name", "en"),
        ("course-en-v1", "content", "fi"),
    ]
    counts = counts_by_cell(selection)
    assert counts[(TeachingTextField.NAME, TeachingTextLanguage.FI)] == (1, 0, 0, 1)
    assert counts[(TeachingTextField.NAME, TeachingTextLanguage.EN)] == (0, 0, 1, 1)
    assert counts[(TeachingTextField.CONTENT, TeachingTextLanguage.FI)] == (0, 0, 1, 1)
    assert counts[(TeachingTextField.CONTENT, TeachingTextLanguage.EN)] == (1, 0, 0, 1)
    # The name-only course never invents content/outcomes from its name.
    assert counts[(TeachingTextField.OUTCOMES, TeachingTextLanguage.FI)] == (0, 0, 0, 2)
    assert counts[(TeachingTextField.OUTCOMES, TeachingTextLanguage.EN)] == (0, 0, 0, 2)


def test_selector_skips_current_derived_and_requeues_stale_or_mismatched_derived() -> None:
    """Current same-source same-model rows are reused. Stale, wrong-source, or wrong-model rows requeue."""
    representative = version(
        "course-a-v1", name_fi="Nimi", content_fi="Sisältö", outcomes_fi="Osat"
    )
    manual_representative = version("course-b-v1", name_fi="Toinen")
    rows = (
        row(
            "course-a-v1",
            TeachingTextField.NAME,
            TeachingTextLanguage.EN,
            TeachingTextLanguage.FI,
            "Nimi",
            "Name",
        ),
        row(
            "course-a-v1",
            TeachingTextField.CONTENT,
            TeachingTextLanguage.EN,
            TeachingTextLanguage.FI,
            "Vanha sisältö",
            "Old content",
        ),
        row(
            "course-a-v1",
            TeachingTextField.OUTCOMES,
            TeachingTextLanguage.EN,
            TeachingTextLanguage.FI,
            "Osat",
            "Outcomes",
            translation_model="other-model",
        ),
        DerivedTranslation(
            sisu_course_unit_id="course-b-v1",
            field=TeachingTextField.NAME,
            language=TeachingTextLanguage.EN,
            source_language=TeachingTextLanguage.FI,
            source_text_hash=teaching_text_sha256("Toinen"),
            text="Second",
            translation_method=TranslationMethod.MANUAL,
            translation_model=None,
            generated_at=GENERATED_AT,
        ),
    )
    selection = select(
        (course("course-a", representative), course("course-b", manual_representative)), rows
    )

    counts = counts_by_cell(selection)
    assert counts[(TeachingTextField.NAME, TeachingTextLanguage.EN)] == (0, 2, 0, 0)
    assert counts[(TeachingTextField.CONTENT, TeachingTextLanguage.EN)] == (0, 0, 1, 1)
    assert counts[(TeachingTextField.OUTCOMES, TeachingTextLanguage.EN)] == (0, 0, 1, 1)
    assert keys(selection) == [
        ("course-a-v1", "content", "en"),
        ("course-a-v1", "outcomes", "en"),
    ]


def test_selector_applies_positive_course_limit_before_representative_filtering() -> None:
    """The limit narrows stable canonical order first, even when the first course has no representative."""
    courses = (
        course("course-a", None),
        course("course-b", version("course-b-v1", name_fi="Nimi")),
    )
    selection = select(courses, course_limit=1)

    assert selection.canonical_course_count == 1
    assert selection.representative_course_count == 0
    assert selection.no_representative_course_count == 1
    assert selection.items == ()

    # A nonpositive public limit is refused before any read or provider work.
    with pytest.raises(ValueError):
        select(courses, course_limit=0)
    with pytest.raises(ValueError):
        select(courses, course_limit=-1)
