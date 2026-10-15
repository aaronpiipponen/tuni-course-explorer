"""Re-export the shared prerequisite catalogue fixtures for the db test tree."""

from __future__ import annotations

from tests.prerequisite.conftest import (
    prerequisite_catalogue,
)

__all__ = [
    "prerequisite_catalogue",
]
