"""Public proofs for the per-process retained caches of one serving dataset identity."""

from __future__ import annotations

from course_explorer.config import DatabaseSettings, WebSettings
from course_explorer_web.dataset import ServingDataset
from course_explorer_web.serving_cache import serving_caches
from tests.support import settings_factory


def test_serving_caches_are_reused_for_one_identity_and_rebuilt_for_another() -> None:
    """One identity keeps its three cache instances, and a different identity replaces them."""
    settings = settings_factory(WebSettings)
    database_settings = settings_factory(DatabaseSettings)
    serving = ServingDataset(settings=database_settings, identity="a" * 64)

    first = serving_caches(serving, settings)
    second = serving_caches(serving, settings)

    assert first is second
    assert first.lookup_projection is second.lookup_projection
    assert first.prerequisite_sources is second.prerequisite_sources
    assert first.descriptive_chunks is second.descriptive_chunks

    other = serving_caches(ServingDataset(settings=database_settings, identity="b" * 64), settings)

    assert other is not first
    assert other.dataset_identity == "b" * 64
    assert other.lookup_projection is not first.lookup_projection
    assert other.prerequisite_sources is not first.prerequisite_sources
    assert other.descriptive_chunks is not first.descriptive_chunks
