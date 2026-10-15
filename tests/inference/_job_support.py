"""Shared real-PostgreSQL job fixtures and the one worker-runtime fake.

The incremental job runs against the disposable database with the real catalogue, candidate
repository, selection and evidence writer. Only the process/model boundaries are stubbed: settings
loaders return test-only values and the shared HTTP boundary stands in for the local
generation/rerank endpoints.
"""

from __future__ import annotations

import json
from contextlib import nullcontext
from typing import Any

from sqlalchemy import select

from course_explorer.config import (
    EmbeddingSettings,
    InferenceContextSettings,
    InferenceRerankInputSettings,
    InferenceRerankSettings,
    InferenceSelectionSettings,
    InferenceSettings,
)
from course_explorer.constants import COURSE_EMBEDDING_DIMENSION
from course_explorer.curriculum_repository import CurriculumRepository
from course_explorer.db.models import (
    Course,
    CourseEmbeddingChunk,
    CourseVersion,
    InferenceProcessingCycle,
)
from course_explorer.db.session import session_scope
from course_explorer.embeddings.generation import build_course_embedding_chunks
from course_explorer.enums import CourseEmbeddingStatus
from course_explorer.inference import job as job_module
from course_explorer.inference.operational import prepare_operational_catalogue
from course_explorer.inference.prompts import load_prompt_pack
from course_explorer.inference.scheduling_repository import InferenceSchedulingRepository
from course_explorer.teaching_text.repository import DerivedTranslationRepository
from course_explorer.teaching_text.service import TeachingTextService
from tests.inference._fixture_support import embedding_settings
from tests.inference._http_support import InferenceHttpBoundary, install_inference_http
from tests.inference._scheduling_support import seed_courses
from tests.support import settings_factory

CANDIDATES = tuple(f"job-c{index:02d}" for index in range(50))
_TEST_POOL_K = 50


def seed_embeddings(factory: object, settings: EmbeddingSettings) -> None:
    """Seed completed chunk rows matching the current desired embedding work exactly.

    Every chunk carries a nonzero unit vector so the real pgvector cosine ranking, fusion and
    selection run instead of collapsing on zero vectors.
    """
    curriculum = CurriculumRepository(factory)
    teaching_text = TeachingTextService(curriculum, DerivedTranslationRepository(factory))
    catalogue = prepare_operational_catalogue(curriculum, teaching_text, settings)
    chunks = build_course_embedding_chunks(catalogue.teaching_text_catalogue, settings)
    vector = [1.0] + [0.0] * (COURSE_EMBEDDING_DIMENSION - 1)
    with session_scope(factory) as session:
        version_ids = dict(
            session.execute(
                select(Course.group_id, CourseVersion.id).join(
                    CourseVersion, CourseVersion.course_id == Course.id
                )
            ).all()
        )
        for chunk in chunks:
            session.add(
                CourseEmbeddingChunk(
                    course_version_id=version_ids[chunk.group_id],
                    field=chunk.field,
                    language=chunk.language,
                    chunk_index=chunk.chunk_index,
                    text_origin=chunk.text_origin,
                    text=chunk.text,
                    representative_source_hash=chunk.representative_source_hash,
                    effective_text_hash=chunk.effective_text_hash,
                    source_text_hash=chunk.source_text_hash,
                    chunk_text_hash=chunk.chunk_text_hash,
                    translation_method=chunk.translation_method,
                    translation_model=chunk.translation_model,
                    translation_generated_at=chunk.translation_generated_at,
                    embedding_model=chunk.embedding_model,
                    embedding_artifact_sha256=chunk.embedding_artifact_sha256,
                    embedding_configuration_hash=chunk.embedding_configuration_hash,
                    status=CourseEmbeddingStatus.COMPLETED,
                    embedding=vector,
                )
            )


class WorkerRuntime:
    """One in-process owned runtime that records idempotent load/unload controls."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self._active_variant: Any | None = None

    def activate(self, variant: Any) -> None:
        self.calls.append("activate")
        self._active_variant = variant

    def active_variant(self) -> Any | None:
        return self._active_variant

    def stop(self) -> None:
        self.calls.append("stop")
        self._active_variant = None

    def start_rerank(self) -> None:
        self.calls.append("start_rerank")
        self._active_variant = None

    def stop_rerank(self) -> None:
        self.calls.append("stop_rerank")
        self._active_variant = None

    def request_scope(self, seconds: float):
        del seconds
        return nullcontext()


def _install_settings(monkeypatch: Any) -> InferenceSettings:
    """Install the test-only settings and return the inference settings."""
    embedding = embedding_settings()
    inference = settings_factory(
        InferenceSettings,
        INFERENCE_MAX_ATTEMPTS=1,
        INFERENCE_RETRY_BACKOFF_SECONDS=0,
    )
    selection = settings_factory(
        InferenceSelectionSettings,
        INFERENCE_SELECTION_POOL_K=_TEST_POOL_K,
        INFERENCE_SELECTION_FINAL_K=_TEST_POOL_K,
    )
    pack = load_prompt_pack("v9")
    monkeypatch.setattr(job_module, "load_embedding_settings", lambda: embedding)
    monkeypatch.setattr(job_module, "load_inference_settings", lambda: inference)
    monkeypatch.setattr(
        job_module,
        "load_inference_context_settings",
        lambda: settings_factory(InferenceContextSettings),
    )
    monkeypatch.setattr(job_module, "load_inference_selection_settings", lambda: selection)
    monkeypatch.setattr(
        job_module,
        "load_inference_rerank_settings",
        lambda: settings_factory(InferenceRerankSettings),
    )
    monkeypatch.setattr(
        job_module,
        "load_inference_rerank_input_settings",
        lambda: settings_factory(InferenceRerankInputSettings),
    )
    monkeypatch.setattr(job_module, "load_prompt_pack", lambda version: pack)
    return inference


def prepare_job_case(
    factory: object, monkeypatch: Any, targets: tuple[str, ...]
) -> tuple[InferenceSchedulingRepository, WorkerRuntime, InferenceHttpBoundary]:
    """Seed the catalogue/embeddings, install the test settings and return the real job owners."""
    seed_courses(
        factory,
        [(target, f"JOB.{index:02d}", True) for index, target in enumerate(targets)]
        + [(candidate, f"JOBC.{index:02d}", False) for index, candidate in enumerate(CANDIDATES)],
    )
    embedding = embedding_settings()
    seed_embeddings(factory, embedding)
    settings = _install_settings(monkeypatch)
    boundary = InferenceHttpBoundary(settings, prompt_tokens=1000)
    install_inference_http(monkeypatch, boundary)
    repository = InferenceSchedulingRepository(factory)
    return repository, WorkerRuntime(), boundary


def run_job(
    factory: object,
    runtime: WorkerRuntime,
    *,
    before_unit,
    before_request=None,
    clock=None,
    on_checkpoint=None,
    on_generation_attempt_checkpoint=None,
    oversize_route=None,
):
    """Run the incremental job with observation callbacks returning the finished cycle."""
    return job_module.run_inference_job(
        factory,
        runtime=runtime,
        before_unit=before_unit,
        before_request=before_request or (lambda: True),
        on_checkpoint=on_checkpoint or (lambda progress: None),
        on_generation_attempt_checkpoint=on_generation_attempt_checkpoint,
        oversize_route=oversize_route,
        **({} if clock is None else {"clock": clock}),
    )


def _latest_cycle_id(factory: object):
    """Return the retained processing cycle id with the greatest creation order."""
    with session_scope(factory) as session:
        return session.scalar(
            select(InferenceProcessingCycle.id)
            .order_by(
                InferenceProcessingCycle.created_at.desc(),
                InferenceProcessingCycle.id.desc(),
            )
            .limit(1)
        )


def _generation_payloads(boundary, group_id: str) -> list[dict]:
    """Return the generation-request payloads sent for one target, in order."""
    return [
        json.loads(request.content)
        for request in boundary.requests
        if request.url.path.endswith("chat/completions") and group_id.encode() in request.content
    ]
