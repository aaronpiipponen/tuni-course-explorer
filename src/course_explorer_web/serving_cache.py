"""The serving dataset's engine and artifacts with the supervisor's shared state.

The module holds one slot per serving process. The supervisor fixes one dataset identity for its
whole lifetime. Before it forks every worker it opens the serving artifact set, appends the identity
to the catalogue body, compresses that body once and retains both response forms, so a worker's
first request neither reopens the artifacts nor reads or compresses the catalogue. The supervisor
also resolves the one serving settings bundle, preloads the lookup projection and creates the shared
next-course report region and, on a site that serves the embedding features, the query embedding
region. The worker's first request then builds only its own engine and centroid lookup. Each
worker's native fact handle fills on its first compiler read.
"""

from __future__ import annotations

import gzip
import threading
from dataclasses import dataclass
from functools import cached_property

import httpx
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from course_explorer.config import EmbeddingRuntimeSettings, SearchSettings, WebSettings
from course_explorer.db.session import (
    DatabaseConnectionSettings,
    create_database_engine,
    create_session_factory,
)
from course_explorer.embeddings.generation import embedding_configuration_sha256
from course_explorer.embeddings.query_cache import SharedQueryEmbeddingCache
from course_explorer.next_courses.report_cache import NextCourseReportCache
from course_explorer.recommendations.centroid_cache import CourseCentroidCache
from course_explorer.search.projection import LookupProjection
from course_explorer.serving_artifacts import ServingArtifacts
from course_explorer_web.dataset import ServingDataset


class ServingDatabase:
    """One open engine and session factory for the lifetime of one serving dataset identity.

    Construction opens the engine. ``factory()`` returns the one factory every request of this
    identity uses. The serving process exits with its engine open, so no close path exists.
    """

    def __init__(self, settings: DatabaseConnectionSettings) -> None:
        self._engine: Engine = create_database_engine(settings)
        self._factory: sessionmaker[Session] = create_session_factory(self._engine)

    def factory(self) -> sessionmaker[Session]:
        """Return the session factory bound to this serving dataset's engine."""
        return self._factory


@dataclass(frozen=True)
class ServingCaches:
    """The serving engine, opened artifacts, shared caches and shared-store centroid lookup.

    ``query_embeddings`` and ``course_centroids`` are ``None`` on a site with the embedding features
    off, because such a build holds no embedding read. The artifacts, catalogue body and gzip form
    are the supervisor's preloaded values, inherited by every forked worker.
    """

    database: ServingDatabase
    artifacts: ServingArtifacts
    catalogue_body: bytes
    catalogue_gzip: bytes
    next_course_reports: NextCourseReportCache
    query_embeddings: SharedQueryEmbeddingCache | None
    course_centroids: CourseCentroidCache | None


@dataclass(frozen=True)
class PreloadedServingArtifacts:
    """The serving artifact set and response bodies the supervisor builds before it forks."""

    artifacts: ServingArtifacts
    catalogue_body: bytes
    catalogue_gzip: bytes


@dataclass(frozen=True)
class ServingSettings:
    """The web, search, embedding and dataset settings and academic year one supervisor resolves.

    ``embedding_configuration_hash`` is derived from ``embedding``, so the resolved configuration is
    the only authority for the identity and no second stored copy can disagree with it.
    ``search_embedding_client`` is the one client every worker request uses for its query embedding.
    """

    web: WebSettings
    search: SearchSettings
    embedding: EmbeddingRuntimeSettings | None
    academic_year_start: int
    dataset: ServingDataset
    search_embedding_client: httpx.Client | None = None

    @cached_property
    def embedding_configuration_hash(self) -> str | None:
        """Return the identity of the resolved embedding configuration, or ``None`` when off.

        The identity is derived from the one resolved configuration and cached on this bundle, so a
        route computes it at most once and every identity matches the configuration the bundle
        holds.
        """
        if self.embedding is None:
            return None
        return embedding_configuration_sha256(self.embedding)


@dataclass(frozen=True)
class PreloadedSharedCaches:
    """The supervisor's shared caches, inherited read-write by every forked worker."""

    next_course_reports: NextCourseReportCache
    query_embeddings: SharedQueryEmbeddingCache | None

    def close(self) -> None:
        """Release the regions after the workers have stopped."""
        self.next_course_reports.close()
        if self.query_embeddings is not None:
            self.query_embeddings.close()


_lock = threading.Lock()
_current: ServingCaches | None = None
_preloaded_projection: LookupProjection | None = None
_preloaded_shared_caches: PreloadedSharedCaches | None = None
_preloaded_settings: ServingSettings | None = None
_preloaded_artifacts: PreloadedServingArtifacts | None = None


def set_preloaded_lookup_projection(projection: LookupProjection) -> None:
    """Set the one lookup projection the supervisor built before it forked its workers."""
    global _preloaded_projection
    _preloaded_projection = projection


def preloaded_lookup_projection() -> LookupProjection:
    """Return the supervisor's preloaded lookup projection.

    A worker that was not forked from a preloaded supervisor raises ``ValueError``. There is no
    per-worker rebuild.
    """
    if _preloaded_projection is None:
        raise ValueError("the serving lookup projection is not preloaded; start the web supervisor")
    return _preloaded_projection


def set_preloaded_shared_caches(caches: PreloadedSharedCaches) -> None:
    """Set the shared report and query embedding caches the supervisor created before the fork."""
    global _preloaded_shared_caches
    _preloaded_shared_caches = caches


def preloaded_shared_caches() -> PreloadedSharedCaches:
    """Return the supervisor's shared caches.

    A worker that was not forked from a preloaded supervisor raises ``ValueError``. There is no
    per-worker cache.
    """
    if _preloaded_shared_caches is None:
        raise ValueError("the serving shared caches are not preloaded; start the web supervisor")
    return _preloaded_shared_caches


def set_preloaded_serving_settings(settings: ServingSettings) -> None:
    """Set the one settings bundle the supervisor resolved before it forked its workers."""
    global _preloaded_settings
    _preloaded_settings = settings


def preloaded_serving_settings() -> ServingSettings:
    """Return the supervisor's resolved settings bundle.

    A worker that was not forked from a preloaded supervisor raises ``ValueError``. There is no
    per-request settings reload or dataset resolution.
    """
    if _preloaded_settings is None:
        raise ValueError("the serving settings are not preloaded; start the web supervisor")
    return _preloaded_settings


def preloaded_serving_artifacts() -> PreloadedServingArtifacts:
    """Return the supervisor's opened artifact set and catalogue response bodies.

    A worker that was not forked from a preloaded supervisor raises ``ValueError``. There is no
    per-worker artifact opening, catalogue read or compression.
    """
    if _preloaded_artifacts is None:
        raise ValueError("the serving artifacts are not preloaded; start the web supervisor")
    return _preloaded_artifacts


def preload_serving_artifacts() -> None:
    """Open the artifact set and build both catalogue response forms before the workers fork.

    The mode and the embedding configuration come from the preloaded settings bundle, so this
    opening reads no settings file and derives the embedding directory from the one resolved
    configuration.
    """
    global _preloaded_artifacts
    bundle = preloaded_serving_settings()
    artifacts = ServingArtifacts.open(
        bundle.dataset.settings,
        embedding=bundle.embedding,
    )
    body = artifacts.catalogue_body(bundle.dataset.identity)
    _preloaded_artifacts = PreloadedServingArtifacts(
        artifacts=artifacts,
        catalogue_body=body,
        catalogue_gzip=gzip.compress(body, compresslevel=6, mtime=0),
    )


def serving_caches(serving: ServingDataset) -> ServingCaches:
    """Return the one retained engine of this serving process with the preloaded artifacts.

    The supervisor fixes one dataset identity and opens the artifact set before it forks the
    workers, so this worker builds its engine and centroid lookup on its first request and keeps
    them for the process lifetime.
    """
    global _current
    with _lock:
        if _current is None:
            shared = preloaded_shared_caches()
            artifacts = preloaded_serving_artifacts()
            _current = ServingCaches(
                database=ServingDatabase(serving.settings),
                artifacts=artifacts.artifacts,
                catalogue_body=artifacts.catalogue_body,
                catalogue_gzip=artifacts.catalogue_gzip,
                next_course_reports=shared.next_course_reports,
                query_embeddings=shared.query_embeddings,
                course_centroids=(
                    None
                    if artifacts.artifacts.embeddings is None
                    else CourseCentroidCache(artifacts.artifacts.embeddings.shared_store)
                ),
            )
        return _current
