"""Sole transaction owner for the shared inference execution, target work and completions.

This repository records one shared execution identity per coarse configuration, one global
matching-work row per canonical target/execution/input identity, and one completion row per
completed generation. It validates every transition against the persisted execution and the live
canonical target activity context read through a ``Course`` projection. Completed matching
work is reused, failed work is visible until retried, and a
completion payload carries the descriptors and uncomposed result only until proposal composition
releases them. It never calculates a target, retrieves candidates, calls a model, publishes a
proposal, or writes official curriculum or final inferred product stores.
"""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from course_explorer.db.models import (
    Course,
    InferenceModelAttempt,
    InferencePipelineRun,
    InferenceTargetWork,
)
from course_explorer.db.session import session_scope
from course_explorer.enums import InferenceWorkStatus
from course_explorer.inference.context import (
    RequestCourseDescriptors,
    resolve_result_codes,
)
from course_explorer.inference.domain import (
    InferenceTargetResultV2,
    target_result_model,
)
from course_explorer.inference.evidence import (
    InferenceCompletionFacts,
    InferenceCompletionPayload,
    InferenceModelAttemptRecord,
    InferencePipelineRunRecord,
    InferencePipelineRunSpec,
    InferenceTargetWorkRecord,
    InferenceTargetWorkRequest,
    InferenceWorkClaim,
    InferenceWorkClaimAction,
    run_identity_sha256,
    work_key_sha256,
)


def _storage_json(value: object) -> object:
    """Convert one evidence value into JSON-native data for JSONB storage.

    Provider-parsed content carries `Decimal` numbers, and the strict target-result JSON schema
    represents confidence as a JSON number rather than text. Integral decimals become JSON
    integers and other finite decimals become JSON numbers so a stored completion keeps the
    numeric JSON document that validated. This never accepts a non-finite or non-JSON value.
    """
    if value is None or isinstance(value, str | bool):
        return value
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("stored evidence must not contain a non-finite number")
        if value == value.to_integral_value():
            return int(value)
        return float(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError("stored evidence must not contain a non-finite number")
        return value
    if isinstance(value, dict):
        for key in value:
            if not isinstance(key, str):
                raise ValueError("stored evidence mapping keys must be strings")
        return {key: _storage_json(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_storage_json(item) for item in value]
    raise ValueError("stored evidence must contain only JSON-compatible values")


def _run_spec_from_row(row: InferencePipelineRun) -> InferencePipelineRunSpec:
    """Rebuild one shared execution spec from its persisted identity columns."""
    return InferencePipelineRunSpec(
        model_identity=row.model_identity,
        runtime_identity=row.runtime_identity,
        prompt_version=row.prompt_version,
        prompt_content_sha256=row.prompt_content_sha256,
        schema_version=row.schema_version,
        schema_sha256=row.schema_sha256,
        pipeline_version=row.pipeline_version,
        configuration=row.configuration,
    )


def _run_record(row: InferencePipelineRun) -> InferencePipelineRunRecord:
    """Map one persisted execution row to the read contract."""
    return InferencePipelineRunRecord(
        run_id=row.id,
        spec=_run_spec_from_row(row),
        run_identity_sha256=row.run_identity_sha256,
    )


def _completion_record(row: InferenceModelAttempt) -> InferenceModelAttemptRecord:
    """Rebuild one completion row from its stored payload."""
    payload = InferenceCompletionPayload.model_validate_json(json.dumps(row.request_payload))
    return InferenceModelAttemptRecord(
        attempt_id=row.id,
        target_work_id=row.target_work_id,
        payload=payload,
        finished_at=row.finished_at,
    )


def _work_record(row: InferenceTargetWork, *, target_group_id: str) -> InferenceTargetWorkRecord:
    """Map one persisted work row plus its canonical target identity to the read contract."""
    return InferenceTargetWorkRecord(
        work_id=row.id,
        created_by_run_id=row.created_by_run_id,
        target_course_id=row.target_course_id,
        request=InferenceTargetWorkRequest(
            target_group_id=target_group_id,
            activity_as_of_academic_year_start=row.activity_as_of_academic_year_start,
            activity_window_years=row.activity_window_years,
            input_sha256=row.input_sha256,
        ),
        work_key_sha256=row.work_key_sha256,
        status=row.status,
    )


class InferenceEvidenceRepository:
    """Create, read, reuse, retry and complete shared inference evidence."""

    def __init__(self, factory: sessionmaker[Session]) -> None:
        self._factory = factory

    def create_run(self, spec: InferencePipelineRunSpec) -> InferencePipelineRunRecord:
        """Select or create the one shared execution matching this coarse identity."""
        target_result_model(spec.schema_version)
        identity = run_identity_sha256(spec)
        with session_scope(self._factory) as session:
            row = session.scalar(
                select(InferencePipelineRun)
                .where(InferencePipelineRun.run_identity_sha256 == identity)
                .with_for_update()
            )
            if row is None:
                row = InferencePipelineRun(
                    model_identity=spec.model_identity,
                    runtime_identity=spec.runtime_identity,
                    prompt_version=spec.prompt_version,
                    prompt_content_sha256=spec.prompt_content_sha256,
                    schema_version=spec.schema_version,
                    schema_sha256=spec.schema_sha256,
                    pipeline_version=spec.pipeline_version,
                    run_identity_sha256=identity,
                    configuration=spec.configuration,
                )
                session.add(row)
                session.flush()
                session.refresh(row)
            return _run_record(row)

    def read_run(self, run_id: UUID) -> InferencePipelineRunRecord:
        """Return one persisted execution or fail clearly for an unknown id."""
        with self._factory() as session:
            row = session.get(InferencePipelineRun, run_id)
            if row is None:
                raise ValueError(f"unknown inference pipeline run {run_id}")
            return _run_record(row)

    def claim_work(self, run_id: UUID, request: InferenceTargetWorkRequest) -> InferenceWorkClaim:
        """Claim or reuse the one global work row matching this target and execution identity."""
        with session_scope(self._factory) as session:
            run = self._locked_execution(session, run_id)
            course_id = self._current_target_course_id(session, request)
            work_key = work_key_sha256(request, run.run_identity_sha256)
            row = session.scalar(
                select(InferenceTargetWork)
                .where(InferenceTargetWork.target_course_id == course_id)
                .where(InferenceTargetWork.work_key_sha256 == work_key)
                .with_for_update()
            )
            if row is None:
                row = InferenceTargetWork(
                    created_by_run_id=run.id,
                    target_course_id=course_id,
                    activity_as_of_academic_year_start=(request.activity_as_of_academic_year_start),
                    activity_window_years=request.activity_window_years,
                    input_sha256=request.input_sha256,
                    work_key_sha256=work_key,
                    status=InferenceWorkStatus.PENDING,
                )
                session.add(row)
                session.flush()
                session.refresh(row)
                return InferenceWorkClaim(
                    action=InferenceWorkClaimAction.CREATED,
                    work=_work_record(row, target_group_id=request.target_group_id),
                )
            action = (
                InferenceWorkClaimAction.REUSED
                if row.status is InferenceWorkStatus.COMPLETED
                else InferenceWorkClaimAction.EXISTING
            )
            target_group_id = self._target_group_id(session, row.target_course_id)
            return InferenceWorkClaim(
                action=action, work=_work_record(row, target_group_id=target_group_id)
            )

    def retry_work(self, run_id: UUID, work_id: UUID) -> InferenceTargetWorkRecord:
        """Reset one failed work row to pending without deleting its completion identity."""
        with session_scope(self._factory) as session:
            self._locked_execution(session, run_id)
            row = session.scalar(
                select(InferenceTargetWork)
                .where(InferenceTargetWork.id == work_id)
                .with_for_update()
            )
            if row is None:
                raise ValueError(f"unknown inference target work {work_id}")
            if row.status is not InferenceWorkStatus.FAILED:
                raise ValueError(f"inference target work {work_id} is not failed")
            target_group_id = self._target_group_id(session, row.target_course_id)
            row.status = InferenceWorkStatus.PENDING
            session.flush()
            session.refresh(row)
            return _work_record(row, target_group_id=target_group_id)

    def fail_work(self, run_id: UUID, work_id: UUID) -> InferenceTargetWorkRecord:
        """Mark one pending work row failed for a real generation request/output failure."""
        with session_scope(self._factory) as session:
            self._locked_execution(session, run_id)
            row = session.scalar(
                select(InferenceTargetWork)
                .where(InferenceTargetWork.id == work_id)
                .with_for_update()
            )
            if row is None:
                raise ValueError(f"unknown inference target work {work_id}")
            if row.status is InferenceWorkStatus.COMPLETED:
                raise ValueError(f"inference target work {work_id} is already completed")
            target_group_id = self._target_group_id(session, row.target_course_id)
            if row.status is InferenceWorkStatus.FAILED:
                return _work_record(row, target_group_id=target_group_id)
            if row.status is not InferenceWorkStatus.PENDING:
                raise ValueError(f"inference target work {work_id} is not pending")
            row.status = InferenceWorkStatus.FAILED
            session.flush()
            session.refresh(row)
            return _work_record(row, target_group_id=target_group_id)

    def record_completion(
        self,
        run_id: UUID,
        work_id: UUID,
        *,
        result: InferenceTargetResultV2,
        descriptors: RequestCourseDescriptors,
        facts: InferenceCompletionFacts,
        finished_at: datetime,
    ) -> InferenceTargetWorkRecord:
        """Validate one untrusted result and atomically write its completion and work status.

        Acceptance is enforced through the shared :func:`resolve_result_codes` before success is
        recorded, so a rejected result raises :class:`TargetResultError` and never becomes completed.
        Completed work is returned as-is.
        """
        resolve_result_codes(result, descriptors)
        stored = {
            "facts": facts.model_dump(mode="json"),
            "descriptors": descriptors.model_dump(mode="json"),
            "result": _storage_json(result.model_dump(mode="python")),
        }
        with session_scope(self._factory) as session:
            self._locked_execution(session, run_id)
            row = session.scalar(
                select(InferenceTargetWork)
                .where(InferenceTargetWork.id == work_id)
                .with_for_update()
            )
            if row is None:
                raise ValueError(f"unknown inference target work {work_id}")
            target_group_id = self._target_group_id(session, row.target_course_id)
            if row.status is InferenceWorkStatus.COMPLETED:
                return _work_record(row, target_group_id=target_group_id)
            if row.status is not InferenceWorkStatus.PENDING:
                raise ValueError(f"inference target work {work_id} is not pending")
            completion = InferenceModelAttempt(
                target_work_id=row.id,
                request_payload=stored,
                finished_at=finished_at,
            )
            session.add(completion)
            row.status = InferenceWorkStatus.COMPLETED
            session.flush()
            session.refresh(row)
            return _work_record(row, target_group_id=target_group_id)

    def read_completion(self, work_id: UUID) -> InferenceModelAttemptRecord | None:
        """Return the one completion row for a work id, or None when absent."""
        with self._factory() as session:
            row = session.scalar(
                select(InferenceModelAttempt).where(InferenceModelAttempt.target_work_id == work_id)
            )
            return None if row is None else _completion_record(row)

    def read_work(self, target_group_id: str, work_key: str) -> InferenceTargetWorkRecord | None:
        """Return retained work by canonical target and work key, or None when absent."""
        if not target_group_id.strip():
            raise ValueError("target_group_id must not be blank")
        with self._factory() as session:
            row = session.scalar(
                select(InferenceTargetWork)
                .join(Course, Course.id == InferenceTargetWork.target_course_id)
                .where(Course.group_id == target_group_id)
                .where(InferenceTargetWork.work_key_sha256 == work_key)
            )
            return None if row is None else _work_record(row, target_group_id=target_group_id)

    def read_work_by_id(self, work_id: UUID) -> InferenceTargetWorkRecord:
        """Return one retained work row by its id, or fail clearly for an unknown id."""
        with self._factory() as session:
            row = session.execute(
                select(InferenceTargetWork, Course.group_id)
                .join(Course, Course.id == InferenceTargetWork.target_course_id)
                .where(InferenceTargetWork.id == work_id)
            ).one_or_none()
            if row is None:
                raise ValueError(f"unknown inference target work {work_id}")
            work, target_group_id = row
            return _work_record(work, target_group_id=target_group_id)

    @staticmethod
    def _locked_execution(session: Session, run_id: UUID) -> InferencePipelineRun:
        """Lock and return one shared execution, rejecting an unknown id."""
        run = session.scalar(
            select(InferencePipelineRun).where(InferencePipelineRun.id == run_id).with_for_update()
        )
        if run is None:
            raise ValueError(f"unknown inference pipeline run {run_id}")
        return run

    @staticmethod
    def _current_target_course_id(session: Session, request: InferenceTargetWorkRequest) -> UUID:
        """Read only the target's identity/activity columns and reject unknown, inactive, stale."""
        row = session.execute(
            select(
                Course.id,
                Course.is_active,
                Course.activity_as_of_academic_year_start,
                Course.activity_window_years,
            ).where(Course.group_id == request.target_group_id)
        ).one_or_none()
        if row is None:
            raise ValueError(f"unknown canonical target course {request.target_group_id}")
        if not row.is_active:
            raise ValueError(f"cannot record work for inactive target {request.target_group_id}")
        if (
            row.activity_as_of_academic_year_start != request.activity_as_of_academic_year_start
            or row.activity_window_years != request.activity_window_years
        ):
            raise ValueError(
                f"work request activity context does not match target {request.target_group_id}"
            )
        return row.id

    @staticmethod
    def _target_group_id(session: Session, course_id: UUID) -> str:
        """Return one canonical target group id for an already-persisted work row."""
        group_id = session.scalar(select(Course.group_id).where(Course.id == course_id))
        if group_id is None:
            raise ValueError(f"inference target work references unknown course {course_id}")
        return group_id
