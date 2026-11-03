"""One administrative CLI dispatcher over the engine-owned operator commands.

This module holds the one command parser, JSON emission and safe-error presentation shared by every
administrative entry script. It parses one command and delegates exactly once to
``course_explorer_admin.commands``. A caller may supply its own stage and summary callables so a
wrapper can inject an additional explicit route without a second parser or duplicated dispatch.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ValidationError

from course_explorer.config import ConfiguredSettings
from course_explorer.feedback.service import parse_feedback_filters
from course_explorer_admin.commands import (
    REPORT_SCOPE,
    ExampleSetupInput,
    RealDatabaseSetupInput,
    format_operator_error,
    operator_guidance,
    read_inference_target_disposition,
    run_administrative_admin_rebuild,
    run_administrative_backup_delete,
    run_administrative_backup_list,
    run_administrative_command,
    run_administrative_command_log,
    run_administrative_config_list,
    run_administrative_config_read,
    run_administrative_config_set,
    run_administrative_coverage,
    run_administrative_database_migration,
    run_administrative_dataset_copy,
    run_administrative_dataset_delete,
    run_administrative_dataset_ensure,
    run_administrative_dataset_list,
    run_administrative_dataset_promotion,
    run_administrative_embedding_log,
    run_administrative_example_setup,
    run_administrative_feedback_attachment,
    run_administrative_feedback_delete,
    run_administrative_feedback_list,
    run_administrative_log_sessions,
    run_administrative_migration,
    run_administrative_password,
    run_administrative_preflight,
    run_administrative_real_database_setup,
    run_administrative_rebuild,
    run_administrative_restart_admin,
    run_administrative_server_status,
    run_administrative_serving_artifacts,
    run_administrative_session_log,
    run_administrative_setup,
    run_administrative_summary,
    run_administrative_usage,
    run_operator_menu,
    set_inference_target_disposition,
    worker_origin_notice,
)
from course_explorer_admin.logs import LOG_SOURCES

_STAGES = ("ingestion", "translation", "embedding", "inference")
_ACTIONS = ("start", "pause", "resume", "status", "stop")

type StageCommand = Callable[..., BaseModel]
type SummaryCommand = Callable[..., BaseModel]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="admin.py", description=__doc__)
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("menu", help="run the interactive operator menu")
    setup = subparsers.add_parser("setup", help="enroll the selected dataset or prepare the worker")
    setup.add_argument("kind", choices=["datasets", "worker"])
    setup.add_argument("--branch", default="main")
    setup.add_argument("--code-only", action="store_true")
    self_host = subparsers.add_parser(
        "self-host", help="run one self-host setup workflow from non-interactive JSON input"
    )
    self_host.add_argument("verb", choices=["example", "real-database"])
    subparsers.add_parser("preflight", help="read-only worker readiness check")
    migrate = subparsers.add_parser("migrate", help="explicit database maintenance")
    migrate.add_argument("kind", choices=["selected", "working", "database"])
    datasets = subparsers.add_parser(
        "datasets", help="list, copy, enroll or delete one receipt-bearing dataset"
    )
    dataset_verbs = datasets.add_subparsers(dest="cleanup_command", required=True)
    dataset_verbs.add_parser("list", help="list every receipt-bearing dataset with its role")
    dataset_delete = dataset_verbs.add_parser(
        "delete", help="delete one receipt-bearing dataset other than Selected"
    )
    dataset_delete.add_argument("dataset_id")
    dataset_delete.add_argument(
        "--confirm-working",
        action="store_true",
        help="confirm deletion of the Working dataset; every stage must be idle",
    )
    dataset_copy = dataset_verbs.add_parser(
        "copy-to-working", help="copy one dataset and assign the copy to Working"
    )
    dataset_copy.add_argument("source_dataset_id")
    dataset_promotion = dataset_verbs.add_parser(
        "copy-to-selected",
        help=(
            "copy one dataset, build it, switch Selected and restart serving; "
            "the site is briefly unavailable"
        ),
    )
    dataset_promotion.add_argument("source_dataset_id")
    dataset_promotion.add_argument(
        "--confirm-restart",
        action="store_true",
        help="confirm the serving restart; without it nothing is copied or changed",
    )
    dataset_verbs.add_parser(
        "ensure-selected",
        help="enroll the configured database as Selected unless it is the example",
    )
    backups = subparsers.add_parser(
        "backups", help="list the backup files or delete one listed backup file"
    )
    backup_verbs = backups.add_subparsers(dest="cleanup_command", required=True)
    backup_verbs.add_parser("list", help="list the regular files under data/backups")
    backup_delete = backup_verbs.add_parser("delete", help="delete one listed backup file")
    backup_delete.add_argument("name")
    config = subparsers.add_parser("config", help="list, read or set one configuration file key")
    config_verbs = config.add_subparsers(dest="configuration_command", required=True)
    config_verbs.add_parser("list", help="list the editable configuration files")
    config_read = config_verbs.add_parser("read", help="read every key of one configuration file")
    config_read.add_argument("file")
    config_set = config_verbs.add_parser("set", help="save one key of one configuration file")
    config_set.add_argument("file")
    config_set.add_argument("key")
    config_set.add_argument("value")
    password = subparsers.add_parser(
        "password", help="store one administration account's password over the terminal"
    )
    password.add_argument("--username", required=True)
    server = subparsers.add_parser("server", help="read the server status report")
    server_verbs = server.add_subparsers(dest="server_command", required=True)
    server_verbs.add_parser("status", help="read the server status report")
    logs = subparsers.add_parser("logs", help="list the log sessions or read one bounded log")
    log_verbs = logs.add_subparsers(dest="log_command", required=True)
    log_verbs.add_parser("sessions", help="list the discovered log sessions")
    log_verbs.add_parser("commands", help="read the retained administration command log")
    log_read = log_verbs.add_parser("read", help="read the last lines of one fixed log source")
    log_read.add_argument("stage", choices=list(_STAGES))
    log_read.add_argument("session_id")
    log_read.add_argument("source", choices=list(LOG_SOURCES))
    log_read.add_argument("--lines", type=int, required=True)
    log_embedding = log_verbs.add_parser("embedding", help="read the embedding container log")
    log_embedding.add_argument("--lines", type=int, required=True)
    feedback = subparsers.add_parser(
        "feedback", help="list, read one attachment of, or delete a feedback submission"
    )
    feedback_verbs = feedback.add_subparsers(dest="feedback_command", required=True)
    feedback_list = feedback_verbs.add_parser("list", help="list stored feedback submissions")
    feedback_list.add_argument("--query")
    feedback_list.add_argument("--filters", default="{}")
    feedback_attachment = feedback_verbs.add_parser(
        "attachment", help="read one stored attachment transiently"
    )
    feedback_attachment.add_argument("feedback_id")
    feedback_attachment.add_argument("attachment_id")
    feedback_delete = feedback_verbs.add_parser(
        "delete", help="delete one named feedback submission and its stored images"
    )
    feedback_delete.add_argument("feedback_id")
    usage = subparsers.add_parser(
        "usage", help="read the windowed request usage report and prune past retention"
    )
    usage.add_argument("--hours", type=int, required=True)
    subparsers.add_parser("rebuild", help="rebuild the frontend, containers and web server")
    subparsers.add_parser("rebuild-admin", help="build the administration frontend alone")
    subparsers.add_parser("restart-admin", help="queue this checkout's administration restart")
    dispose = subparsers.add_parser(
        "dispose", help="set one canonical inference target's operator decision"
    )
    dispose.add_argument("kind", choices=["inference"])
    dispose.add_argument("target_id")
    dispose.add_argument("disposition", choices=["nothing", "done", "failed"])
    target = subparsers.add_parser(
        "target", help="read one canonical inference target's identity and decision"
    )
    target.add_argument("kind", choices=["inference"])
    target.add_argument("target_id")
    for stage in _STAGES:
        stage_parser = subparsers.add_parser(stage, help=f"{stage} tool lifecycle")
        stage_parser.add_argument("action", choices=_ACTIONS)
    coverage = subparsers.add_parser("coverage", help="narrow coverage report for one dataset role")
    coverage.add_argument("kind", choices=["teaching-text", "embedding", "inference"])
    coverage.add_argument("--role", choices=["selected", "working"], required=True)
    serving_artifacts = subparsers.add_parser(
        "serving-artifacts",
        help="build one dataset's serving artifacts and switch its current build",
    )
    serving_artifacts.add_argument(
        "--dataset", help="target an in-pipeline dataset id; default is the selected dataset"
    )
    serving_artifacts.add_argument(
        "--prune",
        action="store_true",
        help="after a restart, remove obsolete builds and owned temporary outputs only",
    )
    summary = subparsers.add_parser("summary", help="catalogue or inference summary for one role")
    summary.add_argument("kind", choices=["catalogue", "inference"])
    summary.add_argument("--role", choices=["selected", "working"], required=True)
    return parser


def _emit(report: object) -> None:
    """Print one DTO to stdout and any fixed origin notice to stderr."""
    print(report.model_dump_json())  # type: ignore[attr-defined]
    notice = worker_origin_notice(report)
    if notice is not None:
        print(notice, file=sys.stderr)


def _progress(line: str) -> None:
    """Write one fixed workflow step name to the error stream."""
    print(line, file=sys.stderr)


def _fail(
    exc: Exception,
    operation: Literal[
        "setup",
        "preflight",
        "stage",
        "report",
        "migration",
        "disposition",
        "target-read",
        "serving-artifacts",
        "dataset-cleanup",
        "dataset-copy",
        "dataset-list",
        "dataset-promotion",
        "backup-list",
        "backup-cleanup",
        "configuration",
        "server",
        "logs",
        "rebuild",
        "usage",
        "password",
        "feedback",
        "self-host-example",
        "self-host-real-database",
    ],
) -> None:
    print(format_operator_error(exc), file=sys.stderr)
    print(
        operator_guidance(operation, configuration_error=isinstance(exc, ValidationError)),
        file=sys.stderr,
    )


def main(
    argv: Sequence[str] | None = None,
    *,
    run_command: StageCommand | None = None,
    run_summary: SummaryCommand | None = None,
    configuration_families: tuple[type[ConfiguredSettings], ...] = (),
) -> int:
    """Parse one command and delegate once. Return 0 on success, 1 on failure, 130 on interrupt.

    An absent stage or summary callback resolves to the base command. A supplied callback
    replaces that one call only, so a wrapper can inject an extra route without owning dispatch.
    ``configuration_families`` reach the configuration save and the menu's configuration entry
    alone, so a wrapper can add the validation families of a package the base product does not
    import.
    """
    args = _parser().parse_args(argv)
    if args.command is None or args.command == "menu":
        return run_operator_menu(
            run_command=run_command,
            run_summary=run_summary,
            configuration_families=configuration_families,
        )
    stage_command = run_command or run_administrative_command
    summary_command = run_summary or run_administrative_summary
    try:
        if args.command == "self-host":
            if sys.stdin.isatty():
                raise ValueError(
                    "self-host reads one JSON input object from non-interactive stdin; "
                    "use the operator menu instead"
                )
            payload = sys.stdin.read()
            if args.verb == "example":
                example = ExampleSetupInput.model_validate_json(payload)
                report = run_administrative_example_setup(example, write=_progress)
            else:
                real = RealDatabaseSetupInput.model_validate_json(payload)
                report = run_administrative_real_database_setup(real, write=_progress)
            _emit(report)
            return 0
        if args.command == "setup":
            report = run_administrative_setup(
                args.kind, branch=args.branch, code_only=args.code_only
            )
            _emit(report)
            return 0
        if args.command == "preflight":
            report = run_administrative_preflight()
            _emit(report)
            if report.resources is None or not report.resources.ready:
                return 1
            return 0
        if args.command == "migrate":
            if args.kind == "database":
                _emit(run_administrative_database_migration())
            else:
                _emit(run_administrative_migration(role=args.kind))
            return 0
        if args.command == "datasets":
            if args.cleanup_command == "list":
                _emit(run_administrative_dataset_list())
            elif args.cleanup_command == "copy-to-working":
                _emit(run_administrative_dataset_copy(args.source_dataset_id))
            elif args.cleanup_command == "copy-to-selected":
                _emit(
                    run_administrative_dataset_promotion(
                        args.source_dataset_id, confirm_restart=args.confirm_restart
                    )
                )
            elif args.cleanup_command == "ensure-selected":
                _emit(run_administrative_dataset_ensure())
            else:
                _emit(
                    run_administrative_dataset_delete(
                        args.dataset_id, confirm_working=args.confirm_working
                    )
                )
            return 0
        if args.command == "backups":
            if args.cleanup_command == "list":
                _emit(run_administrative_backup_list())
            else:
                _emit(run_administrative_backup_delete(args.name))
            return 0
        if args.command == "config":
            if args.configuration_command == "list":
                _emit(run_administrative_config_list())
            elif args.configuration_command == "read":
                _emit(run_administrative_config_read(args.file))
            else:
                _emit(
                    run_administrative_config_set(
                        args.file,
                        args.key,
                        args.value,
                        settings_families=configuration_families,
                    )
                )
            return 0
        if args.command == "server":
            _emit(run_administrative_server_status())
            return 0
        if args.command == "password":
            _emit(run_administrative_password(username=args.username))
            return 0
        if args.command == "logs":
            if args.log_command == "sessions":
                _emit(run_administrative_log_sessions())
            elif args.log_command == "commands":
                _emit(run_administrative_command_log())
            elif args.log_command == "read":
                _emit(
                    run_administrative_session_log(
                        args.stage, args.session_id, args.source, lines=args.lines
                    )
                )
            else:
                _emit(run_administrative_embedding_log(lines=args.lines))
            return 0
        if args.command == "rebuild":
            _emit(run_administrative_rebuild())
            return 0
        if args.command == "rebuild-admin":
            _emit(run_administrative_admin_rebuild())
            return 0
        if args.command == "restart-admin":
            _emit(run_administrative_restart_admin())
            return 0
        if args.command == "usage":
            _emit(run_administrative_usage(hours=args.hours))
            return 0
        if args.command == "feedback":
            if args.feedback_command == "list":
                _emit(
                    run_administrative_feedback_list(
                        query=args.query,
                        filters=parse_feedback_filters(args.filters),
                    )
                )
            elif args.feedback_command == "attachment":
                _emit(
                    run_administrative_feedback_attachment(
                        UUID(args.feedback_id), UUID(args.attachment_id)
                    )
                )
            else:
                _emit(run_administrative_feedback_delete(UUID(args.feedback_id)))
            return 0
        if args.command == "dispose":
            disposition = None if args.disposition == "nothing" else args.disposition
            _emit(set_inference_target_disposition(args.target_id, disposition))
            return 0
        if args.command == "target":
            _emit(read_inference_target_disposition(args.target_id))
            return 0
        if args.command == "serving-artifacts":
            _emit(run_administrative_serving_artifacts(args.dataset, prune=args.prune))
            return 0
        if args.command in _STAGES:
            _emit(stage_command(args.command, args.action))
            return 0
        if args.command == "coverage":
            _emit(run_administrative_coverage(args.kind, role=args.role))
            print(REPORT_SCOPE, file=sys.stderr)
            return 0
        _emit(summary_command(args.kind, role=args.role))
        print(REPORT_SCOPE, file=sys.stderr)
        return 0
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        operation = (
            "setup"
            if args.command == "setup"
            else "self-host-example"
            if args.command == "self-host" and args.verb == "example"
            else "self-host-real-database"
            if args.command == "self-host"
            else "preflight"
            if args.command == "preflight"
            else "migration"
            if args.command == "migrate"
            else "disposition"
            if args.command == "dispose"
            else "target-read"
            if args.command == "target"
            else "serving-artifacts"
            if args.command == "serving-artifacts"
            else "dataset-promotion"
            if args.command == "datasets" and args.cleanup_command == "copy-to-selected"
            else "dataset-copy"
            if args.command == "datasets" and args.cleanup_command == "copy-to-working"
            else "dataset-list"
            if args.command == "datasets" and args.cleanup_command == "list"
            else "dataset-cleanup"
            if args.command == "datasets"
            else "backup-list"
            if args.command == "backups" and args.cleanup_command == "list"
            else "backup-cleanup"
            if args.command == "backups"
            else "configuration"
            if args.command == "config"
            else "server"
            if args.command == "server"
            else "logs"
            if args.command == "logs"
            else "rebuild"
            if args.command in {"rebuild", "rebuild-admin", "restart-admin"}
            else "usage"
            if args.command == "usage"
            else "feedback"
            if args.command == "feedback"
            else "password"
            if args.command == "password"
            else "report"
            if args.command in {"coverage", "summary"}
            else "stage"
        )
        _fail(exc, operation)
        return 1
