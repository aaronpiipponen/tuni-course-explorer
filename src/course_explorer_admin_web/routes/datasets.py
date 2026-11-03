"""The dataset routes: one inventory and the explicit role actions over it.

Every route maps one authenticated request to exactly one fixed command and returns that command's
transient outcome, except the confirmed promotion, which answers one request-bound
newline-delimited JSON stream. The inventory forwards the console's automatic-read marker.
Enrollment, role migration, deletion and both copies are explicit actions. Each command's owning
service keeps its own guards: the dataset owner resolves roles, idle state and the chain again
under its action lock, so this layer validates only the shape of a parameter.

The promotion stream owns one queue and one worker thread for exactly its own command invocation,
and nothing else: the producer runs the fixed command once, queues each coarse step its owner
reports and then queues that command's terminal result after its single log record. The consumer
ends at the terminal record. A disconnected or failed send cancels nothing, so the mutation, its
rollback and its log record finish. The finite events then exist only in that request's queue
until the producer exits. There is no job id, retained stream, status address, reconnection or
executor pool.

Every answer is non-cacheable.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from queue import Queue
from typing import Any

from fastapi import APIRouter, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, ValidationError

from course_explorer_admin.commands import format_operator_error, operator_guidance
from course_explorer_admin_web.routes.auth import NO_STORE_HEADERS
from course_explorer_admin_web.routes.read_mode import automatic_read
from course_explorer_admin_web.runner import (
    CommandResult,
    DatasetCopyCommand,
    DatasetCopyInput,
    DatasetDeleteCommand,
    DatasetDeleteInput,
    DatasetListCommand,
    DatasetMigrateCommand,
    DatasetMigrateInput,
    DatasetPromotionCommand,
    DatasetPromotionInput,
    DatasetSetupCommand,
)

router = APIRouter()

# The one media type of the promotion's newline-delimited JSON records.
PROMOTION_MEDIA_TYPE = "application/x-ndjson"


class EmptyRequest(BaseModel):
    """The empty body of one maintenance request, so a body with any field is refused."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class DatasetMigrateRequest(DatasetMigrateInput):
    """One requested migration of one role's dataset or of the configured bootstrap database."""


class DatasetDeleteRequest(DatasetDeleteInput):
    """One requested deletion of a listed non-selected dataset and its Working confirmation."""


class DatasetCopyRequest(DatasetCopyInput):
    """One requested copy of one listed source dataset to Working."""


class DatasetPromotionRequest(DatasetPromotionInput):
    """One requested promotion of one listed source dataset and its restart confirmation."""


@router.get("/api/datasets")
def inventory(request: Request, response: Response) -> CommandResult:
    """Run the fixed retained-dataset listing once and return its transient outcome."""
    response.headers.update(NO_STORE_HEADERS)
    return request.app.state.commands.run(
        DatasetListCommand(kind="datasets-list"), automatic=automatic_read(request)
    )


@router.post("/api/datasets/setup")
def setup(request: Request, response: Response, body: EmptyRequest) -> CommandResult:
    """Run the fixed selected-dataset enrollment once and return its transient outcome."""
    response.headers.update(NO_STORE_HEADERS)
    return request.app.state.commands.run(DatasetSetupCommand(kind="datasets-setup"))


@router.post("/api/datasets/migrate")
def migrate(request: Request, response: Response, body: DatasetMigrateRequest) -> CommandResult:
    """Run the fixed migration of one named role or the configured database once."""
    response.headers.update(NO_STORE_HEADERS)
    return request.app.state.commands.run(
        DatasetMigrateCommand(kind="datasets-migrate", role=body.role)
    )


@router.post("/api/datasets/delete")
def delete(request: Request, response: Response, body: DatasetDeleteRequest) -> CommandResult:
    """Run the fixed single-dataset deletion once and return its transient outcome."""
    response.headers.update(NO_STORE_HEADERS)
    return request.app.state.commands.run(
        DatasetDeleteCommand(
            kind="datasets-delete",
            dataset_id=body.dataset_id,
            confirm_working=body.confirm_working,
        )
    )


@router.post("/api/datasets/copy-to-working")
def copy_to_working(
    request: Request, response: Response, body: DatasetCopyRequest
) -> CommandResult:
    """Run the fixed copy to Working once and return its transient outcome."""
    response.headers.update(NO_STORE_HEADERS)
    return request.app.state.commands.run(
        DatasetCopyCommand(
            kind="datasets-copy-to-working", source_dataset_id=body.source_dataset_id
        )
    )


@router.post("/api/datasets/copy-to-selected")
def copy_to_selected(request: Request, body: DatasetPromotionRequest) -> StreamingResponse:
    """Stream one admitted promotion's coarse steps and then its one terminal result.

    The producer starts when the response body starts, after admission, so a refused request runs no
    command. It runs the fixed command once and queues the terminal result after the runner's single
    log record. A run that fails outside its own result path, notably a log-write failure, queues
    one failure result carrying the operator error class instead of its message, and is neither
    retried nor logged again. The consumer ends at that terminal record and joins the finished
    producer. An abandoned iteration cancels the read alone, never the producer.
    """
    records: Queue[dict[str, Any]] = Queue()
    command = DatasetPromotionCommand(
        kind="datasets-copy-to-selected",
        source_dataset_id=body.source_dataset_id,
        confirm_restart=body.confirm_restart,
    )

    def produce() -> None:
        try:
            result = request.app.state.commands.run(
                command, on_progress=lambda step: records.put({"step": step})
            )
        except Exception as exc:
            result = CommandResult(
                exit_code=1,
                report=None,
                failure_line=format_operator_error(exc),
                guidance_line=operator_guidance(
                    "dataset-promotion", configuration_error=isinstance(exc, ValidationError)
                ),
            )
        records.put({"result": result.model_dump(mode="json")})

    def stream() -> Iterator[str]:
        worker = threading.Thread(target=produce, name="dataset-promotion", daemon=False)
        worker.start()
        while True:
            record = records.get()
            yield json.dumps(record, separators=(",", ":")) + "\n"
            if "result" in record:
                break
        worker.join()

    return StreamingResponse(
        stream(), media_type=PROMOTION_MEDIA_TYPE, headers=dict(NO_STORE_HEADERS)
    )
