"""One-shot import of the authored fictional served mock curriculum and its bundled vectors.

This is the offline adapter behind ``scripts/mock_data.py``. It represents the authored fixture
bytes through the ``RawCaptureStore``
and registers them exactly like a completed capture, reuses the real normalization repository,
parser, embedding reconciliation and worker readiness owners, and stores the fixture curriculum
and its bundled vectors.

The fixture is authored fiction: it occupies the source layer of an entirely fictional dataset and
is never presented as university data. The ``load-curriculum``, ``load`` and
``write-artifacts`` actions are the supported actions. Both the loader and the artifact writer prepare the fixture
through one shared helper and then apply the same projected fixture-identity guard at their entry:
foreign or changed retained curriculum fails before any database provenance/normalized write and
before any fixture-bundle or hub output file is touched, and the writer computes both hub means
before its first output mutation.
"""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from pathlib import Path
from typing import Literal

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, TypeAdapter, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from course_explorer.config import (
    EmbeddingRuntimeSettings,
    NormalizationSettings,
    load_embedding_runtime_settings,
    load_normalization_settings,
    load_raw_database_settings,
)
from course_explorer.constants import COURSE_EMBEDDING_DIMENSION
from course_explorer.curriculum_repository import CurriculumRepository
from course_explorer.datasets import require_database_schema
from course_explorer.db.models import Course, Module, SourceSnapshot
from course_explorer.db.session import database_context
from course_explorer.embeddings.generation import (
    CourseEmbeddingChunkInput,
    CourseEmbeddingCoverageReport,
    CourseEmbeddingResult,
    build_course_embedding_chunks,
    embedding_configuration_sha256,
)
from course_explorer.embeddings.hub import mean_unit_vectors
from course_explorer.embeddings.read import TeachingEmbeddingRepository
from course_explorer.embeddings.repository import CourseEmbeddingRepository
from course_explorer.enums import (
    IngestionRunStatus,
    SourceObjectType,
    TeachingTextField,
    TeachingTextLanguage,
)
from course_explorer.hashing import json_sha256, parse_strict_json
from course_explorer.ingestion.manifest import (
    CapturedResponseRecord,
    RawCaptureStore,
    discover_capture_manifests,
)
from course_explorer.ingestion.normalization import (
    NormalizationBatch,
    NormalizationReport,
    parse_capture,
)
from course_explorer.ingestion.normalization_repository import NormalizationRepository
from course_explorer.ingestion.repository import CaptureRepository
from course_explorer.ingestion.source import CapturedResponse, CurriculumPeriodRef
from course_explorer.teaching_text.repository import DerivedTranslationRepository
from course_explorer.teaching_text.service import TeachingTextService
from course_explorer.validation import require_sha256

# Explicit request parameters marking these captured envelopes as authored fixture input rather
# than a fetched response. They participate in the content-addressed request identity.
_FIXTURE_REQUEST_PARAMS: tuple[tuple[str, str], ...] = (("fixture", "fictional"),)
_BUNDLE_NAME = "embeddings.json"
_CATALOGUE_HUB_NAME = "embedding-hub.json"
_OUTCOMES_HUB_NAME = "embedding-outcomes-hub.json"

_ANY_HTTP_URL_ADAPTER = TypeAdapter(AnyHttpUrl)

MockDataAction = Literal["load-curriculum", "load", "write-artifacts"]


class _MockModel(BaseModel):
    """Frozen, closed DTO base for this adapter's fixture/bundle boundaries."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class _MockEmbeddingChunk(_MockModel):
    """One bundled fixture chunk vector keyed by its exact teaching-text chunk identity."""

    group_id: str
    field: TeachingTextField
    language: TeachingTextLanguage
    chunk_index: int = Field(ge=0)
    embedding: tuple[float, ...]

    @field_validator("group_id")
    @classmethod
    def reject_blank_group_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("bundled chunk group_id must not be blank")
        return value

    @field_validator("embedding")
    @classmethod
    def validate_embedding(cls, value: tuple[float, ...]) -> tuple[float, ...]:
        """Require one finite vector at the fixed embedding dimension."""
        if len(value) != COURSE_EMBEDDING_DIMENSION:
            raise ValueError(
                f"bundled chunk embedding must have exactly {COURSE_EMBEDDING_DIMENSION} components"
            )
        if any(not math.isfinite(component) for component in value):
            raise ValueError("bundled chunk embedding components must be finite")
        return value


class _MockEmbeddingBundle(_MockModel):
    """The one closed bundled-vector artifact: its coarse input identity and its chunks."""

    input_sha256: str
    chunks: tuple[_MockEmbeddingChunk, ...]

    @field_validator("input_sha256")
    @classmethod
    def validate_input_sha256(cls, value: str) -> str:
        return require_sha256(value, "bundled embeddings input_sha256")


def _read_fixture_json(fixture_dir: Path, name: str) -> object:
    """Read one authored fixture document with strict JSON validation."""
    try:
        raw = (fixture_dir / name).read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"mock fixture file is not readable: {name}") from exc
    try:
        return parse_strict_json(raw)
    except ValueError as exc:
        raise ValueError(f"mock fixture file is not valid JSON: {name}") from exc


def _require_object_list(value: object, name: str) -> tuple[dict[str, object], ...]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ValueError(f"mock fixture {name} must be a JSON list of objects")
    return tuple(value)


def _fixture_response_inputs(
    fixture_dir: Path,
) -> tuple[tuple[CapturedResponse, SourceObjectType | None, tuple[object, ...]], ...]:
    """Build the three authored source-shaped envelope inputs in fixed representative order."""
    periods_body = (fixture_dir / "periods.json").read_bytes()
    courses_body = (fixture_dir / "courses.json").read_bytes()
    modules_body = (fixture_dir / "modules.json").read_bytes()
    courses = _require_object_list(_read_fixture_json(fixture_dir, "courses.json"), "courses.json")
    modules = _require_object_list(_read_fixture_json(fixture_dir, "modules.json"), "modules.json")
    return (
        (
            CapturedResponse("/api/curriculum-periods", _FIXTURE_REQUEST_PARAMS, periods_body),
            None,
            (),
        ),
        (
            CapturedResponse("/api/course-units", _FIXTURE_REQUEST_PARAMS, courses_body),
            SourceObjectType.COURSE_UNIT,
            tuple(courses),
        ),
        (
            CapturedResponse("/api/modules", _FIXTURE_REQUEST_PARAMS, modules_body),
            SourceObjectType.MODULE,
            tuple(modules),
        ),
    )


def _fixture_periods(fixture_dir: Path) -> tuple[CurriculumPeriodRef, ...]:
    """Return the fixture's explicit period selection with its authored academic-year starts."""
    values = _require_object_list(_read_fixture_json(fixture_dir, "periods.json"), "periods.json")
    selected: list[CurriculumPeriodRef] = []
    for value in values:
        identifier = value.get("id")
        active = value.get("activePeriod")
        if not isinstance(identifier, str) or not isinstance(active, dict):
            raise ValueError("mock fixture period must carry an id and an activePeriod object")
        start_date = active.get("startDate")
        if not isinstance(start_date, str) or len(start_date) < 4 or not start_date[:4].isdigit():
            raise ValueError("mock fixture period must carry an explicit startDate year")
        selected.append(CurriculumPeriodRef(id=identifier, academic_year_start=int(start_date[:4])))
    if not selected:
        raise ValueError("mock fixture must select at least one curriculum period")
    return tuple(selected)


def _mock_store(raw_root: Path) -> RawCaptureStore:
    """Reuse the sole retained mock import manifest or create the first one."""
    manifests = discover_capture_manifests(raw_root)
    if len(manifests) > 1:
        raise ValueError("multiple mock import manifests are ambiguous")
    if manifests:
        return RawCaptureStore.open(raw_root, manifests[0])
    return RawCaptureStore.create(raw_root)


def _require_reused_mock_inputs(
    store: RawCaptureStore,
    inputs: tuple[tuple[CapturedResponse, SourceObjectType | None, tuple[object, ...]], ...],
) -> None:
    """Compare a retained completed capture's response bodies with the current fixture once."""
    expected = {
        (captured.request_path, captured.request_params): captured.body for captured, _, _ in inputs
    }
    replayed = tuple(store.iter_responses())
    if len(replayed) != len(expected):
        raise ValueError("retained mock import manifest does not match the current fixture")
    for response in replayed:
        key = (response.record.request_path, response.record.request_params)
        if expected.get(key) != response.body:
            raise ValueError("retained mock import manifest does not match the current fixture")


def _checkpoint_mock_capture(
    store: RawCaptureStore,
    inputs: tuple[tuple[CapturedResponse, SourceObjectType | None, tuple[object, ...]], ...],
    periods: tuple[CurriculumPeriodRef, ...],
) -> tuple[CapturedResponseRecord, ...]:
    """Complete the fixture capture once, or verify and reuse the already completed one."""
    if store.manifest.status is IngestionRunStatus.COMPLETED:
        _require_reused_mock_inputs(store, inputs)
        return store.manifest.responses
    if store.manifest.status is IngestionRunStatus.FAILED:
        store.mark_running()
    store.set_periods(periods)
    records = store.checkpoint_responses(inputs)
    store.mark_completed()
    return records


def _fixture_batch(
    store: RawCaptureStore, fixture_dir: Path, normalization: NormalizationSettings
) -> NormalizationBatch:
    """Parse the completed fixture capture, then bind each course to its authored fictional URL."""
    batch = parse_capture(store, course_guide_base_url=normalization.course_guide_base_url)
    urls: dict[str, str] = {}
    for course in _require_object_list(
        _read_fixture_json(fixture_dir, "courses.json"), "courses.json"
    ):
        identifier = course.get("id")
        fictional_url = course.get("fictionalUrl")
        if not isinstance(identifier, str) or not isinstance(fictional_url, str):
            raise ValueError("mock fixture course must carry an id and a fictionalUrl")
        urls[identifier] = str(_ANY_HTTP_URL_ADAPTER.validate_python(fictional_url))
    missing = [
        course.provenance.source_object_id
        for course in batch.courses
        if course.provenance.source_object_id not in urls
    ]
    if missing:
        raise ValueError(f"mock fixture courses have no fictional URL: {sorted(missing)}")
    return batch.model_copy(
        update={
            "courses": tuple(
                course.model_copy(update={"official_url": urls[course.provenance.source_object_id]})
                for course in batch.courses
            )
        }
    )


def _prepare_mock_fixture(
    *,
    fixture_dir: Path,
    raw_root: Path,
    normalization: NormalizationSettings,
) -> tuple[RawCaptureStore, tuple[CapturedResponseRecord, ...], NormalizationBatch]:
    """Prepare the authored fixture capture and parse it into a normalization batch.

    This is the one preparation path the loader and the artifact writer share: it builds the
    fixture response inputs and periods, selects or creates the sole retained capture, completes
    and reuses that capture, then parses it into a normalization batch. It writes no database row,
    so each caller can apply the same projected
    fixture-identity guard before its own database or output work.
    """
    inputs = _fixture_response_inputs(fixture_dir)
    periods = _fixture_periods(fixture_dir)
    store = _mock_store(raw_root)
    records = _checkpoint_mock_capture(store, inputs, periods)
    batch = _fixture_batch(store, fixture_dir, normalization)
    return store, records, batch


def _require_fixture_dataset(factory: sessionmaker[Session], expected: NormalizationBatch) -> None:
    """Refuse a dataset holding anything but this fiction fixture before any database write.

    The guard projects only the canonical group IDs and the retained source identity/hash set, so an
    empty dataset or exactly this fixture's identities may proceed. A foreign or changed retained
    curriculum fails here, before any provenance or normalized row is written. Duplicate identical
    provenance rows collapse by set semantics.
    """
    expected_courses = {course.group_id for course in expected.courses}
    expected_modules = {module.group_id for module in expected.modules}
    expected_snapshots = {
        (
            provenance.object_type,
            provenance.source_object_id,
            provenance.source_group_id,
            provenance.source_hash,
        )
        for provenance in (
            *(course.provenance for course in expected.courses),
            *(module.provenance for module in expected.modules),
        )
    }
    with factory() as session:
        course_groups = set(session.scalars(select(Course.group_id)))
        module_groups = set(session.scalars(select(Module.group_id)))
        snapshots = set(
            session.execute(
                select(
                    SourceSnapshot.object_type,
                    SourceSnapshot.source_object_id,
                    SourceSnapshot.source_group_id,
                    SourceSnapshot.source_hash,
                )
            )
        )
    if not (course_groups or module_groups or snapshots):
        return
    if (
        course_groups != expected_courses
        or module_groups != expected_modules
        or snapshots != expected_snapshots
    ):
        raise ValueError("database already holds curriculum outside the fictional mock fixture")


def load_mock_curriculum(
    factory: sessionmaker[Session],
    *,
    fixture_dir: Path,
    raw_root: Path,
    normalization: NormalizationSettings,
) -> NormalizationReport:
    """Import the authored fictional fixture exactly like one completed capture run."""
    store, records, batch = _prepare_mock_fixture(
        fixture_dir=fixture_dir, raw_root=raw_root, normalization=normalization
    )
    _require_fixture_dataset(factory, batch)
    capture = CaptureRepository(factory)
    capture.ensure_run(store.manifest, store.manifest_relative_path)
    capture.register_responses(store.manifest.run_id, records)
    return NormalizationRepository(factory).apply(
        batch,
        current_academic_year_start=normalization.current_academic_year_start,
        activity_window_years=normalization.active_academic_year_window,
    )


def _bundle_input_sha256(chunks: Sequence[CourseEmbeddingChunkInput]) -> str:
    """Hash the ordered desired chunk identity/provenance dumps excluding the chunk text."""
    payload = sorted(
        (chunk.model_dump(mode="json", exclude={"text"}) for chunk in chunks),
        key=lambda item: (
            item["group_id"],
            item["field"],
            item["language"],
            item["chunk_index"],
        ),
    )
    return json_sha256(payload, ensure_ascii=True)


def _read_bundle(fixture_dir: Path) -> _MockEmbeddingBundle:
    """Read the one bundled-vector artifact through its strict boundary."""
    try:
        raw = (fixture_dir / _BUNDLE_NAME).read_bytes()
    except OSError as exc:
        raise ValueError(f"bundled mock embeddings are not readable: {_BUNDLE_NAME}") from exc
    try:
        parsed = parse_strict_json(raw)
    except ValueError as exc:
        raise ValueError("bundled mock embeddings are not valid JSON") from exc
    if not isinstance(parsed, dict):
        raise ValueError("bundled mock embeddings must be a JSON object")
    try:
        return _MockEmbeddingBundle.model_validate_json(raw, strict=True)
    except ValueError as exc:
        raise ValueError("bundled mock embeddings violate the artifact contract") from exc


def _require_bundle_matches(
    chunks: Sequence[CourseEmbeddingChunkInput], bundle: _MockEmbeddingBundle
) -> None:
    """Require the bundled artifact to name exactly the current fixture's chunk identities."""
    desired = sorted(
        (chunk.group_id, chunk.field, chunk.language, chunk.chunk_index) for chunk in chunks
    )
    bundled = sorted(
        (chunk.group_id, chunk.field, chunk.language, chunk.chunk_index) for chunk in bundle.chunks
    )
    if bundled != desired:
        raise ValueError("bundled mock embeddings do not match the current fixture chunks")
    if bundle.input_sha256 != _bundle_input_sha256(chunks):
        raise ValueError(
            "bundled mock embeddings input identity does not match the current fixture"
        )


def load_mock_embeddings(
    factory: sessionmaker[Session],
    *,
    fixture_dir: Path,
    embedding: EmbeddingRuntimeSettings,
) -> CourseEmbeddingCoverageReport:
    """Import the bundled fixture vectors through the one embedding reconciliation owner."""
    catalogue = TeachingTextService(
        CurriculumRepository(factory), DerivedTranslationRepository(factory)
    ).build_catalogue()
    scope = tuple(catalogue.canonical_group_ids)
    chunks = build_course_embedding_chunks(catalogue, embedding)
    bundle = _read_bundle(fixture_dir)
    _require_bundle_matches(chunks, bundle)
    vectors = {
        (chunk.group_id, chunk.field, chunk.language, chunk.chunk_index): chunk.embedding
        for chunk in bundle.chunks
    }
    repository = CourseEmbeddingRepository(factory)
    reconciliation = repository.reconcile(scope, chunks)
    pending_ids = tuple(pending.row_id for pending in reconciliation.pending)
    if pending_ids:
        keys = repository.read_chunk_keys(pending_ids)
        missing = [row_id for row_id in pending_ids if row_id not in keys]
        if missing:
            raise ValueError("reconciled bundled-vector rows are missing")
        repository.complete(
            tuple(
                CourseEmbeddingResult(row_id=row_id, embedding=vectors[keys[row_id]])
                for row_id in pending_ids
            )
        )
    return repository.coverage(scope)


def _write_json(path: Path, payload: object) -> None:
    """Write one deterministic JSON artifact with a trailing newline."""
    path.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n",
        encoding="utf-8",
    )


def write_mock_artifacts(
    factory: sessionmaker[Session],
    *,
    fixture_dir: Path,
    raw_root: Path,
    normalization: NormalizationSettings,
    embedding: EmbeddingRuntimeSettings,
    hubs_dir: Path,
) -> None:
    """Write the fixture's bundled vectors and both computed hub means from stored vectors.

    This writer is database-read-only. At entry it prepares the named fixture and applies the same
    projected fixture-identity guard the loader uses, so a foreign or changed retained dataset is
    refused before the teaching catalogue is built, vectors are read or any output path is touched.
    Both hub means are then computed from the exact current key set before the first ``_write_json``
    or ``hubs_dir.mkdir``, so a not-ready dataset fails without mutating the fixture bundle or the
    derived hubs. It reads the stored vectors and writes the fixture bundle and both hub files.
    """
    _, _, batch = _prepare_mock_fixture(
        fixture_dir=fixture_dir, raw_root=raw_root, normalization=normalization
    )
    _require_fixture_dataset(factory, batch)
    catalogue = TeachingTextService(
        CurriculumRepository(factory), DerivedTranslationRepository(factory)
    ).build_catalogue()
    chunks = build_course_embedding_chunks(catalogue, embedding)
    repository = CourseEmbeddingRepository(factory)
    repository.require_current_chunks(chunks)
    stored = TeachingEmbeddingRepository(factory).get_chunks(
        CurriculumRepository(factory).list_represented_summaries(),
        embedding_configuration_hash=embedding_configuration_sha256(embedding),
    )
    vectors = {
        (chunk.group_id, chunk.field, chunk.language, chunk.chunk_index): chunk.embedding
        for chunk in stored
    }
    keys = [(chunk.group_id, chunk.field, chunk.language, chunk.chunk_index) for chunk in chunks]
    missing = [key for key in keys if key not in vectors]
    if missing:
        raise ValueError("current compatible fixture vectors are incomplete")
    catalogue_hub = mean_unit_vectors([vectors[key] for key in keys])
    outcomes_hub = mean_unit_vectors(
        [vectors[key] for key in keys if key[1] is TeachingTextField.OUTCOMES]
    )
    _write_json(
        fixture_dir / _BUNDLE_NAME,
        {
            "input_sha256": _bundle_input_sha256(chunks),
            "chunks": [
                {
                    "group_id": key[0],
                    "field": key[1].value,
                    "language": key[2].value,
                    "chunk_index": key[3],
                    "embedding": list(vectors[key]),
                }
                for key in keys
            ],
        },
    )
    hubs_dir.mkdir(parents=True, exist_ok=True)
    _write_json(hubs_dir / _CATALOGUE_HUB_NAME, list(catalogue_hub))
    _write_json(hubs_dir / _OUTCOMES_HUB_NAME, list(outcomes_hub))


def run_mock_data_command(
    action: MockDataAction, *, fixture_dir: Path, raw_root: Path, hubs_dir: Path
) -> BaseModel | None:
    """Run exactly one mock action against the configured database.

    A selected-dataset-enabled configuration is refused before any engine is opened, and the
    single Alembic head is required on the database this command opens.
    """
    if action not in ("load-curriculum", "load", "write-artifacts"):
        raise ValueError(f"unknown mock data action: {action}")
    database = load_raw_database_settings()
    if database.selected_dataset_enabled:
        raise ValueError("mock data import refuses a selected-dataset enabled configuration")
    normalization = load_normalization_settings()
    embedding = load_embedding_runtime_settings()
    with database_context(database) as factory:
        with factory() as session:
            require_database_schema(session.connection())
        if action == "write-artifacts":
            write_mock_artifacts(
                factory,
                fixture_dir=fixture_dir,
                raw_root=raw_root,
                normalization=normalization,
                embedding=embedding,
                hubs_dir=hubs_dir,
            )
            return None
        report = load_mock_curriculum(
            factory, fixture_dir=fixture_dir, raw_root=raw_root, normalization=normalization
        )
        if action == "load":
            return load_mock_embeddings(factory, fixture_dir=fixture_dir, embedding=embedding)
        return report
