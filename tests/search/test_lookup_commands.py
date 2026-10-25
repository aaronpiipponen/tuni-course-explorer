"""Command contracts for the official catalogue and course summaries."""

from __future__ import annotations

from contextlib import contextmanager

import pytest

from course_explorer.config import DatabaseSettings
from course_explorer.curriculum import (
    CatalogueCurriculumPeriod,
    CatalogueModuleLookup,
    CatalogueModuleVersionIdentity,
)
from course_explorer.enums import ModuleType
from course_explorer.search import lookup_commands as command_module
from tests.support import (
    FakeCurriculum,
    course,
    represented_rows,
    settings_factory,
    version,
)


def _module_version(
    sisu_module_id: str,
    *,
    module_type: ModuleType = ModuleType.STUDY_MODULE,
    code: str | None = None,
    name_fi: str | None = None,
    name_en: str | None = None,
    curriculum_periods: tuple[CatalogueCurriculumPeriod, ...] = (),
) -> CatalogueModuleVersionIdentity:
    """Build one projected module-version identity fixture."""
    return CatalogueModuleVersionIdentity(
        sisu_module_id=sisu_module_id,
        module_type=module_type,
        code=code,
        name_fi=name_fi,
        name_en=name_en,
        curriculum_periods=curriculum_periods,
    )


def _module(group_id: str, *versions: CatalogueModuleVersionIdentity) -> CatalogueModuleLookup:
    """Build one canonical module lookup fixture from its projected versions."""
    return CatalogueModuleLookup(group_id=group_id, versions=versions)


def test_catalogue_command_maps_minimal_projection_and_empty_summaries_shortcut(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The catalogue report carries course and module candidate fields, and an empty summaries
    request returns no results.
    """
    active = course(
        "course-group-b",
        version("source-b", name_fi="Beeta", name_en="Beta", code="B.1"),
    )
    inactive = course(
        "course-group-a",
        version("source-a", name_fi="Alfa", name_en="Alpha", code="A.1"),
        is_active=False,
    )
    curriculum = FakeCurriculum(
        (active, inactive),
        summaries_by_activity={None: represented_rows((active, inactive))},
        module_lookup=(
            _module(
                "module-group-a",
                _module_version(
                    "module-a-v1",
                    module_type=ModuleType.DEGREE_PROGRAMME,
                    code="DP.A",
                    name_fi="Ohjelma",
                    name_en="Degree",
                    curriculum_periods=(
                        CatalogueCurriculumPeriod(id="period-2026", academic_year_start=2026),
                    ),
                ),
            ),
        ),
    )
    settings = settings_factory(DatabaseSettings)

    @contextmanager
    def _context(_settings: DatabaseSettings):
        yield object()

    monkeypatch.setattr(command_module, "CurriculumRepository", lambda _factory: curriculum)
    monkeypatch.setattr(command_module, "_database_context", _context)
    monkeypatch.setattr(command_module, "load_database_settings", lambda: settings)

    report = command_module.run_catalogue_command()

    payload = report.model_dump(mode="json")
    # Only the narrowing fields leave the projection: no URL, source identity, text or prerequisite.
    assert payload["courses"] == [
        {
            "group_id": "course-group-a",
            "code": "A.1",
            "name_fi": "Alfa",
            "name_en": "Alpha",
            "credits_min": "5",
            "credits_max": None,
            "is_active": False,
        },
        {
            "group_id": "course-group-b",
            "code": "B.1",
            "name_fi": "Beeta",
            "name_en": "Beta",
            "credits_min": "5",
            "credits_max": None,
            "is_active": True,
        },
    ]
    assert payload["modules"] == [
        {
            "group_id": "module-group-a",
            "candidates": [
                {
                    "sisu_module_id": "module-a-v1",
                    "module_type": "DegreeProgramme",
                    "code": "DP.A",
                    "name_fi": "Ohjelma",
                    "name_en": "Degree",
                    "validity_start": None,
                    "validity_end": None,
                    "curriculum_periods": [{"id": "period-2026", "academic_year_start": 2026}],
                }
            ],
        }
    ]

    assert command_module.run_course_summaries_command(()).results == ()
