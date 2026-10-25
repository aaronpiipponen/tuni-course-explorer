"""Contracts for inference evidence DTOs and canonical identities."""

from __future__ import annotations

from course_explorer.inference.evidence import (
    InferenceTargetWorkRequest,
    run_identity_sha256,
    work_key_sha256,
)
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
    }
    values.update(overrides)
    return InferenceTargetWorkRequest(**values)


def test_run_spec_derives_identity_from_settings_execution_and_versions() -> None:
    """Spec identity comes from validated settings, the execution profile, and version fields."""
    settings = inference_settings()
    execution = execution_profile(settings)
    spec = run_spec(settings, execution=execution)

    assert spec.model_identity == settings.primary_model_identity
    assert spec.runtime_identity == settings.local_runtime_identity(
        settings.inference_local_variants[0]
    )
    assert spec.prompt_version == settings.inference_prompt_version
    assert spec.schema_version == settings.inference_schema_version
    assert spec.pipeline_version == settings.inference_pipeline_version
    assert spec.configuration == {"route": execution.route}

    identity = run_identity_sha256(spec)

    # A changed model/runtime, version field, or route changes run identity.
    other_model = run_spec(inference_settings(INFERENCE_PRIMARY_MODEL_REPOSITORY="Qwen/Other"))
    assert run_identity_sha256(other_model) != identity
    assert run_identity_sha256(spec.model_copy(update={"pipeline_version": "v2"})) != identity
    route_changed = spec.model_copy(update={"configuration": {"route": "other-executor"}})
    assert run_identity_sha256(route_changed) != identity


def test_work_key_changes_for_target_activity_input_or_execution_identity_only() -> None:
    """Work identity is target activity plus exact input plus execution identity."""
    spec = run_spec()
    identity = run_identity_sha256(spec)
    base = work_request()
    key = work_key_sha256(base, identity, INPUT_SHA256)

    assert (
        work_key_sha256(work_request(target_group_id="tut-cu-g-27086"), identity, INPUT_SHA256)
        != key
    )
    assert (
        work_key_sha256(
            work_request(activity_as_of_academic_year_start=2027), identity, INPUT_SHA256
        )
        != key
    )
    assert work_key_sha256(work_request(activity_window_years=2), identity, INPUT_SHA256) != key
    assert work_key_sha256(base, identity, "6" * 64) != key
    assert work_key_sha256(base, "7" * 64, INPUT_SHA256) != key
