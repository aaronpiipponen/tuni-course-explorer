"""One operator surface over the stage owners: dispatch, reports, presentation, menu.

This module is the one normal operator surface. It owns the stage/action dispatcher, the two
separate setup choices (selected-dataset enrollment and worker preparation), the read-only worker
preflight, the routine read-only server reports, the embedding hub writer, the server-only
target-disposition entry, the presentation-only safe failure surface, and the numbered menu. Every
call delegates exactly once to its owning module and returns that owner's exact DTO. The menu keeps
running until Exit, EOF, or interrupt. Reports read the server state read-only.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from course_explorer.administration import repository_root
from course_explorer.config import (
    DatabaseSettings,
    load_database_settings,
    load_embedding_runtime_settings,
    load_inference_selection_settings,
    load_inference_settings,
)
from course_explorer.configuration import hub_reference_path
from course_explorer.curriculum_repository import CurriculumRepository
from course_explorer.datasets import DatasetVerification
from course_explorer.db.session import database_context
from course_explorer.embeddings.hub_files import (
    EmbeddingHubReport,
    compute_embedding_hubs,
    read_current_chunk_vectors,
    write_hub_file,
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
from course_explorer_admin import local_stages, mechanics, remote_stages
from course_explorer_admin.inference.disposition import (
    InferenceTargetDisposition,
    read_inference_target_disposition,
    set_inference_target_disposition,
)
from course_explorer_admin.lifecycle import Stage, StageName
from course_explorer_admin.mechanics import ControllerAction
from course_explorer_admin.provisioning import (
    ProvisioningReport,
    preflight_worker,
    prepare_worker,
    update_worker_code,
)

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


class InferenceAdministrativeSummary(BaseModel):
    """One explicit inference report: coverage, publication diagnostics and failures.

    ``operator_done_targets`` and ``operator_failed_target_group_ids`` are ordinary report additions
    from the durable marker decision owner: they distinguish explicit operator terminal choices from
    model results.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[2] = 2
    dataset_scope: Literal["retained_server"] = "retained_server"
    coverage: InferenceCoverageSummary
    publication: PublicationDiagnostics
    failures: tuple[TargetFailureRecord, ...]
    operator_done_targets: int
    operator_failed_target_group_ids: tuple[str, ...]


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
        publication = read_inference_publication_diagnostics(
            factory,
            cohort,
            load_inference_settings(),
            load_inference_selection_settings(),
        )
        return InferenceAdministrativeSummary(
            coverage=coverage,
            publication=publication,
            failures=failures,
            operator_done_targets=coverage.operator_done_targets,
            operator_failed_target_group_ids=repository.read_operator_failed_target_group_ids(),
        )


def run_administrative_hubs() -> EmbeddingHubReport:
    """Compute both embedding hubs from the selected dataset and write their configured files.

    Both means are computed before either file is written, so incomplete embedding coverage fails
    without touching the hub files. The files are the paths ``EMBEDDING_HUB_VECTOR`` and
    ``EMBEDDING_OUTCOMES_HUB_VECTOR`` reference. A running web server reads the hubs at start.
    """
    root = repository_root()
    catalogue_path = hub_reference_path(root, "EMBEDDING_HUB_VECTOR")
    outcomes_path = hub_reference_path(root, "EMBEDDING_OUTCOMES_HUB_VECTOR")
    with database_context(_selected_dataset_settings()) as factory:
        current = read_current_chunk_vectors(factory, load_embedding_runtime_settings())
    hubs = compute_embedding_hubs(current)
    write_hub_file(root / catalogue_path, hubs.catalogue)
    write_hub_file(root / outcomes_path, hubs.outcomes)
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
    operation: Literal["setup", "preflight", "stage", "report", "migration", "disposition", "hubs"],
    *,
    configuration_error: bool = False,
) -> str:
    """Return the fixed actionable guidance for one operator operation.

    A configuration error (an invalid or missing validated setting) returns fixed configuration
    guidance and never includes the exception's errors, inputs or environment values.
    """
    if configuration_error:
        return (
            "check the tracked config/*.toml and this device's ignored .env per "
            "config/README.md, then retry the same command"
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
    ("0", "Exit"),
)

_SETUP_OPTIONS = (
    ("1", "Enroll/select dataset"),
    ("2", "Worker setup/update"),
    ("3", "Read-only worker preflight"),
    ("4", "Migrate selected dataset"),
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

# The inference and embedding tools add one extra option before the trailing `0 Back` row. Every
# other tool uses the base options.
# The inference menu inserts `6 Dispose target`.
_INFERENCE_TOOL_OPTIONS = (*_TOOL_OPTIONS[:-1], ("6", "Dispose target"), _TOOL_OPTIONS[-1])
# The embedding menu inserts `6 Write hubs`.
_EMBEDDING_TOOL_OPTIONS = (*_TOOL_OPTIONS[:-1], ("6", "Write hubs"), _TOOL_OPTIONS[-1])

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
    operation: Literal["setup", "preflight", "stage", "report", "migration", "disposition", "hubs"],
    call: Callable[[], object],
) -> None:
    """Run one operation, printing its DTO and notice or the shared safe error and guidance."""
    try:
        result = call()
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


def _setup_menu(read: Callable[[str], str], write: Callable[[str], None]) -> None:
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
        if stage == "embedding" and choice == "6":
            _perform(write, "hubs", run_administrative_hubs)
            continue
        action = _TOOL_ACTIONS.get(choice)
        if action is None:
            continue
        _perform(write, "stage", lambda: run_command(stage, action))  # type: ignore[arg-type]


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
) -> int:
    """Run the numbered operator menu until Exit, EOF (0), or interrupt (130).

    An absent stage or summary callback resolves to the base command at entry. A supplied
    callback replaces that one call only, so a wrapper injects an extra route without a second menu
    or dispatcher. The wrapper injects only the extra route. Choices, scope, safe failures,
    disposition and EOF behavior come from the base command.
    """
    commands = run_command if run_command is not None else run_administrative_command
    summaries = run_summary if run_summary is not None else run_administrative_summary
    try:
        while True:
            choice = _prompt(read, write, "Course Explorer administration", _MAIN_OPTIONS)
            if choice == "0":
                return 0
            if choice == "1":
                _setup_menu(read, write)
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
    except KeyboardInterrupt:
        return 130
    except EOFError:
        return 0


__all__ = [
    "AdministrativeCoverage",
    "AdministrativeSummary",
    "ControllerAction",
    "InferenceAdministrativeSummary",
    "InferenceTargetDisposition",
    "REPORT_SCOPE",
    "StageName",
    "format_operator_error",
    "operator_guidance",
    "read_inference_target_disposition",
    "run_administrative_command",
    "run_administrative_coverage",
    "run_administrative_hubs",
    "run_administrative_migration",
    "run_administrative_preflight",
    "run_administrative_setup",
    "run_administrative_summary",
    "run_operator_menu",
    "set_inference_target_disposition",
    "worker_origin_notice",
]
