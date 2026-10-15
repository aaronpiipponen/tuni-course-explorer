"""Closed translation-file parser for the derived-translation import seam."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from course_explorer.teaching_text.service import DerivedTranslationInput

_INPUT_ADAPTER = TypeAdapter(tuple[DerivedTranslationInput, ...])


def load_translation_file(path: Path) -> tuple[DerivedTranslationInput, ...]:
    """Parse and validate one closed top-level JSON array of translation inputs."""
    content = path.read_text(encoding="utf-8")
    try:
        value = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError("translation file is not valid JSON") from exc
    if not isinstance(value, list):
        raise ValueError("translation file must contain a top-level JSON array")
    if not value:
        raise ValueError("translation file must contain at least one translation")
    try:
        return _INPUT_ADAPTER.validate_python(value)
    except ValidationError as exc:
        raise ValueError("translation file contains malformed translation entries") from exc
