"""Shared synthetic serving generation, preloaded artifact set and retained-cache scope for web
tests."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import pytest

import course_explorer_web.serving_cache as serving_cache
from course_explorer.config import (
    embedding_configuration_for_site,
    load_normalization_settings,
    load_search_settings,
    load_web_settings,
)
from course_explorer.constants import COURSE_EMBEDDING_DIMENSION
from course_explorer.embeddings.centroids import CourseCentroid
from course_explorer.embeddings.query_cache import SharedQueryEmbeddingCache
from course_explorer.embeddings.shared_store import SharedServingStore
from course_explorer.next_courses.report_cache import NextCourseReportCache
from course_explorer.search.projection import LookupProjection
from course_explorer.serving_artifacts import (
    ServingArtifacts,
    ServingEmbeddings,
    ServingSearchMeta,
    serving_artifact_key,
)
from course_explorer.serving_build import write_hub_pair
from course_explorer.study_structure.fragments import StudyFragmentStore
from course_explorer_web.dataset import resolve_serving_dataset
from course_explorer_web.serving_cache import ServingSettings, set_preloaded_serving_settings

SYNTHETIC_SERVING_GENERATION = "f" * 32


@pytest.fixture(autouse=True)
def _synthetic_serving_generation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Supply one synthetic generation value, so no test needs a running serving parent."""
    monkeypatch.setenv("COURSE_EXPLORER_WEB_GENERATION", SYNTHETIC_SERVING_GENERATION)


@pytest.fixture(autouse=True)
def _fresh_serving_caches(monkeypatch: pytest.MonkeyPatch) -> None:
    """Start every test with no retained cache, so one test's projection answers no other test."""
    monkeypatch.setattr(serving_cache, "_current", None)


def refresh_serving_settings(*, preload: bool = True) -> ServingSettings:
    """Resolve the settings bundle as a supervisor restart after a configuration change.

    A restart reads the configuration afresh and, unless the caller owns the artifact opening,
    drops the retained cache and re-preloads the artifact set and catalogue bodies exactly as the
    supervisor does before it forks fresh workers.
    """
    web = load_web_settings()
    bundle = ServingSettings(
        web=web,
        search=load_search_settings(),
        embedding=embedding_configuration_for_site(web),
        academic_year_start=load_normalization_settings().current_academic_year_start,
        dataset=resolve_serving_dataset(),
    )
    set_preloaded_serving_settings(bundle)
    if preload:
        serving_cache._current = None
        serving_cache.preload_serving_artifacts()
    return bundle


@pytest.fixture(autouse=True)
def _preloaded_serving_settings(_synthetic_serving_generation: None) -> None:
    """Supply the supervisor's resolved settings bundle to a mounted test application."""
    refresh_serving_settings(preload=False)


@pytest.fixture(autouse=True)
def _preloaded_lookup_projection(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[None]:
    """Supply the supervisor's preloaded projection and shared caches to a mounted test
    application."""
    monkeypatch.setattr(
        serving_cache,
        "_preloaded_projection",
        LookupProjection(courses=(), active_courses=(), modules=()),
    )
    caches = serving_cache.PreloadedSharedCaches(
        next_course_reports=NextCourseReportCache.create(2 * 1024 * 1024),
        query_embeddings=SharedQueryEmbeddingCache.create(1024 * 1024),
    )
    monkeypatch.setattr(serving_cache, "_preloaded_shared_caches", caches)
    yield
    caches.close()


@pytest.fixture(autouse=True)
def _serving_artifact_set(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> ServingArtifacts:
    """Build one lightweight artifact set on disk and open it for every web test."""
    key = serving_artifact_key("web_test", 2026)
    root = tmp_path / "artifacts"
    root.mkdir()
    (root / "catalogue.json").write_bytes(b'{"courses":[],"modules":[]}')
    write_hub_pair(
        root,
        (0.0,) * COURSE_EMBEDDING_DIMENSION,
        (0.0,) * COURSE_EMBEDDING_DIMENSION,
    )
    shared_store = SharedServingStore.build(
        root,
        dataset_key=key.key,
        academic_year_start=key.academic_year_start,
        centroids=(
            CourseCentroid(
                group_id="test-course",
                sisu_course_unit_id="test-version",
                representative_source_hash="b" * 64,
                chunk_count=0,
                centroid=(0.0,) * COURSE_EMBEDDING_DIMENSION,
            ),
        ),
        chunks=(),
    )
    fragments = StudyFragmentStore.build(
        object(),
        (),
        dataset_key=key.key,
        academic_year_start=key.academic_year_start,
        path=root / "study-fragments.bin",
    )
    del fragments
    artifacts = ServingArtifacts(
        root=root,
        study_fragments=StudyFragmentStore.open(
            root / "study-fragments.bin",
            dataset_key=key.key,
            academic_year_start=key.academic_year_start,
        ),
        embeddings=ServingEmbeddings(
            hubs=((0.0,) * COURSE_EMBEDDING_DIMENSION, (0.0,) * COURSE_EMBEDDING_DIMENSION),
            shared_store=shared_store,
            search=ServingSearchMeta(group_count=1),
        ),
    )
    return artifacts


@pytest.fixture(autouse=True)
def _open_lightweight_artifacts(
    monkeypatch: pytest.MonkeyPatch, _serving_artifact_set: ServingArtifacts
) -> None:
    """Answer the supervisor's artifact open with the lightweight on-disk set."""
    monkeypatch.setattr(
        serving_cache.ServingArtifacts,
        "open",
        classmethod(lambda cls, *args, **kwargs: _serving_artifact_set),
    )


@pytest.fixture(autouse=True)
def _preload_supervisor_artifacts(
    _preloaded_serving_settings: None,
    _open_lightweight_artifacts: None,
) -> None:
    """Preload the catalogues and opened set the supervisor hands to its workers."""
    serving_cache.preload_serving_artifacts()


@pytest.fixture()
def embeddings_off(
    monkeypatch: pytest.MonkeyPatch,
    _serving_artifact_set: ServingArtifacts,
) -> None:
    """Preload an embeddings-off artifact set, so the off path runs through the routes.

    The site switch and the opened set agree: with the features off the set holds no hub pair,
    shared store or packed search row, and the routes read none of them.
    """
    monkeypatch.setenv("WEB_EMBEDDINGS_ENABLED", "0")
    refresh_serving_settings(preload=False)
    off = replace(_serving_artifact_set, embeddings=None)
    monkeypatch.setattr(
        serving_cache.ServingArtifacts,
        "open",
        classmethod(lambda cls, *args, **kwargs: off),
    )
    serving_cache.preload_serving_artifacts()
