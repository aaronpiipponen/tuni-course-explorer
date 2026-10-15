"""File contracts for the closed derived-translation import parser."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from course_explorer.enums import (
    TeachingTextField,
    TeachingTextLanguage,
    TranslationMethod,
)
from course_explorer.teaching_text import commands as command_module

VALID_ENTRY = {
    "sisu_course_unit_id": "course-a-v1",
    "field": "name",
    "language": "en",
    "source_language": "fi",
    "source_text": "Lineaarialgebra",
    "text": "Linear algebra",
    "translation_method": "manual",
    "translation_model": None,
    "generated_at": "2026-01-01T12:00:00+00:00",
}


def test_translation_file_parses_closed_json_array(tmp_path: Path) -> None:
    """A closed JSON array becomes validated translation inputs in order. Malformed fails."""
    import json

    path = tmp_path / "translations.json"
    path.write_text(json.dumps([VALID_ENTRY]), encoding="utf-8")

    loaded = command_module.load_translation_file(path)

    assert len(loaded) == 1
    assert loaded[0].sisu_course_unit_id == "course-a-v1"
    assert loaded[0].field is TeachingTextField.NAME
    assert loaded[0].language is TeachingTextLanguage.EN
    assert loaded[0].source_language is TeachingTextLanguage.FI
    assert loaded[0].translation_method is TranslationMethod.MANUAL
    assert loaded[0].generated_at == datetime(2026, 1, 1, 12, 0, tzinfo=UTC)

    path.write_text("not json", encoding="utf-8")
    with pytest.raises(ValueError):
        command_module.load_translation_file(path)
