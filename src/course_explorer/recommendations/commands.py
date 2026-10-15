"""Read-only composition for one deduplicated similarity recommendation report."""

from __future__ import annotations

from collections.abc import Collection

from pydantic import BaseModel, ConfigDict

from course_explorer.config import (
    load_database_settings,
    load_embedding_settings,
    load_search_settings,
)
from course_explorer.curriculum_repository import CurriculumRepository
from course_explorer.db.session import database_context
from course_explorer.embeddings.generation import embedding_configuration_sha256
from course_explorer.embeddings.read import TeachingEmbeddingRepository
from course_explorer.enums import TeachingTextField
from course_explorer.next_courses.commands import run_next_courses_command
from course_explorer.recommendations.service import (
    SimilarityRecommendation,
    rank_recommendation_candidates,
    recommendations_from_candidates,
)
from course_explorer.search.lookup import DisplayLanguage


class RecommendationsReport(BaseModel):
    """Deduplicated similarity recommendations for one request."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    similarity_results: tuple[SimilarityRecommendation, ...]


def run_recommendations_command(
    *,
    selected_courses: Collection[str] = (),
    completed_courses: Collection[str] = (),
    basis: str = "completed",
    mode: str = "all",
    display_language: DisplayLanguage,
    include_inferred: bool = False,
    active_only: bool = True,
) -> RecommendationsReport:
    """Return bounded current-vector similarity results that exclude the basis and its next courses."""
    selected = tuple(selected_courses)
    completed = tuple(completed_courses)
    next_report = run_next_courses_command(
        selected_courses=selected,
        completed_courses=completed,
        basis=basis,
        mode=mode,
        display_language=display_language,
        include_inferred=include_inferred,
        active_only=active_only,
    )
    chosen_ids = (
        next_report.selected_group_ids
        if next_report.basis == "selected"
        else next_report.completed_group_ids
    )
    if not chosen_ids:
        return RecommendationsReport(similarity_results=())

    search_settings = load_search_settings()
    embedding_settings = load_embedding_settings()
    configuration_hash = embedding_configuration_sha256(embedding_settings)
    excluded = set(chosen_ids) | {result.course.group_id for result in next_report.results}
    with database_context(load_database_settings()) as factory:
        curriculum = CurriculumRepository(factory)
        embedding_repository = TeachingEmbeddingRepository(factory)
        basis_records = curriculum.get_represented_summaries(chosen_ids)
        basis_chunks = tuple(
            chunk
            for chunk in embedding_repository.get_chunks(
                basis_records, embedding_configuration_hash=configuration_hash
            )
            if chunk.field in (TeachingTextField.CONTENT, TeachingTextField.OUTCOMES)
        )
        if not basis_chunks:
            return RecommendationsReport(similarity_results=())
        neighbors = embedding_repository.find_nearest_chunks(
            basis_chunks,
            embedding_configuration_hash=configuration_hash,
            top_k=search_settings.recommendation_chunk_top_k,
            active_only=active_only,
            excluded_group_ids=excluded,
        )
        hit_ids = {neighbor.group_id for neighbor in neighbors}
        represented = curriculum.get_represented_summaries(
            hit_ids, active_only=True if active_only else None
        )
        candidates = rank_recommendation_candidates(
            neighbors,
            represented,
            excluded_group_ids=excluded,
            display_language=display_language,
            settings=search_settings,
        )
        candidate_chunks = embedding_repository.get_chunks(
            tuple(record for record, _ in candidates),
            embedding_configuration_hash=configuration_hash,
        )
        similarity_results = recommendations_from_candidates(
            candidates,
            basis_chunks,
            candidate_chunks,
            display_language=display_language,
            settings=search_settings,
            hub=embedding_settings.embedding_hub_vector,
            outcomes_hub=embedding_settings.embedding_outcomes_hub_vector,
        )
    return RecommendationsReport(similarity_results=similarity_results)
