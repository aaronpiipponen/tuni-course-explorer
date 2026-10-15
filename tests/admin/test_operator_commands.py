"""Contracts for the unified administrative commands and the engine dispatcher.

The engine CLI owns the parser, dispatch and safe failures. The wrapper delegates to it
and is proven by the import/CLI gate.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from course_explorer_admin import commands
from course_explorer_admin.provisioning import ProvisioningReport, WorkerCodeReport
from course_explorer_admin.provisioning_worker import WorkerResourcesReport

_CLI_SPEC = importlib.util.spec_from_file_location(
    "admin_cli", Path(__file__).parents[2] / "src" / "course_explorer_admin" / "cli.py"
)
assert _CLI_SPEC is not None and _CLI_SPEC.loader is not None
_CLI_MODULE = importlib.util.module_from_spec(_CLI_SPEC)
_CLI_SPEC.loader.exec_module(_CLI_MODULE)


class _Sentinel:
    """One JSON-renderable owner result standing in for a real DTO."""

    def __init__(self, label: str) -> None:
        self.label = label

    def model_dump_json(self) -> str:
        return json.dumps({"label": self.label})


@pytest.mark.parametrize(
    "case",
    [
        "setup-preflight",
        "migration",
        "cli-help-invalid",
        "preflight-not-ready",
        "stage",
        "report-safe-failure",
        "migrate-cli",
        "migrate-safe-failure",
        "hubs-cli",
        "dispose-nothing",
        "dispose-done",
        "dispose-failed",
        "dispose-invalid-syntax",
        "dispose-safe-failure",
    ],
)
def test_operator_setup_preflight_and_cli_preserve_owners_notices_and_safe_failures(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], case: str
) -> None:
    """Setup/preflight forward to owners and the CLI is safe on success and failure.

    Each parametrized invocation drives one coherent public adapter behavior: an owner delegation,
    the CLI help/syntax guard, or one ``dispose inference ...`` machine command with nothing mapped
    to None, invalid syntax, or a safe failure. Assertions live in their owning case instead of one
    combined session-wide call list.
    """
    if case == "setup-preflight":
        worker = _Sentinel("worker")
        code_only = ProvisioningReport(
            code=WorkerCodeReport(branch="main", revision="a" * 40, server_origin_differs=False),
            resources=None,
        )
        enrollment = _Sentinel("enrollment")
        prepared: list[dict] = []
        updated: list[dict] = []
        enrolled: list[dict] = []
        preflighted: list[dict] = []

        monkeypatch.setattr(
            commands,
            "prepare_worker",
            lambda *, branch, runner: prepared.append({"branch": branch}) or worker,
        )
        monkeypatch.setattr(
            commands,
            "update_worker_code",
            lambda *, branch, runner: updated.append({"branch": branch}) or code_only.code,
        )
        monkeypatch.setattr(
            commands,
            "preflight_worker",
            lambda *, runner: preflighted.append({"runner": runner}) or worker,
        )
        from course_explorer_admin import datasets as datasets_module

        monkeypatch.setattr(
            datasets_module,
            "initialize_selected_dataset",
            lambda *, runner: enrolled.append({"runner": runner}) or enrollment,
        )

        # Default main and explicit branch forwarding. Code-only and enrollment stay separate.
        assert commands.run_administrative_setup("worker") is worker
        assert commands.run_administrative_setup("worker", branch="feature") is worker
        assert prepared == [{"branch": "main"}, {"branch": "feature"}]
        assert (
            commands.run_administrative_setup("worker", branch="feature", code_only=True)
            == code_only
        )
        assert updated == [{"branch": "feature"}]
        assert commands.run_administrative_setup("datasets") is enrollment
        assert len(enrolled) == 1
        with pytest.raises(ValueError):
            commands.run_administrative_setup("datasets", code_only=True)
        with pytest.raises(ValueError):
            commands.run_administrative_setup("datasets", branch="feature")
        assert commands.run_administrative_preflight() is worker
        assert len(preflighted) == 1
        return

    if case == "migration":
        # The explicit migration dispatcher delegates once to the guarded owner with its own runner.
        from course_explorer_admin import datasets as datasets_module

        migration = _Sentinel("migration")
        migrated: list[dict] = []
        monkeypatch.setattr(
            datasets_module,
            "migrate_selected_dataset",
            lambda *, runner: migrated.append({"runner": runner}) or migration,
        )
        assert commands.run_administrative_migration() is migration
        assert len(migrated) == 1
        return

    if case == "cli-help-invalid":
        # Real CLI help and invalid syntax perform no owner call.
        delegated: list[object] = []
        monkeypatch.setattr(
            _CLI_MODULE, "run_administrative_setup", lambda *a, **k: delegated.append(1)
        )
        with pytest.raises(SystemExit) as help_exit:
            _CLI_MODULE.main(["--help"])
        assert help_exit.value.code == 0
        with pytest.raises(SystemExit) as bad_exit:
            _CLI_MODULE.main(["bogus"])
        assert bad_exit.value.code != 0
        capsys.readouterr()
        assert delegated == []
        return

    if case == "preflight-not-ready":
        # A not-ready preflight prints its report and exits 1.
        not_ready = ProvisioningReport(
            code=WorkerCodeReport(branch="main", revision="a" * 40, server_origin_differs=True),
            resources=WorkerResourcesReport(ready=False, missing=["dependencies"]),
        )
        monkeypatch.setattr(_CLI_MODULE, "run_administrative_preflight", lambda: not_ready)
        assert _CLI_MODULE.main(["preflight"]) == 1
        captured = capsys.readouterr()
        assert json.loads(captured.out)["resources"]["ready"] is False
        assert captured.err.strip()
        return

    if case == "stage":
        # A lifecycle stage/action routes through the CLI to its one owner call.
        worker = _Sentinel("worker")
        lifecycle_calls: list[tuple[str, str]] = []
        monkeypatch.setattr(
            _CLI_MODULE,
            "run_administrative_command",
            lambda stage, action: lifecycle_calls.append((stage, action)) or worker,
        )
        assert _CLI_MODULE.main(["ingestion", "pause"]) == 0
        captured = capsys.readouterr()
        assert lifecycle_calls == [("ingestion", "pause")]
        assert json.loads(captured.out)["label"] == "worker"
        return

    if case == "report-safe-failure":
        # One synthetic unsafe exception produces only its class token, never the payload.

        def unsafe(kind):
            raise RuntimeError("secret-payload-value")

        monkeypatch.setattr(_CLI_MODULE, "run_administrative_coverage", unsafe)
        assert _CLI_MODULE.main(["coverage", "embedding"]) == 1
        captured = capsys.readouterr()
        assert json.loads(captured.err.splitlines()[0]) == {"error": "RuntimeError"}
        assert "secret-payload-value" not in captured.err
        return

    if case == "migrate-cli":
        # Real CLI `migrate datasets` emits the owner DTO and exits 0. Invalid syntax delegates nothing.
        migration = _Sentinel("migration")
        migrated: list[object] = []
        monkeypatch.setattr(
            _CLI_MODULE,
            "run_administrative_migration",
            lambda: migrated.append(migration) or migration,
        )
        assert _CLI_MODULE.main(["migrate", "datasets"]) == 0
        captured = capsys.readouterr()
        assert json.loads(captured.out)["label"] == "migration"
        with pytest.raises(SystemExit) as bad_migrate:
            _CLI_MODULE.main(["migrate"])
        assert bad_migrate.value.code != 0
        capsys.readouterr()
        assert len(migrated) == 1
        return

    if case == "migrate-safe-failure":
        # A safe migration failure prints only its class token and the migration guidance, exit 1.

        def failing_migration():
            raise RuntimeError("migration-payload-value")

        monkeypatch.setattr(_CLI_MODULE, "run_administrative_migration", failing_migration)
        assert _CLI_MODULE.main(["migrate", "datasets"]) == 1
        captured = capsys.readouterr()
        assert json.loads(captured.err.splitlines()[0]) == {"error": "RuntimeError"}
        assert "migration-payload-value" not in captured.err
        assert "ordinary-stop all four stages" in captured.err
        return

    if case == "hubs-cli":
        # `hubs` delegates once to the hub writer and emits its report.
        hubs = _Sentinel("hubs")
        hub_calls: list[object] = []
        monkeypatch.setattr(
            _CLI_MODULE, "run_administrative_hubs", lambda: hub_calls.append(hubs) or hubs
        )
        assert _CLI_MODULE.main(["hubs"]) == 0
        captured = capsys.readouterr()
        assert json.loads(captured.out)["label"] == "hubs"
        assert len(hub_calls) == 1
        return

    # The explicit `dispose inference ...` machine command: one delegation or safe-failure case.
    disposition_calls: list[tuple[str, object]] = []
    disposition_report = _Sentinel("disposition")
    if case in {"dispose-nothing", "dispose-done", "dispose-failed"}:
        token, expected = {
            "dispose-nothing": ("nothing", None),
            "dispose-done": ("done", "done"),
            "dispose-failed": ("failed", "failed"),
        }[case]
        monkeypatch.setattr(
            _CLI_MODULE,
            "set_inference_target_disposition",
            lambda target, choice: disposition_calls.append((target, choice)) or disposition_report,
        )
        assert _CLI_MODULE.main(["dispose", "inference", "disp-target", token]) == 0
        captured = capsys.readouterr()
        assert json.loads(captured.out)["label"] == "disposition"
        assert disposition_calls == [("disp-target", expected)]
        return

    if case == "dispose-invalid-syntax":
        monkeypatch.setattr(
            _CLI_MODULE,
            "set_inference_target_disposition",
            lambda target, choice: disposition_calls.append((target, choice)) or disposition_report,
        )
        with pytest.raises(SystemExit) as bad_dispose:
            _CLI_MODULE.main(["dispose", "inference", "disp-target"])
        assert bad_dispose.value.code != 0
        with pytest.raises(SystemExit) as bad_dispose_kind:
            _CLI_MODULE.main(["dispose", "translation", "disp-target", "done"])
        assert bad_dispose_kind.value.code != 0
        capsys.readouterr()
        assert disposition_calls == []
        return

    # A safe disposition failure prints only its class token and the disposition guidance, exit 1.
    def failing_disposition(target, choice):
        raise RuntimeError("disposition-payload-value")

    monkeypatch.setattr(_CLI_MODULE, "set_inference_target_disposition", failing_disposition)
    assert _CLI_MODULE.main(["dispose", "inference", "disp-target", "done"]) == 1
    captured = capsys.readouterr()
    assert json.loads(captured.err.splitlines()[0]) == {"error": "RuntimeError"}
    assert "disposition-payload-value" not in captured.err
    assert "ordinary-stop all four stages" in captured.err
