"""Create the derived course embedding centroid table.

Revision ID: 20261027_0020
Revises: 20261025_0019

Adds the per-represented-course hub-centred unit centroid used to apply the recommendation
relatedness floor before candidate summaries and chunks are read. The centroid is a little-endian
float64 array of 1024 components. The table holds derived data, and the serving artifact build
replaces every row.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261027_0020"
down_revision: str | Sequence[str] | None = "20261025_0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CENTROID_BYTES = 1024 * 8


def upgrade() -> None:
    """Create the derived centroid table."""
    op.create_table(
        "course_embedding_centroids",
        sa.Column("group_id", sa.Text(), nullable=False),
        sa.Column("sisu_course_unit_id", sa.Text(), nullable=False),
        sa.Column("representative_source_hash", sa.Text(), nullable=False),
        sa.Column("embedding_configuration_hash", sa.Text(), nullable=False),
        sa.Column("hub_sha256", sa.Text(), nullable=False),
        sa.Column("chunk_count", sa.Integer(), nullable=False),
        sa.Column("centroid", sa.LargeBinary(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            f"octet_length(centroid) = {_CENTROID_BYTES}",
            name="ck_course_embedding_centroids_centroid_length",
        ),
        sa.CheckConstraint(
            "chunk_count > 0",
            name="ck_course_embedding_centroids_chunk_count_positive",
        ),
        sa.CheckConstraint(
            "btrim(sisu_course_unit_id) <> ''",
            name="ck_course_embedding_centroids_sisu_course_unit_id_not_blank",
        ),
        sa.CheckConstraint(
            "representative_source_hash ~ '^[0-9a-f]{64}$'",
            name="ck_course_embedding_centroids_representative_source_hash_sha256",
        ),
        sa.CheckConstraint(
            "embedding_configuration_hash ~ '^[0-9a-f]{64}$'",
            name="ck_course_embedding_centroids_embedding_configuration_hash_sha256",
        ),
        sa.CheckConstraint(
            "hub_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_course_embedding_centroids_hub_sha256_sha256",
        ),
        sa.ForeignKeyConstraint(
            ["group_id"],
            ["courses.group_id"],
            name="fk_course_embedding_centroids_group_id_courses",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("group_id", name="pk_course_embedding_centroids"),
    )


def downgrade() -> None:
    """Drop the derived centroid table."""
    op.drop_table("course_embedding_centroids")
