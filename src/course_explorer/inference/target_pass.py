"""Render one deterministic complete-target request and run one route-budgeted call.

Request rendering reads the label-free packet and the versioned prompt pack, and the work identity
binds the compact selection reference digest to the rendered request digest. One call owns one
target. The writer runs that route's generation loop, unbounded on a local route and at most
``provider.max_attempts`` requests per pass on a bounded route, and writes the completion row only
for a result that passes strict validation. A failed request or invalid output marks the work failed
and appends one safe single-attempt episode.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from course_explorer.administration import utc_now as _utc_now
from course_explorer.config import InferenceSettings
from course_explorer.enums import InferenceWorkStatus
from course_explorer.hashing import canonical_json_sha256
from course_explorer.http_retry import RequestNotStarted
from course_explorer.inference.context import (
    InferencePacketCourse,
    InferenceTargetPacket,
    processing_text_sha256,
    request_descriptors_from_packet,
)
from course_explorer.inference.domain import (
    parse_target_result,
    target_result_json_schema,
    target_result_model,
)
from course_explorer.inference.evidence import (
    InferenceCompletionFacts,
    InferenceExecutionProfile,
    InferencePipelineRunSpec,
    InferenceRequestEvidence,
    InferenceTargetWorkRecord,
    InferenceTargetWorkRequest,
    InferenceWorkClaimAction,
)
from course_explorer.inference.evidence_repository import InferenceEvidenceRepository
from course_explorer.inference.failures import (
    FailureReason,
    TargetPassFailure,
    TargetResultError,
)
from course_explorer.inference.operational_selection import FINAL_CANDIDATE_MAX
from course_explorer.inference.prompts import PromptPack
from course_explorer.inference.provider import (
    InferenceContractError,
    InferenceOutputError,
    InferenceRequestError,
    InferenceTargetRequestError,
)
from course_explorer.validation import require_sha256 as _require_sha256

if TYPE_CHECKING:
    from course_explorer.inference.operational import OperationalTargetInput
    from course_explorer.inference.scheduling import (
        ProcessingTargetRecord,
        TargetFailureRecord,
    )
    from course_explorer.inference.scheduling_repository import InferenceSchedulingRepository


class TargetGenerationResult(Protocol):
    """The one validated-generation surface the writer reads from any execution route.

    It exposes the strict JSON content the provider observed. Every route's own generation record
    is that route's contract and no route-specific field crosses this boundary.
    """

    @property
    def raw_json(self) -> str:
        """Return the provider response as JSON text.

        The writer parses this text against the configured result schema.
        """
        ...


class TargetGenerationProvider(Protocol):
    """The one generation surface a route-budgeted target call needs from any provider route.

    Every configured route's provider satisfies it, so the one claim/validate/write body accepts any
    route without a second evidence path. Each route exposes its configured execution backoff so the
    writer, not the provider, owns the whole-target retry loop. A local route is unbounded and a
    bounded route exposes its per-pass request budget through ``max_attempts``.
    """

    @property
    def max_attempts(self) -> int:
        """Return the number of requests one bounded route pass may make.

        The writer applies this budget to every route whose execution profile is not ``local``.
        """
        ...

    @property
    def retry_backoff_seconds(self) -> float:
        """Return the initial backoff in seconds after a failed request on this route.

        The writer caps the wait at ``inference_retry_max_backoff_seconds`` and doubles it after
        each failure up to that cap.
        """
        ...

    def generate_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema_name: str,
        json_schema: Mapping[str, object],
        attempt_ordinal: int,
        first_attempt: bool,
    ) -> TargetGenerationResult:
        """Return one generation response for the supplied prompts and schema.

        The writer supplies the reserved durable attempt ordinal and the first-attempt flag. A route
        implements the call over its own transport and returns the response JSON text through
        :class:`TargetGenerationResult`.
        """
        ...


def target_result_schema_name(schema_version: str) -> str:
    """Return the closed request schema name for one result schema version.

    The version is checked by the single :func:`target_result_model` owner, which accepts only
    ``v2``, so this helper returns a name only for a version the schema owner accepts.
    """
    target_result_model(schema_version)
    return f"inference_target_result_{schema_version}"


class TargetPassError(RuntimeError):
    """A target-pass lifecycle failure with a safe, content-free message."""


class _TargetPassModel(BaseModel):
    """Frozen, closed, strict DTO base for the route-budgeted target-pass contract."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


def _prompt_course_descriptor(course: InferencePacketCourse) -> dict[str, object]:
    """Render one label-free packet course into its request descriptor.

    The descriptor carries the group ID, the course code, the representative source digest, and one
    entry per effective teaching cell with its field, language, text, and origin.
    """
    return {
        "group_id": course.identity.group_id,
        "course_code": course.course_code,
        "representative_source_sha256": course.identity.representative_source_sha256,
        "texts": [
            {
                "field": cell.field.value,
                "language": cell.language.value,
                "text": cell.text,
                "origin": cell.origin.value,
            }
            for cell in course.texts
        ],
    }


def render_target_request(
    packet: InferenceTargetPacket, pack: PromptPack, schema_version: str
) -> InferenceRequestEvidence:
    """Render one deterministic same-schema complete-target request for a label-free packet.

    The pack supplies the system prompt and the curated worked examples. The system prompt combines
    the pack's system prompt with the worked examples as sorted UTF-8 JSON, excluding the target's
    own curated answer. The user prompt is compact sorted UTF-8 JSON of the target and ordered
    candidate descriptors. ``schema_version`` selects the strict result schema and its request
    identity. Live callers pass the configured version and it has no default.
    """
    if not packet.target.is_active:
        raise ValueError("the target pass requires an active target")
    if not 1 <= len(packet.candidates) <= FINAL_CANDIDATE_MAX:
        raise ValueError(f"the target pass requires 1..{FINAL_CANDIDATE_MAX} ordered candidates")
    examples = tuple(
        example
        for example in pack.examples_for_target(packet.target.identity.group_id)
        if example.target.course_code != packet.target.course_code
    )
    examples_json = json.dumps(
        [example.model_dump(mode="json") for example in examples],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    system_prompt = (
        f"{pack.system_prompt}\n\nWorked examples (curated inference, not university facts):\n"
        f"{examples_json}"
    )
    user_prompt = json.dumps(
        {
            "target": _prompt_course_descriptor(packet.target),
            "candidates": [
                _prompt_course_descriptor(candidate.course) for candidate in packet.candidates
            ],
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return InferenceRequestEvidence(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        schema_name=target_result_schema_name(schema_version),
        json_schema=target_result_json_schema(schema_version),
    )


def request_sha256(request: InferenceRequestEvidence) -> str:
    """Return the canonical identity of one rendered request."""
    return canonical_json_sha256(request.model_dump(mode="json"))


class TargetWorkIdentity(_TargetPassModel):
    """The exact reusable work identity for one operational input and settings pair."""

    request: InferenceRequestEvidence
    input_sha256: str
    spec: InferencePipelineRunSpec
    work_request: InferenceTargetWorkRequest


class PreparedTargetRequest(_TargetPassModel):
    """One rendered request with its transient request and target-input digests."""

    request: InferenceRequestEvidence
    request_sha256: str
    input_sha256: str


def target_input_sha256(value: OperationalTargetInput, request_digest: str) -> str:
    """Hash one operational target's exact work input from its compact selection and request.

    This is the one two-key formula over the packet digest and the rendered request digest.
    """
    _require_sha256(request_digest, "request_digest")
    return canonical_json_sha256(
        {
            "packet_sha256": value.packet_sha256,
            "request_sha256": request_digest,
        }
    )


def prepare_target_request(
    value: OperationalTargetInput,
    pack: PromptPack,
    settings: InferenceSettings,
    *,
    packet: InferenceTargetPacket,
) -> PreparedTargetRequest:
    """Render one target's request once and derive its request and input digests.

    The pack version must equal the configured inference prompt version, so a mismatching pack
    fails before token counting or generation. No Pydantic object is passed to the hashers.
    """
    if pack.version != settings.inference_prompt_version:
        raise ValueError("prompt pack version must equal the configured inference prompt version")
    request = render_target_request(packet, pack, settings.inference_schema_version)
    request_digest = request_sha256(request)
    return PreparedTargetRequest(
        request=request,
        request_sha256=request_digest,
        input_sha256=target_input_sha256(value, request_digest),
    )


def target_work_identity(
    value: OperationalTargetInput,
    settings: InferenceSettings,
    execution: InferenceExecutionProfile,
    *,
    packet: InferenceTargetPacket,
    prepared: PreparedTargetRequest,
) -> TargetWorkIdentity:
    """Derive one operational CE-only target's execution spec and reuse request.

    The work input binds the selected packet digest and the prepared request digest, so a changed
    CE-only selection or route produces a different work identity. The packet supplies the target
    activity context, and nothing is rendered again.
    """
    target = packet.target
    work_request = InferenceTargetWorkRequest(
        target_group_id=value.target_group_id,
        activity_as_of_academic_year_start=target.activity_as_of_academic_year_start,
        activity_window_years=target.activity_window_years,
    )
    return TargetWorkIdentity(
        request=prepared.request,
        input_sha256=prepared.input_sha256,
        spec=InferencePipelineRunSpec.from_contracts(settings, execution=execution),
        work_request=work_request,
    )


def run_target(
    value: OperationalTargetInput,
    settings: InferenceSettings,
    repository: InferenceEvidenceRepository,
    provider: TargetGenerationProvider,
    execution: InferenceExecutionProfile,
    *,
    packet: InferenceTargetPacket,
    identity: TargetWorkIdentity,
    scheduling_repository: InferenceSchedulingRepository,
    cycle_id: UUID,
    retry_failed: bool = False,
    before_request: Callable[[], bool] | None = None,
    on_failure: Callable[[ProcessingTargetRecord, TargetFailureRecord], None] | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> InferenceTargetWorkRecord:
    """Run or reuse one complete-target call for one operational CE-only target.

    ``identity`` is the route's one prepared work identity. The writer renders nothing and claims
    the work key from ``identity.input_sha256``.

    Matching completed work is reused without any reservation or HTTP request. The writer owns the
    whole-target generation loop for the route: unbounded on the local route, at most
    ``provider.max_attempts`` requests per pass on a bounded route (its own cost cap). Before
    every request it checks admission, reserves ``(ordinal, first_attempt)`` durably on the canonical
    counter, and calls the provider once with both. The provider makes one request per call, so
    retries are never multiplied. Each genuine request/output/semantic failure marks the work failed,
    appends one safe single-attempt episode through the scheduling owner, and calls ``on_failure``.

    A control/reboot refusal, before any request or after a recorded failure, is the fixed
    cooperative :class:`RequestNotStarted`, never an invented aggregate failure, and leaves the failed
    work as-is. A bounded route's final failed request with admission open raises a
    content-free :class:`TargetPassFailure` with ``exhausted=True``. The local route never exhausts.
    """
    if before_request is not None and not before_request():
        raise RequestNotStarted("inference target request not started")
    run = repository.create_run(identity.spec)
    claim = repository.claim_work(run.run_id, identity.work_request, identity.input_sha256)
    work_id = claim.work.work_id
    if claim.action is InferenceWorkClaimAction.REUSED:
        return claim.work
    if (
        claim.action is InferenceWorkClaimAction.EXISTING
        and claim.work.status is InferenceWorkStatus.FAILED
    ):
        if not retry_failed:
            raise TargetPassError(f"inference target work {work_id} previously failed")
        if before_request is not None and not before_request():
            raise RequestNotStarted("inference target request not started")
        repository.retry_work(run.run_id, work_id)

    max_requests = None if execution.route == "local" else provider.max_attempts
    requests_made = 0
    last_error_type: str | None = None
    last_reason: FailureReason | None = None

    def summary() -> TargetPassFailure:
        assert last_error_type is not None and last_reason is not None
        return TargetPassFailure(
            attempt_count=requests_made,
            reason=last_reason,
            error_type=last_error_type,
            exhausted=True,
        )

    def record_failure(*, reason: FailureReason, error_type: str, exhausted: bool) -> None:
        """Mark the work failed and append one safe single-attempt episode for the failed request."""
        nonlocal last_reason, last_error_type
        last_reason = reason
        last_error_type = error_type
        repository.fail_work(run.run_id, work_id)
        record, failure = scheduling_repository.record_target_failure(
            cycle_id,
            value.target_group_id,
            stage="inference",
            attempt_count=1,
            error_type=error_type,
            reason=reason,
            exhausted=exhausted,
        )
        if on_failure is not None:
            on_failure(record, failure)

    def wait_before_retry(delay: float) -> None:
        """Sleep the capped delay in poll chunks, checking admission around each chunk."""
        remaining = min(delay, settings.inference_retry_max_backoff_seconds)
        poll = settings.inference_retry_poll_seconds
        while remaining > 0:
            if before_request is not None and not before_request():
                raise RequestNotStarted("inference target request not started")
            chunk = min(remaining, poll)
            sleep(chunk)
            remaining -= chunk
            if before_request is not None and not before_request():
                raise RequestNotStarted("inference target request not started")

    delay = min(provider.retry_backoff_seconds, settings.inference_retry_max_backoff_seconds)

    def pass_exhausted() -> bool:
        """Return whether the bounded pass has already used its final request."""
        return max_requests is not None and requests_made >= max_requests

    def after_failure() -> None:
        """Yield on control, exhaust the bounded pass, or wait then retry the same work."""
        nonlocal delay
        if before_request is not None and not before_request():
            raise RequestNotStarted("inference target request not started")
        if pass_exhausted():
            raise summary()
        wait_before_retry(delay)
        delay = min(settings.inference_retry_max_backoff_seconds, delay * 2)
        repository.retry_work(run.run_id, work_id)

    descriptors = request_descriptors_from_packet(packet)
    facts = InferenceCompletionFacts(
        target_teaching_text_sha256=processing_text_sha256(
            tuple(
                (cell.field.value, cell.language.value, cell.text) for cell in packet.target.texts
            )
        ),
        candidate_count=len(packet.candidates),
    )

    while True:
        if before_request is not None and not before_request():
            raise RequestNotStarted("inference target request not started")
        ordinal, first_attempt = scheduling_repository.reserve_generation_attempt(
            cycle_id, value.target_group_id
        )
        requests_made += 1
        try:
            generation = provider.generate_json(
                system_prompt=identity.request.system_prompt,
                user_prompt=identity.request.user_prompt,
                schema_name=identity.request.schema_name,
                json_schema=identity.request.json_schema,
                attempt_ordinal=ordinal,
                first_attempt=first_attempt,
            )
        except RequestNotStarted:
            raise
        except InferenceTargetRequestError as exc:
            record_failure(
                reason="request_failed",
                error_type=type(exc).__name__,
                exhausted=pass_exhausted(),
            )
            after_failure()
            continue
        except InferenceOutputError as exc:
            record_failure(
                reason="provider_output",
                error_type=type(exc).__name__,
                exhausted=pass_exhausted(),
            )
            after_failure()
            continue
        except (InferenceRequestError, InferenceContractError) as exc:
            # Infrastructure failures are never a target-scoped retry: record one nonexhausted safe
            # episode for the started request and propagate loudly instead of continuing.
            record_failure(
                reason=(
                    "request_failed"
                    if isinstance(exc, InferenceRequestError)
                    else "provider_output"
                ),
                error_type=type(exc).__name__,
                exhausted=False,
            )
            raise

        finished_at = _utc_now()
        try:
            result = parse_target_result(generation.raw_json, settings.inference_schema_version)
            return repository.record_completion(
                run.run_id,
                work_id,
                result=result,
                descriptors=descriptors,
                facts=facts,
                finished_at=finished_at,
            )
        except TargetResultError as exc:
            record_failure(
                reason=exc.reason,
                error_type=type(exc).__name__,
                exhausted=pass_exhausted(),
            )
            after_failure()
            continue
