"""Contracts for the fit-only operational router over real evidence and the shared HTTP boundary."""

from __future__ import annotations

from typing import Any

import pytest

from course_explorer.curriculum_repository import CurriculumRepository
from course_explorer.enums import InferenceWorkStatus
from course_explorer.http_retry import RequestNotStarted
from course_explorer.inference import routing
from course_explorer.inference import target_pass as target_pass_module
from course_explorer.inference.evidence import run_identity_sha256, work_key_sha256
from course_explorer.inference.evidence_repository import InferenceEvidenceRepository
from course_explorer.inference.failures import TargetPreparationFailure
from course_explorer.inference.operational import (
    materialize_selection_packet,
    prepare_operational_catalogue,
)
from course_explorer.inference.prompts import load_prompt_pack
from course_explorer.inference.target_pass import prepare_target_request, target_work_identity
from course_explorer.teaching_text.repository import DerivedTranslationRepository
from course_explorer.teaching_text.service import TeachingTextService
from tests.inference._fixture_support import embedding_settings
from tests.inference._http_support import InferenceHttpBoundary, install_inference_http
from tests.inference._scheduling_support import (
    build_pool,
    build_target_input,
    prepare_generation_cycle,
    seed_courses,
)
from tests.inference._target_support import TARGET_CODE, TARGET_GROUP_ID, target_settings

CANDIDATES = tuple(f"rc-{index:02d}" for index in range(50))


class _RecordingRuntime:
    """Record fit-key activation/stop order for the routing owner."""

    def __init__(self) -> None:
        self.controls: list[str] = []
        self._active: Any | None = None

    def activate(self, variant: Any) -> None:
        self.controls.append(f"activate:{variant.alias}")
        self._active = variant

    def stop(self) -> None:
        self.controls.append("stop")
        self._active = None

    def active_variant(self) -> Any | None:
        return self._active


def _catalogue(factory: object):
    curriculum = CurriculumRepository(factory)
    teaching_text = TeachingTextService(curriculum, DerivedTranslationRepository(factory))
    return prepare_operational_catalogue(curriculum, teaching_text, embedding_settings())


def _work_key(value: Any, packet: Any, pack: Any, settings: Any, execution: Any) -> str:
    prepared = prepare_target_request(value, pack, settings, packet=packet)
    identity = target_work_identity(value, settings, execution, packet=packet, prepared=prepared)
    return work_key_sha256(
        identity.work_request, run_identity_sha256(identity.spec), identity.input_sha256
    )


@pytest.mark.integration
@pytest.mark.parametrize(
    ("prompt_tokens", "route"),
    [
        (1000, "local"),
        (130000, "local"),
    ],
)
def test_runtime_switch_is_fit_only_and_callbacks_reach_one_writer(
    database: tuple[Any, Any],
    monkeypatch: pytest.MonkeyPatch,
    prompt_tokens: int,
    route: str,
) -> None:
    """The router selects by fit and records a genuine execution profile through the one writer."""
    factory = database[1]
    seed_courses(
        factory,
        [(TARGET_GROUP_ID, TARGET_CODE, True)]
        + [(c, f"RC.{i}", False) for i, c in enumerate(CANDIDATES)],
    )
    settings = target_settings()
    pack = load_prompt_pack("v9")
    catalogue = _catalogue(factory)
    boundary = InferenceHttpBoundary(settings, prompt_tokens=prompt_tokens)
    install_inference_http(monkeypatch, boundary)
    evidence = InferenceEvidenceRepository(factory)
    runtime = _RecordingRuntime()
    identities: list[Any] = []

    render_count = 0
    original_render = target_pass_module.render_target_request

    def render_once(packet: Any, pack_value: Any, schema_version: str) -> Any:
        """Render one request per routed invocation and reject a second render."""
        nonlocal render_count
        render_count += 1
        if render_count > 1:
            raise AssertionError("a routed invocation rendered its request twice")
        return original_render(packet, pack_value, schema_version)

    monkeypatch.setattr(target_pass_module, "render_target_request", render_once)

    pool = build_pool(factory, TARGET_GROUP_ID, CANDIDATES)
    value = build_target_input(pool)
    scheduling, cycle = prepare_generation_cycle(factory, value)
    render_count = 0
    work = routing.run_routed_operational_target(
        value,
        pack,
        settings,
        evidence,
        catalogue=catalogue,
        scheduling_repository=scheduling,
        cycle_id=cycle.cycle_id,
        runtime=runtime,
        on_identity=identities.append,
        before_request=lambda: True,
    )
    assert work.status is InferenceWorkStatus.COMPLETED
    assert evidence.read_completion(work.work_id) is not None
    assert render_count == 1
    run = evidence.read_run(work.created_by_run_id)
    assert len(identities) == 1
    assert run.spec.configuration == {"route": route}
    assert runtime.controls[0] == f"activate:{settings.inference_local_variants[0].alias}"

    if prompt_tokens != 1000:
        return

    # A failed local tokenizer retries a bounded preparation action and surfaces as a preparation
    # failure, never a fit failure, injected route, identity callback or model completion.
    failing_pool = build_pool(factory, TARGET_GROUP_ID, tuple(reversed(CANDIDATES)))
    failing = build_target_input(failing_pool)
    failing_scheduling, failing_cycle = prepare_generation_cycle(factory, failing)
    failing_packet = materialize_selection_packet(failing.references, catalogue)
    execution = routing.local_execution(settings, settings.inference_local_variants[0])
    render_count = 0
    failing_key = _work_key(failing, failing_packet, pack, settings, execution)
    boundary.failure_path = "apply-template"
    boundary.failure_status = 500
    identities_before = len(identities)
    render_count = 0
    with pytest.raises(TargetPreparationFailure) as preparation_error:
        routing.run_routed_operational_target(
            failing,
            pack,
            settings,
            evidence,
            catalogue=catalogue,
            scheduling_repository=failing_scheduling,
            cycle_id=failing_cycle.cycle_id,
            runtime=runtime,
            before_request=lambda: True,
        )
    assert preparation_error.value.exhausted is True
    assert preparation_error.value.attempt_count == settings.inference_max_attempts
    assert preparation_error.value.reason == "request_failed"
    assert len(identities) == identities_before
    assert render_count == 1
    assert evidence.read_work(TARGET_GROUP_ID, failing_key) is None

    # The same retained input recovers through the fit route once the transient failure ends.
    boundary.failure_path = None
    render_count = 0
    recovered = routing.run_routed_operational_target(
        failing,
        pack,
        settings,
        evidence,
        catalogue=catalogue,
        scheduling_repository=failing_scheduling,
        cycle_id=failing_cycle.cycle_id,
        runtime=runtime,
        on_identity=identities.append,
        before_request=lambda: True,
    )
    assert recovered.status is InferenceWorkStatus.COMPLETED
    assert len(identities) == identities_before + 1
    assert render_count == 1

    # A denied admission raises before any runtime activation, provider, or writer call.
    controls_before = list(runtime.controls)
    render_count = 0
    with pytest.raises(RequestNotStarted):
        routing.run_routed_operational_target(
            value,
            pack,
            settings,
            evidence,
            catalogue=catalogue,
            scheduling_repository=scheduling,
            cycle_id=cycle.cycle_id,
            runtime=runtime,
            before_request=lambda: False,
        )
    assert runtime.controls == controls_before
    assert render_count == 0
