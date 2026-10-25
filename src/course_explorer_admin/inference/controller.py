"""Closed text-free controller contracts for remote prerequisite inference.

This module owns the durable inference session/state schemas and the strict loaders for one
detached inference PC window. It reuses the shared ``WorkerControllerStatus`` base, the neutral
``WorkerControl`` record, and the canonical shared-dataset session owner. It adds the
inference-owned configuration fingerprint and the job-progress and coverage
observation. The measured rate and ETA are derived for the named stage alone. Every DTO is frozen
and closed.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Literal

from pydantic import Field, computed_field, field_validator, model_validator

from course_explorer.administration import load_private_model
from course_explorer.config import (
    load_administrative_dataset_settings,
    load_embedding_settings,
    load_inference_context_settings,
    load_inference_rerank_input_settings,
    load_inference_rerank_settings,
    load_inference_selection_settings,
    load_inference_settings,
)
from course_explorer.datasets import DatasetId, DatasetSha256
from course_explorer.hashing import canonical_json_sha256
from course_explorer.inference.diagnostics import InferenceCoverageSummary
from course_explorer.inference.job import InferenceJobProgress
from course_explorer.inference.prompts import load_prompt_pack
from course_explorer_admin.remote import (
    WorkerControllerStatus,
    WorkerDatasetSession,
    _ControllerModel,
    load_worker_dataset_session,
    worker_dataset_session_directory,
)

_STAGE_LIFECYCLES = frozenset({"multiview", "rerank", "inference"})


class InferenceControllerPolicy(_ControllerModel):
    """Immutable canonical worker policy for one shared-dataset inference session.

    The canonical session identity lives in the neutral ``WorkerDatasetSession`` and the derived
    database name in the administrative settings. This policy carries the retained-session
    configuration fingerprint, separate from the catalogue scheduling identity: a generation
    model/prompt/settings change alone alters the fingerprint, so a retained PC window prepared
    under a different configuration cannot continue.
    """

    schema_version: Literal[2]
    session_id: DatasetId
    configuration_sha256: DatasetSha256


class InferenceStageProgress(_ControllerModel):
    """One compute-stage progress projection: durable done/total/remaining counts."""

    stage: Literal["multiview", "rerank", "inference"]
    done: int
    total: int
    remaining: int


class InferenceControllerStatus(WorkerControllerStatus):
    """Inference operator status adding the current stage's progress and coverage.

    The shared stage-neutral fields, validators and remaining-count derive live in
    ``WorkerControllerStatus``. This subclass exposes one per-stage projection and overrides
    ``remaining_count``, throughput and ETA so they all describe the named compute stage from its
    completed and skipped counters, and publication/complete, idle/imported and
    unknown observations report no rate or ETA. ``desired_count``/``completed_count`` cover whole
    results and are separate from the stage counters.
    """

    progress: InferenceJobProgress | None = None
    coverage: InferenceCoverageSummary | None = None
    stage_processed_count: int = Field(default=0, ge=0)

    @field_validator("coverage", mode="before")
    @classmethod
    def coerce_coverage_json(cls, value: object) -> object:
        """Coerce the nested strict coverage DTO's JSON array back to its tuple field.

        ``InferenceCoverageSummary`` is a strict product DTO whose ``generation_counts`` tuple
        rejects a JSON array under strict validation even though in-process construction accepts
        one. Converting it here lets the strict loader serve status files.
        """
        if isinstance(value, Mapping) and isinstance(value.get("generation_counts"), list):
            return {**value, "generation_counts": tuple(value["generation_counts"])}
        return value

    @model_validator(mode="before")
    @classmethod
    def drop_inference_derived_fields(cls, value: object) -> object:
        """Strip the two inference-only computed fields before strict loading."""
        if isinstance(value, Mapping):
            return {
                key: item
                for key, item in value.items()
                if key not in {"stages", "stages_remaining"}
            }
        return value

    @computed_field
    @property
    def stages(self) -> tuple[InferenceStageProgress, ...]:
        """Return the three compute-stage projections in pipeline order, empty before known
        progress.

        ``done`` counts completed targets plus targets whose stage state is ``skipped``, never
        failures. ``remaining`` subtracts only the targets this invocation exhausted at that stage
        or an upstream stage, so a retained retryable failure counts as remaining.
        """
        if self.progress is None:
            return ()
        total = self.progress.desired_targets

        def remaining(done: int, not_remaining: int) -> int:
            return max(0, total - done - not_remaining)

        multiview_done = self.progress.multiview_completed
        rerank_done = self.progress.rerank_completed + self.progress.rerank_skipped
        inference_done = self.progress.inference_completed + self.progress.inference_skipped
        return (
            InferenceStageProgress(
                stage="multiview",
                done=multiview_done,
                total=total,
                remaining=remaining(multiview_done, self.progress.multiview_not_remaining),
            ),
            InferenceStageProgress(
                stage="rerank",
                done=rerank_done,
                total=total,
                remaining=remaining(rerank_done, self.progress.rerank_not_remaining),
            ),
            InferenceStageProgress(
                stage="inference",
                done=inference_done,
                total=total,
                remaining=remaining(inference_done, self.progress.inference_not_remaining),
            ),
        )

    @computed_field
    @property
    def stages_remaining(self) -> tuple[str, ...]:
        """Return the compute stages with remaining work plus publication, unless the cycle is
        complete."""
        if self.progress is None:
            return ()
        stages = tuple(stage.stage for stage in self.stages if stage.remaining > 0)
        if self.progress.stage == "complete":
            return stages
        return (*stages, "publication")

    @computed_field
    @property
    def remaining_count(self) -> int | None:
        """Return the current compute stage's remaining count, or ``None`` outside a compute
        stage."""
        if self.progress is None or self.progress.stage not in _STAGE_LIFECYCLES:
            return None
        return next(stage.remaining for stage in self.stages if stage.stage == self.progress.stage)

    def _stage_remaining(self) -> int | None:
        """Return the current compute stage's remaining count, or ``None`` outside a compute
        stage."""
        return self.remaining_count

    @computed_field
    @property
    def items_per_second(self) -> float | None:
        """Derive throughput for the named current stage only, else ``None``."""
        if self.progress is None or self.progress.stage not in _STAGE_LIFECYCLES:
            return None
        if self.lifecycle != "running":
            return None
        if self.stage_processed_count <= 0 or self.active_seconds <= 0:
            return None
        return self.stage_processed_count / self.active_seconds

    @computed_field
    @property
    def projected_remaining_seconds(self) -> float | None:
        """Derive remaining seconds for the named current stage only, else ``None``."""
        if self.lifecycle != "running":
            return None
        remaining = self._stage_remaining()
        rate = self.items_per_second
        if remaining is None or rate is None:
            return None
        return remaining / rate


class InferenceControllerWorkerState(InferenceControllerStatus):
    """Text-free inference worker lifecycle state with the exact process matrix.

    Schema 2 is the inference matrix: starting and running carry display process identifiers,
    a starting or running state requires the runner, a runtime is optional (multiview and external
    route work use no local model), and failed carries a safe error type. Ownership files prove
    quiescence.
    """

    schema_version: Literal[2]
    session_id: DatasetId
    lifecycle: Literal[
        "prepared",
        "starting",
        "running",
        "paused",
        "stopped",
        "completed",
        "failed",
        "cleaned",
    ]
    runner_pid: int | None = None
    runtime_pid: int | None = None

    @field_validator("runner_pid", "runtime_pid")
    @classmethod
    def validate_pid(cls, value: int | None) -> int | None:
        if value is not None and value <= 0:
            raise ValueError("process identifiers must be positive when set")
        return value

    @model_validator(mode="after")
    def validate_lifecycle_matrix(self) -> InferenceControllerWorkerState:
        """Enforce each inference lifecycle's process/error pattern."""
        runtime_pid = self.runtime_pid is not None
        error_type = self.error_type is not None
        if self.lifecycle in {"starting", "running"}:
            if self.runner_pid is None or error_type:
                raise ValueError("starting/running state requires a runner and no error")
        elif self.lifecycle == "failed":
            if self.runner_pid is not None or runtime_pid or not error_type:
                raise ValueError("failed state requires only a safe error type")
        elif self.runner_pid is not None or runtime_pid or error_type:
            raise ValueError("unloaded state records no processes or error")
        return self


def inference_configuration_sha256() -> str:
    """Hash the retained-session configuration fingerprint for one inference PC window.

    This is retained-session compatibility. It excludes the catalogue and embedding-state identities
    owned by the product scheduling cycle hash.
    """
    generation = load_inference_settings()
    mapping = {
        "generation": generation.model_dump(mode="json"),
        "embedding": load_embedding_settings().model_dump(mode="json"),
        "context": load_inference_context_settings().model_dump(mode="json"),
        "selection": load_inference_selection_settings().model_dump(mode="json"),
        "rerank": load_inference_rerank_settings().model_dump(mode="json"),
        "rerank_input": load_inference_rerank_input_settings().model_dump(mode="json"),
        "prompt_content_sha256": load_prompt_pack(
            generation.inference_prompt_version
        ).content_sha256,
    }
    return canonical_json_sha256(mapping)


def load_inference_controller_policy(path: Path) -> InferenceControllerPolicy:
    """Load the immutable canonical worker policy from its strict file."""
    return load_private_model(path, InferenceControllerPolicy)


def load_inference_controller_status(path: Path) -> InferenceControllerStatus:
    """Load one operator status from its strict file."""
    return load_private_model(path, InferenceControllerStatus)


def load_inference_controller_worker_state(path: Path) -> InferenceControllerWorkerState:
    """Load the worker lifecycle state from its strict file."""
    return load_private_model(path, InferenceControllerWorkerState)


def load_inference_dataset_session(
    session_id: str,
) -> tuple[WorkerDatasetSession, InferenceControllerPolicy, Path]:
    """Load one canonical inference session, its policy, and its shared session directory.

    It requires an inference-stage session whose derived worker database name is the configured one,
    whose requested/session/policy identities agree, and which is unbounded, so a foreign, bounded,
    or mismatched session is never prepared, run, or cleaned as this one.
    """
    settings = load_administrative_dataset_settings()
    directory = worker_dataset_session_directory(session_id)
    session = load_worker_dataset_session(session_id)
    policy = load_inference_controller_policy(directory / "policy.json")
    if session.session_id != session_id or policy.session_id != session_id:
        raise ValueError(
            "canonical session or policy identity does not match the requested session"
        )
    if session.stage != "inference":
        raise ValueError("canonical session is not an inference session")
    if session.database_name != settings.database_name(session_id, worker=True):
        raise ValueError("canonical session database name is not the configured derived name")
    if session.course_limit is not None:
        raise ValueError("canonical inference session must not be bounded")
    return session, policy, directory
