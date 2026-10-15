"""Recommendation command report and CLI public contracts."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from course_explorer.next_courses import commands as next_courses_commands
from course_explorer.recommendations import commands as command_module
from course_explorer.recommendations.commands import RecommendationsReport

_SPEC = importlib.util.spec_from_file_location(
    "recommendations", Path(__file__).parents[2] / "scripts" / "recommendations.py"
)
assert _SPEC is not None and _SPEC.loader is not None
_CLI_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_CLI_MODULE)


def test_recommendations_cli_preserves_inputs_and_report(monkeypatch, capsys) -> None:
    """The adapter forwards all toggles once and emits one closed similarity-only JSON report."""
    report = RecommendationsReport(similarity_results=())
    calls = []
    monkeypatch.setattr(
        _CLI_MODULE,
        "run_recommendations_command",
        lambda **kwargs: calls.append(kwargs) or report,
    )
    assert (
        _CLI_MODULE.main(
            [
                "--selected",
                "basis",
                "--completed",
                "basis",
                "--basis",
                "selected",
                "--mode",
                "at_least_one",
                "--include-inferred",
                "--all-courses",
                "--display-language",
                "fi",
            ]
        )
        == 0
    )
    assert calls == [
        {
            "selected_courses": ["basis"],
            "completed_courses": ["basis"],
            "basis": "selected",
            "mode": "at_least_one",
            "display_language": "fi",
            "include_inferred": True,
            "active_only": False,
        }
    ]
    assert capsys.readouterr().out == report.model_dump_json() + "\n"
    assert RecommendationsReport.model_validate_json(report.model_dump_json()) == report


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
    monkeypatch.setattr(next_courses_commands, "load_database_settings", lambda: object())
    monkeypatch.setattr(next_courses_commands, "_database_context", lambda _settings: NoIoContext())
    report = command_module.run_recommendations_command(display_language="en")
    assert report.similarity_results == ()
