"""Create the packed exact semantic search relation and drop the centroid hub digest.

Revision ID: 20261028_0022
Revises: 20261028_0021

The three tables hold the packed exact semantic search relation of one dataset build: one row per
canonical course representative group, one row per 128-vector block, and the one-row build meta.
The scan extension is installed before the tables so the function exists before the search read
uses it. The rows are derived data that the serving-artifact build replaces.

The revision also drops the hub digest of the derived centroid rows. Its values cannot be
reconstructed, so the downgrade restores the column as nullable with the same format check.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY

revision: str = "20261028_0022"
down_revision: str | Sequence[str] | None = "20261028_0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Install the scan extension, create the packed search tables and drop the hub digest."""
    op.execute("CREATE EXTENSION IF NOT EXISTS course_embedding_search")
    op.create_table(
        "course_embedding_search_groups",
        sa.Column("group_no", sa.Integer(), nullable=False),
        sa.Column("group_id", sa.Text(), nullable=False),
        sa.Column("sisu_course_unit_id", sa.Text(), nullable=False),
        sa.Column("representative_source_hash", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("group_no", name="pk_course_embedding_search_groups"),
        sa.UniqueConstraint(
            "group_id",
            "sisu_course_unit_id",
            "representative_source_hash",
            name="uq_course_embedding_search_groups_identity",
        ),
    )
    op.create_table(
        "course_embedding_search_blocks",
        sa.Column("block_no", sa.Integer(), nullable=False),
        sa.Column("n", sa.Integer(), nullable=False),
        sa.Column("groups", ARRAY(sa.Integer()), nullable=False),
        sa.Column("norms", ARRAY(sa.Double()), nullable=False),
        sa.Column("vectors", sa.LargeBinary(), nullable=False),
        sa.CheckConstraint("n > 0 AND n <= 128", name="ck_course_embedding_search_blocks_n_range"),
        sa.PrimaryKeyConstraint("block_no", name="pk_course_embedding_search_blocks"),
    )
    op.execute(
        "ALTER TABLE course_embedding_search_blocks ALTER COLUMN vectors SET STORAGE EXTERNAL"
    )
    op.create_table(
        "course_embedding_search_meta",
        sa.Column("one_row", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("group_count", sa.Integer(), nullable=False),
        sa.CheckConstraint("one_row", name="ck_course_embedding_search_meta_one_row"),
        sa.CheckConstraint(
            "group_count > 0", name="ck_course_embedding_search_meta_group_count_positive"
        ),
        sa.PrimaryKeyConstraint("one_row", name="pk_course_embedding_search_meta"),
    )
    op.drop_constraint(
        "ck_course_embedding_centroids_hub_sha256_sha256",
        "course_embedding_centroids",
        type_="check",
    )
    op.drop_column("course_embedding_centroids", "hub_sha256")


def downgrade() -> None:
    """Restore the centroid hub digest, then drop the packed search tables and the extension."""
    op.add_column(
        "course_embedding_centroids",
        sa.Column("hub_sha256", sa.Text(), nullable=True),
    )
    op.create_check_constraint(
        "ck_course_embedding_centroids_hub_sha256_sha256",
        "course_embedding_centroids",
        "hub_sha256 ~ '^[0-9a-f]{64}$'",
    )
    op.drop_table("course_embedding_search_meta")
    op.drop_table("course_embedding_search_blocks")
    op.drop_table("course_embedding_search_groups")
    op.execute("DROP EXTENSION IF EXISTS course_embedding_search")
