"""Public proof for one serving dataset identity's engine, artifacts and supervisor-shared
caches."""

from __future__ import annotations

import gzip

from course_explorer.config import DatabaseSettings
from course_explorer_web.dataset import ServingDataset
from course_explorer_web.serving_cache import serving_caches
from tests.support import settings_factory


def test_serving_caches_are_reused_for_the_supervisor_identity() -> None:
    """One supervisor fixes one dataset identity, so repeated reads retain the one built set.

    The next-course report region is the supervisor's preloaded cache, and the artifacts, catalogue
    body and gzip form are the supervisor's preloaded values. The gzip form holds the compressed
    catalogue body.
    """
    database_settings = settings_factory(DatabaseSettings)
    serving = ServingDataset(settings=database_settings, identity="a" * 64)

    first = serving_caches(serving)
    second = serving_caches(serving)

    assert first is second
    assert first.database is second.database
    assert first.artifacts is second.artifacts
    assert first.catalogue_body.endswith(b"}")
    assert b'"dataset_identity"' in first.catalogue_body
    assert gzip.decompress(first.catalogue_gzip) == first.catalogue_body
    assert first.next_course_reports is second.next_course_reports
    assert first.course_centroids is second.course_centroids
