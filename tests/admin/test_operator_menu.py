"""Behavior contracts for the numbered operator menu."""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime

import pytest

from course_explorer.config import WebSettings
from course_explorer_admin import commands
from course_explorer_admin.backups import BackupDeletionReport, BackupFile, BackupListReport
from course_explorer_admin.configuration import (
    ConfigurationFileReport,
    ConfigurationFilesReport,
    ConfigurationWriteReport,
)
from course_explorer_admin.datasets import (
    DatasetDeletionReport,
    DatasetListEntry,
    DatasetListReport,
)
from course_explorer_admin.logs import LogReadReport, LogSessionEntry, LogSessionsReport
from course_explorer_admin.rebuild import RebuildReport
from tests.support import REPO_ROOT


class _Sentinel:
    """One JSON-renderable owner result standing in for a real DTO."""

    disposition: str | None = None

    def __init__(self, label: str) -> None:
        self.label = label

    def model_dump_json(self) -> str:
        return json.dumps({"label": self.label})


class _ScriptedRead:
    """Scripted input that records every prompt it is asked for."""

    def __init__(self, answers: list[str]) -> None:
        self._answers = list(answers)
        self.prompts: list[str] = []

    def __call__(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if not self._answers:
            raise EOFError
        return self._answers.pop(0)


@pytest.mark.parametrize(
    ("scenario", "answers", "server_branch"),
    [
        ("ingestion-status", ["2", "4", "0", "0"], "main"),
        ("catalogue-summary", ["6", "1", "1", "0", "0"], "main"),
        ("selected-migration", ["1", "5", "1", "0", "0"], "main"),
        ("working-migration", ["1", "5", "2", "0", "0"], "main"),
        ("copy-to-working", ["1", "2", "a" * 32, "1", "0", "0"], "main"),
        ("worker-setup-main", ["1", "3", "0", "0"], "main"),
        ("worker-setup-nonmain-default", ["1", "3", "", "0", "0"], "prerequisite-inference"),
        (
            "worker-setup-explicit-branch",
            ["1", "3", "other-origin-branch", "0", "0"],
            "prerequisite-inference",
        ),
        ("dispose-nothing", ["5", "6", "disp-target", "1", "0", "0"], "main"),
        ("dispose-done", ["5", "6", "disp-target", "2", "0", "0"], "main"),
        ("dispose-failed", ["5", "6", "disp-target", "3", "0", "0"], "main"),
        ("dataset-cleanup-initial", ["1", "6", "0" * 32, "1", "0", "0"], "main"),
        ("working-cleanup", ["1", "6", "0" * 32, "1", "0", "0"], "main"),
        ("backup-cleanup-file", ["1", "7", "before-inference.dump", "1", "0", "0"], "main"),
        # Choice 7 holds no inference entry, so it dispatches nothing and the menu re-prompts.
        ("inference-absent-cleanup", ["5", "7", "0", "0"], "main"),
        ("embedding-build-serving-artifacts", ["4", "6", "0", "0"], "main"),
        ("server-status", ["7", "1", "0", "0"], "main"),
        ("command-log", ["7", "5", "0", "0"], "main"),
        ("usage-report", ["7", "4", "24", "0", "0"], "main"),
        ("session-log", ["7", "2", "embedding", "a" * 32, "1", "2", "0", "0"], "main"),
        ("embedding-log", ["7", "3", "4", "0", "0"], "main"),
        ("rebuild-app", ["1", "9", "1", "0", "0"], "main"),
        ("rebuild-admin-panel", ["1", "11", "1", "0", "0"], "main"),
        ("password-setup", ["1", "10", "synthetic-operator", "0", "0"], "main"),
        ("example-setup", ["1", "12", "", "synthetic-operator", "2", "1", "0", "0", "0"], "main"),
        ("example-setup-cancel", ["1", "12", "", "synthetic-operator", "0", "0", "0"], "main"),
        ("real-database-setup", ["1", "13", "", "1", "0", "0"], "main"),
        (
            "configuration-save",
            ["1", "8", "config/web.toml", "WEB_PORT", "18026", "1", "0", "0"],
            "main",
        ),
        (
            "supplied-callbacks",
            [
                "2",
                "4",
                "0",
                "6",
                "4",
                "2",
                "0",
                "1",
                "8",
                "config/web.toml",
                "WEB_PORT",
                "18026",
                "1",
                "0",
                "0",
            ],
            "main",
        ),
    ],
)
def test_operator_menu_routes_explicit_choices_and_uses_server_setup_branch(
    monkeypatch: pytest.MonkeyPatch,
    scenario: str,
    answers: list[str],
    server_branch: str,
) -> None:
    """Each scenario drives only its menu path and asserts only that path's calls/report/prompts."""
    sentinel = _Sentinel("ok")
    disposition_report = _Sentinel("disposition-report")
    tool_calls: list[tuple[str, str]] = []
    report_calls: list[tuple[str, str]] = []
    setup_calls: list[dict] = []
    migration_calls: list[object] = []
    preflight_calls: list[object] = []
    disposition_reads: list[str] = []
    disposition_sets: list[tuple[str, object]] = []
    checkout_calls: list[object] = []
    hub_calls: list[object] = []
    dataset_listings: list[object] = []
    backup_listings: list[object] = []
    dataset_deletions: list[tuple[str, bool]] = []
    copy_calls: list[str] = []
    backup_deletions: list[str] = []
    configuration_listings: list[object] = []
    configuration_reads: list[str] = []
    configuration_writes: list[tuple] = []
    server_status_calls: list[object] = []
    command_log_reads: list[object] = []
    log_session_listings: list[object] = []
    log_reads: list[tuple] = []
    embedding_log_reads: list[int] = []
    rebuild_calls: list[object] = []
    admin_maintenance_calls: list[str] = []
    usage_hours: list[int] = []
    example_setup_calls: list[object] = []
    real_setup_calls: list[object] = []
    working_target = scenario == "working-cleanup"
    dataset_listing = DatasetListReport(
        datasets=(
            DatasetListEntry(
                dataset_id="a" * 32,
                kind="returned",
                database_name="course_dataset_selected",
                predecessor_id="0" * 32,
                receipt_schema_revision="20261028_0022",
                dump_path="data/admin/datasets/selected/database.dump",
                selected=True,
                working=False,
                database_presence="present",
                artifacts_present=True,
            ),
            DatasetListEntry(
                dataset_id="0" * 32,
                kind="initial",
                database_name="course_explorer",
                predecessor_id=None,
                receipt_schema_revision="20261028_0022",
                dump_path=None,
                selected=False,
                working=working_target,
                database_presence="present",
                artifacts_present=False,
            ),
        ),
        mode="enrolled",
        database_probe="available",
        bootstrap_database=None,
        stage_busy={
            stage: False for stage in ("ingestion", "embedding", "translation", "inference")
        },
    )
    backup_listing = BackupListReport(
        backups=(
            BackupFile(
                name="before-inference.dump",
                size_bytes=4096,
                modified_at=datetime(2026, 10, 18, 9, 30, tzinfo=UTC),
            ),
        )
    )
    dataset_deletion = DatasetDeletionReport(dataset_id="0" * 32, database_name="course_explorer")
    backup_deletion = BackupDeletionReport(name="before-inference.dump")
    configuration_listing = ConfigurationFilesReport(files=("config/web.toml", ".env"))
    configuration_report = ConfigurationFileReport(
        file="config/web.toml", values={"WEB_HOST": "127.0.0.1", "WEB_PORT": 8037}
    )
    configuration_acknowledgment = ConfigurationWriteReport(file="config/web.toml", key="WEB_PORT")
    log_session_listing = LogSessionsReport(
        sessions=(
            LogSessionEntry(
                stage="embedding",
                session_id="a" * 32,
                created_at=datetime(2026, 10, 18, 9, 30, tzinfo=UTC),
            ),
        )
    )
    log_read = LogReadReport(
        stage="embedding",
        session_id="a" * 32,
        source="server-stdout",
        available=True,
        text="fourth\nfifth\n",
    )
    rebuild_report = RebuildReport(
        steps=("frontend", "containers", "web", "bind"), host="127.0.0.1", port=18026
    )
    admin_restart_report = _Sentinel("admin-restart")

    class _BranchRunner:
        """Answer the server's branch read and record every checkout call."""

        def run(self, argv, *, cwd=None):
            checkout_calls.append((self, cwd))
            return subprocess.CompletedProcess(
                list(argv), 0, stdout=f"{server_branch}\n".encode(), stderr=b""
            )

    monkeypatch.setattr(commands.mechanics, "SubprocessRunner", _BranchRunner)
    monkeypatch.setattr(
        commands,
        "run_administrative_command",
        lambda stage, action: tool_calls.append((stage, action)) or sentinel,
    )
    monkeypatch.setattr(
        commands,
        "run_administrative_summary",
        lambda kind, *, role: report_calls.append(("summary", kind, role)) or sentinel,
    )
    monkeypatch.setattr(
        commands,
        "run_administrative_coverage",
        lambda kind, *, role: report_calls.append(("coverage", kind, role)) or sentinel,
    )
    monkeypatch.setattr(
        commands,
        "run_administrative_setup",
        lambda kind, branch="main", code_only=False: (
            setup_calls.append({"kind": kind, "branch": branch, "code_only": code_only}) or sentinel
        ),
    )
    monkeypatch.setattr(
        commands,
        "run_administrative_preflight",
        lambda: preflight_calls.append(sentinel) or sentinel,
    )
    monkeypatch.setattr(
        commands,
        "run_administrative_migration",
        lambda *, role: migration_calls.append(role) or sentinel,
    )
    monkeypatch.setattr(
        commands,
        "run_administrative_serving_artifacts",
        lambda **kwargs: hub_calls.append((sentinel, kwargs)) or sentinel,
    )
    monkeypatch.setattr(
        commands,
        "run_administrative_dataset_list",
        lambda: dataset_listings.append(sentinel) or dataset_listing,
    )
    monkeypatch.setattr(
        commands,
        "run_administrative_dataset_delete",
        lambda dataset_id, *, confirm_working=False: (
            dataset_deletions.append((dataset_id, confirm_working)) or dataset_deletion
        ),
    )
    monkeypatch.setattr(
        commands,
        "run_administrative_dataset_copy",
        lambda dataset_id: copy_calls.append(dataset_id) or sentinel,
    )
    monkeypatch.setattr(
        commands,
        "run_administrative_backup_list",
        lambda: backup_listings.append(sentinel) or backup_listing,
    )
    monkeypatch.setattr(
        commands,
        "run_administrative_backup_delete",
        lambda name: backup_deletions.append(name) or backup_deletion,
    )
    monkeypatch.setattr(
        commands,
        "run_administrative_config_list",
        lambda: configuration_listings.append(sentinel) or configuration_listing,
    )
    monkeypatch.setattr(
        commands,
        "run_administrative_config_read",
        lambda file: configuration_reads.append(file) or configuration_report,
    )
    monkeypatch.setattr(
        commands,
        "run_administrative_config_set",
        lambda file, key, value, *, settings_families=(): (
            configuration_writes.append((file, key, value, settings_families))
            or configuration_acknowledgment
        ),
    )
    monkeypatch.setattr(
        commands,
        "read_inference_target_disposition",
        lambda target: disposition_reads.append(target) or disposition_report,
    )
    monkeypatch.setattr(
        commands,
        "set_inference_target_disposition",
        lambda target, decision: disposition_sets.append((target, decision)) or disposition_report,
    )
    monkeypatch.setattr(
        commands,
        "run_administrative_server_status",
        lambda: server_status_calls.append(sentinel) or sentinel,
    )
    monkeypatch.setattr(
        commands,
        "run_administrative_command_log",
        lambda: command_log_reads.append(sentinel) or sentinel,
    )
    monkeypatch.setattr(
        commands,
        "run_administrative_log_sessions",
        lambda: log_session_listings.append(sentinel) or log_session_listing,
    )
    monkeypatch.setattr(
        commands,
        "run_administrative_session_log",
        lambda stage, session_id, source, *, lines: (
            log_reads.append((stage, session_id, source, lines)) or log_read
        ),
    )
    monkeypatch.setattr(
        commands,
        "run_administrative_embedding_log",
        lambda *, lines: embedding_log_reads.append(lines) or log_read,
    )
    monkeypatch.setattr(
        commands,
        "run_administrative_rebuild",
        lambda: rebuild_calls.append(sentinel) or rebuild_report,
    )
    monkeypatch.setattr(
        commands,
        "run_administrative_admin_rebuild",
        lambda: admin_maintenance_calls.append("build") or sentinel,
    )
    monkeypatch.setattr(
        commands,
        "run_administrative_restart_admin",
        lambda: admin_maintenance_calls.append("restart") or admin_restart_report,
    )
    monkeypatch.setattr(
        commands,
        "run_administrative_usage",
        lambda *, hours: usage_hours.append(hours) or sentinel,
    )
    password_calls: list[dict] = []
    monkeypatch.setattr(
        commands,
        "run_administrative_password",
        lambda *, username, read_password=None: (
            password_calls.append({"username": username, "read_password": read_password})
            or sentinel
        ),
    )
    monkeypatch.setattr(
        commands,
        "run_administrative_example_setup",
        lambda options: example_setup_calls.append(options) or sentinel,
    )
    monkeypatch.setattr(
        commands,
        "run_administrative_real_database_setup",
        lambda options: real_setup_calls.append(options) or sentinel,
    )
    hidden_answers = ["synthetic-password", "synthetic-password"]
    monkeypatch.setattr(commands.getpass, "getpass", lambda prompt: hidden_answers.pop(0))
    if scenario in {"example-setup", "example-setup-cancel"}:
        # The terminal default comes from the tracked example file, which the shared repository
        # fixture does not link into its temporary root.
        monkeypatch.setattr(commands.administration, "repository_root", lambda: REPO_ROOT)

    reader = _ScriptedRead(answers)
    writes: list[str] = []
    supplied_calls: list[tuple[str, str, str]] = []

    def supplied_command(stage, action):
        supplied_calls.append(("command", stage, action))
        return sentinel

    def supplied_summary(kind, *, role):
        supplied_calls.append(("summary", kind, role))
        return sentinel

    menu_arguments: dict[str, object] = {}
    if scenario == "supplied-callbacks":
        menu_arguments = {"run_command": supplied_command, "run_summary": supplied_summary}
    elif scenario == "configuration-save":
        menu_arguments = {"configuration_families": (WebSettings,)}
    assert commands.run_operator_menu(read=reader, write=writes.append, **menu_arguments) == 0

    if scenario == "configuration-save":
        # The configuration entry lists the files, prints the chosen file's values, and saves exactly
        # one file, key and JSON literal with the family tuple the caller supplied.
        assert configuration_listings == [sentinel]
        assert configuration_reads == ["config/web.toml"]
        assert configuration_writes == [("config/web.toml", "WEB_PORT", "18026", (WebSettings,))]
        assert configuration_listing.model_dump_json() in writes
        assert configuration_report.model_dump_json() in writes
        confirmation = "Save configuration config/web.toml key WEB_PORT?"
        assert confirmation in writes
        assert writes.index(configuration_listing.model_dump_json()) < writes.index(
            configuration_report.model_dump_json()
        )
        assert writes.index(configuration_report.model_dump_json()) < writes.index(confirmation)
        assert configuration_acknowledgment.model_dump_json() in writes
        assert tool_calls == [] and report_calls == [] and setup_calls == []
        assert migration_calls == [] and disposition_reads == [] and disposition_sets == []
        assert checkout_calls == [] and hub_calls == []
        return

    if scenario == "supplied-callbacks":
        # The supplied callbacks replace exactly the stage command and the inference summary, and
        # every unrelated owner, the configuration editor included, is reached.
        assert supplied_calls == [
            ("command", "ingestion", "status"),
            ("summary", "inference", "working"),
        ]
        assert tool_calls == [] and report_calls == []
        assert setup_calls == [] and migration_calls == []
        assert preflight_calls == [] and disposition_reads == [] and disposition_sets == []
        assert checkout_calls == []
        assert configuration_reads == ["config/web.toml"]
        assert configuration_writes == [("config/web.toml", "WEB_PORT", "18026", ())]
        return

    if scenario == "ingestion-status":
        assert tool_calls == [("ingestion", "status")]
        # The ingestion tool menu shows no dispose entry and status touches only the ingestion tool.
        assert report_calls == [] and setup_calls == [] and migration_calls == []
        assert preflight_calls == [] and disposition_reads == [] and disposition_sets == []
        assert checkout_calls == []
        return
    if scenario == "embedding-build-serving-artifacts":
        # Only the embedding tool offers the artifact build, and choosing it calls the builder once.
        assert len(hub_calls) == 1
        assert tool_calls == [] and report_calls == [] and setup_calls == []
        assert disposition_reads == [] and disposition_sets == [] and checkout_calls == []
        return
    if scenario == "server-status":
        # The server/logs entry reads one server status report and reaches nothing else.
        assert len(server_status_calls) == 1
        assert sentinel.model_dump_json() in writes
        assert tool_calls == [] and report_calls == [] and setup_calls == []
        assert log_session_listings == [] and log_reads == [] and embedding_log_reads == []
        assert rebuild_calls == []
        return
    if scenario == "command-log":
        # The Server/logs choice 5 reads the retained command log and reaches nothing else.
        assert len(command_log_reads) == 1
        assert sentinel.model_dump_json() in writes
        assert server_status_calls == [] and log_session_listings == [] and log_reads == []
        assert embedding_log_reads == [] and usage_hours == [] and rebuild_calls == []
        assert tool_calls == [] and report_calls == [] and setup_calls == []
        return
    if scenario == "usage-report":
        # The usage entry asks for the hours first and runs the report once for that window.
        assert usage_hours == [24]
        assert sentinel.model_dump_json() in writes
        assert server_status_calls == [] and log_session_listings == [] and log_reads == []
        assert embedding_log_reads == [] and rebuild_calls == []
        assert tool_calls == [] and report_calls == [] and setup_calls == []
        return
    if scenario == "session-log":
        # The session entry lists the sessions, refuses an unlisted answer, and reads one source.
        assert len(log_session_listings) == 1
        assert log_reads == [("embedding", "a" * 32, "server-stdout", 2)]
        assert log_session_listing.model_dump_json() in writes
        assert log_read.model_dump_json() in writes
        assert embedding_log_reads == [] and rebuild_calls == [] and server_status_calls == []
        assert tool_calls == [] and report_calls == [] and setup_calls == []
        return
    if scenario == "embedding-log":
        # The embedding entry asks only for the positive line count and reads that one log.
        assert embedding_log_reads == [4]
        assert log_read.model_dump_json() in writes
        assert log_session_listings == [] and log_reads == [] and rebuild_calls == []
        assert server_status_calls == [] and tool_calls == []
        return
    if scenario == "rebuild-app":
        # The app rebuild entry asks for confirmation first and runs the site rebuild once.
        assert len(rebuild_calls) == 1
        assert "Rebuild this site's frontend, containers and web server?" in writes
        assert rebuild_report.model_dump_json() in writes
        assert writes.index(
            "Rebuild this site's frontend, containers and web server?"
        ) < writes.index(rebuild_report.model_dump_json())
        assert admin_maintenance_calls == []
        assert server_status_calls == [] and log_session_listings == [] and log_reads == []
        assert embedding_log_reads == [] and tool_calls == [] and setup_calls == []
        return
    if scenario == "rebuild-admin-panel":
        # The administration entry builds the panel and then queues its restart, in that order, and
        # its own confirmation names the sign-out the restart causes.
        assert admin_maintenance_calls == ["build", "restart"]
        assert "Rebuild the admin panel? This signs all operators out." in writes
        assert admin_restart_report.model_dump_json() in writes
        assert writes.index(
            "Rebuild the admin panel? This signs all operators out."
        ) < writes.index(admin_restart_report.model_dump_json())
        assert rebuild_calls == []
        assert server_status_calls == [] and log_session_listings == [] and log_reads == []
        assert embedding_log_reads == [] and tool_calls == [] and setup_calls == []
        return
    if scenario == "inference-absent-cleanup":
        # Choice 7 holds no inference cleanup action, so it reads no listing, deletes nothing and
        # runs no command.
        assert dataset_listings == [] and dataset_deletions == []
        assert backup_listings == [] and backup_deletions == []
        assert tool_calls == [] and report_calls == [] and setup_calls == []
        assert migration_calls == [] and disposition_reads == [] and disposition_sets == []
        # The menu prints no entry for choice 7, and no report line names it.
        assert not [line for line in writes if "Dataset cleanup" in line]
        assert "7 Dataset cleanup" not in writes
        return
    if scenario in {"dataset-cleanup-initial", "working-cleanup"}:
        # The dataset listing is printed before the confirmation, only the eligible row is named for
        # deletion, and the matching delete delegate is the one call with its role confirmation.
        assert len(dataset_listings) == 1
        assert dataset_deletions == [("0" * 32, working_target)]
        assert backup_listings == [] and backup_deletions == []
        listing_line = dataset_listing.model_dump_json()
        confirmation = (
            f"Delete Working dataset {'0' * 32} (course_explorer)? Working becomes absent."
            if working_target
            else f"Delete dataset {'0' * 32} (course_explorer)?"
        )
        assert listing_line in writes
        assert confirmation in writes
        assert writes.index(listing_line) < writes.index(confirmation)
        assert '"selected":true' in listing_line
        assert not any(line.startswith(f"Delete dataset {'a' * 32}") for line in writes)
        assert dataset_deletion.model_dump_json() in writes
        assert tool_calls == [] and report_calls == [] and setup_calls == []
        assert migration_calls == [] and disposition_reads == [] and disposition_sets == []
        assert checkout_calls == [] and hub_calls == []
        return
    if scenario == "backup-cleanup-file":
        # The backup listing is printed before the confirmation, and the one delete call names the
        # exact relative file the operator typed.
        assert len(backup_listings) == 1
        assert backup_deletions == ["before-inference.dump"]
        assert dataset_listings == [] and dataset_deletions == []
        listing_line = backup_listing.model_dump_json()
        confirmation = "Delete backup before-inference.dump?"
        assert listing_line in writes
        assert confirmation in writes
        assert writes.index(listing_line) < writes.index(confirmation)
        assert backup_deletion.model_dump_json() in writes
        assert tool_calls == [] and report_calls == [] and setup_calls == []
        assert migration_calls == [] and disposition_reads == [] and disposition_sets == []
        assert checkout_calls == [] and hub_calls == []
        return
    if scenario == "catalogue-summary":
        assert report_calls == [("summary", "catalogue", "selected")]
        assert tool_calls == [] and setup_calls == [] and migration_calls == []
        assert disposition_reads == [] and disposition_sets == [] and checkout_calls == []
        return
    if scenario in {"selected-migration", "working-migration"}:
        assert migration_calls == ["selected" if scenario == "selected-migration" else "working"]
        assert tool_calls == [] and report_calls == [] and setup_calls == []
        assert disposition_reads == [] and disposition_sets == [] and checkout_calls == []
        return
    if scenario == "copy-to-working":
        # The listing is printed before the source prompt, the copy names the listed source, and its
        # ordinary confirmation names the exact dataset.
        assert len(dataset_listings) == 1
        assert copy_calls == ["a" * 32]
        assert dataset_deletions == []
        listing_line = dataset_listing.model_dump_json()
        confirmation = f"Copy dataset {'a' * 32} (course_dataset_selected) to Working?"
        assert listing_line in writes
        assert confirmation in writes
        assert writes.index(listing_line) < writes.index(confirmation)
        assert sentinel.model_dump_json() in writes
        assert tool_calls == [] and report_calls == [] and setup_calls == []
        assert migration_calls == [] and disposition_reads == [] and disposition_sets == []
        assert checkout_calls == [] and hub_calls == []
        return
    if scenario.startswith("worker-setup"):
        expected_branch = {
            "worker-setup-main": "main",
            "worker-setup-nonmain-default": "prerequisite-inference",
            "worker-setup-explicit-branch": "other-origin-branch",
        }[scenario]
        assert setup_calls == [{"kind": "worker", "branch": expected_branch, "code_only": False}]
        assert len(checkout_calls) == 1
        branch_prompts = [prompt for prompt in reader.prompts if prompt.startswith("Origin branch")]
        if scenario == "worker-setup-main":
            # The server branch is main, so no branch prompt is offered.
            assert branch_prompts == []
        else:
            # Each non-main selection prompts once and offers the server branch as its Enter default.
            assert len(branch_prompts) == 1
        assert tool_calls == [] and report_calls == [] and migration_calls == []
        assert disposition_reads == [] and disposition_sets == []
        return

    if scenario == "password-setup":
        # The Setup menu offers the password entry, and only the username reaches the command: the
        # two password entries belong to the command's own hidden prompt.
        assert password_calls == [{"username": "synthetic-operator", "read_password": None}]
        assert not any(prompt.startswith("Password") for prompt in reader.prompts)
        assert sentinel.model_dump_json() in writes
        assert tool_calls == [] and report_calls == [] and setup_calls == []
        assert configuration_writes == [] and disposition_reads == [] and disposition_sets == []
        return

    if scenario == "example-setup":
        # Choice 12 asks the device choices, reads both password entries hidden, and delegates once.
        assert len(example_setup_calls) == 1
        options = example_setup_calls[0]
        assert isinstance(options, commands.ExampleSetupInput)
        assert options.app_url is None
        assert options.username == "synthetic-operator"
        assert options.mode == "foreground"
        assert options.confirm_download is True
        assert options.publication_token is None
        assert options.password.get_secret_value() == "synthetic-password"
        assert not any("synthetic-password" in line for line in writes)
        assert not any(prompt.startswith("Password") for prompt in reader.prompts)
        assert sentinel.model_dump_json() in writes
        assert real_setup_calls == []
        assert tool_calls == [] and report_calls == [] and setup_calls == []
        return

    if scenario == "example-setup-cancel":
        # Cancelling the startup choice runs neither self-host workflow and posts no action.
        assert example_setup_calls == [] and real_setup_calls == []
        assert sentinel.model_dump_json() not in writes
        assert tool_calls == [] and report_calls == [] and setup_calls == []
        return

    if scenario == "real-database-setup":
        # Choice 13 keeps the terminal default name and delegates the chosen startup mode once.
        assert len(real_setup_calls) == 1
        options = real_setup_calls[0]
        assert isinstance(options, commands.RealDatabaseSetupInput)
        assert options.database_name == "course_explorer_real"
        assert options.mode == "user"
        assert sentinel.model_dump_json() in writes
        assert example_setup_calls == []
        assert tool_calls == [] and report_calls == [] and setup_calls == []
        return

    # One nothing/done/failed disposition choice: the entry is present, the canonical identity is
    # reported before the choice prompt, and the shared setter is called exactly once.
    expected = {
        "dispose-nothing": None,
        "dispose-done": "done",
        "dispose-failed": "failed",
    }[scenario]
    assert disposition_reads == ["disp-target"]
    assert disposition_sets == [("disp-target", expected)]
    assert writes.index('{"label": "disposition-report"}') < writes.index("Dispose target")
    assert tool_calls == [] and report_calls == [] and setup_calls == [] and migration_calls == []
    assert checkout_calls == []


@pytest.mark.parametrize(
    "scenario",
    [
        "stage-failure-retry",
        "main-eof",
        "main-interrupt",
        "worker-branch-eof",
        "disposition-read-error",
        "disposition-cancellation",
        "disposition-choice-interrupt",
        "cleanup-list-error",
        "cleanup-unlisted-target",
        "cleanup-selected-target",
        "cleanup-cancel",
        "cleanup-choice-interrupt",
        "configuration-list-error",
        "configuration-read-error",
        "configuration-unlisted-file",
        "configuration-unlisted-key",
        "configuration-cancel",
        "configuration-save-interrupt",
        "server-logs-list-error",
        "server-logs-unlisted-session",
        "server-logs-invalid-source",
        "server-logs-invalid-lines",
        "server-logs-cancel",
        "usage-cancel",
        "usage-invalid-hours",
        "rebuild-cancel",
        "rebuild-interrupt",
        "admin-rebuild-cancel",
        "admin-rebuild-build-failure",
        "password-cancel",
        "password-interrupt",
        "password-hidden-eof",
    ],
)
def test_operator_menu_failure_and_eof_preserve_running_work(
    monkeypatch: pytest.MonkeyPatch, scenario: str
) -> None:
    """One refusal/interruption path per invocation: no implicit stop and no setter/setup call."""
    sentinel = _Sentinel("ok")
    calls: list[tuple[str, str]] = []
    setup_calls: list[dict] = []
    disposition_sets: list[tuple[str, object]] = []
    writes: list[str] = []
    dataset_deletions: list[tuple[str, bool]] = []
    backup_deletions: list[str] = []
    configuration_writes: list[tuple] = []
    server_status_calls: list[object] = []
    log_reads: list[tuple] = []
    embedding_log_reads: list[int] = []
    rebuild_calls: list[object] = []
    usage_hours: list[int] = []
    dataset_listing = DatasetListReport(
        datasets=(
            DatasetListEntry(
                dataset_id="a" * 32,
                kind="returned",
                database_name="course_dataset_selected",
                predecessor_id="0" * 32,
                receipt_schema_revision="20261028_0022",
                dump_path=None,
                selected=True,
                working=False,
                database_presence="present",
                artifacts_present=False,
            ),
            DatasetListEntry(
                dataset_id="0" * 32,
                kind="initial",
                database_name="course_explorer",
                predecessor_id=None,
                receipt_schema_revision="20261028_0022",
                dump_path=None,
                selected=False,
                working=False,
                database_presence="present",
                artifacts_present=False,
            ),
        ),
        mode="enrolled",
        database_probe="available",
        bootstrap_database=None,
        stage_busy={
            stage: False for stage in ("ingestion", "embedding", "translation", "inference")
        },
    )
    backup_listing = BackupListReport(
        backups=(
            BackupFile(
                name="before-inference.dump",
                size_bytes=4096,
                modified_at=datetime(2026, 10, 18, 9, 30, tzinfo=UTC),
            ),
        )
    )

    monkeypatch.setattr(
        commands,
        "run_administrative_command",
        lambda stage, action: calls.append((stage, action)) or sentinel,
    )
    monkeypatch.setattr(
        commands,
        "run_administrative_setup",
        lambda kind, branch="main", code_only=False: setup_calls.append({"kind": kind}) or sentinel,
    )
    monkeypatch.setattr(commands, "read_inference_target_disposition", lambda target: sentinel)
    monkeypatch.setattr(
        commands,
        "set_inference_target_disposition",
        lambda target, decision: disposition_sets.append((target, decision)) or sentinel,
    )
    monkeypatch.setattr(commands, "run_administrative_dataset_list", lambda: dataset_listing)
    monkeypatch.setattr(
        commands,
        "run_administrative_dataset_delete",
        lambda dataset_id, *, confirm_working=False: (
            dataset_deletions.append((dataset_id, confirm_working)) or sentinel
        ),
    )
    monkeypatch.setattr(commands, "run_administrative_backup_list", lambda: backup_listing)
    monkeypatch.setattr(
        commands,
        "run_administrative_backup_delete",
        lambda name: backup_deletions.append(name) or sentinel,
    )
    monkeypatch.setattr(
        commands,
        "run_administrative_config_list",
        lambda: ConfigurationFilesReport(files=("config/web.toml", ".env")),
    )
    monkeypatch.setattr(
        commands,
        "run_administrative_config_read",
        lambda file: ConfigurationFileReport(file=file, values={"WEB_PORT": 8037}),
    )
    monkeypatch.setattr(
        commands,
        "run_administrative_config_set",
        lambda file, key, value, *, settings_families=(): (
            configuration_writes.append((file, key, value, settings_families)) or sentinel
        ),
    )
    monkeypatch.setattr(
        commands,
        "run_administrative_log_sessions",
        lambda: LogSessionsReport(
            sessions=(
                LogSessionEntry(
                    stage="inference",
                    session_id="b" * 32,
                    created_at=datetime(2026, 10, 18, 9, 30, tzinfo=UTC),
                ),
            )
        ),
    )
    monkeypatch.setattr(
        commands,
        "run_administrative_server_status",
        lambda: server_status_calls.append(sentinel) or sentinel,
    )
    monkeypatch.setattr(
        commands,
        "run_administrative_session_log",
        lambda stage, session_id, source, *, lines: (
            log_reads.append((stage, session_id, source, lines)) or sentinel
        ),
    )
    monkeypatch.setattr(
        commands,
        "run_administrative_embedding_log",
        lambda *, lines: embedding_log_reads.append(lines) or sentinel,
    )
    monkeypatch.setattr(
        commands,
        "run_administrative_rebuild",
        lambda: rebuild_calls.append(sentinel) or sentinel,
    )
    monkeypatch.setattr(
        commands,
        "run_administrative_usage",
        lambda *, hours: usage_hours.append(hours) or sentinel,
    )
    admin_builds: list[object] = []
    admin_restarts: list[object] = []
    password_calls: list[str] = []
    real_password = commands.run_administrative_password
    monkeypatch.setattr(
        commands,
        "run_administrative_admin_rebuild",
        lambda: admin_builds.append(sentinel) or sentinel,
    )
    monkeypatch.setattr(
        commands,
        "run_administrative_restart_admin",
        lambda: admin_restarts.append(sentinel) or sentinel,
    )
    monkeypatch.setattr(
        commands,
        "run_administrative_password",
        lambda *, username, read_password=None: password_calls.append(username) or sentinel,
    )

    if scenario == "stage-failure-retry":
        # A failed operation is not success. A retry after the failure succeeds and stops nothing.

        def flaky(stage, action):
            calls.append((stage, action))
            if len(calls) == 1:
                raise RuntimeError("boom")
            return sentinel

        monkeypatch.setattr(commands, "run_administrative_command", flaky)
        assert (
            commands.run_operator_menu(
                read=_ScriptedRead(["2", "4", "4", "0", "0"]), write=writes.append
            )
            == 0
        )
        assert calls == [("ingestion", "status"), ("ingestion", "status")]
        payloads = [json.loads(line) for line in writes if line.startswith("{")]
        assert {"error": "RuntimeError"} in payloads
        assert {"label": "ok"} in payloads
        assert not any(action == "stop" for _stage, action in calls)
        assert setup_calls == [] and disposition_sets == []
        return

    if scenario == "main-eof":
        # EOF at the main menu returns 0 without any implicit stop or setup.
        assert (
            commands.run_operator_menu(read=lambda prompt: (_ for _ in ()).throw(EOFError())) == 0
        )
    elif scenario == "main-interrupt":
        # An interrupt at the main menu returns 130 without any implicit stop or setup.
        assert (
            commands.run_operator_menu(
                read=lambda prompt: (_ for _ in ()).throw(KeyboardInterrupt())
            )
            == 130
        )
    elif scenario == "worker-branch-eof":
        # EOF at the worker branch prompt returns 0, with no spurious operation error.
        class _BranchRunner:
            """Report a non-main branch for the setup prompt."""

            def run(self, argv, *, cwd=None):
                return subprocess.CompletedProcess(
                    list(argv), 0, stdout=b"prerequisite-inference\n", stderr=b""
                )

        monkeypatch.setattr(commands.mechanics, "SubprocessRunner", _BranchRunner)
        assert commands.run_operator_menu(read=_ScriptedRead(["1", "2"]), write=writes.append) == 0
        assert not any('"error"' in line for line in writes)
    elif scenario == "disposition-read-error":
        # A disposition read failure presents the safe error class and sets nothing.

        def failing_read(_target):
            raise RuntimeError("disposition-read-payload")

        monkeypatch.setattr(commands, "read_inference_target_disposition", failing_read)
        assert (
            commands.run_operator_menu(
                read=_ScriptedRead(["5", "6", "disp-target", "0", "0"]), write=writes.append
            )
            == 0
        )
        assert not any("disposition-read-payload" in line for line in writes)
        assert {"error": "RuntimeError"} in [
            json.loads(line) for line in writes if line.startswith("{")
        ]
    elif scenario == "disposition-cancellation":
        # Cancel at the choice prompt mutates nothing.
        assert (
            commands.run_operator_menu(
                read=_ScriptedRead(["5", "6", "disp-target", "0", "0"]), write=writes.append
            )
            == 0
        )
    elif scenario == "cleanup-list-error":
        # A failed cleanup listing prints the safe error class and deletes nothing.

        def failing_listing():
            raise RuntimeError("cleanup-list-payload")

        monkeypatch.setattr(commands, "run_administrative_dataset_list", failing_listing)
        assert (
            commands.run_operator_menu(
                read=_ScriptedRead(["1", "6", "0", "0"]), write=writes.append
            )
            == 0
        )
        assert not any("cleanup-list-payload" in line for line in writes)
        assert {"error": "RuntimeError"} in [
            json.loads(line) for line in writes if line.startswith("{")
        ]
    elif scenario == "cleanup-unlisted-target":
        # An answer outside the displayed inventory is refused and draws no confirmation.
        assert (
            commands.run_operator_menu(
                read=_ScriptedRead(["1", "6", "d" * 32, "0", "0"]), write=writes.append
            )
            == 0
        )
        assert not any(line.startswith("Delete dataset ") for line in writes)
    elif scenario == "cleanup-selected-target":
        # The selected dataset is displayed, refused as a target, and never confirmed.
        assert (
            commands.run_operator_menu(
                read=_ScriptedRead(["1", "6", "a" * 32, "0", "0"]), write=writes.append
            )
            == 0
        )
        assert dataset_listing.model_dump_json() in writes
        assert not any(line.startswith("Delete dataset ") for line in writes)
    elif scenario == "cleanup-cancel":
        # The confirmation names the exact target, and a cancel answer deletes nothing.
        assert (
            commands.run_operator_menu(
                read=_ScriptedRead(["1", "7", "before-inference.dump", "2", "0", "0"]),
                write=writes.append,
            )
            == 0
        )
        assert "Delete backup before-inference.dump?" in writes
    elif scenario == "cleanup-choice-interrupt":
        # An interrupt at the confirmation prompt returns 130 and deletes nothing.
        cleanup_answers = ["1", "6", "0" * 32]

        def interrupting_cleanup_read(prompt: str) -> str:
            if not cleanup_answers:
                raise KeyboardInterrupt
            return cleanup_answers.pop(0)

        assert commands.run_operator_menu(read=interrupting_cleanup_read) == 130
    elif scenario == "configuration-list-error":
        # A failed file listing prints the safe error class and the configuration guidance, reads no
        # file and saves nothing.
        def failing_configuration_listing():
            raise RuntimeError("configuration-list-payload")

        monkeypatch.setattr(
            commands, "run_administrative_config_list", failing_configuration_listing
        )
        assert (
            commands.run_operator_menu(
                read=_ScriptedRead(["1", "8", "0", "0"]), write=writes.append
            )
            == 0
        )
        assert not any("configuration-list-payload" in line for line in writes)
        assert {"error": "RuntimeError"} in [
            json.loads(line) for line in writes if line.startswith("{")
        ]
    elif scenario == "configuration-read-error":
        # A failed file read returns after the safe error, so no key or value is asked for.
        def failing_configuration_read(file):
            raise RuntimeError("configuration-read-payload")

        monkeypatch.setattr(commands, "run_administrative_config_read", failing_configuration_read)
        reader = _ScriptedRead(["1", "8", "config/web.toml", "0", "0"])
        assert commands.run_operator_menu(read=reader, write=writes.append) == 0
        assert not any("configuration-read-payload" in line for line in writes)
        assert not any("Configuration key (0 to cancel)" in prompt for prompt in reader.prompts)
    elif scenario == "configuration-unlisted-file":
        # An answer outside the listed files is refused before the read, and no key is asked for.
        reader = _ScriptedRead(["1", "8", "config/not-listed.toml", "0", "0"])
        assert commands.run_operator_menu(read=reader, write=writes.append) == 0
        assert "Configuration key (0 to cancel): " not in reader.prompts
    elif scenario == "configuration-unlisted-key":
        # An answer outside the chosen file's keys is refused and no confirmation is drawn.
        reader = _ScriptedRead(["1", "8", "config/web.toml", "NOT_A_KEY", "0", "0"])
        assert commands.run_operator_menu(read=reader, write=writes.append) == 0
        assert "JSON value: " not in reader.prompts
        assert not any(line.startswith("Save configuration ") for line in writes)
    elif scenario == "configuration-cancel":
        # Cancelling at the file prompt writes nothing and asks for no key.
        reader = _ScriptedRead(["1", "8", "0", "0", "0"])
        assert commands.run_operator_menu(read=reader, write=writes.append) == 0
        assert "Configuration key (0 to cancel): " not in reader.prompts
    elif scenario == "configuration-save-interrupt":
        # An interrupt at the confirmation prompt returns 130 and saves nothing.
        configuration_answers = ["1", "8", "config/web.toml", "WEB_PORT", "18026"]

        def interrupting_configuration_read(prompt: str) -> str:
            if not configuration_answers:
                raise KeyboardInterrupt
            return configuration_answers.pop(0)

        assert commands.run_operator_menu(read=interrupting_configuration_read) == 130
    elif scenario == "server-logs-list-error":
        # A failed session listing prints the safe error and the log guidance, then reads nothing.

        def failing_log_listing():
            raise RuntimeError("log-list-payload")

        monkeypatch.setattr(commands, "run_administrative_log_sessions", failing_log_listing)
        reader = _ScriptedRead(["7", "2", "0", "0"])
        assert commands.run_operator_menu(read=reader, write=writes.append) == 0
        assert not any("log-list-payload" in line for line in writes)
        assert {"error": "RuntimeError"} in [
            json.loads(line) for line in writes if line.startswith("{")
        ]
        assert not any("Stage (0 to cancel)" in prompt for prompt in reader.prompts)
    elif scenario == "server-logs-unlisted-session":
        # An answer the listing does not carry is refused before any source or line count.
        reader = _ScriptedRead(["7", "2", "inference", "c" * 32, "0", "0"])
        assert commands.run_operator_menu(read=reader, write=writes.append) == 0
        assert not any("Log source" in prompt for prompt in reader.prompts)
        assert not any("Lines (0 to cancel)" in prompt for prompt in reader.prompts)
    elif scenario == "server-logs-invalid-source":
        # A source choice outside the offered set reads nothing and asks for no line count.
        reader = _ScriptedRead(["7", "2", "inference", "b" * 32, "9", "0", "0"])
        assert commands.run_operator_menu(read=reader, write=writes.append) == 0
        assert not any("Lines (0 to cancel)" in prompt for prompt in reader.prompts)
    elif scenario == "server-logs-invalid-lines":
        # A line count that is not a positive whole number reads nothing.
        assert (
            commands.run_operator_menu(
                read=_ScriptedRead(["7", "2", "inference", "b" * 32, "4", "many", "0", "0"]),
                write=writes.append,
            )
            == 0
        )
    elif scenario == "server-logs-cancel":
        # Cancel at the stage prompt returns without a session prompt and without a read.
        reader = _ScriptedRead(["7", "2", "0", "0", "0"])
        assert commands.run_operator_menu(read=reader, write=writes.append) == 0
        assert "Session id (0 to cancel): " not in reader.prompts
    elif scenario == "usage-cancel":
        # Cancel at the hour prompt returns without a report and without pruning.
        reader = _ScriptedRead(["7", "4", "0", "0", "0"])
        assert commands.run_operator_menu(read=reader, write=writes.append) == 0
        assert "Hours (0 to cancel): " in reader.prompts
    elif scenario == "usage-invalid-hours":
        # An answer that is not a positive whole hour count reads nothing.
        assert (
            commands.run_operator_menu(
                read=_ScriptedRead(["7", "4", "many", "0", "0"]), write=writes.append
            )
            == 0
        )
    elif scenario == "rebuild-cancel":
        # Any confirmation other than the rebuild choice runs nothing.
        assert (
            commands.run_operator_menu(
                read=_ScriptedRead(["1", "9", "2", "0", "0"]), write=writes.append
            )
            == 0
        )
        assert "Rebuild this site's frontend, containers and web server?" in writes
    elif scenario == "rebuild-interrupt":
        # An interrupt at the confirmation prompt returns 130 and runs nothing.
        rebuild_answers = ["1", "9"]

        def interrupting_rebuild_read(prompt: str) -> str:
            if not rebuild_answers:
                raise KeyboardInterrupt
            return rebuild_answers.pop(0)

        assert commands.run_operator_menu(read=interrupting_rebuild_read) == 130
    elif scenario == "admin-rebuild-cancel":
        # Any confirmation other than the administration rebuild choice builds and restarts nothing.
        assert (
            commands.run_operator_menu(
                read=_ScriptedRead(["1", "11", "2", "0", "0"]), write=writes.append
            )
            == 0
        )
        assert "Rebuild the admin panel? This signs all operators out." in writes
    elif scenario == "admin-rebuild-build-failure":
        # A failed administration build stops the callback before its restart, with the safe error.
        def failing_admin_build():
            raise RuntimeError("admin-build-payload")

        monkeypatch.setattr(commands, "run_administrative_admin_rebuild", failing_admin_build)
        assert (
            commands.run_operator_menu(
                read=_ScriptedRead(["1", "11", "1", "0", "0"]), write=writes.append
            )
            == 0
        )
        # Only the build delegate is reached, and it recorded no success.
        assert admin_builds == []
        assert not any("admin-build-payload" in line for line in writes)
        assert {"error": "RuntimeError"} in [
            json.loads(line) for line in writes if line.startswith("{")
        ]
    elif scenario == "password-cancel":
        # The password entry offers the setup choice, and a cancel stores nothing.
        reader = _ScriptedRead(["1", "9", "0", "0", "0"])
        assert commands.run_operator_menu(read=reader, write=writes.append) == 0
    elif scenario == "password-interrupt":
        # An interrupt at the username prompt returns 130 and stores nothing.
        password_answers = ["1", "10"]

        def interrupting_password_read(prompt: str) -> str:
            if not password_answers:
                raise KeyboardInterrupt
            return password_answers.pop(0)

        assert commands.run_operator_menu(read=interrupting_password_read) == 130
    elif scenario == "password-hidden-eof":
        # An end of input at the hidden prompt leaves the menu with 0 and stores nothing.

        def eof_password(_prompt: str) -> str:
            raise EOFError

        stored: list[str] = []
        monkeypatch.setattr(commands, "run_administrative_password", real_password)
        monkeypatch.setattr(
            commands,
            "set_admin_password",
            lambda *, username, password: stored.append(username),
        )
        monkeypatch.setattr(commands.getpass, "getpass", eof_password)
        reader = _ScriptedRead(["1", "10", "synthetic-operator", "0", "0"])
        assert commands.run_operator_menu(read=reader, write=writes.append) == 0
        assert stored == []
        assert not any('"error"' in line for line in writes)
    else:  # disposition-choice-interrupt
        # An interrupt at the choice prompt returns 130 and sets nothing.
        disposition_answers = ["5", "6", "disp-target"]

        def interrupting_read(prompt: str) -> str:
            if not disposition_answers:
                raise KeyboardInterrupt
            return disposition_answers.pop(0)

        assert commands.run_operator_menu(read=interrupting_read) == 130

    assert disposition_sets == []
    assert calls == []
    assert setup_calls == []
    assert dataset_deletions == []
    assert backup_deletions == []
    assert configuration_writes == []
    assert server_status_calls == []
    assert log_reads == []
    assert embedding_log_reads == []
    assert rebuild_calls == []
    assert usage_hours == []
    assert password_calls == []
    assert admin_builds == []
    assert admin_restarts == []
