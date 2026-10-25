"""Command and CLI contracts for the structure-of-studies command."""

from __future__ import annotations

import importlib.util
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import pytest

from course_explorer.curriculum import ModuleSummary
from course_explorer.enums import ModuleRuleType, ModuleType
from course_explorer.study_structure import commands as command_module
from course_explorer.study_structure.commands import StudyStructureReport
from course_explorer.study_structure.service import (
    StudyStructureBatch,
    StudyStructureModule,
    StudyStructureRule,
)


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

    service_calls: list[tuple[tuple[str, ...], bool, dict[str, str]]] = []

    class _Service:
        def __init__(self, *_args, **_kwargs):
            pass

        def read_many(self, root_group_ids, *, allow_unavailable=False, module_versions=None):
            service_calls.append(
                (tuple(root_group_ids), allow_unavailable, dict(module_versions or {}))
            )
            return StudyStructureBatch(roots=(), unavailable_root_group_ids=())

    monkeypatch.setattr(command_module, "StudyStructureService", _Service)
    monkeypatch.setattr(command_module, "CurriculumRepository", lambda _factory: object())
    monkeypatch.setattr(
        command_module, "_database_context", lambda _settings: nullcontext(object())
    )
    monkeypatch.setattr(
        command_module,
        "load_normalization_settings",
        lambda: SimpleNamespace(current_academic_year_start=2026),
    )
    monkeypatch.setattr(command_module, "load_database_settings", lambda: object())
    command_module.run_study_structures_command(
        ("module-group-x",),
        module_versions={"module-group-x": "module-group-x-v1"},
    )
    assert service_calls == [(("module-group-x",), False, {"module-group-x": "module-group-x-v1"})]

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
    calls: list[tuple[str, dict[str, str]]] = []

    def _run(root_group_id, *, module_versions=None):
        calls.append((root_group_id, dict(module_versions or {})))
        return report

    monkeypatch.setattr(_STRUCTURE_CLI, "run_study_structure_command", _run)

    assert _STRUCTURE_CLI.main(["module-group-x"]) == 0
    assert calls == [("module-group-x", {})]
    assert capsys.readouterr().out == report.model_dump_json() + "\n"

    assert (
        _STRUCTURE_CLI.main(
            [
                "module-group-x",
                "--module-version",
                "  module-group-x = module-group-x-v1  ",
            ]
        )
        == 0
    )
    assert calls[-1] == ("module-group-x", {"module-group-x": "module-group-x-v1"})
    capsys.readouterr()

    with pytest.raises(SystemExit):
        _STRUCTURE_CLI.main(
            [
                "module-group-x",
                "--module-version",
                "module-group-x=one",
                "--module-version",
                "module-group-x=two",
            ]
        )
    with pytest.raises(SystemExit):
        _STRUCTURE_CLI.main(["module-group-x", "--active-only"])
