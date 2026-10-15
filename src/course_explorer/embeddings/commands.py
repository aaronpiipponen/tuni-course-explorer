"""Process composition for course-embedding generation."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager

from course_explorer.config import load_database_settings, load_embedding_runtime_settings
from course_explorer.curriculum_repository import CurriculumRepository
from course_explorer.db.session import database_context as _database_context
from course_explorer.embeddings.generation import (
    CourseEmbeddingProgress,
    CourseEmbeddingRunReport,
    CourseEmbeddingService,
)
from course_explorer.embeddings.provider import EmbeddingProvider
from course_explorer.embeddings.repository import CourseEmbeddingRepository
from course_explorer.teaching_text.repository import DerivedTranslationRepository
from course_explorer.teaching_text.service import TeachingTextService


def run_course_embedding_command(
    *,
    before_pending_batch: Callable[[], bool] | None = None,
    on_checkpoint: Callable[[CourseEmbeddingProgress], None] | None = None,
    before_request: Callable[[], bool] | None = None,
    request_scope: Callable[[float], AbstractContextManager[None]] | None = None,
) -> CourseEmbeddingRunReport | None:
    """Compose exactly one generation command over the shared repositories.

    Both lifecycle callbacks are forwarded to the sole service. This function is the
    only composition path a controller worker can enter. ``before_request`` and ``request_scope``
    are passed to the provider.
    """
    with _database_context(load_database_settings()) as factory:
        repository = CourseEmbeddingRepository(factory)
        teaching_text = TeachingTextService(
            CurriculumRepository(factory), DerivedTranslationRepository(factory)
        )
        settings = load_embedding_runtime_settings()
        with EmbeddingProvider(
            settings,
            before_request=before_request,
            request_scope=request_scope,
        ) as provider:
            service = CourseEmbeddingService(teaching_text, repository, provider, settings)
            return service.run(
                before_pending_batch=before_pending_batch,
                on_checkpoint=on_checkpoint,
            )
