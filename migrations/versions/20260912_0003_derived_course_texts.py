"""derived_course_texts.

Revision ID: 20260912_0003
Revises: 20260911_0002
Create Date: 2026-09-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260912_0003"
down_revision: str | Sequence[str] | None = "20260911_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the separate derived teaching-text store with provenance constraints."""
    op.create_table(
        "derived_course_texts",
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
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "source_language",
            sa.Enum(
                "fi",
                "en",
                name="derived_source_language",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("source_text_hash", sa.Text(), nullable=False),
        sa.Column(
            "translation_method",
            sa.Enum(
                "manual",
                "model",
                name="translation_method",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("translation_model", sa.Text(), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
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
            "btrim(source_text_hash) <> ''",
            name=op.f("ck_derived_course_texts_source_text_hash_not_blank"),
        ),
        sa.CheckConstraint(
            "btrim(text) <> ''", name=op.f("ck_derived_course_texts_text_not_blank")
        ),
        sa.CheckConstraint(
            "source_text_hash ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_derived_course_texts_source_text_hash_sha256"),
        ),
        sa.CheckConstraint(
            "source_language <> language",
            name=op.f("ck_derived_course_texts_source_and_target_languages_differ"),
        ),
        sa.CheckConstraint(
            "(translation_method = 'manual' AND translation_model IS NULL) OR "
            "(translation_method = 'model' AND translation_model IS NOT NULL "
            "AND btrim(translation_model) <> '')",
            name=op.f("ck_derived_course_texts_method_model_consistent"),
        ),
        sa.ForeignKeyConstraint(
            ["course_version_id"],
            ["course_versions.id"],
            name=op.f("fk_derived_course_texts_course_version_id_course_versions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_derived_course_texts")),
        sa.UniqueConstraint(
            "course_version_id",
            "field",
            "language",
            name="uq_derived_course_texts_version_field_language",
        ),
    )


def downgrade() -> None:
    """Drop the derived teaching-text store."""
    op.drop_table("derived_course_texts")
