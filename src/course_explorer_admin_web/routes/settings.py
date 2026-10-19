"""The Settings routes: the configuration editor, the backup cleanup and the maintenance actions.

Most routes map one authenticated request to exactly one fixed command and return that command's
transient outcome. The administration self-rebuild is the one two-command action: the request runs
the build command synchronously and returns its ordinary outcome, and only a successful build
attaches the separate restart command as a background task that Starlette runs after the final
response body send. A failed or cancelled send therefore runs no restart. The command's owning
service enforces file confinement, key existence, JSON literal parsing, backup name safety, branch
validity and every stage guard, and this layer validates the shape of a parameter. A refused
preflight presents the command's own failure. The configuration file
listing, the configuration file read and the backup listing forward the console's automatic-read
marker to the runner, while every write and maintenance action is explicit. Every answer is
non-cacheable.
"""

from __future__ import annotations

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from starlette.background import BackgroundTask

from course_explorer_admin_web.routes.auth import NO_STORE_HEADERS
from course_explorer_admin_web.routes.read_mode import automatic_read
from course_explorer_admin_web.runner import (
    AdminRebuildCommand,
    BackupDeleteCommand,
    BackupDeleteInput,
    BackupListCommand,
    CommandResult,
    ConfigFilesCommand,
    ConfigReadCommand,
    ConfigReadInput,
    ConfigSetCommand,
    ConfigSetInput,
    DatasetMigrateCommand,
    DatasetSetupCommand,
    RebuildCommand,
    RestartAdminCommand,
    WorkerPreflightCommand,
    WorkerSetupCommand,
    WorkerSetupInput,
)

router = APIRouter()


class EmptyRequest(BaseModel):
    """The empty body of one maintenance request, so a body with any field is refused."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class ConfigReadRequest(ConfigReadInput):
    """One requested read of one listed configuration file."""


class ConfigSetRequest(ConfigSetInput):
    """One requested save of one key of one listed configuration file."""


class BackupDeleteRequest(BackupDeleteInput):
    """One requested deletion of one listed backup file."""


class WorkerSetupRequest(WorkerSetupInput):
    """One requested worker setup or update over its branch and code-only choice."""


@router.get("/api/settings/config/files")
def config_files(request: Request, response: Response) -> CommandResult:
    """Run the fixed configuration file listing once and return its transient outcome."""
    response.headers.update(NO_STORE_HEADERS)
    return request.app.state.commands.run(
        ConfigFilesCommand(kind="config-files"), automatic=automatic_read(request)
    )


@router.post("/api/settings/config/read")
def config_read(request: Request, response: Response, body: ConfigReadRequest) -> CommandResult:
    """Run the fixed read of one listed configuration file once."""
    response.headers.update(NO_STORE_HEADERS)
    return request.app.state.commands.run(
        ConfigReadCommand(kind="config-read", file=body.file), automatic=automatic_read(request)
    )


@router.post("/api/settings/config/set")
def config_set(request: Request, response: Response, body: ConfigSetRequest) -> CommandResult:
    """Run the fixed save of one configuration key once."""
    response.headers.update(NO_STORE_HEADERS)
    return request.app.state.commands.run(
        ConfigSetCommand(kind="config-set", file=body.file, key=body.key, value=body.value)
    )


@router.get("/api/settings/backups")
def backups(request: Request, response: Response) -> CommandResult:
    """Run the fixed backup-file listing once and return its transient outcome."""
    response.headers.update(NO_STORE_HEADERS)
    return request.app.state.commands.run(
        BackupListCommand(kind="backups-list"), automatic=automatic_read(request)
    )


@router.post("/api/settings/backups/delete")
def backup_delete(request: Request, response: Response, body: BackupDeleteRequest) -> CommandResult:
    """Run the fixed deletion of one listed backup file once."""
    response.headers.update(NO_STORE_HEADERS)
    return request.app.state.commands.run(
        BackupDeleteCommand(kind="backups-delete", name=body.name)
    )


@router.post("/api/settings/rebuild")
def rebuild(request: Request, response: Response, body: EmptyRequest) -> CommandResult:
    """Run the fixed site rebuild once and return its transient outcome."""
    response.headers.update(NO_STORE_HEADERS)
    return request.app.state.commands.run(RebuildCommand(kind="rebuild"))


@router.post("/api/settings/rebuild-admin")
def rebuild_admin(request: Request, body: EmptyRequest) -> JSONResponse:
    """Build the administration frontend and, on success, queue its own unit restart.

    The build command runs synchronously and its ordinary outcome is the response. The restart
    command is admitted as a background task only when the build succeeded, so the final response body
    is sent before the restart request is made and a failed or cancelled send runs no restart. A queue
    failure follows the runner's ordinary safe outcome and log entry and cannot change the sent build
    response. Both commands are explicit actions and ignore the automatic-read marker.
    """
    result = request.app.state.commands.run(AdminRebuildCommand(kind="rebuild-admin"))
    task = (
        BackgroundTask(request.app.state.commands.run, RestartAdminCommand(kind="restart-admin"))
        if result.exit_code == 0 and result.failure_line is None
        else None
    )
    return JSONResponse(
        content=result.model_dump(mode="json"), headers=NO_STORE_HEADERS, background=task
    )


@router.post("/api/settings/datasets/setup")
def dataset_setup(request: Request, response: Response, body: EmptyRequest) -> CommandResult:
    """Run the fixed selected-dataset enrollment once."""
    response.headers.update(NO_STORE_HEADERS)
    return request.app.state.commands.run(DatasetSetupCommand(kind="datasets-setup"))


@router.post("/api/settings/datasets/migrate")
def dataset_migrate(request: Request, response: Response, body: EmptyRequest) -> CommandResult:
    """Run the fixed selected-dataset migration once."""
    response.headers.update(NO_STORE_HEADERS)
    return request.app.state.commands.run(DatasetMigrateCommand(kind="datasets-migrate"))


@router.post("/api/settings/worker/setup")
def worker_setup(request: Request, response: Response, body: WorkerSetupRequest) -> CommandResult:
    """Run the fixed worker setup or update once."""
    response.headers.update(NO_STORE_HEADERS)
    return request.app.state.commands.run(
        WorkerSetupCommand(kind="worker-setup", branch=body.branch, code_only=body.code_only)
    )


@router.post("/api/settings/worker/preflight")
def worker_preflight(request: Request, response: Response, body: EmptyRequest) -> CommandResult:
    """Run the fixed read-only worker preflight once."""
    response.headers.update(NO_STORE_HEADERS)
    return request.app.state.commands.run(WorkerPreflightCommand(kind="worker-preflight"))
