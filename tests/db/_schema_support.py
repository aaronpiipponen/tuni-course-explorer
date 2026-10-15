"""Shared schema-test fixtures and row builders for the opt-in PostgreSQL proofs."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.exc import IntegrityError

from course_explorer.db.models import (
    Course,
    CourseEmbeddingChunk,
    CourseText,
    CourseVersion,
    CourseVersionCurriculumPeriod,
    CurriculumPeriod,
    DerivedCourseText,
    InferredPrerequisiteSet,
    IngestionRun,
    Module,
    ModuleRuleNode,
    ModuleVersion,
    OfficialPrerequisiteOption,
    OfficialPrerequisiteOptionMember,
    OfficialSubstitutionOption,
    OfficialSubstitutionOptionMember,
    SourceSnapshot,
)
from course_explorer.db.session import session_scope
from course_explorer.enums import (
    CourseEmbeddingStatus,
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
from course_explorer.prerequisite.domain import InferenceNodeMetadata


def _schema_inferred_metadata() -> InferenceNodeMetadata:
    """Build one test-produced inferred metadata payload for stored expression rows."""
    return InferenceNodeMetadata(confidence=Decimal("0.9"), requirement_ids=("R1",))


@pytest.fixture()
def integrity_records(database: tuple[Engine, object]) -> dict[str, uuid.UUID | str]:
    """Insert representative source, identity, official-expression, and AST rows."""
    _, factory = database
    period_id = "uta-lvv-2026"
    run_id = uuid.uuid4()
    course_id = uuid.uuid4()
    course_version_id = uuid.uuid4()
    module_ids = [uuid.uuid4(), uuid.uuid4()]
    module_version_ids = [uuid.uuid4(), uuid.uuid4()]
    snapshot_ids = [uuid.uuid4(), uuid.uuid4(), uuid.uuid4()]
    prerequisite_option_id = uuid.uuid4()
    substitution_option_id = uuid.uuid4()
    root_node_id = uuid.uuid4()

    with session_scope(factory) as session:
        session.add(
            IngestionRun(
                id=run_id,
                status=IngestionRunStatus.COMPLETED,
                raw_root_path="data/raw/run",
                manifest_path="data/raw/run/manifest.json",
            )
        )
        session.add(CurriculumPeriod(id=period_id, academic_year_start=2026))
        session.add(
            SourceSnapshot(
                id=snapshot_ids[0],
                ingestion_run_id=run_id,
                object_type=SourceObjectType.COURSE_UNIT,
                source_object_id="course-version-2026",
                source_group_id="course-group-1",
                response_path="courses/batch.json",
                response_item_index=0,
                source_hash="hash-course",
            )
        )
        for index, snapshot_id in enumerate(snapshot_ids[1:], start=1):
            session.add(
                SourceSnapshot(
                    id=snapshot_id,
                    ingestion_run_id=run_id,
                    object_type=SourceObjectType.MODULE,
                    source_object_id=f"module-version-{index}",
                    source_group_id=f"module-group-{index}",
                    response_path="modules/batch.json",
                    response_item_index=index - 1,
                    source_hash=f"hash-module-{index}",
                )
            )
        session.flush()
        session.add(
            Course(
                id=course_id,
                group_id="course-group-1",
                is_active=True,
                activity_as_of_academic_year_start=2026,
                activity_window_years=3,
            )
        )
        session.add(
            CourseVersion(
                id=course_version_id,
                course_id=course_id,
                sisu_course_unit_id="course-version-2026",
                code="TEST.100",
                name_en="Test Course",
                credits_min=5,
                credits_max=5,
                official_url="https://example.test/course",
                document_state="ACTIVE",
                source_snapshot_id=snapshot_ids[0],
            )
        )
        session.flush()
        session.add(
            CourseVersionCurriculumPeriod(
                course_version_id=course_version_id, curriculum_period_id=period_id
            )
        )
        session.add(CourseText(course_version_id=course_version_id, content_en="Course content"))
        session.add(
            OfficialPrerequisiteOption(
                id=prerequisite_option_id,
                target_course_version_id=course_version_id,
                option_index=0,
                requirement_kind=PrerequisiteRequirementKind.COMPULSORY,
            )
        )
        session.add_all(
            [
                OfficialPrerequisiteOptionMember(
                    id=uuid.uuid4(),
                    prerequisite_option_id=prerequisite_option_id,
                    member_index=0,
                    member_type=PrerequisiteMemberType.COURSE,
                    referenced_group_id="unresolved-course-group",
                ),
                OfficialPrerequisiteOptionMember(
                    id=uuid.uuid4(),
                    prerequisite_option_id=prerequisite_option_id,
                    member_index=1,
                    member_type=PrerequisiteMemberType.MODULE,
                    referenced_group_id="unresolved-module-group",
                ),
            ]
        )
        session.add(
            OfficialSubstitutionOption(
                id=substitution_option_id,
                source_course_version_id=course_version_id,
                option_index=0,
            )
        )
        session.add(
            OfficialSubstitutionOptionMember(
                id=uuid.uuid4(),
                substitution_option_id=substitution_option_id,
                member_index=0,
                course_group_id="substitute-course-group",
                credits=5,
            )
        )
        for index, (module_id, version_id, snapshot_id) in enumerate(
            zip(module_ids, module_version_ids, snapshot_ids[1:], strict=True), start=1
        ):
            session.add(Module(id=module_id, group_id=f"module-group-{index}"))
            session.add(
                ModuleVersion(
                    id=version_id,
                    module_id=module_id,
                    sisu_module_id=f"module-version-{index}",
                    module_type=ModuleType.STUDY_MODULE,
                    name_en=f"Test Module {index}",
                    target_credits_min=5,
                    target_credits_max=10,
                    document_state="ACTIVE",
                    source_snapshot_id=snapshot_id,
                )
            )
        session.flush()
        session.add(
            ModuleRuleNode(
                id=root_node_id,
                module_version_id=module_version_ids[0],
                sibling_position=0,
                node_type=ModuleRuleType.COMPOSITE_RULE,
                require_min=1,
                require_max=1,
                all_mandatory=True,
            )
        )
        session.add(
            ModuleRuleNode(
                id=uuid.uuid4(),
                module_version_id=module_version_ids[0],
                parent_node_id=root_node_id,
                sibling_position=0,
                node_type=ModuleRuleType.COURSE_UNIT_RULE,
                referenced_group_id="unresolved-rule-course",
            )
        )

    return {
        "run_id": run_id,
        "course_id": course_id,
        "course_version_id": course_version_id,
        "period_id": period_id,
        "snapshot_id": snapshot_ids[0],
        "module_version_id": module_version_ids[0],
        "other_module_version_id": module_version_ids[1],
        "prerequisite_option_id": prerequisite_option_id,
        "substitution_option_id": substitution_option_id,
        "root_node_id": root_node_id,
    }


def constraint_name(error: IntegrityError) -> str:
    """Return PostgreSQL's authoritative violated constraint name."""
    return error.orig.diag.constraint_name


def derived_text_row(course_version_id: uuid.UUID, **overrides: object) -> DerivedCourseText:
    """Build one otherwise valid derived translation row for constraint tests."""
    values: dict[str, object] = {
        "course_version_id": course_version_id,
        "field": TeachingTextField.CONTENT,
        "language": TeachingTextLanguage.EN,
        "text": "Matrices",
        "source_language": TeachingTextLanguage.FI,
        "source_text_hash": "a" * 64,
        "translation_method": TranslationMethod.MANUAL,
        "translation_model": None,
        "generated_at": datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
    }
    values.update(overrides)
    return DerivedCourseText(**values)


@pytest.fixture()
def two_course_versions(database: tuple[Engine, object]) -> tuple[object, dict[str, uuid.UUID]]:
    """Seed two exact course versions with distinct canonical identities."""
    _, factory = database
    run_id = uuid.uuid4()
    snapshot_ids = [uuid.uuid4(), uuid.uuid4()]
    course_ids = [uuid.uuid4(), uuid.uuid4()]
    version_ids = [uuid.uuid4(), uuid.uuid4()]
    with session_scope(factory) as session:
        session.add(
            IngestionRun(
                id=run_id,
                status=IngestionRunStatus.COMPLETED,
                raw_root_path="data/raw/run",
                manifest_path="data/raw/run/manifest.json",
            )
        )
        for index in range(2):
            session.add(
                SourceSnapshot(
                    id=snapshot_ids[index],
                    ingestion_run_id=run_id,
                    object_type=SourceObjectType.COURSE_UNIT,
                    source_object_id=f"derived-course-v{index}",
                    source_group_id=f"derived-course-{index}",
                    response_path="courses/derived.json",
                    response_item_index=index,
                    source_hash="d" * 64,
                )
            )
            session.add(
                Course(
                    id=course_ids[index],
                    group_id=f"derived-course-{index}",
                    is_active=True,
                    activity_as_of_academic_year_start=2026,
                    activity_window_years=3,
                )
            )
        session.flush()
        for index in range(2):
            session.add(
                CourseVersion(
                    id=version_ids[index],
                    course_id=course_ids[index],
                    sisu_course_unit_id=f"derived-course-v{index}",
                    code=f"DERIVED.{index}",
                    name_en="Derived Course",
                    credits_min=5,
                    credits_max=5,
                    official_url="https://example.test/derived",
                    document_state="ACTIVE",
                    source_snapshot_id=snapshot_ids[index],
                )
            )
    return factory, {
        "run_id": run_id,
        "snapshot_ids": snapshot_ids,
        "course_ids": course_ids,
        "version_ids": version_ids,
    }


def embedding_chunk_row(course_version_id: uuid.UUID, **overrides: object) -> CourseEmbeddingChunk:
    """Build one otherwise valid pending embedding chunk row for constraint tests."""
    values: dict[str, object] = {
        "course_version_id": course_version_id,
        "field": TeachingTextField.CONTENT,
        "language": TeachingTextLanguage.EN,
        "chunk_index": 0,
        "text_origin": TeachingTextOrigin.OFFICIAL,
        "text": "Matrices",
        "representative_source_hash": "a" * 64,
        "effective_text_hash": "b" * 64,
        "source_text_hash": "b" * 64,
        "chunk_text_hash": "c" * 64,
        "embedding_model": "BAAI/bge-m3",
        "embedding_artifact_sha256": "d" * 64,
        "embedding_configuration_hash": "e" * 64,
        "status": CourseEmbeddingStatus.PENDING,
    }
    values.update(overrides)
    return CourseEmbeddingChunk(**values)


def inferred_set_row(
    target_course_id: uuid.UUID,
    **overrides: object,
) -> InferredPrerequisiteSet:
    """Build one otherwise valid inferred set row for constraint tests."""
    values: dict[str, object] = {
        "target_course_id": target_course_id,
        "activity_as_of_academic_year_start": 2026,
        "activity_window_years": 3,
        "coverage_state": InferredCoverageState.COMPLETE,
        "eligible_source_count": 1,
        "processed_source_count": 1,
        "accepted_source_count": 0,
        "producer_kind": InferredProducerKind.TEST,
        "producer_name": "test-fixture",
        "producer_version": "1",
        "input_hash": "a" * 64,
        "payload_hash": "b" * 64,
        "expression": None,
        "generated_at": datetime(2026, 9, 14, 12, 0, tzinfo=UTC),
    }
    values.update(overrides)
    return InferredPrerequisiteSet(**values)


def target_course_id(factory: object, group_id: str) -> uuid.UUID:
    """Return the persisted UUID for one seeded canonical course."""
    with session_scope(factory) as session:
        course = session.scalar(select(Course).where(Course.group_id == group_id))
        assert course is not None
        return course.id


def _pre_category_expression(required: dict[str, object]) -> dict[str, object]:
    """Strip every inferred category from one dump to build the pre-category expression shape."""
    stripped: dict[str, object] = {
        key: value for key, value in required.items() if key != "inferred_category"
    }
    children = stripped.get("children")
    if isinstance(children, list):
        stripped["children"] = [
            _pre_category_expression(child) for child in children if isinstance(child, dict)
        ]
    return stripped


def _collect_inferred_categories(node: object) -> list[object]:
    """Return every `inferred_category` value in one nested stored expression."""
    if not isinstance(node, dict):
        raise AssertionError("stored inferred expression nodes must be JSON objects")
    categories: list[object] = [node.get("inferred_category")]
    children = node.get("children")
    if isinstance(children, list):
        for child in children:
            categories.extend(_collect_inferred_categories(child))
    return categories


def _stored_expression(factory: object, group_id: str) -> dict[str, object]:
    """Return one persisted inferred expression payload by canonical target identity."""
    with session_scope(factory) as session:
        course = session.scalar(select(Course).where(Course.group_id == group_id))
        assert course is not None
        row = session.scalar(
            select(InferredPrerequisiteSet).where(
                InferredPrerequisiteSet.target_course_id == course.id
            )
        )
        assert row is not None
        assert row.expression is not None
        return dict(row.expression)


def _stored_payload_hash(factory: object, group_id: str) -> str:
    """Return one persisted inferred-set payload hash by canonical target identity."""
    with session_scope(factory) as session:
        course = session.scalar(select(Course).where(Course.group_id == group_id))
        assert course is not None
        row = session.scalar(
            select(InferredPrerequisiteSet).where(
                InferredPrerequisiteSet.target_course_id == course.id
            )
        )
        assert row is not None
        return row.payload_hash
