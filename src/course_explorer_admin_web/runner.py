"""The fixed-command subprocess runner of the administration backend.

Each admitted command shape names one ``scripts/admin.py`` invocation, and this module builds its
exact argument list. The caller never supplies an executable, a script, a shell fragment or an extra
argument, so the process boundary admits only the command shapes defined here. Every execution
appends one fixed-label entry to the sole command log before it returns, except a successful
automatic read, which appends none, and no command's captured streams or report are persisted.

A command's own operation-specific guard stays with its owning service: the web layer validates the
shape of a parameter and never the course existence, stage idleness, dataset chain or selected
status.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, TypeAdapter, field_validator

from course_explorer.administration import utc_now
from course_explorer.datasets import DatasetId
from course_explorer.validation import require_error_type, require_text
from course_explorer_admin.commands import format_operator_error
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


class HubsCommand(BaseModel):
    """The fixed embedding hub writer command, whose request carries no argument."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["hubs"]


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
    """The fixed retained-dataset listing command, whose request carries no argument."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["datasets-list"]


class DatasetDeleteCommand(BaseModel):
    """The fixed single non-selected dataset deletion command."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["datasets-delete"]
    dataset_id: DatasetId


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
        """Require one nonblank, NUL-free key the owning file carries."""
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
    """The fixed selected-dataset enrollment command, whose request carries no argument."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["datasets-setup"]


class DatasetMigrateCommand(BaseModel):
    """The fixed selected-dataset migration command, whose request carries no argument."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["datasets-migrate"]


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
    | StageCommand
    | CoverageCommand
    | SummaryCommand
    | HubsCommand
    | TargetReadCommand
    | TargetDecisionCommand
    | DatasetListCommand
    | DatasetDeleteCommand
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


class CommandResult(BaseModel):
    """One transient command outcome: its exit code, its decoded report and its safe failure line.

    The report is the command's own decoded JSON object and is never written to the log or kept. The
    failure line names an exception class and an optional checked-process return code alone.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    exit_code: int
    report: dict[str, JsonValue] | None
    failure_line: str | None


class FixedCommandRunner:
    """Run one admitted fixed command over the shared administrative process boundary.

    The runner revalidates the command against the discriminated union before it executes anything,
    so a mapping or an arbitrary object a caller assembles cannot become a command.
    """

    def __init__(self, root: Path, log: CommandLog, *, runner: ProcessRunner | None = None) -> None:
        self._root = root
        self._log = log
        self._runner = runner if runner is not None else SubprocessRunner()

    def run(self, command: FixedCommand, *, automatic: bool = False) -> CommandResult:
        """Run one admitted command once and record its outcome.

        The command's UTC start time and its monotonic start are captured before it executes, and
        that start time is the recorded entry time. A checked non-zero exit becomes its own integer
        status and the child's own safe failure line when its first stderr line is one, or the
        wrapper's content-free class line otherwise. Any other failure of execution, decoding or
        report assembly becomes status 1 and one content-free class line. No branch returns a
        captured stream or an exception message. A log write failure propagates instead of reporting
        a successful command.

        ``automatic`` marks one read the console repeats on its own timer. A successful automatic
        read appends no entry, while a failed one records like any other outcome. The flag selects
        no argv and changes no admission: the calling route alone decides which commands are reads.
        """
        request = _FIXED_COMMAND_ADAPTER.validate_python(command)
        argv = self._argv(request)
        started_at = utc_now()
        started = time.monotonic()
        try:
            completed = self._runner.run(argv, cwd=self._root)
            result = CommandResult(
                exit_code=completed.returncode,
                report=_decode_report(completed.stdout),
                failure_line=None,
            )
        except subprocess.CalledProcessError as exc:
            result = CommandResult(
                exit_code=exc.returncode, report=None, failure_line=_checked_failure_line(exc)
            )
        except Exception as exc:
            result = CommandResult(
                exit_code=1, report=None, failure_line=format_operator_error(exc)
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

        Every admitted kind has its own branch, and the function holds no other argument source, so
        an argument list cannot be assembled for a command the union does not admit.
        """
        prefix = (sys.executable, str(self._root / ADMIN_SCRIPT))
        match request.kind:
            case "server-status":
                return (*prefix, "server", "status")
            case "usage":
                return (*prefix, "usage", "--hours", str(request.hours))
            case "stage":
                return (*prefix, request.stage, request.action)
            case "coverage":
                return (*prefix, "coverage", request.report)
            case "summary":
                return (*prefix, "summary", request.report)
            case "hubs":
                return (*prefix, "hubs")
            case "target-read":
                return (*prefix, "target", "inference", request.target_id)
            case "target-decision":
                return (*prefix, "dispose", "inference", request.target_id, request.disposition)
            case "datasets-list":
                return (*prefix, "datasets", "list")
            case "datasets-delete":
                return (*prefix, "datasets", "delete", request.dataset_id)
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
                return (*prefix, "migrate", "datasets")
            case "worker-setup":
                argv = (*prefix, "setup", "worker", f"--branch={request.branch}")
                return (*argv, "--code-only") if request.code_only else argv
            case "worker-preflight":
                return (*prefix, "preflight")

    def _record(
        self,
        label: str,
        *,
        started_at: datetime,
        duration: float,
        result: CommandResult,
    ) -> None:
        """Append one fixed-label entry for one command outcome.

        The entry carries the fixed command label, the outcome's exit code and safe failure line, the
        command's start time, the elapsed monotonic duration and the outcome token the failure line
        selects.
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
        case "stage":
            return f"{request.stage} {request.action}"
        case "coverage":
            return f"coverage {request.report}"
        case "summary":
            return f"summary {request.report}"
        case "hubs":
            return "hubs"
        case "target-read":
            return "target inference"
        case "target-decision":
            return "dispose inference"
        case "datasets-list":
            return "datasets list"
        case "datasets-delete":
            return "datasets delete"
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
            return "migrate datasets"
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
