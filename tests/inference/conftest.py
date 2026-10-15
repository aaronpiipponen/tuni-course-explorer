"""Re-export the shared prerequisite catalogue fixtures for the inference test tree."""

from __future__ import annotations

from tests.prerequisite.conftest import (
    PrerequisiteCatalogueSeed,
    prerequisite_catalogue,
    set_prerequisite_course_activity,
)

__all__ = [
    "PrerequisiteCatalogueSeed",
    "prerequisite_catalogue",
    "set_prerequisite_course_activity",
]
