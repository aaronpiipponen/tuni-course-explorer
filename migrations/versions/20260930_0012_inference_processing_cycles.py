"""inference processing cycles.

Revision ID: 20260930_0012
Revises: 20260929_0011
Create Date: 2026-09-30

Creates the three inference-owned scheduling tables: the per-canonical-course teaching-text
processing marker with its retained accepted pointer, the durable processing cycle with its global
stage, and the strict per-target stage checkpoints. The stage, payload, failure and hash checks mirror
the closed scheduling DTO matrices, and every foreign key is RESTRICT. Downgrade refuses while any of
the three tables is nonempty.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260930_0012"
down_revision: str | Sequence[str] | None = "20260929_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the inference-owned processing marker/cycle/target scheduling store."""
    op.create_table(
        "inference_course_processing",
        sa.Column("course_id", sa.UUID(), nullable=False),
        sa.Column("teaching_text_sha256", sa.Text(), nullable=False),
        sa.Column("processed", sa.Boolean(), nullable=False),
        sa.Column("was_active", sa.Boolean(), nullable=False),
        sa.Column("accepted_proposal_id", sa.UUID(), nullable=True),
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
            "teaching_text_sha256 ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_inference_course_processing_teaching_text_sha256_sha256"),
        ),
        sa.ForeignKeyConstraint(
            ["course_id"],
            ["courses.id"],
            name=op.f("fk_inference_course_processing_course_id_courses"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["accepted_proposal_id"],
            ["inference_proposals.id"],
            name=op.f("fk_inference_course_processing_accepted_proposal_id_inference_proposals"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("course_id", name=op.f("pk_inference_course_processing")),
    )

    op.create_table(
        "inference_processing_cycles",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("input_sha256", sa.Text(), nullable=False),
        sa.Column("stage", sa.Text(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
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
            "input_sha256 ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_inference_processing_cycles_input_sha256_sha256"),
        ),
        sa.CheckConstraint(
            "stage IN ('multiview','rerank','inference','publication','complete')",
            name=op.f("ck_inference_processing_cycles_stage_valid"),
        ),
        sa.CheckConstraint(
            "(stage = 'complete') = (completed_at IS NOT NULL)",
            name=op.f("ck_inference_processing_cycles_completion_consistent"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_inference_processing_cycles")),
    )
    op.create_index(
        "ix_inference_processing_cycles_created_at",
        "inference_processing_cycles",
        ["created_at", "id"],
        unique=False,
    )

    op.create_table(
        "inference_processing_targets",
        sa.Column("cycle_id", sa.UUID(), nullable=False),
        sa.Column("target_course_id", sa.UUID(), nullable=False),
        sa.Column("multiview_state", sa.Text(), nullable=False),
        sa.Column("rerank_state", sa.Text(), nullable=False),
        sa.Column("inference_state", sa.Text(), nullable=False),
        sa.Column(
            "pool_input",
            postgresql.JSONB(astext_type=sa.Text(), none_as_null=True),
            nullable=True,
        ),
        sa.Column(
            "target_input",
            postgresql.JSONB(astext_type=sa.Text(), none_as_null=True),
            nullable=True,
        ),
        sa.Column("generation_work_key_sha256", sa.Text(), nullable=True),
        sa.Column("proposal_id", sa.UUID(), nullable=True),
        sa.Column("error_type", sa.Text(), nullable=True),
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
            "multiview_state IN ('pending','completed','failed')",
            name=op.f("ck_inference_processing_targets_multiview_state_valid"),
        ),
        sa.CheckConstraint(
            "rerank_state IN ('pending','completed','skipped','failed')",
            name=op.f("ck_inference_processing_targets_rerank_state_valid"),
        ),
        sa.CheckConstraint(
            "inference_state IN ('pending','completed','skipped','failed')",
            name=op.f("ck_inference_processing_targets_inference_state_valid"),
        ),
        sa.CheckConstraint(
            "((multiview_state = 'completed') = (pool_input IS NOT NULL)) "
            "AND ((rerank_state = 'completed') = (target_input IS NOT NULL)) "
            "AND ((inference_state = 'completed') = (proposal_id IS NOT NULL)) "
            "AND (inference_state <> 'completed' OR generation_work_key_sha256 IS NOT NULL) "
            "AND (inference_state <> 'skipped' OR generation_work_key_sha256 IS NULL)",
            name=op.f("ck_inference_processing_targets_payloads_consistent"),
        ),
        sa.CheckConstraint(
            "(rerank_state = 'pending' OR multiview_state = 'completed') "
            "AND (inference_state = 'pending' OR (multiview_state = 'completed' "
            "AND (rerank_state = 'completed' "
            "OR (rerank_state = 'skipped' AND inference_state = 'skipped')))) "
            "AND (rerank_state <> 'skipped' OR inference_state = 'skipped')",
            name=op.f("ck_inference_processing_targets_stage_order_consistent"),
        ),
        sa.CheckConstraint(
            "generation_work_key_sha256 IS NULL OR generation_work_key_sha256 ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_inference_processing_targets_generation_work_key_sha256_sha256"),
        ),
        sa.CheckConstraint(
            "error_type IS NULL OR (length(error_type) BETWEEN 1 AND 200 "
            "AND error_type ~ '^[A-Za-z_][A-Za-z0-9_]*$')",
            name=op.f("ck_inference_processing_targets_error_type_safe"),
        ),
        sa.CheckConstraint(
            "(multiview_state = 'failed' OR rerank_state = 'failed' "
            "OR inference_state = 'failed') = (error_type IS NOT NULL)",
            name=op.f("ck_inference_processing_targets_failure_consistent"),
        ),
        sa.ForeignKeyConstraint(
            ["cycle_id"],
            ["inference_processing_cycles.id"],
            name=op.f("fk_inference_processing_targets_cycle_id_inference_processing_cycles"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["target_course_id"],
            ["courses.id"],
            name=op.f("fk_inference_processing_targets_target_course_id_courses"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["proposal_id"],
            ["inference_proposals.id"],
            name=op.f("fk_inference_processing_targets_proposal_id_inference_proposals"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "cycle_id", "target_course_id", name=op.f("pk_inference_processing_targets")
        ),
    )


def downgrade() -> None:
    """Refuse to lose durable checkpoints, else drop only the three inference-owned tables."""
    bind = op.get_bind()
    counts = {
        table: bind.execute(sa.text(f"SELECT count(*) FROM {table}")).scalar_one()
        for table in (
            "inference_processing_targets",
            "inference_course_processing",
            "inference_processing_cycles",
        )
    }
    nonempty = {table: count for table, count in counts.items() if count}
    if nonempty:
        raise RuntimeError(
            f"cannot downgrade inference processing cycles: {nonempty} rows would be lost"
        )
    op.drop_table("inference_processing_targets")
    op.drop_index(
        "ix_inference_processing_cycles_created_at", table_name="inference_processing_cycles"
    )
    op.drop_table("inference_processing_cycles")
    op.drop_table("inference_course_processing")
