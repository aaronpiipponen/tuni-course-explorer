"""Proof that the one command-log read command reads the sole owner's file and nothing else.

Each invocation points the administration command-log owner at one temporary checkout, writes no
real state, drives the real ``logs commands`` machine command, and asserts the retained entries the
report carries. No case opens a site's own administration state.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from course_explorer_admin import cli
from course_explorer_admin_web import command_log as command_log_module
from course_explorer_admin_web.command_log import CommandLog, CommandLogEntry
from tests.admin_web import _support

_LIMIT = 3
_ENTRY_FIELDS = {
    "time",
    "command",
    "exit_code",
    "duration_seconds",
    "result",
    "failure_line",
}


def _entry(index: int) -> CommandLogEntry:
    """Return one retained entry of the log owner's own shape."""
    return CommandLogEntry(
        time=datetime(2026, 10, 18, 9, index, tzinfo=UTC),
        command="logs commands",
        exit_code=0,
        duration_seconds=float(index),
        result="success",
    )


@pytest.mark.parametrize("case", ["present", "absent"])
def test_command_log_command_reads_the_sole_owner(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    case: str,
) -> None:
    """The command prints the newest configured entries oldest first and rewrites no file."""
    root = tmp_path / "checkout"
    root.mkdir()
    monkeypatch.setattr(command_log_module, "repository_root", lambda: root)
    monkeypatch.setattr(
        command_log_module,
        "load_admin_web_settings",
        lambda: _support.admin_web_settings(ADMIN_WEB_COMMAND_LOG_LIMIT=_LIMIT),
    )
    log_path = root / _support.COMMAND_LOG_PATH

    if case == "present":
        # The writer keeps five entries while the configured read limit is three.
        log = CommandLog(root, limit=5)
        for index in range(5):
            log.append(_entry(index))
        before = log_path.read_bytes()
        expected = [
            {"command": "logs commands", "exit_code": 0, "duration_seconds": float(index)}
            for index in range(2, 5)
        ]
    else:
        assert not log_path.exists()
        before = None
        expected = []

    assert cli.main(["logs", "commands"]) == 0
    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert report["schema_version"] == 1
    assert [
        {
            "command": entry["command"],
            "exit_code": entry["exit_code"],
            "duration_seconds": entry["duration_seconds"],
        }
        for entry in report["entries"]
    ] == expected
    # Every rendered entry carries the owner's own fields, in the owner's own order.
    assert [entry["time"] for entry in report["entries"]] == sorted(
        entry["time"] for entry in report["entries"]
    )
    for entry in report["entries"]:
        assert set(entry) == _ENTRY_FIELDS
    assert captured.err == ""

    if before is None:
        # No log file exists, and the read returns an empty report.
        assert not log_path.exists()
    else:
        # The read appends and prunes nothing.
        assert log_path.read_bytes() == before
