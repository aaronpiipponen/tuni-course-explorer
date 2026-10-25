"""Disposable-PostgreSQL round-trip proof for bulk official course summaries."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from course_explorer.config import SearchSettings
from course_explorer.curriculum_repository import CurriculumRepository
from course_explorer.hashing import json_sha256
from course_explorer.ingestion.normalization import normalize_curriculum
from course_explorer.ingestion.normalization_repository import NormalizationRepository
from course_explorer.ingestion.repository import CaptureRepository
from course_explorer.search import lookup_commands
from course_explorer.search.lookup import CourseLookupService
from course_explorer_web.app import app
from course_explorer_web.dataset import SERVING_GENERATION_ENV
from tests.ingestion._normalization_repository_support import (
    GUIDE_URL,
    build_completed_fixture_store,
)
from tests.support import settings_factory

pytestmark = [
    pytest.mark.integration,
]


def test_course_summaries_route_preserves_resolution(
    database: tuple[object, object], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A real normalized test catalogue resolves ordered repeated official summaries over HTTP."""
    _, factory = database
    store = build_completed_fixture_store(tmp_path, CaptureRepository(factory))
    normalize_curriculum(
        store,
        NormalizationRepository(factory),
        current_academic_year_start=2026,
        activity_window_years=3,
        course_guide_base_url=GUIDE_URL,
    )
    monkeypatch.setattr(
        lookup_commands, "load_search_settings", lambda: settings_factory(SearchSettings)
    )
    generation = "a" * 32
    monkeypatch.setenv(SERVING_GENERATION_ENV, generation)
    expected_records = CourseLookupService(
        CurriculumRepository(factory), settings_factory(SearchSettings)
    ).resolve_courses(("course-group-inactive", "CS.A2", "course-group-inactive"))
    response = TestClient(app).post(
        "/api/course-summaries",
        json={"identifiers": ["course-group-inactive", "CS.A2", "course-group-inactive"]},
    )
    assert response.status_code == 200
    assert response.json() == {
        "results": [record.summary.model_dump(mode="json") for record in expected_records],
        "dataset_identity": json_sha256([generation, None], ensure_ascii=False),
    }
