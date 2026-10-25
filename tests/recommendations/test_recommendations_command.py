"""Recommendation command contracts for input validation and an empty basis report."""

from __future__ import annotations

import pytest

from course_explorer.config import DatabaseSettings
from course_explorer.next_courses import commands as next_courses_commands
from course_explorer.recommendations import commands as command_module
from tests.support import settings_factory


def test_recommendations_command_preserves_validation_and_empty_basis(monkeypatch) -> None:
    """Validation runs first. An empty basis preserves its report without embedding I/O."""

    def fail(*_args, **_kwargs):
        pytest.fail("recommendation settings/database I/O reached")

    monkeypatch.setattr(command_module, "load_search_settings", fail)
    monkeypatch.setattr(command_module, "load_embedding_settings", fail)
    monkeypatch.setattr(command_module, "load_database_settings", fail)
    monkeypatch.setattr(command_module, "database_context", fail)
    with pytest.raises(ValueError):
        command_module.run_recommendations_command(selected_courses=(" ",), display_language="en")

    class NoIoContext:
        def __enter__(self):
            return object()

        def __exit__(self, *_exc):
            return False

    monkeypatch.setattr(next_courses_commands, "load_search_settings", lambda: object())
    monkeypatch.setattr(next_courses_commands, "load_database_settings", fail)
    monkeypatch.setattr(next_courses_commands, "_database_context", lambda _settings: NoIoContext())
    report = command_module.run_recommendations_command(
        display_language="en", database_settings=settings_factory(DatabaseSettings)
    )
    assert report.similarity_results == ()
