"""Opt-in PostgreSQL proofs for inferred prerequisite and equivalence schema constraints."""

from datetime import UTC, datetime

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, delete, select, text

from course_explorer.db.models import (
    Course,
    InferredPrerequisiteSet,
)
from course_explorer.db.session import session_scope
from course_explorer.enums import (
    InferredCoverageState,
    InferredProducerKind,
)
from course_explorer.prerequisite.domain import (
    AndRequirement,
    CourseRequirement,
    InferredPrerequisiteCategory,
    InferredPublicationAction,
    InferredReadState,
    InferredSetCoverage,
    InferredSetPublication,
    OrRequirement,
    PrerequisiteOrigin,
    dump_prerequisite_expression,
)
from course_explorer.prerequisite.repository import InferredPrerequisiteRepository
from tests.conftest import alembic_config
from tests.db._schema_support import (
    _collect_inferred_categories,
    _pre_category_expression,
    _schema_inferred_metadata,
    _stored_expression,
    _stored_payload_hash,
    inferred_set_row,
    target_course_id,
)

pytestmark = [
    pytest.mark.integration,
]


@pytest.fixture
def database(monkeypatch: pytest.MonkeyPatch):
    """Isolated pre-category database shadowing the root fixture for the historical category proof.

    The irreversible 0014 conversion applies in one direction, so this module proves the historical
    category migration on its own dedicated database upgraded only to the pre-category revision.
    """
    from course_explorer.administration import repository_root
    from course_explorer.config import load_database_settings
    from course_explorer.db.session import create_database_engine, create_session_factory
    from course_explorer_admin import mechanics

    name = "course_category_migration_test"
    assert name.endswith("_test")
    runner = mechanics.SubprocessRunner()
    user = load_database_settings().postgres_user

    def psql_argv(*argv: str) -> tuple[str, ...]:
        return (
            *mechanics.compose_prefix(),
            "exec",
            "-T",
            "db",
            "psql",
            "--username",
            user,
            "--dbname",
            "postgres",
            "--tuples-only",
            "--no-align",
            *argv,
        )

    probe = (
        runner.run(
            psql_argv("--command", f"SELECT count(*) FROM pg_database WHERE datname='{name}'"),
            cwd=repository_root(),
        )
        .stdout.decode()
        .strip()
    )
    if probe != "0":
        raise ValueError("course_category_migration_test already exists")
    runner.run(
        (
            *mechanics.compose_prefix(),
            "exec",
            "-T",
            "db",
            "createdb",
            "--username",
            user,
            "--template",
            "template0",
            name,
        ),
        cwd=repository_root(),
    )
    monkeypatch.setenv("POSTGRES_DB", name)
    monkeypatch.setenv("SELECTED_DATASET_ENABLED", "0")
    engine = create_database_engine(load_database_settings())
    try:
        with engine.connect() as connection:
            command.upgrade(alembic_config(connection), "20260915_0006")
        yield engine, create_session_factory(engine)
    finally:
        engine.dispose()
        runner.run(
            (*mechanics.compose_prefix(), "exec", "-T", "db", "dropdb", "--username", user, name),
            cwd=repository_root(),
        )


def test_inferred_category_migration_preserves_required_semantics_and_hash(
    database: tuple[Engine, object], migration_config: Config, prerequisite_catalogue
) -> None:
    """Pre-category rows migrate to explicit REQUIRED with exact hashes and reversible downgrade."""
    engine, factory = database
    target = prerequisite_catalogue.active_target_group_id
    second_target = prerequisite_catalogue.active_source_group_id

    # One nested pre-category expression is inserted at the pre-category revision with a placeholder
    # hash, so a matching migrated publication can prove the exact canonical hash was rebuilt.
    required_expression = AndRequirement(
        type="and",
        origin=PrerequisiteOrigin.INFERRED,
        inferred_category=InferredPrerequisiteCategory.REQUIRED,
        inference=_schema_inferred_metadata(),
        children=(
            CourseRequirement(
                type="course",
                origin=PrerequisiteOrigin.INFERRED,
                inferred_category=InferredPrerequisiteCategory.REQUIRED,
                course_group_id=second_target,
                inference=_schema_inferred_metadata(),
            ),
            OrRequirement(
                type="or",
                origin=PrerequisiteOrigin.INFERRED,
                inferred_category=InferredPrerequisiteCategory.REQUIRED,
                inference=_schema_inferred_metadata(),
                children=(
                    CourseRequirement(
                        type="course",
                        origin=PrerequisiteOrigin.INFERRED,
                        inferred_category=InferredPrerequisiteCategory.REQUIRED,
                        course_group_id=prerequisite_catalogue.inactive_source_group_id,
                        inference=_schema_inferred_metadata(),
                    ),
                ),
            ),
        ),
    )
    old_expression = _pre_category_expression(dump_prerequisite_expression(required_expression))
    placeholder_hash = "b" * 64

    command.downgrade(migration_config, "20260915_0006")
    with session_scope(factory) as session:
        session.add(
            inferred_set_row(
                target_course_id(factory, target),
                eligible_source_count=2,
                processed_source_count=2,
                accepted_source_count=2,
                expression=old_expression,
                payload_hash=placeholder_hash,
            )
        )
    assert _collect_inferred_categories(_stored_expression(factory, target)) == [
        None,
        None,
        None,
        None,
    ]

    command.upgrade(migration_config, "20260915_0007")
    migrated_expression = _stored_expression(factory, target)
    assert _collect_inferred_categories(migrated_expression) == [
        "required",
        "required",
        "required",
        "required",
    ]
    migrated_hash = _stored_payload_hash(factory, target)
    assert migrated_hash != placeholder_hash

    # The repository read parses every migrated occurrence as explicit REQUIRED, and an equivalent
    # explicitly required publication is identical: the migration recomputed the exact canonical
    # payload hash the sole publication path owns.
    repository = InferredPrerequisiteRepository(factory)
    read_back = repository.read(target)
    assert read_back.state is InferredReadState.CURRENT
    assert read_back.current_set is not None
    assert read_back.current_set.payload_hash == migrated_hash
    assert read_back.current_set.expression == required_expression
    publication = repository.publish(
        InferredSetPublication(
            target_group_id=target,
            activity_as_of_academic_year_start=(
                prerequisite_catalogue.activity_as_of_academic_year_start
            ),
            activity_window_years=prerequisite_catalogue.activity_window_years,
            producer_kind=InferredProducerKind.TEST,
            producer_name="test-fixture",
            producer_version="1",
            input_hash="a" * 64,
            coverage_state=InferredCoverageState.COMPLETE,
            coverage=InferredSetCoverage(
                eligible_source_count=2, processed_source_count=2, accepted_source_count=2
            ),
            expression=required_expression,
            generated_at=datetime(2026, 9, 14, 12, 0, tzinfo=UTC),
        )
    )
    assert publication.action is InferredPublicationAction.UNCHANGED
    assert publication.current_set.payload_hash == migrated_hash

    # Downgrade strips only the category fields and yields the pre-category canonical hash.
    command.downgrade(migration_config, "20260915_0006")
    downgraded_expression = _stored_expression(factory, target)
    assert downgraded_expression == old_expression
    assert _collect_inferred_categories(downgraded_expression) == [None, None, None, None]
    downgraded_hash = _stored_payload_hash(factory, target)
    assert downgraded_hash != migrated_hash
    command.upgrade(migration_config, "20260915_0007")
    assert _stored_payload_hash(factory, target) == migrated_hash

    # A recommended occurrence exists at head: downgrade must refuse the whole pass atomically
    # instead of relabeling a recommendation as required under the old contract.
    recommended_expression = AndRequirement(
        type="and",
        origin=PrerequisiteOrigin.INFERRED,
        inferred_category=InferredPrerequisiteCategory.REQUIRED,
        inference=_schema_inferred_metadata(),
        children=(
            CourseRequirement(
                type="course",
                origin=PrerequisiteOrigin.INFERRED,
                inferred_category=InferredPrerequisiteCategory.RECOMMENDED,
                course_group_id=prerequisite_catalogue.inactive_source_group_id,
                inference=_schema_inferred_metadata(),
            ),
        ),
    )
    repository.publish(
        InferredSetPublication(
            target_group_id=second_target,
            activity_as_of_academic_year_start=(
                prerequisite_catalogue.activity_as_of_academic_year_start
            ),
            activity_window_years=prerequisite_catalogue.activity_window_years,
            producer_kind=InferredProducerKind.TEST,
            producer_name="test-fixture",
            producer_version="1",
            input_hash="a" * 64,
            coverage_state=InferredCoverageState.COMPLETE,
            coverage=InferredSetCoverage(
                eligible_source_count=1, processed_source_count=1, accepted_source_count=1
            ),
            expression=recommended_expression,
            generated_at=datetime(2026, 9, 14, 12, 0, tzinfo=UTC),
        )
    )
    with pytest.raises(ValueError):
        command.downgrade(migration_config, "20260915_0006")

    # The failed downgrade changed nothing: the required row keeps its categories and exact hash,
    # the recommended row keeps its distinction, and the schema is at head.
    assert _collect_inferred_categories(_stored_expression(factory, target)) == [
        "required",
        "required",
        "required",
        "required",
    ]
    assert _stored_payload_hash(factory, target) == migrated_hash
    assert _collect_inferred_categories(_stored_expression(factory, second_target)) == [
        "required",
        "recommended",
    ]
    with engine.begin() as connection:
        head_revision = "20260915_0007"
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == head_revision

    # Remove the test-only recommended row, then prove the remaining all-required state reverses
    # and re-upgrades.
    with session_scope(factory) as session:
        course = session.scalar(select(Course).where(Course.group_id == second_target))
        assert course is not None
        session.execute(
            delete(InferredPrerequisiteSet).where(
                InferredPrerequisiteSet.target_course_id == course.id
            )
        )
    command.downgrade(migration_config, "20260915_0006")
    assert _stored_expression(factory, target) == old_expression
    command.upgrade(migration_config, "20260915_0007")
    assert _stored_payload_hash(factory, target) == migrated_hash
