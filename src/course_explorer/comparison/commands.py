"""Read-only composition for one machine-readable course-comparison command.

This module owns the process-level orchestration behind `scripts/compare_courses.py`: it rejects
blank inputs before any settings load or I/O, uses the supplied database, comparison-policy and
embedding settings as given, loads each family the caller omits, resolves both inputs through the
shared official lookup, reads those current representatives' compatible chunk vectors once inside
one engine lifetime, and returns one transient report. The meters and the verdict are
calculated analysis percentages that estimate equivalence.
"""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session, sessionmaker

from course_explorer.comparison.service import (
    ComparisonMeters,
    ComparisonVerdict,
    compare_teaching_chunks,
    comparison_verdict,
)
from course_explorer.config import (
    DatabaseSettings,
    EmbeddingRuntimeSettings,
    SearchSettings,
    load_database_settings,
    load_embedding_runtime_settings,
    load_search_settings,
)
from course_explorer.curriculum import CourseSummary
from course_explorer.curriculum_repository import CurriculumRepository
from course_explorer.db.session import database_context as _database_context
from course_explorer.embeddings.generation import embedding_configuration_sha256
from course_explorer.embeddings.read import TeachingEmbeddingChunk, TeachingEmbeddingRepository
from course_explorer.enums import TeachingTextOrigin
from course_explorer.search.projection import LookupProjection
from course_explorer.search.resolver import CourseResolver


class CourseComparisonReport(BaseModel):
    """One transient course-comparison report consumed by the CLI and the web backend."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    course_a: CourseSummary
    course_b: CourseSummary
    meters: ComparisonMeters
    verdict: ComparisonVerdict | None
    uses_derived_text: bool


def run_course_comparison_command(
    course_a: str,
    course_b: str,
    *,
    database_settings: DatabaseSettings | None = None,
    search_settings: SearchSettings | None = None,
    embedding_settings: EmbeddingRuntimeSettings | None = None,
    hub: Sequence[float] | None = None,
    outcomes_hub: Sequence[float] | None = None,
    embedding_configuration_hash: str | None = None,
    projection: LookupProjection | None = None,
    session_factory: sessionmaker[Session] | None = None,
) -> CourseComparisonReport:
    """Compare two courses (canonical id or exact code) and return one report in caller A/B order.

    A supplied settings object is used as given, and each settings family the caller omits is
    loaded here. The hub pair is the opened serving artifact build's pair. A supplied embedding
    configuration identity answers the chunk read. Otherwise it is hashed from the supplied
    settings. A supplied projection answers the input resolution without the whole-catalogue code
    read. A supplied session factory carries the serving engine and is never disposed here.
    """
    if not course_a.strip():
        raise ValueError("course_a must be nonblank")
    if not course_b.strip():
        raise ValueError("course_b must be nonblank")
    search_settings = search_settings or load_search_settings()
    embedding_settings = embedding_settings or load_embedding_runtime_settings()
    if hub is None or outcomes_hub is None:
        raise ValueError("course comparison requires the serving artifact hub pair")
    resolved_settings = (
        database_settings if database_settings is not None else load_database_settings()
    )
    with _database_context(resolved_settings, factory=session_factory) as factory:
        curriculum = CurriculumRepository(factory)
        resolver = CourseResolver(curriculum, projection=projection)
        resolved = resolver.resolve_courses((course_a, course_b))
        chunks = TeachingEmbeddingRepository(factory).get_chunks(
            resolved,
            embedding_configuration_hash=(
                embedding_configuration_hash or embedding_configuration_sha256(embedding_settings)
            ),
        )

    chunks_by_group: dict[str, list[TeachingEmbeddingChunk]] = {}
    for chunk in chunks:
        chunks_by_group.setdefault(chunk.group_id, []).append(chunk)
    a_chunks = tuple(chunks_by_group.get(resolved[0].summary.group_id, ()))
    b_chunks = tuple(chunks_by_group.get(resolved[1].summary.group_id, ()))
    meters = compare_teaching_chunks(
        a_chunks,
        b_chunks,
        settings=search_settings,
        hub=hub,
        outcomes_hub=outcomes_hub,
    )
    verdict = comparison_verdict(meters, settings=search_settings)
    uses_derived_text = any(
        chunk.text_origin is TeachingTextOrigin.DERIVED for chunk in (*a_chunks, *b_chunks)
    )
    return CourseComparisonReport(
        course_a=resolved[0].summary,
        course_b=resolved[1].summary,
        meters=meters,
        verdict=verdict,
        uses_derived_text=uses_derived_text,
    )
