"""Inference records.

Revision ID: 20261008_0014
Revises: 20261007_0013
Create Date: 2026-10-08

Drops the inference evidence, telemetry, settings and per-cycle payload records: the shared
execution identity holds its coarse identity, target work holds its generation resumability state,
the model-attempt table holds its completion payload and generated time, proposals hold the accepted
pointer and composed payload, and the cycle and target checkpoint tables drop their duplicate state
matrices and timestamps. Upgrade performs explicit DDL drops.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20261008_0014"
down_revision: str | Sequence[str] | None = "20261007_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_RUN_CHECKS = (
    "ck_inference_pipeline_runs_policy_sha256_sha256",
    "ck_inference_pipeline_runs_catalogue_identity_sha256_sha256",
    "ck_inference_pipeline_runs_configuration_sha256_sha256",
    "ck_inference_pipeline_runs_activity_year_start_positive",
    "ck_inference_pipeline_runs_activity_window_years_positive",
    "ck_inference_pipeline_runs_lifecycle_consistent",
    "ck_inference_pipeline_runs_timestamps_ordered",
)
_RUN_COLUMNS = (
    "pipeline_type",
    "policy_sha256",
    "catalogue_identity_sha256",
    "configuration_sha256",
    "activity_as_of_academic_year_start",
    "activity_window_years",
    "status",
    "started_at",
    "finished_at",
    "failure_type",
    "failure_message",
    "created_at",
    "updated_at",
)

_WORK_CHECKS = (
    "ck_inference_target_work_run_identity_sha256_sha256",
    "ck_inference_target_work_attempt_count_nonnegative",
    "ck_inference_target_work_lifecycle_consistent",
    "ck_inference_target_work_timestamps_ordered",
)
_WORK_COLUMNS = (
    "run_identity_sha256",
    "attempt_count",
    "last_attempted_at",
    "completed_at",
    "last_error_type",
    "last_error_message",
    "created_at",
    "updated_at",
)

_ATTEMPT_CHECKS = (
    "ck_inference_model_attempts_attempt_number_positive",
    "ck_inference_model_attempts_request_sha256_sha256",
    "ck_inference_model_attempts_response_sha256_sha256",
    "ck_inference_model_attempts_response_hash_pair_consistent",
    "ck_inference_model_attempts_counts_nonnegative",
    "ck_inference_model_attempts_rates_positive",
    "ck_inference_model_attempts_timestamps_ordered",
    "ck_inference_model_attempts_lifecycle_consistent",
)
_ATTEMPT_COLUMNS = (
    "pipeline_run_id",
    "attempt_number",
    "status",
    "request_sha256",
    "raw_response",
    "response_sha256",
    "parsed_response",
    "validated_result",
    "observed_model",
    "observed_system_fingerprint",
    "prompt_tokens",
    "completion_tokens",
    "prompt_tokens_per_second",
    "completion_tokens_per_second",
    "error_type",
    "error_message",
    "started_at",
    "created_at",
)


def upgrade() -> None:
    """Drop the inference columns, checks, indexes and unique constraints."""
    for name in _RUN_CHECKS:
        op.drop_constraint(op.f(name), "inference_pipeline_runs", type_="check")
    for column in _RUN_COLUMNS:
        op.drop_column("inference_pipeline_runs", column)

    for name in _WORK_CHECKS:
        op.drop_constraint(op.f(name), "inference_target_work", type_="check")
    for column in _WORK_COLUMNS:
        op.drop_column("inference_target_work", column)

    for name in _ATTEMPT_CHECKS:
        op.drop_constraint(op.f(name), "inference_model_attempts", type_="check")
    op.drop_constraint(
        op.f("uq_inference_model_attempts_work_number"),
        "inference_model_attempts",
        type_="unique",
    )
    for column in _ATTEMPT_COLUMNS:
        op.drop_column("inference_model_attempts", column)

    op.drop_constraint(
        op.f("ck_inference_proposals_official_snapshot_sha256_sha256"),
        "inference_proposals",
        type_="check",
    )
    op.drop_index("ix_inference_proposals_target_course_id", table_name="inference_proposals")
    for column in ("source_work_id", "official_snapshot_sha256", "dedup_diagnostics", "created_at"):
        op.drop_column("inference_proposals", column)

    op.drop_column("inference_course_processing", "created_at")
    op.drop_column("inference_course_processing", "updated_at")

    op.drop_constraint(
        op.f("ck_inference_processing_cycles_completion_consistent"),
        "inference_processing_cycles",
        type_="check",
    )
    op.drop_column("inference_processing_cycles", "completed_at")
    op.drop_column("inference_processing_cycles", "updated_at")

    for name in (
        "ck_inference_processing_targets_payloads_consistent",
        "ck_inference_processing_targets_stage_order_consistent",
        "ck_inference_processing_targets_failure_consistent",
    ):
        op.drop_constraint(op.f(name), "inference_processing_targets", type_="check")
    op.drop_column("inference_processing_targets", "created_at")
    op.drop_column("inference_processing_targets", "updated_at")


def downgrade() -> None:
    """Refuse the irreversible record conversion."""
    raise RuntimeError(
        "20261008_0014 is an irreversible inference-record conversion; "
        "restore from the pre-conversion backup instead of downgrading"
    )
