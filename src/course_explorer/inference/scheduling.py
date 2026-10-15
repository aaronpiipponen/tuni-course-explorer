"""Strict processing-marker, cycle, and target-checkpoint DTOs plus their pure helpers.

This module owns the closed scheduling contract that the inference job and stage work consume:
the teaching-text processing marker (a scheduling flag, not a coverage claim),
the marker's nullable operator disposition decision (``done``/``failed``, or NULL for automatic),
the durable processing-cycle and per-target stage checkpoints, and the pure membership/identity
helpers. The DTOs carry only
canonical group IDs, lowercase digests, aware timestamps, and the already-validated selection
payloads.

The teaching-text-only hash excludes course code, source ID/hash, origin, translation
model/time, academic year/activity, generator configuration, and official prerequisite structure, so
calendar rollover or a generation prompt/model change alone can never reset a marker while an
effective teaching-text change always does.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

from course_explorer.config import (
    InferenceContextSettings,
    InferenceRerankInputSettings,
    InferenceRerankSettings,
    InferenceSelectionSettings,
)
from course_explorer.hashing import canonical_json_sha256
from course_explorer.inference.failures import FailureReason, FailureStage
from course_explorer.inference.operational import (
    OperationalPoolInput,
    OperationalTargetInput,
)
from course_explorer.validation import require_error_type as _require_error_type
from course_explorer.validation import require_sha256 as _require_sha256
from course_explorer.validation import require_text as _require_text

# The fixed protocol version of the checkpoint DTOs. It participates in the cycle input digest so a
# checkpoint schema change creates a new cycle.
PROCESSING_CHECKPOINT_SCHEMA_VERSION = 2

_MAX_ERROR_TYPE_LENGTH = 200

MultiviewState = Literal["pending", "completed", "failed"]
RerankState = Literal["pending", "completed", "skipped", "failed"]
InferenceState = Literal["pending", "completed", "skipped", "failed"]
CycleStage = Literal["multiview", "rerank", "inference", "publication", "complete"]

# The two explicit operator decisions a canonical target's processing marker may carry. ``None``
# (NULL) means no override, i.e. ordinary automatic scheduling.
TargetDisposition = Literal["done", "failed"]


class _SchedulingModel(BaseModel):
    """Frozen, closed, strict DTO base for the processing/checkpoint contract."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


def _membership_selection(
    processed: bool,
    candidate_group_ids: Sequence[str],
    markers: Mapping[str, CourseProcessingRecord],
) -> bool:
    """Share one predicate: run when own marker is FALSE or any supplied member is FALSE."""
    if not processed:
        return True
    return any(not markers[group_id].processed for group_id in candidate_group_ids)


def select_rerank(
    processed: bool,
    candidate_group_ids: Sequence[str],
    markers: Mapping[str, CourseProcessingRecord],
) -> bool:
    """Return whether a target's rerank stage must run under the live membership filter."""
    return _membership_selection(processed, candidate_group_ids, markers)


def select_inference(
    processed: bool,
    candidate_group_ids: Sequence[str],
    markers: Mapping[str, CourseProcessingRecord],
) -> bool:
    """Return whether a target's inference stage must run under the live membership filter."""
    return _membership_selection(processed, candidate_group_ids, markers)


class CourseProcessingRecord(_SchedulingModel):
    """One canonical course's teaching-text processing marker and accepted pointer."""

    group_id: str
    teaching_text_sha256: str
    processed: bool
    was_active: bool
    accepted_proposal_id: UUID | None
    disposition: TargetDisposition | None = None

    @field_validator("group_id")
    @classmethod
    def validate_group_id(cls, value: str) -> str:
        return _require_text(value, "processing group_id")

    @field_validator("teaching_text_sha256")
    @classmethod
    def validate_text_hash(cls, value: str) -> str:
        return _require_sha256(value, "processing teaching_text_sha256")


class ProcessingCycleRecord(_SchedulingModel):
    """One durable processing cycle and its current global stage."""

    cycle_id: UUID
    input_sha256: str
    stage: CycleStage

    @field_validator("input_sha256")
    @classmethod
    def validate_input_hash(cls, value: str) -> str:
        return _require_sha256(value, "cycle input_sha256")


class ProcessingTargetState(_SchedulingModel):
    """The per-target cycle/group/three-stage-state projection without any payload."""

    cycle_id: UUID
    target_group_id: str
    multiview_state: MultiviewState
    rerank_state: RerankState
    inference_state: InferenceState

    @field_validator("target_group_id")
    @classmethod
    def validate_target_group_id(cls, value: str) -> str:
        return _require_text(value, "target_group_id")


class ProcessingTargetRecord(ProcessingTargetState):
    """One per-target checkpoint with its stage payloads and planned-work pointer.

    The repository transition owner decides payload/failure policy once. This DTO is a shape carrier
    so consumed payloads may be absent and a completed inference keeps its planned generation key.
    """

    pool_input: OperationalPoolInput | None
    target_input: OperationalTargetInput | None
    generation_work_key_sha256: str | None
    proposal_id: UUID | None
    error_type: str | None

    @field_validator("generation_work_key_sha256")
    @classmethod
    def validate_planned_key(cls, value: str | None) -> str | None:
        return None if value is None else _require_sha256(value, "generation_work_key_sha256")

    @field_validator("error_type")
    @classmethod
    def validate_error_type(cls, value: str | None) -> str | None:
        return (
            None if value is None else _require_error_type(value, max_length=_MAX_ERROR_TYPE_LENGTH)
        )


class TargetFailureRecord(_SchedulingModel):
    """One append-only retained summary of a failed target episode.

    It is failure history, not a checkpoint, model attempt or work identity, and it is retained through
    a success or stop. For generation it is one row per failed whole-target attempt. A bounded
    multiview/rerank/preparation stage keeps one summary row per pass. ``stage`` is stored verbatim,
    including ``inference_preparation``.
    """

    failure_id: UUID
    cycle_id: UUID
    target_group_id: str
    stage: FailureStage
    attempt_count: int
    error_type: str
    reason: FailureReason
    exhausted: bool
    created_at: datetime

    @field_validator("target_group_id")
    @classmethod
    def validate_failure_group_id(cls, value: str) -> str:
        return _require_text(value, "target failure target_group_id")

    @field_validator("attempt_count")
    @classmethod
    def validate_failure_attempt_count(cls, value: int) -> int:
        if value < 1:
            raise ValueError("target failure attempt_count must be positive")
        return value

    @field_validator("error_type")
    @classmethod
    def validate_failure_error_type(cls, value: str) -> str:
        return _require_error_type(value, max_length=_MAX_ERROR_TYPE_LENGTH)

    @field_validator("created_at")
    @classmethod
    def validate_failure_created_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("target failure created_at must be timezone-aware")
        return value


def processing_cycle_input_sha256(
    catalogue_identity_sha256: str,
    embedding_state_sha256: str,
    *,
    selection: InferenceSelectionSettings,
    context_settings: InferenceContextSettings,
    rerank_input: InferenceRerankInputSettings,
    rerank_settings: InferenceRerankSettings,
) -> str:
    """Hash the selection/embedding compatibility inputs of one processing cycle.

    The digest excludes generation configuration, prompt version, and controller
    revision: a generation model/prompt/settings change alone must never force a new cycle or reset a
    marker. Catalogue identity, the embedding-state fingerprint, and the selection/context/
    rerank settings are the only compatibility inputs.
    """
    _require_sha256(catalogue_identity_sha256, "catalogue_identity_sha256")
    _require_sha256(embedding_state_sha256, "embedding_state_sha256")
    return canonical_json_sha256(
        {
            "checkpoint_schema_version": PROCESSING_CHECKPOINT_SCHEMA_VERSION,
            "catalogue_identity_sha256": catalogue_identity_sha256,
            "embedding_state_sha256": embedding_state_sha256,
            "selection": selection.model_dump(mode="json"),
            "context": context_settings.model_dump(mode="json"),
            "rerank_input": rerank_input.model_dump(mode="json"),
            "rerank": rerank_settings.model_dump(mode="json"),
        }
    )
