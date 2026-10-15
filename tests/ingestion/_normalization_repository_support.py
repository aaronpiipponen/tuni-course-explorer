"""Shared capture/read fixtures for the opt-in normalization repository SQL proofs."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from pydantic import AnyHttpUrl, TypeAdapter
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from course_explorer.db.models import Base
from course_explorer.enums import SourceObjectType
from course_explorer.ingestion.manifest import RawCaptureStore
from course_explorer.ingestion.repository import CaptureRepository
from course_explorer.ingestion.source import CapturedResponse, CurriculumPeriodRef
from course_explorer.prerequisite.domain import CurrentEquivalenceGroup, InferredSetReadResult

FIXTURE_ROOT = Path(__file__).parents[1] / "fixtures" / "kori" / "normalization"
GUIDE_URL = TypeAdapter(AnyHttpUrl).validate_python("https://sisu.tuni.fi/student/courseunit")


class _NoInferredSetRead:
    """Test-only inferred read that fails loudly if module compilation consults inference."""

    def read(self, target_group_id: str) -> InferredSetReadResult:
        """Reject any inferred read during inference-disabled module compilation."""
        raise AssertionError("inference-disabled module compilation must not read inferred sets")


class _NoEquivalenceGroupRead:
    """Test-only equivalence read that fails if inference-disabled compilation consults groups."""

    def read_for_member(self, member_group_id: str) -> tuple[CurrentEquivalenceGroup, ...]:
        """Reject any equivalence read during inference-disabled module compilation."""
        raise AssertionError(
            "inference-disabled module compilation must not read equivalence groups"
        )

    def read_for_members(self, member_group_ids) -> dict[str, tuple[CurrentEquivalenceGroup, ...]]:
        """Reject any bulk equivalence read during inference-disabled module compilation."""
        raise AssertionError(
            "inference-disabled module compilation must not read equivalence groups"
        )


def fixture_bytes(name: str) -> bytes:
    """Load exact normalization fixture bytes."""
    return (FIXTURE_ROOT / name).read_bytes()


def fixture_response_inputs(
    courses_body: bytes,
    modules_body: bytes,
    *,
    duplicate_first_course_response: bool = False,
) -> tuple[tuple[CapturedResponse, SourceObjectType | None, tuple[object, ...]], ...]:
    """Build the shared period/course/module captured-response input tuple.

    The tuple uses the exact fixture periods and public ``CapturedResponse`` assembly shared by the
    network-free and PostgreSQL normalization store builders.
    """
    periods_body = fixture_bytes("periods.json")
    course_values = json.loads(courses_body)
    response_inputs: list[tuple[CapturedResponse, SourceObjectType | None, tuple[object, ...]]] = [
        (
            CapturedResponse(
                "/api/curriculum-periods", (("universityOrgId", "fixture"),), periods_body
            ),
            None,
            (),
        ),
        (
            CapturedResponse("/api/course-units", (("id", "fixture-course-batch"),), courses_body),
            SourceObjectType.COURSE_UNIT,
            tuple(course_values),
        ),
        (
            CapturedResponse("/api/modules", (("id", "fixture-module-batch"),), modules_body),
            SourceObjectType.MODULE,
            tuple(json.loads(modules_body)),
        ),
    ]
    if duplicate_first_course_response:
        duplicate_body = json.dumps(
            [course_values[0]], sort_keys=True, separators=(",", ":")
        ).encode()
        response_inputs.append(
            (
                CapturedResponse(
                    "/api/course-units",
                    (("groupId", "duplicate-course-group-a"),),
                    duplicate_body,
                ),
                SourceObjectType.COURSE_UNIT,
                (course_values[0],),
            )
        )
    return tuple(response_inputs)


def build_completed_fixture_store(
    tmp_path: Path,
    repository: CaptureRepository,
    *,
    courses_body: bytes | None = None,
    modules_body: bytes | None = None,
    unresolved_course_group_ids: tuple[str, ...] = (),
    unresolved_module_group_ids: tuple[str, ...] = (),
    duplicate_first_course_response: bool = False,
) -> RawCaptureStore:
    """Build and register one completed capture using real raw/provenance owners."""
    store = RawCaptureStore.create(tmp_path / f"raw-{uuid.uuid4()}", run_id=uuid.uuid4())
    courses_body = fixture_bytes("courses.json") if courses_body is None else courses_body
    modules_body = fixture_bytes("modules.json") if modules_body is None else modules_body
    repository.ensure_run(store.manifest, store.manifest_relative_path)
    records = store.checkpoint_responses(
        fixture_response_inputs(
            courses_body,
            modules_body,
            duplicate_first_course_response=duplicate_first_course_response,
        ),
        unresolved_course_group_ids=unresolved_course_group_ids,
        unresolved_module_group_ids=unresolved_module_group_ids,
    )
    repository.register_responses(store.manifest.run_id, records)
    store.set_periods((CurriculumPeriodRef("period-2026", 2026),))
    store.mark_completed()
    repository.ensure_run(store.manifest, store.manifest_relative_path)
    store.verify()
    repository.verify_run(store.manifest, store.manifest_relative_path)
    return store


def normalized_database_digest(factory: sessionmaker[Session]) -> tuple[tuple[object, ...], ...]:
    """Serialize all normalized tables in stable table/primary-key order."""
    digest: list[tuple[object, ...]] = []
    with factory.begin() as session:
        for table_name in sorted(Base.metadata.tables):
            if table_name in {"ingestion_runs", "source_snapshots"}:
                continue
            table = Base.metadata.tables[table_name]
            rows = session.execute(select(table)).all()
            primary_key_indexes = [column.key for column in table.primary_key.columns]
            rows = sorted(
                rows,
                key=lambda row: tuple(row._mapping[column] for column in primary_key_indexes),
            )
            digest.append((table_name, *tuple(tuple(row) for row in rows)))
    return tuple(digest)
