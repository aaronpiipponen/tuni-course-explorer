"""Shared test-owned PostgreSQL database lifetime for disposable ``_test`` application schemas.

One caller receives an engine connected to a uniquely named database created from ``template0``
and the database is dropped when the caller finishes. The raw settings must name a disposable
``_test`` database, so no live application database can be reached.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine

from course_explorer.config import load_raw_database_settings
from course_explorer.db.session import create_database_engine

_PREFIX = re.compile(r"[a-z][a-z0-9_]*")


@contextmanager
def scratch_database(prefix: str) -> Iterator[Engine]:
    """Create one uniquely named test-owned database and drop it after the caller finishes.

    ``prefix`` names the database and must be lowercase letters, digits or underscores. The raw
    settings must name a disposable ``_test`` database and no selected dataset. The database is
    created through one administration connection to ``postgres``, and the yielded engine connects
    to the new database alone. Both engines are disposed even when creating or dropping the database
    fails.
    """
    if _PREFIX.fullmatch(prefix) is None:
        raise ValueError("scratch database prefix must be lowercase letters, digits or underscores")
    raw = load_raw_database_settings()
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
