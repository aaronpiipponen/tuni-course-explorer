"""SQLAlchemy engine and transaction ownership for course_explorer persistence.

This module is the one product owner of database resource lifetimes: every command and report
that opens a short-lived engine resolves its settings elsewhere and holds them through
:func:`database_context`, while :func:`session_scope` keeps the commit/rollback contract. A caller
that owns a longer-lived factory supplies it to :func:`database_context` and keeps its engine. It
reads no environment implicitly and invents no state location. A settings value exposes the
connection URL of the database it names, so one engine lifetime serves the curriculum store and the
separate feedback application store alike.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Protocol

from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session, sessionmaker


class DatabaseConnectionSettings(Protocol):
    """Settings value that names one application database by its connection URL."""

    @property
    def sqlalchemy_url(self) -> URL:
        """Return the connection URL of the database the settings value names."""
        ...


def create_database_engine(settings: DatabaseConnectionSettings) -> Engine:
    """Create a SQLAlchemy 2 engine from validated database settings."""
    return create_engine(settings.sqlalchemy_url, pool_pre_ping=True)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create sessions that retain loaded state after successful commits."""
    return sessionmaker(bind=engine, expire_on_commit=False)


@contextmanager
def database_context(
    settings: DatabaseConnectionSettings,
    *,
    factory: sessionmaker[Session] | None = None,
) -> Iterator[sessionmaker[Session]]:
    """Yield one session factory and dispose an engine this context created.

    A supplied factory is yielded as given and never disposed, so its owner keeps the engine's
    lifetime. Without one, this context creates an engine and disposes it on exit.
    """
    if factory is not None:
        yield factory
        return
    engine = create_database_engine(settings)
    try:
        yield create_session_factory(engine)
    finally:
        engine.dispose()


@contextmanager
def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    """Commit successful work and roll back database errors through SQLAlchemy."""
    with factory.begin() as session:
        yield session
