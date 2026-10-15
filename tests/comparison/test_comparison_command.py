"""Command and CLI contracts for course comparison."""

from __future__ import annotations

import importlib.util
from decimal import Decimal
from pathlib import Path

import pytest

from course_explorer.comparison import commands as command_module
from course_explorer.comparison.commands import CourseComparisonReport
from course_explorer.comparison.service import ComparisonMeters, DirectionalOverlap
from course_explorer.curriculum import CourseSummary

_CLI_SPEC = importlib.util.spec_from_file_location(
    "compare_courses", Path(__file__).parents[2] / "scripts" / "compare_courses.py"
)
assert _CLI_SPEC is not None and _CLI_SPEC.loader is not None
_CLI_MODULE = importlib.util.module_from_spec(_CLI_SPEC)
_CLI_SPEC.loader.exec_module(_CLI_MODULE)


def _summary(group_id: str, code: str, *, is_active: bool = True) -> CourseSummary:
    """Build one shared official summary fixture for the report round-trip."""
    return CourseSummary(
        group_id=group_id,
        name_fi=None,
        name_en=f"Course {group_id}",
        code=code,
        credits_min=Decimal("5"),
        credits_max=Decimal("5"),
        is_active=is_active,
        official_url=f"https://example.test/{group_id}",
    )


def test_comparison_command_and_cli_report(monkeypatch, capsys) -> None:
    """Blank inputs fail before settings/I/O and the CLI delegates two identities once."""
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

    report = CourseComparisonReport(
        course_a=_summary("group-a", "A.1"),
        course_b=_summary("group-b", "B.1", is_active=False),
        meters=ComparisonMeters(
            overall_relatedness=90.0,
            content_similarity=80.0,
            learning_outcome_similarity=None,
            overlap=DirectionalOverlap(a_in_b=100.0, b_in_a=40.0),
        ),
        verdict="heavily_overlapping",
        uses_derived_text=False,
    )
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        _CLI_MODULE,
        "run_course_comparison_command",
        lambda course_a, course_b: calls.append((course_a, course_b)) or report,
    )

    assert _CLI_MODULE.main(["A.1", "B.1"]) == 0
    assert calls == [("A.1", "B.1")]
    assert report.course_b.is_active is False
    assert capsys.readouterr().out == report.model_dump_json() + "\n"

    with pytest.raises(SystemExit):
        _CLI_MODULE.main(["A.1"])
