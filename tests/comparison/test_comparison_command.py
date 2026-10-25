"""Command contracts for course comparison."""

from __future__ import annotations

import pytest

from course_explorer.comparison import commands as command_module


def test_comparison_command_rejects_blank_inputs_before_io(monkeypatch) -> None:
    """Blank input refuses before any settings load."""
    monkeypatch.setattr(
        command_module, "load_search_settings", lambda: pytest.fail("settings load reached")
    )
    monkeypatch.setattr(
        command_module, "load_embedding_settings", lambda: pytest.fail("settings load reached")
    )
    monkeypatch.setattr(
        command_module, "load_database_settings", lambda: pytest.fail("settings load reached")
    )
    with pytest.raises(ValueError):
        command_module.run_course_comparison_command("   ", "B.1")
    with pytest.raises(ValueError):
        command_module.run_course_comparison_command("A.1", "   ")
