"""Dataset-scoped reuse of the immutable raw course and module source facts a graph read returns.

The store retains the exact DTO a curriculum read returned, or the fact that one dataset holds no row
for an identity. It keeps one least-recently-used bound over course and module keys together, never
expires an entry, and serializes access with one lock. One instance belongs to one serving dataset
identity.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from collections.abc import Collection

from course_explorer.curriculum import (
    CatalogueCourse,
    CatalogueModule,
    CurriculumGraphRead,
)


class PrerequisiteSourceFactCache:
    """Bounded least-recently-used store of raw course and module facts for one dataset.

    A retained absence is an entry like a retained row, so a request that asks again for a missing
    identity issues no read. The bound counts course and module keys together.
    """

    def __init__(self, *, max_entries: int) -> None:
        self._max_entries = max_entries
        self._lock = threading.Lock()
        self._entries: OrderedDict[tuple[str, str], object | None] = OrderedDict()

    def get_course(self, group_id: str) -> tuple[bool, CatalogueCourse | None]:
        """Return whether this dataset is known for the identity, and the retained row when present."""
        return self._get("course", group_id)

    def put_course(self, course: CatalogueCourse) -> None:
        """Retain one course row under its canonical identity."""
        self._store(("course", course.group_id), course)

    def mark_course_absent(self, group_id: str) -> None:
        """Retain that this dataset holds no row for one canonical course identity."""
        self._store(("course", group_id), None)

    def get_module(self, group_id: str) -> tuple[bool, CatalogueModule | None]:
        """Return whether this dataset is known for the identity, and the retained row when present."""
        return self._get("module", group_id)

    def put_module(self, module: CatalogueModule) -> None:
        """Retain one module row under its canonical identity."""
        self._store(("module", module.group_id), module)

    def mark_module_absent(self, group_id: str) -> None:
        """Retain that this dataset holds no row for one canonical module identity."""
        self._store(("module", group_id), None)

    def _get(self, kind: str, group_id: str) -> tuple[bool, object | None]:
        """Return one retained entry and touch its recency, or report an unknown identity."""
        key = (kind, group_id)
        with self._lock:
            if key not in self._entries:
                return (False, None)
            self._entries.move_to_end(key)
            return (True, self._entries[key])

    def _store(self, key: tuple[str, str], value: object | None) -> None:
        """Retain one entry as the most recently used and drop the oldest entries above the bound."""
        with self._lock:
            self._entries[key] = value
            self._entries.move_to_end(key)
            while len(self._entries) > self._max_entries:
                self._entries.popitem(last=False)


class ReusingCurriculumGraphRead:
    """Curriculum graph read that answers retained facts and reads each unknown identity once.

    The wrapped read receives only the identities this dataset is not known for. Every returned row is
    retained under its canonical identity, and every requested identity the read did not return is
    retained as absent. Returned rows keep the canonical group order of the request.
    """

    def __init__(self, curriculum: CurriculumGraphRead, cache: PrerequisiteSourceFactCache) -> None:
        self._curriculum = curriculum
        self._cache = cache

    def get_courses(self, group_ids: Collection[str]) -> tuple[CatalogueCourse, ...]:
        """Return the requested present courses, reading the unknown identities once."""
        requested = tuple(sorted(set(group_ids)))
        present: list[CatalogueCourse] = []
        unknown: list[str] = []
        for group_id in requested:
            known, course = self._cache.get_course(group_id)
            if not known:
                unknown.append(group_id)
            elif course is not None:
                present.append(course)
        if not unknown:
            return tuple(sorted(present, key=lambda course: course.group_id))
        read = {course.group_id: course for course in self._curriculum.get_courses(tuple(unknown))}
        for course in read.values():
            self._cache.put_course(course)
            present.append(course)
        for group_id in unknown:
            if group_id not in read:
                self._cache.mark_course_absent(group_id)
        return tuple(sorted(present, key=lambda course: course.group_id))

    def get_modules(self, group_ids: Collection[str]) -> tuple[CatalogueModule, ...]:
        """Return the requested present modules, reading the unknown identities once."""
        requested = tuple(sorted(set(group_ids)))
        present: list[CatalogueModule] = []
        unknown: list[str] = []
        for group_id in requested:
            known, module = self._cache.get_module(group_id)
            if not known:
                unknown.append(group_id)
            elif module is not None:
                present.append(module)
        if not unknown:
            return tuple(sorted(present, key=lambda module: module.group_id))
        read = {module.group_id: module for module in self._curriculum.get_modules(tuple(unknown))}
        for module in read.values():
            self._cache.put_module(module)
            present.append(module)
        for group_id in unknown:
            if group_id not in read:
                self._cache.mark_module_absent(group_id)
        return tuple(sorted(present, key=lambda module: module.group_id))
