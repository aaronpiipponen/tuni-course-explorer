"""Alembic environment using course_explorer ORM metadata as schema authority."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection, create_engine, pool

from course_explorer.config import load_database_settings
from course_explorer.db.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations without a live connection using validated settings."""
    settings = load_database_settings()
    context.configure(
        url=settings.sqlalchemy_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def _run_migrations(connection: Connection) -> None:
    """Configure the one shared metadata/transaction path on a caller-owned connection."""
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations on a caller-supplied connection or the configured PostgreSQL database.

    A caller may supply its own connection through ``config.attributes["connection"]``. The
    connection's lifetime and resolved credential are then owned by that caller. Otherwise the
    composed settings resolve the target database on a short-lived NullPool engine.
    """
    supplied = config.attributes.get("connection")
    if supplied is not None:
        _run_migrations(supplied)
        return
    settings = load_database_settings()
    connectable = create_engine(settings.sqlalchemy_url, poolclass=pool.NullPool)

    with connectable.connect() as connection:
        _run_migrations(connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
