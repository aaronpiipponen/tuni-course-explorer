"""Neutral fixed product constants shared by settings and ORM metadata.

This module owns values that are fixed by the current schema and vector contract rather than
deployment policy, so the settings model and the migration-owned ORM column cannot drift apart.
It is stdlib-only, reads no configuration, performs no I/O, and holds no tunable, path, or secret.
"""

from __future__ import annotations

COURSE_EMBEDDING_DIMENSION = 1024
