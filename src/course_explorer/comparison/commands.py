"""Read-only composition for one machine-readable course-comparison command.

This module owns the process-level orchestration behind `scripts/compare_courses.py` and nothing
else: it rejects blank inputs before any settings load or I/O, loads the comparison policy and
embedding configuration once, resolves both inputs through the shared official lookup, reads those
current representatives' compatible chunk vectors once inside one engine lifetime, and returns one
transient JSON report. It reads through the shared official lookup and stored-vector owner, and the
meters/verdict are calculated analysis percentages that estimate equivalence.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from course_explorer.comparison.service import (
    ComparisonMeters,
    ComparisonVerdict,
    compare_teaching_chunks,
    comparison_verdict,
)
from course_explorer.config import (
    load_database_settings,
    load_embedding_settings,
    load_search_settings,
)
from course_explorer.curriculum import CourseSummary
from course_explorer.curriculum_repository import CurriculumRepository
from course_explorer.db.session import database_context as _database_context
from course_explorer.embeddings.generation import embedding_configuration_sha256
from course_explorer.embeddings.read import TeachingEmbeddingChunk, TeachingEmbeddingRepository
from course_explorer.enums import TeachingTextOrigin
from course_explorer.search.lookup import CourseLookupService


class CourseComparisonReport(BaseModel):
    """One transient course-comparison report consumed by the CLI and the web backend."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    course_a: CourseSummary
    course_b: CourseSummary
    meters: ComparisonMeters
    verdict: ComparisonVerdict | None
    uses_derived_text: bool


def run_course_comparison_command(course_a: str, course_b: str) -> CourseComparisonReport:
    """Compare two courses (canonical id or exact code) and return one report in caller A/B order."""
    if not course_a.strip():
        raise ValueError("course_a must be nonblank")
    if not course_b.strip():
        raise ValueError("course_b must be nonblank")
    search_settings = load_search_settings()
    embedding_settings = load_embedding_settings()
    with _database_context(load_database_settings()) as factory:
        curriculum = CurriculumRepository(factory)
        lookup = CourseLookupService(curriculum, search_settings)
        resolved = lookup.resolve_courses((course_a, course_b))
        chunks = TeachingEmbeddingRepository(factory).get_chunks(
            resolved,
            embedding_configuration_hash=embedding_configuration_sha256(embedding_settings),
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
        hub=embedding_settings.embedding_hub_vector,
        outcomes_hub=embedding_settings.embedding_outcomes_hub_vector,
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
