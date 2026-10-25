"""Contracts for the unified administrative commands and the engine dispatcher.

The engine CLI owns the parser, dispatch and safe failures. The wrapper delegates to it
and is proven by the import/CLI gate.
"""

from __future__ import annotations

import getpass
import importlib.util
import json
import warnings
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
        "preflight-not-ready",
        "report-safe-failure",
        "config-safe-set-failure",
        "password-delegate",
        "password-mismatch",
        "password-hidden-input-failure",
        "password-safe-failure",
        "dispose-nothing",
    ],
)
def test_operator_commands_report_status_refuse_bad_input_and_map_nothing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], case: str
) -> None:
    """Public input refusal, preflight status, hidden password entry, safe failures and ``nothing``.

    Each parametrized invocation drives one coherent public adapter behavior. Invalid dataset setup
    combinations refuse at the public command entry, a not-ready preflight exits 1 with its report,
    a failed report or configuration save prints only its class token, the password command reads
    hidden input, and ``dispose inference ... nothing`` maps to no disposition.
    """
    if case == "setup-preflight":
        worker = _Sentinel("worker")
        code_only = ProvisioningReport(
            code=WorkerCodeReport(branch="main", revision="a" * 40, server_origin_differs=False),
            resources=None,
        )
        enrollment = _Sentinel("enrollment")
        from course_explorer_admin import datasets as datasets_module

        monkeypatch.setattr(commands, "prepare_worker", lambda *, branch, runner: worker)
        monkeypatch.setattr(
            commands,
            "update_worker_code",
            lambda *, branch, runner: code_only.code,
        )
        monkeypatch.setattr(commands, "preflight_worker", lambda *, runner: worker)
        monkeypatch.setattr(
            datasets_module,
            "initialize_selected_dataset",
            lambda *, runner: enrollment,
        )

        # Invalid dataset setup combinations refuse at the public command entry.
        with pytest.raises(ValueError):
            commands.run_administrative_setup("datasets", code_only=True)
        with pytest.raises(ValueError):
            commands.run_administrative_setup("datasets", branch="feature")
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

    if case == "config-safe-set-failure":
        # A failed configuration save prints only its class token, the guidance and no value.
        def failing_set(file, key, value, *, settings_families=()):
            raise RuntimeError("configuration-payload-value")

        monkeypatch.setattr(_CLI_MODULE, "run_administrative_config_set", failing_set)
        assert _CLI_MODULE.main(["config", "set", "config/web.toml", "WEB_PORT", "18026"]) == 1
        captured = capsys.readouterr()
        assert json.loads(captured.err.splitlines()[0]) == {"error": "RuntimeError"}
        assert "configuration-payload-value" not in captured.err
        return

    if case in {"password-delegate", "password-mismatch", "password-hidden-input-failure"}:
        # The password command reads twice through the supplied hidden reader and delegates once.
        report = commands.PasswordSetReport()
        delegated: list[dict] = []
        monkeypatch.setattr(
            commands,
            "set_admin_password",
            lambda *, username, password: (
                delegated.append({"username": username, "password": password}) or report
            ),
        )
        if case == "password-hidden-input-failure":
            # An entry the terminal cannot hide is an error rather than an echoed fallback.
            def warning_reader(prompt: str) -> str:
                warnings.warn("input will be echoed", getpass.GetPassWarning)
                return "synthetic-entry"

            with pytest.raises(getpass.GetPassWarning):
                commands.run_administrative_password(
                    username="synthetic-operator", read_password=warning_reader
                )
            assert delegated == []
            return
        answers = ["first-entry", "first-entry"]
        if case == "password-mismatch":
            answers = ["first-entry", "other-entry"]

        def reader(_prompt: str) -> str:
            return answers.pop(0)

        if case == "password-mismatch":
            with pytest.raises(ValueError):
                commands.run_administrative_password(
                    username="synthetic-operator", read_password=reader
                )
            assert delegated == []
            return
        assert (
            commands.run_administrative_password(
                username="synthetic-operator", read_password=reader
            )
            == report
        )
        assert len(delegated) == 1
        assert delegated[0]["username"] == "synthetic-operator"
        assert delegated[0]["password"].get_secret_value() == "first-entry"
        assert "first-entry" not in report.model_dump_json()
        return

    if case == "password-safe-failure":
        # A failed password command prints only its class token and the hidden-entry guidance.

        def failing_password(*, username):
            raise RuntimeError("password-payload-value")

        monkeypatch.setattr(_CLI_MODULE, "run_administrative_password", failing_password)
        assert _CLI_MODULE.main(["password", "--username", "synthetic-operator"]) == 1
        captured = capsys.readouterr()
        assert json.loads(captured.err.splitlines()[0]) == {"error": "RuntimeError"}
        assert "password-payload-value" not in captured.err
        return

    # The explicit `dispose inference ... nothing` machine command maps to no disposition.
    disposition_calls: list[tuple[str, object]] = []
    disposition_report = _Sentinel("disposition")
    monkeypatch.setattr(
        _CLI_MODULE,
        "set_inference_target_disposition",
        lambda target, choice: disposition_calls.append((target, choice)) or disposition_report,
    )
    assert _CLI_MODULE.main(["dispose", "inference", "disp-target", "nothing"]) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out)["label"] == "disposition"
    assert disposition_calls == [("disp-target", None)]
