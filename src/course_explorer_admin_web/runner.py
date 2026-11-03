"""The fixed-command runner of the administration backend.

A closed read table answers the routine server, dataset, coverage, summary and stage-status reads in
process through the same owning command functions the CLI uses, and passes them the caller's process
runner so their own service probes keep the same boundary. The dataset promotion is the one admitted
mutation that also runs in process: its owner is the only place that knows each coarse step, and an
observer supplies those steps to the console's streamed report without any subprocess streaming
machinery. Every other admitted command shape names one ``scripts/admin.py`` invocation, and this
module builds its exact argument list. The caller never supplies an executable, a script, a shell
fragment or an extra argument, so either path admits only the command shapes defined here. Every
execution appends one fixed-label entry to the sole command log before it returns, except a
successful automatic read, which appends none, and no command's captured streams or report are
persisted.

A command's own operation-specific guard stays with its owning service: the web layer validates the
shape of a parameter and never the course existence, stage idleness, dataset chain or selected
status.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal, cast
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    TypeAdapter,
    ValidationError,
    field_validator,
)

from course_explorer.administration import utc_now
from course_explorer.config import load_administrative_dataset_settings
from course_explorer.datasets import DatasetId, read_dataset_role
from course_explorer.validation import require_error_type, require_text
from course_explorer_admin import commands as administrative_commands
from course_explorer_admin.commands import format_operator_error
from course_explorer_admin.datasets import PromotionStep, admin_state_root
from course_explorer_admin.logs import LogSource
from course_explorer_admin.mechanics import ProcessRunner, SubprocessRunner
from course_explorer_admin_web.command_log import CommandLog, CommandLogEntry

# The fixed relative script every admitted command runs.
ADMIN_SCRIPT = Path("scripts") / "admin.py"


class ServerStatusCommand(BaseModel):
    """The fixed read-only server status command."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["server-status"]


class UsageCommand(BaseModel):
    """The fixed windowed usage report command, with its positive whole-hour window."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["usage"]
    hours: int = Field(gt=0, strict=True)


class FeedbackListInput(BaseModel):
    """One feedback listing's optional search text and select filters.

    The query and filter text are excluded from the rendered form, so a rendered command carries
    neither the search text nor a filter value.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    query: str | None = Field(default=None, repr=False)
    filters: dict[str, str] = Field(default_factory=dict, repr=False)

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str | None) -> str | None:
        """Require text without NUL characters while preserving the supplied query."""
        if value is not None and "\x00" in value:
            raise ValueError("feedback query must be text without NUL characters")
        return value

    @field_validator("filters")
    @classmethod
    def validate_filters(cls, value: dict[str, str]) -> dict[str, str]:
        """Require text field IDs and option values without NUL characters."""
        for field_id, option in value.items():
            if "\x00" in field_id or "\x00" in option:
                raise ValueError("feedback filters must not contain NUL characters")
        return value


class FeedbackListCommand(FeedbackListInput):
    """The fixed feedback listing command."""

    kind: Literal["feedback-list"]


class FeedbackAttachmentInput(BaseModel):
    """One transient attachment read, keyed by both stored identities."""

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    feedback_id: UUID
    attachment_id: UUID


class FeedbackAttachmentCommand(FeedbackAttachmentInput):
    """The fixed transient attachment read."""

    kind: Literal["feedback-attachment"]


class FeedbackDeleteInput(BaseModel):
    """The named feedback submission a deletion removes with its stored images."""

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    feedback_id: UUID


class FeedbackDeleteCommand(FeedbackDeleteInput):
    """The fixed deletion of one named feedback submission."""

    kind: Literal["feedback-delete"]


class StageCommand(BaseModel):
    """One stage lifecycle action over the fixed stage and action vocabularies."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["stage"]
    stage: Literal["ingestion", "translation", "embedding", "inference"]
    action: Literal["start", "pause", "resume", "status", "stop"]


class CoverageCommand(BaseModel):
    """The fixed narrow coverage report command."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["coverage"]
    report: Literal["teaching-text", "embedding", "inference"]


class SummaryCommand(BaseModel):
    """The fixed catalogue or inference summary command."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["summary"]
    report: Literal["catalogue", "inference"]


class ServingArtifactsCommand(BaseModel):
    """The fixed served-database serving-artifact build command."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["serving-artifacts"]


class TargetInput(BaseModel):
    """One canonical target identity with the shared external-input validation.

    A positional target must not read as an option, so a leading hyphen is refused here rather than
    reaching the command's own parser.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    target_id: str

    @field_validator("target_id")
    @classmethod
    def validate_target_id(cls, value: str) -> str:
        """Require one nonblank argument that cannot be taken as an option."""
        checked = require_text(value, "target id")
        if checked.startswith("-"):
            raise ValueError("target id must not start with a hyphen")
        return checked


class TargetReadCommand(TargetInput):
    """The fixed read-only target identity and decision command."""

    kind: Literal["target-read"]


class TargetDecisionInput(TargetInput):
    """One canonical target identity with the selected terminal decision token."""

    disposition: Literal["nothing", "done", "failed"]


class TargetDecisionCommand(TargetDecisionInput):
    """The fixed target decision command, which its owning service guards before it writes."""

    kind: Literal["target-decision"]


class DatasetListCommand(BaseModel):
    """The fixed receipt-bearing dataset listing command, whose request carries no argument."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["datasets-list"]


class DatasetDeleteInput(BaseModel):
    """One named dataset deletion and the explicit Working confirmation it may carry."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    dataset_id: DatasetId
    confirm_working: bool = Field(default=False, strict=True)


class DatasetDeleteCommand(DatasetDeleteInput):
    """The fixed single non-Selected dataset deletion command."""

    kind: Literal["datasets-delete"]


class DatasetCopyInput(BaseModel):
    """One source dataset identity for a copy operation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_dataset_id: DatasetId


class DatasetCopyCommand(DatasetCopyInput):
    """The fixed copy command that assigns its verified copy to Working."""

    kind: Literal["datasets-copy-to-working"]


class DatasetPromotionInput(DatasetCopyInput):
    """One source dataset identity and the serving-restart confirmation a promotion requires."""

    confirm_restart: bool = Field(default=False, strict=True)


class DatasetPromotionCommand(DatasetPromotionInput):
    """The fixed copy, build, switch, restart and serving-proof command."""

    kind: Literal["datasets-copy-to-selected"]


class DatasetMigrateInput(BaseModel):
    """One closed dataset role or the bootstrap configured database to migrate."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    role: Literal["selected", "working", "database"]


class DatasetMigrateCommand(DatasetMigrateInput):
    """The fixed explicit database migration command over its closed role vocabulary."""

    kind: Literal["datasets-migrate"]


class CommandLogCommand(BaseModel):
    """The fixed retained command-log read command, whose request carries no argument."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["command-log"]


class LogSessionsCommand(BaseModel):
    """The fixed log-session listing command, whose request carries no argument."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["log-sessions"]


class SessionLogInput(BaseModel):
    """One bounded log read: the session it names, its fixed source and its positive line count."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    stage: Literal["ingestion", "translation", "embedding", "inference"]
    session_id: DatasetId
    source: LogSource
    lines: int = Field(gt=0, strict=True)


class SessionLogCommand(SessionLogInput):
    """The fixed bounded session-log read command."""

    kind: Literal["session-log"]


class EmbeddingLogInput(BaseModel):
    """One embedding runtime log read with its positive line count."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    lines: int = Field(gt=0, strict=True)


class EmbeddingLogCommand(EmbeddingLogInput):
    """The fixed embedding runtime log read command."""

    kind: Literal["embedding-log"]


class ConfigReadInput(BaseModel):
    """One configuration file read over the name of a file the editor lists."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    file: str

    @field_validator("file")
    @classmethod
    def validate_file(cls, value: str) -> str:
        """Require one nonblank, NUL-free file name the editor itself resolves."""
        return require_text(value, "configuration file")


class ConfigReadCommand(ConfigReadInput):
    """The fixed configuration file read command."""

    kind: Literal["config-read"]


class ConfigSetInput(BaseModel):
    """One configuration key save: its file, its key and one JSON literal value.

    The value is the JSON literal the owning editor decodes, so this layer neither strips nor
    interprets it. The field is excluded from the model's rendered form.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    file: str
    key: str
    value: str = Field(repr=False)

    @field_validator("file")
    @classmethod
    def validate_file(cls, value: str) -> str:
        """Require one nonblank, NUL-free file name the editor itself resolves."""
        return require_text(value, "configuration file")

    @field_validator("key")
    @classmethod
    def validate_key(cls, value: str) -> str:
        """Require one nonblank, NUL-free configuration key."""
        return require_text(value, "configuration key")

    @field_validator("value")
    @classmethod
    def validate_value(cls, value: str) -> str:
        """Require one JSON literal string without NUL characters."""
        if not isinstance(value, str):
            raise ValueError("configuration value must be one JSON literal string")
        if "\x00" in value:
            raise ValueError("configuration value must not contain NUL characters")
        return value


class ConfigSetCommand(ConfigSetInput):
    """The fixed configuration key save command."""

    kind: Literal["config-set"]


class ConfigFilesCommand(BaseModel):
    """The fixed configuration file listing command, whose request carries no argument."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["config-files"]


class BackupListCommand(BaseModel):
    """The fixed backup-file listing command, whose request carries no argument."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["backups-list"]


class BackupDeleteInput(BaseModel):
    """One backup-file deletion over the relative name a listing reports."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        """Require one nonblank, NUL-free name the backup owner confines itself."""
        return require_text(value, "backup name")


class BackupDeleteCommand(BackupDeleteInput):
    """The fixed single backup-file deletion command."""

    kind: Literal["backups-delete"]


class RebuildCommand(BaseModel):
    """The fixed site rebuild command, whose request carries no argument."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["rebuild"]


class AdminRebuildCommand(BaseModel):
    """The fixed administration frontend build command, whose request carries no argument."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["rebuild-admin"]


class RestartAdminCommand(BaseModel):
    """The fixed administration restart command, whose request carries no argument."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["restart-admin"]


class DatasetSetupCommand(BaseModel):
    """The fixed Selected-dataset enrollment command, whose request carries no argument."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["datasets-setup"]


class WorkerSetupInput(BaseModel):
    """One worker setup or update over the origin branch it selects and its code-only choice."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    branch: str
    code_only: bool = Field(strict=True)

    @field_validator("branch")
    @classmethod
    def validate_branch(cls, value: str) -> str:
        """Require one nonblank, NUL-free branch name the provisioning owner validates."""
        return require_text(value, "worker branch")


class WorkerSetupCommand(WorkerSetupInput):
    """The fixed worker setup or update command."""

    kind: Literal["worker-setup"]


class WorkerPreflightCommand(BaseModel):
    """The fixed read-only worker preflight command, whose request carries no argument."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["worker-preflight"]


# Every command shape the runner admits, keyed by its own fixed kind.
FixedCommand = Annotated[
    ServerStatusCommand
    | UsageCommand
    | FeedbackListCommand
    | FeedbackAttachmentCommand
    | FeedbackDeleteCommand
    | StageCommand
    | CoverageCommand
    | SummaryCommand
    | ServingArtifactsCommand
    | TargetReadCommand
    | TargetDecisionCommand
    | DatasetListCommand
    | DatasetDeleteCommand
    | DatasetCopyCommand
    | DatasetPromotionCommand
    | CommandLogCommand
    | LogSessionsCommand
    | SessionLogCommand
    | EmbeddingLogCommand
    | ConfigFilesCommand
    | ConfigReadCommand
    | ConfigSetCommand
    | BackupListCommand
    | BackupDeleteCommand
    | RebuildCommand
    | AdminRebuildCommand
    | RestartAdminCommand
    | DatasetSetupCommand
    | DatasetMigrateCommand
    | WorkerSetupCommand
    | WorkerPreflightCommand,
    Field(discriminator="kind"),
]

_FIXED_COMMAND_ADAPTER = TypeAdapter(FixedCommand)


def _read_server_status(_request: FixedCommand, runner: ProcessRunner) -> BaseModel:
    """Return the server status through its owning read."""
    return administrative_commands.run_administrative_server_status(runner=runner)


def _read_dataset_list(_request: FixedCommand, runner: ProcessRunner) -> BaseModel:
    """Return the retained dataset listing through its owning read."""
    return administrative_commands.run_administrative_dataset_list(runner=runner)


def _report_role() -> Literal["selected", "working"] | None:
    """Return Working when it exists, else Selected, else None for a bootstrap state."""
    root = admin_state_root(load_administrative_dataset_settings())
    if read_dataset_role(root, "working") is not None:
        return "working"
    if read_dataset_role(root, "selected") is not None:
        return "selected"
    return None


def _read_coverage(request: FixedCommand, _runner: ProcessRunner) -> BaseModel:
    """Return the named coverage report for the role the console reads."""
    kind = cast(CoverageCommand, request).report
    role = _report_role()
    if role is None:
        return ReportScope(role=None, report=None)
    report = administrative_commands.run_administrative_coverage(kind, role=role)
    return ReportScope(role=role, report=report.model_dump(mode="json"))


def _read_summary(request: FixedCommand, _runner: ProcessRunner) -> BaseModel:
    """Return the named summary report for the role the console reads."""
    kind = cast(SummaryCommand, request).report
    role = _report_role()
    if role is None:
        return ReportScope(role=None, report=None)
    report = administrative_commands.run_administrative_summary(kind, role=role)
    return ReportScope(role=role, report=report.model_dump(mode="json"))


def _read_stage_status(request: FixedCommand, _runner: ProcessRunner) -> BaseModel:
    """Return one stage's status through its owning lifecycle read."""
    return administrative_commands.run_administrative_command(
        cast(StageCommand, request).stage, "status"
    )


# The closed read table: a validated kind and action dispatch to the function that owns the read.
_IN_PROCESS_READS: dict[
    tuple[str, str | None], Callable[[FixedCommand, ProcessRunner], BaseModel]
] = {
    ("server-status", None): _read_server_status,
    ("datasets-list", None): _read_dataset_list,
    ("coverage", None): _read_coverage,
    ("summary", None): _read_summary,
    ("stage", "status"): _read_stage_status,
}


def _read_key(request: FixedCommand) -> tuple[str, str | None]:
    """Return the closed read-table key of one admitted command."""
    if isinstance(request, StageCommand):
        return (request.kind, request.action)
    return (request.kind, None)


class ReportScope(BaseModel):
    """One role-resolved console report. A bootstrap state carries no role and no report."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    role: Literal["selected", "working"] | None
    report: dict[str, JsonValue] | None


class CommandResult(BaseModel):
    """One transient command outcome: its exit code, its decoded report and its failure text.

    The report is the command's own decoded JSON object and is never written to the log or kept. The
    failure line names an exception class and an optional checked-process return code alone. The
    guidance line is the owning command operation's fixed advice for the operator, and it lives only
    in this response.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    exit_code: int
    report: dict[str, JsonValue] | None
    failure_line: str | None
    guidance_line: str | None = None


class FixedCommandRunner:
    """Run one admitted fixed command over the shared administrative process boundary.

    The runner revalidates the command against the discriminated union before it executes anything,
    so a mapping or an arbitrary object a caller assembles cannot become a command.
    """

    def __init__(self, root: Path, log: CommandLog, *, runner: ProcessRunner | None = None) -> None:
        self._root = root
        self._log = log
        self._runner = runner if runner is not None else SubprocessRunner()

    def run(
        self,
        command: FixedCommand,
        *,
        automatic: bool = False,
        on_progress: Callable[[PromotionStep], None] | None = None,
    ) -> CommandResult:
        """Run one admitted command once and record its outcome.

        The command's UTC start time and its monotonic start are captured before it executes, and
        that start time is the recorded entry time. A checked non-zero exit becomes its own integer
        status and the child's own safe failure line when its first stderr line is one, or the
        wrapper's content-free class line otherwise. Any other failure of execution, decoding or
        report assembly becomes status 1 and one content-free class line. No branch returns a
        captured stream or an exception message. A log write failure propagates instead of reporting
        a successful command.

        The dataset promotion is the one admitted command that runs in process rather than as a
        subprocess, because its owner reports each coarse step before that step's mutation.
        ``on_progress`` receives those steps and changes nothing else. Every other admitted command
        keeps its own execution path.

        A failed outcome carries the owning command operation's fixed guidance line in its transient
        result. That line is response data alone and never reaches the command log.

        ``automatic`` marks one read the console repeats on its own timer. A successful automatic
        read appends no entry, while a failed one records like any other outcome. The flag selects
        no argv and changes no admission: the calling route alone decides which commands are reads.
        """
        request = _FIXED_COMMAND_ADAPTER.validate_python(command)
        reader = _IN_PROCESS_READS.get(_read_key(request))
        started_at = utc_now()
        started = time.monotonic()
        try:
            if isinstance(request, DatasetPromotionCommand):
                result = CommandResult(
                    exit_code=0,
                    report=administrative_commands.run_administrative_dataset_promotion(
                        request.source_dataset_id,
                        confirm_restart=request.confirm_restart,
                        on_progress=on_progress,
                        runner=self._runner,
                    ).model_dump(mode="json"),
                    failure_line=None,
                )
            elif reader is not None:
                result = CommandResult(
                    exit_code=0,
                    report=reader(request, self._runner).model_dump(mode="json"),
                    failure_line=None,
                )
            else:
                completed = self._runner.run(self._argv(request), cwd=self._root)
                result = CommandResult(
                    exit_code=completed.returncode,
                    report=_decode_report(completed.stdout),
                    failure_line=None,
                )
        except subprocess.CalledProcessError as exc:
            result = CommandResult(
                exit_code=exc.returncode,
                report=None,
                failure_line=_checked_failure_line(exc),
                guidance_line=administrative_commands.operator_guidance(
                    _guidance_operation(request),
                    configuration_error=isinstance(exc, ValidationError),
                ),
            )
        except Exception as exc:
            result = CommandResult(
                exit_code=1,
                report=None,
                failure_line=format_operator_error(exc),
                guidance_line=administrative_commands.operator_guidance(
                    _guidance_operation(request),
                    configuration_error=isinstance(exc, ValidationError),
                ),
            )
        if not (automatic and result.exit_code == 0 and result.failure_line is None):
            self._record(
                _command_label(request),
                started_at=started_at,
                duration=time.monotonic() - started,
                result=result,
            )
        return result

    def _argv(self, request: FixedCommand) -> tuple[str, ...]:
        """Return the exact argument list of one admitted command.

        Every admitted kind that runs as a subprocess has its own branch, and the function holds no
        other argument source, so an argument list cannot be assembled for a command the union does
        not admit. The `server-status`, `datasets-list`, `coverage` and `summary` reads, `stage
        status` and the in-process `datasets-copy-to-selected` promotion do not reach this function.
        """
        prefix = (sys.executable, str(self._root / ADMIN_SCRIPT))
        match request.kind:
            case "usage":
                return (*prefix, "usage", "--hours", str(request.hours))
            case "feedback-list":
                argv = (*prefix, "feedback", "list")
                if request.query is not None:
                    argv = (*argv, f"--query={request.query}")
                return (*argv, f"--filters={json.dumps(request.filters)}")
            case "feedback-attachment":
                return (
                    *prefix,
                    "feedback",
                    "attachment",
                    str(request.feedback_id),
                    str(request.attachment_id),
                )
            case "feedback-delete":
                return (*prefix, "feedback", "delete", str(request.feedback_id))
            case "stage":
                return (*prefix, request.stage, request.action)
            case "serving-artifacts":
                return (*prefix, "serving-artifacts")
            case "target-read":
                return (*prefix, "target", "inference", request.target_id)
            case "target-decision":
                return (*prefix, "dispose", "inference", request.target_id, request.disposition)
            case "datasets-delete":
                argv = (*prefix, "datasets", "delete", request.dataset_id)
                return (*argv, "--confirm-working") if request.confirm_working else argv
            case "datasets-copy-to-working":
                return (*prefix, "datasets", "copy-to-working", request.source_dataset_id)
            case "command-log":
                return (*prefix, "logs", "commands")
            case "log-sessions":
                return (*prefix, "logs", "sessions")
            case "session-log":
                return (
                    *prefix,
                    "logs",
                    "read",
                    request.stage,
                    request.session_id,
                    request.source,
                    "--lines",
                    str(request.lines),
                )
            case "embedding-log":
                return (*prefix, "logs", "embedding", "--lines", str(request.lines))
            case "config-files":
                return (*prefix, "config", "list")
            case "config-read":
                return (*prefix, "config", "read", "--", request.file)
            case "config-set":
                return (*prefix, "config", "set", "--", request.file, request.key, request.value)
            case "backups-list":
                return (*prefix, "backups", "list")
            case "backups-delete":
                return (*prefix, "backups", "delete", "--", request.name)
            case "rebuild":
                return (*prefix, "rebuild")
            case "rebuild-admin":
                return (*prefix, "rebuild-admin")
            case "restart-admin":
                return (*prefix, "restart-admin")
            case "datasets-setup":
                return (*prefix, "setup", "datasets")
            case "datasets-migrate":
                return (*prefix, "migrate", request.role)
            case "worker-setup":
                argv = (*prefix, "setup", "worker", f"--branch={request.branch}")
                return (*argv, "--code-only") if request.code_only else argv
            case "worker-preflight":
                return (*prefix, "preflight")
        raise ValueError(f"command kind {request.kind} carries no process argument list")

    def _record(
        self,
        label: str,
        *,
        started_at: datetime,
        duration: float,
        result: CommandResult,
    ) -> None:
        """Append one fixed-label entry for one command outcome.

        The entry carries the fixed command label, the outcome's exit code and safe failure line,
        the command's start time, the elapsed monotonic duration and the outcome token the failure
        line selects.
        """
        self._log.append(
            CommandLogEntry(
                time=started_at,
                command=label,
                exit_code=result.exit_code,
                duration_seconds=duration,
                result="success" if result.failure_line is None else "failure",
                failure_line=result.failure_line,
            )
        )


def _guidance_operation(request: FixedCommand) -> str:
    """Return the operator operation whose fixed guidance explains one command failure."""
    match request.kind:
        case "server-status":
            return "server"
        case "datasets-list":
            return "dataset-list"
        case "coverage" | "summary":
            return "report"
        case "stage":
            return "stage"
        case "serving-artifacts":
            return "serving-artifacts"
        case "target-read":
            return "target-read"
        case "target-decision":
            return "disposition"
        case "datasets-setup" | "worker-setup":
            return "setup"
        case "datasets-migrate":
            return "migration"
        case "datasets-delete":
            return "dataset-cleanup"
        case "datasets-copy-to-working":
            return "dataset-copy"
        case "datasets-copy-to-selected":
            return "dataset-promotion"
        case "backups-list":
            return "backup-list"
        case "backups-delete":
            return "backup-cleanup"
        case "config-files" | "config-read" | "config-set":
            return "configuration"
        case "command-log" | "log-sessions" | "session-log" | "embedding-log":
            return "logs"
        case "rebuild" | "rebuild-admin" | "restart-admin":
            return "rebuild"
        case "usage":
            return "usage"
        case "feedback-list" | "feedback-attachment" | "feedback-delete":
            return "feedback"
        case "worker-preflight":
            return "preflight"


def _command_label(request: FixedCommand) -> str:
    """Return the one fixed log label of an admitted command.

    The label is a fixed literal or a closed vocabulary combination chosen from source text alone,
    so no target id, dataset id, disposition argument, window, report payload or credential can
    reach the log. Every admitted kind has its own branch.
    """
    match request.kind:
        case "server-status":
            return "server status"
        case "usage":
            return "usage"
        case "feedback-list":
            return "feedback list"
        case "feedback-attachment":
            return "feedback attachment"
        case "feedback-delete":
            return "feedback delete"
        case "stage":
            return f"{request.stage} {request.action}"
        case "coverage":
            return f"coverage {request.report}"
        case "summary":
            return f"summary {request.report}"
        case "serving-artifacts":
            return "serving artifacts"
        case "target-read":
            return "target inference"
        case "target-decision":
            return "dispose inference"
        case "datasets-list":
            return "datasets list"
        case "datasets-delete":
            return "datasets delete"
        case "datasets-copy-to-working":
            return "datasets copy-to-working"
        case "datasets-copy-to-selected":
            return "datasets copy-to-selected"
        case "command-log":
            return "logs commands"
        case "log-sessions":
            return "logs sessions"
        case "session-log":
            return "logs read"
        case "embedding-log":
            return "logs embedding"
        case "config-files":
            return "config list"
        case "config-read":
            return "config read"
        case "config-set":
            return "config set"
        case "backups-list":
            return "backups list"
        case "backups-delete":
            return "backups delete"
        case "rebuild":
            return "rebuild"
        case "rebuild-admin":
            return "rebuild-admin"
        case "restart-admin":
            return "restart-admin"
        case "datasets-setup":
            return "setup datasets"
        case "datasets-migrate":
            return f"migrate {request.role}"
        case "worker-setup":
            return "setup worker"
        case "worker-preflight":
            return "preflight"


def _decode_report(stdout: bytes) -> dict[str, JsonValue]:
    """Decode one command's captured stdout as the single JSON object it reports."""
    try:
        decoded = json.loads(stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("administration command did not report one JSON object") from exc
    if not isinstance(decoded, dict):
        raise ValueError("administration command did not report one JSON object")
    return decoded


def _checked_failure_line(exc: subprocess.CalledProcessError) -> str:
    """Return the child's own safe failure line, or the wrapper's class line when it carries none.

    Only the first physical stderr line is read. It must be one JSON object holding an ``error``
    identifier and an optional integer ``returncode``, and the returned line is rebuilt from those
    two fields alone. An absent, undecodable, malformed, extra-field or invalid value returns
    ``format_operator_error(exc)``, so no message, traceback or later guidance reaches a response or
    the command log.
    """
    fallback = format_operator_error(exc)
    stderr = exc.stderr
    if isinstance(stderr, bytes):
        try:
            text = stderr.decode("utf-8")
        except UnicodeDecodeError:
            return fallback
    elif isinstance(stderr, str):
        text = stderr
    else:
        return fallback
    lines = text.splitlines()
    if not lines:
        return fallback
    try:
        payload = json.loads(lines[0])
    except json.JSONDecodeError:
        return fallback
    if not isinstance(payload, dict) or not set(payload) <= {"error", "returncode"}:
        return fallback
    if "error" not in payload:
        return fallback
    try:
        error = require_error_type(payload["error"], max_length=64)
    except ValueError:
        return fallback
    safe: dict[str, object] = {"error": error}
    if "returncode" in payload:
        returncode = payload["returncode"]
        if isinstance(returncode, bool) or not isinstance(returncode, int):
            return fallback
        safe["returncode"] = returncode
    return json.dumps(safe, separators=(",", ":"))
