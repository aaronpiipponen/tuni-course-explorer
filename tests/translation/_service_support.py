"""Shared fixtures for the translation selector and worker recovery contracts.

The in-memory curriculum/derived seams and provider stubs mirror the real selector and worker
boundaries closely enough to exercise scheduling, provenance, and retained-output recovery. The
catalogue builders, official read double, derived read double and derived-translation DTO builder
come from ``tests.support``.
"""

from __future__ import annotations

import json
from functools import partial
from pathlib import Path

from course_explorer.config import TranslationSettings
from course_explorer.enums import (
    TeachingTextField,
    TeachingTextLanguage,
    TranslationMethod,
)
from course_explorer.teaching_text.service import (
    DerivedTranslationInput,
)
from course_explorer.translation.service import (
    TranslationWorkerService,
    select_translation_work,
)
from tests.support import (
    GENERATED_AT,
    FakeCurriculum,
    FakeTranslations,
    course,
    derived_translation,
    settings_factory,
    version,
)

__all__ = [
    "GENERATED_AT",
    "PROVENANCE",
    "FakeCurriculum",
    "FakeTranslations",
    "ForbiddenProvider",
    "RecordingProvider",
    "counts_by_cell",
    "course",
    "keys",
    "load_output",
    "retained_entry",
    "row",
    "select",
    "settings",
    "version",
    "worker",
    "write_output",
]

PROVENANCE = (
    "google/translategemma-12b-it@d1b225e1caa17f1ddc7e62065d8637d0923f34e2"
    ";Q5_K_M;sha256:6a4cd9eae938fd869ceeb310ed9c8de2f44bacb0c2d79541a4f4dbf2b201c6da"
)


def settings() -> TranslationSettings:
    return settings_factory(
        TranslationSettings,
        TRANSLATION_ARTIFACT_PATH="models/translategemma-12b-it-Q5_K_M.gguf",
    )


row = partial(
    derived_translation,
    method=TranslationMethod.MODEL,
    translation_model=PROVENANCE,
)


def select(courses, rows=(), *, course_limit=None):
    return select_translation_work(
        FakeCurriculum(courses), FakeTranslations(rows), settings(), course_limit=course_limit
    )


def keys(selection) -> list[tuple[str, str, str]]:
    return [
        (item.sisu_course_unit_id, item.field.value, item.language.value)
        for item in selection.items
    ]


def counts_by_cell(
    selection,
) -> dict[tuple[TeachingTextField, TeachingTextLanguage], tuple[int, int, int, int]]:
    return {
        (count.field, count.language): (
            count.official_target_count,
            count.current_derived_count,
            count.pending_count,
            count.missing_source_count,
        )
        for count in selection.fields
    }


class RecordingProvider:
    """Provider stub returning scripted outcomes and recording every call."""

    def __init__(self, outcomes) -> None:
        self.calls: list[tuple[str, TeachingTextLanguage, TeachingTextLanguage]] = []
        self._outcomes = list(outcomes)

    def translate(self, text, *, source_language, target_language) -> str:
        self.calls.append((text, source_language, target_language))
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class ForbiddenProvider:
    """Provider stub that fails if any request is attempted."""

    def translate(self, text, *, source_language, target_language) -> str:
        raise AssertionError("no provider call expected")


def load_output(path: Path) -> list[DerivedTranslationInput]:
    from course_explorer.teaching_text.commands import load_translation_file

    return list(load_translation_file(path))


def write_output(path: Path, entries: list[DerivedTranslationInput]) -> None:
    path.write_text(
        json.dumps([entry.model_dump(mode="json") for entry in entries], ensure_ascii=False),
        encoding="utf-8",
    )


def retained_entry(
    source_id: str = "course-a-v1",
    field: TeachingTextField = TeachingTextField.NAME,
    language: TeachingTextLanguage = TeachingTextLanguage.EN,
    *,
    source_language: TeachingTextLanguage = TeachingTextLanguage.FI,
    source_text: str = "Nimi",
    text: str = "Name",
    method: TranslationMethod = TranslationMethod.MODEL,
    translation_model: str | None = PROVENANCE,
) -> DerivedTranslationInput:
    return DerivedTranslationInput(
        sisu_course_unit_id=source_id,
        field=field,
        language=language,
        source_language=source_language,
        source_text=source_text,
        text=text,
        translation_method=method,
        translation_model=translation_model,
        generated_at=GENERATED_AT,
    )


def worker(tmp_path: Path, provider) -> TranslationWorkerService:
    representative = version("course-a-v1", name_fi="Nimi")
    return TranslationWorkerService(
        FakeCurriculum((course("course-a", representative),)),
        FakeTranslations(),
        provider,
        settings(),
        clock=lambda: GENERATED_AT,
    )
