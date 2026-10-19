"""The Data preparation routes: the three local stage panels and their owning reports.

Each route maps one authenticated request to exactly one fixed command and returns that command's
transient outcome. The stage guards the operation needs, such as stage idleness and a prepared
checkout, stay with the command's owning service. A status read and a report read forward the
console's automatic-read marker to the runner, because the console polls them on its own timer,
while a stage action is an explicit command. Every answer is non-cacheable.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, ConfigDict

from course_explorer_admin_web.routes.auth import NO_STORE_HEADERS
from course_explorer_admin_web.routes.read_mode import automatic_read
from course_explorer_admin_web.runner import (
    CommandResult,
    CoverageCommand,
    HubsCommand,
    StageCommand,
    SummaryCommand,
)

router = APIRouter()

# The three stages the preparation tab owns. Inference is its own tab with its own routes.
PreparationStage = Literal["ingestion", "translation", "embedding"]

# The four lifecycle actions the preparation panels offer.
StageAction = Literal["start", "pause", "resume", "stop"]


class StageActionRequest(BaseModel):
    """One requested lifecycle action on one preparation stage."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    stage: PreparationStage
    action: StageAction


class HubsRequest(BaseModel):
    """The empty body of one hub write request, so a body with any field is refused."""

    model_config = ConfigDict(extra="forbid", frozen=True)


@router.get("/api/preparation/status/{stage}")
def status(request: Request, response: Response, stage: PreparationStage) -> CommandResult:
    """Run one stage's fixed status read once and return its transient outcome."""
    response.headers.update(NO_STORE_HEADERS)
    return request.app.state.commands.run(
        StageCommand(kind="stage", stage=stage, action="status"),
        automatic=automatic_read(request),
    )


@router.post("/api/preparation/action")
def action(request: Request, response: Response, body: StageActionRequest) -> CommandResult:
    """Run one stage's fixed lifecycle action once and return its transient outcome."""
    response.headers.update(NO_STORE_HEADERS)
    return request.app.state.commands.run(
        StageCommand(kind="stage", stage=body.stage, action=body.action)
    )


@router.get("/api/preparation/report/{report}")
def report(
    request: Request,
    response: Response,
    report: Literal["catalogue", "teaching-text", "embedding"],
) -> CommandResult:
    """Run the fixed report command that owns the requested preparation report."""
    response.headers.update(NO_STORE_HEADERS)
    commands = request.app.state.commands
    automatic = automatic_read(request)
    if report == "catalogue":
        return commands.run(SummaryCommand(kind="summary", report="catalogue"), automatic=automatic)
    return commands.run(CoverageCommand(kind="coverage", report=report), automatic=automatic)


@router.post("/api/preparation/hubs")
def hubs(request: Request, response: Response, body: HubsRequest) -> CommandResult:
    """Write both embedding hub files through the fixed hub command once."""
    response.headers.update(NO_STORE_HEADERS)
    return request.app.state.commands.run(HubsCommand(kind="hubs"))
