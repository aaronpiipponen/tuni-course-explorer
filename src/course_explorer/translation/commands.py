"""Process composition for the offline translation-only worker.

This module is the sole application composition point for the translation worker CLI. It
builds one database context, one provider, and one worker service, runs generation once,
and closes the provider before disposing the engine.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from pathlib import Path

from course_explorer.config import load_database_settings, load_translation_settings
from course_explorer.curriculum_repository import CurriculumRepository
from course_explorer.db.session import database_context as _database_context
from course_explorer.teaching_text.repository import DerivedTranslationRepository
from course_explorer.translation.provider import TranslationProvider
from course_explorer.translation.service import TranslationRunReport, TranslationWorkerService


def run_translation_command(
    *,
    output_path: Path,
    course_limit: int | None = None,
    before_pending_item: Callable[[], bool] | None = None,
    on_checkpoint: Callable[[int], None] | None = None,
    before_request: Callable[[], bool] | None = None,
    request_scope: Callable[[float], AbstractContextManager[None]] | None = None,
) -> TranslationRunReport:
    """Compose one worker run over the shared repositories and the one loopback provider.

    The two optional lifecycle callbacks are forwarded to the single worker
    service call. They never change resource or provider ownership. ``before_request`` and
    ``request_scope`` are passed to the provider so a detached worker can refuse a
    transport request after pause/stop and bound the request itself. Product callers omit them.
    The worker service owns the nonpositive-limit and directory-output checks.
    """
    database_settings = load_database_settings()
    translation_settings = load_translation_settings()
    with _database_context(database_settings) as factory:
        curriculum = CurriculumRepository(factory)
        translations = DerivedTranslationRepository(factory)
        with TranslationProvider(
            translation_settings,
            before_request=before_request,
            request_scope=request_scope,
        ) as provider:
            service = TranslationWorkerService(
                curriculum, translations, provider, translation_settings
            )
            return service.run(
                output_path=output_path,
                course_limit=course_limit,
                before_pending_item=before_pending_item,
                on_checkpoint=on_checkpoint,
            )
