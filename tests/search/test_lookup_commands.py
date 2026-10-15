"""Command and CLI contracts for course and module substring lookup."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from course_explorer.search import lookup_commands as command_module
from course_explorer.search.lookup_commands import CourseLookupReport, ModuleLookupReport


def _load_script(name: str):
    """Import one ``scripts/`` adapter as a standalone module."""
    spec = importlib.util.spec_from_file_location(
        name, Path(__file__).parents[2] / "scripts" / f"{name}.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_COURSE_CLI = _load_script("course_lookup")
_MODULE_CLI = _load_script("module_lookup")


def test_lookup_commands_reject_invalid_input_before_settings(monkeypatch) -> None:
    """Both commands refuse blank or unsupported input before loading settings or opening a DB."""

    def _fail():
        pytest.fail("settings load reached")

    monkeypatch.setattr(command_module, "load_search_settings", _fail)
    monkeypatch.setattr(command_module, "load_normalization_settings", _fail)
    monkeypatch.setattr(command_module, "load_database_settings", _fail)
    runners = (
        command_module.run_course_lookup_command,
        command_module.run_module_lookup_command,
    )
    for runner in runners:
        with pytest.raises(ValueError):
            runner("   ", display_language="fi")
        with pytest.raises(ValueError):
            runner("tensorit", display_language="de")

    from fastapi.testclient import TestClient

    from course_explorer_web.app import app

    response = TestClient(app).post(
        "/api/course-lookup", json={"query": "   ", "display_language": "fi"}
    )
    assert response.status_code == 422
    assert response.json() == {"detail": "lookup query must be nonblank"}
    assert command_module.run_course_summaries_command(()).results == ()


@pytest.mark.parametrize(
    ("cli_module", "function_name", "report", "argv", "expected_kwargs"),
    [
        (
            _COURSE_CLI,
            "run_course_lookup_command",
            CourseLookupReport(
                query="COMP.CS",
                display_language="fi",
                include_inactive=True,
                results=(),
            ),
            ["COMP.CS", "--display-language", "fi", "--active-only"],
            {"display_language": "fi", "include_inactive": False},
        ),
        (
            _MODULE_CLI,
            "run_module_lookup_command",
            ModuleLookupReport(
                query="tietotekniikka",
                display_language="en",
                academic_year_start=2026,
                results=(),
            ),
            ["tietotekniikka", "--display-language", "en"],
            {"display_language": "en"},
        ),
    ],
)
def test_lookup_cli_forwards_options_and_prints_one_report(
    monkeypatch, capsys, cli_module, function_name, report, argv, expected_kwargs
) -> None:
    """Each CLI delegates once with forwarded options and prints exactly one JSON report."""
    calls: list[dict] = []
    monkeypatch.setattr(
        cli_module,
        function_name,
        lambda query, **kwargs: calls.append({"query": query, **kwargs}) or report,
    )

    assert cli_module.main(argv) == 0
    assert calls == [{"query": argv[0], **expected_kwargs}]
    assert capsys.readouterr().out == report.model_dump_json() + "\n"

    # The module adapter exposes the query and display-language options only.
    if function_name == "run_module_lookup_command":
        with pytest.raises(SystemExit):
            cli_module.main(["tietotekniikka", "--display-language", "fi", "--active-only"])
