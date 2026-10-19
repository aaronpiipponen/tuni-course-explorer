"""One operator surface over the stage owners: dispatch, reports, presentation, menu.

This module is the one normal operator surface. It owns the stage/action dispatcher, the two
separate setup choices (selected-dataset enrollment and worker preparation), the read-only worker
preflight, the routine read-only server reports, the embedding hub writer, the server-only
target-disposition entry, the presentation-only safe failure surface, and the numbered menu. Every
call delegates exactly once to its owning module and returns that owner's exact DTO. The menu keeps
running until Exit, EOF, or interrupt. Reports read the server state read-only.
"""

from __future__ import annotations

import getpass
import json
import subprocess
import warnings
from collections.abc import Callable
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, SecretStr, ValidationError

from course_explorer.administration import repository_root
from course_explorer.config import (
    ConfiguredSettings,
    DatabaseSettings,
    load_database_settings,
    load_embedding_runtime_settings,
    load_inference_selection_settings,
    load_inference_settings,
    load_usage_settings,
)
from course_explorer.configuration import hub_reference_path
from course_explorer.curriculum_repository import CurriculumRepository
from course_explorer.datasets import DatasetVerification
from course_explorer.db.session import database_context
from course_explorer.embeddings.hub_files import (
    EmbeddingHubReport,
    compute_embedding_hubs,
    read_current_chunk_vectors,
    write_hub_files,
)
from course_explorer.embeddings.repository import CourseEmbeddingRepository
from course_explorer.inference.diagnostics import (
    InferenceCoverageSummary,
    PublicationDiagnostics,
)
from course_explorer.inference.publication import read_inference_publication_diagnostics
from course_explorer.inference.scheduling import TargetDisposition, TargetFailureRecord
from course_explorer.inference.scheduling_repository import InferenceSchedulingRepository
from course_explorer.teaching_text.repository import DerivedTranslationRepository
from course_explorer.teaching_text.service import TeachingTextService
from course_explorer.usage import UsageReport, read_usage_report
from course_explorer_admin import local_stages, mechanics, remote_stages
from course_explorer_admin.backups import BackupDeletionReport, BackupListReport
from course_explorer_admin.configuration import (
    ConfigurationFileReport,
    ConfigurationFilesReport,
    ConfigurationWriteReport,
)
from course_explorer_admin.credentials import PasswordSetReport, set_admin_password
from course_explorer_admin.datasets import DatasetDeletionReport, DatasetListReport
from course_explorer_admin.inference.disposition import (
    InferenceTargetDisposition,
    read_inference_target_disposition,
    set_inference_target_disposition,
)
from course_explorer_admin.lifecycle import Stage, StageName
from course_explorer_admin.logs import LogReadReport, LogSessionsReport, LogSource
from course_explorer_admin.mechanics import ControllerAction
from course_explorer_admin.provisioning import (
    ProvisioningReport,
    preflight_worker,
    prepare_worker,
    update_worker_code,
)
from course_explorer_admin.rebuild import AdminRebuildReport, AdminRestartReport, RebuildReport
from course_explorer_admin.server import ServerStatusReport

if TYPE_CHECKING:
    from course_explorer_admin_web.command_log import CommandLogReport

_STAGE_ACTIONS = ("start", "pause", "resume", "status", "stop")

type AdministrativeCoverage = Literal["teaching-text", "embedding", "inference"]
type AdministrativeSummary = Literal["catalogue", "inference"]

_COVERAGE_KINDS = ("teaching-text", "embedding", "inference")
_SUMMARY_KINDS = ("catalogue", "inference")


def run_administrative_command(
    stage: StageName,
    action: ControllerAction,
    *,
    runner: mechanics.ProcessRunner | None = None,
    inference_stage_factory: Callable[[], Stage] | None = None,
) -> BaseModel:
    """Dispatch exactly one stage lifecycle action to its owning module.

    Membership is validated before any runner or settings work, and one delegate call returns the
    owner's DTO. ``inference_stage_factory`` is forwarded to the inference lifecycle owner alone so
    a wrapper can inject an extra explicit route. Ingestion, embedding and translation take the
    ordinary route.
    """
    if stage not in {"ingestion", "embedding", "translation", "inference"}:
        raise ValueError("stage must be ingestion, embedding, translation, or inference")
    if action not in _STAGE_ACTIONS:
        raise ValueError("action must be start, pause, resume, status, or stop")
    if stage == "ingestion":
        return local_stages.run_ingestion_command(action, runner=runner)
    if stage == "embedding":
        return local_stages.run_embedding_command(action, runner=runner)
    if stage == "translation":
        return remote_stages.run_translation_lifecycle_command(action, runner=runner)
    return remote_stages.run_inference_lifecycle_command(
        action, runner=runner, stage_factory=inference_stage_factory
    )


def run_administrative_setup(
    kind: Literal["datasets", "worker"],
    *,
    branch: str = "main",
    code_only: bool = False,
    runner: mechanics.ProcessRunner | None = None,
) -> BaseModel:
    """Run exactly one separate setup choice through its owner.

    Dataset enrollment and worker preparation are independent. ``code_only`` and a nondefault branch
    belong to worker setup alone, and the branch validator and readiness are owned by provisioning.
    """
    if kind not in {"datasets", "worker"}:
        raise ValueError("setup kind must be datasets or worker")
    process_runner = runner if runner is not None else mechanics.SubprocessRunner()
    if kind == "datasets":
        if code_only:
            raise ValueError("selected-dataset setup does not accept code-only")
        if branch != "main":
            raise ValueError("selected-dataset setup does not accept a branch")
        from course_explorer_admin import datasets

        return datasets.initialize_selected_dataset(runner=process_runner)
    if code_only:
        code = update_worker_code(branch=branch, runner=process_runner)
        return ProvisioningReport(code=code, resources=None)
    return prepare_worker(branch=branch, runner=process_runner)


def run_administrative_preflight(
    *, runner: mechanics.ProcessRunner | None = None
) -> ProvisioningReport:
    """Delegate once to the read-only worker preflight."""
    process_runner = runner if runner is not None else mechanics.SubprocessRunner()
    return preflight_worker(runner=process_runner)


def run_administrative_migration(
    *, runner: mechanics.ProcessRunner | None = None
) -> DatasetVerification:
    """Delegate once to the guarded selected-dataset migration owner.

    One-shot explicit maintenance: it resolves the runner exactly like setup and returns the
    owner's verification report.
    """
    process_runner = runner if runner is not None else mechanics.SubprocessRunner()
    from course_explorer_admin import datasets

    return datasets.migrate_selected_dataset(runner=process_runner)


def run_administrative_dataset_list(
    *, runner: mechanics.ProcessRunner | None = None
) -> DatasetListReport:
    """Delegate once to the retained-dataset listing owner.

    The runner resolves exactly as setup does, so the owner's existence probe reaches the
    configured database service.
    """
    process_runner = runner if runner is not None else mechanics.SubprocessRunner()
    from course_explorer_admin import datasets

    return datasets.list_retained_datasets(runner=process_runner)


def run_administrative_dataset_delete(
    dataset_id: str, *, runner: mechanics.ProcessRunner | None = None
) -> DatasetDeletionReport:
    """Delegate once to the explicit dataset cleanup owner.

    The runner resolves exactly as setup does, so the owner's one Compose drop reaches the
    configured database service.
    """
    process_runner = runner if runner is not None else mechanics.SubprocessRunner()
    from course_explorer_admin import datasets

    return datasets.delete_retained_dataset(dataset_id, runner=process_runner)


def run_administrative_backup_list() -> BackupListReport:
    """Delegate once to the backup-file listing owner."""
    from course_explorer_admin import backups

    return backups.list_backups()


def run_administrative_backup_delete(name: str) -> BackupDeletionReport:
    """Delegate once to the explicit backup-file cleanup owner."""
    from course_explorer_admin import backups

    return backups.delete_backup(name)


def run_administrative_config_list() -> ConfigurationFilesReport:
    """Delegate once to the configuration file listing owner."""
    from course_explorer_admin import configuration

    return configuration.list_configuration_files()


def run_administrative_config_read(file: str) -> ConfigurationFileReport:
    """Delegate once to the configuration file read owner."""
    from course_explorer_admin import configuration

    return configuration.read_configuration_file(file)


def run_administrative_config_set(
    file: str,
    key: str,
    value: str,
    *,
    settings_families: tuple[type[ConfiguredSettings], ...] = (),
) -> ConfigurationWriteReport:
    """Delegate once to the configuration save owner with its validation families."""
    from course_explorer_admin import configuration

    return configuration.set_configuration_value(
        file, key, value, settings_families=settings_families
    )


def run_administrative_password(
    *, username: str, read_password: Callable[[str], str] | None = None
) -> PasswordSetReport:
    """Read one site password twice at hidden prompts and store it through the credential owner.

    An omitted reader resolves to the interactive hidden prompt at call time. A terminal that cannot
    hide the entry, a read failure, two different entries and a blank entry each raise instead of
    falling back to an echoed entry or a partial write. The password comes from that reader, and the
    acknowledgment reports the account as configured.
    """
    reader = read_password if read_password is not None else getpass.getpass
    with warnings.catch_warnings():
        # An entry the terminal cannot hide is refused rather than echoed from the input stream.
        warnings.simplefilter("error", getpass.GetPassWarning)
        password = reader("Password: ")
        repeated = reader("Repeat password: ")
    if password != repeated:
        raise ValueError("password entries must match")
    return set_admin_password(username=username, password=SecretStr(password))


def run_administrative_server_status(
    *, runner: mechanics.ProcessRunner | None = None
) -> ServerStatusReport:
    """Delegate once to the server-only status owner."""
    process_runner = runner if runner is not None else mechanics.SubprocessRunner()
    from course_explorer_admin import server

    return server.read_server_status(runner=process_runner)


def run_administrative_log_sessions() -> LogSessionsReport:
    """Delegate once to the log-session listing owner."""
    from course_explorer_admin import logs

    return logs.list_log_sessions()


def run_administrative_command_log() -> CommandLogReport:
    """Delegate once to the sole command-log owner's retained-entry read.

    The owner lives in the administration backend package, whose runner imports this module, so the
    import happens inside the call.
    """
    from course_explorer_admin_web.command_log import read_command_log

    return read_command_log()


def run_administrative_session_log(
    stage: StageName,
    session_id: str,
    source: LogSource,
    *,
    lines: int,
    runner: mechanics.ProcessRunner | None = None,
) -> LogReadReport:
    """Delegate once to the fixed bounded session-log owner.

    The runner resolves exactly as setup does, because a worker log read reaches the configured
    worker over the transport.
    """
    process_runner = runner if runner is not None else mechanics.SubprocessRunner()
    from course_explorer_admin import logs

    return logs.read_session_log(stage, session_id, source, lines=lines, runner=process_runner)


def run_administrative_embedding_log(
    *, lines: int, runner: mechanics.ProcessRunner | None = None
) -> LogReadReport:
    """Delegate once to the embedding container-log owner."""
    process_runner = runner if runner is not None else mechanics.SubprocessRunner()
    from course_explorer_admin import logs

    return logs.read_embedding_log(lines=lines, runner=process_runner)


def run_administrative_rebuild(*, runner: mechanics.ProcessRunner | None = None) -> RebuildReport:
    """Delegate once to the fixed rebuild owner."""
    process_runner = runner if runner is not None else mechanics.SubprocessRunner()
    from course_explorer_admin import rebuild

    return rebuild.rebuild_site(runner=process_runner)


def run_administrative_admin_rebuild(
    *, runner: mechanics.ProcessRunner | None = None
) -> AdminRebuildReport:
    """Delegate once to the fixed administration build owner."""
    process_runner = runner if runner is not None else mechanics.SubprocessRunner()
    from course_explorer_admin import rebuild

    return rebuild.rebuild_admin(runner=process_runner)


def run_administrative_restart_admin(
    *, runner: mechanics.ProcessRunner | None = None
) -> AdminRestartReport:
    """Delegate once to the fixed administration restart owner."""
    process_runner = runner if runner is not None else mechanics.SubprocessRunner()
    from course_explorer_admin import rebuild

    return rebuild.restart_admin(runner=process_runner)


def run_administrative_usage(*, hours: int) -> UsageReport:
    """Delegate once to the usage report with the configured retention window."""
    return read_usage_report(hours=hours, retention_days=load_usage_settings().usage_retention_days)


class InferenceAdministrativeSummary(BaseModel):
    """One explicit inference report: coverage, publication diagnostics and failures.

    ``operator_done_targets`` and ``operator_failed_target_group_ids`` are ordinary report additions
    from the durable marker decision owner: they distinguish explicit operator terminal choices from
    model results. ``routing_policy``, ``recommendation_policy`` and ``finding_filter_policy`` are
    the configured inference policy values the detailed report states.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[2] = 2
    dataset_scope: Literal["retained_server"] = "retained_server"
    coverage: InferenceCoverageSummary
    publication: PublicationDiagnostics
    failures: tuple[TargetFailureRecord, ...]
    operator_done_targets: int
    operator_failed_target_group_ids: tuple[str, ...]
    routing_policy: str
    recommendation_policy: str
    finding_filter_policy: str


def _selected_dataset_settings() -> DatabaseSettings:
    """Resolve the selected dataset database settings without opening an engine.

    The explicit admin read requires the selected-dataset switch. Missing pointer or database
    failures propagate to the caller.
    """
    settings = load_database_settings()
    if not settings.selected_dataset_enabled:
        raise ValueError(
            "administrative reports require the selected dataset; "
            "run setup with `uv run python scripts/admin.py setup datasets`"
        )
    return settings


def run_administrative_coverage(kind: AdministrativeCoverage) -> BaseModel:
    """Return one coverage report from its owning repository."""
    if kind not in _COVERAGE_KINDS:
        raise ValueError("coverage kind must be teaching-text, embedding, or inference")
    with database_context(_selected_dataset_settings()) as factory:
        if kind == "teaching-text":
            return TeachingTextService(
                CurriculumRepository(factory), DerivedTranslationRepository(factory)
            ).coverage()
        if kind == "embedding":
            return CourseEmbeddingRepository(factory).coverage()
        return InferenceSchedulingRepository(factory).read_coverage()


def run_administrative_summary(kind: AdministrativeSummary) -> BaseModel:
    """Return the catalogue summary or the one explicit detailed inference summary."""
    if kind not in _SUMMARY_KINDS:
        raise ValueError("summary kind must be catalogue or inference")
    with database_context(_selected_dataset_settings()) as factory:
        if kind == "catalogue":
            return CurriculumRepository(factory).summary()
        repository = InferenceSchedulingRepository(factory)
        coverage = repository.read_coverage()
        failures = (
            () if coverage.cycle_id is None else repository.read_target_failures(coverage.cycle_id)
        )
        cohort = repository.read_publication_cohort()
        generation = load_inference_settings()
        publication = read_inference_publication_diagnostics(
            factory,
            cohort,
            generation,
            load_inference_selection_settings(),
        )
        return InferenceAdministrativeSummary(
            coverage=coverage,
            publication=publication,
            failures=failures,
            operator_done_targets=coverage.operator_done_targets,
            operator_failed_target_group_ids=repository.read_operator_failed_target_group_ids(),
            routing_policy=generation.inference_routing_policy,
            recommendation_policy=generation.inference_recommendation_policy,
            finding_filter_policy=generation.inference_finding_filter_policy,
        )


def run_administrative_hubs() -> EmbeddingHubReport:
    """Compute both embedding hubs from the selected dataset and write their configured files.

    Both means are computed before either file is written, so incomplete embedding coverage fails
    without touching the hub files. Both files are staged first and then replace their destinations
    in sequence, so a failure during the replacement can leave only the first destination replaced.
    The files are the paths ``EMBEDDING_HUB_VECTOR`` and
    ``EMBEDDING_OUTCOMES_HUB_VECTOR`` reference. A running web server reads the hubs at start.
    """
    root = repository_root()
    catalogue_path = hub_reference_path(root, "EMBEDDING_HUB_VECTOR")
    outcomes_path = hub_reference_path(root, "EMBEDDING_OUTCOMES_HUB_VECTOR")
    with database_context(_selected_dataset_settings()) as factory:
        current = read_current_chunk_vectors(factory, load_embedding_runtime_settings())
    hubs = compute_embedding_hubs(current)
    write_hub_files(root / catalogue_path, root / outcomes_path, hubs)
    return EmbeddingHubReport(
        catalogue_path=catalogue_path.as_posix(),
        outcomes_path=outcomes_path.as_posix(),
        chunk_count=hubs.chunk_count,
        outcomes_chunk_count=hubs.outcomes_chunk_count,
    )


def format_operator_error(exc: Exception) -> str:
    """Return one content-free single-line JSON error token for any operation exception.

    Only the exception class name is emitted, plus the integer ``returncode`` for a checked
    subprocess failure.
    """
    payload: dict[str, object] = {"error": type(exc).__name__}
    if isinstance(exc, subprocess.CalledProcessError):
        payload["returncode"] = exc.returncode
    return json.dumps(payload, separators=(",", ":"))


def operator_guidance(
    operation: Literal[
        "setup",
        "preflight",
        "stage",
        "report",
        "migration",
        "disposition",
        "hubs",
        "dataset-cleanup",
        "backup-cleanup",
        "configuration",
        "server",
        "logs",
        "rebuild",
        "usage",
        "password",
    ],
    *,
    configuration_error: bool = False,
) -> str:
    """Return the fixed actionable guidance for one operator operation.

    A configuration error (an invalid or missing validated setting) returns fixed configuration
    guidance and never includes the exception's errors, inputs or environment values.
    """
    if configuration_error:
        return "check config/*.toml and this device's ignored .env, then retry the same command"
    if operation == "configuration":
        return (
            "choose a listed configuration file and key, provide a valid JSON value, "
            "and check file permissions"
        )
    if operation == "password":
        return (
            "provide a nonblank username, enter the same password twice at the hidden prompts, "
            "and check the file permissions of the administration state directory"
        )
    if operation == "server":
        return (
            "check the configured site unit, this checkout, and the running database and "
            "embedding services, then retry"
        )
    if operation == "logs":
        return (
            "choose a session and source from the listed sessions, provide a positive line count, "
            "and check the worker connection for a worker read"
        )
    if operation == "rebuild":
        return (
            "check the prepared frontend, the prepared container images and the configured site "
            "unit, then retry"
        )
    if operation == "usage":
        return (
            "request a positive hour window no longer than the configured retention, "
            "and check the usage file permissions"
        )
    if operation in {"setup", "preflight"}:
        return (
            "finish or stop retained stages before updates, then check the prepared clean checkout "
            "and the configured origin"
        )
    if operation == "migration":
        return "ordinary-stop all four stages, ensure the server db is running, then retry"
    if operation == "disposition":
        return (
            "ordinary-stop all four stages, select the verified returned selected dataset and keep "
            "the server db running at the current schema, then retry"
        )
    if operation == "hubs":
        return (
            "complete the embedding stage on the selected dataset, ensure the server db is running, "
            "then retry and restart the web server"
        )
    if operation == "dataset-cleanup":
        return (
            "enroll the selected dataset, pick a non-selected target from the dataset listing "
            "printed by this entry, and ensure the server db is running"
        )
    if operation == "backup-cleanup":
        return (
            "pick a regular file from the backup listing printed by this entry "
            "and check its access permissions"
        )
    if operation == "stage":
        return "inspect this tool's status, then retry its ordinary stop or resume as appropriate"
    return "enroll the selected dataset and ensure the server PostgreSQL service is running"


def worker_origin_notice(report: object) -> str | None:
    """Return the fixed origin notice for a real provisioning report, else ``None``.

    It reports a captured ``server_origin_differs`` fact. Pushing is a separate manual action.
    """
    if not isinstance(report, ProvisioningReport) or not report.code.server_origin_differs:
        return None
    return (
        "notice: the server checkout branch differs from its origin counterpart; "
        "pushing is a separate manual step"
    )


_MAIN_OPTIONS = (
    ("1", "Setup/preflight"),
    ("2", "Ingestion"),
    ("3", "Translation"),
    ("4", "Embedding"),
    ("5", "Inference"),
    ("6", "Coverage/summaries"),
    ("7", "Server/logs"),
    ("0", "Exit"),
)

_SETUP_OPTIONS = (
    ("1", "Enroll/select dataset"),
    ("2", "Worker setup/update"),
    ("3", "Read-only worker preflight"),
    ("4", "Migrate selected dataset"),
    ("5", "Dataset cleanup"),
    ("6", "Backup cleanup"),
    ("7", "Configuration"),
    ("8", "Rebuild app"),
    ("9", "Administration password"),
    ("10", "Rebuild admin panel"),
    ("0", "Back"),
)

_TOOL_OPTIONS = (
    ("1", "Start"),
    ("2", "Pause"),
    ("3", "Resume"),
    ("4", "Status"),
    ("5", "Stop"),
    ("0", "Back"),
)
_TOOL_ACTIONS = {
    "1": "start",
    "2": "pause",
    "3": "resume",
    "4": "status",
    "5": "stop",
}

# The inference and embedding tools add extra options before the trailing `0 Back` row. Every
# other tool uses the base options.
# The inference menu inserts `6 Dispose target` and `7 Dataset cleanup`.
_INFERENCE_TOOL_OPTIONS = (
    *_TOOL_OPTIONS[:-1],
    ("6", "Dispose target"),
    ("7", "Dataset cleanup"),
    _TOOL_OPTIONS[-1],
)
# The embedding menu inserts `6 Write hubs`.
_EMBEDDING_TOOL_OPTIONS = (*_TOOL_OPTIONS[:-1], ("6", "Write hubs"), _TOOL_OPTIONS[-1])

_CLEANUP_OPTIONS = (
    ("1", "Delete"),
    ("0", "Cancel"),
)

_SERVER_LOG_OPTIONS = (
    ("1", "Server status"),
    ("2", "Session log"),
    ("3", "Embedding log"),
    ("4", "Usage"),
    ("5", "Command log"),
    ("0", "Back"),
)

# The two server-side stream choices every session holds, and the three a remote worker session
# adds. A local stage never offers a worker log.
_SERVER_LOG_SOURCES = (
    ("1", "server-stdout"),
    ("2", "server-stderr"),
)
_WORKER_LOG_SOURCES = (
    ("3", "keepalive"),
    ("4", "worker-runner"),
    ("5", "worker-runtime"),
)

_REBUILD_OPTIONS = (
    ("1", "Rebuild"),
    ("0", "Cancel"),
)

_CONFIGURATION_SAVE_OPTIONS = (
    ("1", "Save"),
    ("0", "Cancel"),
)

_DISPOSITION_OPTIONS = (
    ("1", "NOTHING (automatic/no override)"),
    ("2", "DONE (no inferred output)"),
    ("3", "FAILED (terminal)"),
    ("0", "Cancel"),
)
_DISPOSITION_CHOICES: dict[str, TargetDisposition | None] = {"1": None, "2": "done", "3": "failed"}

_REPORT_OPTIONS = (
    ("1", "Catalogue summary"),
    ("2", "Teaching-text/translation coverage"),
    ("3", "Embedding coverage"),
    ("4", "Inference summary"),
    ("0", "Back"),
)

REPORT_SCOPE = (
    "Reports read the selected dataset state, not unreturned worker progress; "
    "use that tool's Status for the latter."
)


def _prompt(
    read: Callable[[str], str],
    write: Callable[[str], None],
    title: str,
    options: tuple[tuple[str, str], ...],
) -> str:
    """Draw one numbered menu and return the stripped selection."""
    write(title)
    for key, label in options:
        write(f"{key} {label}")
    return read("> ").strip()


def _perform(
    write: Callable[[str], None],
    operation: Literal[
        "setup",
        "preflight",
        "stage",
        "report",
        "migration",
        "disposition",
        "hubs",
        "dataset-cleanup",
        "backup-cleanup",
        "configuration",
        "server",
        "logs",
        "rebuild",
        "usage",
        "password",
    ],
    call: Callable[[], object],
) -> None:
    """Run one operation, printing its DTO and notice or the shared safe error and guidance."""
    try:
        result = call()
    except EOFError:
        raise
    except Exception as exc:
        write(format_operator_error(exc))
        write(operator_guidance(operation, configuration_error=isinstance(exc, ValidationError)))
        return
    write(result.model_dump_json())  # type: ignore[attr-defined]
    notice = worker_origin_notice(result)
    if notice is not None:
        write(notice)


def _setup_worker(read: Callable[[str], str], write: Callable[[str], None]) -> None:
    """Prepare or update the worker, asking for a non-main origin branch when the server is not main."""
    try:
        server_branch = mechanics.require_prepared_checkout(
            mechanics.SubprocessRunner(), repository_root()
        )[0]
    except Exception as exc:
        write(format_operator_error(exc))
        write(operator_guidance("setup"))
        return
    if server_branch == "main":
        branch = "main"
    else:
        answer = read(f"Origin branch [{server_branch}]:").strip()
        branch = answer or server_branch
    _perform(write, "setup", lambda: run_administrative_setup("worker", branch=branch))


def _positive_line_count(answer: str) -> int | None:
    """Return one positive whole line count, or ``None`` for anything else."""
    try:
        count = int(answer.strip(), 10)
    except ValueError:
        return None
    return count if count > 0 else None


def _session_log_menu(read: Callable[[str], str], write: Callable[[str], None]) -> None:
    """List the discovered sessions, then read one fixed source of one listed session.

    The listing is printed before the prompts, so the operator answers against real receipts. A
    failed listing follows the shared safe-error presentation and returns without prompting. An
    answer the listing does not carry, a cancel, an unlisted source choice and a line count that is
    not a positive whole number each write nothing and read nothing.
    """
    try:
        listing = run_administrative_log_sessions()
    except Exception as exc:
        write(format_operator_error(exc))
        write(operator_guidance("logs", configuration_error=isinstance(exc, ValidationError)))
        return
    write(listing.model_dump_json())
    stage_answer = read("Stage (0 to cancel): ").strip()
    if stage_answer == "0":
        return
    session_answer = read("Session id (0 to cancel): ").strip()
    if session_answer == "0":
        return
    if (stage_answer, session_answer) not in {
        (entry.stage, entry.session_id) for entry in listing.sessions
    }:
        write("the answer is not a listed session; nothing was read")
        return
    # A remote worker session holds three further sources, and a local stage never offers one.
    sources = (
        (*_SERVER_LOG_SOURCES, *_WORKER_LOG_SOURCES)
        if stage_answer in {"translation", "inference"}
        else _SERVER_LOG_SOURCES
    )
    source = dict(sources).get(_prompt(read, write, "Log source", (*sources, ("0", "Cancel"))))
    if source is None:
        return
    line_answer = read("Lines (0 to cancel): ").strip()
    if line_answer == "0":
        return
    lines = _positive_line_count(line_answer)
    if lines is None:
        write("the answer is not a positive line count; nothing was read")
        return
    _perform(
        write,
        "logs",
        lambda: run_administrative_session_log(stage_answer, session_answer, source, lines=lines),
    )


def _embedding_log_menu(read: Callable[[str], str], write: Callable[[str], None]) -> None:
    """Read the last lines of the embedding container log after one positive line count."""
    line_answer = read("Lines (0 to cancel): ").strip()
    if line_answer == "0":
        return
    lines = _positive_line_count(line_answer)
    if lines is None:
        write("the answer is not a positive line count; nothing was read")
        return
    _perform(write, "logs", lambda: run_administrative_embedding_log(lines=lines))


def _server_logs_menu(read: Callable[[str], str], write: Callable[[str], None]) -> None:
    """Run one of the five server and log reads."""
    while True:
        choice = _prompt(read, write, "Server/logs", _SERVER_LOG_OPTIONS)
        if choice == "0":
            return
        if choice == "1":
            _perform(write, "server", run_administrative_server_status)
        elif choice == "2":
            _session_log_menu(read, write)
        elif choice == "3":
            _embedding_log_menu(read, write)
        elif choice == "4":
            _usage_menu(read, write)
        elif choice == "5":
            _perform(write, "logs", run_administrative_command_log)


def _usage_menu(read: Callable[[str], str], write: Callable[[str], None]) -> None:
    """Run the windowed usage report after one positive hour count.

    A cancel, an end of input, an interrupt and an answer that is not a positive whole hour count
    each read nothing and prune nothing. The report owner bounds the window by the configured
    retention.
    """
    answer = read("Hours (0 to cancel): ").strip()
    if answer == "0":
        return
    hours = _positive_line_count(answer)
    if hours is None:
        write("the answer is not a positive hour count; nothing was read")
        return
    _perform(write, "usage", lambda: run_administrative_usage(hours=hours))


def _rebuild_menu(read: Callable[[str], str], write: Callable[[str], None]) -> None:
    """Confirm the site's frontend, container and web rebuild, then run it once."""
    question = "Rebuild this site's frontend, containers and web server?"
    if _prompt(read, write, question, _REBUILD_OPTIONS) != "1":
        return
    _perform(write, "rebuild", run_administrative_rebuild)


def _admin_rebuild_menu(read: Callable[[str], str], write: Callable[[str], None]) -> None:
    """Confirm the administration panel's rebuild, then build and queue its restart once.

    The build delegate runs first, so a raised build failure stops the callback before the restart
    delegate is reached and restarts nothing. The restart delegate's own acknowledgment is the report
    the entry prints.
    """
    question = "Rebuild the admin panel? This signs all operators out."
    if _prompt(read, write, question, _REBUILD_OPTIONS) != "1":
        return

    def rebuild_then_restart() -> AdminRestartReport:
        run_administrative_admin_rebuild()
        return run_administrative_restart_admin()

    _perform(write, "rebuild", rebuild_then_restart)


def _setup_menu(
    read: Callable[[str], str],
    write: Callable[[str], None],
    *,
    configuration_families: tuple[type[ConfiguredSettings], ...] = (),
) -> None:
    while True:
        choice = _prompt(read, write, "Setup/preflight", _SETUP_OPTIONS)
        if choice == "0":
            return
        if choice == "1":
            _perform(write, "setup", lambda: run_administrative_setup("datasets"))
        elif choice == "2":
            _setup_worker(read, write)
        elif choice == "3":
            _perform(write, "preflight", run_administrative_preflight)
        elif choice == "4":
            _perform(write, "migration", run_administrative_migration)
        elif choice == "5":
            _cleanup_menu(read, write, kind="datasets")
        elif choice == "6":
            _cleanup_menu(read, write, kind="backups")
        elif choice == "7":
            _configuration_menu(read, write, settings_families=configuration_families)
        elif choice == "8":
            _rebuild_menu(read, write)
        elif choice == "9":
            _password_menu(read, write)
        elif choice == "10":
            _admin_rebuild_menu(read, write)


def _password_menu(read: Callable[[str], str], write: Callable[[str], None]) -> None:
    """Ask for one site username and store its password through the hidden terminal entry.

    The username comes from the ordinary menu input and cancels on ``0``. The two password entries
    belong to the command's own hidden terminal prompt, never to the menu's input callback or output,
    so no password reaches the menu's streams. An end of input and an interrupt keep the menu's
    exit semantics.
    """
    username = read("Username (0 to cancel): ").strip()
    if username == "0":
        return
    _perform(write, "password", lambda: run_administrative_password(username=username))


def _configuration_menu(
    read: Callable[[str], str],
    write: Callable[[str], None],
    *,
    settings_families: tuple[type[ConfiguredSettings], ...] = (),
) -> None:
    """List the configuration files, then read one file and save one validated key of it.

    The file listing and the chosen file's values are printed before the prompts that select them, so
    the operator answers against the real files. A failed listing or read prints the shared safe
    error and guidance and returns without a further prompt. The save forwards exactly one listed
    file, one key of that report and one JSON literal to its owner. A cancel, an end of input and an
    interrupt end the entry after writing nothing, and no stage is started or stopped.
    """
    operation: Literal["configuration"] = "configuration"
    try:
        files = run_administrative_config_list()
    except Exception as exc:
        write(format_operator_error(exc))
        write(operator_guidance(operation, configuration_error=isinstance(exc, ValidationError)))
        return
    write(files.model_dump_json())
    file = read("Configuration file (0 to cancel): ").strip()
    if file == "0":
        return
    if file not in files.files:
        write("the answer is not a listed configuration file; nothing was read or written")
        return
    try:
        report = run_administrative_config_read(file)
    except Exception as exc:
        write(format_operator_error(exc))
        write(operator_guidance(operation, configuration_error=isinstance(exc, ValidationError)))
        return
    write(report.model_dump_json())
    key = read("Configuration key (0 to cancel): ").strip()
    if key == "0":
        return
    if key not in report.values:
        write("the answer is not a key of the chosen configuration file; nothing was written")
        return
    value = read("JSON value: ")
    if (
        _prompt(read, write, f"Save configuration {file} key {key}?", _CONFIGURATION_SAVE_OPTIONS)
        != "1"
    ):
        return
    _perform(
        write,
        operation,
        lambda: run_administrative_config_set(
            file, key, value, settings_families=settings_families
        ),
    )


def _tool_menu(
    read: Callable[[str], str],
    write: Callable[[str], None],
    stage: str,
    *,
    run_command: Callable[..., BaseModel],
) -> None:
    options = {"inference": _INFERENCE_TOOL_OPTIONS, "embedding": _EMBEDDING_TOOL_OPTIONS}.get(
        stage, _TOOL_OPTIONS
    )
    while True:
        choice = _prompt(read, write, f"{stage.capitalize()} tool", options)
        if choice == "0":
            return
        if stage == "inference" and choice == "6":
            _dispose_target_menu(read, write)
            continue
        if stage == "inference" and choice == "7":
            _cleanup_menu(read, write, kind="datasets")
            continue
        if stage == "embedding" and choice == "6":
            _perform(write, "hubs", run_administrative_hubs)
            continue
        action = _TOOL_ACTIONS.get(choice)
        if action is None:
            continue
        _perform(write, "stage", lambda: run_command(stage, action))  # type: ignore[arg-type]


def _cleanup_menu(
    read: Callable[[str], str],
    write: Callable[[str], None],
    *,
    kind: Literal["datasets", "backups"],
) -> None:
    """List one cleanup inventory, then confirm and delete one target that listing names.

    The listing is read and printed before the target prompt, as the disposition entry reads its
    target before the choice prompt, so the operator answers against the real inventory. The dataset
    owner resolves the retained chain again under its own action lock, and the backup owner rechecks
    its confined target, so the printed inventory labels the target and the owner's check decides the
    deletion. A failed listing, an answer outside the displayed inventory, a selected dataset, a
    confirmation other than the delete choice, an end of input and an interrupt each return after
    deleting nothing. One invocation deletes at most the one target the confirmation names.
    """
    operation: Literal["dataset-cleanup", "backup-cleanup"] = (
        "dataset-cleanup" if kind == "datasets" else "backup-cleanup"
    )
    if kind == "datasets":
        try:
            listing = run_administrative_dataset_list()
        except Exception as exc:
            write(format_operator_error(exc))
            write(
                operator_guidance(operation, configuration_error=isinstance(exc, ValidationError))
            )
            return
        write(listing.model_dump_json())
        eligible = {
            entry.dataset_id: f"Delete dataset {entry.dataset_id} ({entry.database_name})?"
            for entry in listing.datasets
            if not entry.selected
        }
        target_prompt = "Dataset id: "
    else:
        try:
            backup_listing = run_administrative_backup_list()
        except Exception as exc:
            write(format_operator_error(exc))
            write(
                operator_guidance(operation, configuration_error=isinstance(exc, ValidationError))
            )
            return
        write(backup_listing.model_dump_json())
        eligible = {
            backup.name: f"Delete backup {backup.name}?" for backup in backup_listing.backups
        }
        target_prompt = "Backup file name: "
    if not eligible:
        return
    answer = read(target_prompt).strip()
    if answer == "0":
        return
    title = eligible.get(answer)
    if title is None:
        write("the answer is not an eligible target of this listing; nothing was deleted")
        return
    if _prompt(read, write, title, _CLEANUP_OPTIONS) != "1":
        return
    if kind == "datasets":
        _perform(write, operation, lambda: run_administrative_dataset_delete(answer))
    else:
        _perform(write, operation, lambda: run_administrative_backup_delete(answer))


def _dispose_target_menu(read: Callable[[str], str], write: Callable[[str], None]) -> None:
    """Run the identity-first disposition flow for one supplied canonical target.

    The target's canonical identity, official code/name and current durable decision are read and
    printed BEFORE the choice prompt, so the operator decides against the real identity rather than an
    assumed one. A read failure follows the shared safe-error presentation and returns without ever
    prompting or writing. Cancel, an invalid selection, EOF or an interrupt mutates nothing and never
    stops a job.
    """
    target_group_id = read("Target canonical group id: ").strip()
    try:
        current = read_inference_target_disposition(target_group_id)
    except Exception as exc:
        write(format_operator_error(exc))
        write(
            operator_guidance("disposition", configuration_error=isinstance(exc, ValidationError))
        )
        return
    write(current.model_dump_json())
    current_label = (
        "NOTHING (automatic)" if current.disposition is None else current.disposition.upper()
    )
    write(f"current decision: {current_label}")
    choice = _prompt(read, write, "Dispose target", _DISPOSITION_OPTIONS)
    if choice not in _DISPOSITION_CHOICES:
        return
    disposition = _DISPOSITION_CHOICES[choice]
    _perform(
        write,
        "disposition",
        lambda: set_inference_target_disposition(target_group_id, disposition),
    )


def _reports_menu(
    read: Callable[[str], str],
    write: Callable[[str], None],
    *,
    run_summary: Callable[..., BaseModel],
) -> None:
    write(REPORT_SCOPE)
    while True:
        choice = _prompt(read, write, "Coverage/summaries", _REPORT_OPTIONS)
        if choice == "0":
            return
        if choice == "1":
            _perform(write, "report", lambda: run_administrative_summary("catalogue"))
        elif choice == "2":
            _perform(write, "report", lambda: run_administrative_coverage("teaching-text"))
        elif choice == "3":
            _perform(write, "report", lambda: run_administrative_coverage("embedding"))
        elif choice == "4":
            _perform(write, "report", lambda: run_summary("inference"))


def run_operator_menu(
    *,
    read: Callable[[str], str] = input,
    write: Callable[[str], None] = print,
    run_command: Callable[..., BaseModel] | None = None,
    run_summary: Callable[..., BaseModel] | None = None,
    configuration_families: tuple[type[ConfiguredSettings], ...] = (),
) -> int:
    """Run the numbered operator menu until Exit, EOF (0), or interrupt (130).

    An absent stage or summary callback resolves to the base command at entry. A supplied
    callback replaces that one call only, so a wrapper injects an extra route without a second menu
    or dispatcher. ``configuration_families`` reach the configuration entry alone, so a wrapper can
    add the validation families of its own package. Choices, scope, safe failures, disposition and
    EOF behavior come from the base command.
    """
    commands = run_command if run_command is not None else run_administrative_command
    summaries = run_summary if run_summary is not None else run_administrative_summary
    try:
        while True:
            choice = _prompt(read, write, "Course Explorer administration", _MAIN_OPTIONS)
            if choice == "0":
                return 0
            if choice == "1":
                _setup_menu(read, write, configuration_families=configuration_families)
            elif choice == "2":
                _tool_menu(read, write, "ingestion", run_command=commands)
            elif choice == "3":
                _tool_menu(read, write, "translation", run_command=commands)
            elif choice == "4":
                _tool_menu(read, write, "embedding", run_command=commands)
            elif choice == "5":
                _tool_menu(read, write, "inference", run_command=commands)
            elif choice == "6":
                _reports_menu(read, write, run_summary=summaries)
            elif choice == "7":
                _server_logs_menu(read, write)
    except KeyboardInterrupt:
        return 130
    except EOFError:
        return 0


__all__ = [
    "AdminRebuildReport",
    "AdminRestartReport",
    "AdministrativeCoverage",
    "AdministrativeSummary",
    "BackupDeletionReport",
    "BackupListReport",
    "ConfigurationFileReport",
    "ConfigurationFilesReport",
    "ConfigurationWriteReport",
    "ControllerAction",
    "DatasetDeletionReport",
    "DatasetListReport",
    "InferenceAdministrativeSummary",
    "InferenceTargetDisposition",
    "LogReadReport",
    "LogSessionsReport",
    "LogSource",
    "PasswordSetReport",
    "REPORT_SCOPE",
    "RebuildReport",
    "ServerStatusReport",
    "StageName",
    "UsageReport",
    "format_operator_error",
    "operator_guidance",
    "read_inference_target_disposition",
    "run_administrative_backup_delete",
    "run_administrative_backup_list",
    "run_administrative_admin_rebuild",
    "run_administrative_command",
    "run_administrative_command_log",
    "run_administrative_config_list",
    "run_administrative_config_read",
    "run_administrative_config_set",
    "run_administrative_coverage",
    "run_administrative_dataset_delete",
    "run_administrative_dataset_list",
    "run_administrative_embedding_log",
    "run_administrative_hubs",
    "run_administrative_log_sessions",
    "run_administrative_migration",
    "run_administrative_password",
    "run_administrative_preflight",
    "run_administrative_rebuild",
    "run_administrative_restart_admin",
    "run_administrative_server_status",
    "run_administrative_session_log",
    "run_administrative_setup",
    "run_administrative_summary",
    "run_administrative_usage",
    "run_operator_menu",
    "set_inference_target_disposition",
    "worker_origin_notice",
]
