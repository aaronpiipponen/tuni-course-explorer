"""Command contracts for the structure-of-studies command."""

from __future__ import annotations

from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from course_explorer.study_structure import commands as command_module
from course_explorer.study_structure.service import StudyStructureBatch


def test_structure_command_validates_input_and_forwards_version_selection(monkeypatch) -> None:
    """The command refuses blank input before settings and forwards selected module versions."""

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
