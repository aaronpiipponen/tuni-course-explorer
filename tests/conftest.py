"""Shared disposable-PostgreSQL fixtures for package and schema integration tests.

The session fixture migrates the dedicated ``*_test`` database once at head and truncates it
between tests through the ``database`` fixture. It forces ``SELECTED_DATASET_ENABLED=0`` and asserts
the ``_test`` suffix around the whole fixture lifetime, so the opt-out controls engine creation,
Alembic migration, yielded tests and cleanup.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, Engine

from course_explorer.config import (
    ENVIRONMENT_ONLY_SETTINGS_SOURCE,
    SETTINGS_SOURCE_MARKER,
    DatabaseSettings,
    load_database_settings,
)
from course_explorer.db.models import Base
from course_explorer.db.session import create_database_engine, create_session_factory
from tests.support import _SYNTHETIC_VALUES, public_environment

_DATABASE_SETTINGS_ALIASES = frozenset(
    field.validation_alias
    for field in DatabaseSettings.model_fields.values()
    if isinstance(field.validation_alias, str)
)


@pytest.fixture(autouse=True)
def _file_free_settings_environment(
    monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest
) -> None:
    """Keep ordinary tests file-free while integration tests consume the owning local database.

    An ordinary test receives the tracked public base fixture values and a synthetic
    database password through the process environment, and the environment-only marker stops the
    settings layer from reopening any file. A database integration test instead leaves every
    ``DatabaseSettings`` alias and the environment-only marker alone, so the database settings owner
    composes its normal local configuration for the fixture, snapshot, Compose and local subprocess
    boundaries alike. That credential is consumed only by the owning database operations and is never
    extracted, inspected or copied. Both kinds preserve an already-set process override, inject the
    remaining public aliases, and force the selected-dataset opt-out.
    """
    integration = request.node.get_closest_marker("integration") is not None
    for alias, value in public_environment().items():
        if integration and alias in _DATABASE_SETTINGS_ALIASES:
            continue
        if alias not in os.environ:
            monkeypatch.setenv(alias, value)
    if not integration:
        if "POSTGRES_PASSWORD" not in os.environ:
            monkeypatch.setenv("POSTGRES_PASSWORD", _SYNTHETIC_VALUES["POSTGRES_PASSWORD"])
        monkeypatch.setenv(SETTINGS_SOURCE_MARKER, ENVIRONMENT_ONLY_SETTINGS_SOURCE)
    monkeypatch.setenv("SELECTED_DATASET_ENABLED", "0")


def alembic_config(connection: Connection | None = None) -> Config:
    """Load the repository migration configuration, optionally bound to a caller-owned connection.

    When a connection is supplied it is published on the Alembic config so ``migrations/env.py``
    reuses that exact connection (and its already-resolved credential) instead of loading settings and
    opening its own engine.
    """
    config = Config("alembic.ini")
    if connection is not None:
        config.attributes["connection"] = connection
    return config


def _truncate_database(engine: Engine) -> None:
    """Truncate every mapped table with identity restart, leaving ``alembic_version`` at head."""
    tables = ", ".join(
        engine.dialect.identifier_preparer.quote(table.name)
        for table in Base.metadata.sorted_tables
    )
    if not tables:
        return
    with engine.begin() as connection:
        connection.exec_driver_sql(f"TRUNCATE {tables} RESTART IDENTITY CASCADE")


@pytest.fixture(scope="session")
def _database_session() -> Iterator[tuple[Engine, object]]:
    """Migrate the disposable test database once and yield its engine/factory pair."""
    # Integration tests always target the raw ``*_test`` database, so the opt-out is forced through
    # migration, yielded tests and cleanup.
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setenv("SELECTED_DATASET_ENABLED", "0")
        settings = load_database_settings()
        assert settings.postgres_db.endswith("_test")
        engine = create_database_engine(settings)
        try:
            with engine.connect() as connection:
                command.upgrade(alembic_config(connection), "head")
            _truncate_database(engine)
            yield engine, create_session_factory(engine)
        finally:
            engine.dispose()


@pytest.fixture()
def database(_database_session: tuple[Engine, object]) -> Iterator[tuple[Engine, object]]:
    """Yield the migrated test database pair and truncate it after each test."""
    engine, factory = _database_session
    yield engine, factory
    _truncate_database(engine)


@pytest.fixture()
def migration_config(database: tuple[Engine, object]) -> Iterator[Config]:
    """Yield an Alembic config bound to one caller-owned connection for a migration proof.

    The connection lives for the fixture and closes on exit. No outer transaction is opened, so
    Alembic commits each successful command and rolls back each refused one on its own.
    """
    engine, _ = database
    with engine.connect() as connection:
        yield alembic_config(connection)
