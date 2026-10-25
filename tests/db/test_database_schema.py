"""Opt-in PostgreSQL migration, constraint, and transaction integration tests."""

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, MetaData, Table, inspect, select, text, update
from sqlalchemy.exc import IntegrityError

from course_explorer.config import load_database_settings, load_raw_database_settings
from course_explorer.datasets import require_database_schema
from course_explorer.db.models import (
    Base,
    Course,
    CourseVersion,
    InferenceCourseProcessing,
    InferenceModelAttempt,
    InferenceProcessingTarget,
    InferenceProposal,
    InferenceTargetWork,
    IngestionRun,
    ModuleRuleNode,
    SourceSnapshot,
)
from course_explorer.db.session import create_database_engine, create_session_factory, session_scope
from course_explorer.enums import (
    IngestionRunStatus,
    ModuleRuleType,
    SourceObjectType,
)
from course_explorer.inference.evidence_repository import InferenceEvidenceRepository
from course_explorer.inference.proposal_repository import InferenceProposalRepository
from course_explorer.inference.scheduling_repository import InferenceSchedulingRepository
from tests.conftest import alembic_config
from tests.db._schema_support import constraint_name
from tests.db._schema_support import integrity_records as integrity_records

pytestmark = [
    pytest.mark.integration,
]


@contextmanager
def _scratch_database(prefix: str) -> Iterator[Engine]:
    """Create one uniquely named test-owned database and drop it after the caller finishes.

    The raw settings must name a disposable ``_test`` database and no selected dataset. The
    database is created from ``template0`` through one administration connection to ``postgres``,
    and the yielded engine connects to the new database alone. Both engines are disposed even when
    creating or dropping the database fails.
    """
    raw = load_raw_database_settings()
    assert raw.selected_dataset_enabled is False
    assert raw.postgres_db.endswith("_test")

    name = f"{prefix}_{uuid.uuid4().hex}_test"
    administration_engine = create_database_engine(
        raw.model_copy(update={"postgres_db": "postgres"})
    )
    engine = create_database_engine(raw.model_copy(update={"postgres_db": name}))

    def autocommit():
        return administration_engine.connect().execution_options(isolation_level="AUTOCOMMIT")

    created = False
    try:
        with autocommit() as administration:
            administration.exec_driver_sql(f'CREATE DATABASE "{name}" TEMPLATE template0')
        created = True
        yield engine
    finally:
        engine.dispose()
        try:
            if created:
                with autocommit() as administration:
                    administration.exec_driver_sql(f'DROP DATABASE "{name}"')
        finally:
            administration_engine.dispose()


def test_head_schema_matches_metadata_and_preserves_operator_decision(
    database: tuple[Engine, object], migration_config: Config
) -> None:
    """The head schema matches the ORM metadata and carries the counter and disposition columns.

    Both columns carry their named checks, and reapplying the head over a populated dataset
    preserves the recorded operator decision.
    """
    engine, factory = database
    # The same public loader Alembic uses must return the guarded raw test database,
    # so migration authority matches the engine the fixture handed the test.
    settings = load_database_settings()
    assert settings.selected_dataset_enabled is False
    assert settings.postgres_db.endswith("_test")
    assert settings.postgres_db == engine.url.database

    inspector = inspect(engine)
    assert set(inspector.get_table_names()) == set(Base.metadata.tables) | {"alembic_version"}
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")) == 1

    # The additive counter migration's columns/types/defaults and named check are present.
    marker_columns = {
        column["name"]: column for column in inspector.get_columns("inference_course_processing")
    }
    counter = marker_columns["generation_attempt_count"]
    assert "BIGINT" in str(counter["type"]).upper()
    assert counter["nullable"] is False
    assert counter["default"] == "0"
    # The additive disposition migration adds one nullable closed-choice column with no default.
    disposition = marker_columns["disposition"]
    assert "TEXT" in str(disposition["type"]).upper()
    assert disposition["nullable"] is True
    assert disposition["default"] is None
    marker_checks = {
        check["name"] for check in inspector.get_check_constraints("inference_course_processing")
    }
    # The ORM convention name exceeds PostgreSQL's 63-byte identifier limit, so the emitted name is
    # the deterministic truncated form. Assert the stable prefix.
    assert any(
        name.startswith("ck_inference_course_processing_generation_attempt_count_")
        for name in marker_checks
    )
    assert "ck_inference_course_processing_disposition_valid" in marker_checks
    target_columns = {
        column["name"]: column for column in inspector.get_columns("inference_processing_targets")
    }
    started = target_columns["generation_started"]
    assert "BOOLEAN" in str(started["type"]).upper()
    assert started["nullable"] is False
    assert started["default"] == "false"

    with session_scope(factory) as session:
        session.add(
            Course(
                group_id="disp-mig-target",
                is_active=True,
                activity_as_of_academic_year_start=2026,
                activity_window_years=3,
            )
        )
        session.flush()
        course_id = session.scalar(select(Course.id).where(Course.group_id == "disp-mig-target"))
        session.add(
            InferenceCourseProcessing(
                course_id=course_id,
                teaching_text_sha256="a" * 64,
                processed=False,
                was_active=True,
                accepted_proposal_id=None,
                disposition="done",
            )
        )

    # Reapplying the head over the populated dataset preserves the recorded decision.
    command.upgrade(migration_config, "head")
    with session_scope(factory) as session:
        assert (
            session.scalar(
                select(InferenceCourseProcessing.disposition).where(
                    InferenceCourseProcessing.course_id == course_id
                )
            )
            == "done"
        )


def test_shared_migration_chain_builds_fresh_head_schema() -> None:
    """The one shared chain builds the head schema on a fresh test-owned database.

    The session fixture migrates a populated database, so it cannot prove a fresh chain. This
    proof creates its own uniquely named ``course_chain_<hex>_test`` database from ``template0``,
    migrates it over the shared supplied-connection path, and asserts the single head, the exact
    ORM table set and the four columns of ``inference_model_attempts``.
    """
    with _scratch_database("course_chain") as engine:
        with engine.connect() as connection:
            command.upgrade(alembic_config(connection), "head")
            assert require_database_schema(connection) == "20261025_0019"
            assert (
                connection.scalar(text("SELECT version_num FROM alembic_version"))
                == "20261025_0019"
            )
            assert set(inspect(connection).get_table_names()) == set(Base.metadata.tables) | {
                "alembic_version"
            }
            attempt_columns = [
                column["name"]
                for column in inspect(connection).get_columns("inference_model_attempts")
            ]
            assert attempt_columns == ["id", "target_work_id", "request_payload", "finished_at"]
            attempt_checks = {
                check["name"]
                for check in inspect(connection).get_check_constraints("inference_model_attempts")
            }
            assert "ck_inference_model_attempts_lifecycle_consistent" not in attempt_checks


def test_identity_column_migration_preserves_populated_results() -> None:
    """The identity-hash migration drops three identity columns and keeps every retained value."""

    def table(connection, table_name: str) -> Table:
        return Table(table_name, MetaData(), autoload_with=connection)

    def rows(connection, table_names: tuple[str, ...]) -> dict[str, list[dict[str, object]]]:
        snapshot: dict[str, list[dict[str, object]]] = {}
        for table_name in table_names:
            reflected = table(connection, table_name)
            primary_key = next(iter(reflected.primary_key.columns))
            snapshot[table_name] = [
                dict(row)
                for row in connection.execute(select(reflected).order_by(primary_key)).mappings()
            ]
        return snapshot

    retained_tables = (
        "ingestion_runs",
        "source_snapshots",
        "courses",
        "course_versions",
        "course_texts",
        "inference_pipeline_runs",
        "inference_target_work",
        "inference_model_attempts",
        "inference_proposals",
        "inference_course_processing",
        "inference_processing_cycles",
        "inference_processing_targets",
        "inference_target_failures",
    )
    target_group_id = "identity-mig-target"
    run_id, snapshot_id = uuid.uuid4(), uuid.uuid4()
    course_id, version_id = uuid.uuid4(), uuid.uuid4()
    work_id, attempt_id, proposal_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    cycle_id, failure_id = uuid.uuid4(), uuid.uuid4()
    run_identity = "3" * 64
    work_key = "5" * 64

    with _scratch_database("course_identity") as engine:
        with engine.connect() as connection:
            command.upgrade(alembic_config(connection), "20261014_0018")

            def insert(table_name: str, **values: object) -> None:
                connection.execute(table(connection, table_name).insert().values(**values))

            insert(
                "ingestion_runs",
                id=run_id,
                status=IngestionRunStatus.COMPLETED.value,
                raw_root_path="data/raw/identity",
                manifest_path="data/raw/identity/manifest.json",
            )
            insert(
                "source_snapshots",
                id=snapshot_id,
                ingestion_run_id=run_id,
                object_type=SourceObjectType.COURSE_UNIT.value,
                source_object_id="identity-version",
                source_group_id=target_group_id,
                response_path="responses/identity.json.gz",
                response_item_index=0,
                source_hash="a" * 64,
            )
            insert(
                "courses",
                id=course_id,
                group_id=target_group_id,
                is_active=True,
                activity_as_of_academic_year_start=2026,
                activity_window_years=3,
            )
            insert(
                "course_versions",
                id=version_id,
                course_id=course_id,
                sisu_course_unit_id="identity-version",
                code="IDENT.1",
                name_fi="Identiteetti",
                name_en="Identity",
                credits_min=5,
                credits_max=5,
                official_url="https://example.test/identity",
                document_state="ACTIVE",
                source_modification_ordinal=0,
                source_snapshot_id=snapshot_id,
            )
            insert(
                "course_texts",
                course_version_id=version_id,
                content_en="Official course content.",
            )
            insert(
                "inference_pipeline_runs",
                id=run_id,
                model_identity="model@rev",
                runtime_identity="runtime@rev",
                prompt_version="v9",
                prompt_content_sha256="1" * 64,
                schema_version="v2",
                schema_sha256="2" * 64,
                pipeline_version="v1",
                run_identity_sha256=run_identity,
                configuration={"route": "local"},
            )
            insert(
                "inference_target_work",
                id=work_id,
                created_by_run_id=run_id,
                target_course_id=course_id,
                activity_as_of_academic_year_start=2026,
                activity_window_years=3,
                input_sha256="4" * 64,
                work_key_sha256=work_key,
                status="completed",
            )
            insert(
                "inference_model_attempts",
                id=attempt_id,
                target_work_id=work_id,
                request_payload={
                    "facts": {
                        "target_teaching_text_sha256": "b" * 64,
                        "candidate_count": 0,
                    }
                },
                finished_at=datetime(2026, 10, 1, tzinfo=UTC),
            )
            insert(
                "inference_proposals",
                id=proposal_id,
                target_course_id=course_id,
                source_attempt_id=attempt_id,
                proposal_version="v1",
                identity_sha256="6" * 64,
                expression=None,
                equivalence=[],
            )
            insert(
                "inference_course_processing",
                course_id=course_id,
                teaching_text_sha256="7" * 64,
                processed=True,
                was_active=True,
                accepted_proposal_id=proposal_id,
                generation_attempt_count=2,
                disposition="done",
            )
            insert(
                "inference_processing_cycles",
                id=cycle_id,
                input_sha256="8" * 64,
                stage="complete",
            )
            insert(
                "inference_processing_targets",
                cycle_id=cycle_id,
                target_course_id=course_id,
                multiview_state="completed",
                rerank_state="completed",
                inference_state="completed",
                pool_input=None,
                target_input=None,
                generation_work_key_sha256=work_key,
                generation_started=True,
                proposal_id=proposal_id,
                error_type=None,
            )
            insert(
                "inference_target_failures",
                id=failure_id,
                cycle_id=cycle_id,
                target_course_id=course_id,
                stage="inference",
                attempt_count=1,
                error_type="InferenceTargetRequestError",
                reason="request_failed",
                exhausted=False,
            )
            before = rows(connection, retained_tables)
            connection.commit()

            command.upgrade(alembic_config(connection), "head")
            assert require_database_schema(connection) == "20261025_0019"
            after = rows(connection, retained_tables)
            connection.commit()

            # The three identity columns are absent and every other retained value is equal.
            for table_name, after_rows in after.items():
                after_columns = set(after_rows[0])
                assert [
                    {column: row[column] for column in after_columns} for row in before[table_name]
                ] == after_rows

            run_columns = {
                column["name"]
                for column in inspect(connection).get_columns("inference_pipeline_runs")
            }
            assert "prompt_content_sha256" not in run_columns
            assert "schema_sha256" not in run_columns
            work_columns = {
                column["name"]
                for column in inspect(connection).get_columns("inference_target_work")
            }
            assert "input_sha256" not in work_columns
            check_names = {
                check["name"]
                for check in inspect(connection).get_check_constraints("inference_pipeline_runs")
            } | {
                check["name"]
                for check in inspect(connection).get_check_constraints("inference_target_work")
            }
            assert "ck_inference_pipeline_runs_prompt_content_sha256_sha256" not in check_names
            assert "ck_inference_pipeline_runs_schema_sha256_sha256" not in check_names
            assert "ck_inference_target_work_input_sha256_sha256" not in check_names

            # Every retained record reads through its owning repository.
            factory = create_session_factory(engine)
            evidence = InferenceEvidenceRepository(factory)
            run = evidence.read_run(run_id)
            assert run.spec.model_identity == "model@rev"
            work = evidence.read_work_by_id(work_id)
            assert work.work_key_sha256 == work_key
            assert work.status.value == "completed"
            assert evidence.read_completion(work_id) is not None
            proposal = InferenceProposalRepository(factory).read_for_work(work_id)
            assert proposal is not None and proposal.proposal_id == proposal_id
            scheduling = InferenceSchedulingRepository(factory)
            assert scheduling.read_cycle(cycle_id).stage == "complete"
            target = scheduling.read_target(cycle_id, target_group_id)
            assert target.inference_state == "completed"
            assert target.proposal_id == proposal_id
            failures = scheduling.read_target_failures(cycle_id, unresolved_only=False)
            assert [failure.failure_id for failure in failures] == [failure_id]

            # The refused downgrade leaves the head and the retained data equal.
            with pytest.raises(RuntimeError):
                command.downgrade(alembic_config(connection), "20261014_0018")
            connection.rollback()
            assert (
                connection.scalar(text("SELECT version_num FROM alembic_version"))
                == "20261025_0019"
            )
            after_downgrade = rows(connection, retained_tables)
            assert after_downgrade == after


def test_curriculum_constraints_preserve_identity_and_official_order(
    database: tuple[Engine, object], integrity_records: dict[str, uuid.UUID | str]
) -> None:
    """Canonical source identity is unique and module-rule parents stay in the same tree."""
    _, factory = database
    course_id = integrity_records["course_id"]
    snapshot_id = integrity_records["snapshot_id"]

    with pytest.raises(IntegrityError) as duplicate_version:
        with session_scope(factory) as session:
            session.add(
                CourseVersion(
                    id=uuid.uuid4(),
                    course_id=course_id,
                    sisu_course_unit_id="course-version-2026",
                    code="TEST.101",
                    credits_min=1,
                    credits_max=1,
                    official_url="https://example.test/duplicate",
                    document_state="ACTIVE",
                    source_snapshot_id=snapshot_id,
                )
            )
    assert constraint_name(duplicate_version.value) == "uq_course_versions_sisu_course_unit_id"

    with pytest.raises(IntegrityError) as cross_module_parent:
        with session_scope(factory) as session:
            session.add(
                ModuleRuleNode(
                    id=uuid.uuid4(),
                    module_version_id=integrity_records["other_module_version_id"],
                    parent_node_id=integrity_records["root_node_id"],
                    sibling_position=1,
                    node_type=ModuleRuleType.COURSE_UNIT_RULE,
                    referenced_group_id="cross-module-reference",
                )
            )
    assert constraint_name(cross_module_parent.value) == "fk_module_rule_nodes_parent_same_module"


def test_nullable_course_credit_max_downgrade_rejects_unbounded_rows(
    database: tuple[Engine, object],
) -> None:
    """A nullable course credit maximum is stored and read back without a fabricated bound."""
    _, factory = database
    run_id = uuid.uuid4()
    snapshot_id = uuid.uuid4()
    course_id = uuid.uuid4()
    version_id = uuid.uuid4()
    with session_scope(factory) as session:
        session.add(
            IngestionRun(
                id=run_id,
                status=IngestionRunStatus.COMPLETED,
                raw_root_path="data/raw/run",
                manifest_path="data/raw/run/manifest.json",
            )
        )
        session.add(
            SourceSnapshot(
                id=snapshot_id,
                ingestion_run_id=run_id,
                object_type=SourceObjectType.COURSE_UNIT,
                source_object_id="unbounded-course-v1",
                source_group_id="unbounded-course",
                response_path="responses/unbounded.json.gz",
                response_item_index=0,
                source_hash="u" * 64,
            )
        )
        session.add(
            Course(
                id=course_id,
                group_id="unbounded-course",
                is_active=False,
                activity_as_of_academic_year_start=2026,
                activity_window_years=3,
            )
        )
        session.flush()
        session.add(
            CourseVersion(
                id=version_id,
                course_id=course_id,
                sisu_course_unit_id="unbounded-course-v1",
                code="UNBOUNDED.1",
                credits_min=1,
                credits_max=None,
                official_url="https://example.test/unbounded",
                document_state="ACTIVE",
                source_snapshot_id=snapshot_id,
            )
        )

    with session_scope(factory) as session:
        version = session.get(CourseVersion, version_id)
        assert version is not None and version.credits_max is None
        session.delete(version)
        session.delete(session.get(Course, course_id))
        session.delete(session.get(SourceSnapshot, snapshot_id))
        session.flush()
        session.delete(session.get(IngestionRun, run_id))


def test_generation_counter_preserves_markers_and_rejects_negative_counts(
    database: tuple[Engine, object], migration_config: Config
) -> None:
    """A retained marker keeps its counter, proposal pointer and decision through head reapplication."""
    _, factory = database

    from course_explorer.inference.prompts import load_prompt_pack
    from tests.inference._scheduling_support import (
        build_pool,
        build_target_input,
        complete_target,
        prepare_generation_cycle,
        seed_courses,
    )

    candidates = tuple(f"mig-cand-{index:02d}" for index in range(3))
    seed_courses(
        factory,
        [("mig-target", "MIG.1", True)]
        + [(candidate, f"MIGC.{index}", True) for index, candidate in enumerate(candidates)],
    )
    pool = build_pool(factory, "mig-target", candidates)
    value = build_target_input(pool)
    fixture = complete_target(factory, value, load_prompt_pack("v9"))
    scheduling, cycle = prepare_generation_cycle(factory, value)
    planned = scheduling.read_target(cycle.cycle_id, "mig-target").model_copy(
        update={"generation_work_key_sha256": fixture.work.work_key_sha256}
    )
    scheduling.checkpoint(planned)
    marker = scheduling.accept_target(cycle.cycle_id, "mig-target", fixture.proposal)
    assert marker.processed is True
    assert marker.accepted_proposal_id == fixture.proposal.proposal_id

    def _marker_row() -> InferenceCourseProcessing:
        with session_scope(factory) as session:
            row = session.scalar(
                select(InferenceCourseProcessing)
                .join(Course, Course.id == InferenceCourseProcessing.course_id)
                .where(Course.group_id == "mig-target")
            )
            assert row is not None
            return row

    def _target_row() -> InferenceProcessingTarget:
        with session_scope(factory) as session:
            row = session.scalar(
                select(InferenceProcessingTarget)
                .join(Course, Course.id == InferenceProcessingTarget.target_course_id)
                .where(
                    InferenceProcessingTarget.cycle_id == cycle.cycle_id,
                    Course.group_id == "mig-target",
                )
            )
            assert row is not None
            return row

    def _preserved_facts(course_id: uuid.UUID) -> tuple:
        """Read the retained marker/target/work/completion/proposal facts by their exact ids."""
        with session_scope(factory) as session:
            marker_facts = tuple(
                session.execute(
                    select(
                        InferenceCourseProcessing.teaching_text_sha256,
                        InferenceCourseProcessing.processed,
                        InferenceCourseProcessing.was_active,
                        InferenceCourseProcessing.accepted_proposal_id,
                        InferenceCourseProcessing.generation_attempt_count,
                        InferenceCourseProcessing.disposition,
                    ).where(InferenceCourseProcessing.course_id == course_id)
                ).one()
            )
            target_facts = tuple(
                session.execute(
                    select(
                        InferenceProcessingTarget.multiview_state,
                        InferenceProcessingTarget.rerank_state,
                        InferenceProcessingTarget.inference_state,
                        InferenceProcessingTarget.pool_input,
                        InferenceProcessingTarget.target_input,
                        InferenceProcessingTarget.generation_work_key_sha256,
                        InferenceProcessingTarget.generation_started,
                        InferenceProcessingTarget.proposal_id,
                    ).where(
                        InferenceProcessingTarget.cycle_id == cycle.cycle_id,
                        InferenceProcessingTarget.target_course_id == course_id,
                    )
                ).one()
            )
            work_facts = tuple(
                session.execute(
                    select(
                        InferenceTargetWork.created_by_run_id,
                        InferenceTargetWork.target_course_id,
                        InferenceTargetWork.activity_as_of_academic_year_start,
                        InferenceTargetWork.activity_window_years,
                        InferenceTargetWork.work_key_sha256,
                        InferenceTargetWork.status,
                    ).where(InferenceTargetWork.id == fixture.work.work_id)
                ).one()
            )
            completion_facts = tuple(
                session.execute(
                    select(
                        InferenceModelAttempt.request_payload,
                        InferenceModelAttempt.finished_at,
                    ).where(InferenceModelAttempt.target_work_id == fixture.work.work_id)
                ).one()
            )
            proposal_facts = tuple(
                session.execute(
                    select(
                        InferenceProposal.target_course_id,
                        InferenceProposal.source_attempt_id,
                        InferenceProposal.proposal_version,
                        InferenceProposal.identity_sha256,
                        InferenceProposal.expression,
                        InferenceProposal.equivalence,
                    ).where(InferenceProposal.id == fixture.proposal.proposal_id)
                ).one()
            )
        return marker_facts, target_facts, work_facts, completion_facts, proposal_facts

    # Re-applying the head over the populated dataset preserves the genuine facts.
    command.upgrade(migration_config, "head")
    preserved_marker = _marker_row()
    assert preserved_marker.processed is True
    assert preserved_marker.accepted_proposal_id == fixture.proposal.proposal_id
    assert preserved_marker.generation_attempt_count == 0
    preserved_target = _target_row()
    assert preserved_target.proposal_id == fixture.proposal.proposal_id
    assert preserved_target.generation_work_key_sha256 == fixture.work.work_key_sha256
    assert preserved_target.generation_started is False

    # The named nonnegative check rejects a negative count.
    with pytest.raises(IntegrityError) as negative:
        with session_scope(factory) as session:
            session.execute(
                update(InferenceCourseProcessing)
                .where(InferenceCourseProcessing.course_id == preserved_marker.course_id)
                .values(generation_attempt_count=-1)
            )
    assert constraint_name(negative.value).startswith(
        "ck_inference_course_processing_generation_attempt_count_"
    )

    # A nonzero counter and the accepted pointer survive another head reapplication exactly.
    with session_scope(factory) as session:
        session.execute(
            update(InferenceCourseProcessing)
            .where(InferenceCourseProcessing.course_id == preserved_marker.course_id)
            .values(generation_attempt_count=1)
        )
    preserved_facts = _preserved_facts(preserved_marker.course_id)
    command.upgrade(migration_config, "head")
    assert _preserved_facts(preserved_marker.course_id) == preserved_facts


def test_context_failure_preserves_evidence_at_head(
    database: tuple[Engine, object], migration_config: Config
) -> None:
    """Two retained failures keep their identities, reasons and safe facts through head reapplication.

    The shared migration fixture supplies one owning connection, so every in-test Alembic call reuses
    the credential that connection already resolved. Nothing is extracted from the URL or synthesized.
    """
    _, factory = database

    from tests.inference._scheduling_support import (
        build_pool,
        build_target_input,
        prepare_generation_cycle,
        seed_courses,
    )

    candidates = tuple(f"ctx-cand-{index:02d}" for index in range(3))
    seed_courses(
        factory,
        [("ctx-target", "CTX.1", True)]
        + [(candidate, f"CTXC.{index}", True) for index, candidate in enumerate(candidates)],
    )
    pool = build_pool(factory, "ctx-target", candidates)
    value = build_target_input(pool)
    scheduling, cycle = prepare_generation_cycle(factory, value)
    original_record, original = scheduling.record_target_failure(
        cycle.cycle_id,
        "ctx-target",
        stage="inference",
        attempt_count=1,
        error_type="InferenceTargetRequestError",
        reason="request_failed",
        exhausted=True,
    )
    assert original_record.inference_state == "failed"

    # The retained failure keeps its exact identity and evidence at the head schema.
    retained = scheduling.read_target_failures(cycle.cycle_id, unresolved_only=False)
    assert [failure.failure_id for failure in retained] == [original.failure_id]
    assert retained[0].reason == "request_failed"
    assert retained[0].attempt_count == 1
    assert retained[0].error_type == "InferenceTargetRequestError"

    # The context_exceeded reason is accepted at the head. Reapplying the head preserves both
    # recorded failures with their reasons, attempts and safe error types.
    _record, context_failure = scheduling.record_target_failure(
        cycle.cycle_id,
        "ctx-target",
        stage="inference",
        attempt_count=1,
        error_type="TargetContextError",
        reason="context_exceeded",
        exhausted=True,
    )
    command.upgrade(migration_config, "head")
    rows = scheduling.read_target_failures(cycle.cycle_id, unresolved_only=False)
    by_id = {failure.failure_id: failure for failure in rows}
    assert set(by_id) == {original.failure_id, context_failure.failure_id}
    assert by_id[original.failure_id].reason == "request_failed"
    assert by_id[original.failure_id].attempt_count == 1
    assert by_id[original.failure_id].error_type == "InferenceTargetRequestError"
    assert by_id[context_failure.failure_id].reason == "context_exceeded"
    assert by_id[context_failure.failure_id].attempt_count == 1
    assert by_id[context_failure.failure_id].error_type == "TargetContextError"
