"""SQLAlchemy engine and transaction ownership for course_explorer persistence.

This module is the one product owner of database resource lifetimes: every command and report
that opens a short-lived engine resolves its settings elsewhere and holds them through
:func:`database_context`, while :func:`session_scope` keeps the commit/rollback contract. It reads
no environment implicitly and invents no state location.
"""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from course_explorer.config import DatabaseSettings


def create_database_engine(settings: DatabaseSettings) -> Engine:
    """Create a SQLAlchemy 2 engine from validated database settings."""
    return create_engine(settings.sqlalchemy_url, pool_pre_ping=True)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create sessions that retain loaded state after successful commits."""
    return sessionmaker(bind=engine, expire_on_commit=False)


@contextmanager
def database_context(settings: DatabaseSettings) -> Iterator[sessionmaker[Session]]:
    """Create one session factory and dispose its engine on every command exit."""
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
