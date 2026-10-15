"""One incremental product job that drives the inference stages to a finished cycle.

This module owns the single resumable product job over the stage owners: it prepares one
operational catalogue and its embedding readiness once, reconciles teaching-text processing markers,
resumes or begins one serial processing cycle, and then advances only the durable cycle's real
current stage and its forward successors through the multiview, cross-encoder rerank and whole-target
inference stages under the live membership filter. It composes and accepts each completed whole-target
result through the proposal owner and publishes the retained cohort once through the sole
publisher. Catalogue/selection compatibility is checked once at entry, and a resumed stage never
requests a backward barrier or repeats a finished stage.

The job is provider-neutral: a caller injects an :class:`InferenceJobRuntime` for the
owned local generation/rerank services and live admission callbacks. It contains no subprocess, SSH,
Compose, administrative, or model-policy logic, and it never loads a route credential or alternative
route setting at entry. An oversize route is supplied as an explicit callable only when a caller owns
one. A declined request is the cooperative :class:`RequestNotStarted` yield: the job preserves
the pending/failed unit and its already durable completed result and returns the unfinished cycle
normally. Whole-target generation failures are recorded once per failed attempt by the sole writer
(the operator's history). The writer's bounded ``TargetPassFailure`` is only an exhausted-pass summary
with no extra episode, while bounded multiview/rerank/preparation stages keep one summary episode for
the pass.
Only a successfully completed cycle bulk-marks the catalogue processed. An explicit operator
disposition decision is honoured, never re-derived: a FAILED target is visited last and skipped
without any admission, request or episode, and a DONE target already carries a completed inference
state.

Observation state is transient. The job holds one unit's full checkpoint
payload at a time. The cross-unit maps hold only the payload-free stage-state projection, transition
deltas are counted in a process-local :class:`collections.Counter`, and the reported stage seconds
accumulate only admitted atomic-unit work through an injected aware clock, never observer/checkpoint
idle or previous-process time. The maps and counters are process-local observations.
"""

from __future__ import annotations

import json
import sys
import time
from collections import Counter
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from datetime import datetime
from typing import Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session, sessionmaker

from course_explorer.administration import utc_now
from course_explorer.config import (
    load_embedding_settings,
    load_inference_context_settings,
    load_inference_rerank_input_settings,
    load_inference_rerank_settings,
    load_inference_selection_settings,
    load_inference_settings,
)
from course_explorer.curriculum_repository import CurriculumRepository
from course_explorer.embeddings.generation import build_course_embedding_chunks
from course_explorer.embeddings.repository import CourseEmbeddingRepository
from course_explorer.enums import InferenceWorkStatus
from course_explorer.http_retry import RequestNotStarted
from course_explorer.inference.context_repository import InferenceCandidateRepository
from course_explorer.inference.evidence import run_identity_sha256, work_key_sha256
from course_explorer.inference.evidence_repository import InferenceEvidenceRepository
from course_explorer.inference.failures import (
    FailureReason,
    FailureStage,
    InferenceTargetsFailed,
    TargetContextError,
    TargetPassFailure,
    TargetPreparationFailure,
    TargetSelectionError,
)
from course_explorer.inference.operational import (
    prepare_operational_catalogue,
    rerank_operational_pool,
    select_operational_multiview_pool,
)
from course_explorer.inference.prompts import load_prompt_pack
from course_explorer.inference.proposal_commands import compose_proposal_from_work
from course_explorer.inference.proposals import TargetProposal
from course_explorer.inference.provider import (
    InferenceOutputError,
    InferenceTargetRequestError,
    RerankProvider,
)
from course_explorer.inference.publication import publish_current_cohort
from course_explorer.inference.routing import (
    GenerationRuntimeControl,
    OversizeRouteFactory,
    run_routed_operational_target,
)
from course_explorer.inference.scheduling import (
    CourseProcessingRecord,
    CycleStage,
    ProcessingCycleRecord,
    ProcessingTargetRecord,
    ProcessingTargetState,
    TargetFailureRecord,
    processing_cycle_input_sha256,
    select_inference,
    select_rerank,
)
from course_explorer.inference.scheduling_repository import InferenceSchedulingRepository
from course_explorer.inference.target_pass import TargetWorkIdentity
from course_explorer.teaching_text.repository import DerivedTranslationRepository
from course_explorer.teaching_text.service import TeachingTextService
from course_explorer.validation import require_aware as _require_aware


class InferenceJobRuntime(GenerationRuntimeControl, Protocol):
    """One owned worker runtime's idempotent load/unload and elapsed-request scope control."""

    def start_rerank(self) -> None: ...

    def stop_rerank(self) -> None: ...

    def request_scope(self, seconds: float) -> AbstractContextManager[None]: ...


class _JobModel(BaseModel):
    """Frozen, closed, strict DTO base for the incremental job boundary."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class InferenceJobProgress(_JobModel):
    """One read-only observation of the current cycle's work and completed-result coverage.

    This is observation, never a second durable counter store: the counters are derived from the
    in-memory state/marker maps, the process-local transition counter and the invocation-local
    exhausted set each time they are reported. ``failed_targets`` is the durable FAILED-target
    count. The three ``*_not_remaining`` counters name only targets this invocation actually exhausted,
    so a retained failure is retryable on re-entry and only current exhaustion (or a blocked
    downstream stage) leaves remaining work.
    """

    schema_version: Literal[1] = 1
    cycle_id: UUID
    stage: CycleStage
    desired_targets: int = Field(ge=0)
    multiview_completed: int = Field(ge=0)
    rerank_completed: int = Field(ge=0)
    rerank_skipped: int = Field(ge=0)
    inference_completed: int = Field(ge=0)
    inference_skipped: int = Field(ge=0)
    failed_targets: int = Field(ge=0)
    retained_complete_targets: int = Field(ge=0)
    active_stage_seconds: float = Field(ge=0.0, allow_inf_nan=False)
    measured_stage_completed: int = Field(default=0, ge=0)
    multiview_not_remaining: int = Field(default=0, ge=0)
    rerank_not_remaining: int = Field(default=0, ge=0)
    inference_not_remaining: int = Field(default=0, ge=0)


_STAGE_STATE_ATTRIBUTES = ("multiview_state", "rerank_state", "inference_state")

_UNIT_FAILURE_MESSAGE: dict[str, str] = {
    "multiview": "inference multiview unit failure",
    "rerank": "inference rerank unit failure",
    "inference": "inference unit failure",
}


def _has_failed(state: ProcessingTargetState) -> bool:
    """Return whether any of one target state's three stages is failed."""
    return "failed" in (
        state.multiview_state,
        state.rerank_state,
        state.inference_state,
    )


def _eligible(state: ProcessingTargetState, stage: CycleStage) -> bool:
    """Return whether one target's named stage is pending or failed on explicit entry.

    A stage is eligible only when its own state is pending/failed and its upstream dependency is
    completed. A failed dependency is blocked.
    """
    if stage == "multiview":
        return state.multiview_state in ("pending", "failed")
    if stage == "rerank":
        if state.multiview_state != "completed":
            return False
        return state.rerank_state in ("pending", "failed")
    if stage == "inference":
        if state.multiview_state != "completed" or state.rerank_state != "completed":
            return False
        return state.inference_state in ("pending", "failed")
    return False


def _ordered_units(
    states: dict[str, ProcessingTargetState],
    markers: dict[str, CourseProcessingRecord],
    stage: CycleStage,
) -> list[str]:
    """Return the target IDs one stage must visit, in that stage's scheduling order.

    Ordinary eligible targets are ordered TRUE-marker first and then by ID. At the inference stage an
    explicit operator FAILED decision is visited after every ordinary eligible target and is included
    even when its rerank was legitimately skipped, so the job can honour the terminal decision without
    admitting, recovering or generating anything for it. A DONE target already carries a completed
    inference state and is not eligible.
    """

    def key(group_id: str) -> tuple[bool, str]:
        return (not markers[group_id].processed, group_id)

    eligible = [group_id for group_id, state in states.items() if _eligible(state, stage)]
    if stage != "inference":
        return sorted(eligible, key=key)
    decided = {group_id for group_id in states if markers[group_id].disposition == "failed"}
    ordinary = sorted((group_id for group_id in eligible if group_id not in decided), key=key)
    decided_eligible = sorted((group_id for group_id in eligible if group_id in decided), key=key)
    decided_skipped = sorted(
        (group_id for group_id in decided if group_id not in eligible), key=key
    )
    return [*ordinary, *decided_eligible, *decided_skipped]


def run_inference_job(
    factory: sessionmaker[Session],
    *,
    runtime: InferenceJobRuntime,
    before_unit: Callable[[], bool],
    before_request: Callable[[], bool],
    on_checkpoint: Callable[[InferenceJobProgress], None],
    on_generation_attempt_checkpoint: Callable[[], None] | None = None,
    oversize_route: OversizeRouteFactory | None = None,
    clock: Callable[[], datetime] = utc_now,
) -> ProcessingCycleRecord:
    """Drive one resumable inference cycle through the stage owners.

    The whole run shares one prepared catalogue, one set of loaded settings, one prompt pack and one
    session factory. It never loads a route credential, starts a subprocess, reads the whole
    catalogue per unit, or publishes per target. A control refusal yields the current unfinished
    cycle. A real failure checkpoints only the executing nonterminal stage FAILED and re-raises.
    The owned runtime is always unloaded on exit. Only the durable cycle's real stage and its forward
    successors are dispatched, so reopening a retained stage never requests a backward barrier.
    ``oversize_route`` is the caller's explicit alternative route for a packet fitting neither local
    key, defaulting to the :class:`TargetContextError` capacity failure.
    ``on_generation_attempt_checkpoint`` is invoked after every committed whole-target generation
    failure so the worker's periodic reboot clock samples a safe failed-attempt checkpoint
    before the writer issues another request. A bounded-stage summary or unrelated notification is
    not this callback.
    """
    embedding_settings = load_embedding_settings()
    settings = load_inference_settings()
    context_settings = load_inference_context_settings()
    selection = load_inference_selection_settings()
    rerank_settings = load_inference_rerank_settings()
    rerank_input = load_inference_rerank_input_settings()
    prompt_pack = load_prompt_pack(settings.inference_prompt_version)

    curriculum = CurriculumRepository(factory)
    translations = DerivedTranslationRepository(factory)
    teaching_text = TeachingTextService(curriculum, translations)
    candidate_repository = InferenceCandidateRepository(factory)
    embedding_repository = CourseEmbeddingRepository(factory)
    evidence = InferenceEvidenceRepository(factory)
    repository = InferenceSchedulingRepository(factory)

    cycle: ProcessingCycleRecord | None = None
    try:
        catalogue = prepare_operational_catalogue(curriculum, teaching_text, embedding_settings)
        desired_chunks = build_course_embedding_chunks(
            catalogue.teaching_text_catalogue, embedding_settings
        )
        embedding_repository.require_current_chunks(desired_chunks)
        active_group_ids = sorted(
            group_id for group_id, course in catalogue.courses_by_group.items() if course.is_active
        )
        embedded_group_ids = {chunk.group_id for chunk in desired_chunks}
        missing_embeddings = [
            group_id for group_id in active_group_ids if group_id not in embedded_group_ids
        ]
        if missing_embeddings:
            raise ValueError(
                "embedding stage is required for active targets: " + ", ".join(missing_embeddings)
            )

        embedding_state = candidate_repository.embedding_state_sha256(
            catalogue.represented_courses,
            embedding_configuration_hash=catalogue.embedding_configuration_sha256,
        )
        cycle_input = processing_cycle_input_sha256(
            catalogue.catalogue_identity_sha256,
            embedding_state,
            selection=selection,
            context_settings=context_settings,
            rerank_input=rerank_input,
            rerank_settings=rerank_settings,
        )

        # The whole-catalogue marker read decides genuine empty-store seeding only. Reconciliation's
        # returned tuple is the authoritative current marker map, so no second full read happens.
        existing_markers = repository.read_processing()
        seed_proposals = {} if existing_markers else repository.read_seed_proposals()
        courses = tuple(catalogue.courses_by_group.values())
        markers = {
            record.group_id: record
            for record in repository.reconcile_courses(
                courses, catalogue.effective_by_group, seed_proposals=seed_proposals
            )
        }
        cycle = repository.begin_cycle(cycle_input, active_group_ids)
        states: dict[str, ProcessingTargetState] = {
            state.target_group_id: state for state in repository.list_target_states(cycle.cycle_id)
        }
        coverage = repository.read_coverage()
        if coverage.eligible_targets != len(active_group_ids):
            raise ValueError("coverage eligible targets do not match the active prepared catalogue")

        stage_state_counts: Counter[tuple[str, str]] = Counter(
            (attribute, getattr(state, attribute))
            for state in states.values()
            for attribute in _STAGE_STATE_ATTRIBUTES
        )
        failed_target_ids: set[str] = {
            group_id for group_id, state in states.items() if _has_failed(state)
        }
        # Process-local exhausted scope for this invocation: only IDs whose bounded stage failure
        # was actually exhausted here, never loaded from retained history.
        exhausted_ids: set[str] = set()
        # Active-target coverage only: an inactive retained pointer is scheduleable but is never
        # counted as a genuine active-target result.
        retained_complete_targets = coverage.retained_complete_targets
        stage_seconds = 0.0
        measured_stage_completed = 0

        def current_stage() -> CycleStage:
            return cycle.stage

        @contextmanager
        def unit_scope() -> Iterator[None]:
            """Accumulate one admitted unit's real work time between two aware clock samples."""
            nonlocal stage_seconds
            started = _require_aware(clock(), "inference job clock")
            try:
                yield
            finally:
                ended = _require_aware(clock(), "inference job clock")
                stage_seconds += max(0.0, (ended - started).total_seconds())

        def progress() -> InferenceJobProgress:
            # An explicit operator FAILED decision is never remaining at inference on any invocation,
            # independently of transient exhaustion, while its genuinely pending/failed upstream work
            # is counted. Invocation-local exhaustion is added once and never double-counts the
            # terminal decision.
            decided_failed = {
                group_id for group_id in states if markers[group_id].disposition == "failed"
            }
            multiview_not_remaining = 0
            rerank_not_remaining = 0
            inference_not_remaining = len(decided_failed)
            for group_id in exhausted_ids:
                state = states[group_id]
                if state.multiview_state == "failed":
                    multiview_not_remaining += 1
                    rerank_not_remaining += 1
                    if group_id not in decided_failed:
                        inference_not_remaining += 1
                elif state.rerank_state == "failed":
                    rerank_not_remaining += 1
                    if group_id not in decided_failed:
                        inference_not_remaining += 1
                elif state.inference_state == "failed" and group_id not in decided_failed:
                    inference_not_remaining += 1
            return InferenceJobProgress(
                cycle_id=cycle.cycle_id,
                stage=current_stage(),
                desired_targets=len(active_group_ids),
                multiview_completed=stage_state_counts[("multiview_state", "completed")],
                rerank_completed=stage_state_counts[("rerank_state", "completed")],
                rerank_skipped=stage_state_counts[("rerank_state", "skipped")],
                inference_completed=stage_state_counts[("inference_state", "completed")],
                inference_skipped=stage_state_counts[("inference_state", "skipped")],
                failed_targets=len(failed_target_ids),
                retained_complete_targets=retained_complete_targets,
                active_stage_seconds=stage_seconds,
                measured_stage_completed=measured_stage_completed,
                multiview_not_remaining=multiview_not_remaining,
                rerank_not_remaining=rerank_not_remaining,
                inference_not_remaining=inference_not_remaining,
            )

        def notify() -> None:
            on_checkpoint(progress())

        def load_record(group_id: str) -> ProcessingTargetRecord:
            """Read exactly one unit's durable checkpoint. Nothing is cached across units."""
            return repository.read_target(cycle.cycle_id, group_id)

        def apply_record(record: ProcessingTargetRecord) -> None:
            """Project one durable record into the state map and transition counters."""
            previous = states.get(record.target_group_id)
            if previous is None:
                for attribute in _STAGE_STATE_ATTRIBUTES:
                    stage_state_counts[(attribute, getattr(record, attribute))] += 1
            else:
                for attribute in _STAGE_STATE_ATTRIBUTES:
                    old = getattr(previous, attribute)
                    new = getattr(record, attribute)
                    if old != new:
                        stage_state_counts[(attribute, old)] -= 1
                        stage_state_counts[(attribute, new)] += 1
            states[record.target_group_id] = ProcessingTargetState(
                cycle_id=record.cycle_id,
                target_group_id=record.target_group_id,
                multiview_state=record.multiview_state,
                rerank_state=record.rerank_state,
                inference_state=record.inference_state,
            )
            if _has_failed(record):
                failed_target_ids.add(record.target_group_id)
            else:
                failed_target_ids.discard(record.target_group_id)

        def accept_record(
            record: ProcessingTargetRecord, proposal: TargetProposal, work_key: str
        ) -> None:
            """Accept one whole-target result and update the marker map and observations."""
            nonlocal retained_complete_targets
            previous_marker = markers.get(record.target_group_id)
            marker = repository.accept_target(cycle.cycle_id, record.target_group_id, proposal)
            markers[record.target_group_id] = marker
            if previous_marker is None or previous_marker.accepted_proposal_id is None:
                retained_complete_targets += 1
            apply_record(
                record.model_copy(
                    update={
                        "inference_state": "completed",
                        "proposal_id": proposal.proposal_id,
                        "generation_work_key_sha256": work_key,
                        "error_type": None,
                    }
                )
            )

        def yield_current() -> ProcessingCycleRecord:
            return repository.read_cycle(cycle.cycle_id)

        def record_failure(
            group_id: str,
            stage: Literal["multiview", "rerank", "inference"],
            exc: Exception,
        ) -> None:
            """Mark only the named executing stage FAILED while it is nonterminal."""
            record = repository.read_target(cycle.cycle_id, group_id)
            attribute = f"{stage}_state"
            if getattr(record, attribute) not in ("pending", "failed"):
                return
            failed = record.model_copy(
                update={attribute: "failed", "error_type": type(exc).__name__}
            )
            apply_record(repository.checkpoint(failed))

        def persist_target_failure(
            group_id: str,
            stage: FailureStage,
            attempt_count: int,
            error_type: str,
            reason: FailureReason,
            *,
            exhausted: bool,
        ) -> TargetFailureRecord:
            """Durably append one failure episode and project its checkpoint into the state map."""
            record, failure = repository.record_target_failure(
                cycle.cycle_id,
                group_id,
                stage=stage,
                attempt_count=attempt_count,
                error_type=error_type,
                reason=reason,
                exhausted=exhausted,
            )
            apply_record(record)
            return failure

        def log_target_failure(failure: TargetFailureRecord) -> None:
            """Emit one content-free structured JSON target-failure line from its owning row."""
            print(
                json.dumps(
                    {
                        "event": "inference_target_failure",
                        "target_group_id": failure.target_group_id,
                        "cycle_id": str(failure.cycle_id),
                        "stage": failure.stage,
                        "attempt_count": failure.attempt_count,
                        "error_type": failure.error_type,
                        "reason": failure.reason,
                    },
                    separators=(",", ":"),
                ),
                file=sys.stderr,
            )

        def record_exhausted(
            group_id: str,
            stage: FailureStage,
            attempt_count: int,
            error_type: str,
            reason: FailureReason,
            *,
            exhausted: bool,
        ) -> None:
            """Persist one bounded-stage episode, log it only when exhausted, and update the scope."""
            failure = persist_target_failure(
                group_id, stage, attempt_count, error_type, reason, exhausted=exhausted
            )
            if exhausted:
                exhausted_ids.add(group_id)
                log_target_failure(failure)
            notify()

        def on_generation_failure(
            record: ProcessingTargetRecord, failure: TargetFailureRecord
        ) -> None:
            """Project one committed per-attempt generation failure and checkpoint its reboot clock.

            This runs for EVERY committed generation failure, not only a transition to failed: the
            durable episode is already written, ``notify()`` republishes the stage state, and
            the worker's reboot clock samples the safe failed-attempt checkpoint before the
            writer is allowed another request. It adds no stored counter or progress field.
            """
            apply_record(record)
            if failure.exhausted:
                exhausted_ids.add(failure.target_group_id)
            log_target_failure(failure)
            notify()
            if on_generation_attempt_checkpoint is not None:
                on_generation_attempt_checkpoint()

        def retryable_reason(
            stage: Literal["multiview", "rerank", "inference"], exc: Exception
        ) -> FailureReason | None:
            """Return the fixed reason when the exception is a retryable target-scoped failure."""
            if stage == "multiview" and isinstance(exc, TargetSelectionError):
                return exc.reason
            if stage == "rerank" and isinstance(exc, InferenceTargetRequestError):
                return "request_failed"
            if stage == "rerank" and isinstance(exc, InferenceOutputError):
                return "provider_output"
            return None

        def execute_unit(
            group_id: str,
            stage: Literal["multiview", "rerank", "inference"],
            action: Callable[[], None],
        ) -> bool:
            """Run one admitted unit's timed action. Return False only for a cooperative yield.

            Multiview selection and rerank request/output failures retry the same whole-target action
            up to the configured bound with admission before each action and around the backoff. The
            inference stage's writer owns its whole-target generation loop and records one episode per
            failed attempt through the failure callback, so its ``TargetPassFailure`` aggregate is
            only republished, not recorded again. The bounded preparation loop keeps its
            ``TargetPreparationFailure`` summary. Every non-target infrastructure/programmer failure
            keeps the FAILED checkpoint and re-raises. An observer failure after a committed
            success is not reclassified as a unit failure.
            """
            attempts = 0
            last_reason: FailureReason | None = None
            last_error_type: str = ""
            max_actions = settings.inference_max_attempts
            while True:
                try:
                    with unit_scope():
                        action()
                except RequestNotStarted:
                    if last_reason is None:
                        return False
                    record_exhausted(
                        group_id, stage, attempts, last_error_type, last_reason, exhausted=False
                    )
                    return False
                except TargetContextError:
                    # The completed fit-preparation action found no configured route for this
                    # oversized packet: one preparation episode, no generation reservation,
                    # work, completion or proposal, and the remaining targets are visited.
                    record_exhausted(
                        group_id,
                        "inference_preparation",
                        1,
                        "TargetContextError",
                        "context_exceeded",
                        exhausted=True,
                    )
                    return True
                except TargetPreparationFailure as exc:
                    if stage != "inference":
                        raise
                    record_exhausted(
                        group_id,
                        "inference_preparation",
                        exc.attempt_count,
                        exc.error_type,
                        exc.reason,
                        exhausted=exc.exhausted,
                    )
                    return exc.exhausted
                except TargetPassFailure as exc:
                    if stage != "inference":
                        raise
                    # The writer already recorded one safe episode per failed generation attempt
                    # through the failure callback. Republish the stage state.
                    notify()
                    return exc.exhausted
                except Exception as exc:
                    reason = retryable_reason(stage, exc)
                    if reason is None:
                        try:
                            record_failure(group_id, stage, exc)
                            notify()
                        except Exception as secondary:
                            raise ExceptionGroup(
                                _UNIT_FAILURE_MESSAGE[stage], [exc, secondary]
                            ) from exc
                        raise
                    attempts += 1
                    last_reason = reason
                    last_error_type = type(exc).__name__
                    if attempts >= max_actions:
                        record_exhausted(
                            group_id,
                            stage,
                            attempts,
                            last_error_type,
                            reason,
                            exhausted=True,
                        )
                        return True
                    if not before_unit():
                        record_exhausted(
                            group_id,
                            stage,
                            attempts,
                            last_error_type,
                            reason,
                            exhausted=False,
                        )
                        return False
                    time.sleep(settings.inference_retry_backoff_seconds * 2 ** (attempts - 1))
                    if not before_unit():
                        record_exhausted(
                            group_id,
                            stage,
                            attempts,
                            last_error_type,
                            reason,
                            exhausted=False,
                        )
                        return False
                    continue
                notify()
                return True

        def run_multiview_stage() -> bool:
            nonlocal cycle, stage_seconds, measured_stage_completed
            for group_id in _ordered_units(states, markers, "multiview"):
                if not before_unit():
                    return False
                if not execute_unit(
                    group_id, "multiview", lambda group_id=group_id: _multiview_action(group_id)
                ):
                    return False
            if not before_unit():
                return False
            repository.set_stage(cycle.cycle_id, "rerank", exhausted_target_group_ids=exhausted_ids)
            cycle = repository.read_cycle(cycle.cycle_id)
            stage_seconds = 0.0
            measured_stage_completed = 0
            notify()
            return True

        def _multiview_action(group_id: str) -> None:
            nonlocal measured_stage_completed
            pool = select_operational_multiview_pool(
                catalogue,
                group_id,
                candidate_repository,
                selection=selection,
                context_settings=context_settings,
            )
            record = load_record(group_id)
            apply_record(
                repository.checkpoint(
                    record.model_copy(
                        update={
                            "multiview_state": "completed",
                            "pool_input": pool,
                            "error_type": None,
                        }
                    )
                )
            )
            measured_stage_completed += 1

        def run_rerank_stage() -> bool:
            nonlocal cycle, stage_seconds, measured_stage_completed
            for group_id in _ordered_units(states, markers, "rerank"):
                if not before_unit():
                    return False
                if not execute_unit(
                    group_id, "rerank", lambda group_id=group_id: _rerank_action(group_id)
                ):
                    return False
            runtime.stop_rerank()
            if not before_unit():
                return False
            repository.set_stage(
                cycle.cycle_id, "inference", exhausted_target_group_ids=exhausted_ids
            )
            cycle = repository.read_cycle(cycle.cycle_id)
            stage_seconds = 0.0
            measured_stage_completed = 0
            notify()
            return True

        def _rerank_action(group_id: str) -> None:
            nonlocal measured_stage_completed
            record = load_record(group_id)
            candidate_ids = tuple(
                reference.group_id for reference in record.pool_input.references.candidates
            )
            if not select_rerank(markers[group_id].processed, candidate_ids, markers):
                if markers[group_id].disposition is not None:
                    # A disposed target keeps its decision-owned inference state, planned key and
                    # proposal. Only the legitimately skipped rerank stage is projected.
                    update: dict[str, object] = {"rerank_state": "skipped", "target_input": None}
                else:
                    update = {
                        "rerank_state": "skipped",
                        "inference_state": "skipped",
                        "target_input": None,
                        "generation_work_key_sha256": None,
                        "error_type": None,
                    }
                apply_record(repository.checkpoint(record.model_copy(update=update)))
                return
            if not before_request():
                raise RequestNotStarted("inference target request not started")
            runtime.start_rerank()
            with RerankProvider(
                rerank_settings,
                before_request=before_request,
                request_scope=runtime.request_scope,
            ) as reranker:
                target_input = rerank_operational_pool(
                    record.pool_input,
                    reranker,
                    catalogue=catalogue,
                    selection=selection,
                    context_settings=context_settings,
                    rerank_input=rerank_input,
                    rerank_settings=rerank_settings,
                    before_request=before_request,
                )
            apply_record(
                repository.checkpoint(
                    record.model_copy(
                        update={
                            "rerank_state": "completed",
                            "target_input": target_input,
                            "error_type": None,
                        }
                    )
                )
            )
            measured_stage_completed += 1

        def run_generation_stage() -> bool:
            nonlocal cycle, stage_seconds, measured_stage_completed
            for group_id in _ordered_units(states, markers, "inference"):
                if markers[group_id].disposition == "failed":
                    # A terminal operator FAILED decision is never admitted, runtime-activated,
                    # planned-work recovered, requested, reserved or given a new failure episode. It
                    # is FAILED for publication and terminal handling.
                    continue
                if not before_unit():
                    return False
                if not execute_unit(
                    group_id, "inference", lambda group_id=group_id: _inference_action(group_id)
                ):
                    return False
            runtime.stop()
            if not before_unit():
                return False
            repository.set_stage(
                cycle.cycle_id, "publication", exhausted_target_group_ids=exhausted_ids
            )
            cycle = repository.read_cycle(cycle.cycle_id)
            stage_seconds = 0.0
            measured_stage_completed = 0
            notify()
            return True

        def _inference_action(group_id: str) -> None:
            nonlocal measured_stage_completed
            record = load_record(group_id)
            planned_key = record.generation_work_key_sha256
            completed = None if planned_key is None else evidence.read_work(group_id, planned_key)
            if completed is not None and completed.status is InferenceWorkStatus.COMPLETED:
                proposal = compose_proposal_from_work(factory, completed.work_id, settings=settings)
                accept_record(record, proposal, planned_key)
                return
            candidate_ids = tuple(
                reference.group_id for reference in record.target_input.references.candidates
            )
            if record.inference_state != "failed" and not select_inference(
                markers[group_id].processed, candidate_ids, markers
            ):
                apply_record(
                    repository.checkpoint(
                        record.model_copy(
                            update={
                                "inference_state": "skipped",
                                "generation_work_key_sha256": None,
                                "error_type": None,
                            }
                        )
                    )
                )
                return

            def on_identity(identity: TargetWorkIdentity) -> None:
                nonlocal record
                planned = work_key_sha256(
                    identity.work_request,
                    run_identity_sha256(identity.spec),
                )
                record = repository.checkpoint(
                    record.model_copy(update={"generation_work_key_sha256": planned})
                )
                apply_record(record)

            work = run_routed_operational_target(
                record.target_input,
                prompt_pack,
                settings,
                evidence,
                catalogue=catalogue,
                scheduling_repository=repository,
                cycle_id=cycle.cycle_id,
                runtime=runtime,
                on_identity=on_identity,
                retry_failed=True,
                before_request=before_request,
                on_failure=on_generation_failure,
                request_scope=runtime.request_scope,
                oversize_route=oversize_route,
            )
            proposal = compose_proposal_from_work(factory, work.work_id, settings=settings)
            accept_record(record, proposal, work.work_key_sha256)
            measured_stage_completed += 1

        def run_publication_stage() -> ProcessingCycleRecord:
            nonlocal cycle
            if not before_unit():
                return yield_current()
            cohort = repository.read_publication_cohort()
            publish_current_cohort(factory, cohort, settings, selection)
            repository.prune_retained_state()
            notify()
            if failed_target_ids:
                # Useful targets are published. A failed target keeps the cycle unfinished so
                # the next ordinary start retries it without repeating completed checkpoints.
                raise InferenceTargetsFailed("inference targets failed")
            cycle = repository.finish_cycle(cycle.cycle_id, input_sha256=cycle.input_sha256)
            notify()
            return cycle

        # Emit the real durable done/total before any new measured pace exists.
        notify()
        if cycle.stage == "multiview":
            if not run_multiview_stage():
                return yield_current()
        if cycle.stage == "rerank":
            if not run_rerank_stage():
                return yield_current()
        if cycle.stage == "inference":
            if not run_generation_stage():
                return yield_current()
        if cycle.stage == "publication":
            return run_publication_stage()
        raise ValueError("the retained cycle is not on a dispatchable stage")
    finally:
        cleanup_errors: list[Exception] = []
        for action in (runtime.stop_rerank, runtime.stop):
            try:
                action()
            except Exception as exc:  # noqa: BLE001 - cleanup failure must be surfaced
                cleanup_errors.append(exc)
        if cleanup_errors:
            active = sys.exc_info()[1]
            if active is not None:
                raise ExceptionGroup(
                    "inference job cleanup failure", [active, *cleanup_errors]
                ) from active
            raise ExceptionGroup("inference job cleanup failure", cleanup_errors)
