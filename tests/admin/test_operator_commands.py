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

from course_explorer.config import UsageSettings, WebSettings
from course_explorer_admin import commands, mechanics
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
        "cleanup-delegates",
        "dataset-list-cli",
        "dataset-delete-cli",
        "backup-list-cli",
        "backup-delete-cli",
        "cleanup-missing-target",
        "dataset-cleanup-safe-failure",
        "backup-cleanup-safe-failure",
        "hubs-cli",
        "config-delegate-list",
        "config-delegate-read",
        "config-delegate-set",
        "config-delegate-set-default",
        "config-cli-list",
        "config-cli-read",
        "config-cli-set",
        "config-required-verb",
        "config-required-read-file",
        "config-required-set-value",
        "config-menu-explicit",
        "config-menu-default",
        "config-safe-read-failure",
        "config-safe-set-failure",
        "target-read-cli",
        "target-read-safe-failure",
        "dispose-nothing",
        "dispose-done",
        "dispose-failed",
        "dispose-invalid-syntax",
        "dispose-safe-failure",
        "server-status-delegate",
        "logs-sessions-delegate",
        "session-log-delegate",
        "embedding-log-delegate",
        "rebuild-delegate",
        "admin-rebuild-delegate",
        "admin-restart-delegate",
        "server-status-cli",
        "logs-sessions-cli",
        "logs-commands-delegate",
        "logs-commands-cli",
        "logs-read-cli",
        "logs-embedding-cli",
        "rebuild-cli",
        "admin-rebuild-cli",
        "admin-restart-cli",
        "logs-required-syntax",
        "server-safe-failure",
        "logs-safe-failure",
        "rebuild-safe-failure",
        "admin-rebuild-safe-failure",
        "admin-restart-safe-failure",
        "usage-delegate",
        "usage-cli",
        "usage-safe-failure",
        "password-delegate",
        "password-mismatch",
        "password-hidden-input-failure",
        "password-cli",
        "password-required-username",
        "password-safe-failure",
    ],
)
def test_operator_setup_preflight_and_cli_preserve_owners_notices_and_safe_failures(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], case: str
) -> None:
    """Setup/preflight forward to owners and the CLI is safe on success and failure.

    Each parametrized invocation drives one coherent public adapter behavior: an owner delegation, one
    dispatched configuration verb, the CLI help/syntax guard, or one ``dispose inference ...`` machine
    command with nothing mapped to None, invalid syntax, or a safe failure. Assertions live in their
    owning case instead of one combined session-wide call list.
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

    if case == "cleanup-delegates":
        # Each cleanup delegate forwards once to its owner: the backup listing takes no argument, the
        # dataset delegates forward a runner, the deletion also its target, and the production runner
        # resolves like setup.
        from course_explorer_admin import backups as backups_module
        from course_explorer_admin import datasets as datasets_module

        dataset_listing = _Sentinel("dataset-listing")
        backup_listing = _Sentinel("backup-listing")
        dataset_deletion = _Sentinel("dataset-deletion")
        backup_deletion = _Sentinel("backup-deletion")
        delegated: list[tuple] = []
        monkeypatch.setattr(
            datasets_module,
            "list_retained_datasets",
            lambda *, runner: delegated.append(("datasets", runner)) or dataset_listing,
        )
        monkeypatch.setattr(
            datasets_module,
            "delete_retained_dataset",
            lambda dataset_id, *, runner: (
                delegated.append(("dataset-delete", dataset_id, runner)) or dataset_deletion
            ),
        )
        monkeypatch.setattr(
            backups_module,
            "list_backups",
            lambda: delegated.append(("backups",)) or backup_listing,
        )
        monkeypatch.setattr(
            backups_module,
            "delete_backup",
            lambda name: delegated.append(("backup-delete", name)) or backup_deletion,
        )

        assert commands.run_administrative_dataset_list() is dataset_listing
        assert commands.run_administrative_backup_list() is backup_listing
        assert commands.run_administrative_backup_delete("before.dump") is backup_deletion
        explicit_runner = mechanics.SubprocessRunner()
        assert commands.run_administrative_dataset_list(runner=explicit_runner) is dataset_listing
        assert commands.run_administrative_dataset_delete("a" * 32) is dataset_deletion
        assert (
            commands.run_administrative_dataset_delete("b" * 32, runner=explicit_runner)
            is dataset_deletion
        )
        assert delegated[0][0] == "datasets"
        assert isinstance(delegated[0][1], mechanics.SubprocessRunner)
        assert delegated[1:3] == [("backups",), ("backup-delete", "before.dump")]
        assert delegated[3] == ("datasets", explicit_runner)
        assert delegated[4][0] == "dataset-delete" and delegated[4][1] == "a" * 32
        assert isinstance(delegated[4][2], mechanics.SubprocessRunner)
        assert delegated[5] == ("dataset-delete", "b" * 32, explicit_runner)
        return

    if case == "dataset-list-cli":
        # `datasets list` emits the owner listing on stdout with no notice on stderr.
        listing = _Sentinel("dataset-listing")
        listed: list[object] = []
        monkeypatch.setattr(
            _CLI_MODULE,
            "run_administrative_dataset_list",
            lambda: listed.append(listing) or listing,
        )
        assert _CLI_MODULE.main(["datasets", "list"]) == 0
        captured = capsys.readouterr()
        assert json.loads(captured.out)["label"] == "dataset-listing"
        assert captured.err == ""
        assert len(listed) == 1
        return

    if case == "dataset-delete-cli":
        # `datasets delete DATASET_ID` forwards exactly that identity once.
        deletion = _Sentinel("dataset-deletion")
        deleted: list[str] = []
        monkeypatch.setattr(
            _CLI_MODULE,
            "run_administrative_dataset_delete",
            lambda dataset_id: deleted.append(dataset_id) or deletion,
        )
        assert _CLI_MODULE.main(["datasets", "delete", "a" * 32]) == 0
        captured = capsys.readouterr()
        assert json.loads(captured.out)["label"] == "dataset-deletion"
        assert captured.err == ""
        assert deleted == ["a" * 32]
        return

    if case == "backup-list-cli":
        listing = _Sentinel("backup-listing")
        listed: list[object] = []
        monkeypatch.setattr(
            _CLI_MODULE,
            "run_administrative_backup_list",
            lambda: listed.append(listing) or listing,
        )
        assert _CLI_MODULE.main(["backups", "list"]) == 0
        captured = capsys.readouterr()
        assert json.loads(captured.out)["label"] == "backup-listing"
        assert captured.err == ""
        assert len(listed) == 1
        return

    if case == "backup-delete-cli":
        deletion = _Sentinel("backup-deletion")
        deleted: list[str] = []
        monkeypatch.setattr(
            _CLI_MODULE,
            "run_administrative_backup_delete",
            lambda name: deleted.append(name) or deletion,
        )
        assert _CLI_MODULE.main(["backups", "delete", "before-inference.dump"]) == 0
        captured = capsys.readouterr()
        assert json.loads(captured.out)["label"] == "backup-deletion"
        assert captured.err == ""
        assert deleted == ["before-inference.dump"]
        return

    if case == "cleanup-missing-target":
        # Each nested verb requires its one target, and an unknown verb delegates nothing.
        delegated: list[str] = []
        monkeypatch.setattr(
            _CLI_MODULE, "run_administrative_dataset_list", lambda: delegated.append("datasets")
        )
        monkeypatch.setattr(
            _CLI_MODULE,
            "run_administrative_dataset_delete",
            lambda dataset_id: delegated.append("dataset-delete"),
        )
        monkeypatch.setattr(
            _CLI_MODULE, "run_administrative_backup_list", lambda: delegated.append("backups")
        )
        monkeypatch.setattr(
            _CLI_MODULE,
            "run_administrative_backup_delete",
            lambda name: delegated.append("backup-delete"),
        )
        for argv in (
            ["datasets"],
            ["datasets", "delete"],
            ["datasets", "enroll"],
            ["backups"],
            ["backups", "delete"],
            ["backups", "prune"],
        ):
            with pytest.raises(SystemExit) as bad_cleanup:
                _CLI_MODULE.main(argv)
            assert bad_cleanup.value.code != 0
        capsys.readouterr()
        assert delegated == []
        return

    if case == "dataset-cleanup-safe-failure":
        # A failed dataset cleanup prints only its class token and the dataset cleanup guidance.

        def failing_dataset_cleanup():
            raise RuntimeError("dataset-cleanup-payload-value")

        monkeypatch.setattr(_CLI_MODULE, "run_administrative_dataset_list", failing_dataset_cleanup)
        assert _CLI_MODULE.main(["datasets", "list"]) == 1
        captured = capsys.readouterr()
        assert json.loads(captured.err.splitlines()[0]) == {"error": "RuntimeError"}
        assert "dataset-cleanup-payload-value" not in captured.err
        assert "dataset listing" in captured.err
        return

    if case == "backup-cleanup-safe-failure":

        def failing_backup_cleanup(name):
            raise RuntimeError("backup-cleanup-payload-value")

        monkeypatch.setattr(_CLI_MODULE, "run_administrative_backup_delete", failing_backup_cleanup)
        assert _CLI_MODULE.main(["backups", "delete", "before.dump"]) == 1
        captured = capsys.readouterr()
        assert json.loads(captured.err.splitlines()[0]) == {"error": "RuntimeError"}
        assert "backup-cleanup-payload-value" not in captured.err
        assert "backup listing" in captured.err
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

    if case == "config-delegate-list":
        # The listing delegate forwards once to its owner and returns the listing report.
        from course_explorer_admin import configuration as editor_module

        listing = _Sentinel("config-files")
        delegated: list[tuple] = []
        monkeypatch.setattr(
            editor_module,
            "list_configuration_files",
            lambda: delegated.append(("list",)) or listing,
        )

        assert commands.run_administrative_config_list() is listing
        assert delegated == [("list",)]
        return

    if case == "config-delegate-read":
        # The read delegate forwards the one file name once.
        from course_explorer_admin import configuration as editor_module

        reading = _Sentinel("config-file")
        delegated: list[tuple] = []
        monkeypatch.setattr(
            editor_module,
            "read_configuration_file",
            lambda file: delegated.append(("read", file)) or reading,
        )

        assert commands.run_administrative_config_read("config/web.toml") is reading
        assert delegated == [("read", "config/web.toml")]
        return

    if case == "config-delegate-set":
        # The save delegate forwards the file, the key, the literal and the injected families once.
        from course_explorer_admin import configuration as editor_module

        writing = _Sentinel("config-write")
        delegated: list[tuple] = []
        families = (WebSettings,)
        monkeypatch.setattr(
            editor_module,
            "set_configuration_value",
            lambda file, key, value, *, settings_families=(): (
                delegated.append(("set", file, key, value, settings_families)) or writing
            ),
        )

        assert (
            commands.run_administrative_config_set(
                "config/web.toml", "WEB_PORT", "18026", settings_families=families
            )
            is writing
        )
        assert delegated == [("set", "config/web.toml", "WEB_PORT", "18026", families)]
        return

    if case == "config-delegate-set-default":
        # Without a supplied tuple the save delegate forwards an empty family tuple.
        from course_explorer_admin import configuration as editor_module

        writing = _Sentinel("config-write")
        delegated: list[tuple] = []
        monkeypatch.setattr(
            editor_module,
            "set_configuration_value",
            lambda file, key, value, *, settings_families=(): (
                delegated.append(("set", file, key, value, settings_families)) or writing
            ),
        )

        assert (
            commands.run_administrative_config_set("config/web.toml", "WEB_PORT", "18026")
            is writing
        )
        assert delegated == [("set", "config/web.toml", "WEB_PORT", "18026", ())]
        return

    if case == "config-cli-list":
        # `config list` dispatches once and emits the listing.
        listing = _Sentinel("config-files")
        calls: list[tuple] = []
        monkeypatch.setattr(
            _CLI_MODULE,
            "run_administrative_config_list",
            lambda: calls.append(("list",)) or listing,
        )

        assert _CLI_MODULE.main(["config", "list"]) == 0
        assert json.loads(capsys.readouterr().out)["label"] == "config-files"
        assert calls == [("list",)]
        return

    if case == "config-cli-read":
        # `config read FILE` dispatches the one file name once and emits its report.
        reading = _Sentinel("config-file")
        calls: list[tuple] = []
        monkeypatch.setattr(
            _CLI_MODULE,
            "run_administrative_config_read",
            lambda file: calls.append(("read", file)) or reading,
        )

        assert _CLI_MODULE.main(["config", "read", "config/web.toml"]) == 0
        assert json.loads(capsys.readouterr().out)["label"] == "config-file"
        assert calls == [("read", "config/web.toml")]
        return

    if case == "config-cli-set":
        # `config set FILE KEY VALUE` dispatches once and carries the injected family tuple.
        writing = _Sentinel("config-write")
        calls: list[tuple] = []
        families = (WebSettings,)
        monkeypatch.setattr(
            _CLI_MODULE,
            "run_administrative_config_set",
            lambda file, key, value, *, settings_families=(): (
                calls.append(("set", file, key, value, settings_families)) or writing
            ),
        )

        assert (
            _CLI_MODULE.main(
                ["config", "set", "config/web.toml", "WEB_PORT", "18026"],
                configuration_families=families,
            )
            == 0
        )
        assert json.loads(capsys.readouterr().out)["label"] == "config-write"
        assert calls == [("set", "config/web.toml", "WEB_PORT", "18026", families)]
        return

    if case in {"config-required-verb", "config-required-read-file", "config-required-set-value"}:
        # Each missing positional is one syntax failure that dispatches nothing.
        argv = {
            "config-required-verb": ["config"],
            "config-required-read-file": ["config", "read"],
            "config-required-set-value": ["config", "set", "config/web.toml", "WEB_PORT"],
        }[case]
        calls: list[tuple] = []
        monkeypatch.setattr(
            _CLI_MODULE, "run_administrative_config_list", lambda: calls.append(("list",))
        )
        monkeypatch.setattr(
            _CLI_MODULE,
            "run_administrative_config_read",
            lambda file: calls.append(("read", file)),
        )
        monkeypatch.setattr(
            _CLI_MODULE,
            "run_administrative_config_set",
            lambda file, key, value, *, settings_families=(): calls.append(("set",)),
        )

        with pytest.raises(SystemExit) as bad_config:
            _CLI_MODULE.main(argv)
        assert bad_config.value.code != 0
        capsys.readouterr()
        assert calls == []
        return

    if case in {"config-menu-explicit", "config-menu-default"}:
        # `menu` and an absent subcommand each forward the same family tuple to the menu owner.
        argv = ["menu"] if case == "config-menu-explicit" else []
        families = (WebSettings,)
        menu_calls: list[dict] = []
        monkeypatch.setattr(
            _CLI_MODULE, "run_operator_menu", lambda **kwargs: menu_calls.append(kwargs) or 0
        )

        assert _CLI_MODULE.main(argv, configuration_families=families) == 0
        assert menu_calls == [
            {"run_command": None, "run_summary": None, "configuration_families": families}
        ]
        return

    if case == "config-safe-read-failure":
        # A failed configuration read prints only its class token and the configuration guidance.
        def failing_read(file):
            raise RuntimeError("configuration-payload-value")

        monkeypatch.setattr(_CLI_MODULE, "run_administrative_config_read", failing_read)
        assert _CLI_MODULE.main(["config", "read", "config/web.toml"]) == 1
        captured = capsys.readouterr()
        assert json.loads(captured.err.splitlines()[0]) == {"error": "RuntimeError"}
        assert "configuration-payload-value" not in captured.err
        assert "listed configuration file and key" in captured.err
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
        assert "listed configuration file and key" in captured.err
        return

    if case == "server-status-delegate":
        # The server status delegate resolves the production runner and forwards once.
        from course_explorer_admin import server as server_module

        status = _Sentinel("server-status")
        delegated: list[tuple] = []
        monkeypatch.setattr(
            server_module,
            "read_server_status",
            lambda *, runner: delegated.append(("status", runner)) or status,
        )

        assert commands.run_administrative_server_status() is status
        explicit_runner = mechanics.SubprocessRunner()
        assert commands.run_administrative_server_status(runner=explicit_runner) is status
        assert delegated[0][0] == "status"
        assert isinstance(delegated[0][1], mechanics.SubprocessRunner)
        assert delegated[1] == ("status", explicit_runner)
        return

    if case == "logs-sessions-delegate":
        # The session listing delegate takes no argument and forwards once.
        from course_explorer_admin import logs as logs_module

        listing = _Sentinel("log-sessions")
        delegated: list[tuple] = []
        monkeypatch.setattr(
            logs_module,
            "list_log_sessions",
            lambda: delegated.append(("sessions",)) or listing,
        )

        assert commands.run_administrative_log_sessions() is listing
        assert delegated == [("sessions",)]
        return

    if case == "session-log-delegate":
        # The session log delegate forwards the source selection, the line count and its runner.
        from course_explorer_admin import logs as logs_module

        reading = _Sentinel("log-read")
        delegated: list[tuple] = []
        monkeypatch.setattr(
            logs_module,
            "read_session_log",
            lambda stage, session_id, source, *, lines, runner: (
                delegated.append((stage, session_id, source, lines, runner)) or reading
            ),
        )

        assert (
            commands.run_administrative_session_log("inference", "a" * 32, "worker-runner", lines=5)
            is reading
        )
        explicit_runner = mechanics.SubprocessRunner()
        assert (
            commands.run_administrative_session_log(
                "embedding", "b" * 32, "server-stdout", lines=0, runner=explicit_runner
            )
            is reading
        )
        # A non-positive count reaches the owner, which owns the positive-count policy.
        assert delegated[0][:4] == ("inference", "a" * 32, "worker-runner", 5)
        assert isinstance(delegated[0][4], mechanics.SubprocessRunner)
        assert delegated[1] == ("embedding", "b" * 32, "server-stdout", 0, explicit_runner)
        return

    if case == "embedding-log-delegate":
        # The embedding log delegate forwards one line count and resolves its runner.
        from course_explorer_admin import logs as logs_module

        reading = _Sentinel("embedding-log")
        delegated: list[tuple] = []
        monkeypatch.setattr(
            logs_module,
            "read_embedding_log",
            lambda *, lines, runner: delegated.append((lines, runner)) or reading,
        )

        assert commands.run_administrative_embedding_log(lines=7) is reading
        assert delegated[0][0] == 7
        assert isinstance(delegated[0][1], mechanics.SubprocessRunner)
        return

    if case == "rebuild-delegate":
        # The rebuild delegate resolves the production runner and forwards once.
        from course_explorer_admin import rebuild as rebuild_module

        report = _Sentinel("rebuild")
        delegated: list[tuple] = []
        monkeypatch.setattr(
            rebuild_module,
            "rebuild_site",
            lambda *, runner: delegated.append(("rebuild", runner)) or report,
        )

        assert commands.run_administrative_rebuild() is report
        assert delegated[0][0] == "rebuild"
        assert isinstance(delegated[0][1], mechanics.SubprocessRunner)
        return

    if case == "admin-rebuild-delegate" or case == "admin-restart-delegate":
        # Each administration maintenance delegate resolves the production runner and forwards once.
        from course_explorer_admin import rebuild as rebuild_module

        build = _Sentinel("admin-rebuild")
        restart = _Sentinel("admin-restart")
        delegated: list[tuple] = []
        monkeypatch.setattr(
            rebuild_module,
            "rebuild_admin",
            lambda *, runner: delegated.append(("build", runner)) or build,
        )
        monkeypatch.setattr(
            rebuild_module,
            "restart_admin",
            lambda *, runner: delegated.append(("restart", runner)) or restart,
        )

        if case == "admin-rebuild-delegate":
            assert commands.run_administrative_admin_rebuild() is build
            assert delegated[0][0] == "build"
        else:
            assert commands.run_administrative_restart_admin() is restart
            assert delegated[0][0] == "restart"
        assert isinstance(delegated[0][1], mechanics.SubprocessRunner)
        assert len(delegated) == 1
        return

    if case == "server-status-cli":
        # `server status` dispatches once and emits the owner report.
        status = _Sentinel("server-status")
        calls: list[tuple] = []
        monkeypatch.setattr(
            _CLI_MODULE,
            "run_administrative_server_status",
            lambda: calls.append(("status",)) or status,
        )

        assert _CLI_MODULE.main(["server", "status"]) == 0
        assert json.loads(capsys.readouterr().out)["label"] == "server-status"
        assert calls == [("status",)]
        return

    if case == "logs-sessions-cli":
        # `logs sessions` dispatches once and emits the session listing.
        listing = _Sentinel("log-sessions")
        calls: list[tuple] = []
        monkeypatch.setattr(
            _CLI_MODULE,
            "run_administrative_log_sessions",
            lambda: calls.append(("sessions",)) or listing,
        )

        assert _CLI_MODULE.main(["logs", "sessions"]) == 0
        assert json.loads(capsys.readouterr().out)["label"] == "log-sessions"
        assert calls == [("sessions",)]
        return

    if case == "logs-commands-delegate":
        # The command-log delegate reads the administration backend's sole log owner once, and it
        # imports that owner inside the call so the two packages do not import each other.
        from course_explorer_admin_web import command_log as command_log_module

        report = _Sentinel("command-log")
        reads: list[object] = []
        monkeypatch.setattr(
            command_log_module,
            "read_command_log",
            lambda: reads.append(report) or report,
        )

        assert commands.run_administrative_command_log() is report
        assert reads == [report]
        return

    if case == "logs-commands-cli":
        # `logs commands` dispatches once and emits the retained command-log report.
        report = _Sentinel("command-log")
        calls: list[object] = []
        monkeypatch.setattr(
            _CLI_MODULE,
            "run_administrative_command_log",
            lambda: calls.append(report) or report,
        )

        assert _CLI_MODULE.main(["logs", "commands"]) == 0
        assert json.loads(capsys.readouterr().out)["label"] == "command-log"
        assert calls == [report]
        return

    if case == "logs-read-cli":
        # `logs read` forwards the stage, the session, the source and the integer line count once.
        reading = _Sentinel("log-read")
        calls: list[tuple] = []
        monkeypatch.setattr(
            _CLI_MODULE,
            "run_administrative_session_log",
            lambda stage, session_id, source, *, lines: (
                calls.append((stage, session_id, source, lines)) or reading
            ),
        )

        assert (
            _CLI_MODULE.main(
                ["logs", "read", "inference", "a" * 32, "worker-runtime", "--lines", "5"]
            )
            == 0
        )
        assert json.loads(capsys.readouterr().out)["label"] == "log-read"
        assert calls == [("inference", "a" * 32, "worker-runtime", 5)]
        return

    if case == "logs-embedding-cli":
        # `logs embedding` forwards the one line count.
        reading = _Sentinel("embedding-log")
        calls: list[tuple] = []
        monkeypatch.setattr(
            _CLI_MODULE,
            "run_administrative_embedding_log",
            lambda *, lines: calls.append((lines,)) or reading,
        )

        assert _CLI_MODULE.main(["logs", "embedding", "--lines", "7"]) == 0
        assert json.loads(capsys.readouterr().out)["label"] == "embedding-log"
        assert calls == [(7,)]
        return

    if case == "rebuild-cli":
        # `rebuild` dispatches once and emits the owner report.
        report = _Sentinel("rebuild")
        calls: list[tuple] = []
        monkeypatch.setattr(
            _CLI_MODULE,
            "run_administrative_rebuild",
            lambda: calls.append(("rebuild",)) or report,
        )

        assert _CLI_MODULE.main(["rebuild"]) == 0
        captured = capsys.readouterr()
        assert json.loads(captured.out)["label"] == "rebuild"
        assert captured.err == ""
        assert calls == [("rebuild",)]
        return

    if case == "admin-rebuild-cli" or case == "admin-restart-cli":
        # Each administration verb dispatches once and emits only its own report.
        report = _Sentinel("admin-maintenance")
        calls: list[str] = []
        monkeypatch.setattr(
            _CLI_MODULE,
            "run_administrative_admin_rebuild",
            lambda: calls.append("build") or report,
        )
        monkeypatch.setattr(
            _CLI_MODULE,
            "run_administrative_restart_admin",
            lambda: calls.append("restart") or report,
        )
        build_verb = case == "admin-rebuild-cli"
        assert _CLI_MODULE.main(["rebuild-admin" if build_verb else "restart-admin"]) == 0
        captured = capsys.readouterr()
        assert json.loads(captured.out)["label"] == "admin-maintenance"
        # The verb performs its own command alone, so no other maintenance call is reached.
        assert captured.err == ""
        assert calls == ["build" if build_verb else "restart"]
        return

    if case == "logs-required-syntax":
        # Every missing or unknown argument is one syntax failure that dispatches nothing.
        delegated: list[str] = []
        monkeypatch.setattr(
            _CLI_MODULE,
            "run_administrative_server_status",
            lambda: delegated.append("server"),
        )
        monkeypatch.setattr(
            _CLI_MODULE, "run_administrative_log_sessions", lambda: delegated.append("sessions")
        )
        monkeypatch.setattr(
            _CLI_MODULE,
            "run_administrative_session_log",
            lambda stage, session_id, source, *, lines: delegated.append("read"),
        )
        monkeypatch.setattr(
            _CLI_MODULE,
            "run_administrative_embedding_log",
            lambda *, lines: delegated.append("log"),
        )
        monkeypatch.setattr(
            _CLI_MODULE, "run_administrative_rebuild", lambda: delegated.append("rebuild")
        )
        for argv in (
            ["server"],
            ["server", "report"],
            ["logs"],
            ["logs", "prune"],
            ["logs", "commands", "extra"],
            ["logs", "read", "inference", "a" * 32, "server-stdout"],
            ["logs", "read", "inference", "a" * 32, "server-stdout", "--lines", "many"],
            ["logs", "read", "bogus", "a" * 32, "server-stdout", "--lines", "5"],
            ["logs", "read", "inference", "a" * 32, "bogus", "--lines", "5"],
            ["logs", "embedding"],
            ["rebuild", "extra"],
        ):
            with pytest.raises(SystemExit) as bad_logs:
                _CLI_MODULE.main(argv)
            assert bad_logs.value.code != 0
        capsys.readouterr()
        assert delegated == []
        return

    if case in {
        "server-safe-failure",
        "logs-safe-failure",
        "rebuild-safe-failure",
        "admin-rebuild-safe-failure",
        "admin-restart-safe-failure",
    }:
        # A failed server, log or maintenance operation prints only its class token and its guidance.
        payload = f"{case}-payload-value"

        def failing_operation(*args, **kwargs):
            raise RuntimeError(payload)

        argv, symbol = {
            "server-safe-failure": (["server", "status"], "run_administrative_server_status"),
            "logs-safe-failure": (
                ["logs", "read", "inference", "a" * 32, "keepalive", "--lines", "5"],
                "run_administrative_session_log",
            ),
            "rebuild-safe-failure": (["rebuild"], "run_administrative_rebuild"),
            "admin-rebuild-safe-failure": (
                ["rebuild-admin"],
                "run_administrative_admin_rebuild",
            ),
            "admin-restart-safe-failure": (
                ["restart-admin"],
                "run_administrative_restart_admin",
            ),
        }[case]
        monkeypatch.setattr(_CLI_MODULE, symbol, failing_operation)
        assert _CLI_MODULE.main(argv) == 1
        captured = capsys.readouterr()
        assert json.loads(captured.err.splitlines()[0]) == {"error": "RuntimeError"}
        assert payload not in captured.err
        assert captured.err.splitlines()[1] != ""
        if case != "server-safe-failure" and case != "logs-safe-failure":
            # Both maintenance verbs select the rebuild guidance rather than another operation's.
            assert "prepared frontend" in captured.err
        return

    if case == "usage-delegate":
        # The usage delegate loads the retention settings once and forwards the window once.
        settings = UsageSettings(USAGE_RETENTION_DAYS=7)
        loaded: list[object] = []
        windows: list[dict] = []
        report = _Sentinel("usage-report")
        monkeypatch.setattr(
            commands, "load_usage_settings", lambda: loaded.append(settings) or settings
        )
        monkeypatch.setattr(
            commands,
            "read_usage_report",
            lambda *, hours, retention_days: (
                windows.append({"hours": hours, "retention_days": retention_days}) or report
            ),
        )

        assert commands.run_administrative_usage(hours=5) is report
        assert loaded == [settings]
        assert windows == [{"hours": 5, "retention_days": 7}]
        return

    if case == "usage-cli":
        # `usage --hours N` dispatches once with that window and emits the report.
        report = _Sentinel("usage-report")
        calls: list[int] = []
        monkeypatch.setattr(
            _CLI_MODULE, "run_administrative_usage", lambda *, hours: calls.append(hours) or report
        )

        assert _CLI_MODULE.main(["usage", "--hours", "24"]) == 0
        captured = capsys.readouterr()
        assert json.loads(captured.out)["label"] == "usage-report"
        assert captured.err == ""
        assert calls == [24]
        with pytest.raises(SystemExit) as bad_usage:
            _CLI_MODULE.main(["usage"])
        assert bad_usage.value.code != 0
        capsys.readouterr()
        assert calls == [24]
        return

    if case == "usage-safe-failure":
        # A failed usage report prints only its class token and the usage guidance.

        def failing_usage(*, hours):
            raise RuntimeError("usage-payload-value")

        monkeypatch.setattr(_CLI_MODULE, "run_administrative_usage", failing_usage)
        assert _CLI_MODULE.main(["usage", "--hours", "24"]) == 1
        captured = capsys.readouterr()
        assert json.loads(captured.err.splitlines()[0]) == {"error": "RuntimeError"}
        assert "usage-payload-value" not in captured.err
        assert "configured retention" in captured.err
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
        prompts: list[str] = []

        def reader(prompt: str) -> str:
            prompts.append(prompt)
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
        assert prompts == ["Password: ", "Repeat password: "]
        assert len(delegated) == 1
        assert delegated[0]["username"] == "synthetic-operator"
        assert delegated[0]["password"].get_secret_value() == "first-entry"
        assert report.model_dump() == {"configured": True}
        assert "first-entry" not in report.model_dump_json()
        return

    if case == "password-cli":
        # `password --username USERNAME` dispatches that username once and emits its acknowledgment.
        report = commands.PasswordSetReport()
        usernames: list[str] = []
        monkeypatch.setattr(
            _CLI_MODULE,
            "run_administrative_password",
            lambda *, username: usernames.append(username) or report,
        )
        assert _CLI_MODULE.main(["password", "--username", "synthetic-operator"]) == 0
        captured = capsys.readouterr()
        assert json.loads(captured.out) == {"configured": True}
        assert captured.err == ""
        assert usernames == ["synthetic-operator"]
        return

    if case == "password-required-username":
        # A missing username is one syntax failure that dispatches nothing.
        usernames: list[str] = []
        monkeypatch.setattr(
            _CLI_MODULE,
            "run_administrative_password",
            lambda *, username: usernames.append(username) or commands.PasswordSetReport(),
        )
        with pytest.raises(SystemExit) as missing_username:
            _CLI_MODULE.main(["password"])
        assert missing_username.value.code != 0
        capsys.readouterr()
        assert usernames == []
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
        assert "hidden prompts" in captured.err
        return

    if case == "target-read-cli":
        # `target inference TARGET_ID` emits the owner read and delegates nothing else.
        target_read = _Sentinel("target-read")
        reads: list[str] = []
        monkeypatch.setattr(
            _CLI_MODULE,
            "read_inference_target_disposition",
            lambda target: reads.append(target) or target_read,
        )
        assert _CLI_MODULE.main(["target", "inference", "disp-target"]) == 0
        captured = capsys.readouterr()
        assert json.loads(captured.out)["label"] == "target-read"
        assert captured.err == ""
        with pytest.raises(SystemExit) as bad_read_kind:
            _CLI_MODULE.main(["target", "translation", "disp-target"])
        assert bad_read_kind.value.code != 0
        capsys.readouterr()
        assert reads == ["disp-target"]
        return

    if case == "target-read-safe-failure":
        # A safe target read failure prints only its class token and the disposition guidance.

        def failing_target_read(target):
            raise RuntimeError("target-read-payload-value")

        monkeypatch.setattr(_CLI_MODULE, "read_inference_target_disposition", failing_target_read)
        assert _CLI_MODULE.main(["target", "inference", "disp-target"]) == 1
        captured = capsys.readouterr()
        assert json.loads(captured.err.splitlines()[0]) == {"error": "RuntimeError"}
        assert "target-read-payload-value" not in captured.err
        assert "ordinary-stop all four stages" in captured.err
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
