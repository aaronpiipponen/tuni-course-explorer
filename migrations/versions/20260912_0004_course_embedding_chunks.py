"""course_embedding_chunks.

Revision ID: 20260912_0004
Revises: 20260912_0003
Create Date: 2026-09-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "20260912_0004"
down_revision: str | Sequence[str] | None = "20260912_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the durable provenance-marked teaching-text chunk vector table."""
    op.create_table(
        "course_embedding_chunks",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("course_version_id", sa.UUID(), nullable=False),
        sa.Column(
            "field",
            sa.Enum(
                "name",
                "content",
                "outcomes",
                name="teaching_text_field",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column(
            "language",
            sa.Enum(
                "fi",
                "en",
                name="derived_target_language",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column(
            "text_origin",
            sa.Enum(
                "official",
                "derived",
                name="teaching_text_origin",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("representative_source_hash", sa.Text(), nullable=False),
        sa.Column("effective_text_hash", sa.Text(), nullable=False),
        sa.Column("source_text_hash", sa.Text(), nullable=False),
        sa.Column("chunk_text_hash", sa.Text(), nullable=False),
        sa.Column("embedding_model", sa.Text(), nullable=False),
        sa.Column("embedding_artifact_sha256", sa.Text(), nullable=False),
        sa.Column("embedding_configuration_hash", sa.Text(), nullable=False),
        sa.Column(
            "translation_method",
            sa.Enum(
                "manual",
                "model",
                name="translation_method",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=True,
        ),
        sa.Column("translation_model", sa.Text(), nullable=True),
        sa.Column("translation_generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "completed",
                "failed",
                name="course_embedding_status",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("embedding", Vector(1024), nullable=True),
        sa.Column("attempt_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("last_attempted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
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
            "btrim(text) <> ''",
            name=op.f("ck_course_embedding_chunks_text_not_blank"),
        ),
        sa.CheckConstraint(
            "btrim(embedding_model) <> ''",
            name=op.f("ck_course_embedding_chunks_embedding_model_not_blank"),
        ),
        sa.CheckConstraint(
            "representative_source_hash ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_course_embedding_chunks_representative_source_hash_sha256"),
        ),
        sa.CheckConstraint(
            "effective_text_hash ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_course_embedding_chunks_effective_text_hash_sha256"),
        ),
        sa.CheckConstraint(
            "source_text_hash ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_course_embedding_chunks_source_text_hash_sha256"),
        ),
        sa.CheckConstraint(
            "chunk_text_hash ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_course_embedding_chunks_chunk_text_hash_sha256"),
        ),
        sa.CheckConstraint(
            "embedding_artifact_sha256 ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_course_embedding_chunks_embedding_artifact_sha256_sha256"),
        ),
        sa.CheckConstraint(
            "embedding_configuration_hash ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_course_embedding_chunks_embedding_configuration_hash_sha256"),
        ),
        sa.CheckConstraint(
            "chunk_index >= 0",
            name=op.f("ck_course_embedding_chunks_chunk_index_nonnegative"),
        ),
        sa.CheckConstraint(
            "attempt_count >= 0",
            name=op.f("ck_course_embedding_chunks_attempt_count_nonnegative"),
        ),
        sa.CheckConstraint(
            "(text_origin = 'official' AND effective_text_hash = source_text_hash "
            "AND translation_method IS NULL AND translation_model IS NULL "
            "AND translation_generated_at IS NULL) "
            "OR (text_origin = 'derived' AND translation_method IS NOT NULL "
            "AND translation_generated_at IS NOT NULL "
            "AND ((translation_method = 'manual' AND translation_model IS NULL) "
            "OR (translation_method = 'model' AND translation_model IS NOT NULL "
            "AND btrim(translation_model) <> '')))",
            name=op.f("ck_course_embedding_chunks_origin_provenance_consistent"),
        ),
        sa.CheckConstraint(
            "(status = 'pending' AND embedding IS NULL AND last_error IS NULL) "
            "OR (status = 'completed' AND embedding IS NOT NULL AND last_error IS NULL) "
            "OR (status = 'failed' AND embedding IS NULL AND last_error IS NOT NULL "
            "AND btrim(last_error) <> '')",
            name=op.f("ck_course_embedding_chunks_lifecycle_consistent"),
        ),
        sa.ForeignKeyConstraint(
            ["course_version_id"],
            ["course_versions.id"],
            name=op.f("fk_course_embedding_chunks_course_version_id_course_versions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_course_embedding_chunks")),
        sa.UniqueConstraint(
            "course_version_id",
            "field",
            "language",
            "chunk_index",
            name="uq_course_embedding_chunks_version_field_language_index",
        ),
    )


def downgrade() -> None:
    """Drop the course embedding chunk table."""
    op.drop_table("course_embedding_chunks")
