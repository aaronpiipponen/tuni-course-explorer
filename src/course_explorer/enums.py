"""Database-independent shared enum values owned by the course-explorer domain.

ORM metadata, ingestion, inference, and every service import these enumerations from this
module so that domain code never depends on SQLAlchemy model declarations. Values are frozen:
they are persisted in columns and recorded in provenance identities, so renaming or reordering
a member changes stored bytes.
"""

from enum import StrEnum


class IngestionRunStatus(StrEnum):
    """Lifecycle values for raw source capture runs."""

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class SourceObjectType(StrEnum):
    """Raw source object families retained by a capture run."""

    COURSE_UNIT = "course_unit"
    MODULE = "module"


class ModuleType(StrEnum):
    """Public and recursively discovered Kori module types."""

    DEGREE_PROGRAMME = "DegreeProgramme"
    STUDY_MODULE = "StudyModule"
    GROUPING_MODULE = "GroupingModule"


class PrerequisiteRequirementKind(StrEnum):
    """Official prerequisite provenance categories."""

    COMPULSORY = "compulsory"
    RECOMMENDED = "recommended"


class PrerequisiteMemberType(StrEnum):
    """Canonical group type referenced by an official prerequisite member."""

    COURSE = "course"
    MODULE = "module"


class ModuleRuleType(StrEnum):
    """Typed Kori module-rule AST node kinds."""

    COMPOSITE_RULE = "CompositeRule"
    CREDITS_RULE = "CreditsRule"
    COURSE_UNIT_COUNT_RULE = "CourseUnitCountRule"
    COURSE_UNIT_RULE = "CourseUnitRule"
    MODULE_RULE = "ModuleRule"
    ANY_COURSE_UNIT_RULE = "AnyCourseUnitRule"
    ANY_MODULE_RULE = "AnyModuleRule"


class TeachingTextField(StrEnum):
    """Searchable teaching-text field families that may be translated."""

    NAME = "name"
    CONTENT = "content"
    OUTCOMES = "outcomes"


# The two fields whose text describes what a course teaches. Search, comparison and recommendation
# measure these fields, while a name cell identifies a course rather than teaching its subject.
DESCRIPTIVE_TEACHING_TEXT_FIELDS: tuple[TeachingTextField, ...] = (
    TeachingTextField.CONTENT,
    TeachingTextField.OUTCOMES,
)


class TeachingTextLanguage(StrEnum):
    """Language of a teaching-text value, either official or derived."""

    FI = "fi"
    EN = "en"


class TranslationMethod(StrEnum):
    """Provenance category for one derived translation row."""

    MANUAL = "manual"
    MODEL = "model"


class TeachingTextOrigin(StrEnum):
    """Whether an effective or embedded teaching-text value is official or derived."""

    OFFICIAL = "official"
    DERIVED = "derived"


class CourseEmbeddingStatus(StrEnum):
    """Lifecycle state of one durable course teaching-text chunk embedding."""

    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


class InferredCoverageState(StrEnum):
    """Whether a current inferred set processed every eligible source course."""

    PARTIAL = "partial"
    COMPLETE = "complete"


class InferredProducerKind(StrEnum):
    """What produced a derived inferred artifact, such as a current prerequisite set or group."""

    TEST = "test"
    INFERENCE = "inference"


class InferenceRunStatus(StrEnum):
    """Lifecycle of one durable inference pipeline-run occurrence."""

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class InferenceWorkStatus(StrEnum):
    """Lifecycle of one target's work row inside the global matching-work store."""

    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


class InferenceAttemptStatus(StrEnum):
    """Closed validation outcome of one immutable model attempt."""

    VALIDATED = "validated"
    CONTRACT_ERROR = "contract_error"
    REQUEST_ERROR = "request_error"
