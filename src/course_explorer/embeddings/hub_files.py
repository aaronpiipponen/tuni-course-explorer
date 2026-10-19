"""Catalogue and outcomes embedding-hub computation and hub-file writing over current chunk vectors.

The catalogue hub is the mean of every current chunk vector of the represented courses, and the
outcomes hub is the same mean over the learning-outcome chunks. Both read only from complete current
embedding coverage, so a dataset whose desired chunks are not all completed under the configured
embedding contract fails before any file is written. Both files are staged before either
destination is replaced, and the two destinations are then replaced one after the other.
"""

from __future__ import annotations

import json
import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session, sessionmaker

from course_explorer.config import EmbeddingRuntimeSettings
from course_explorer.curriculum_repository import CurriculumRepository
from course_explorer.embeddings.generation import (
    CourseEmbeddingChunkInput,
    build_course_embedding_chunks,
    embedding_configuration_sha256,
)
from course_explorer.embeddings.hub import mean_unit_vectors
from course_explorer.embeddings.read import TeachingEmbeddingRepository
from course_explorer.embeddings.repository import CourseEmbeddingRepository
from course_explorer.enums import TeachingTextField
from course_explorer.teaching_text.repository import DerivedTranslationRepository
from course_explorer.teaching_text.service import TeachingTextService


@dataclass(frozen=True, slots=True)
class CurrentChunkVectors:
    """Every desired current chunk of a dataset, aligned by position with its stored vector."""

    chunks: tuple[CourseEmbeddingChunkInput, ...]
    vectors: tuple[tuple[float, ...], ...]


@dataclass(frozen=True, slots=True)
class EmbeddingHubs:
    """The catalogue hub and the outcomes hub, with the chunk counts each mean covers."""

    catalogue: tuple[float, ...]
    outcomes: tuple[float, ...]
    chunk_count: int
    outcomes_chunk_count: int


class EmbeddingHubReport(BaseModel):
    """The written hub files, as repository-relative paths, and the chunk counts behind them."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    catalogue_path: str
    outcomes_path: str
    chunk_count: int
    outcomes_chunk_count: int


def read_current_chunk_vectors(
    factory: sessionmaker[Session], embedding: EmbeddingRuntimeSettings
) -> CurrentChunkVectors:
    """Read the stored vector of every desired current chunk in curriculum order.

    The desired chunks are built from the effective teaching text of the represented courses under
    ``embedding``. Missing, stale, pending or failed desired work raises ``ValueError`` from the
    readiness read, and a desired chunk without a compatible stored vector raises ``ValueError``.
    """
    catalogue = TeachingTextService(
        CurriculumRepository(factory), DerivedTranslationRepository(factory)
    ).build_catalogue()
    chunks = build_course_embedding_chunks(catalogue, embedding)
    CourseEmbeddingRepository(factory).require_current_chunks(chunks)
    stored = TeachingEmbeddingRepository(factory).get_chunks(
        CurriculumRepository(factory).list_represented_summaries(),
        embedding_configuration_hash=embedding_configuration_sha256(embedding),
    )
    by_key = {
        (chunk.group_id, chunk.field, chunk.language, chunk.chunk_index): chunk.embedding
        for chunk in stored
    }
    keys = [(chunk.group_id, chunk.field, chunk.language, chunk.chunk_index) for chunk in chunks]
    if any(key not in by_key for key in keys):
        raise ValueError("current compatible embedding vectors are incomplete")
    return CurrentChunkVectors(chunks=chunks, vectors=tuple(tuple(by_key[key]) for key in keys))


def compute_embedding_hubs(current: CurrentChunkVectors) -> EmbeddingHubs:
    """Return the mean of every current chunk vector and the mean of the outcome chunk vectors.

    A dataset with no current chunk, or with no learning-outcome chunk, raises ``ValueError``.
    """
    outcomes = [
        vector
        for chunk, vector in zip(current.chunks, current.vectors, strict=True)
        if chunk.field is TeachingTextField.OUTCOMES
    ]
    return EmbeddingHubs(
        catalogue=mean_unit_vectors(current.vectors),
        outcomes=mean_unit_vectors(outcomes),
        chunk_count=len(current.vectors),
        outcomes_chunk_count=len(outcomes),
    )


def write_hub_file(path: Path, hub: Sequence[float]) -> None:
    """Write one hub as a compact JSON number array with a trailing newline."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(list(hub), separators=(",", ":"), ensure_ascii=True) + "\n", encoding="utf-8"
    )


def write_hub_files(catalogue_path: Path, outcomes_path: Path, hubs: EmbeddingHubs) -> None:
    """Stage both hubs, then replace their destinations one after the other.

    Each hub is written to a temporary file beside its destination, so a failure while staging
    leaves both destinations unchanged. The temporary files then replace their destinations in
    turn, so a failure during replacement can leave the catalogue hub updated and the outcomes hub
    not. Every temporary file is removed.
    """
    targets = (catalogue_path, outcomes_path)
    temporary_paths = tuple(path.with_name(f"{path.name}.tmp") for path in targets)
    try:
        for temporary, hub in zip(temporary_paths, (hubs.catalogue, hubs.outcomes), strict=True):
            write_hub_file(temporary, hub)
        for temporary, path in zip(temporary_paths, targets, strict=True):
            os.replace(temporary, path)
    finally:
        for temporary in temporary_paths:
            temporary.unlink(missing_ok=True)
