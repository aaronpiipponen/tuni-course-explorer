"""Strict, immutable inference-evidence contracts and canonical run/work identities.

This module owns the DTO boundary between the frozen inference runtime/result/prompt/provider
contracts declared by this package and durable inference evidence. It defines one shared execution
identity derived from validated configuration and the selected execution, per-target work requests
whose exact execution and transient input identity own reuse, and the two normal completion states
of one completed generation. The ``request_payload`` JSONB carries a completion payload: before
composition it holds the descriptors and the uncomposed validated result for zero-model recovery.
After composition both are absent and only the generated time, target teaching digest and candidate
count remain for publication/seed coverage. Canonical JSON hashing lives in the neutral
``course_explorer.hashing`` owner. Nothing here reads configuration from the environment, calls a
model, calculates a target, or writes any official or final product store.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Self
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from course_explorer.config import InferenceSettings
from course_explorer.enums import InferenceWorkStatus
from course_explorer.hashing import canonical_json_sha256, require_json_compatible
from course_explorer.inference.context import RequestCourseDescriptors
from course_explorer.inference.domain import (
    InferenceTargetResultV2,
)
from course_explorer.validation import (
    require_aware as _require_aware,
)
from course_explorer.validation import (
    require_sha256 as _require_sha256,
)
from course_explorer.validation import (
    require_text as _require_text,
)


class _EvidenceModel(BaseModel):
    """Frozen, closed, strict DTO base for the inference evidence boundary."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class InferenceWorkClaimAction(StrEnum):
    """Outcome of one global matching-work claim inside a shared execution."""

    CREATED = "created"
    EXISTING = "existing"
    REUSED = "reused"


class InferenceExecutionProfile(_EvidenceModel):
    """One validated execution profile selecting exactly one accepted executor.

    ``route`` is the neutral current-executor identity the selected route records (a local fit key or
    another configured route). ``model_identity`` and ``runtime_identity`` are that route's
    exact provider identities. No route credential is ever a member, and a route change invalidates
    work recorded under another route.
    """

    route: str
    model_identity: str
    runtime_identity: str

    @field_validator("route", "model_identity", "runtime_identity")
    @classmethod
    def validate_identity_text(cls, value: str) -> str:
        """Require meaningful nonblank execution identities and a recorded route token."""
        return _require_text(value, "execution identity")


class InferencePipelineRunSpec(_EvidenceModel):
    """One shared execution identity derived from validated settings and the selected execution.

    It carries only the coarse configuration identity consumed by claim/reuse and mixed-result
    attribution: the model/runtime/prompt/schema/pipeline identity plus the route. Catalogue
    identity, activity context and full operational configuration are absent, so
    unrelated catalogue or operational changes never invalidate retained work. The rendered
    request carries content identity.
    """

    model_identity: str
    runtime_identity: str
    prompt_version: str
    schema_version: str
    pipeline_version: str
    configuration: dict[str, object]

    @field_validator(
        "model_identity",
        "runtime_identity",
        "prompt_version",
        "schema_version",
        "pipeline_version",
    )
    @classmethod
    def validate_identity_text(cls, value: str) -> str:
        """Require meaningful nonblank identity and version text."""
        return _require_text(value, "run spec identity")

    @field_validator("configuration")
    @classmethod
    def validate_configuration(cls, value: dict[str, object]) -> dict[str, object]:
        """Require exact JSON-compatible configuration evidence."""
        require_json_compatible(value, "configuration")
        return value

    @classmethod
    def from_contracts(
        cls,
        settings: InferenceSettings,
        *,
        execution: InferenceExecutionProfile,
    ) -> Self:
        """Derive one shared execution spec from validated settings and the selected route.

        Model and runtime identities and the recorded route come from the selected execution route,
        and the version fields come from validated settings. This never reads configuration files
        or the process environment.
        """
        return cls(
            model_identity=execution.model_identity,
            runtime_identity=execution.runtime_identity,
            prompt_version=settings.inference_prompt_version,
            schema_version=settings.inference_schema_version,
            pipeline_version=settings.inference_pipeline_version,
            configuration={"route": execution.route},
        )


class InferenceTargetWorkRequest(_EvidenceModel):
    """One target's canonical identity and activity context."""

    target_group_id: str
    activity_as_of_academic_year_start: int = Field(gt=0)
    activity_window_years: int = Field(gt=0)

    @field_validator("target_group_id")
    @classmethod
    def validate_target_group_id(cls, value: str) -> str:
        """Require a meaningful canonical target identity."""
        return _require_text(value, "target_group_id")


class InferenceRequestEvidence(_EvidenceModel):
    """The exact transient request payload one generation call rendered, never persisted.

    It exists only in memory between rendering and the provider call. The completion payload keeps
    no prompt text.
    """

    system_prompt: str
    user_prompt: str
    schema_name: str
    json_schema: dict[str, object]

    @field_validator("system_prompt", "user_prompt")
    @classmethod
    def validate_prompt(cls, value: str) -> str:
        """Require meaningful nonblank prompt text."""
        return _require_text(value, "request prompt")

    @field_validator("schema_name")
    @classmethod
    def validate_schema_name(cls, value: str) -> str:
        """Require a meaningful nonblank schema name."""
        return _require_text(value, "schema_name")

    @field_validator("json_schema")
    @classmethod
    def validate_json_schema(cls, value: dict[str, object]) -> dict[str, object]:
        """Require a recursively string-keyed, finite JSON schema without repairing it."""
        require_json_compatible(value, "json_schema")
        return value


class InferenceCompletionFacts(_EvidenceModel):
    """The facts one completed generation leaves for publication and seed coverage."""

    target_teaching_text_sha256: str
    candidate_count: int = Field(ge=0)

    @field_validator("target_teaching_text_sha256")
    @classmethod
    def validate_teaching_text_sha256(cls, value: str) -> str:
        """Require the exact text-only target teaching digest."""
        return _require_sha256(value, "completion target_teaching_text_sha256")


class InferenceCompletionPayload(_EvidenceModel):
    """One completed generation's stored payload in its current lifecycle state.

    Before composition the descriptors and the uncomposed validated result are both present for
    zero-model recovery. After composition both are absent and only the facts remain.
    """

    facts: InferenceCompletionFacts
    descriptors: RequestCourseDescriptors | None = None
    result: InferenceTargetResultV2 | None = None

    @model_validator(mode="after")
    def validate_state(self) -> InferenceCompletionPayload:
        """Require the descriptors and result to be present together or absent together."""
        if (self.descriptors is None) != (self.result is None):
            raise ValueError(
                "a completion payload keeps descriptors and result together until composition"
            )
        return self


class InferencePipelineRunRecord(_EvidenceModel):
    """One persisted shared execution identity row."""

    run_id: UUID
    spec: InferencePipelineRunSpec
    run_identity_sha256: str


class InferenceTargetWorkRecord(_EvidenceModel):
    """One persisted target-work row: matching-work authority and generation resumability."""

    work_id: UUID
    created_by_run_id: UUID
    target_course_id: UUID
    request: InferenceTargetWorkRequest
    work_key_sha256: str
    status: InferenceWorkStatus


class InferenceModelAttemptRecord(_EvidenceModel):
    """One persisted completion row and its actual generated time."""

    attempt_id: UUID
    target_work_id: UUID
    payload: InferenceCompletionPayload
    finished_at: datetime

    @field_validator("finished_at")
    @classmethod
    def validate_finished_at(cls, value: datetime) -> datetime:
        """Require a timezone-aware generated time."""
        return _require_aware(value, "completion finished_at")


class InferenceWorkClaim(_EvidenceModel):
    """One global matching-work claim: created, existing, or reused completed evidence."""

    action: InferenceWorkClaimAction
    work: InferenceTargetWorkRecord


def run_identity_sha256(spec: InferencePipelineRunSpec) -> str:
    """Hash the shared execution identity that controls matching-work reuse."""
    return canonical_json_sha256(
        {
            "model_identity": spec.model_identity,
            "runtime_identity": spec.runtime_identity,
            "prompt_version": spec.prompt_version,
            "schema_version": spec.schema_version,
            "pipeline_version": spec.pipeline_version,
            "configuration": spec.configuration,
        }
    )


def work_key_sha256(
    request: InferenceTargetWorkRequest, run_identity: str, input_sha256: str
) -> str:
    """Hash one target's global matching-work identity: execution identity plus exact input."""
    _require_sha256(run_identity, "run_identity")
    _require_sha256(input_sha256, "input_sha256")
    return canonical_json_sha256(
        {
            "target_group_id": request.target_group_id,
            "activity_as_of_academic_year_start": request.activity_as_of_academic_year_start,
            "activity_window_years": request.activity_window_years,
            "input_sha256": input_sha256,
            "run_identity_sha256": run_identity,
        }
    )
