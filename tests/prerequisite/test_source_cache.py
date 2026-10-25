"""Public proofs for the dataset-scoped raw prerequisite source-fact reuse."""

from __future__ import annotations

from course_explorer.prerequisite.source_cache import (
    PrerequisiteSourceFactCache,
    ReusingCurriculumGraphRead,
)
from tests.prerequisite._graph_support import (
    FakeCurriculumRead,
    catalogue_course,
    catalogue_module,
)


def test_reusing_graph_read_reuses_rows_and_known_absences_without_a_second_read() -> None:
    """A retained row and a retained absence both answer the next request without a read."""
    wrapped = FakeCurriculumRead(
        (catalogue_course("present"),),
        (catalogue_module("module-present", ()),),
    )
    cache = PrerequisiteSourceFactCache(max_entries=8)
    reader = ReusingCurriculumGraphRead(wrapped, cache)

    assert reader.get_courses(("present", "missing", "present")) == (catalogue_course("present"),)
    assert wrapped.course_reads == [("missing", "present")]
    assert cache.get_course("missing") == (True, None)
    assert reader.get_courses(("missing", "present")) == (catalogue_course("present"),)
    assert wrapped.course_reads == [("missing", "present")]

    assert reader.get_modules(("module-present", "module-missing")) == (
        catalogue_module("module-present", ()),
    )
    assert wrapped.module_reads == [("module-missing", "module-present")]
    assert cache.get_module("module-missing") == (True, None)
    assert reader.get_modules(("module-missing", "module-present")) == (
        catalogue_module("module-present", ()),
    )
    assert wrapped.module_reads == [("module-missing", "module-present")]
