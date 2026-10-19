"""The Logs routes: the command log, the log-session inventory and the bounded log reads.

Each route maps one authenticated request to exactly one fixed command and returns that command's
transient outcome. The positive line count, the fixed source vocabulary and the session receipt
confinement stay with the command's owning service, so this layer validates the shape of a parameter
alone. A worker source is read only by the request that names it. Every route here forwards the
console's automatic-read marker to the runner, because each of them serves an automatic panel read
as well as an explicit one. Every answer is non-cacheable.
"""

from __future__ import annotations

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from course_explorer_admin_web.routes.auth import NO_STORE_HEADERS
from course_explorer_admin_web.routes.read_mode import automatic_read
from course_explorer_admin_web.runner import (
    CommandLogCommand,
    CommandResult,
    EmbeddingLogCommand,
    EmbeddingLogInput,
    LogSessionsCommand,
    SessionLogCommand,
    SessionLogInput,
    UsageCommand,
)

router = APIRouter()


class UsageRequest(BaseModel):
    """One requested usage window in positive whole hours."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    hours: int = Field(gt=0, strict=True)


class SessionLogRequest(SessionLogInput):
    """One requested bounded read of one listed session's own log."""


class EmbeddingLogRequest(EmbeddingLogInput):
    """One requested bounded read of the embedding service's own container log."""


@router.get("/api/logs/commands")
def commands(request: Request, response: Response) -> CommandResult:
    """Run the fixed retained command-log read once and return its transient outcome."""
    response.headers.update(NO_STORE_HEADERS)
    return request.app.state.commands.run(
        CommandLogCommand(kind="command-log"), automatic=automatic_read(request)
    )


@router.get("/api/logs/sessions")
def sessions(request: Request, response: Response) -> CommandResult:
    """Run the fixed log-session listing once and return its transient outcome."""
    response.headers.update(NO_STORE_HEADERS)
    return request.app.state.commands.run(
        LogSessionsCommand(kind="log-sessions"), automatic=automatic_read(request)
    )


@router.post("/api/logs/read")
def read(request: Request, response: Response, body: SessionLogRequest) -> CommandResult:
    """Run one fixed bounded session-log read once and return its transient outcome."""
    response.headers.update(NO_STORE_HEADERS)
    return request.app.state.commands.run(
        SessionLogCommand(
            kind="session-log",
            stage=body.stage,
            session_id=body.session_id,
            source=body.source,
            lines=body.lines,
        ),
        automatic=automatic_read(request),
    )


@router.post("/api/logs/embedding")
def embedding(request: Request, response: Response, body: EmbeddingLogRequest) -> CommandResult:
    """Run one fixed bounded embedding-log read once and return its transient outcome."""
    response.headers.update(NO_STORE_HEADERS)
    return request.app.state.commands.run(
        EmbeddingLogCommand(kind="embedding-log", lines=body.lines),
        automatic=automatic_read(request),
    )


@router.post("/api/logs/usage")
def usage(request: Request, response: Response, body: UsageRequest) -> CommandResult:
    """Run the fixed windowed usage report once and return its transient outcome."""
    response.headers.update(NO_STORE_HEADERS)
    return request.app.state.commands.run(
        UsageCommand(kind="usage", hours=body.hours), automatic=automatic_read(request)
    )
