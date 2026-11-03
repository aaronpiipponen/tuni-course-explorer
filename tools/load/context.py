"""Read the measurement dataset's pool identities, titles, codes, study roots and academic year.

The workload holds the pool as course identities. This module resolves the code and full title of
every pool course, the dataset's module roots, and the configured academic year that selects the
explicit study version. A pool identity with no catalogue row or no title fails the measurement.
"""

from __future__ import annotations

import psycopg

from course_explorer.config import NormalizationSettings, load_normalization_settings

_STUDY_ROOT_LIMIT = 20
_STUDY_ROOTS_WITH_UNAVAILABLE_AVAILABLE = 18
_STUDY_ROOTS_WITH_UNAVAILABLE_UNAVAILABLE = 2


def connect(environment: dict[str, str]) -> psycopg.Connection:
    """Open one read-only connection to the disposable measurement database."""
    return psycopg.connect(
        host=environment["POSTGRES_HOST"],
        port=int(environment["POSTGRES_PORT"]),
        dbname=environment["POSTGRES_DB"],
        user=environment["POSTGRES_USER"],
        password=environment["POSTGRES_PASSWORD"],
        connect_timeout=10,
        autocommit=True,
    )


def _academic_year_start(environment: dict[str, str]) -> int:
    """Return the validated academic-year start that selects the explicit study version.

    ``NormalizationSettings`` requires an activity window and a course-guide address as well, so
    those come from this process's own settings and ``CURRENT_ACADEMIC_YEAR`` comes from
    ``environment``.
    """
    local = load_normalization_settings()
    return NormalizationSettings(
        CURRENT_ACADEMIC_YEAR=environment["CURRENT_ACADEMIC_YEAR"],
        ACTIVE_ACADEMIC_YEAR_WINDOW=local.active_academic_year_window,
        COURSE_GUIDE_BASE_URL=local.course_guide_base_url,
    ).current_academic_year_start


def build_context(environment: dict[str, str], workload: dict) -> dict:
    """Return the pool titles and codes, the study roots and the dataset schema."""
    database = environment["POSTGRES_DB"]
    if not database.endswith("_test"):
        raise ValueError("the payload context database name must end with _test")
    pool = list(workload["pool"])
    academic_year = _academic_year_start(environment)
    with connect(environment) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT DISTINCT ON (c.group_id) c.group_id, cv.code, cv.name_en, cv.name_fi
            FROM courses c
            JOIN course_versions cv ON cv.course_id = c.id
            WHERE c.group_id = ANY(%s)
            ORDER BY c.group_id, cv.created_at DESC, cv.id
            """,
            (pool,),
        )
        rows = cursor.fetchall()
        cursor.execute(
            """
            SELECT DISTINCT m.group_id
            FROM modules m
            JOIN module_versions mv ON mv.module_id = m.id
            JOIN module_version_curriculum_periods p ON p.module_version_id = mv.id
            ORDER BY m.group_id
            """
        )
        available = [row[0] for row in cursor.fetchall()]
        roots = available[:_STUDY_ROOT_LIMIT]
        cursor.execute("SELECT DISTINCT group_id FROM modules ORDER BY group_id")
        all_roots = [row[0] for row in cursor.fetchall()]
        available_set = set(available)
        unavailable = [group_id for group_id in all_roots if group_id not in available_set]
        if len(unavailable) < 2:
            raise RuntimeError(
                "the measurement dataset holds fewer than two unavailable module roots"
            )
        cursor.execute(
            """
            SELECT m.group_id, mv.sisu_module_id
            FROM modules m
            JOIN module_versions mv ON mv.module_id = m.id
            JOIN module_version_curriculum_periods p ON p.module_version_id = mv.id
            JOIN curriculum_periods cp ON cp.id = p.curriculum_period_id
            WHERE cp.academic_year_start = %s
            ORDER BY m.group_id, mv.created_at DESC, mv.id
            LIMIT 1
            """,
            (academic_year,),
        )
        explicit = cursor.fetchone()
        if explicit is None:
            raise RuntimeError(
                "the measurement dataset holds no module version for the current year"
            )
        cursor.execute("SELECT version_num FROM alembic_version")
        schema = cursor.fetchone()[0]
    by_id = {
        group_id: {"code": code, "title_en": name_en, "title_fi": name_fi}
        for group_id, code, name_en, name_fi in rows
    }
    missing = [group_id for group_id in pool if group_id not in by_id]
    if missing:
        raise RuntimeError(f"the workload pool is not in the measurement dataset: {missing}")
    without_title = [
        group_id
        for group_id, values in by_id.items()
        if not (values["title_en"] or values["title_fi"] or values["code"])
    ]
    if without_title:
        raise RuntimeError(f"the pool courses have no query text: {without_title}")
    if not roots:
        raise RuntimeError("the measurement dataset holds no module roots")
    return {
        "dataset": {
            "name": environment["POSTGRES_DB"],
            "schema": schema,
            "course_count": _course_count(environment),
        },
        "pool": by_id,
        "study_roots": roots,
        "study_roots_with_unavailable": (
            available[:_STUDY_ROOTS_WITH_UNAVAILABLE_AVAILABLE]
            + unavailable[:_STUDY_ROOTS_WITH_UNAVAILABLE_UNAVAILABLE]
        ),
        "study_explicit_version": {"group_id": explicit[0], "version": explicit[1]},
    }


def _course_count(environment: dict[str, str]) -> int:
    """Return the measurement dataset's canonical course count."""
    with connect(environment) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM courses")
        return int(cursor.fetchone()[0])
