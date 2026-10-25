"""Shared command search settings for the prerequisite integration tests."""

from __future__ import annotations

from course_explorer.config import SearchSettings
from tests.support import settings_factory


def search_settings() -> SearchSettings:
    """Build the real required search policy from the composed public configuration."""
    return settings_factory(SearchSettings)
