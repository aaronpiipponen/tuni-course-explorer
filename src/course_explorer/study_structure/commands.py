"""Reusable read-only composition for the official structure-of-studies commands.

This module owns the process-level orchestration behind `scripts/study_structure.py` and the web
batch read: it validates the canonical root identities before any settings load or I/O, reads the
configured current academic year once, composes the repository-backed structure service inside one
engine lifetime, reads the roots through one shared batch projection, and returns one transient
JSON report. The single-root command delegates to that batch owner. The reports are request-local
values consumed by the CLI adapter and the web backend.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping

from pydantic import BaseModel, ConfigDict

from course_explorer.config import (
    DatabaseSettings,
    load_database_settings,
    load_normalization_settings,
)
from course_explorer.curriculum_repository import CurriculumRepository
from course_explorer.db.session import database_context as _database_context
from course_explorer.study_structure.service import (
    StudyStructureModule,
    StudyStructureService,
    StudyStructureVersionSelectionRequired,
)


class StudyStructureReport(BaseModel):
    """One transient official structure-of-studies report for a canonical root."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    academic_year_start: int
    root: StudyStructureModule


class StudyStructuresReport(BaseModel):
    """One transient official structure-of-studies report for several canonical roots."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    academic_year_start: int
    roots: tuple[StudyStructureModule, ...]
    unavailable_root_group_ids: tuple[str, ...]
    version_selection_required: tuple[str, ...] = ()


def run_study_structures_command(
    root_group_ids: Collection[str],
    *,
    allow_unavailable: bool = False,
    module_versions: Mapping[str, str] | None = None,
    database_settings: DatabaseSettings | None = None,
) -> StudyStructuresReport:
    """Compose one official structure read for the supplied canonical roots.

    A root that is not a projectable official module or programme is collected in
    ``unavailable_root_group_ids`` when ``allow_unavailable`` is true, and an ambiguous root without
    an explicit selection is reported in ``version_selection_required``. Nested resolution failures
    stay typed unresolved nodes, and every other failure propagates.
    """
    materialized = tuple(root_group_ids)
    for root_group_id in materialized:
        if not root_group_id.strip():
            raise ValueError("root group identities must not be blank")
    academic_year_start = load_normalization_settings().current_academic_year_start
    resolved_settings = (
        database_settings if database_settings is not None else load_database_settings()
    )
    with _database_context(resolved_settings) as factory:
        service = StudyStructureService(
            CurriculumRepository(factory), academic_year_start=academic_year_start
        )
        batch = service.read_many(
            materialized, allow_unavailable=allow_unavailable, module_versions=module_versions
        )
    return StudyStructuresReport(
        academic_year_start=academic_year_start,
        roots=batch.roots,
        unavailable_root_group_ids=batch.unavailable_root_group_ids,
        version_selection_required=batch.version_selection_required,
    )


def run_study_structure_command(
    root_group_id: str, *, module_versions: Mapping[str, str] | None = None
) -> StudyStructureReport:
    """Compose one official single-root structure read at the configured current academic year.

    ``module_versions`` supplies the explicit version of each ambiguous module group. An ambiguous
    root without its selection raises ``StudyStructureVersionSelectionRequired``, so the command
    fails nonzero. An ambiguous nested module stays a typed unresolved node in the report.
    """
    report = run_study_structures_command((root_group_id,), module_versions=module_versions)
    if report.version_selection_required:
        raise StudyStructureVersionSelectionRequired(
            f"module {report.version_selection_required[0]!r} needs an explicit version selection"
        )
    return StudyStructureReport(
        academic_year_start=report.academic_year_start, root=report.roots[0]
    )
