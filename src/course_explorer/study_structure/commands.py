"""Reusable read-only composition for the official structure-of-studies command.

This module owns the process-level orchestration behind `scripts/study_structure.py`: it
validates the canonical root identity before any settings load or I/O, reads the configured
current academic year once, composes the repository-backed structure service inside one engine
lifetime, reads one root structure, and returns one transient JSON report. The report is a
request-local value consumed by the CLI adapter and the web backend.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from course_explorer.config import load_database_settings, load_normalization_settings
from course_explorer.curriculum_repository import CurriculumRepository
from course_explorer.db.session import database_context as _database_context
from course_explorer.study_structure.service import StudyStructureModule, StudyStructureService


class StudyStructureReport(BaseModel):
    """One transient official structure-of-studies report for a canonical root."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    academic_year_start: int
    root: StudyStructureModule


def run_study_structure_command(root_group_id: str) -> StudyStructureReport:
    """Compose one official structure read at the configured current academic year."""
    if not root_group_id.strip():
        raise ValueError("root_group_id must be nonblank")
    academic_year_start = load_normalization_settings().current_academic_year_start
    with _database_context(load_database_settings()) as factory:
        service = StudyStructureService(
            CurriculumRepository(factory), academic_year_start=academic_year_start
        )
        root = service.read(root_group_id)
    return StudyStructureReport(academic_year_start=academic_year_start, root=root)
