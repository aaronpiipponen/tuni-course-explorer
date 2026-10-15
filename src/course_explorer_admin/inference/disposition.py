"""Server-only operator disposition of one canonical inference target.

This module is the server administrative surface for an explicit per-target inference decision: it
reads and sets the durable NOTHING/DONE/FAILED choice on the cleanly stopped, verified-returned,
selected dataset through the scheduling repository and sole publication owner. Its guards are
server-local: all four tools idle, a returned selected dataset, and the executing checkout's schema
head.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session, sessionmaker

from course_explorer.config import (
    load_administrative_dataset_settings,
    load_inference_selection_settings,
    load_inference_settings,
    load_raw_database_settings,
)
from course_explorer.curriculum import CourseSummary
from course_explorer.curriculum_repository import CurriculumRepository
from course_explorer.datasets import require_database_schema, resolve_selected_dataset
from course_explorer.db.session import database_context
from course_explorer.inference.publication import publish_current_cohort
from course_explorer.inference.scheduling import TargetDisposition
from course_explorer.inference.scheduling_repository import InferenceSchedulingRepository
from course_explorer.search.lookup import official_display_name
from course_explorer_admin import mechanics
from course_explorer_admin.datasets import admin_state_root, require_stages_idle


class InferenceTargetDisposition(BaseModel):
    """One read-only identity and durable decision report for a single canonical target.

    ``disposition`` is ``None`` for NOTHING (no override/automatic) or one of the two explicit
    terminal choices.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    dataset_id: str
    target_group_id: str
    course_code: str | None
    course_name: str | None
    disposition: TargetDisposition | None


@contextmanager
def _disposition_context(*, mutating: bool) -> Iterator[tuple[str, sessionmaker[Session]]]:
    """Guard and open one selected-dataset context for a read or a decision write.

    It resolves the configured admin state root, holds the shared datasets action lock (read-only
    callers take it without creating anything), requires the selected-dataset switch, a verified returned
    receipt and the schema head, then yields the dataset id and one short-lived session factory bound
    to the selected database.
    """
    settings = load_administrative_dataset_settings()
    root = admin_state_root(settings)
    with mechanics.exclusive_action_lock(root, controller_name="datasets", create=mutating):
        raw = load_raw_database_settings()
        if not raw.selected_dataset_enabled:
            raise ValueError("target disposition requires the selected dataset")
        receipt = resolve_selected_dataset(root)
        if receipt.kind != "returned":
            raise ValueError("target disposition requires a verified returned selected dataset")
        require_stages_idle()
        database = raw.model_copy(update={"postgres_db": receipt.database_name})
        with database_context(database) as factory:
            with factory() as session:
                require_database_schema(session.connection())
            yield receipt.dataset_id, factory


def _resolve_target_summary(factory: sessionmaker[Session], target_group_id: str) -> CourseSummary:
    """Resolve exactly one supplied canonical target to its single active official summary."""
    summaries = CurriculumRepository(factory).get_course_summaries((target_group_id,))
    if len(summaries) != 1 or not summaries[0].is_active:
        raise ValueError(f"target {target_group_id} is not a current active canonical course")
    return summaries[0]


def _report(
    dataset_id: str, summary: CourseSummary, disposition: TargetDisposition | None
) -> InferenceTargetDisposition:
    """Build the one identity-first disposition report from the real summary and decision."""
    return InferenceTargetDisposition(
        dataset_id=dataset_id,
        target_group_id=summary.group_id,
        course_code=summary.code,
        course_name=official_display_name(summary, "en"),
        disposition=disposition,
    )


def read_inference_target_disposition(target_group_id: str) -> InferenceTargetDisposition:
    """Read one canonical target's current durable inference decision without any mutation."""
    with _disposition_context(mutating=False) as (dataset_id, factory):
        summary = _resolve_target_summary(factory, target_group_id)
        marker = InferenceSchedulingRepository(factory).read_target_processing(target_group_id)
        return _report(dataset_id, summary, marker.disposition)


def set_inference_target_disposition(
    target_group_id: str, disposition: TargetDisposition | None
) -> InferenceTargetDisposition:
    """Set one canonical target's decision and publish the resulting current cohort once.

    The decision is committed by the scheduling repository first, so a publication failure leaves the
    durable choice for an idempotent repeat. An identical set runs the publisher, so a failed
    publication is repaired idempotently. The repository decision and eligibility persist across a
    repeat.
    """
    with _disposition_context(mutating=True) as (dataset_id, factory):
        summary = _resolve_target_summary(factory, target_group_id)
        repository = InferenceSchedulingRepository(factory)
        marker = repository.set_target_disposition(target_group_id, disposition)
        publish_current_cohort(
            factory,
            repository.read_publication_cohort(),
            load_inference_settings(),
            load_inference_selection_settings(),
        )
        return _report(dataset_id, summary, marker.disposition)


__all__ = [
    "InferenceTargetDisposition",
    "read_inference_target_disposition",
    "set_inference_target_disposition",
]
