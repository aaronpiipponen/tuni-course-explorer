"""The Inference tab routes: the separate inference run, its reports and its target decisions.

Each route maps one authenticated request to exactly one fixed command and returns that command's
transient outcome. The inference run, the target read, the target decision and the dataset deletion
each keep their own operation-specific guards in the command's owning service, including the
all-idle and verified-returned-dataset conditions a decision requires. The run status, the summary
and the dataset listing forward the console's automatic-read marker to the runner, while the target
read, the decision and the deletion are explicit. Every answer is non-cacheable.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, ConfigDict

from course_explorer.datasets import DatasetId
from course_explorer_admin_web.routes.auth import NO_STORE_HEADERS
from course_explorer_admin_web.routes.read_mode import automatic_read
from course_explorer_admin_web.runner import (
    CommandResult,
    DatasetDeleteCommand,
    DatasetListCommand,
    StageCommand,
    SummaryCommand,
    TargetDecisionCommand,
    TargetDecisionInput,
    TargetInput,
    TargetReadCommand,
)

router = APIRouter()

# The four lifecycle actions the inference run panel offers.
InferenceAction = Literal["start", "pause", "resume", "stop"]


class InferenceActionRequest(BaseModel):
    """One requested lifecycle action on the inference run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    action: InferenceAction


class TargetReadRequest(TargetInput):
    """One requested canonical target identity read."""


class TargetDecisionRequest(TargetDecisionInput):
    """One requested canonical target decision with its terminal token."""


class DatasetDeleteRequest(BaseModel):
    """One requested deletion of a listed non-selected dataset."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    dataset_id: DatasetId


@router.get("/api/inference/status")
def status(request: Request, response: Response) -> CommandResult:
    """Run the fixed inference status read once and return its transient outcome."""
    response.headers.update(NO_STORE_HEADERS)
    return request.app.state.commands.run(
        StageCommand(kind="stage", stage="inference", action="status"),
        automatic=automatic_read(request),
    )


@router.post("/api/inference/action")
def action(request: Request, response: Response, body: InferenceActionRequest) -> CommandResult:
    """Run one fixed inference lifecycle action once and return its transient outcome."""
    response.headers.update(NO_STORE_HEADERS)
    return request.app.state.commands.run(
        StageCommand(kind="stage", stage="inference", action=body.action)
    )


@router.get("/api/inference/summary")
def summary(request: Request, response: Response) -> CommandResult:
    """Run the fixed inference summary command once and return its transient outcome."""
    response.headers.update(NO_STORE_HEADERS)
    return request.app.state.commands.run(
        SummaryCommand(kind="summary", report="inference"), automatic=automatic_read(request)
    )


@router.post("/api/inference/target/read")
def target(request: Request, response: Response, body: TargetReadRequest) -> CommandResult:
    """Run the fixed target identity read once and return its transient outcome."""
    response.headers.update(NO_STORE_HEADERS)
    return request.app.state.commands.run(
        TargetReadCommand(kind="target-read", target_id=body.target_id)
    )


@router.post("/api/inference/target/decision")
def decision(request: Request, response: Response, body: TargetDecisionRequest) -> CommandResult:
    """Run the fixed target decision command once and return its transient outcome."""
    response.headers.update(NO_STORE_HEADERS)
    return request.app.state.commands.run(
        TargetDecisionCommand(
            kind="target-decision", target_id=body.target_id, disposition=body.disposition
        )
    )


@router.get("/api/inference/datasets")
def datasets(request: Request, response: Response) -> CommandResult:
    """Run the fixed retained-dataset listing once and return its transient outcome."""
    response.headers.update(NO_STORE_HEADERS)
    return request.app.state.commands.run(
        DatasetListCommand(kind="datasets-list"), automatic=automatic_read(request)
    )


@router.post("/api/inference/datasets/delete")
def delete_dataset(
    request: Request, response: Response, body: DatasetDeleteRequest
) -> CommandResult:
    """Run the fixed single-dataset deletion once and return its transient outcome."""
    response.headers.update(NO_STORE_HEADERS)
    return request.app.state.commands.run(
        DatasetDeleteCommand(kind="datasets-delete", dataset_id=body.dataset_id)
    )
