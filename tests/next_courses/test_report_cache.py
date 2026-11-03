"""Cache contract for repeated canonical and raw next-course reports in the shared region."""

from __future__ import annotations

import os

from course_explorer.next_courses.commands import NextCoursesReport
from course_explorer.next_courses.report_cache import (
    NextCourseRawKey,
    NextCourseReportCache,
    NextCourseReportKey,
)
from course_explorer.next_courses.service import NextCourseMode
from course_explorer.prerequisite.commands import PrerequisiteCalculationBasis
from course_explorer.search.lookup import DisplayLanguage


def _report(key: NextCourseReportKey) -> NextCoursesReport:
    return NextCoursesReport(
        selected_group_ids=key.selected_group_ids,
        completed_group_ids=key.completed_group_ids,
        basis=key.basis,
        mode=key.mode,
        display_language=key.display_language,
        include_inferred=key.include_inferred,
        active_only=key.active_only,
        results=(),
    )


def _key(
    *,
    mode: NextCourseMode = NextCourseMode.ALL,
    language: DisplayLanguage = "en",
    selected: tuple[str, ...] = ("a", "b"),
) -> NextCourseReportKey:
    return NextCourseReportKey(
        selected_group_ids=selected,
        completed_group_ids=("a",),
        basis=PrerequisiteCalculationBasis.COMPLETED,
        mode=mode,
        display_language=language,
        include_inferred=False,
        active_only=True,
    )


def _raw(
    *,
    mode: NextCourseMode = NextCourseMode.ALL,
    language: DisplayLanguage = "en",
    selected: tuple[str, ...] = ("A.1", "B.1"),
) -> NextCourseRawKey:
    return NextCourseRawKey(
        selected_inputs=selected,
        completed_inputs=("A.1",),
        basis=PrerequisiteCalculationBasis.COMPLETED,
        mode=mode,
        display_language=language,
        include_inferred=False,
        active_only=True,
    )


def _forked(check) -> bool:
    """Run one check in a forked child and return whether the child observed it."""
    pid = os.fork()
    if pid == 0:
        os._exit(0 if check() else 1)
    _pid, status = os.waitpid(pid, 0)
    return os.waitstatus_to_exitcode(status) == 0


def test_report_cache_separates_key_inputs_and_is_shared_across_forked_processes() -> None:
    """Each key answers its own request and both cache directions cross a fork."""
    cache = NextCourseReportCache.create(64 * 1024)
    try:
        all_key = _key()
        one_key = _key(mode=NextCourseMode.AT_LEAST_ONE)
        cache.put_raw(_raw(), all_key, _report(all_key))
        cache.put_raw(_raw(mode=NextCourseMode.AT_LEAST_ONE), one_key, _report(one_key))

        assert cache.get_raw(_raw()) is not None
        assert cache.get_raw(_raw(mode=NextCourseMode.AT_LEAST_ONE)) is not None
        assert cache.get_raw(_raw(language="fi")) is None
        assert cache.get_raw(_raw(selected=("A.1", "B.1", "C.1"))) is None
        assert cache.get(_key()) is not None
        assert cache.get(_key(mode=NextCourseMode.AT_LEAST_ONE)) is not None

        child_key = _key(language="fi")
        assert _forked(
            lambda: (
                cache.put_raw(_raw(language="fi"), child_key, _report(child_key)),
                cache.get_raw(_raw(language="fi")) is not None,
            )[1]
        )
        assert cache.get_raw(_raw(language="fi")) is not None

        parent_key = _key(selected=("c", "d"))
        cache.put_raw(_raw(selected=("C.1", "D.1")), parent_key, _report(parent_key))
        assert _forked(lambda: cache.get_raw(_raw(selected=("C.1", "D.1"))) is not None)

        for index in range(200):
            key = _key(selected=(f"course-{index}",))
            cache.put_raw(_raw(selected=(f"COURSE-{index}",)), key, _report(key))
        newest = _key(selected=("course-199",))
        assert cache.get(newest) is not None
        assert cache.get(_key()) is None
    finally:
        cache.close()
