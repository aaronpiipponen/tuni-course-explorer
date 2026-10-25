"""Resumable immutable Kori capture, typed reference closure, and replay verification."""

from __future__ import annotations

from collections.abc import Callable, Collection, Iterator, Sequence
from itertools import batched, islice
from typing import Literal, TypeVar, get_args
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from course_explorer.enums import (
    IngestionRunStatus,
    SourceObjectType,
)
from course_explorer.ingestion.manifest import RawCaptureStore
from course_explorer.ingestion.references import (
    SourceReferences,
    extract_course_references,
    extract_module_references,
)
from course_explorer.ingestion.repository import CapturePersistence
from course_explorer.ingestion.source import (
    CurriculumSource,
    KoriModuleType,
    SourceObject,
    SourceResponse,
    SourceVersionRef,
)


class CaptureReport(BaseModel):
    """Operator-visible counts derived from one verified capture manifest."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    status: IngestionRunStatus
    manifest_path: str
    response_count: int
    course_object_count: int
    module_object_count: int
    unresolved_course_group_count: int
    unresolved_module_group_count: int
    selected_period_count: int = Field(ge=0)


_TaggedGroup = tuple[SourceObjectType, str]
_ItemT = TypeVar("_ItemT")

CaptureBoundary = Callable[
    [Literal["verification", "capture", "before_normalization"], int, int | None], bool
]
"""Cooperative lifecycle gate over durable response units.

The callback receives only a stage name plus completed/total response counts; it never receives
captured content, a path, exception text, or source identity. The total is known only while
verifying a manifest. Returning ``False`` means the controller asked to pause or stop
at this durable boundary.
"""


def _report(store: RawCaptureStore) -> CaptureReport:
    object_ids = {
        (record.object_type, record.source_object_id)
        for response in store.manifest.responses
        for record in response.objects
    }
    return CaptureReport(
        run_id=store.manifest.run_id,
        status=store.manifest.status,
        manifest_path=store.manifest_relative_path,
        response_count=len(store.manifest.responses),
        course_object_count=sum(
            object_type is SourceObjectType.COURSE_UNIT for object_type, _ in object_ids
        ),
        module_object_count=sum(
            object_type is SourceObjectType.MODULE for object_type, _ in object_ids
        ),
        unresolved_course_group_count=len(store.manifest.unresolved_course_group_ids),
        unresolved_module_group_count=len(store.manifest.unresolved_module_group_ids),
        selected_period_count=len(store.manifest.periods),
    )


def _boundary_allows(
    on_boundary: CaptureBoundary | None,
    stage: Literal["verification", "capture", "before_normalization"],
    completed: int,
    total: int | None,
) -> bool:
    """Consult the optional lifecycle gate, defaulting to uninterrupted progress."""
    if on_boundary is None:
        return True
    return on_boundary(stage, completed, total)


def _next_controlled_batch(  # noqa: UP047 - shared helper keeps the explicit TypeVar contract
    iterator: Iterator[_ItemT],
    size: int,
    *,
    on_boundary: CaptureBoundary | None,
    completed: int,
) -> tuple[tuple[_ItemT, ...], bool]:
    """Pull one source batch only after the controller allows a request.

    The cooperative gate is consulted immediately before consuming from the iterator, so a pause or
    stop arriving after the previous durable checkpoint is observed before any further source work
    starts. ``((), False)`` means the controller asked to pause or stop. ``((), True)`` means the
    iterator was exhausted normally. Otherwise one batch of at most ``size`` items is returned.
    """
    if not _boundary_allows(on_boundary, "capture", completed, None):
        return (), False
    return tuple(islice(iterator, size)), True


def _record_responses(
    store: RawCaptureStore,
    repository: CapturePersistence,
    responses: Sequence[SourceResponse[tuple[SourceObject, ...]]],
    *,
    object_type: SourceObjectType | None = None,
    unresolved_course_group_ids: Collection[str] | None = None,
    unresolved_module_group_ids: Collection[str] | None = None,
) -> None:
    records = store.checkpoint_responses(
        tuple(
            (
                response.captured,
                object_type,
                response.value if object_type is not None else (),
            )
            for response in responses
        ),
        unresolved_course_group_ids=unresolved_course_group_ids,
        unresolved_module_group_ids=unresolved_module_group_ids,
    )
    repository.register_responses(store.manifest.run_id, records)


def _reconcile_manifest(
    store: RawCaptureStore,
    repository: CapturePersistence,
    *,
    checkpoint_response_count: int,
    verification_start_index: int,
    on_boundary: CaptureBoundary | None,
) -> bool:
    """Repair database provenance only from evidence already verified on disk.

    A same-invocation resume verifies only the envelopes this instance has not checked, while
    a reopened store checks its whole retained prefix. Either way provenance reconciliation then
    runs for the complete manifest in durable batches. ``False`` means the controller asked to
    pause or stop, so nothing further runs this invocation.
    """
    if not store.verify(
        start_response_index=verification_start_index,
        before_response=lambda completed, total: _boundary_allows(
            on_boundary, "verification", completed, total
        ),
    ):
        return False
    repository.ensure_run(store.manifest, store.manifest_relative_path)
    for responses in batched(store.manifest.responses, checkpoint_response_count):
        if not _boundary_allows(on_boundary, "capture", len(store.manifest.responses), None):
            return False
        repository.register_responses(store.manifest.run_id, responses)
    return True


class _CaptureState:
    """Invocation-local accumulator of represented objects and pending typed references.

    It is seeded once from the incoming verified manifest, then updated directly from each
    committed exact/group response, so closure discovery never reconstructs the catalogue.
    """

    def __init__(self) -> None:
        self.represented_ids: set[_TaggedGroup] = set()
        self.known_groups: set[_TaggedGroup] = set()
        self.processed: set[_TaggedGroup] = set()
        self.pending: set[_TaggedGroup] = set()
        self.unresolved_course: set[str] = set()
        self.unresolved_module: set[str] = set()

    def add_references(self, object_type: SourceObjectType, value: SourceObject) -> None:
        """Extract one unique captured object's typed references through the reference helpers."""
        identifier = value.get("id")
        if not isinstance(identifier, str):
            raise ValueError("captured source object ID is not a string")
        key = (object_type, identifier)
        if key in self.processed:
            return
        self.processed.add(key)
        references: SourceReferences = (
            extract_course_references(value)
            if object_type is SourceObjectType.COURSE_UNIT
            else extract_module_references(value)
        )
        self.pending.update(
            (SourceObjectType.COURSE_UNIT, group_id) for group_id in references.course_group_ids
        )
        self.pending.update(
            (SourceObjectType.MODULE, group_id) for group_id in references.module_group_ids
        )

    def observe_object(self, object_type: SourceObjectType, value: SourceObject) -> None:
        """Record one captured object's identity, group, and references."""
        identifier = value.get("id")
        if not isinstance(identifier, str):
            raise ValueError("captured source object ID is not a string")
        group_id = value.get("groupId")
        if isinstance(group_id, str) and group_id.strip():
            self.known_groups.add((object_type, group_id))
        self.represented_ids.add((object_type, identifier))
        self.add_references(object_type, value)

    def observe_group(
        self, object_type: SourceObjectType, group_id: str, values: Sequence[SourceObject]
    ) -> None:
        """Record one fetched group as resolved, or as an empty unresolved reference."""
        if not values:
            if object_type is SourceObjectType.COURSE_UNIT:
                self.unresolved_course.add(group_id)
            else:
                self.unresolved_module.add(group_id)
            return
        self.known_groups.add((object_type, group_id))
        for value in values:
            self.observe_object(object_type, value)


def _seed_capture_state(store: RawCaptureStore) -> _CaptureState:
    """Seed the accumulator once by replaying the incoming verified manifest objects."""
    state = _CaptureState()
    state.unresolved_course = set(store.manifest.unresolved_course_group_ids)
    state.unresolved_module = set(store.manifest.unresolved_module_group_ids)
    for replayed in store.iter_objects():
        record = replayed.record
        state.represented_ids.add((record.object_type, record.source_object_id))
        state.known_groups.add((record.object_type, record.source_group_id))
        state.add_references(record.object_type, replayed.value)
    return state


def _capture_closure(
    source: CurriculumSource,
    store: RawCaptureStore,
    repository: CapturePersistence,
    *,
    state: _CaptureState,
    checkpoint_response_count: int,
    on_boundary: CaptureBoundary | None,
) -> bool:
    """Close typed references breadth-first, committing each fetched group response."""
    while state.pending:
        frontier = tuple(sorted(state.pending, key=lambda item: (item[0].value, item[1])))
        state.pending.clear()
        course_ids = tuple(
            group_id
            for object_type, group_id in frontier
            if object_type is SourceObjectType.COURSE_UNIT
            and (object_type, group_id) not in state.known_groups
            and group_id not in state.unresolved_course
        )
        module_ids = tuple(
            group_id
            for object_type, group_id in frontier
            if object_type is SourceObjectType.MODULE
            and (object_type, group_id) not in state.known_groups
            and group_id not in state.unresolved_module
        )
        for object_type, group_ids, responses in (
            (
                SourceObjectType.COURSE_UNIT,
                course_ids,
                source.iter_course_group_versions(course_ids),
            ),
            (SourceObjectType.MODULE, module_ids, source.iter_module_group_versions(module_ids)),
        ):
            if not group_ids:
                continue
            pairs_iterator = zip(group_ids, responses, strict=True)
            while True:
                pairs, allowed = _next_controlled_batch(
                    pairs_iterator,
                    checkpoint_response_count,
                    on_boundary=on_boundary,
                    completed=len(store.manifest.responses),
                )
                if not allowed:
                    return False
                if not pairs:
                    break
                response_batch = tuple(response for _, response in pairs)
                persisted_course = set(state.unresolved_course)
                persisted_module = set(state.unresolved_module)
                for group_id, response in pairs:
                    if not response.value:
                        if object_type is SourceObjectType.COURSE_UNIT:
                            persisted_course.add(group_id)
                        else:
                            persisted_module.add(group_id)
                _record_responses(
                    store,
                    repository,
                    response_batch,
                    object_type=object_type,
                    unresolved_course_group_ids=persisted_course,
                    unresolved_module_group_ids=persisted_module,
                )
                for group_id, response in pairs:
                    state.observe_group(object_type, group_id, response.value)
                if not _boundary_allows(
                    on_boundary, "capture", len(store.manifest.responses), None
                ):
                    return False
    return True


def _record_reference_batches(
    responses: Iterator[SourceResponse[tuple[SourceVersionRef, ...]]],
    accumulated_ids: set[str],
    store: RawCaptureStore,
    repository: CapturePersistence,
    *,
    checkpoint_response_count: int,
    on_boundary: CaptureBoundary | None,
) -> bool:
    """Record reference-only responses in bounded batches and accumulate every discovered ID."""
    while True:
        batch, allowed = _next_controlled_batch(
            responses,
            checkpoint_response_count,
            on_boundary=on_boundary,
            completed=len(store.manifest.responses),
        )
        if not allowed:
            return False
        if not batch:
            return True
        _record_responses(store, repository, batch)
        if not _boundary_allows(on_boundary, "capture", len(store.manifest.responses), None):
            return False
        for response in batch:
            accumulated_ids.update(ref.id for ref in response.value)


def _discover_catalogue(
    source: CurriculumSource,
    store: RawCaptureStore,
    repository: CapturePersistence,
    *,
    checkpoint_response_count: int,
    on_boundary: CaptureBoundary | None,
) -> tuple[set[str], set[str]] | None:
    """Record periods and course/module version references, returning discovered IDs.

    ``None`` means the controller paused or stopped at a durable boundary. Source discovery is
    fresh on resume.
    """
    if not _boundary_allows(on_boundary, "capture", len(store.manifest.responses), None):
        return None
    periods = source.get_curriculum_periods()
    _record_responses(store, repository, (periods,))
    store.set_periods(periods.value)
    if not _boundary_allows(on_boundary, "capture", len(store.manifest.responses), None):
        return None

    period_ids = tuple(period.id for period in periods.value)
    course_ids: set[str] = set()
    if not _record_reference_batches(
        source.iter_course_version_refs(period_ids),
        course_ids,
        store,
        repository,
        checkpoint_response_count=checkpoint_response_count,
        on_boundary=on_boundary,
    ):
        return None

    module_ids: set[str] = set()
    for module_type in get_args(KoriModuleType):
        if not _record_reference_batches(
            source.iter_module_version_refs(period_ids, module_type),
            module_ids,
            store,
            repository,
            checkpoint_response_count=checkpoint_response_count,
            on_boundary=on_boundary,
        ):
            return None
    return course_ids, module_ids


def _fetch_exact_objects(
    source: CurriculumSource,
    store: RawCaptureStore,
    repository: CapturePersistence,
    state: _CaptureState,
    *,
    object_type: SourceObjectType,
    missing_ids: Sequence[str],
    checkpoint_response_count: int,
    on_boundary: CaptureBoundary | None,
) -> bool:
    """Fetch missing exact versions in bounded batches and observe each committed response."""
    if not missing_ids:
        return True
    responses = (
        source.iter_course_versions(missing_ids)
        if object_type is SourceObjectType.COURSE_UNIT
        else source.iter_module_versions(missing_ids)
    )
    while True:
        batch, allowed = _next_controlled_batch(
            responses,
            checkpoint_response_count,
            on_boundary=on_boundary,
            completed=len(store.manifest.responses),
        )
        if not allowed:
            return False
        if not batch:
            break
        _record_responses(store, repository, batch, object_type=object_type)
        for response in batch:
            for value in response.value:
                state.observe_object(object_type, value)
        if not _boundary_allows(on_boundary, "capture", len(store.manifest.responses), None):
            return False
    return True


def capture_curriculum(
    source: CurriculumSource,
    store: RawCaptureStore,
    repository: CapturePersistence,
    *,
    checkpoint_response_count: int,
    verification_start_index: int = 0,
    on_boundary: CaptureBoundary | None = None,
) -> CaptureReport | None:
    """Capture source evidence, close typed references, and reconcile its provenance.

    ``None`` means the controller paused or stopped at a durable boundary: the manifest holds
    whatever running/failed state it reached after the last committed checkpoint and is never
    relabelled as a source failure. The one exception is the completed-manifest checkpoint
    published after ``mark_completed()`` and matching provenance: rejecting that checkpoint
    returns ``None`` with completed manifest bytes plus matching provenance committed, so the
    next ordinary start continues into normalization instead of losing the final identity. Real
    source, evidence, or database errors mark the manifest failed.
    """
    if checkpoint_response_count < 1:
        raise ValueError("checkpoint response count must be at least 1")
    incoming_response_count = len(store.manifest.responses)
    try:
        if not _reconcile_manifest(
            store,
            repository,
            checkpoint_response_count=checkpoint_response_count,
            verification_start_index=verification_start_index,
            on_boundary=on_boundary,
        ):
            return None
        if store.manifest.status is IngestionRunStatus.COMPLETED:
            repository.verify_run(store.manifest, store.manifest_relative_path)
            return _report(store)
        # Seed from the manifest that ``_reconcile_manifest`` verified, before the
        # failed-to-running transition invalidates that invocation-local verified snapshot.
        state = _seed_capture_state(store)
        store.mark_running()
        repository.ensure_run(store.manifest, store.manifest_relative_path)

        discovered = _discover_catalogue(
            source,
            store,
            repository,
            checkpoint_response_count=checkpoint_response_count,
            on_boundary=on_boundary,
        )
        if discovered is None:
            return None
        course_ids, module_ids = discovered

        represented_course_ids = {
            identifier
            for object_type, identifier in state.represented_ids
            if object_type is SourceObjectType.COURSE_UNIT
        }
        represented_module_ids = {
            identifier
            for object_type, identifier in state.represented_ids
            if object_type is SourceObjectType.MODULE
        }
        missing_course_ids = sorted(course_ids - represented_course_ids)
        if not _fetch_exact_objects(
            source,
            store,
            repository,
            state,
            object_type=SourceObjectType.COURSE_UNIT,
            missing_ids=missing_course_ids,
            checkpoint_response_count=checkpoint_response_count,
            on_boundary=on_boundary,
        ):
            return None
        missing_module_ids = sorted(module_ids - represented_module_ids)
        if not _fetch_exact_objects(
            source,
            store,
            repository,
            state,
            object_type=SourceObjectType.MODULE,
            missing_ids=missing_module_ids,
            checkpoint_response_count=checkpoint_response_count,
            on_boundary=on_boundary,
        ):
            return None

        if not _capture_closure(
            source,
            store,
            repository,
            state=state,
            checkpoint_response_count=checkpoint_response_count,
            on_boundary=on_boundary,
        ):
            return None
        if not store.verify(
            start_response_index=incoming_response_count,
            before_response=lambda completed, total: _boundary_allows(
                on_boundary, "verification", completed, total
            ),
        ):
            return None
        store.mark_completed()
        repository.ensure_run(store.manifest, store.manifest_relative_path)
        # Completion rewrites the manifest bytes and publishes matching completed provenance, so
        # this is a distinct durable checkpoint before the completed-directory final-set check.
        # A pause/stop observed here must record the completed manifest identity. The shorter final
        # verification below only re-runs the directory/orphan/final-set block.
        if not _boundary_allows(on_boundary, "capture", len(store.manifest.responses), None):
            return None
        if not store.verify(
            start_response_index=len(store.manifest.responses),
            before_response=lambda completed, total: _boundary_allows(
                on_boundary, "verification", completed, total
            ),
        ):
            return None
        repository.verify_run(store.manifest, store.manifest_relative_path)
        return _report(store)
    except Exception as original_error:
        if store.manifest.status is IngestionRunStatus.COMPLETED:
            raise
        try:
            store.mark_failed(original_error)
            repository.ensure_run(store.manifest, store.manifest_relative_path)
        except Exception as persistence_error:
            raise ExceptionGroup(
                "capture and failure-state persistence failed", [original_error, persistence_error]
            ) from original_error
        raise
