"""Command and CLI contracts for the next-course discovery report."""

from __future__ import annotations

import importlib.util
from decimal import Decimal
from pathlib import Path

import pytest

from course_explorer.config import SearchSettings
from course_explorer.curriculum import CourseSummary
from course_explorer.next_courses import commands as command_module
from course_explorer.next_courses.commands import NextCoursesReport
from course_explorer.next_courses.service import NextCourseMode, NextCourseResult
from course_explorer.prerequisite.commands import PrerequisiteCalculationBasis
from tests.support import settings_factory

_SPEC = importlib.util.spec_from_file_location(
    "next_courses", Path(__file__).parents[2] / "scripts" / "next_courses.py"
)
assert _SPEC is not None and _SPEC.loader is not None
_CLI_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_CLI_MODULE)


def _summary(group_id: str, *, is_active: bool = True) -> CourseSummary:
    """Build one shared official summary fixture for the report round-trip."""
    return CourseSummary(
        group_id=group_id,
        name_fi=None,
        name_en=f"Course {group_id}",
        code=group_id.upper(),
        credits_min=Decimal("5"),
        credits_max=Decimal("5"),
        is_active=is_active,
        official_url=f"https://example.test/{group_id}",
    )


def _report() -> NextCoursesReport:
    """Build one valid prepared report carrying a single result."""
    return NextCoursesReport(
        selected_group_ids=("base",),
        completed_group_ids=("base",),
        basis=PrerequisiteCalculationBasis.COMPLETED,
        mode=NextCourseMode.ALL,
        display_language="en",
        include_inferred=False,
        active_only=True,
        results=(
            NextCourseResult(
                course=_summary("next"),
                required_coverage=1.0,
                recommended_coverage=0.0,
                depends_on_inferred=False,
            ),
        ),
    )


def test_next_courses_command_and_cli(monkeypatch, capsys) -> None:
    """Input fails before I/O, the adapter delegates once with the mode defaults/toggles, and an
    empty chosen basis returns an empty report."""

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

    report = _report()
    assert NextCoursesReport.model_validate_json(report.model_dump_json()) == report

    calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        _CLI_MODULE,
        "run_next_courses_command",
        lambda **kwargs: calls.append(kwargs) or report,
    )
    assert _CLI_MODULE.main(["--completed", "COMP.CS.100", "--display-language", "en"]) == 0
    assert calls[-1] == {
        "selected_courses": [],
        "completed_courses": ["COMP.CS.100"],
        "basis": "completed",
        "mode": "all",
        "display_language": "en",
        "include_inferred": False,
        "active_only": True,
    }
    assert capsys.readouterr().out == report.model_dump_json() + "\n"

    assert (
        _CLI_MODULE.main(
            [
                "--selected",
                "A",
                "--selected",
                "B",
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
    assert calls[-1] == {
        "selected_courses": ["A", "B"],
        "completed_courses": [],
        "basis": "selected",
        "mode": "at_least_one",
        "display_language": "fi",
        "include_inferred": True,
        "active_only": False,
    }
    with pytest.raises(SystemExit):
        _CLI_MODULE.main(["--completed", "A"])

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
