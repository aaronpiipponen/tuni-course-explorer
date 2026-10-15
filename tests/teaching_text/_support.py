"""Shared in-memory fixtures for the teaching-text public contract tests.

The shared catalogue builders, official read double, derived read double and derived-translation
DTO builder come from ``tests.support``. The effective-text service is composed over them without a
database.
"""

from __future__ import annotations

from course_explorer.curriculum import CatalogueCourse
from course_explorer.teaching_text.service import (
    DerivedTranslation,
    TeachingTextService,
)
from tests.support import (
    GENERATED_AT,
    FakeCurriculum,
    FakeTranslations,
    course,
    version,
)
from tests.support import (
    derived_translation as translation,
)

__all__ = [
    "GENERATED_AT",
    "FakeCurriculum",
    "FakeTranslations",
    "build",
    "course",
    "translation",
    "version",
]


def build(courses: tuple[CatalogueCourse, ...], rows: tuple[DerivedTranslation, ...]):
    """Compose the effective-text catalogue over the shared fixture seams."""
    return TeachingTextService(FakeCurriculum(courses), FakeTranslations(rows)).build_catalogue()
