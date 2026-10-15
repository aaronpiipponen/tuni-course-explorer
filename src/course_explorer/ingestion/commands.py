"""Process composition for curriculum import and retained-manifest resume."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from course_explorer.config import (
    NormalizationSettings,
    load_capture_settings,
    load_database_settings,
    load_kori_settings,
    load_normalization_settings,
)
from course_explorer.db.session import database_context as _database_context
from course_explorer.ingestion.capture import CaptureBoundary
from course_explorer.ingestion.importing import CurriculumImportReport, import_curriculum
from course_explorer.ingestion.kori import TuniKoriSource
from course_explorer.ingestion.manifest import RawCaptureStore
from course_explorer.ingestion.normalization_repository import NormalizationRepository
from course_explorer.ingestion.repository import CaptureRepository


def _import_report(
    *,
    source: Any,
    store: RawCaptureStore,
    capture_repository: CaptureRepository,
    normalization_repository: NormalizationRepository,
    capture_settings: Any,
    normalization_settings: NormalizationSettings,
    verification_start_index: int = 0,
    on_boundary: CaptureBoundary | None = None,
) -> CurriculumImportReport | None:
    """Pass validated settings into the reusable import service."""
    return import_curriculum(
        source=source,
        store=store,
        capture_repository=capture_repository,
        normalization_repository=normalization_repository,
        checkpoint_response_count=capture_settings.capture_checkpoint_response_count,
        current_academic_year_start=normalization_settings.current_academic_year_start,
        activity_window_years=normalization_settings.active_academic_year_window,
        course_guide_base_url=normalization_settings.course_guide_base_url,
        verification_start_index=verification_start_index,
        on_boundary=on_boundary,
    )


def run_capture_command(
    *,
    resume_manifest: Path | None = None,
    verification_start_index: int = 0,
    on_store_selected: Callable[[RawCaptureStore], None] | None = None,
    on_boundary: CaptureBoundary | None = None,
    before_request: Callable[[], bool] | None = None,
) -> CurriculumImportReport | None:
    """Compose one fresh full capture or one retained-manifest resume.

    ``on_store_selected`` runs immediately after the exact store is created or opened, before any
    capture, so a detached worker can bind durable state to the authoritative manifest identity.
    ``on_boundary`` forwards the cooperative lifecycle gate. A controlled ``None`` means the
    caller paused or stopped at a durable boundary. ``before_request`` is the pure live-control
    admission callback forwarded to the Kori client: an already-admitted initial source pull is
    untouched, while a requested pause or stop refuses any further transport retry.
    """
    if verification_start_index < 0:
        raise ValueError("verification start index must not be negative")

    capture_settings = load_capture_settings()

    resume_store = None
    if resume_manifest is not None:
        resume_store = RawCaptureStore.open(capture_settings.raw_data_root, resume_manifest)
    normalization_settings = load_normalization_settings()
    kori_settings = load_kori_settings()
    database_settings = load_database_settings()
    source_context = TuniKoriSource(kori_settings, before_request=before_request)
    with source_context as source, _database_context(database_settings) as factory:
        capture_repository = CaptureRepository(factory)
        store = (
            resume_store
            if resume_store is not None
            else RawCaptureStore.create(capture_settings.raw_data_root)
        )
        if on_store_selected is not None:
            on_store_selected(store)
        return _import_report(
            source=source,
            store=store,
            capture_repository=capture_repository,
            normalization_repository=NormalizationRepository(factory),
            capture_settings=capture_settings,
            normalization_settings=normalization_settings,
            verification_start_index=verification_start_index,
            on_boundary=on_boundary,
        )
