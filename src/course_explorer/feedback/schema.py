"""Require the feedback application database to be at the one feedback migration head."""

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Connection

from course_explorer import administration


def require_feedback_schema(connection: Connection) -> str:
    """Return the feedback migration head, or refuse a repository or database that differs.

    The repository must expose exactly one head for the feedback chain. A connection whose current
    heads differ from it, or that carries no version, raises a content-free ``ValueError``.
    """
    repository_heads = ScriptDirectory.from_config(
        Config(str(administration.repository_root() / "alembic_feedback.ini"))
    ).get_heads()
    if len(repository_heads) != 1:
        raise ValueError("feedback migrations must expose exactly one head")
    expected_head = repository_heads[0]
    if MigrationContext.configure(connection).get_current_heads() != (expected_head,):
        raise ValueError("the feedback database is not at its single migration head")
    return expected_head


__all__ = ["require_feedback_schema"]
