"""inferred_prerequisite_sets.

Revision ID: 20260914_0005
Revises: 20260912_0004
Create Date: 2026-09-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260914_0005"
down_revision: str | Sequence[str] | None = "20260912_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the separately derived inferred prerequisite set store."""
    op.create_table(
        "inferred_prerequisite_sets",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("target_course_id", sa.UUID(), nullable=False),
        sa.Column("activity_as_of_academic_year_start", sa.Integer(), nullable=False),
        sa.Column("activity_window_years", sa.Integer(), nullable=False),
        sa.Column(
            "coverage_state",
            sa.Enum(
                "partial",
                "complete",
                name="inferred_coverage_state",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("eligible_source_count", sa.Integer(), nullable=False),
        sa.Column("processed_source_count", sa.Integer(), nullable=False),
        sa.Column("accepted_source_count", sa.Integer(), nullable=False),
        sa.Column(
            "producer_kind",
            sa.Enum(
                "test",
                "inference",
                name="inferred_producer_kind",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("producer_name", sa.Text(), nullable=False),
        sa.Column("producer_version", sa.Text(), nullable=False),
        sa.Column("input_hash", sa.Text(), nullable=False),
        sa.Column("payload_hash", sa.Text(), nullable=False),
        sa.Column(
            "expression",
            postgresql.JSONB(astext_type=sa.Text(), none_as_null=True),
            nullable=True,
        ),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "published_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
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
            "btrim(producer_name) <> ''",
            name=op.f("ck_inferred_prerequisite_sets_producer_name_not_blank"),
        ),
        sa.CheckConstraint(
            "btrim(producer_version) <> ''",
            name=op.f("ck_inferred_prerequisite_sets_producer_version_not_blank"),
        ),
        sa.CheckConstraint(
            "activity_as_of_academic_year_start > 0",
            name=op.f("ck_inferred_prerequisite_sets_activity_year_start_positive"),
        ),
        sa.CheckConstraint(
            "activity_window_years > 0",
            name=op.f("ck_inferred_prerequisite_sets_activity_window_years_positive"),
        ),
        sa.CheckConstraint(
            "eligible_source_count >= 0",
            name=op.f("ck_inferred_prerequisite_sets_eligible_source_count_nonnegative"),
        ),
        sa.CheckConstraint(
            "processed_source_count >= 0",
            name=op.f("ck_inferred_prerequisite_sets_processed_count_nonnegative"),
        ),
        sa.CheckConstraint(
            "accepted_source_count >= 0",
            name=op.f("ck_inferred_prerequisite_sets_accepted_source_count_nonnegative"),
        ),
        sa.CheckConstraint(
            "accepted_source_count <= processed_source_count "
            "AND processed_source_count <= eligible_source_count",
            name=op.f("ck_inferred_prerequisite_sets_inferred_counts_ordered"),
        ),
        sa.CheckConstraint(
            "(coverage_state = 'partial' AND processed_source_count < eligible_source_count) "
            "OR (coverage_state = 'complete' "
            "AND processed_source_count = eligible_source_count)",
            name=op.f("ck_inferred_prerequisite_sets_coverage_state_counts_consistent"),
        ),
        sa.CheckConstraint(
            "(accepted_source_count = 0 AND expression IS NULL) "
            "OR (accepted_source_count > 0 AND expression IS NOT NULL)",
            name=op.f("ck_inferred_prerequisite_sets_expression_count_consistent"),
        ),
        sa.CheckConstraint(
            "input_hash ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_inferred_prerequisite_sets_input_hash_sha256"),
        ),
        sa.CheckConstraint(
            "payload_hash ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_inferred_prerequisite_sets_payload_hash_sha256"),
        ),
        sa.ForeignKeyConstraint(
            ["target_course_id"],
            ["courses.id"],
            name=op.f("fk_inferred_prerequisite_sets_target_course_id_courses"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_inferred_prerequisite_sets")),
        sa.UniqueConstraint(
            "target_course_id",
            name="uq_inferred_prerequisite_sets_target_course_id",
        ),
    )


def downgrade() -> None:
    """Drop the inferred prerequisite set table."""
    op.drop_table("inferred_prerequisite_sets")
