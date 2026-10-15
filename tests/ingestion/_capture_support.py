"""Shared source-shaped fixtures and persistence doubles for the capture tests."""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from course_explorer.ingestion.manifest import RawCaptureStore
from course_explorer.ingestion.repository import CapturePersistence
from course_explorer.ingestion.source import (
    CapturedResponse,
    CurriculumPeriodRef,
    SourceObject,
    SourceResponse,
    SourceVersionRef,
)

FIXTURE_ROOT = Path(__file__).parents[1] / "fixtures" / "kori" / "capture"


def fixture(name: str) -> bytes:
    """Load exact compact source fixture bytes."""
    return (FIXTURE_ROOT / name).read_bytes()


def parsed(name: str) -> Any:
    return json.loads(fixture(name))


class FixtureSource:
    """One deterministic source-shaped fixture provider with optional one-shot failure."""

    def __init__(self, *, fail_method: str | None = None):
        self.fail_method = fail_method
        self.failed = False
        self.calls: list[tuple[str, Any]] = []

    def _response(
        self,
        method: str,
        path: str,
        params: tuple[tuple[str, str], ...],
        name: str,
        value: Any,
        *,
        log_value: Any = None,
    ):
        self.calls.append((method, value if log_value is None else log_value))
        if self.fail_method == method and not self.failed:
            self.failed = True
            raise FixtureFailure(method)
        return SourceResponse(CapturedResponse(path, params, fixture(name)), value)

    def get_curriculum_periods(self) -> SourceResponse[tuple[CurriculumPeriodRef, ...]]:
        return self._response(
            "periods",
            "/api/curriculum-periods",
            (("universityOrgId", "university"),),
            "periods.json",
            (CurriculumPeriodRef("period-2026", 2026),),
        )

    def iter_course_version_refs(
        self, period_ids: tuple[str, ...]
    ) -> Iterator[SourceResponse[tuple[SourceVersionRef, ...]]]:
        yield self._response(
            "course_search",
            "/api/course-unit-search",
            (("curriculumPeriodId", period_ids[0]), ("start", "0"), ("limit", "100")),
            "course-search.json",
            (
                SourceVersionRef("course-a-v1", "course-group-a", (period_ids[0],)),
                SourceVersionRef("course-b-v1", "course-group-b", (period_ids[0],)),
            ),
        )

    def iter_module_version_refs(
        self, period_ids: tuple[str, ...], module_type: str
    ) -> Iterator[SourceResponse[tuple[SourceVersionRef, ...]]]:
        name = "degree-search.json" if module_type == "DegreeProgramme" else "study-search.json"
        value = (
            ()
            if module_type == "DegreeProgramme"
            else (SourceVersionRef("module-direct-v1", "module-group-direct", (period_ids[0],)),)
        )
        yield self._response(
            "degree_search" if module_type == "DegreeProgramme" else "study_search",
            "/api/module-search",
            (("curriculumPeriodId", period_ids[0]), ("moduleType", module_type)),
            name,
            value,
        )

    def iter_course_versions(
        self, ids: tuple[str, ...]
    ) -> Iterator[SourceResponse[tuple[SourceObject, ...]]]:
        self.calls.append(("course_exact", ids))
        if self.fail_method == "course_exact" and not self.failed:
            self.failed = True
            raise FixtureFailure("course_exact")
        values = tuple(value for value in parsed("exact-courses.json") if value["id"] in set(ids))
        body = (json.dumps(values, separators=(",", ":")) + "\n").encode()
        yield SourceResponse(
            CapturedResponse(
                "/api/course-units",
                tuple(("id", identifier) for identifier in ids),
                body,
            ),
            values,
        )

    def iter_module_versions(
        self, ids: tuple[str, ...]
    ) -> Iterator[SourceResponse[tuple[SourceObject, ...]]]:
        self.calls.append(("module_exact", ids))
        if self.fail_method == "module_exact" and not self.failed:
            self.failed = True
            raise FixtureFailure("module_exact")
        values = tuple(value for value in parsed("exact-modules.json") if value["id"] in set(ids))
        body = (json.dumps(values, separators=(",", ":")) + "\n").encode()
        yield SourceResponse(
            CapturedResponse(
                "/api/modules",
                tuple(("id", identifier) for identifier in ids),
                body,
            ),
            values,
        )

    def get_course_group_versions(self, group_id: str) -> SourceResponse[tuple[SourceObject, ...]]:
        names = {
            "course-group-ref": "course-group-ref.json",
            "course-group-ref-2": "course-group-ref-2.json",
        }
        name = names.get(group_id, "empty.json")
        return self._response(
            "course_group",
            "/api/course-units",
            (("groupId", group_id),),
            name,
            tuple(parsed(name)),
            log_value=group_id,
        )

    def get_module_group_versions(self, group_id: str) -> SourceResponse[tuple[SourceObject, ...]]:
        name = "module-group-cycle.json" if group_id == "module-group-cycle" else "empty.json"
        return self._response(
            "module_group",
            "/api/modules/by-group-id",
            (("groupId", group_id),),
            name,
            tuple(parsed(name)),
            log_value=group_id,
        )

    def iter_course_group_versions(
        self, group_ids: tuple[str, ...]
    ) -> Iterator[SourceResponse[tuple[SourceObject, ...]]]:
        for group_id in group_ids:
            yield self.get_course_group_versions(group_id)

    def iter_module_group_versions(
        self, group_ids: tuple[str, ...]
    ) -> Iterator[SourceResponse[tuple[SourceObject, ...]]]:
        for group_id in group_ids:
            yield self.get_module_group_versions(group_id)


class FixtureFailure(RuntimeError):
    """Fixture source interruption."""


class RecordingCapturePersistence(CapturePersistence):
    """Recording persistence double for service tests.

    It records the calls it receives, so service tests assert public behavior without
    re-implementing the repository's provenance reconciliation. Provenance repair is proved
    against PostgreSQL in the capture-repository tests.
    """

    def __init__(self):
        self.register_calls: list[int] = []

    def register_responses(self, run_id: UUID, responses) -> None:
        self.register_calls.append(len(responses))


def new_store(tmp_path: Path) -> RawCaptureStore:
    return RawCaptureStore.create(
        tmp_path / "raw",
        run_id=uuid4(),
        started_at=datetime(2026, 9, 10, 12, 0, 0, tzinfo=UTC),
    )


class PersistenceFailure(RuntimeError):
    """Failure-state persistence interruption."""


class FailingPersistence(RecordingCapturePersistence):
    """Persistence double that fails while reconciling the terminal failure state."""

    def __init__(self):
        super().__init__()
        self.ensure_calls = 0

    def ensure_run(self, manifest, manifest_path: str) -> None:
        self.ensure_calls += 1
        if self.ensure_calls == 3:
            raise PersistenceFailure
        super().ensure_run(manifest, manifest_path)
