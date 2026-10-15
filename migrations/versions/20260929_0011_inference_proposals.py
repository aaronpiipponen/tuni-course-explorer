"""inference proposals.

Revision ID: 20260929_0011
Revises: 20260929_0010
Create Date: 2026-09-29

Creates the inference-owned `inference_proposals` table. Each row is one immutable, versioned
accepted-result proposal composed from a completed validated attempt: its target/work/attempt
references are RESTRICT foreign keys, `identity_sha256` is unique and is the append-only proposal
authority, and the composed expression, equivalence and diagnostics are JSONB. Downgrade drops this
table and refuses while any proposal row exists.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260929_0011"
down_revision: str | Sequence[str] | None = "20260929_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the append-only inference-owned accepted-result proposal store."""
    op.create_table(
        "inference_proposals",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("target_course_id", sa.UUID(), nullable=False),
        sa.Column("source_work_id", sa.UUID(), nullable=False),
        sa.Column("source_attempt_id", sa.UUID(), nullable=False),
        sa.Column("proposal_version", sa.Text(), nullable=False),
        sa.Column("official_snapshot_sha256", sa.Text(), nullable=False),
        sa.Column("identity_sha256", sa.Text(), nullable=False),
        sa.Column(
            "expression",
            postgresql.JSONB(astext_type=sa.Text(), none_as_null=True),
            nullable=True,
        ),
        sa.Column(
            "equivalence",
            postgresql.JSONB(astext_type=sa.Text(), none_as_null=True),
            nullable=False,
        ),
        sa.Column(
            "dedup_diagnostics",
            postgresql.JSONB(astext_type=sa.Text(), none_as_null=True),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "btrim(proposal_version) <> ''",
            name=op.f("ck_inference_proposals_proposal_version_not_blank"),
        ),
        sa.CheckConstraint(
            "official_snapshot_sha256 ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_inference_proposals_official_snapshot_sha256_sha256"),
        ),
        sa.CheckConstraint(
            "identity_sha256 ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_inference_proposals_identity_sha256_sha256"),
        ),
        sa.ForeignKeyConstraint(
            ["target_course_id"],
            ["courses.id"],
            name=op.f("fk_inference_proposals_target_course_id_courses"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_work_id"],
            ["inference_target_work.id"],
            name=op.f("fk_inference_proposals_source_work_id_inference_target_work"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_attempt_id"],
            ["inference_model_attempts.id"],
            name=op.f("fk_inference_proposals_source_attempt_id_inference_model_attempts"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_inference_proposals")),
        sa.UniqueConstraint("identity_sha256", name="uq_inference_proposals_identity_sha256"),
    )
    op.create_index(
        "ix_inference_proposals_target_course_id",
        "inference_proposals",
        ["target_course_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    """Refuse to lose accepted proposals, else drop only this inference-owned table."""
    bind = op.get_bind()
    proposals = bind.execute(sa.text("SELECT count(*) FROM inference_proposals")).scalar_one()
    if proposals:
        raise RuntimeError(
            "cannot downgrade inference proposals: "
            f"{proposals} accepted proposal rows would be lost"
        )
    op.drop_index("ix_inference_proposals_target_course_id", table_name="inference_proposals")
    op.drop_table("inference_proposals")
