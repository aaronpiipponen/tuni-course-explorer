"""Read-only composition for one deduplicated similarity recommendation report."""

from __future__ import annotations

from collections.abc import Collection, Sequence

from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session, sessionmaker

from course_explorer.config import (
    DatabaseSettings,
    EmbeddingRuntimeSettings,
    SearchSettings,
    load_database_settings,
    load_embedding_runtime_settings,
    load_search_settings,
)
from course_explorer.curriculum import RepresentedCourseSummary
from course_explorer.curriculum_repository import CurriculumRepository
from course_explorer.db.session import database_context
from course_explorer.embeddings.generation import embedding_configuration_sha256
from course_explorer.embeddings.read import TeachingEmbeddingRepository
from course_explorer.embeddings.shared_store import SharedServingStore
from course_explorer.next_courses.commands import (
    prepare_next_course_inputs,
    read_next_courses,
)
from course_explorer.next_courses.report_cache import NextCourseReportCache
from course_explorer.recommendations.centroid_cache import CourseCentroidCache
from course_explorer.recommendations.service import (
    SimilarityRecommendation,
    filter_neighbors_by_centroid,
    prepare_recommendation_basis,
    rank_recommendation_candidates,
    recommendations_from_candidates,
)
from course_explorer.search.lookup import DisplayLanguage
from course_explorer.search.projection import LookupProjection


class RecommendationsReport(BaseModel):
    """Deduplicated similarity recommendations for one request."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    similarity_results: tuple[SimilarityRecommendation, ...]


def _represented_records(
    projection: LookupProjection | None,
    curriculum: CurriculumRepository,
    group_ids: Collection[str],
    *,
    active_only: bool | None,
) -> tuple[RepresentedCourseSummary, ...]:
    """Return the represented records of one identity scope from the projection or the scoped read."""
    if projection is None:
        return curriculum.get_represented_summaries(group_ids, active_only=active_only)
    records = (
        projection.by_group_id[group_id]
        for group_id in sorted(group_ids)
        if group_id in projection.by_group_id
    )
    if active_only is True:
        return tuple(record for record in records if record.summary.is_active)
    return tuple(records)


def run_recommendations_command(
    *,
    selected_courses: Collection[str] = (),
    completed_courses: Collection[str] = (),
    basis: str = "completed",
    mode: str = "all",
    display_language: DisplayLanguage,
    include_inferred: bool = False,
    active_only: bool = True,
    database_settings: DatabaseSettings | None = None,
    search_settings: SearchSettings | None = None,
    embedding_settings: EmbeddingRuntimeSettings | None = None,
    hub: Sequence[float] | None = None,
    outcomes_hub: Sequence[float] | None = None,
    embedding_configuration_hash: str | None = None,
    shared_store: SharedServingStore,
    next_course_cache: NextCourseReportCache | None = None,
    centroid_cache: CourseCentroidCache | None = None,
    projection: LookupProjection | None = None,
    session_factory: sessionmaker[Session] | None = None,
) -> RecommendationsReport:
    """Return bounded current-vector similarity results that exclude the basis and its next courses.

    The native fact loader answers the next-course step's course and module facts through this
    process's database fact handle. The shared store answers every descriptive chunk read from the
    opened artifact set. A supplied projection answers the input resolution and the basis and
    candidate representative records without database reads. A supplied next-course report cache
    answers a repeated canonical request and supplies the exclusion set. A supplied centroid cache
    defaults to the shared store's matrix. A supplied search or embedding settings object is used as
    given, and each one the caller omits is loaded here. The hub pair is the opened serving
    artifact set's pair. A supplied embedding configuration identity answers the stored chunk and
    neighbour reads. Otherwise it is hashed from the supplied settings. A supplied session factory
    carries the serving engine and is never disposed here. Both chunk reads select the content and
    learning-outcomes rows alone.
    """
    inputs = prepare_next_course_inputs(
        selected_courses=selected_courses,
        completed_courses=completed_courses,
        basis=basis,
        mode=mode,
        display_language=display_language,
        include_inferred=include_inferred,
        active_only=active_only,
    )
    resolved_settings = (
        database_settings if database_settings is not None else load_database_settings()
    )
    next_report = read_next_courses(
        inputs,
        resolved_settings,
        report_cache=next_course_cache,
        projection=projection,
        session_factory=session_factory,
    )
    chosen_ids = (
        next_report.selected_group_ids
        if next_report.basis == "selected"
        else next_report.completed_group_ids
    )
    if not chosen_ids:
        return RecommendationsReport(similarity_results=())

    search_settings = search_settings or load_search_settings()
    embedding_settings = embedding_settings or load_embedding_runtime_settings()
    if hub is None or outcomes_hub is None:
        raise ValueError("recommendations require the serving artifact hub pair")
    configuration_hash = embedding_configuration_hash or embedding_configuration_sha256(
        embedding_settings
    )
    excluded = set(chosen_ids) | {result.course.group_id for result in next_report.results}
    with database_context(resolved_settings, factory=session_factory) as factory:
        curriculum = CurriculumRepository(factory)
        embedding_repository = TeachingEmbeddingRepository(factory)
        basis_records = _represented_records(projection, curriculum, chosen_ids, active_only=None)
        basis_chunks = embedding_repository.get_chunks(
            basis_records,
            embedding_configuration_hash=configuration_hash,
            descriptive_only=True,
            shared_store=shared_store,
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
        basis = prepare_recommendation_basis(
            basis_chunks,
            hub=hub,
            outcomes_hub=outcomes_hub,
        )
        if centroid_cache is None:
            centroid_cache = CourseCentroidCache(shared_store)
        survivors = filter_neighbors_by_centroid(
            neighbors,
            centroid_cache,
            basis,
            settings=search_settings,
        )
        if not survivors:
            return RecommendationsReport(similarity_results=())
        hit_ids = {neighbor.group_id for neighbor in survivors}
        represented = _represented_records(
            projection,
            curriculum,
            hit_ids,
            active_only=True if active_only else None,
        )
        candidates = rank_recommendation_candidates(survivors, represented)
        similarity_results = recommendations_from_candidates(
            candidates,
            basis_chunks,
            shared_store,
            display_language=display_language,
            settings=search_settings,
            hub=hub,
            outcomes_hub=outcomes_hub,
            basis=basis,
        )
    return RecommendationsReport(similarity_results=similarity_results)
