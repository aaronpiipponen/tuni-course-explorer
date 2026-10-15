"""Contracts for inference evidence DTOs and canonical identities."""

from __future__ import annotations

import pytest

from course_explorer.inference.domain import target_result_json_schema
from course_explorer.inference.evidence import (
    InferencePipelineRunSpec,
    InferenceTargetWorkRequest,
    canonical_json_sha256,
    run_identity_sha256,
    work_key_sha256,
)
from course_explorer.inference.prompts import load_prompt_pack
from tests.inference._fixture_support import (
    execution_profile,
    inference_settings,
    run_spec,
)

INPUT_SHA256 = "3" * 64


def work_request(**overrides: object) -> InferenceTargetWorkRequest:
    """Build one otherwise valid target-work request."""
    values: dict[str, object] = {
        "target_group_id": "tut-cu-g-27096",
        "activity_as_of_academic_year_start": 2026,
        "activity_window_years": 3,
        "input_sha256": INPUT_SHA256,
    }
    values.update(overrides)
    return InferenceTargetWorkRequest(**values)


def test_run_spec_derives_exact_accepted_contract_and_canonical_hashes() -> None:
    """Spec identity comes from validated settings, the prompt pack, the execution, and schema."""
    settings = inference_settings()
    execution = execution_profile(settings)
    pack = load_prompt_pack("v9")
    spec = run_spec(settings, execution=execution)

    assert spec.model_identity == settings.primary_model_identity
    assert spec.runtime_identity == settings.local_runtime_identity(
        settings.inference_local_variants[0]
    )
    assert spec.prompt_version == pack.version == settings.inference_prompt_version
    assert spec.prompt_content_sha256 == pack.content_sha256
    assert spec.schema_version == settings.inference_schema_version
    assert spec.schema_sha256 == canonical_json_sha256(target_result_json_schema("v2"))
    assert spec.pipeline_version == settings.inference_pipeline_version
    assert spec.configuration == {"route": execution.route}

    identity = run_identity_sha256(spec)

    # A changed model/runtime, prompt content, schema, pipeline, or route changes run identity.
    other_model = run_spec(inference_settings(INFERENCE_PRIMARY_MODEL_REPOSITORY="Qwen/Other"))
    assert run_identity_sha256(other_model) != identity
    assert (
        run_identity_sha256(spec.model_copy(update={"prompt_content_sha256": "9" * 64})) != identity
    )
    route_changed = spec.model_copy(update={"configuration": {"route": "other-executor"}})
    assert run_identity_sha256(route_changed) != identity

    # A prompt pack whose version disagrees with configured settings is rejected outright.
    with pytest.raises(ValueError):
        InferencePipelineRunSpec.from_contracts(
            inference_settings(),
            pack.model_copy(update={"version": "v2"}),
            execution=execution,
        )


def test_work_key_changes_for_target_activity_input_or_execution_identity_only() -> None:
    """Work identity is target activity plus exact input plus execution identity."""
    spec = run_spec()
    identity = run_identity_sha256(spec)
    base = work_request()
    key = work_key_sha256(base, identity)

    assert work_key_sha256(work_request(target_group_id="tut-cu-g-27086"), identity) != key
    assert work_key_sha256(work_request(activity_as_of_academic_year_start=2027), identity) != key
    assert work_key_sha256(work_request(activity_window_years=2), identity) != key
    assert work_key_sha256(work_request(input_sha256="6" * 64), identity) != key
    assert work_key_sha256(base, "7" * 64) != key
