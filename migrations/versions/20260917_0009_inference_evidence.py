"""inference evidence foundation.

Revision ID: 20260917_0009
Revises: 20260917_0008
Create Date: 2026-09-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260917_0009"
down_revision: str | Sequence[str] | None = "20260917_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_GENERATION_COLUMNS_PRESENT = (
    "raw_response IS NOT NULL AND parsed_response IS NOT NULL "
    "AND observed_model IS NOT NULL AND observed_system_fingerprint IS NOT NULL "
    "AND prompt_tokens IS NOT NULL AND completion_tokens IS NOT NULL "
    "AND prompt_tokens_per_second IS NOT NULL AND completion_tokens_per_second IS NOT NULL"
)
_GENERATION_COLUMNS_ABSENT = (
    "raw_response IS NULL AND parsed_response IS NULL "
    "AND observed_model IS NULL AND observed_system_fingerprint IS NULL "
    "AND prompt_tokens IS NULL AND completion_tokens IS NULL "
    "AND prompt_tokens_per_second IS NULL AND completion_tokens_per_second IS NULL"
)


def upgrade() -> None:
    """Create the inference-owned run, target-work, and immutable attempt evidence tables."""
    op.create_table(
        "inference_pipeline_runs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "pipeline_type",
            sa.Enum(
                "target_result",
                name="inference_pipeline_type",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("model_identity", sa.Text(), nullable=False),
        sa.Column("runtime_identity", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        sa.Column("prompt_content_sha256", sa.Text(), nullable=False),
        sa.Column("schema_version", sa.Text(), nullable=False),
        sa.Column("schema_sha256", sa.Text(), nullable=False),
        sa.Column("pipeline_version", sa.Text(), nullable=False),
        sa.Column("policy_sha256", sa.Text(), nullable=False),
        sa.Column("catalogue_identity_sha256", sa.Text(), nullable=False),
        sa.Column("run_identity_sha256", sa.Text(), nullable=False),
        sa.Column(
            "configuration",
            postgresql.JSONB(astext_type=sa.Text(), none_as_null=True),
            nullable=False,
        ),
        sa.Column("configuration_sha256", sa.Text(), nullable=False),
        sa.Column("activity_as_of_academic_year_start", sa.Integer(), nullable=False),
        sa.Column("activity_window_years", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "running",
                "completed",
                "failed",
                name="inference_run_status",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_type", sa.Text(), nullable=True),
        sa.Column("failure_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "btrim(model_identity) <> ''",
            name=op.f("ck_inference_pipeline_runs_model_identity_not_blank"),
        ),
        sa.CheckConstraint(
            "btrim(runtime_identity) <> ''",
            name=op.f("ck_inference_pipeline_runs_runtime_identity_not_blank"),
        ),
        sa.CheckConstraint(
            "btrim(prompt_version) <> ''",
            name=op.f("ck_inference_pipeline_runs_prompt_version_not_blank"),
        ),
        sa.CheckConstraint(
            "prompt_content_sha256 ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_inference_pipeline_runs_prompt_content_sha256_sha256"),
        ),
        sa.CheckConstraint(
            "btrim(schema_version) <> ''",
            name=op.f("ck_inference_pipeline_runs_schema_version_not_blank"),
        ),
        sa.CheckConstraint(
            "schema_sha256 ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_inference_pipeline_runs_schema_sha256_sha256"),
        ),
        sa.CheckConstraint(
            "btrim(pipeline_version) <> ''",
            name=op.f("ck_inference_pipeline_runs_pipeline_version_not_blank"),
        ),
        sa.CheckConstraint(
            "policy_sha256 ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_inference_pipeline_runs_policy_sha256_sha256"),
        ),
        sa.CheckConstraint(
            "catalogue_identity_sha256 ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_inference_pipeline_runs_catalogue_identity_sha256_sha256"),
        ),
        sa.CheckConstraint(
            "run_identity_sha256 ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_inference_pipeline_runs_run_identity_sha256_sha256"),
        ),
        sa.CheckConstraint(
            "configuration_sha256 ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_inference_pipeline_runs_configuration_sha256_sha256"),
        ),
        sa.CheckConstraint(
            "activity_as_of_academic_year_start > 0",
            name=op.f("ck_inference_pipeline_runs_activity_year_start_positive"),
        ),
        sa.CheckConstraint(
            "activity_window_years > 0",
            name=op.f("ck_inference_pipeline_runs_activity_window_years_positive"),
        ),
        sa.CheckConstraint(
            "(status = 'running' AND finished_at IS NULL AND failure_type IS NULL "
            "AND failure_message IS NULL) "
            "OR (status = 'completed' AND finished_at IS NOT NULL AND failure_type IS NULL "
            "AND failure_message IS NULL) "
            "OR (status = 'failed' AND finished_at IS NOT NULL "
            "AND failure_type IS NOT NULL AND btrim(failure_type) <> '' "
            "AND failure_message IS NOT NULL AND btrim(failure_message) <> '')",
            name=op.f("ck_inference_pipeline_runs_lifecycle_consistent"),
        ),
        sa.CheckConstraint(
            "finished_at IS NULL OR finished_at >= started_at",
            name=op.f("ck_inference_pipeline_runs_timestamps_ordered"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_inference_pipeline_runs")),
    )
    op.create_table(
        "inference_target_work",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_by_run_id", sa.UUID(), nullable=False),
        sa.Column("target_course_id", sa.UUID(), nullable=False),
        sa.Column("activity_as_of_academic_year_start", sa.Integer(), nullable=False),
        sa.Column("activity_window_years", sa.Integer(), nullable=False),
        sa.Column("input_sha256", sa.Text(), nullable=False),
        sa.Column("run_identity_sha256", sa.Text(), nullable=False),
        sa.Column("work_key_sha256", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "completed",
                "failed",
                name="inference_work_status",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("attempt_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("last_attempted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_type", sa.Text(), nullable=True),
        sa.Column("last_error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "activity_as_of_academic_year_start > 0",
            name=op.f("ck_inference_target_work_activity_year_start_positive"),
        ),
        sa.CheckConstraint(
            "activity_window_years > 0",
            name=op.f("ck_inference_target_work_activity_window_years_positive"),
        ),
        sa.CheckConstraint(
            "input_sha256 ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_inference_target_work_input_sha256_sha256"),
        ),
        sa.CheckConstraint(
            "run_identity_sha256 ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_inference_target_work_run_identity_sha256_sha256"),
        ),
        sa.CheckConstraint(
            "work_key_sha256 ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_inference_target_work_work_key_sha256_sha256"),
        ),
        sa.CheckConstraint(
            "attempt_count >= 0", name=op.f("ck_inference_target_work_attempt_count_nonnegative")
        ),
        sa.CheckConstraint(
            "(status = 'pending' AND completed_at IS NULL "
            "AND last_error_type IS NULL AND last_error_message IS NULL) "
            "OR (status = 'completed' AND attempt_count >= 1 "
            "AND last_attempted_at IS NOT NULL AND completed_at IS NOT NULL "
            "AND last_error_type IS NULL AND last_error_message IS NULL) "
            "OR (status = 'failed' AND attempt_count >= 1 "
            "AND last_attempted_at IS NOT NULL AND completed_at IS NULL "
            "AND last_error_type IS NOT NULL AND btrim(last_error_type) <> '' "
            "AND last_error_message IS NOT NULL AND btrim(last_error_message) <> '')",
            name=op.f("ck_inference_target_work_lifecycle_consistent"),
        ),
        sa.CheckConstraint(
            "completed_at IS NULL OR completed_at >= last_attempted_at",
            name=op.f("ck_inference_target_work_timestamps_ordered"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by_run_id"],
            ["inference_pipeline_runs.id"],
            name=op.f("fk_inference_target_work_created_by_run_id_inference_pipeline_runs"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["target_course_id"],
            ["courses.id"],
            name=op.f("fk_inference_target_work_target_course_id_courses"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_inference_target_work")),
        sa.UniqueConstraint(
            "target_course_id",
            "work_key_sha256",
            name="uq_inference_target_work_target_work_key",
        ),
    )
    op.create_index(
        "ix_inference_target_work_status",
        "inference_target_work",
        ["status"],
        unique=False,
    )
    op.create_table(
        "inference_model_attempts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("target_work_id", sa.UUID(), nullable=False),
        sa.Column("pipeline_run_id", sa.UUID(), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "validated",
                "contract_error",
                "request_error",
                name="inference_attempt_status",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column(
            "request_payload",
            postgresql.JSONB(astext_type=sa.Text(), none_as_null=True),
            nullable=False,
        ),
        sa.Column("request_sha256", sa.Text(), nullable=False),
        sa.Column("raw_response", sa.Text(), nullable=True),
        sa.Column("response_sha256", sa.Text(), nullable=True),
        sa.Column(
            "parsed_response",
            postgresql.JSONB(astext_type=sa.Text(), none_as_null=True),
            nullable=True,
        ),
        sa.Column(
            "validated_result",
            postgresql.JSONB(astext_type=sa.Text(), none_as_null=True),
            nullable=True,
        ),
        sa.Column("observed_model", sa.Text(), nullable=True),
        sa.Column("observed_system_fingerprint", sa.Text(), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("prompt_tokens_per_second", sa.Numeric(), nullable=True),
        sa.Column("completion_tokens_per_second", sa.Numeric(), nullable=True),
        sa.Column("error_type", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "attempt_number >= 1", name=op.f("ck_inference_model_attempts_attempt_number_positive")
        ),
        sa.CheckConstraint(
            "request_sha256 ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_inference_model_attempts_request_sha256_sha256"),
        ),
        sa.CheckConstraint(
            "response_sha256 ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_inference_model_attempts_response_sha256_sha256"),
        ),
        sa.CheckConstraint(
            "(raw_response IS NULL AND response_sha256 IS NULL) "
            "OR (raw_response IS NOT NULL AND btrim(raw_response) <> '' "
            "AND response_sha256 IS NOT NULL)",
            name=op.f("ck_inference_model_attempts_response_hash_pair_consistent"),
        ),
        sa.CheckConstraint(
            "(prompt_tokens IS NULL OR prompt_tokens >= 0) "
            "AND (completion_tokens IS NULL OR completion_tokens >= 0)",
            name=op.f("ck_inference_model_attempts_counts_nonnegative"),
        ),
        sa.CheckConstraint(
            "(prompt_tokens_per_second IS NULL OR prompt_tokens_per_second > 0) "
            "AND (completion_tokens_per_second IS NULL OR completion_tokens_per_second > 0)",
            name=op.f("ck_inference_model_attempts_rates_positive"),
        ),
        sa.CheckConstraint(
            "finished_at >= started_at",
            name=op.f("ck_inference_model_attempts_timestamps_ordered"),
        ),
        sa.CheckConstraint(
            "(status = 'validated' AND "
            + _GENERATION_COLUMNS_PRESENT
            + " AND validated_result IS NOT NULL "
            "AND error_type IS NULL AND error_message IS NULL) "
            "OR (status = 'contract_error' AND (( "
            + _GENERATION_COLUMNS_PRESENT
            + " ) OR ( "
            + _GENERATION_COLUMNS_ABSENT
            + " )) AND validated_result IS NULL "
            "AND error_type IS NOT NULL AND btrim(error_type) <> '' "
            "AND error_message IS NOT NULL AND btrim(error_message) <> '') "
            "OR (status = 'request_error' AND "
            + _GENERATION_COLUMNS_ABSENT
            + " AND validated_result IS NULL "
            "AND error_type IS NOT NULL AND btrim(error_type) <> '' "
            "AND error_message IS NOT NULL AND btrim(error_message) <> '')",
            name=op.f("ck_inference_model_attempts_lifecycle_consistent"),
        ),
        sa.ForeignKeyConstraint(
            ["target_work_id"],
            ["inference_target_work.id"],
            name=op.f("fk_inference_model_attempts_target_work_id_inference_target_work"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["pipeline_run_id"],
            ["inference_pipeline_runs.id"],
            name=op.f("fk_inference_model_attempts_pipeline_run_id_inference_pipeline_runs"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_inference_model_attempts")),
        sa.UniqueConstraint(
            "target_work_id",
            "attempt_number",
            name="uq_inference_model_attempts_work_number",
        ),
    )


def downgrade() -> None:
    """Drop the inference evidence tables."""
    op.drop_table("inference_model_attempts")
    op.drop_index("ix_inference_target_work_status", table_name="inference_target_work")
    op.drop_table("inference_target_work")
    op.drop_table("inference_pipeline_runs")
