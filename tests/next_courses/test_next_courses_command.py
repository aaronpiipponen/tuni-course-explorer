"""Command contracts for the next-course discovery report."""

from __future__ import annotations

import pytest

from course_explorer.config import SearchSettings
from course_explorer.next_courses import commands as command_module
from course_explorer.next_courses.service import NextCourseMode
from course_explorer.prerequisite.commands import PrerequisiteCalculationBasis
from tests.support import settings_factory


def test_next_courses_command_validates_inputs_and_shortcuts_empty_basis(monkeypatch) -> None:
    """Input fails before I/O and an empty chosen basis returns an empty report."""

    def _fail(*_args, **_kwargs):
        pytest.fail("settings or database I/O reached")

    monkeypatch.setattr(command_module, "load_search_settings", _fail)
    monkeypatch.setattr(command_module, "load_database_settings", _fail)
    monkeypatch.setattr(command_module, "_database_context", _fail)
    with pytest.raises(ValueError):
        command_module.run_next_courses_command(selected_courses=["   "], display_language="en")
    with pytest.raises(ValueError):
        command_module.run_next_courses_command(display_language="en", basis="bogus")
    with pytest.raises(ValueError):
        command_module.run_next_courses_command(display_language="en", mode="bogus")
    with pytest.raises(ValueError):
        command_module.run_next_courses_command(display_language="de")

    # An empty chosen basis returns the report without any candidate or compiler read. Only
    # the settings/database boundary is substituted, never the business calculation.
    class _NoIoContext:
        def __enter__(self):
            return object()

        def __exit__(self, *_exc):
            return False

    monkeypatch.setattr(
        command_module, "load_search_settings", lambda: settings_factory(SearchSettings)
    )
    monkeypatch.setattr(command_module, "load_database_settings", lambda: object())
    monkeypatch.setattr(command_module, "_database_context", lambda _settings: _NoIoContext())
    empty = command_module.run_next_courses_command(display_language="en")
    assert empty.results == ()
    assert empty.selected_group_ids == ()
    assert empty.completed_group_ids == ()
    assert empty.basis is PrerequisiteCalculationBasis.COMPLETED
    assert empty.mode is NextCourseMode.ALL
    assert empty.include_inferred is False
    assert empty.active_only is True
