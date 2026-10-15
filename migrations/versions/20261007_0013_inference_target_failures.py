"""inference target failures.

Revision ID: 20261007_0013
Revises: 20260930_0012
Create Date: 2026-10-07

Adds one append-only failure table: a per-cycle, per-target summary of a fully failed target episode
with its failing stage, actual bounded action count, producer error class, fixed reason and
exhaustion flag. It creates this table and its index. Downgrade refuses while any failure row is
retained, else drops this table and its index.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261007_0013"
down_revision: str | Sequence[str] | None = "20260930_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the additive inference target-failure history table and its index."""
    op.create_table(
        "inference_target_failures",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("cycle_id", sa.UUID(), nullable=False),
        sa.Column("target_course_id", sa.UUID(), nullable=False),
        sa.Column("stage", sa.Text(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("error_type", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("exhausted", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "stage IN ('multiview','rerank','inference_preparation','inference')",
            name=op.f("ck_inference_target_failures_stage_valid"),
        ),
        sa.CheckConstraint(
            "attempt_count > 0",
            name=op.f("ck_inference_target_failures_attempt_count_positive"),
        ),
        sa.CheckConstraint(
            "length(error_type) BETWEEN 1 AND 200 AND error_type ~ '^[A-Za-z_][A-Za-z0-9_]*$'",
            name=op.f("ck_inference_target_failures_error_type_safe"),
        ),
        sa.CheckConstraint(
            "reason IN ('missing_target_chunks','insufficient_candidates','incomplete_views',"
            "'request_failed','provider_output','invalid_result','ambiguous_code',"
            "'multiple_requirement_sets','target_direct_source')",
            name=op.f("ck_inference_target_failures_reason_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["cycle_id", "target_course_id"],
            [
                "inference_processing_targets.cycle_id",
                "inference_processing_targets.target_course_id",
            ],
            name=op.f("fk_inference_target_failures_target"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_inference_target_failures")),
    )
    op.create_index(
        "ix_inference_target_failures_cycle_target_created",
        "inference_target_failures",
        ["cycle_id", "target_course_id", "created_at", "id"],
        unique=False,
    )


def downgrade() -> None:
    """Refuse to lose retained failure history, else drop only this table and its index."""
    bind = op.get_bind()
    count = bind.execute(sa.text("SELECT count(*) FROM inference_target_failures")).scalar_one()
    if count:
        raise RuntimeError(
            f"cannot downgrade inference target failures: {count} rows would be lost"
        )
    op.drop_index(
        "ix_inference_target_failures_cycle_target_created",
        table_name="inference_target_failures",
    )
    op.drop_table("inference_target_failures")
