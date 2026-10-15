"""Prerequisite integration fixtures shared by the prerequisite, db and inference test trees."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import pytest
from sqlalchemy import Engine, select

from course_explorer.db.models import Course
from course_explorer.db.session import session_scope


@dataclass(frozen=True)
class PrerequisiteCatalogueSeed:
    """Distinct canonical courses and shared activity context for inferred-set tests."""

    active_target_group_id: str
    inactive_target_group_id: str
    active_source_group_id: str
    inactive_source_group_id: str
    activity_as_of_academic_year_start: int
    activity_window_years: int


@pytest.fixture()
def prerequisite_catalogue(
    database: tuple[Engine, object],
) -> PrerequisiteCatalogueSeed:
    """Seed active/inactive target and source canonical courses through the live schema."""
    _, factory = database
    seed = PrerequisiteCatalogueSeed(
        active_target_group_id="prerequisite-active-target",
        inactive_target_group_id="prerequisite-inactive-target",
        active_source_group_id="prerequisite-active-source",
        inactive_source_group_id="prerequisite-inactive-source",
        activity_as_of_academic_year_start=2026,
        activity_window_years=3,
    )
    with session_scope(factory) as session:
        for group_id, is_active in (
            (seed.active_target_group_id, True),
            (seed.inactive_target_group_id, False),
            (seed.active_source_group_id, True),
            (seed.inactive_source_group_id, False),
        ):
            session.add(
                Course(
                    group_id=group_id,
                    is_active=is_active,
                    activity_as_of_academic_year_start=seed.activity_as_of_academic_year_start,
                    activity_window_years=seed.activity_window_years,
                )
            )
    return seed


@pytest.fixture()
def set_prerequisite_course_activity(
    database: tuple[Engine, object],
) -> Callable[[str, bool, int, int], None]:
    """Return test-only setup that simulates an authoritative activity recalculation."""
    _, factory = database

    def set_activity(
        group_id: str,
        is_active: bool,
        activity_as_of_academic_year_start: int,
        activity_window_years: int,
    ) -> None:
        """Update only one canonical course's three activity fields."""
        with session_scope(factory) as session:
            course = session.scalar(select(Course).where(Course.group_id == group_id))
            if course is None:
                raise ValueError(f"unknown canonical course {group_id}")
            course.is_active = is_active
            course.activity_as_of_academic_year_start = activity_as_of_academic_year_start
            course.activity_window_years = activity_window_years

    return set_activity
