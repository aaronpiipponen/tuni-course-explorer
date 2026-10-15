"""Command and CLI contracts for the structure-of-studies command."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from course_explorer.curriculum import ModuleSummary
from course_explorer.enums import ModuleRuleType, ModuleType
from course_explorer.study_structure import commands as command_module
from course_explorer.study_structure.commands import StudyStructureReport
from course_explorer.study_structure.service import StudyStructureModule, StudyStructureRule


def _load_script(name: str):
    """Import one ``scripts/`` adapter as a standalone module."""
    spec = importlib.util.spec_from_file_location(
        name, Path(__file__).parents[2] / "scripts" / f"{name}.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_STRUCTURE_CLI = _load_script("study_structure")


def test_structure_command_and_cli_report(monkeypatch, capsys) -> None:
    """The command refuses blank input before settings and the CLI prints one delegated report."""

    def _fail():
        pytest.fail("settings load reached")

    monkeypatch.setattr(command_module, "load_normalization_settings", _fail)
    monkeypatch.setattr(command_module, "load_database_settings", _fail)
    with pytest.raises(ValueError):
        command_module.run_study_structure_command("   ")

    report = StudyStructureReport(
        academic_year_start=2026,
        root=StudyStructureModule(
            module=ModuleSummary(
                group_id="module-group-x",
                sisu_module_id="module-group-x-v1",
                module_type=ModuleType.STUDY_MODULE,
                code=None,
                name_fi=None,
                name_en="X",
            ),
            rule=StudyStructureRule(node_type=ModuleRuleType.ANY_MODULE_RULE, sibling_position=0),
        ),
    )
    calls: list[str] = []
    monkeypatch.setattr(
        _STRUCTURE_CLI,
        "run_study_structure_command",
        lambda root_group_id: calls.append(root_group_id) or report,
    )

    assert _STRUCTURE_CLI.main(["module-group-x"]) == 0
    assert calls == ["module-group-x"]
    assert capsys.readouterr().out == report.model_dump_json() + "\n"

    with pytest.raises(SystemExit):
        _STRUCTURE_CLI.main(["module-group-x", "--active-only"])
