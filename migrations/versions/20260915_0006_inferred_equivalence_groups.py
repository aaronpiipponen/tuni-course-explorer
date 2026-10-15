"""inferred_equivalence_groups.

Revision ID: 20260915_0006
Revises: 20260914_0005
Create Date: 2026-09-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260915_0006"
down_revision: str | Sequence[str] | None = "20260914_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the target-independent inferred equivalence group and member store."""
    op.create_table(
        "inferred_equivalence_groups",
        sa.Column("id", sa.UUID(), nullable=False),
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
            "inference",
            postgresql.JSONB(astext_type=sa.Text(), none_as_null=True),
            nullable=False,
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
            name=op.f("ck_inferred_equivalence_groups_producer_name_not_blank"),
        ),
        sa.CheckConstraint(
            "btrim(producer_version) <> ''",
            name=op.f("ck_inferred_equivalence_groups_producer_version_not_blank"),
        ),
        sa.CheckConstraint(
            "input_hash ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_inferred_equivalence_groups_input_hash_sha256"),
        ),
        sa.CheckConstraint(
            "payload_hash ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_inferred_equivalence_groups_payload_hash_sha256"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_inferred_equivalence_groups")),
    )
    op.create_table(
        "inferred_equivalence_group_members",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("equivalence_group_id", sa.UUID(), nullable=False),
        sa.Column("course_id", sa.UUID(), nullable=False),
        sa.Column("activity_as_of_academic_year_start", sa.Integer(), nullable=False),
        sa.Column("activity_window_years", sa.Integer(), nullable=False),
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
            name=op.f("ck_inferred_equivalence_group_members_activity_year_start_positive"),
        ),
        sa.CheckConstraint(
            "activity_window_years > 0",
            name=op.f("ck_inferred_equivalence_group_members_activity_window_years_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["equivalence_group_id"],
            ["inferred_equivalence_groups.id"],
            name=op.f(
                "fk_inferred_equivalence_group_members_equivalence_group_id_"
                "inferred_equivalence_groups"
            ),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["course_id"],
            ["courses.id"],
            name=op.f("fk_inferred_equivalence_group_members_course_id_courses"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_inferred_equivalence_group_members")),
        sa.UniqueConstraint(
            "equivalence_group_id",
            "course_id",
            name="uq_inferred_equivalence_group_members_group_course",
        ),
    )


def downgrade() -> None:
    """Drop the inferred equivalence group tables."""
    op.drop_table("inferred_equivalence_group_members")
    op.drop_table("inferred_equivalence_groups")
