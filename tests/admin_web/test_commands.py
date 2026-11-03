"""Behavior proofs for the fixed-command runner and the sole bounded command log."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import BaseModel, ValidationError

from course_explorer_admin import commands as administrative_commands
from course_explorer_admin.commands import format_operator_error
from course_explorer_admin_web import runner as admin_runner
from course_explorer_admin_web.command_log import CommandLog, CommandLogEntry
from course_explorer_admin_web.runner import (
    AdminRebuildCommand,
    BackupDeleteCommand,
    BackupListCommand,
    CommandLogCommand,
    ConfigFilesCommand,
    ConfigReadCommand,
    ConfigSetCommand,
    CoverageCommand,
    DatasetCopyCommand,
    DatasetDeleteCommand,
    DatasetListCommand,
    DatasetMigrateCommand,
    DatasetPromotionCommand,
    DatasetSetupCommand,
    EmbeddingLogCommand,
    FeedbackAttachmentCommand,
    FeedbackDeleteCommand,
    FeedbackListCommand,
    FixedCommandRunner,
    LogSessionsCommand,
    RebuildCommand,
    RestartAdminCommand,
    ServerStatusCommand,
    ServingArtifactsCommand,
    SessionLogCommand,
    StageCommand,
    SummaryCommand,
    TargetDecisionCommand,
    TargetReadCommand,
    UsageCommand,
    WorkerPreflightCommand,
    WorkerSetupCommand,
)
from tests.admin_web import _support

_ENTRY_FIELDS = {
    "time",
    "command",
    "exit_code",
    "duration_seconds",
    "result",
    "failure_line",
}

# The canonical identities the target and dataset shapes carry. Neither may reach the log.
_TARGET_ID = "tuni-canonical-0f3a91"
_DATASET_ID = "b" * 32

# One listed log session identity and the one listed configuration file the log and settings
# shapes read.
_LOG_SESSION_ID = "d" * 32
_CONFIG_FILE = "config/web.toml"

# One feedback submission, one of its attachments and one search/filter input. None of these may
# reach a retained log entry, and the report carrier stands for the attachment's transient bytes.
_FEEDBACK_ID = "3f1c2a64-5b7d-4e29-8c10-6a9d2b4e7f01"
_ATTACHMENT_ID = "8e2d4b17-9c63-4a52-b0f8-1d7c3e5a9b24"
_FEEDBACK_QUERY = "-leading-hyphen query"
_FEEDBACK_FILTERS = {"role": "student"}
_ATTACHMENT_CARRIER = "c3ludGhldGljLWF0dGFjaG1lbnQtY2Fycmllcg=="

# One admitted command shape beyond the two common ones: its request, its exact argv tail and its
# fixed log label.
_ADMITTED_SHAPES: dict[str, tuple[object, tuple[str, ...], str]] = {
    "feedback-list": (
        FeedbackListCommand(kind="feedback-list", query=_FEEDBACK_QUERY, filters=_FEEDBACK_FILTERS),
        (
            "feedback",
            "list",
            f"--query={_FEEDBACK_QUERY}",
            f"--filters={json.dumps(_FEEDBACK_FILTERS)}",
        ),
        "feedback list",
    ),
    "feedback-list-narrow": (
        FeedbackListCommand(kind="feedback-list"),
        ("feedback", "list", "--filters={}"),
        "feedback list",
    ),
    "feedback-attachment": (
        FeedbackAttachmentCommand(
            kind="feedback-attachment",
            feedback_id=UUID(_FEEDBACK_ID),
            attachment_id=UUID(_ATTACHMENT_ID),
        ),
        ("feedback", "attachment", _FEEDBACK_ID, _ATTACHMENT_ID),
        "feedback attachment",
    ),
    "feedback-delete": (
        FeedbackDeleteCommand(kind="feedback-delete", feedback_id=UUID(_FEEDBACK_ID)),
        ("feedback", "delete", _FEEDBACK_ID),
        "feedback delete",
    ),
    "stage-action": (
        StageCommand(kind="stage", stage="translation", action="pause"),
        ("translation", "pause"),
        "translation pause",
    ),
    "serving-artifacts": (
        ServingArtifactsCommand(kind="serving-artifacts"),
        ("serving-artifacts",),
        "serving artifacts",
    ),
    "target-read": (
        TargetReadCommand(kind="target-read", target_id=_TARGET_ID),
        ("target", "inference", _TARGET_ID),
        "target inference",
    ),
    "target-decision": (
        TargetDecisionCommand(kind="target-decision", target_id=_TARGET_ID, disposition="done"),
        ("dispose", "inference", _TARGET_ID, "done"),
        "dispose inference",
    ),
    "datasets-delete": (
        DatasetDeleteCommand(kind="datasets-delete", dataset_id=_DATASET_ID),
        ("datasets", "delete", _DATASET_ID),
        "datasets delete",
    ),
    "datasets-delete-working": (
        DatasetDeleteCommand(kind="datasets-delete", dataset_id=_DATASET_ID, confirm_working=True),
        ("datasets", "delete", _DATASET_ID, "--confirm-working"),
        "datasets delete",
    ),
    "datasets-copy-to-working": (
        DatasetCopyCommand(kind="datasets-copy-to-working", source_dataset_id=_DATASET_ID),
        ("datasets", "copy-to-working", _DATASET_ID),
        "datasets copy-to-working",
    ),
    "command-log": (
        CommandLogCommand(kind="command-log"),
        ("logs", "commands"),
        "logs commands",
    ),
    "log-sessions": (
        LogSessionsCommand(kind="log-sessions"),
        ("logs", "sessions"),
        "logs sessions",
    ),
    "session-log": (
        SessionLogCommand(
            kind="session-log",
            stage="inference",
            session_id=_LOG_SESSION_ID,
            source="worker-runner",
            lines=5,
        ),
        ("logs", "read", "inference", _LOG_SESSION_ID, "worker-runner", "--lines", "5"),
        "logs read",
    ),
    "embedding-log": (
        EmbeddingLogCommand(kind="embedding-log", lines=7),
        ("logs", "embedding", "--lines", "7"),
        "logs embedding",
    ),
    "config-files": (
        ConfigFilesCommand(kind="config-files"),
        ("config", "list"),
        "config list",
    ),
    "config-read": (
        ConfigReadCommand(kind="config-read", file=_CONFIG_FILE),
        ("config", "read", "--", _CONFIG_FILE),
        "config read",
    ),
    "config-set": (
        ConfigSetCommand(kind="config-set", file=_CONFIG_FILE, key="WEB_PORT", value="18026"),
        ("config", "set", "--", _CONFIG_FILE, "WEB_PORT", "18026"),
        "config set",
    ),
    "backups-list": (
        BackupListCommand(kind="backups-list"),
        ("backups", "list"),
        "backups list",
    ),
    "backups-delete": (
        BackupDeleteCommand(kind="backups-delete", name="before-inference.dump"),
        ("backups", "delete", "--", "before-inference.dump"),
        "backups delete",
    ),
    "rebuild": (RebuildCommand(kind="rebuild"), ("rebuild",), "rebuild"),
    "rebuild-admin": (
        AdminRebuildCommand(kind="rebuild-admin"),
        ("rebuild-admin",),
        "rebuild-admin",
    ),
    "restart-admin": (
        RestartAdminCommand(kind="restart-admin"),
        ("restart-admin",),
        "restart-admin",
    ),
    "datasets-setup": (
        DatasetSetupCommand(kind="datasets-setup"),
        ("setup", "datasets"),
        "setup datasets",
    ),
    "datasets-migrate": (
        DatasetMigrateCommand(kind="datasets-migrate", role="selected"),
        ("migrate", "selected"),
        "migrate selected",
    ),
    "datasets-migrate-working": (
        DatasetMigrateCommand(kind="datasets-migrate", role="working"),
        ("migrate", "working"),
        "migrate working",
    ),
    "datasets-migrate-database": (
        DatasetMigrateCommand(kind="datasets-migrate", role="database"),
        ("migrate", "database"),
        "migrate database",
    ),
    "worker-setup": (
        WorkerSetupCommand(kind="worker-setup", branch="origin-branch", code_only=True),
        ("setup", "worker", "--branch=origin-branch", "--code-only"),
        "setup worker",
    ),
    "worker-setup-code-only-false": (
        WorkerSetupCommand(kind="worker-setup", branch="origin-branch", code_only=False),
        ("setup", "worker", "--branch=origin-branch"),
        "setup worker",
    ),
    "worker-preflight": (
        WorkerPreflightCommand(kind="worker-preflight"),
        ("preflight",),
        "preflight",
    ),
}


def _script(root: Path) -> str:
    """Return the fixed administrative script path the runner must execute."""
    return str(root / "scripts" / "admin.py")


class _ReadReport(BaseModel):
    """One small report an in-process read returns."""

    report: str


_READ_CASES: dict[str, tuple[object, str, str]] = {
    "server-status-read": (
        ServerStatusCommand(kind="server-status"),
        "run_administrative_server_status",
        "server status",
    ),
    "datasets-list-read": (
        DatasetListCommand(kind="datasets-list"),
        "run_administrative_dataset_list",
        "datasets list",
    ),
    "coverage-read": (
        CoverageCommand(kind="coverage", report="embedding"),
        "run_administrative_coverage",
        "coverage embedding",
    ),
    "summary-read": (
        SummaryCommand(kind="summary", report="inference"),
        "run_administrative_summary",
        "summary inference",
    ),
    "stage-status-read": (
        StageCommand(kind="stage", stage="ingestion", action="status"),
        "run_administrative_command",
        "ingestion status",
    ),
}

# The one admitted mutation that runs in process, because its owner reports each coarse step.
_PROMOTION_CASE = (
    DatasetPromotionCommand(
        kind="datasets-copy-to-selected",
        source_dataset_id=_DATASET_ID,
        confirm_restart=True,
    ),
    "run_administrative_dataset_promotion",
    "datasets copy-to-selected",
)


@pytest.mark.parametrize(
    "case",
    [
        "usage-success",
        "usage-window",
        "checked-failure",
        "process-boundary-failure",
        "malformed-stdout",
        "invalid-command",
        "in-process-failure",
        "promotion",
        *_ADMITTED_SHAPES,
        *_READ_CASES,
    ],
)
def test_admin_command_runner_executes_only_fixed_commands(
    tmp_path: Path, case: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The runner builds one allowed fixed argv for each subprocess case and records one outcome."""
    root = tmp_path / "checkout"
    root.mkdir()
    log = CommandLog(root, limit=5)

    if case == "invalid-command":
        boundary = _support.ScriptedProcessBoundary()
        runner = FixedCommandRunner(root, log, runner=boundary)
        with pytest.raises(ValidationError):
            runner.run({"kind": "disk-space"})
        with pytest.raises(ValidationError):
            runner.run({"kind": "usage", "hours": 24, "command": "rm -rf /"})
        # A positional target must not reach the command's own parser as an option.
        with pytest.raises(ValidationError):
            runner.run({"kind": "target-read", "target_id": "--code-only"})
        with pytest.raises(ValidationError):
            runner.run(
                {"kind": "config-set", "file": _CONFIG_FILE, "key": "WEB_PORT", "value": "1\x002"}
            )
        # A feedback shape requires both stored identities and no extra path.
        with pytest.raises(ValidationError):
            runner.run(
                {
                    "kind": "feedback-attachment",
                    "feedback_id": _FEEDBACK_ID,
                    "attachment_id": _ATTACHMENT_ID,
                    "path": "/etc/passwd",
                }
            )
        with pytest.raises(ValidationError):
            runner.run({"kind": "feedback-delete", "feedback_id": f"{_FEEDBACK_ID}/../x"})
        with pytest.raises(ValidationError):
            runner.run({"kind": "feedback-list", "query": "needle\x00tail"})
        with pytest.raises(ValidationError):
            runner.run({"kind": "feedback-list", "filters": {"role": "student\x00"}})
        # A log source outside the fixed vocabulary and a non-positive line count are refused.
        with pytest.raises(ValidationError):
            runner.run(
                {
                    "kind": "session-log",
                    "stage": "inference",
                    "session_id": _LOG_SESSION_ID,
                    "source": "keepalive",
                    "lines": 0,
                }
            )
        with pytest.raises(ValidationError):
            runner.run(
                {
                    "kind": "session-log",
                    "stage": "inference",
                    "session_id": _LOG_SESSION_ID,
                    "source": "bogus",
                    "lines": 5,
                }
            )
        assert boundary.calls == []
        assert log.read() == ()
        return

    if case == "in-process-failure":

        def failing(**_kwargs: object) -> object:
            raise RuntimeError(_support.OUTPUT_SENTINEL)

        monkeypatch.setattr(administrative_commands, "run_administrative_server_status", failing)
        boundary = _support.ScriptedProcessBoundary()
        runner = FixedCommandRunner(root, log, runner=boundary)
        result = runner.run(ServerStatusCommand(kind="server-status"))
        assert result.exit_code == 1
        assert result.report is None
        assert result.failure_line == format_operator_error(RuntimeError("failure"))
        assert result.guidance_line == administrative_commands.operator_guidance("server")
        assert _support.OUTPUT_SENTINEL not in result.model_dump_json()
        entry = log.read()[-1]
        assert entry.command == "server status"
        assert entry.result == "failure"
        assert entry.failure_line == result.failure_line
        # The guidance line is response data alone, and the entry keeps its six fields.
        assert result.guidance_line not in (root / _support.COMMAND_LOG_PATH).read_text(
            encoding="utf-8"
        )
        assert set(entry.model_dump()) == _ENTRY_FIELDS
        return

    if case in _READ_CASES:
        request, function, label = _READ_CASES[case]
        report = _ReadReport(report=_support.VALUE_SENTINEL)
        monkeypatch.setattr(administrative_commands, function, lambda *_args, **_kwargs: report)
        expected_report: dict[str, object] = report.model_dump(mode="json")
        if case in {"coverage-read", "summary-read"}:
            monkeypatch.setattr(admin_runner, "_report_role", lambda: "working")
            expected_report = {"role": "working", "report": expected_report}
        boundary = _support.ScriptedProcessBoundary()
        runner = FixedCommandRunner(root, log, runner=boundary)
        result = runner.run(request)  # type: ignore[arg-type]
        assert result.exit_code == 0
        assert result.report == expected_report
        assert result.failure_line is None
        assert result.guidance_line is None
        entry = log.read()[-1]
        assert entry.command == label
        assert entry.result == "success"
        assert _TARGET_ID not in entry.command
        assert _DATASET_ID not in entry.command
        return

    if case == "promotion":
        request, function, label = _PROMOTION_CASE
        report = _ReadReport(report=_support.VALUE_SENTINEL)
        delegated: list[dict[str, object]] = []

        def promotion(
            source_dataset_id: str,
            *,
            confirm_restart: bool = False,
            on_progress: object = None,
            runner: object = None,
        ) -> _ReadReport:
            delegated.append(
                {
                    "source_dataset_id": source_dataset_id,
                    "confirm_restart": confirm_restart,
                    "on_progress": on_progress,
                    "runner": runner,
                }
            )
            return report

        monkeypatch.setattr(administrative_commands, function, promotion)
        boundary = _support.ScriptedProcessBoundary()
        runner = FixedCommandRunner(root, log, runner=boundary)

        def observe(_step: str) -> None:
            """Stand in for the console's step observer."""

        observed = observe
        result = runner.run(request, on_progress=observed)  # type: ignore[arg-type]
        assert result.exit_code == 0
        assert result.report == report.model_dump(mode="json")
        assert result.failure_line is None
        # The sole in-process action reaches its delegate with the validated input and the observer,
        # and it launches no subprocess.
        assert delegated == [
            {
                "source_dataset_id": _DATASET_ID,
                "confirm_restart": True,
                "on_progress": observed,
                "runner": boundary,
            }
        ]
        assert boundary.calls == []
        entry = log.read()[-1]
        assert entry.command == label
        assert entry.result == "success"
        assert _DATASET_ID not in entry.command
        return

    if case in _ADMITTED_SHAPES:
        request, tail, label = _ADMITTED_SHAPES[case]
        report = {"report": _support.VALUE_SENTINEL}
        if case == "feedback-attachment":
            report = {"content_base64": _ATTACHMENT_CARRIER}
        boundary = _support.ScriptedProcessBoundary((json.dumps(report).encode("utf-8"),))
        runner = FixedCommandRunner(root, log, runner=boundary)
        result = runner.run(request)  # type: ignore[arg-type]
        assert result.exit_code == 0
        assert result.report == report
        assert result.failure_line is None
        assert boundary.calls == [{"argv": (sys.executable, _script(root), *tail), "cwd": root}]
        entry = log.read()[-1]
        assert entry.command == label
        assert entry.result == "success"
        # The fixed label carries no identity a caller supplied.
        assert _TARGET_ID not in entry.command
        assert _DATASET_ID not in entry.command
        return

    if case == "checked-failure":
        failure = subprocess.CalledProcessError(
            returncode=1,
            cmd=[sys.executable, _script(root), "usage", "--hours", "24"],
            stderr=_support.OUTPUT_SENTINEL.encode("utf-8"),
        )
        boundary = _support.ScriptedProcessBoundary((failure,))
    elif case == "process-boundary-failure":
        boundary = _support.ScriptedProcessBoundary(
            (OSError(f"{_support.OUTPUT_SENTINEL} did not start"),)
        )
    elif case == "malformed-stdout":
        boundary = _support.ScriptedProcessBoundary(
            (f"{_support.OUTPUT_SENTINEL} is not one JSON object".encode(),)
        )
    else:
        boundary = _support.ScriptedProcessBoundary(
            (json.dumps({"report": _support.VALUE_SENTINEL}).encode("utf-8"),)
        )
    runner = FixedCommandRunner(root, log, runner=boundary)

    if case == "checked-failure":
        result = runner.run(UsageCommand(kind="usage", hours=24))
        assert result.exit_code == 1
        assert result.report is None
        assert result.failure_line == format_operator_error(failure)
        assert result.guidance_line == administrative_commands.operator_guidance("usage")
        assert _support.OUTPUT_SENTINEL not in result.model_dump_json()
        entry = log.read()[-1]
        assert entry.command == "usage"
        assert entry.result == "failure"
        assert entry.failure_line == format_operator_error(failure)
        # One entry never holds more than one safe failure line.
        with pytest.raises(ValidationError):
            CommandLogEntry(
                time=entry.time,
                command="server status",
                exit_code=1,
                duration_seconds=1.0,
                result="failure",
                failure_line="first line\nsecond line",
            )
    elif case in {"process-boundary-failure", "malformed-stdout"}:
        result = runner.run(UsageCommand(kind="usage", hours=24))
        expected_error = "OSError" if case == "process-boundary-failure" else "ValueError"
        assert result.exit_code == 1
        assert result.report is None
        assert result.failure_line is not None
        assert json.loads(result.failure_line) == {"error": expected_error}
        assert result.guidance_line == administrative_commands.operator_guidance("usage")
        assert _support.OUTPUT_SENTINEL not in result.model_dump_json()
        entry = log.read()[-1]
        assert entry.command == "usage"
        assert entry.result == "failure"
        assert entry.failure_line == result.failure_line
    else:
        hours = _support.ARGUMENT_SENTINEL if case == "usage-window" else 24
        result = runner.run(UsageCommand(kind="usage", hours=hours))
        assert result.exit_code == 0
        assert result.report == {"report": _support.VALUE_SENTINEL}
        entry = log.read()[-1]
        assert entry.command == "usage"
        assert entry.result == "success"

    expected_tail = (
        "usage",
        "--hours",
        str(_support.ARGUMENT_SENTINEL if case == "usage-window" else 24),
    )
    assert boundary.calls == [
        {"argv": (sys.executable, _script(root), *expected_tail), "cwd": root}
    ]
    assert len(boundary.calls) == 1


@pytest.mark.parametrize(
    ("stderr", "expected"),
    [
        pytest.param(
            f"{format_operator_error(FileNotFoundError(_support.OUTPUT_SENTINEL))}\n"
            "check the checkout directory\n",
            {"error": "FileNotFoundError"},
            id="producer-missing-command",
        ),
        pytest.param(
            f"{format_operator_error(ValueError(_support.VALUE_SENTINEL))}\ncheck config/*.toml\n",
            {"error": "ValueError"},
            id="producer-invalid-value",
        ),
        pytest.param(
            '{"error":"FileNotFoundError","returncode":127}\nfixed guidance\n',
            {"error": "FileNotFoundError", "returncode": 127},
            id="checked-child-code",
        ),
        pytest.param(
            json.dumps({"error": f"ValueError: {_support.OUTPUT_SENTINEL}"}) + "\n",
            {"error": "CalledProcessError", "returncode": 1},
            id="message-bearing-json",
        ),
        pytest.param(
            '{"error":"not a class"}\n',
            {"error": "CalledProcessError", "returncode": 1},
            id="nonidentifier-error",
        ),
        pytest.param(
            f'first line {_support.OUTPUT_SENTINEL}\n{{"error":"ValueError"}}\n',
            {"error": "CalledProcessError", "returncode": 1},
            id="valid-json-not-first-line",
        ),
        pytest.param(
            '{"error":"ValueError","returncode":true}\n',
            {"error": "CalledProcessError", "returncode": 1},
            id="boolean-returncode",
        ),
        pytest.param(
            None,
            {"error": "CalledProcessError", "returncode": 1},
            id="absent-stderr",
        ),
    ],
)
def test_admin_command_failure_exposes_only_safe_child_class(
    tmp_path: Path, stderr: str | None, expected: dict[str, object]
) -> None:
    """A checked child failure exposes its own class line, or the wrapper class when unusable."""
    root = tmp_path / "checkout"
    root.mkdir()
    failure = subprocess.CalledProcessError(
        returncode=1,
        cmd=[sys.executable, _script(root), "usage", "--hours", "24"],
        stderr=None if stderr is None else stderr.encode("utf-8"),
    )
    boundary = _support.ScriptedProcessBoundary((failure,))
    runner = FixedCommandRunner(root, CommandLog(root, limit=5), runner=boundary)

    result = runner.run(UsageCommand(kind="usage", hours=24))

    expected_line = json.dumps(expected, separators=(",", ":"))
    assert len(boundary.calls) == 1
    # The wrapper's exit status is the checked process's own, never the child's reported code.
    assert result.exit_code == 1
    assert result.report is None
    assert result.failure_line == expected_line
    assert result.guidance_line == administrative_commands.operator_guidance("usage")
    entry = CommandLog(root, limit=5).read()[-1]
    assert entry.exit_code == 1
    assert entry.result == "failure"
    assert entry.failure_line == expected_line
    # Neither the returned outcome nor the sole retained entry carries the child's text, and the
    # entry carries no guidance line beyond its one safe failure line.
    outcome = result.model_dump_json()
    log_payload = (root / _support.COMMAND_LOG_PATH).read_text(encoding="utf-8")
    assert _support.OUTPUT_SENTINEL not in outcome
    assert _support.OUTPUT_SENTINEL not in log_payload
    assert _support.VALUE_SENTINEL not in outcome
    assert _support.VALUE_SENTINEL not in log_payload
    assert result.guidance_line not in log_payload
    assert set(entry.model_dump()) == _ENTRY_FIELDS


@pytest.mark.parametrize(
    "producer",
    [
        "runner-success",
        "runner-failure",
        "runner-config-set",
        "runner-feedback",
        "login",
        "failed-login",
        "lock",
    ],
)
def test_admin_command_log_retains_only_bounded_safe_entries(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, producer: str
) -> None:
    """The sole log owner keeps the last entries of one file without retaining an input or a value."""
    limit = 2

    if producer.startswith("runner"):
        root = tmp_path / "checkout"
        root.mkdir()
        failure = subprocess.CalledProcessError(
            returncode=1,
            cmd=[sys.executable, _script(root), "usage", "--hours", "7"],
            stderr=_support.OUTPUT_SENTINEL.encode("utf-8"),
        )
        if producer == "runner-config-set":
            # One configuration value parameter and one exception input, neither of which may reach
            # a retained entry even though both reached the command's own argument list.
            value = json.dumps(_support.VALUE_SENTINEL)
            boundary = _support.ScriptedProcessBoundary(
                (json.dumps({"report": _support.VALUE_SENTINEL}).encode("utf-8"), failure)
            )
            runner = FixedCommandRunner(root, CommandLog(root, limit=limit), runner=boundary)
            for key in ("WEB_PORT", "POSTGRES_PORT"):
                runner.run(
                    ConfigSetCommand(kind="config-set", file=_CONFIG_FILE, key=key, value=value)
                )
            assert [call["argv"][2:] for call in boundary.calls] == [
                ("config", "set", "--", _CONFIG_FILE, "WEB_PORT", value),
                ("config", "set", "--", _CONFIG_FILE, "POSTGRES_PORT", value),
            ]
            expected_results = ["success", "failure"]
            expected_codes = [0, 1]
            expected_commands = ["config set", "config set"]
        elif producer == "runner-feedback":
            # A feedback listing and a feedback attachment read keep their IDs, search, filters and
            # attachment carrier out of the retained file.
            boundary = _support.ScriptedProcessBoundary(
                (
                    json.dumps({"report": _support.VALUE_SENTINEL}).encode("utf-8"),
                    json.dumps({"content_base64": _ATTACHMENT_CARRIER}).encode("utf-8"),
                    failure,
                )
            )
            runner = FixedCommandRunner(root, CommandLog(root, limit=limit), runner=boundary)
            runner.run(
                FeedbackListCommand(
                    kind="feedback-list", query=_FEEDBACK_QUERY, filters=_FEEDBACK_FILTERS
                )
            )
            runner.run(
                FeedbackAttachmentCommand(
                    kind="feedback-attachment",
                    feedback_id=UUID(_FEEDBACK_ID),
                    attachment_id=UUID(_ATTACHMENT_ID),
                )
            )
            runner.run(
                FeedbackDeleteCommand(kind="feedback-delete", feedback_id=UUID(_FEEDBACK_ID))
            )
            expected_results = ["success", "failure"]
            expected_codes = [0, 1]
            expected_commands = ["feedback attachment", "feedback delete"]
        else:
            outcomes: tuple[bytes | BaseException, ...] = (
                (
                    json.dumps({"report": _support.VALUE_SENTINEL}).encode("utf-8"),
                    json.dumps({"report": _support.VALUE_SENTINEL}).encode("utf-8"),
                    failure,
                )
                if producer == "runner-failure"
                else (json.dumps({"report": _support.VALUE_SENTINEL}).encode("utf-8"),)
            )
            runner = FixedCommandRunner(
                root,
                CommandLog(root, limit=limit),
                runner=_support.ScriptedProcessBoundary(outcomes),
            )
            for hours in (_support.ARGUMENT_SENTINEL, 24, 7):
                runner.run(UsageCommand(kind="usage", hours=hours))
            expected_results = (
                ["success", "failure"] if producer == "runner-failure" else ["success", "success"]
            )
            expected_codes = [0, 1] if producer == "runner-failure" else [0, 0]
            expected_commands = ["usage", "usage"]
        entries = CommandLog(root, limit=limit).read()
    else:
        root, _settings, _clock, application = _support.site(
            monkeypatch, tmp_path, ADMIN_WEB_COMMAND_LOG_LIMIT=limit
        )
        client = _support.site_client(application)
        if producer == "login":
            for _ in range(3):
                response = _support.login(client, csrf_token=_support.bootstrap(client))
                assert response.status_code == 200
            expected_results = ["login", "login"]
            expected_codes = [0, 0]
            expected_commands = ["login", "login"]
        else:
            csrf = _support.bootstrap(client)
            attempts = 2 if producer == "failed-login" else 3
            for index in range(attempts):
                response = _support.login(client, csrf_token=csrf, password="wrong-password")
                # The third consecutive failure creates the site lock instead of a login failure.
                assert response.status_code == (401 if index < 2 else 403)
            expected_results = (
                ["failed-login", "failed-login"]
                if producer == "failed-login"
                else ["failed-login", "lock"]
            )
            expected_codes = [1, 1] if producer == "failed-login" else [1, 403]
            expected_commands = (
                ["login", "login"] if producer == "failed-login" else ["login", "lock"]
            )
        entries = CommandLog(root, limit=limit).read()

    assert [entry.command for entry in entries] == expected_commands
    assert [entry.result for entry in entries] == expected_results
    assert [entry.exit_code for entry in entries] == expected_codes
    assert all(entry.duration_seconds >= 0 for entry in entries)
    assert all(entry.time.tzinfo is not None for entry in entries)
    if producer == "lock":
        assert entries[-1].duration_seconds == 0.0
        assert entries[-1].failure_line is None

    state_directory = root / _support.ADMIN_STATE_PATH
    assert sorted(entry.name for entry in state_directory.iterdir()) == _state_files(producer)
    payload = (root / _support.COMMAND_LOG_PATH).read_text(encoding="utf-8")
    lines = payload.splitlines()
    assert len(lines) == limit
    for line in lines:
        assert set(json.loads(line)) == _ENTRY_FIELDS
    assert _support.VALUE_SENTINEL not in payload
    assert _support.OUTPUT_SENTINEL not in payload
    assert str(_support.ARGUMENT_SENTINEL) not in payload
    assert _support.OPERATOR_PASSWORD not in payload
    assert "forged-token" not in payload
    if producer == "runner-feedback":
        assert _FEEDBACK_ID not in payload
        assert _ATTACHMENT_ID not in payload
        assert _FEEDBACK_QUERY not in payload
        assert "student" not in payload
        assert _ATTACHMENT_CARRIER not in payload


@pytest.mark.parametrize("outcome", ["success", "checked-failure"])
def test_automatic_reads_record_only_failures(tmp_path: Path, outcome: str) -> None:
    """An automatic read reaches the sole log only when its own outcome failed."""
    root = tmp_path / "checkout"
    root.mkdir()
    failure = subprocess.CalledProcessError(
        returncode=1,
        cmd=[sys.executable, _script(root), "usage", "--hours", "24"],
        stderr=_support.OUTPUT_SENTINEL.encode("utf-8"),
    )
    boundary = _support.ScriptedProcessBoundary(
        (
            failure
            if outcome == "checked-failure"
            else json.dumps({"report": _support.VALUE_SENTINEL}).encode("utf-8"),
        )
    )
    runner = FixedCommandRunner(root, CommandLog(root, limit=5), runner=boundary)

    result = runner.run(UsageCommand(kind="usage", hours=24), automatic=True)

    # The flag selects no argument, so an automatic read runs the same fixed command.
    assert boundary.calls == [
        {"argv": (sys.executable, _script(root), "usage", "--hours", "24"), "cwd": root}
    ]
    entries = CommandLog(root, limit=5).read()
    if outcome == "success":
        # A successful scheduled read leaves the log file absent and retains no entry.
        assert result.exit_code == 0
        assert result.failure_line is None
        assert result.guidance_line is None
        assert entries == ()
        assert not (root / _support.COMMAND_LOG_PATH).exists()
        return
    assert result.exit_code == 1
    assert result.report is None
    assert result.failure_line == format_operator_error(failure)
    assert result.guidance_line == administrative_commands.operator_guidance("usage")
    assert len(entries) == 1
    assert entries[0].command == "usage"
    assert entries[0].result == "failure"
    assert entries[0].exit_code == 1
    assert entries[0].failure_line == result.failure_line


def test_console_report_reads_working_before_selected_and_bootstrap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The console report reads resolve Working, then Selected, and report nothing in bootstrap."""
    root = tmp_path / "checkout"
    root.mkdir()
    present: set[str] = set()
    report = _ReadReport(report=_support.VALUE_SENTINEL)
    delegated: list[tuple[str, str]] = []

    monkeypatch.setattr(admin_runner, "load_administrative_dataset_settings", lambda: object())
    monkeypatch.setattr(admin_runner, "admin_state_root", lambda _settings: tmp_path / "state")
    monkeypatch.setattr(
        admin_runner,
        "read_dataset_role",
        lambda _root, role: object() if role in present else None,
    )

    def coverage(_kind: str, *, role: str) -> _ReadReport:
        delegated.append(("coverage", role))
        return report

    def summary(_kind: str, *, role: str) -> _ReadReport:
        delegated.append(("summary", role))
        return report

    monkeypatch.setattr(administrative_commands, "run_administrative_coverage", coverage)
    monkeypatch.setattr(administrative_commands, "run_administrative_summary", summary)
    runner = FixedCommandRunner(
        root, CommandLog(root, limit=5), runner=_support.ScriptedProcessBoundary()
    )
    scoped = report.model_dump(mode="json")

    present.update({"working", "selected"})
    working = runner.run(CoverageCommand(kind="coverage", report="embedding"))
    assert working.exit_code == 0
    assert working.report == {"role": "working", "report": scoped}
    assert working.guidance_line is None

    present.discard("working")
    selected = runner.run(SummaryCommand(kind="summary", report="inference"))
    assert selected.exit_code == 0
    assert selected.report == {"role": "selected", "report": scoped}

    present.discard("selected")
    bootstrap = runner.run(CoverageCommand(kind="coverage", report="teaching-text"))
    assert bootstrap.exit_code == 0
    assert bootstrap.report == {"role": None, "report": None}
    # The bootstrap state runs no report command at all.
    assert delegated == [("coverage", "working"), ("summary", "selected")]


def _state_files(producer: str) -> list[str]:
    """Return the administration state files one producer's run must leave behind."""
    if producer.startswith("runner"):
        return ["command-log"]
    files = ["command-log", "failed-logins", "password"]
    if producer == "lock":
        files.append("lock")
    return sorted(files)
