"""curriculum_schema.

Revision ID: 20260910_0001
Revises:
Create Date: 2026-09-10 12:01:07.394476
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260910_0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "courses",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("group_id", sa.Text(), nullable=False),
        sa.Column("first_listed_academic_year_start", sa.Integer(), nullable=True),
        sa.Column("last_listed_academic_year_start", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
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
        sa.CheckConstraint("btrim(group_id) <> ''", name=op.f("ck_courses_group_id_not_blank")),
        sa.CheckConstraint(
            "activity_as_of_academic_year_start > 0",
            name=op.f("ck_courses_activity_as_of_academic_year_start_positive"),
        ),
        sa.CheckConstraint(
            "activity_window_years > 0", name=op.f("ck_courses_activity_window_years_positive")
        ),
        sa.CheckConstraint(
            "first_listed_academic_year_start IS NULL OR last_listed_academic_year_start IS NULL OR first_listed_academic_year_start <= last_listed_academic_year_start",
            name=op.f("ck_courses_listed_years_ordered"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_courses")),
        sa.UniqueConstraint("group_id", name=op.f("uq_courses_group_id")),
    )
    op.create_table(
        "curriculum_periods",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("academic_year_start", sa.Integer(), nullable=False),
        sa.CheckConstraint("btrim(id) <> ''", name=op.f("ck_curriculum_periods_id_not_blank")),
        sa.CheckConstraint(
            "academic_year_start > 0",
            name=op.f("ck_curriculum_periods_academic_year_start_positive"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_curriculum_periods")),
    )
    op.create_table(
        "ingestion_runs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "running",
                "completed",
                "failed",
                name="ingestion_run_status",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("raw_root_path", sa.Text(), nullable=False),
        sa.Column("manifest_path", sa.Text(), nullable=False),
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
            "btrim(manifest_path) <> ''", name=op.f("ck_ingestion_runs_manifest_path_not_blank")
        ),
        sa.CheckConstraint(
            "btrim(raw_root_path) <> ''", name=op.f("ck_ingestion_runs_raw_root_path_not_blank")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ingestion_runs")),
    )
    op.create_table(
        "modules",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("group_id", sa.Text(), nullable=False),
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
        sa.CheckConstraint("btrim(group_id) <> ''", name=op.f("ck_modules_group_id_not_blank")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_modules")),
        sa.UniqueConstraint("group_id", name=op.f("uq_modules_group_id")),
    )
    op.create_table(
        "source_snapshots",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("ingestion_run_id", sa.UUID(), nullable=False),
        sa.Column(
            "object_type",
            sa.Enum(
                "course_unit",
                "module",
                name="source_object_type",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("source_object_id", sa.Text(), nullable=False),
        sa.Column("source_group_id", sa.Text(), nullable=True),
        sa.Column("response_path", sa.Text(), nullable=False),
        sa.Column("response_item_index", sa.Integer(), nullable=False),
        sa.Column("source_hash", sa.Text(), nullable=False),
        sa.Column(
            "captured_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "btrim(response_path) <> ''", name=op.f("ck_source_snapshots_response_path_not_blank")
        ),
        sa.CheckConstraint(
            "btrim(source_hash) <> ''", name=op.f("ck_source_snapshots_source_hash_not_blank")
        ),
        sa.CheckConstraint(
            "btrim(source_object_id) <> ''",
            name=op.f("ck_source_snapshots_source_object_id_not_blank"),
        ),
        sa.CheckConstraint(
            "response_item_index >= 0",
            name=op.f("ck_source_snapshots_response_item_index_nonnegative"),
        ),
        sa.ForeignKeyConstraint(
            ["ingestion_run_id"],
            ["ingestion_runs.id"],
            name=op.f("fk_source_snapshots_ingestion_run_id_ingestion_runs"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_source_snapshots")),
        sa.UniqueConstraint(
            "ingestion_run_id",
            "response_path",
            "response_item_index",
            name="uq_source_snapshots_response_position",
        ),
    )
    op.create_index(
        op.f("ix_source_snapshots_object_type"),
        "source_snapshots",
        ["object_type", "source_object_id"],
        unique=False,
    )
    op.create_table(
        "course_versions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("course_id", sa.UUID(), nullable=False),
        sa.Column("sisu_course_unit_id", sa.Text(), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name_fi", sa.Text(), nullable=True),
        sa.Column("name_en", sa.Text(), nullable=True),
        sa.Column("credits_min", sa.Numeric(precision=6, scale=2), nullable=False),
        sa.Column("credits_max", sa.Numeric(precision=6, scale=2), nullable=False),
        sa.Column("official_url", sa.Text(), nullable=False),
        sa.Column("document_state", sa.Text(), nullable=False),
        sa.Column("validity_start", sa.Date(), nullable=True),
        sa.Column("validity_end", sa.Date(), nullable=True),
        sa.Column("source_revision", sa.Integer(), nullable=True),
        sa.Column("source_modification_ordinal", sa.BigInteger(), nullable=True),
        sa.Column("source_snapshot_id", sa.UUID(), nullable=False),
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
        sa.CheckConstraint("btrim(code) <> ''", name=op.f("ck_course_versions_code_not_blank")),
        sa.CheckConstraint(
            "btrim(document_state) <> ''", name=op.f("ck_course_versions_document_state_not_blank")
        ),
        sa.CheckConstraint(
            "btrim(official_url) <> ''", name=op.f("ck_course_versions_official_url_not_blank")
        ),
        sa.CheckConstraint(
            "btrim(sisu_course_unit_id) <> ''",
            name=op.f("ck_course_versions_sisu_course_unit_id_not_blank"),
        ),
        sa.CheckConstraint(
            "credits_min >= 0 AND credits_max >= 0",
            name=op.f("ck_course_versions_credits_nonnegative"),
        ),
        sa.CheckConstraint(
            "credits_min <= credits_max", name=op.f("ck_course_versions_credits_ordered")
        ),
        sa.CheckConstraint(
            "source_modification_ordinal IS NULL OR source_modification_ordinal >= 0",
            name=op.f("ck_course_versions_source_modification_ordinal_nonnegative"),
        ),
        sa.CheckConstraint(
            "source_revision IS NULL OR source_revision >= 0",
            name=op.f("ck_course_versions_source_revision_nonnegative"),
        ),
        sa.CheckConstraint(
            "validity_start IS NULL OR validity_end IS NULL OR validity_start <= validity_end",
            name=op.f("ck_course_versions_validity_dates_ordered"),
        ),
        sa.ForeignKeyConstraint(
            ["course_id"],
            ["courses.id"],
            name=op.f("fk_course_versions_course_id_courses"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_snapshot_id"],
            ["source_snapshots.id"],
            name=op.f("fk_course_versions_source_snapshot_id_source_snapshots"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_course_versions")),
        sa.UniqueConstraint(
            "sisu_course_unit_id", name=op.f("uq_course_versions_sisu_course_unit_id")
        ),
        sa.UniqueConstraint(
            "source_snapshot_id", name=op.f("uq_course_versions_source_snapshot_id")
        ),
    )
    op.create_table(
        "module_versions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("module_id", sa.UUID(), nullable=False),
        sa.Column("sisu_module_id", sa.Text(), nullable=False),
        sa.Column(
            "module_type",
            sa.Enum(
                "DegreeProgramme",
                "StudyModule",
                "GroupingModule",
                name="module_type",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("code", sa.Text(), nullable=True),
        sa.Column("name_fi", sa.Text(), nullable=True),
        sa.Column("name_en", sa.Text(), nullable=True),
        sa.Column("target_credits_min", sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column("target_credits_max", sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column("document_state", sa.Text(), nullable=False),
        sa.Column("validity_start", sa.Date(), nullable=True),
        sa.Column("validity_end", sa.Date(), nullable=True),
        sa.Column("source_revision", sa.Integer(), nullable=True),
        sa.Column("source_modification_ordinal", sa.BigInteger(), nullable=True),
        sa.Column("source_snapshot_id", sa.UUID(), nullable=False),
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
            "btrim(document_state) <> ''", name=op.f("ck_module_versions_document_state_not_blank")
        ),
        sa.CheckConstraint(
            "btrim(sisu_module_id) <> ''", name=op.f("ck_module_versions_sisu_module_id_not_blank")
        ),
        sa.CheckConstraint(
            "source_modification_ordinal IS NULL OR source_modification_ordinal >= 0",
            name=op.f("ck_module_versions_source_modification_ordinal_nonnegative"),
        ),
        sa.CheckConstraint(
            "source_revision IS NULL OR source_revision >= 0",
            name=op.f("ck_module_versions_source_revision_nonnegative"),
        ),
        sa.CheckConstraint(
            "(target_credits_min IS NULL OR target_credits_min >= 0) AND (target_credits_max IS NULL OR target_credits_max >= 0)",
            name=op.f("ck_module_versions_target_credits_nonnegative"),
        ),
        sa.CheckConstraint(
            "target_credits_min IS NULL OR target_credits_max IS NULL OR target_credits_min <= target_credits_max",
            name=op.f("ck_module_versions_target_credits_ordered"),
        ),
        sa.CheckConstraint(
            "validity_start IS NULL OR validity_end IS NULL OR validity_start <= validity_end",
            name=op.f("ck_module_versions_validity_dates_ordered"),
        ),
        sa.ForeignKeyConstraint(
            ["module_id"],
            ["modules.id"],
            name=op.f("fk_module_versions_module_id_modules"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_snapshot_id"],
            ["source_snapshots.id"],
            name=op.f("fk_module_versions_source_snapshot_id_source_snapshots"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_module_versions")),
        sa.UniqueConstraint("sisu_module_id", name=op.f("uq_module_versions_sisu_module_id")),
        sa.UniqueConstraint(
            "source_snapshot_id", name=op.f("uq_module_versions_source_snapshot_id")
        ),
    )
    op.create_table(
        "course_texts",
        sa.Column("course_version_id", sa.UUID(), nullable=False),
        sa.Column("content_fi", sa.Text(), nullable=True),
        sa.Column("content_en", sa.Text(), nullable=True),
        sa.Column("outcomes_fi", sa.Text(), nullable=True),
        sa.Column("outcomes_en", sa.Text(), nullable=True),
        sa.Column("prerequisite_text_fi", sa.Text(), nullable=True),
        sa.Column("prerequisite_text_en", sa.Text(), nullable=True),
        sa.Column("additional_info_fi", sa.Text(), nullable=True),
        sa.Column("additional_info_en", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["course_version_id"],
            ["course_versions.id"],
            name=op.f("fk_course_texts_course_version_id_course_versions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("course_version_id", name=op.f("pk_course_texts")),
    )
    op.create_table(
        "course_version_curriculum_periods",
        sa.Column("course_version_id", sa.UUID(), nullable=False),
        sa.Column("curriculum_period_id", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["course_version_id"],
            ["course_versions.id"],
            name=op.f("fk_course_version_curriculum_periods_course_version_id_course_versions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["curriculum_period_id"],
            ["curriculum_periods.id"],
            name=op.f(
                "fk_course_version_curriculum_periods_curriculum_period_id_curriculum_periods"
            ),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "course_version_id",
            "curriculum_period_id",
            name=op.f("pk_course_version_curriculum_periods"),
        ),
    )
    op.create_table(
        "module_rule_nodes",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("module_version_id", sa.UUID(), nullable=False),
        sa.Column("parent_node_id", sa.UUID(), nullable=True),
        sa.Column("sibling_position", sa.Integer(), nullable=False),
        sa.Column("local_id", sa.Text(), nullable=True),
        sa.Column(
            "node_type",
            sa.Enum(
                "CompositeRule",
                "CreditsRule",
                "CourseUnitCountRule",
                "CourseUnitRule",
                "ModuleRule",
                "AnyCourseUnitRule",
                "AnyModuleRule",
                name="module_rule_type",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("require_min", sa.Integer(), nullable=True),
        sa.Column("require_max", sa.Integer(), nullable=True),
        sa.Column("all_mandatory", sa.Boolean(), nullable=True),
        sa.Column("description", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("credits_min", sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column("credits_max", sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column("count_min", sa.Integer(), nullable=True),
        sa.Column("count_max", sa.Integer(), nullable=True),
        sa.Column("referenced_group_id", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "(node_type IN ('CourseUnitRule', 'ModuleRule') AND referenced_group_id IS NOT NULL) OR (node_type NOT IN ('CourseUnitRule', 'ModuleRule') AND referenced_group_id IS NULL)",
            name=op.f("ck_module_rule_nodes_referenced_group_id_matches_node_type"),
        ),
        sa.CheckConstraint(
            "count_min IS NULL OR count_max IS NULL OR count_min <= count_max",
            name=op.f("ck_module_rule_nodes_count_bounds_ordered"),
        ),
        sa.CheckConstraint(
            "(count_min IS NULL OR count_min >= 0) AND (count_max IS NULL OR count_max >= 0)",
            name=op.f("ck_module_rule_nodes_count_bounds_nonnegative"),
        ),
        sa.CheckConstraint(
            "(credits_min IS NULL OR credits_min >= 0) AND (credits_max IS NULL OR credits_max >= 0)",
            name=op.f("ck_module_rule_nodes_credit_bounds_nonnegative"),
        ),
        sa.CheckConstraint(
            "credits_min IS NULL OR credits_max IS NULL OR credits_min <= credits_max",
            name=op.f("ck_module_rule_nodes_credit_bounds_ordered"),
        ),
        sa.CheckConstraint(
            "require_min IS NULL OR require_max IS NULL OR require_min <= require_max",
            name=op.f("ck_module_rule_nodes_require_bounds_ordered"),
        ),
        sa.CheckConstraint(
            "(require_min IS NULL OR require_min >= 0) AND (require_max IS NULL OR require_max >= 0)",
            name=op.f("ck_module_rule_nodes_require_bounds_nonnegative"),
        ),
        sa.CheckConstraint(
            "sibling_position >= 0", name=op.f("ck_module_rule_nodes_sibling_position_nonnegative")
        ),
        sa.ForeignKeyConstraint(
            ["module_version_id"],
            ["module_versions.id"],
            name=op.f("fk_module_rule_nodes_module_version_id_module_versions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["parent_node_id", "module_version_id"],
            ["module_rule_nodes.id", "module_rule_nodes.module_version_id"],
            name="fk_module_rule_nodes_parent_same_module",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_module_rule_nodes")),
        sa.UniqueConstraint(
            "id", "module_version_id", name="uq_module_rule_nodes_id_module_version_id"
        ),
        sa.UniqueConstraint(
            "parent_node_id",
            "sibling_position",
            name="uq_module_rule_nodes_parent_sibling_position",
        ),
    )
    op.create_index(
        "uq_module_rule_nodes_root",
        "module_rule_nodes",
        ["module_version_id"],
        unique=True,
        postgresql_where=sa.text("parent_node_id IS NULL"),
    )
    op.create_table(
        "module_version_curriculum_periods",
        sa.Column("module_version_id", sa.UUID(), nullable=False),
        sa.Column("curriculum_period_id", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["curriculum_period_id"],
            ["curriculum_periods.id"],
            name=op.f(
                "fk_module_version_curriculum_periods_curriculum_period_id_curriculum_periods"
            ),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["module_version_id"],
            ["module_versions.id"],
            name=op.f("fk_module_version_curriculum_periods_module_version_id_module_versions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "module_version_id",
            "curriculum_period_id",
            name=op.f("pk_module_version_curriculum_periods"),
        ),
    )
    op.create_table(
        "official_prerequisite_options",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("target_course_version_id", sa.UUID(), nullable=False),
        sa.Column("option_index", sa.Integer(), nullable=False),
        sa.Column(
            "requirement_kind",
            sa.Enum(
                "compulsory",
                "recommended",
                name="prerequisite_requirement_kind",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.CheckConstraint(
            "option_index >= 0",
            name=op.f("ck_official_prerequisite_options_option_index_nonnegative"),
        ),
        sa.ForeignKeyConstraint(
            ["target_course_version_id"],
            ["course_versions.id"],
            name=op.f("fk_official_prerequisite_options_target_course_version_id_course_versions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_official_prerequisite_options")),
        sa.UniqueConstraint(
            "target_course_version_id",
            "requirement_kind",
            "option_index",
            name="uq_prerequisite_options_target_kind_position",
        ),
    )
    op.create_table(
        "official_substitution_options",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("source_course_version_id", sa.UUID(), nullable=False),
        sa.Column("option_index", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "option_index >= 0",
            name=op.f("ck_official_substitution_options_option_index_nonnegative"),
        ),
        sa.ForeignKeyConstraint(
            ["source_course_version_id"],
            ["course_versions.id"],
            name=op.f("fk_official_substitution_options_source_course_version_id_course_versions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_official_substitution_options")),
        sa.UniqueConstraint(
            "source_course_version_id",
            "option_index",
            name="uq_substitution_options_source_position",
        ),
    )
    op.create_table(
        "official_prerequisite_option_members",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("prerequisite_option_id", sa.UUID(), nullable=False),
        sa.Column("member_index", sa.Integer(), nullable=False),
        sa.Column(
            "member_type",
            sa.Enum(
                "course",
                "module",
                name="prerequisite_member_type",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("referenced_group_id", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "btrim(referenced_group_id) <> ''",
            name=op.f("ck_official_prerequisite_option_members_referenced_group_id_not_blank"),
        ),
        sa.CheckConstraint(
            "member_index >= 0",
            name=op.f("ck_official_prerequisite_option_members_member_index_nonnegative"),
        ),
        sa.ForeignKeyConstraint(
            ["prerequisite_option_id"],
            ["official_prerequisite_options.id"],
            name=op.f(
                "fk_official_prerequisite_option_members_prerequisite_option_id_official_prerequisite_options"
            ),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_official_prerequisite_option_members")),
        sa.UniqueConstraint(
            "prerequisite_option_id", "member_index", name="uq_prerequisite_members_option_position"
        ),
    )
    op.create_table(
        "official_substitution_option_members",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("substitution_option_id", sa.UUID(), nullable=False),
        sa.Column("member_index", sa.Integer(), nullable=False),
        sa.Column("course_group_id", sa.Text(), nullable=False),
        sa.Column("credits", sa.Numeric(precision=6, scale=2), nullable=True),
        sa.CheckConstraint(
            "btrim(course_group_id) <> ''",
            name=op.f("ck_official_substitution_option_members_course_group_id_not_blank"),
        ),
        sa.CheckConstraint(
            "credits IS NULL OR credits >= 0",
            name=op.f("ck_official_substitution_option_members_credits_nonnegative"),
        ),
        sa.CheckConstraint(
            "member_index >= 0",
            name=op.f("ck_official_substitution_option_members_member_index_nonnegative"),
        ),
        sa.ForeignKeyConstraint(
            ["substitution_option_id"],
            ["official_substitution_options.id"],
            name=op.f(
                "fk_official_substitution_option_members_substitution_option_id_official_substitution_options"
            ),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_official_substitution_option_members")),
        sa.UniqueConstraint(
            "substitution_option_id", "member_index", name="uq_substitution_members_option_position"
        ),
    )


def downgrade() -> None:
    op.drop_table("official_substitution_option_members")
    op.drop_table("official_prerequisite_option_members")
    op.drop_table("official_substitution_options")
    op.drop_table("official_prerequisite_options")
    op.drop_table("module_version_curriculum_periods")
    op.drop_index(
        "uq_module_rule_nodes_root",
        table_name="module_rule_nodes",
        postgresql_where=sa.text("parent_node_id IS NULL"),
    )
    op.drop_table("module_rule_nodes")
    op.drop_table("course_version_curriculum_periods")
    op.drop_table("course_texts")
    op.drop_table("module_versions")
    op.drop_table("course_versions")
    op.drop_index(op.f("ix_source_snapshots_object_type"), table_name="source_snapshots")
    op.drop_table("source_snapshots")
    op.drop_table("modules")
    op.drop_table("ingestion_runs")
    op.drop_table("curriculum_periods")
    op.drop_table("courses")
    op.execute("DROP EXTENSION IF EXISTS vector")
