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

from pydantic import BaseModel, ValidationError

from course_explorer_admin.commands import (
    REPORT_SCOPE,
    format_operator_error,
    operator_guidance,
    run_administrative_command,
    run_administrative_coverage,
    run_administrative_migration,
    run_administrative_preflight,
    run_administrative_setup,
    run_administrative_summary,
    run_operator_menu,
    set_inference_target_disposition,
    worker_origin_notice,
)

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
    subparsers.add_parser("preflight", help="read-only worker readiness check")
    migrate = subparsers.add_parser("migrate", help="explicit selected-dataset maintenance")
    migrate.add_argument("kind", choices=["datasets"])
    dispose = subparsers.add_parser(
        "dispose", help="set one canonical inference target's operator decision"
    )
    dispose.add_argument("kind", choices=["inference"])
    dispose.add_argument("target_id")
    dispose.add_argument("disposition", choices=["nothing", "done", "failed"])
    for stage in _STAGES:
        stage_parser = subparsers.add_parser(stage, help=f"{stage} tool lifecycle")
        stage_parser.add_argument("action", choices=_ACTIONS)
    coverage = subparsers.add_parser("coverage", help="narrow server coverage report")
    coverage.add_argument("kind", choices=["teaching-text", "embedding", "inference"])
    summary = subparsers.add_parser("summary", help="server catalogue or inference summary")
    summary.add_argument("kind", choices=["catalogue", "inference"])
    return parser


def _emit(report: object) -> None:
    """Print one DTO to stdout and any fixed origin notice to stderr."""
    print(report.model_dump_json())  # type: ignore[attr-defined]
    notice = worker_origin_notice(report)
    if notice is not None:
        print(notice, file=sys.stderr)


def _fail(
    exc: Exception,
    operation: Literal["setup", "preflight", "stage", "report", "migration", "disposition"],
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
) -> int:
    """Parse one command and delegate once. Return 0 on success, 1 on failure, 130 on interrupt.

    An absent stage or summary callback resolves to the base command. A supplied callback
    replaces that one call only, so a wrapper can inject an extra route without owning dispatch.
    """
    args = _parser().parse_args(argv)
    if args.command is None or args.command == "menu":
        return run_operator_menu(run_command=run_command, run_summary=run_summary)
    stage_command = run_command or run_administrative_command
    summary_command = run_summary or run_administrative_summary
    try:
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
            _emit(run_administrative_migration())
            return 0
        if args.command == "dispose":
            disposition = None if args.disposition == "nothing" else args.disposition
            _emit(set_inference_target_disposition(args.target_id, disposition))
            return 0
        if args.command in _STAGES:
            _emit(stage_command(args.command, args.action))
            return 0
        if args.command == "coverage":
            _emit(run_administrative_coverage(args.kind))
            print(REPORT_SCOPE, file=sys.stderr)
            return 0
        _emit(summary_command(args.kind))
        print(REPORT_SCOPE, file=sys.stderr)
        return 0
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        operation = (
            "setup"
            if args.command == "setup"
            else "preflight"
            if args.command == "preflight"
            else "migration"
            if args.command == "migrate"
            else "disposition"
            if args.command == "dispose"
            else "report"
            if args.command in {"coverage", "summary"}
            else "stage"
        )
        _fail(exc, operation)
        return 1
