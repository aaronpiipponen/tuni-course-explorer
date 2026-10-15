"""Deterministic teaching-text chunking, work-key assembly, and idempotent generation.

This module owns the product-neutral contracts that turn the effective-teaching-text catalogue
into provenance-marked chunk inputs for the durable `course_embedding_chunks` store, and the single
generation service that embeds pending chunks through the one `EmbeddingProvider`. Only name,
content, and outcomes participate. Prerequisite/additional text never does. Official and derived
origins are distinct, and every work key is derived from effective text/source/model hashes rather
than row position so reruns reprocess only changed work.
"""

from __future__ import annotations

from collections.abc import Callable, Collection
from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from course_explorer.config import EmbeddingRuntimeSettings
from course_explorer.embeddings.provider import EmbeddingProvider
from course_explorer.enums import (
    TeachingTextField,
    TeachingTextLanguage,
    TeachingTextOrigin,
    TranslationMethod,
)
from course_explorer.hashing import json_sha256
from course_explorer.http_retry import RequestNotStarted
from course_explorer.teaching_text.service import (
    EffectiveTeachingTextCatalogue,
    TeachingTextService,
    teaching_text_sha256,
)

if TYPE_CHECKING:
    from course_explorer.embeddings.repository import CourseEmbeddingRepository


class _EmbeddingModel(BaseModel):
    """Frozen, closed DTO base for the course-embedding contract."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class CourseEmbeddingChunkInput(_EmbeddingModel):
    """One desired teaching-text chunk with its complete provenance/work key."""

    group_id: str
    sisu_course_unit_id: str
    representative_source_hash: str
    field: TeachingTextField
    language: TeachingTextLanguage
    chunk_index: int = Field(ge=0)
    text_origin: TeachingTextOrigin
    text: str
    effective_text_hash: str
    source_text_hash: str
    chunk_text_hash: str
    translation_method: TranslationMethod | None = None
    translation_model: str | None = None
    translation_generated_at: datetime | None = None
    embedding_model: str
    embedding_artifact_sha256: str
    embedding_configuration_hash: str


class PendingCourseEmbeddingChunk(_EmbeddingModel):
    """One persisted chunk awaiting a provider call, carrying its exact text."""

    row_id: UUID
    text: str


class CourseEmbeddingResult(_EmbeddingModel):
    """One provider vector bound to its persisted chunk row."""

    row_id: UUID
    embedding: tuple[float, ...]


class EmbeddingReconciliation(_EmbeddingModel):
    """Outcome of one scoped reconciliation between desired and persisted chunks."""

    desired_count: int = Field(ge=0)
    inserted_count: int = Field(ge=0)
    invalidated_count: int = Field(ge=0)
    reused_count: int = Field(ge=0)
    retry_count: int = Field(ge=0)
    deleted_count: int = Field(ge=0)
    pending: tuple[PendingCourseEmbeddingChunk, ...]


class CourseEmbeddingCoverageCount(_EmbeddingModel):
    """Lifecycle counts for one field/language/origin cell over a scoped chunk set."""

    field: TeachingTextField
    language: TeachingTextLanguage
    origin: TeachingTextOrigin
    pending_count: int = Field(ge=0)
    completed_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)


class CourseEmbeddingCoverageReport(_EmbeddingModel):
    """Scoped chunk lifecycle coverage for all field/language/origin cells."""

    total_chunk_count: int = Field(ge=0)
    pending_count: int = Field(ge=0)
    completed_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    fields: tuple[CourseEmbeddingCoverageCount, ...]


class CourseEmbeddingProgress(_EmbeddingModel):
    """One durable batch-boundary checkpoint of scoped generation progress.

    A controller publishes this only after reconciliation and after every durably committed
    batch, so ``coverage`` always describes committed rows and never work in flight. ``reused``
    counts compatible rows reconciliation found, while ``embedded`` counts vectors this run
    already stored. A partial run therefore reports non-complete coverage.
    """

    desired_chunk_count: int = Field(ge=0)
    reused_count: int = Field(ge=0)
    embedded_count: int = Field(ge=0)
    coverage: CourseEmbeddingCoverageReport


class CourseEmbeddingRunReport(_EmbeddingModel):
    """One completed generation run's reconciled counts and final scoped coverage."""

    canonical_course_count: int = Field(ge=0)
    representative_course_count: int = Field(ge=0)
    unembeddable_course_count: int = Field(ge=0)
    desired_chunk_count: int = Field(ge=0)
    inserted_count: int = Field(ge=0)
    invalidated_count: int = Field(ge=0)
    reused_count: int = Field(ge=0)
    retry_count: int = Field(ge=0)
    deleted_count: int = Field(ge=0)
    embedded_count: int = Field(ge=0)
    coverage: CourseEmbeddingCoverageReport


def embedding_configuration_sha256(settings: EmbeddingRuntimeSettings) -> str:
    """Hash only the configuration values that change embedding vector semantics."""
    payload = {
        "model": settings.embedding_model,
        "artifact_sha256": settings.embedding_artifact_sha256,
        "dimension": settings.embedding_dimension,
        "pooling": settings.embedding_pooling,
        "normalization": settings.embedding_normalization,
        "runtime_revision": settings.embedding_runtime_revision,
    }
    return json_sha256(payload, ensure_ascii=True)


def chunk_teaching_text(
    text: str, *, max_characters: int, overlap_characters: int
) -> tuple[str, ...]:
    """Split exact text into deterministic overlapping windows, omitting blank windows."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("chunked teaching text must be a non-blank string")
    if max_characters < 1:
        raise ValueError("max_characters must be positive")
    if overlap_characters < 0 or overlap_characters >= max_characters:
        raise ValueError("overlap_characters must be nonnegative and smaller than max_characters")
    if len(text) <= max_characters:
        return (text,)
    step = max_characters - overlap_characters
    chunks: list[str] = []
    start = 0
    while start < len(text):
        window = text[start : start + max_characters]
        if window.strip():
            chunks.append(window)
        if start + max_characters >= len(text):
            break
        start += step
    return tuple(chunks)


def build_course_embedding_chunks(
    catalogue: EffectiveTeachingTextCatalogue,
    settings: EmbeddingRuntimeSettings,
    *,
    group_ids: Collection[str] | None = None,
) -> tuple[CourseEmbeddingChunkInput, ...]:
    """Assemble deterministic chunk inputs in catalogue, cell, and chunk-index order."""
    scope: set[str] | None = None
    if group_ids is not None:
        scope = set(group_ids)
        unknown = scope - set(catalogue.canonical_group_ids)
        if unknown:
            raise ValueError(f"unknown canonical group IDs in chunk scope: {sorted(unknown)}")
    configuration_hash = embedding_configuration_sha256(settings)
    chunks: list[CourseEmbeddingChunkInput] = []
    for course in catalogue.courses:
        if scope is not None and course.group_id not in scope:
            continue
        for cell in course.texts:
            pieces = chunk_teaching_text(
                cell.text,
                max_characters=settings.embedding_chunk_max_characters,
                overlap_characters=settings.embedding_chunk_overlap_characters,
            )
            for chunk_index, piece in enumerate(pieces):
                chunks.append(
                    CourseEmbeddingChunkInput(
                        group_id=course.group_id,
                        sisu_course_unit_id=course.sisu_course_unit_id,
                        representative_source_hash=course.representative_source_hash,
                        field=cell.field,
                        language=cell.language,
                        chunk_index=chunk_index,
                        text_origin=cell.origin,
                        text=piece,
                        effective_text_hash=cell.text_hash,
                        source_text_hash=cell.source_text_hash,
                        chunk_text_hash=teaching_text_sha256(piece),
                        translation_method=cell.translation_method,
                        translation_model=cell.translation_model,
                        translation_generated_at=cell.translation_generated_at,
                        embedding_model=settings.embedding_model,
                        embedding_artifact_sha256=settings.embedding_artifact_sha256,
                        embedding_configuration_hash=configuration_hash,
                    )
                )
    return tuple(chunks)


class CourseEmbeddingService:
    """One idempotent, resumable generation service over effective text and the sole provider."""

    def __init__(
        self,
        teaching_text: TeachingTextService,
        repository: CourseEmbeddingRepository,
        provider: EmbeddingProvider,
        settings: EmbeddingRuntimeSettings,
    ) -> None:
        self._teaching_text = teaching_text
        self._repository = repository
        self._provider = provider
        self._settings = settings

    def run(
        self,
        *,
        before_pending_batch: Callable[[], bool] | None = None,
        on_checkpoint: Callable[[CourseEmbeddingProgress], None] | None = None,
    ) -> CourseEmbeddingRunReport | None:
        """Reconcile the full catalogue, embed pending chunks, and report coverage or a stop.

        ``on_checkpoint`` is published after reconciliation and after every durably committed or
        recorded batch, never while a provider/vector write is in flight. ``before_pending_batch``
        is consulted immediately before each batch's attempt write. Returning ``False`` ends the
        call normally with ``None`` and leaves the remaining batches untouched so the next
        reconciliation retries them. Defaults preserve the complete-run behavior.
        """
        catalogue = self._teaching_text.build_catalogue()
        scope = tuple(catalogue.canonical_group_ids)
        chunks = build_course_embedding_chunks(catalogue, self._settings, group_ids=scope)
        reconciliation = self._repository.reconcile(scope, chunks)

        embedded_count = 0

        def publish() -> None:
            if on_checkpoint is not None:
                on_checkpoint(
                    CourseEmbeddingProgress(
                        desired_chunk_count=reconciliation.desired_count,
                        reused_count=reconciliation.reused_count,
                        embedded_count=embedded_count,
                        coverage=self._repository.coverage(scope),
                    )
                )

        publish()
        batch_size = self._settings.embedding_generation_batch_size
        pending = reconciliation.pending
        for start in range(0, len(pending), batch_size):
            if before_pending_batch is not None and not before_pending_batch():
                return None
            batch = pending[start : start + batch_size]
            row_ids = tuple(item.row_id for item in batch)
            texts = tuple(item.text for item in batch)
            self._repository.begin_attempt(row_ids)
            try:
                vectors = self._provider.embed(texts)
            except RequestNotStarted:
                # A pause/stop refusal ends the call with the real partial coverage. The
                # already-started attempt rows stay pending, not completed.
                publish()
                return None
            except Exception:
                # Persist the failed state, then re-raise the exception as-is.
                self._repository.fail(row_ids)
                publish()
                raise
            results = tuple(
                CourseEmbeddingResult(row_id=item.row_id, embedding=vector)
                for item, vector in zip(batch, vectors, strict=True)
            )
            self._repository.complete(results)
            embedded_count += len(results)
            publish()

        coverage = self._repository.coverage(scope)
        return CourseEmbeddingRunReport(
            canonical_course_count=len(scope),
            representative_course_count=len(catalogue.courses),
            unembeddable_course_count=sum(1 for course in catalogue.courses if not course.texts),
            desired_chunk_count=reconciliation.desired_count,
            inserted_count=reconciliation.inserted_count,
            invalidated_count=reconciliation.invalidated_count,
            reused_count=reconciliation.reused_count,
            retry_count=reconciliation.retry_count,
            deleted_count=reconciliation.deleted_count,
            embedded_count=embedded_count,
            coverage=coverage,
        )
