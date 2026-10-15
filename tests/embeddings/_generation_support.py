"""Shared in-memory fixtures for the network-free course-embedding chunk contracts.

The catalogue builders, official read double, derived read double and derived-translation DTO
builder come from ``tests.support``. This module composes the effective-text service over them.
"""

from __future__ import annotations

from typing import Any

from course_explorer.config import EmbeddingSettings
from course_explorer.curriculum import CatalogueCourse
from course_explorer.teaching_text.service import (
    DerivedTranslation,
    TeachingTextService,
)
from tests.support import (
    GENERATED_AT,
    HASH_A,
    FakeCurriculum,
    FakeTranslations,
    course,
    settings_factory,
    version,
)
from tests.support import (
    derived_translation as translation,
)

__all__ = [
    "GENERATED_AT",
    "HASH_A",
    "FakeCurriculum",
    "FakeTranslations",
    "course",
    "settings",
    "teaching_text",
    "translation",
    "version",
]


def settings(**overrides: Any) -> EmbeddingSettings:
    """Build one required embedding configuration with a test batch size."""
    values: dict[str, object] = {
        "EMBEDDING_CONTEXT_SIZE": 1024,
        "EMBEDDING_REQUEST_TIMEOUT_SECONDS": 30,
        "EMBEDDING_GENERATION_BATCH_SIZE": 2,
        "EMBEDDING_CHUNK_MAX_CHARACTERS": 100,
        "EMBEDDING_CHUNK_OVERLAP_CHARACTERS": 10,
        "EMBEDDING_ARTIFACT_URL": "https://example.test/model.gguf",
        "EMBEDDING_ARTIFACT_PATH": "models/model.gguf",
        **overrides,
    }
    return settings_factory(EmbeddingSettings, **values)


def teaching_text(
    courses: tuple[CatalogueCourse, ...], rows: tuple[DerivedTranslation, ...] = ()
) -> TeachingTextService:
    """Compose the effective-text service over the shared fixture seams."""
    return TeachingTextService(FakeCurriculum(courses), FakeTranslations(rows))
