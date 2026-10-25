"""Contracts for the label-free target packet, request, and one bounded call.

The renderer/identity proofs are network-free. The writer proofs run against the disposable
PostgreSQL database with a real evidence repository and a real local client over the shared HTTP
boundary, so reuse/retry/terminal-failure/control behavior is proven end to end.
"""

from __future__ import annotations

import json

import pytest

from course_explorer.enums import InferenceWorkStatus
from course_explorer.hashing import canonical_json_sha256
from course_explorer.http_retry import RequestNotStarted
from course_explorer.inference.context import selection_references_sha256
from course_explorer.inference.domain import (
    DirectnessOutcome,
    InferenceCourseOptionV2,
    InferenceEquivalenceProposalV2,
    InferenceRequirementSetV2,
    InferenceRoutingMetadata,
    InferenceSuppressedCandidate,
    InferenceTargetResultV2,
)
from course_explorer.inference.evidence import run_identity_sha256, work_key_sha256
from course_explorer.inference.evidence_repository import InferenceEvidenceRepository
from course_explorer.inference.prompts import load_prompt_pack
from course_explorer.inference.provider import InferenceRequestError
from course_explorer.inference.target_pass import (
    TargetPassError,
    prepare_target_request,
    render_target_request,
    run_target,
    target_work_identity,
)
from tests.inference._http_support import InferenceHttpBoundary, local_structured_provider
from tests.inference._scheduling_support import (
    attempt_count,
    prepare_generation_cycle,
    seed_courses,
)
from tests.inference._target_support import (
    TARGET_CODE,
    TARGET_GROUP_ID,
    empty_result_json,
    execution_profile,
    operational_input,
    packet_course,
    target_packet,
    target_settings,
)


def _result_json(result: InferenceTargetResultV2) -> str:
    return json.dumps(result.model_dump(mode="python"), default=float)


def _seed_target(factory: object) -> None:
    seed_courses(factory, [(TARGET_GROUP_ID, TARGET_CODE, True)])


def _refuse_after_requests(boundary: InferenceHttpBoundary, allowed: int):
    """Admit while fewer than ``allowed`` HTTP requests have started, then refuse."""

    def admit() -> bool:
        return len(boundary.requests) < allowed

    return admit


def _identity(packet, value, pack, settings, execution):
    """Prepare one target request once and bind the selected route's work identity."""
    prepared = prepare_target_request(value, pack, settings, packet=packet)
    return target_work_identity(value, settings, execution, packet=packet, prepared=prepared)


def _work_key(packet, value, pack, settings, execution) -> str:
    identity = _identity(packet, value, pack, settings, execution)
    return work_key_sha256(
        identity.work_request, run_identity_sha256(identity.spec), identity.input_sha256
    )


def test_render_never_leaks_labels_ranks_or_same_target_example() -> None:
    """The request carries only label-free teaching descriptors and excludes the target's answer."""
    packet = target_packet(50)
    pack = load_prompt_pack("v9")
    request = render_target_request(packet, pack, "v2")

    assert request.schema_name == "inference_target_result_v2"
    body = json.loads(request.user_prompt)
    assert set(body) == {"target", "candidates"}
    assert len(body["candidates"]) == 50
    for candidate in body["candidates"]:
        assert set(candidate) == {
            "group_id",
            "course_code",
            "representative_source_sha256",
            "texts",
        }
    serialized = request.system_prompt + request.user_prompt
    for forbidden in (
        "official_prerequisite",
        "prerequisite_text",
        "retrieval",
        "ranked_candidate",
        "target_packet_sha256",
    ):
        assert forbidden not in serialized.lower()

    # The target's own curated example never appears in its system prompt when the target course
    # code matches it. The renderer excludes the matching-code answer by code.
    example = pack.examples[0]
    labeled_target = packet_course(
        packet.target.identity.group_id, example.target.course_code, "target body"
    )
    labeled_packet = packet.model_copy(update={"target": labeled_target})
    labeled_request = render_target_request(labeled_packet, pack, "v2")
    example_json = json.dumps(
        example.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    assert example_json not in labeled_request.system_prompt


def test_configured_schema_version_selects_request_and_work_identity() -> None:
    """The explicit v2 schema selects the request schema and binds the current identity."""
    pack = load_prompt_pack("v9")
    packet = target_packet(50)
    value = operational_input(packet)
    settings = target_settings()
    execution = execution_profile(settings)

    prepared = prepare_target_request(value, pack, settings, packet=packet)
    assert prepared.request.schema_name == "inference_target_result_v2"
    assert value.packet_sha256 == selection_references_sha256(value.references)

    identity = target_work_identity(value, settings, execution, packet=packet, prepared=prepared)
    assert identity.spec.schema_version == "v2"
    assert identity.request.schema_name == "inference_target_result_v2"
    assert identity.request == prepared.request
    assert identity.spec.configuration == {"route": "local"}
    assert identity.input_sha256 == canonical_json_sha256(
        {"packet_sha256": value.packet_sha256, "request_sha256": prepared.request_sha256}
    )

    # A prompt pack whose version disagrees with configured settings is rejected before rendering.
    with pytest.raises(ValueError):
        prepare_target_request(
            value, pack.model_copy(update={"version": "v2"}), settings, packet=packet
        )


def test_changed_packet_prompt_model_or_activity_changes_work_key() -> None:
    """Work identity binds the packet, prompt, model and activity context."""
    pack = load_prompt_pack("v9")
    settings = target_settings()
    execution = execution_profile(settings)
    base_packet = target_packet(50)
    normal = _identity(base_packet, operational_input(base_packet), pack, settings, execution)
    normal_key = work_key_sha256(
        normal.work_request, run_identity_sha256(normal.spec), normal.input_sha256
    )

    # A changed packet (reversed candidate order) changes the request and input/work key.
    reversed_packet = base_packet.model_copy(
        update={"candidates": tuple(reversed(base_packet.candidates))}
    )
    changed_packet = _identity(
        reversed_packet, operational_input(reversed_packet), pack, settings, execution
    )
    assert changed_packet.request != normal.request
    assert changed_packet.input_sha256 != normal.input_sha256
    assert (
        work_key_sha256(
            changed_packet.work_request,
            run_identity_sha256(changed_packet.spec),
            changed_packet.input_sha256,
        )
        != normal_key
    )

    # An example this target excludes from its request leaves that request and work key unchanged.
    edited_pack = pack.model_copy(
        update={
            "examples": tuple(
                example.model_copy(update={"explanation": "edited example text"})
                if example.target.course_code == base_packet.target.course_code
                else example
                for example in pack.examples
            )
        }
    )
    edited_identity = _identity(
        base_packet, operational_input(base_packet), edited_pack, settings, execution
    )
    assert edited_identity.request == normal.request
    assert (
        work_key_sha256(
            edited_identity.work_request,
            run_identity_sha256(edited_identity.spec),
            edited_identity.input_sha256,
        )
        == normal_key
    )

    # A changed execution route/key changes the run identity.
    second_key = _identity(
        base_packet,
        operational_input(base_packet),
        pack,
        settings,
        execution_profile(settings, variant_index=1),
    )
    assert run_identity_sha256(second_key.spec) != run_identity_sha256(normal.spec)


@pytest.mark.integration
def test_result_rejects_unknown_direct_or_equivalence_code(database) -> None:
    """The writer accepts a named equivalence and refuses an unknown suppressed code."""
    factory = database[1]
    _seed_target(factory)
    settings = target_settings()
    pack = load_prompt_pack("v9")
    execution = execution_profile(settings)
    repository = InferenceEvidenceRepository(factory)

    packet = target_packet(50)
    value = operational_input(packet)
    scheduling, cycle = prepare_generation_cycle(factory, value)
    known = packet.candidates[0].course.course_code
    target = packet.target.course_code
    good = InferenceTargetResultV2(
        required=(),
        recommended=(),
        equivalence=(
            InferenceEquivalenceProposalV2(
                members=(known, target), evidence="e", confidence=0.5, finding_flags=()
            ),
        ),
        routing=InferenceRoutingMetadata(confidence=0.5, flags=(), suppressed=()),
    )
    boundary = InferenceHttpBoundary(settings, content=_result_json(good))
    work = run_target(
        value,
        settings,
        repository,
        local_structured_provider(settings, boundary),
        execution,
        packet=packet,
        identity=_identity(packet, value, pack, settings, execution),
        scheduling_repository=scheduling,
        cycle_id=cycle.cycle_id,
    )
    assert work.status is InferenceWorkStatus.COMPLETED
    completion = repository.read_completion(work.work_id)
    assert completion is not None
    assert completion.payload.result == good

    reversed_packet = packet.model_copy(update={"candidates": tuple(reversed(packet.candidates))})
    bad_value = operational_input(reversed_packet)
    bad = InferenceTargetResultV2(
        required=(),
        recommended=(),
        equivalence=(),
        routing=InferenceRoutingMetadata(
            confidence=0.5,
            flags=(),
            suppressed=(
                InferenceSuppressedCandidate(
                    course_code="NOT.A.CODE", outcome=DirectnessOutcome.RELATED, evidence="e"
                ),
            ),
        ),
    )
    bad_boundary = InferenceHttpBoundary(settings, content=_result_json(bad))
    bad_scheduling, bad_cycle = prepare_generation_cycle(factory, bad_value)
    with pytest.raises(RequestNotStarted):
        run_target(
            bad_value,
            settings,
            repository,
            local_structured_provider(settings, bad_boundary),
            execution,
            packet=reversed_packet,
            identity=_identity(reversed_packet, bad_value, pack, settings, execution),
            scheduling_repository=bad_scheduling,
            cycle_id=bad_cycle.cycle_id,
            before_request=_refuse_after_requests(bad_boundary, 1),
        )
    failures = bad_scheduling.read_target_failures(bad_cycle.cycle_id)
    assert len(failures) == 1
    assert failures[0].reason == "invalid_result"
    assert failures[0].exhausted is False
    bad_work = repository.read_work(
        TARGET_GROUP_ID, _work_key(reversed_packet, bad_value, pack, settings, execution)
    )
    assert bad_work is not None and bad_work.status is InferenceWorkStatus.FAILED
    assert repository.read_completion(bad_work.work_id) is None

    # A structurally valid multi-set result is rejected by the shared acceptance rule before success.
    second_code = packet.candidates[1].course.course_code
    multi_packet = packet.model_copy(
        update={"candidates": tuple(packet.candidates[2:]) + tuple(packet.candidates[:2])}
    )
    multi_value = operational_input(multi_packet)
    multi = InferenceTargetResultV2(
        required=(
            InferenceRequirementSetV2(
                requirement_id="r1",
                options=(
                    InferenceCourseOptionV2(
                        course_codes=(known,), evidence="e", confidence=0.5, finding_flags=()
                    ),
                ),
            ),
            InferenceRequirementSetV2(
                requirement_id="r2",
                options=(
                    InferenceCourseOptionV2(
                        course_codes=(second_code,),
                        evidence="e",
                        confidence=0.5,
                        finding_flags=(),
                    ),
                ),
            ),
        ),
        recommended=(),
        equivalence=(),
        routing=InferenceRoutingMetadata(confidence=0.5, flags=(), suppressed=()),
    )
    multi_boundary = InferenceHttpBoundary(settings, content=_result_json(multi))
    multi_scheduling, multi_cycle = prepare_generation_cycle(factory, multi_value)
    with pytest.raises(RequestNotStarted):
        run_target(
            multi_value,
            settings,
            repository,
            local_structured_provider(settings, multi_boundary),
            execution,
            packet=multi_packet,
            identity=_identity(multi_packet, multi_value, pack, settings, execution),
            scheduling_repository=multi_scheduling,
            cycle_id=multi_cycle.cycle_id,
            before_request=_refuse_after_requests(multi_boundary, 1),
        )
    multi_failures = multi_scheduling.read_target_failures(multi_cycle.cycle_id)
    assert len(multi_failures) == 1
    assert multi_failures[0].reason == "multiple_requirement_sets"
    multi_work = repository.read_work(
        TARGET_GROUP_ID, _work_key(multi_packet, multi_value, pack, settings, execution)
    )
    assert multi_work is not None and multi_work.status is InferenceWorkStatus.FAILED
    assert repository.read_completion(multi_work.work_id) is None


@pytest.mark.integration
def test_run_reuses_completed_work_and_explicitly_retries_failed_work(database) -> None:
    """Completed matching work is reused without HTTP. Failed work needs explicit retry."""
    factory = database[1]
    _seed_target(factory)
    settings = target_settings().model_copy(update={"inference_retry_backoff_seconds": 0.0})
    pack = load_prompt_pack("v9")
    execution = execution_profile(settings)
    repository = InferenceEvidenceRepository(factory)

    packet = target_packet(50)
    value = operational_input(packet)
    scheduling, cycle = prepare_generation_cycle(factory, value)
    good = InferenceHttpBoundary(settings)
    work = run_target(
        value,
        settings,
        repository,
        local_structured_provider(settings, good),
        execution,
        packet=packet,
        identity=_identity(packet, value, pack, settings, execution),
        scheduling_repository=scheduling,
        cycle_id=cycle.cycle_id,
    )
    assert work.status is InferenceWorkStatus.COMPLETED
    assert repository.read_completion(work.work_id) is not None

    reuse_boundary = InferenceHttpBoundary(settings)
    reused = run_target(
        value,
        settings,
        repository,
        local_structured_provider(settings, reuse_boundary),
        execution,
        packet=packet,
        identity=_identity(packet, value, pack, settings, execution),
        scheduling_repository=scheduling,
        cycle_id=cycle.cycle_id,
    )
    assert reused.work_id == work.work_id
    assert reused.status is InferenceWorkStatus.COMPLETED
    assert reuse_boundary.requests == []

    failed_packet = packet.model_copy(update={"candidates": tuple(reversed(packet.candidates))})
    failed_value = operational_input(failed_packet)
    failing = InferenceHttpBoundary(settings)
    failing.failure_path = "v1/chat/completions"
    failing.failure_status = 500
    failed_scheduling, failed_cycle = prepare_generation_cycle(factory, failed_value)
    with pytest.raises(RequestNotStarted):
        run_target(
            failed_value,
            settings,
            repository,
            local_structured_provider(settings, failing),
            execution,
            packet=failed_packet,
            identity=_identity(failed_packet, failed_value, pack, settings, execution),
            scheduling_repository=failed_scheduling,
            cycle_id=failed_cycle.cycle_id,
            before_request=_refuse_after_requests(failing, 1),
        )
    failures = failed_scheduling.read_target_failures(failed_cycle.cycle_id)
    assert len(failures) == 1
    assert failures[0].reason == "request_failed"
    assert failures[0].exhausted is False
    failed_key = _work_key(failed_packet, failed_value, pack, settings, execution)
    failed_work = repository.read_work(TARGET_GROUP_ID, failed_key)
    assert failed_work is not None and failed_work.status is InferenceWorkStatus.FAILED
    assert repository.read_completion(failed_work.work_id) is None

    # Without an explicit retry the failed work is refused and writes no completion.
    with pytest.raises(TargetPassError):
        run_target(
            failed_value,
            settings,
            repository,
            local_structured_provider(settings, InferenceHttpBoundary(settings)),
            execution,
            packet=failed_packet,
            identity=_identity(failed_packet, failed_value, pack, settings, execution),
            scheduling_repository=failed_scheduling,
            cycle_id=failed_cycle.cycle_id,
        )
    assert repository.read_completion(failed_work.work_id) is None

    retry_boundary = InferenceHttpBoundary(settings)
    retried = run_target(
        failed_value,
        settings,
        repository,
        local_structured_provider(settings, retry_boundary),
        execution,
        packet=failed_packet,
        identity=_identity(failed_packet, failed_value, pack, settings, execution),
        scheduling_repository=failed_scheduling,
        cycle_id=failed_cycle.cycle_id,
        retry_failed=True,
    )
    assert retried.status is InferenceWorkStatus.COMPLETED
    assert repository.read_completion(retried.work_id) is not None


@pytest.mark.integration
def test_terminal_request_and_contract_failures_retain_safe_evidence(database) -> None:
    """A request/contract/semantic rejection leaves no completion and one safe episode."""
    factory = database[1]
    _seed_target(factory)
    settings = target_settings()
    pack = load_prompt_pack("v9")
    execution = execution_profile(settings)
    repository = InferenceEvidenceRepository(factory)

    packet = target_packet(50)
    request_value = operational_input(packet)
    request_boundary = InferenceHttpBoundary(settings)
    request_boundary.failure_path = "v1/chat/completions"
    request_boundary.failure_status = 500
    request_scheduling, request_cycle = prepare_generation_cycle(factory, request_value)
    with pytest.raises(RequestNotStarted):
        run_target(
            request_value,
            settings,
            repository,
            local_structured_provider(settings, request_boundary),
            execution,
            packet=packet,
            identity=_identity(packet, request_value, pack, settings, execution),
            scheduling_repository=request_scheduling,
            cycle_id=request_cycle.cycle_id,
            before_request=_refuse_after_requests(request_boundary, 1),
        )
    request_failures = request_scheduling.read_target_failures(request_cycle.cycle_id)
    assert [failure.reason for failure in request_failures] == ["request_failed"]
    request_work = repository.read_work(
        TARGET_GROUP_ID, _work_key(packet, request_value, pack, settings, execution)
    )
    assert request_work is not None and request_work.status is InferenceWorkStatus.FAILED
    assert repository.read_completion(request_work.work_id) is None

    contract_packet = packet.model_copy(update={"candidates": tuple(reversed(packet.candidates))})
    contract_value = operational_input(contract_packet)
    contract_boundary = InferenceHttpBoundary(settings, content="{not valid json")
    contract_scheduling, contract_cycle = prepare_generation_cycle(factory, contract_value)
    with pytest.raises(RequestNotStarted):
        run_target(
            contract_value,
            settings,
            repository,
            local_structured_provider(settings, contract_boundary),
            execution,
            packet=contract_packet,
            identity=_identity(contract_packet, contract_value, pack, settings, execution),
            scheduling_repository=contract_scheduling,
            cycle_id=contract_cycle.cycle_id,
            before_request=_refuse_after_requests(contract_boundary, 1),
        )
    contract_failures = contract_scheduling.read_target_failures(contract_cycle.cycle_id)
    assert [failure.reason for failure in contract_failures] == ["provider_output"]
    contract_work = repository.read_work(
        TARGET_GROUP_ID, _work_key(contract_packet, contract_value, pack, settings, execution)
    )
    assert contract_work is not None and contract_work.status is InferenceWorkStatus.FAILED
    assert repository.read_completion(contract_work.work_id) is None

    # An infrastructure request failure (a non-retryable 401) records one nonexhausted episode for
    # the started request and propagates without any retry.
    infra_packet = packet.model_copy(
        update={"candidates": tuple(packet.candidates[3:]) + tuple(packet.candidates[:3])}
    )
    infra_value = operational_input(infra_packet)
    infra_boundary = InferenceHttpBoundary(settings)
    infra_boundary.failure_path = "v1/chat/completions"
    infra_boundary.failure_status = 401
    infra_scheduling, infra_cycle = prepare_generation_cycle(factory, infra_value)
    with pytest.raises(InferenceRequestError):
        run_target(
            infra_value,
            settings,
            repository,
            local_structured_provider(settings, infra_boundary),
            execution,
            packet=infra_packet,
            identity=_identity(infra_packet, infra_value, pack, settings, execution),
            scheduling_repository=infra_scheduling,
            cycle_id=infra_cycle.cycle_id,
        )
    assert len(infra_boundary.requests) == 1
    infra_failures = infra_scheduling.read_target_failures(infra_cycle.cycle_id)
    assert [failure.reason for failure in infra_failures] == ["request_failed"]
    assert infra_failures[0].exhausted is False
    infra_work = repository.read_work(
        TARGET_GROUP_ID, _work_key(infra_packet, infra_value, pack, settings, execution)
    )
    assert infra_work is not None and infra_work.status is InferenceWorkStatus.FAILED
    assert repository.read_completion(infra_work.work_id) is None

    # One bad attempt is retried immediately and the same work completes with one completion.
    retry_packet = packet.model_copy(
        update={"candidates": tuple(packet.candidates[1:]) + (packet.candidates[0],)}
    )
    retry_value = operational_input(retry_packet)
    good = empty_result_json()
    retry_boundary = InferenceHttpBoundary(settings)
    retry_boundary.content_for = lambda index, request: "{not valid json" if index == 0 else good
    retry_scheduling, retry_cycle = prepare_generation_cycle(factory, retry_value)
    completed = run_target(
        retry_value,
        settings,
        repository,
        local_structured_provider(settings, retry_boundary),
        execution,
        packet=retry_packet,
        identity=_identity(retry_packet, retry_value, pack, settings, execution),
        scheduling_repository=retry_scheduling,
        cycle_id=retry_cycle.cycle_id,
    )
    assert completed.status is InferenceWorkStatus.COMPLETED
    assert repository.read_completion(completed.work_id) is not None
    retry_failures = retry_scheduling.read_target_failures(retry_cycle.cycle_id)
    assert [failure.reason for failure in retry_failures] == ["provider_output"]
    assert retry_failures[0].exhausted is False

    # A candidate both a direct option and a TOO_BASIC_TRANSITIVE suppression is a contradiction.
    contradiction_packet = packet.model_copy(
        update={"candidates": tuple(packet.candidates[2:]) + tuple(packet.candidates[:2])}
    )
    contradiction_value = operational_input(contradiction_packet)
    known = contradiction_packet.candidates[0].course.course_code
    contradiction = json.loads(empty_result_json())
    contradiction["required"] = [
        {
            "requirement_id": "required_1",
            "options": [
                {
                    "course_codes": [known],
                    "evidence": "entry knowledge",
                    "confidence": 0.5,
                    "finding_flags": [],
                }
            ],
        }
    ]
    contradiction["routing"]["suppressed"] = [
        {
            "course_code": known,
            "outcome": "too_basic_transitive",
            "evidence": "foundation below entry level",
        }
    ]
    contradiction_boundary = InferenceHttpBoundary(settings, content=json.dumps(contradiction))
    contradiction_scheduling, contradiction_cycle = prepare_generation_cycle(
        factory, contradiction_value
    )
    with pytest.raises(RequestNotStarted):
        run_target(
            contradiction_value,
            settings,
            repository,
            local_structured_provider(settings, contradiction_boundary),
            execution,
            packet=contradiction_packet,
            identity=_identity(
                contradiction_packet, contradiction_value, pack, settings, execution
            ),
            scheduling_repository=contradiction_scheduling,
            cycle_id=contradiction_cycle.cycle_id,
            before_request=_refuse_after_requests(contradiction_boundary, 1),
        )
    contradiction_failures = contradiction_scheduling.read_target_failures(
        contradiction_cycle.cycle_id
    )
    assert [failure.reason for failure in contradiction_failures] == ["invalid_result"]
    contradiction_work = repository.read_work(
        TARGET_GROUP_ID,
        _work_key(contradiction_packet, contradiction_value, pack, settings, execution),
    )
    assert (
        contradiction_work is not None and contradiction_work.status is InferenceWorkStatus.FAILED
    )
    assert repository.read_completion(contradiction_work.work_id) is None


@pytest.mark.integration
def test_preclaim_refusal_creates_no_run_or_attempt(database) -> None:
    """A denied admission before the claim is refused and creates no reservation/history."""
    factory = database[1]
    _seed_target(factory)
    settings = target_settings()
    pack = load_prompt_pack("v9")
    execution = execution_profile(settings)
    repository = InferenceEvidenceRepository(factory)
    boundary = InferenceHttpBoundary(settings)

    packet = target_packet(50)
    value = operational_input(packet)
    scheduling, cycle = prepare_generation_cycle(factory, value)
    with pytest.raises(RequestNotStarted):
        run_target(
            value,
            settings,
            repository,
            local_structured_provider(settings, boundary),
            execution,
            packet=packet,
            identity=_identity(packet, value, pack, settings, execution),
            scheduling_repository=scheduling,
            cycle_id=cycle.cycle_id,
            before_request=lambda: False,
        )
    assert (
        repository.read_work(TARGET_GROUP_ID, _work_key(packet, value, pack, settings, execution))
        is None
    )
    assert boundary.requests == []
    assert scheduling.read_target_failures(cycle.cycle_id) == ()
    assert attempt_count(factory, TARGET_GROUP_ID) == 0


@pytest.mark.integration
def test_control_change_after_claim_declines_target_generation(database) -> None:
    """A withdrawal during the capped backoff yields after one committed attempt and episode."""
    factory = database[1]
    _seed_target(factory)
    settings = target_settings()
    pack = load_prompt_pack("v9")
    execution = execution_profile(settings)
    repository = InferenceEvidenceRepository(factory)

    packet = target_packet(50)
    value = operational_input(packet)
    scheduling, cycle = prepare_generation_cycle(factory, value)
    boundary = InferenceHttpBoundary(settings, content="{not valid json")
    admitted = {"value": True}
    sleeps: list[float] = []

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        admitted["value"] = False

    with pytest.raises(RequestNotStarted):
        run_target(
            value,
            settings,
            repository,
            local_structured_provider(settings, boundary),
            execution,
            packet=packet,
            identity=_identity(packet, value, pack, settings, execution),
            scheduling_repository=scheduling,
            cycle_id=cycle.cycle_id,
            before_request=lambda: admitted["value"],
            sleep=sleep,
        )
    assert len(boundary.requests) == 1
    assert sleeps and sleeps[0] <= settings.inference_retry_poll_seconds
    failures = scheduling.read_target_failures(cycle.cycle_id)
    assert len(failures) == 1
    assert failures[0].reason == "provider_output"
    assert failures[0].exhausted is False
    assert attempt_count(factory, TARGET_GROUP_ID) == 1
