"""Migration-owned ORM metadata for official and separately derived curriculum storage.

Official source tables carry university-authored curriculum facts. This module also
declares explicitly derived storage: machine or manual teaching-text translations with their own
provenance (never merged into an official text column), final inferred prerequisite expression
sets that record their producer, activity context, and coverage as separately derived claims,
global inferred equivalence groups whose normalized membership and group-level producer/evidence
provenance are target-independent inferred artifacts, and raw inference pipeline-run, target-work,
append-only model-attempt, and immutable result proposal evidence. Raw inference evidence
and composed proposals are separately derived and never official or product-visible: they record
untrusted model output, validation outcomes, and the composition only, and none of these
derived rows are ever written into or presented as official requirements.
"""

import uuid
from datetime import date, datetime
from enum import StrEnum

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    MetaData,
    Numeric,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy import (
    Enum as SQLAlchemyEnum,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from course_explorer.constants import COURSE_EMBEDDING_DIMENSION
from course_explorer.enums import (
    CourseEmbeddingStatus,
    InferenceWorkStatus,
    InferredCoverageState,
    InferredProducerKind,
    IngestionRunStatus,
    ModuleRuleType,
    ModuleType,
    PrerequisiteMemberType,
    PrerequisiteRequirementKind,
    SourceObjectType,
    TeachingTextField,
    TeachingTextLanguage,
    TeachingTextOrigin,
    TranslationMethod,
)

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Declarative root carrying deterministic migration naming conventions."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def _enum(enum_type: type[StrEnum], name: str) -> SQLAlchemyEnum:
    """Create a portable enum that stores declared values as check constraints."""
    return SQLAlchemyEnum(
        enum_type,
        name=name,
        native_enum=False,
        create_constraint=True,
        values_callable=lambda members: [member.value for member in members],
    )


def _not_blank(column_name: str) -> CheckConstraint:
    """Create the standard non-empty text check for a required source field."""
    return CheckConstraint(f"btrim({column_name}) <> ''", name=f"{column_name}_not_blank")


class IngestionRun(Base):
    """Database provenance for one immutable raw-source capture run."""

    __tablename__ = "ingestion_runs"
    __table_args__ = (_not_blank("raw_root_path"), _not_blank("manifest_path"))

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    status: Mapped[IngestionRunStatus] = mapped_column(
        _enum(IngestionRunStatus, "ingestion_run_status")
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    raw_root_path: Mapped[str] = mapped_column(Text)
    manifest_path: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SourceSnapshot(Base):
    """Immutable position and hash provenance for one captured source object."""

    __tablename__ = "source_snapshots"
    __table_args__ = (
        _not_blank("source_object_id"),
        _not_blank("response_path"),
        _not_blank("source_hash"),
        CheckConstraint("response_item_index >= 0", name="response_item_index_nonnegative"),
        UniqueConstraint(
            "ingestion_run_id",
            "response_path",
            "response_item_index",
            name="uq_source_snapshots_response_position",
        ),
        Index(None, "object_type", "source_object_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ingestion_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ingestion_runs.id", ondelete="RESTRICT")
    )
    object_type: Mapped[SourceObjectType] = mapped_column(
        _enum(SourceObjectType, "source_object_type")
    )
    source_object_id: Mapped[str] = mapped_column(Text)
    source_group_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_path: Mapped[str] = mapped_column(Text)
    response_item_index: Mapped[int] = mapped_column(Integer)
    source_hash: Mapped[str] = mapped_column(Text)


class CurriculumPeriod(Base):
    """An academic period identity supplied by the official curriculum source."""

    __tablename__ = "curriculum_periods"
    __table_args__ = (
        _not_blank("id"),
        CheckConstraint("academic_year_start > 0", name="academic_year_start_positive"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    academic_year_start: Mapped[int] = mapped_column(Integer)


class Course(Base):
    """Canonical course identity shared by all exact source versions."""

    __tablename__ = "courses"
    __table_args__ = (
        _not_blank("group_id"),
        CheckConstraint(
            "first_listed_academic_year_start IS NULL OR last_listed_academic_year_start IS NULL "
            "OR first_listed_academic_year_start <= last_listed_academic_year_start",
            name="listed_years_ordered",
        ),
        CheckConstraint(
            "activity_as_of_academic_year_start > 0",
            name="activity_as_of_academic_year_start_positive",
        ),
        CheckConstraint("activity_window_years > 0", name="activity_window_years_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    group_id: Mapped[str] = mapped_column(Text, unique=True)
    first_listed_academic_year_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_listed_academic_year_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean)
    activity_as_of_academic_year_start: Mapped[int] = mapped_column(Integer)
    activity_window_years: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CourseVersion(Base):
    """One exact Kori course-unit version linked to canonical course identity."""

    __tablename__ = "course_versions"
    __table_args__ = (
        _not_blank("sisu_course_unit_id"),
        _not_blank("code"),
        _not_blank("official_url"),
        _not_blank("document_state"),
        CheckConstraint("credits_min >= 0 AND credits_max >= 0", name="credits_nonnegative"),
        CheckConstraint("credits_min <= credits_max", name="credits_ordered"),
        CheckConstraint(
            "validity_start IS NULL OR validity_end IS NULL OR validity_start <= validity_end",
            name="validity_dates_ordered",
        ),
        CheckConstraint(
            "source_revision IS NULL OR source_revision >= 0", name="source_revision_nonnegative"
        ),
        CheckConstraint(
            "source_modification_ordinal IS NULL OR source_modification_ordinal >= 0",
            name="source_modification_ordinal_nonnegative",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courses.id", ondelete="RESTRICT")
    )
    sisu_course_unit_id: Mapped[str] = mapped_column(Text, unique=True)
    code: Mapped[str] = mapped_column(Text)
    name_fi: Mapped[str | None] = mapped_column(Text, nullable=True)
    name_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    credits_min: Mapped[float] = mapped_column(Numeric(6, 2))
    credits_max: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    official_url: Mapped[str] = mapped_column(Text)
    document_state: Mapped[str] = mapped_column(Text)
    validity_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    validity_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    source_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_modification_ordinal: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    source_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("source_snapshots.id", ondelete="RESTRICT"), unique=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CourseVersionCurriculumPeriod(Base):
    """Membership of an exact course version in an official academic period."""

    __tablename__ = "course_version_curriculum_periods"

    course_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("course_versions.id", ondelete="CASCADE"), primary_key=True
    )
    curriculum_period_id: Mapped[str] = mapped_column(
        Text, ForeignKey("curriculum_periods.id", ondelete="RESTRICT"), primary_key=True
    )


class CourseText(Base):
    """Localized source text attached to one exact course version."""

    __tablename__ = "course_texts"

    course_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("course_versions.id", ondelete="CASCADE"), primary_key=True
    )
    content_fi: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    outcomes_fi: Mapped[str | None] = mapped_column(Text, nullable=True)
    outcomes_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    prerequisite_text_fi: Mapped[str | None] = mapped_column(Text, nullable=True)
    prerequisite_text_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    additional_info_fi: Mapped[str | None] = mapped_column(Text, nullable=True)
    additional_info_en: Mapped[str | None] = mapped_column(Text, nullable=True)


class DerivedCourseText(Base):
    """Explicitly derived translation of one teaching-text field for an exact course version.

    Rows record their own provenance and never write into `course_versions` names or
    `course_texts`. Official and derived text are never merged into one field.
    """

    __tablename__ = "derived_course_texts"
    __table_args__ = (
        _not_blank("text"),
        _not_blank("source_text_hash"),
        CheckConstraint("source_language <> language", name="source_and_target_languages_differ"),
        CheckConstraint("source_text_hash ~ '^[0-9a-f]{64}$'", name="source_text_hash_sha256"),
        CheckConstraint(
            "(translation_method = 'manual' AND translation_model IS NULL) "
            "OR (translation_method = 'model' AND translation_model IS NOT NULL "
            "AND btrim(translation_model) <> '')",
            name="method_model_consistent",
        ),
        UniqueConstraint(
            "course_version_id",
            "field",
            "language",
            name="uq_derived_course_texts_version_field_language",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    course_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("course_versions.id", ondelete="CASCADE")
    )
    field: Mapped[TeachingTextField] = mapped_column(
        _enum(TeachingTextField, "teaching_text_field")
    )
    language: Mapped[TeachingTextLanguage] = mapped_column(
        _enum(TeachingTextLanguage, "derived_target_language")
    )
    text: Mapped[str] = mapped_column(Text)
    source_language: Mapped[TeachingTextLanguage] = mapped_column(
        _enum(TeachingTextLanguage, "derived_source_language")
    )
    source_text_hash: Mapped[str] = mapped_column(Text)
    translation_method: Mapped[TranslationMethod] = mapped_column(
        _enum(TranslationMethod, "translation_method")
    )
    translation_model: Mapped[str | None] = mapped_column(Text, nullable=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CourseEmbeddingChunk(Base):
    """One provenance-marked teaching-text chunk embedded for a selected representative.

    Rows reference the exact representative `course_versions` row, record official/derived
    origin and the effective-text/source/model hashes that define their work key, and store
    one validated vector per chunk. Official and derived text are never merged, and
    prerequisite/additional text is never stored here.
    """

    __tablename__ = "course_embedding_chunks"
    __table_args__ = (
        _not_blank("text"),
        _not_blank("embedding_model"),
        CheckConstraint(
            "representative_source_hash ~ '^[0-9a-f]{64}$'",
            name="representative_source_hash_sha256",
        ),
        CheckConstraint(
            "effective_text_hash ~ '^[0-9a-f]{64}$'", name="effective_text_hash_sha256"
        ),
        CheckConstraint("source_text_hash ~ '^[0-9a-f]{64}$'", name="source_text_hash_sha256"),
        CheckConstraint("chunk_text_hash ~ '^[0-9a-f]{64}$'", name="chunk_text_hash_sha256"),
        CheckConstraint(
            "embedding_artifact_sha256 ~ '^[0-9a-f]{64}$'",
            name="embedding_artifact_sha256_sha256",
        ),
        CheckConstraint(
            "embedding_configuration_hash ~ '^[0-9a-f]{64}$'",
            name="embedding_configuration_hash_sha256",
        ),
        CheckConstraint("chunk_index >= 0", name="chunk_index_nonnegative"),
        CheckConstraint(
            "(text_origin = 'official' AND effective_text_hash = source_text_hash "
            "AND translation_method IS NULL AND translation_model IS NULL "
            "AND translation_generated_at IS NULL) "
            "OR (text_origin = 'derived' AND translation_method IS NOT NULL "
            "AND translation_generated_at IS NOT NULL "
            "AND ((translation_method = 'manual' AND translation_model IS NULL) "
            "OR (translation_method = 'model' AND translation_model IS NOT NULL "
            "AND btrim(translation_model) <> '')))",
            name="origin_provenance_consistent",
        ),
        CheckConstraint(
            "(status = 'completed' AND embedding IS NOT NULL) "
            "OR (status IN ('pending', 'failed') AND embedding IS NULL)",
            name="lifecycle_consistent",
        ),
        UniqueConstraint(
            "course_version_id",
            "field",
            "language",
            "chunk_index",
            name="uq_course_embedding_chunks_version_field_language_index",
        ),
        Index(
            "ix_course_embedding_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
            postgresql_with={"m": 16, "ef_construction": 64},
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    course_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("course_versions.id", ondelete="CASCADE")
    )
    field: Mapped[TeachingTextField] = mapped_column(
        _enum(TeachingTextField, "teaching_text_field")
    )
    language: Mapped[TeachingTextLanguage] = mapped_column(
        _enum(TeachingTextLanguage, "derived_target_language")
    )
    chunk_index: Mapped[int] = mapped_column(Integer)
    text_origin: Mapped[TeachingTextOrigin] = mapped_column(
        _enum(TeachingTextOrigin, "teaching_text_origin")
    )
    text: Mapped[str] = mapped_column(Text)
    representative_source_hash: Mapped[str] = mapped_column(Text)
    effective_text_hash: Mapped[str] = mapped_column(Text)
    source_text_hash: Mapped[str] = mapped_column(Text)
    chunk_text_hash: Mapped[str] = mapped_column(Text)
    embedding_model: Mapped[str] = mapped_column(Text)
    embedding_artifact_sha256: Mapped[str] = mapped_column(Text)
    embedding_configuration_hash: Mapped[str] = mapped_column(Text)
    translation_method: Mapped[TranslationMethod | None] = mapped_column(
        _enum(TranslationMethod, "translation_method"), nullable=True
    )
    translation_model: Mapped[str | None] = mapped_column(Text, nullable=True)
    translation_generated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[CourseEmbeddingStatus] = mapped_column(
        _enum(CourseEmbeddingStatus, "course_embedding_status")
    )
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(COURSE_EMBEDDING_DIMENSION), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Module(Base):
    """Canonical module identity shared by exact module versions."""

    __tablename__ = "modules"
    __table_args__ = (_not_blank("group_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    group_id: Mapped[str] = mapped_column(Text, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ModuleVersion(Base):
    """One exact Kori module version, including source state and target credits."""

    __tablename__ = "module_versions"
    __table_args__ = (
        _not_blank("sisu_module_id"),
        _not_blank("document_state"),
        CheckConstraint(
            "(target_credits_min IS NULL OR target_credits_min >= 0) "
            "AND (target_credits_max IS NULL OR target_credits_max >= 0)",
            name="target_credits_nonnegative",
        ),
        CheckConstraint(
            "target_credits_min IS NULL OR target_credits_max IS NULL "
            "OR target_credits_min <= target_credits_max",
            name="target_credits_ordered",
        ),
        CheckConstraint(
            "validity_start IS NULL OR validity_end IS NULL OR validity_start <= validity_end",
            name="validity_dates_ordered",
        ),
        CheckConstraint(
            "source_revision IS NULL OR source_revision >= 0", name="source_revision_nonnegative"
        ),
        CheckConstraint(
            "source_modification_ordinal IS NULL OR source_modification_ordinal >= 0",
            name="source_modification_ordinal_nonnegative",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    module_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("modules.id", ondelete="RESTRICT")
    )
    sisu_module_id: Mapped[str] = mapped_column(Text, unique=True)
    module_type: Mapped[ModuleType] = mapped_column(_enum(ModuleType, "module_type"))
    code: Mapped[str | None] = mapped_column(Text, nullable=True)
    name_fi: Mapped[str | None] = mapped_column(Text, nullable=True)
    name_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_credits_min: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    target_credits_max: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    document_state: Mapped[str] = mapped_column(Text)
    validity_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    validity_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    source_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_modification_ordinal: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    source_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("source_snapshots.id", ondelete="RESTRICT"), unique=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ModuleVersionCurriculumPeriod(Base):
    """Membership of an exact module version in an academic period."""

    __tablename__ = "module_version_curriculum_periods"

    module_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("module_versions.id", ondelete="CASCADE"), primary_key=True
    )
    curriculum_period_id: Mapped[str] = mapped_column(
        Text, ForeignKey("curriculum_periods.id", ondelete="RESTRICT"), primary_key=True
    )


class OfficialPrerequisiteOption(Base):
    """One ordered AND group in an official compulsory/recommended expression."""

    __tablename__ = "official_prerequisite_options"
    __table_args__ = (
        CheckConstraint("option_index >= 0", name="option_index_nonnegative"),
        UniqueConstraint(
            "target_course_version_id",
            "requirement_kind",
            "option_index",
            name="uq_prerequisite_options_target_kind_position",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    target_course_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("course_versions.id", ondelete="CASCADE")
    )
    option_index: Mapped[int] = mapped_column(Integer)
    requirement_kind: Mapped[PrerequisiteRequirementKind] = mapped_column(
        _enum(PrerequisiteRequirementKind, "prerequisite_requirement_kind")
    )


class OfficialPrerequisiteOptionMember(Base):
    """One ordered course or module member in an official prerequisite group."""

    __tablename__ = "official_prerequisite_option_members"
    __table_args__ = (
        _not_blank("referenced_group_id"),
        CheckConstraint("member_index >= 0", name="member_index_nonnegative"),
        UniqueConstraint(
            "prerequisite_option_id",
            "member_index",
            name="uq_prerequisite_members_option_position",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    prerequisite_option_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("official_prerequisite_options.id", ondelete="CASCADE")
    )
    member_index: Mapped[int] = mapped_column(Integer)
    member_type: Mapped[PrerequisiteMemberType] = mapped_column(
        _enum(PrerequisiteMemberType, "prerequisite_member_type")
    )
    referenced_group_id: Mapped[str] = mapped_column(Text)


class OfficialSubstitutionOption(Base):
    """One ordered AND group in a directional official substitution expression."""

    __tablename__ = "official_substitution_options"
    __table_args__ = (
        CheckConstraint("option_index >= 0", name="option_index_nonnegative"),
        UniqueConstraint(
            "source_course_version_id",
            "option_index",
            name="uq_substitution_options_source_position",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_course_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("course_versions.id", ondelete="CASCADE")
    )
    option_index: Mapped[int] = mapped_column(Integer)


class OfficialSubstitutionOptionMember(Base):
    """One ordered course group member in a directional substitution group."""

    __tablename__ = "official_substitution_option_members"
    __table_args__ = (
        _not_blank("course_group_id"),
        CheckConstraint("member_index >= 0", name="member_index_nonnegative"),
        CheckConstraint("credits IS NULL OR credits >= 0", name="credits_nonnegative"),
        UniqueConstraint(
            "substitution_option_id",
            "member_index",
            name="uq_substitution_members_option_position",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    substitution_option_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("official_substitution_options.id", ondelete="CASCADE")
    )
    member_index: Mapped[int] = mapped_column(Integer)
    course_group_id: Mapped[str] = mapped_column(Text)
    credits: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)


class ModuleRuleNode(Base):
    """One ordered typed node in a module version's recursive rule AST."""

    __tablename__ = "module_rule_nodes"
    __table_args__ = (
        CheckConstraint("sibling_position >= 0", name="sibling_position_nonnegative"),
        CheckConstraint(
            "(require_min IS NULL OR require_min >= 0) AND (require_max IS NULL OR require_max >= 0)",
            name="require_bounds_nonnegative",
        ),
        CheckConstraint(
            "require_min IS NULL OR require_max IS NULL OR require_min <= require_max",
            name="require_bounds_ordered",
        ),
        CheckConstraint(
            "(credits_min IS NULL OR credits_min >= 0) AND (credits_max IS NULL OR credits_max >= 0)",
            name="credit_bounds_nonnegative",
        ),
        CheckConstraint(
            "credits_min IS NULL OR credits_max IS NULL OR credits_min <= credits_max",
            name="credit_bounds_ordered",
        ),
        CheckConstraint(
            "(count_min IS NULL OR count_min >= 0) AND (count_max IS NULL OR count_max >= 0)",
            name="count_bounds_nonnegative",
        ),
        CheckConstraint(
            "count_min IS NULL OR count_max IS NULL OR count_min <= count_max",
            name="count_bounds_ordered",
        ),
        CheckConstraint(
            "(node_type IN ('CourseUnitRule', 'ModuleRule') AND referenced_group_id IS NOT NULL) "
            "OR (node_type NOT IN ('CourseUnitRule', 'ModuleRule') AND referenced_group_id IS NULL)",
            name="referenced_group_id_matches_node_type",
        ),
        UniqueConstraint(
            "id", "module_version_id", name="uq_module_rule_nodes_id_module_version_id"
        ),
        ForeignKeyConstraint(
            ["parent_node_id", "module_version_id"],
            ["module_rule_nodes.id", "module_rule_nodes.module_version_id"],
            ondelete="CASCADE",
            name="fk_module_rule_nodes_parent_same_module",
        ),
        UniqueConstraint(
            "parent_node_id",
            "sibling_position",
            name="uq_module_rule_nodes_parent_sibling_position",
        ),
        Index(
            "uq_module_rule_nodes_root",
            "module_version_id",
            unique=True,
            postgresql_where=text("parent_node_id IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    module_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("module_versions.id", ondelete="CASCADE")
    )
    parent_node_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    sibling_position: Mapped[int] = mapped_column(Integer)
    local_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    node_type: Mapped[ModuleRuleType] = mapped_column(_enum(ModuleRuleType, "module_rule_type"))
    require_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    require_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    all_mandatory: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    description: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    credits_min: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    credits_max: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    count_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    count_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    referenced_group_id: Mapped[str | None] = mapped_column(Text, nullable=True)


class InferredPrerequisiteSet(Base):
    """One current final inferred prerequisite expression set for an active canonical target.

    The row is a separately derived claim: it names its producer and coverage, never mutates
    official curriculum storage, and holds at most one current set per target. `expression`
    is the explicit validated AND/OR tree published by the strict repository, or SQL NULL for
    a complete/partial empty result.
    """

    __tablename__ = "inferred_prerequisite_sets"
    __table_args__ = (
        _not_blank("producer_name"),
        _not_blank("producer_version"),
        CheckConstraint(
            "activity_as_of_academic_year_start > 0",
            name="activity_year_start_positive",
        ),
        CheckConstraint("activity_window_years > 0", name="activity_window_years_positive"),
        CheckConstraint("eligible_source_count >= 0", name="eligible_source_count_nonnegative"),
        CheckConstraint("processed_source_count >= 0", name="processed_count_nonnegative"),
        CheckConstraint("accepted_source_count >= 0", name="accepted_source_count_nonnegative"),
        CheckConstraint(
            "accepted_source_count <= processed_source_count "
            "AND processed_source_count <= eligible_source_count",
            name="inferred_counts_ordered",
        ),
        CheckConstraint(
            "(coverage_state = 'partial' AND processed_source_count < eligible_source_count) "
            "OR (coverage_state = 'complete' "
            "AND processed_source_count = eligible_source_count)",
            name="coverage_state_counts_consistent",
        ),
        CheckConstraint(
            "(accepted_source_count = 0 AND expression IS NULL) "
            "OR (accepted_source_count > 0 AND expression IS NOT NULL)",
            name="expression_count_consistent",
        ),
        CheckConstraint("input_hash ~ '^[0-9a-f]{64}$'", name="input_hash_sha256"),
        CheckConstraint("payload_hash ~ '^[0-9a-f]{64}$'", name="payload_hash_sha256"),
        UniqueConstraint("target_course_id", name="uq_inferred_prerequisite_sets_target_course_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    target_course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE")
    )
    activity_as_of_academic_year_start: Mapped[int] = mapped_column(Integer)
    activity_window_years: Mapped[int] = mapped_column(Integer)
    coverage_state: Mapped[InferredCoverageState] = mapped_column(
        _enum(InferredCoverageState, "inferred_coverage_state")
    )
    eligible_source_count: Mapped[int] = mapped_column(Integer)
    processed_source_count: Mapped[int] = mapped_column(Integer)
    accepted_source_count: Mapped[int] = mapped_column(Integer)
    producer_kind: Mapped[InferredProducerKind] = mapped_column(
        _enum(InferredProducerKind, "inferred_producer_kind")
    )
    producer_name: Mapped[str] = mapped_column(Text)
    producer_version: Mapped[str] = mapped_column(Text)
    input_hash: Mapped[str] = mapped_column(Text)
    payload_hash: Mapped[str] = mapped_column(Text)
    expression: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True), nullable=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class InferredEquivalenceGroup(Base):
    """One target-independent inferred equivalent-course group.

    The caller-supplied `id` is the stable group identity across replacement and activity
    reconciliation. It is never derived from membership. Group-level producer/evidence
    provenance is a separately derived inferred claim that never becomes official
    substitution or canonical-alias behavior. Membership lives only in the normalized member
    table, so no course `group_id`, activity boolean, member order, or expression JSON is
    duplicated here.
    """

    __tablename__ = "inferred_equivalence_groups"
    __table_args__ = (
        _not_blank("producer_name"),
        _not_blank("producer_version"),
        CheckConstraint("input_hash ~ '^[0-9a-f]{64}$'", name="input_hash_sha256"),
        CheckConstraint("payload_hash ~ '^[0-9a-f]{64}$'", name="payload_hash_sha256"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    producer_kind: Mapped[InferredProducerKind] = mapped_column(
        _enum(InferredProducerKind, "inferred_producer_kind")
    )
    producer_name: Mapped[str] = mapped_column(Text)
    producer_version: Mapped[str] = mapped_column(Text)
    input_hash: Mapped[str] = mapped_column(Text)
    payload_hash: Mapped[str] = mapped_column(Text)
    inference: Mapped[dict] = mapped_column(JSONB(none_as_null=True))
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class InferredEquivalenceGroupMember(Base):
    """One canonical course member of one inferred equivalence group.

    Only the course FK plus the two publication-time activity context values are persisted.
    Canonical `course.group_id`, `is_active`, member order, and expression data stay owned by
    `courses` and the group row so reconciliation compares stored context against the live
    course rather than a duplicated copy.
    """

    __tablename__ = "inferred_equivalence_group_members"
    __table_args__ = (
        CheckConstraint(
            "activity_as_of_academic_year_start > 0",
            name="activity_year_start_positive",
        ),
        CheckConstraint("activity_window_years > 0", name="activity_window_years_positive"),
        UniqueConstraint(
            "equivalence_group_id",
            "course_id",
            name="uq_inferred_equivalence_group_members_group_course",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    equivalence_group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("inferred_equivalence_groups.id", ondelete="CASCADE")
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE")
    )
    activity_as_of_academic_year_start: Mapped[int] = mapped_column(Integer)
    activity_window_years: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class InferencePipelineRun(Base):
    """One shared inference execution identity keyed by its coarse configuration identity.

    Rows are separately derived evidence, never official curriculum and never a product-visible
    inferred relationship. One row is selected or created per coarse identity (model/runtime/prompt/
    schema/pipeline plus route). Matching work reuse is owned by
    `inference_target_work.work_key_sha256`. `configuration` holds the route only, and catalogue
    identity is absent because the processing cycle owns it.
    """

    __tablename__ = "inference_pipeline_runs"
    __table_args__ = (
        _not_blank("model_identity"),
        _not_blank("runtime_identity"),
        _not_blank("prompt_version"),
        CheckConstraint(
            "prompt_content_sha256 ~ '^[0-9a-f]{64}$'", name="prompt_content_sha256_sha256"
        ),
        _not_blank("schema_version"),
        CheckConstraint("schema_sha256 ~ '^[0-9a-f]{64}$'", name="schema_sha256_sha256"),
        _not_blank("pipeline_version"),
        CheckConstraint(
            "run_identity_sha256 ~ '^[0-9a-f]{64}$'", name="run_identity_sha256_sha256"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    model_identity: Mapped[str] = mapped_column(Text)
    runtime_identity: Mapped[str] = mapped_column(Text)
    prompt_version: Mapped[str] = mapped_column(Text)
    prompt_content_sha256: Mapped[str] = mapped_column(Text)
    schema_version: Mapped[str] = mapped_column(Text)
    schema_sha256: Mapped[str] = mapped_column(Text)
    pipeline_version: Mapped[str] = mapped_column(Text)
    run_identity_sha256: Mapped[str] = mapped_column(Text)
    configuration: Mapped[dict] = mapped_column(JSONB(none_as_null=True))


class InferenceTargetWork(Base):
    """One global matching-work row for a canonical target and exact execution identity.

    `(target_course_id, work_key_sha256)` is the global matching-work authority: a completed
    row is reused across executions with the same coarse identity, target activity context, and
    input hash, and a changed identity creates a distinct row instead of overwriting retained
    evidence. One completion row in `inference_model_attempts` carries the generated result. This
    row carries only the current generation resumability status.
    """

    __tablename__ = "inference_target_work"
    __table_args__ = (
        CheckConstraint(
            "activity_as_of_academic_year_start > 0", name="activity_year_start_positive"
        ),
        CheckConstraint("activity_window_years > 0", name="activity_window_years_positive"),
        CheckConstraint("input_sha256 ~ '^[0-9a-f]{64}$'", name="input_sha256_sha256"),
        CheckConstraint("work_key_sha256 ~ '^[0-9a-f]{64}$'", name="work_key_sha256_sha256"),
        UniqueConstraint(
            "target_course_id",
            "work_key_sha256",
            name="uq_inference_target_work_target_work_key",
        ),
        Index("ix_inference_target_work_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_by_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("inference_pipeline_runs.id", ondelete="RESTRICT")
    )
    target_course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courses.id", ondelete="RESTRICT")
    )
    activity_as_of_academic_year_start: Mapped[int] = mapped_column(Integer)
    activity_window_years: Mapped[int] = mapped_column(Integer)
    input_sha256: Mapped[str] = mapped_column(Text)
    work_key_sha256: Mapped[str] = mapped_column(Text)
    status: Mapped[InferenceWorkStatus] = mapped_column(
        _enum(InferenceWorkStatus, "inference_work_status")
    )


class InferenceModelAttempt(Base):
    """One completion row per completed generation: its current payload and generated time.

    The `request_payload` JSONB holds a completion payload (facts plus, before composition, the
    descriptors and uncomposed validated result for zero-model recovery). After composition only the
    facts and generated time remain. No raw/decoded/request representation is retained, and no column
    here is official curriculum or a final product relationship.
    """

    __tablename__ = "inference_model_attempts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    target_work_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("inference_target_work.id", ondelete="RESTRICT")
    )
    request_payload: Mapped[dict] = mapped_column(JSONB(none_as_null=True))
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class InferenceProposal(Base):
    """One immutable, versioned proposal composed from a validated completion.

    A row is separately derived inference evidence, never official curriculum and never a final
    product relationship: its `expression` JSONB envelope holds the composed expression and the
    option flags, and `equivalence` holds the composed equivalence candidates. The source
    completion FK owns the work link. `identity_sha256` is unique and is the append-only proposal
    authority: an identical identity is reused as-is, and nothing is ever updated in place.
    """

    __tablename__ = "inference_proposals"
    __table_args__ = (
        _not_blank("proposal_version"),
        CheckConstraint("identity_sha256 ~ '^[0-9a-f]{64}$'", name="identity_sha256_sha256"),
        UniqueConstraint("identity_sha256", name="uq_inference_proposals_identity_sha256"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    target_course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courses.id", ondelete="RESTRICT")
    )
    source_attempt_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("inference_model_attempts.id", ondelete="RESTRICT")
    )
    proposal_version: Mapped[str] = mapped_column(Text)
    identity_sha256: Mapped[str] = mapped_column(Text)
    expression: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True), nullable=True)
    equivalence: Mapped[list] = mapped_column(JSONB(none_as_null=True))


# The teaching-text processing marker is scheduling state, never an "inferred-before" coverage claim:
# an inactive candidate source may be marked processed without ever receiving a target result, and a
# generation model/prompt/settings change alone never resets it. `accepted_proposal_id` retains the
# last accepted pointer even while the marker is FALSE, so pending work never erases the
# displayed complete output. `generation_attempt_count` is the durable lifetime
# generation-attempt ordinal owner: it is retained across cycle pruning and drives no-reuse local retry seeds.
# `disposition` is the operator's durable inference decision: NULL means no override (automatic), and
# `done`/`failed` are the two explicit terminal choices. It is separate from the
# teaching-text `processed` flag and is retained across text changes, cycles and pruning until the operator
# changes or clears it.
class InferenceCourseProcessing(Base):
    """One canonical course's teaching-text marker, accepted pointer, lifetime counter and decision."""

    __tablename__ = "inference_course_processing"
    __table_args__ = (
        CheckConstraint(
            "teaching_text_sha256 ~ '^[0-9a-f]{64}$'",
            name="teaching_text_sha256_sha256",
        ),
        CheckConstraint(
            "generation_attempt_count >= 0",
            name="generation_attempt_count_nonnegative",
        ),
        CheckConstraint(
            "disposition IS NULL OR disposition IN ('done','failed')",
            name="disposition_valid",
        ),
    )

    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("courses.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    teaching_text_sha256: Mapped[str] = mapped_column(Text)
    processed: Mapped[bool] = mapped_column(Boolean)
    was_active: Mapped[bool] = mapped_column(Boolean)
    accepted_proposal_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("inference_proposals.id", ondelete="RESTRICT"),
        nullable=True,
    )
    generation_attempt_count: Mapped[int] = mapped_column(
        BigInteger, server_default=text("0"), default=0
    )
    disposition: Mapped[str | None] = mapped_column(Text, nullable=True)


class InferenceProcessingCycle(Base):
    """One durable inference processing cycle and its current global stage.

    A cycle is the serial batch boundary: it records the selection-compatibility input digest
    and advances through multiview, rerank, inference and publication. The stage column itself owns
    completion (``complete``), and created_at orders cycles across retained failure anchors.
    It never carries generation configuration or prompt identity.
    """

    __tablename__ = "inference_processing_cycles"
    __table_args__ = (
        CheckConstraint("input_sha256 ~ '^[0-9a-f]{64}$'", name="input_sha256_sha256"),
        CheckConstraint(
            "stage IN ('multiview','rerank','inference','publication','complete')",
            name="stage_valid",
        ),
        Index("ix_inference_processing_cycles_created_at", "created_at", "id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    input_sha256: Mapped[str] = mapped_column(Text)
    stage: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class InferenceProcessingTarget(Base):
    """One per-target checkpoint inside one processing cycle.

    The three stage-state columns, the payload columns, the planned work key, the proposal
    pointer and the safe error type mirror the shape-carrier DTO. The repository transition owner
    enforces the stage-order/payload/failure policy once. ``generation_started`` is a separate
    reservation-owned calculation fact outside the observer DTO, the cycle
    hash and the generation work-key formula. Only the compact selection references and pointers
    live here.
    """

    __tablename__ = "inference_processing_targets"
    __table_args__ = (
        CheckConstraint(
            "multiview_state IN ('pending','completed','failed')", name="multiview_state_valid"
        ),
        CheckConstraint(
            "rerank_state IN ('pending','completed','skipped','failed')", name="rerank_state_valid"
        ),
        CheckConstraint(
            "inference_state IN ('pending','completed','skipped','failed')",
            name="inference_state_valid",
        ),
        CheckConstraint(
            "generation_work_key_sha256 IS NULL OR generation_work_key_sha256 ~ '^[0-9a-f]{64}$'",
            name="generation_work_key_sha256_sha256",
        ),
        CheckConstraint(
            "error_type IS NULL OR (length(error_type) BETWEEN 1 AND 200 "
            "AND error_type ~ '^[A-Za-z_][A-Za-z0-9_]*$')",
            name="error_type_safe",
        ),
    )

    cycle_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("inference_processing_cycles.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    target_course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("courses.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    multiview_state: Mapped[str] = mapped_column(Text)
    rerank_state: Mapped[str] = mapped_column(Text)
    inference_state: Mapped[str] = mapped_column(Text)
    pool_input: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True), nullable=True)
    target_input: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True), nullable=True)
    generation_work_key_sha256: Mapped[str | None] = mapped_column(Text, nullable=True)
    generation_started: Mapped[bool] = mapped_column(
        Boolean, server_default=text("false"), default=False
    )
    proposal_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("inference_proposals.id", ondelete="RESTRICT"),
        nullable=True,
    )
    error_type: Mapped[str | None] = mapped_column(Text, nullable=True)


class InferenceTargetFailure(Base):
    """One append-only summary of a failed target episode inside one processing cycle.

    It records the failing stage, the actual action count, the producer's safe error class and the
    fixed reason, and is retained after a subsequent success or stop. For generation it is written once
    per failed whole-target attempt (``attempt_count`` one, ``exhausted`` only on a bounded route's
    final pass request), while a bounded multiview/rerank/preparation stage keeps one summary episode
    per exhausted or control-yielded pass. ``inference_preparation`` maps to the inference stage for
    scheduling but is stored verbatim here.
    """

    __tablename__ = "inference_target_failures"
    __table_args__ = (
        ForeignKeyConstraint(
            ["cycle_id", "target_course_id"],
            [
                "inference_processing_targets.cycle_id",
                "inference_processing_targets.target_course_id",
            ],
            ondelete="RESTRICT",
            name="fk_inference_target_failures_target",
        ),
        CheckConstraint(
            "stage IN ('multiview','rerank','inference_preparation','inference')",
            name="stage_valid",
        ),
        CheckConstraint("attempt_count > 0", name="attempt_count_positive"),
        CheckConstraint(
            "length(error_type) BETWEEN 1 AND 200 AND error_type ~ '^[A-Za-z_][A-Za-z0-9_]*$'",
            name="error_type_safe",
        ),
        CheckConstraint(
            "reason IN ('missing_target_chunks','insufficient_candidates','incomplete_views',"
            "'request_failed','provider_output','invalid_result','ambiguous_code',"
            "'multiple_requirement_sets','target_direct_source','context_exceeded')",
            name="reason_valid",
        ),
        Index(
            "ix_inference_target_failures_cycle_target_created",
            "cycle_id",
            "target_course_id",
            "created_at",
            "id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cycle_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    target_course_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    stage: Mapped[str] = mapped_column(Text)
    attempt_count: Mapped[int] = mapped_column(Integer)
    error_type: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text)
    exhausted: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
