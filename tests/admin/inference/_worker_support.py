"""Shared fixtures for the inference worker-session contracts.

This support module owns the deterministic inference settings/environment, the canonical session
and policy seeding, the scripted repository/engine/runtime doubles, and the progress/coverage
helpers the worker feature group drives the real worker entrypoints through.
"""

from __future__ import annotations

import time
from pathlib import Path
from uuid import uuid4

import pytest

from course_explorer.administration import administrative_json, atomic_write_private_text
from course_explorer.config import (
    load_administrative_dataset_settings,
    load_raw_database_settings,
)
from course_explorer.datasets import DatabaseSnapshot
from course_explorer.inference.diagnostics import (
    InferenceCoverageSummary,
    InferenceGenerationCount,
)
from course_explorer.inference.job import InferenceJobProgress
from course_explorer_admin import datasets as datasets_module
from course_explorer_admin import remote, worker_session
from course_explorer_admin.inference.controller import (
    InferenceControllerPolicy,
    InferenceControllerWorkerState,
    inference_configuration_sha256,
)
from course_explorer_admin.remote import (
    WorkerControl,
    WorkerDatasetSession,
    worker_dataset_session_directory,
)
from course_explorer_admin.worker_session import write_worker_control
from tests.config._support import (
    ADMIN_DATASET_KEYS,
    EMBEDDING_KEYS,
    INFERENCE_ALL_KEYS,
    INFERENCE_CONTROLLER_KEYS,
    LOCAL_LIFECYCLE_KEYS,
    POSTGRES_KEYS,
    TRANSLATION_CONTROLLER_KEYS,
    TRANSLATION_KEYS,
)
from tests.datasets._support import sample_verification

SESSION_ID = "0123456789abcdef0123456789abcdef"
REVISION = "a" * 40
INITIAL_ID = "0" * 32


def raw_settings():
    """Build the raw worker database settings pinned to this session's derived worker database."""
    configured = load_administrative_dataset_settings()
    base = load_raw_database_settings()
    return base.model_copy(
        update={
            "selected_dataset_enabled": False,
            "postgres_db": configured.database_name(SESSION_ID, worker=True),
        }
    )


def configure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for key, value in {
        **INFERENCE_ALL_KEYS,
        **INFERENCE_CONTROLLER_KEYS,
        **ADMIN_DATASET_KEYS,
        **LOCAL_LIFECYCLE_KEYS,
        **TRANSLATION_CONTROLLER_KEYS,
        **TRANSLATION_KEYS,
        **EMBEDDING_KEYS,
        **POSTGRES_KEYS,
    }.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("TRANSLATION_CONTROLLER_WORKER_PROJECT_ROOT", str(tmp_path / "worker"))
    monkeypatch.setenv("INFERENCE_CONTROLLER_STATE_ROOT", "state")
    monkeypatch.setenv("ADMIN_STATE_ROOT", "data/admin")
    monkeypatch.setenv("INGESTION_CONTROLLER_STATE_ROOT", "data/admin/ingestion")
    monkeypatch.setenv("EMBEDDING_CONTROLLER_STATE_ROOT", "data/admin/embedding")
    monkeypatch.setenv("TRANSLATION_CONTROLLER_STATE_ROOT", "data/admin/translation")
    monkeypatch.setattr(remote, "repository_root", lambda: tmp_path)
    monkeypatch.setattr(datasets_module, "repository_root", lambda: tmp_path)
    (tmp_path / "data" / "admin").mkdir(mode=0o700, parents=True, exist_ok=True)
    # The real received-database schema barrier opens a database. These network-free contracts
    # stub only its success result, while the disposable SQL proof keeps the real checker.
    monkeypatch.setattr(worker_session, "require_worker_database_schema", lambda session: None)


def session() -> WorkerDatasetSession:
    configured = load_administrative_dataset_settings()
    return WorkerDatasetSession(
        schema_version=1,
        session_id=SESSION_ID,
        database_name=configured.database_name(SESSION_ID, worker=True),
        stage="inference",
        source_dataset_id=INITIAL_ID,
        course_limit=None,
        input_snapshot=DatabaseSnapshot(
            schema_version=1,
            session_id=SESSION_ID,
            database_name="course_explorer",
            dump_sha256="c" * 64,
            verification=sample_verification(),
        ),
    )


def coverage(
    *, eligible: int = 2, retained: int = 1, published: int = 1
) -> InferenceCoverageSummary:
    return InferenceCoverageSummary(
        schema_version=1,
        eligible_targets=eligible,
        retained_complete_targets=retained,
        published_targets=published,
        uncovered_targets=eligible - retained,
        current_equivalence_groups=0,
        historical_proposal_rows=0,
        generation_counts=(
            InferenceGenerationCount(
                model_identity="test-model",
                prompt_version="v9",
                schema_version="v2",
                pipeline_version="v1",
                route="local",
                targets=retained,
            ),
        ),
        cycle_id=None,
        stage=None,
        multiview_completed=0,
        rerank_completed=0,
        rerank_skipped=0,
        inference_completed=0,
        inference_skipped=0,
        failed_targets=0,
        pending_targets=0,
    )


class FakeRunner:
    """Local process runner for the worker runtime-artifact observations."""

    def run(self, argv, *, cwd=None, env=None, stdin_path=None, stdout_path=None, timeout=None):
        import subprocess

        command = tuple(argv)
        output = b""
        if command[:2] == ("git", "rev-parse"):
            output = (REVISION + "\n").encode()
        elif command[:2] == ("git", "status"):
            output = b""
        return subprocess.CompletedProcess(list(command), 0, stdout=output, stderr=b"")


def seed_session(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *, lifecycle: str = "prepared"
) -> Path:
    configure(monkeypatch, tmp_path)
    directory = worker_dataset_session_directory(SESSION_ID)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    atomic_write_private_text(directory / "session.json", administrative_json(session()))
    atomic_write_private_text(
        directory / "policy.json",
        administrative_json(
            InferenceControllerPolicy(
                schema_version=2,
                session_id=SESSION_ID,
                configuration_sha256=inference_configuration_sha256(),
            )
        ),
    )
    write_worker_control(
        directory,
        WorkerControl(
            schema_version=1,
            session_id=SESSION_ID,
            requested_action="run",
        ),
    )
    atomic_write_private_text(
        directory / "state.json",
        administrative_json(
            InferenceControllerWorkerState(
                schema_version=2,
                session_id=SESSION_ID,
                lifecycle=lifecycle,  # type: ignore[arg-type]
                desired_count=None,
                completed_count=None,
                active_seconds=0.0,
                runner_pid=12345 if lifecycle in {"starting", "running"} else None,
            )
        ),
    )
    return directory


class FakeEngine:
    def dispose(self) -> None:
        pass


class FakeRepository:
    def __init__(self, factory) -> None:
        self._factory = factory
        self.coverage = coverage()

    def read_coverage(self) -> InferenceCoverageSummary:
        return self.coverage


class FakeRuntime:
    """Synthetic inference runtime that records protocol calls and request scopes."""

    def __init__(self, runner, *, root, directory, settings, rerank_settings, **kwargs) -> None:
        self.calls: list[str] = []

    def start_rerank(self) -> None:
        self.calls.append("start_rerank")

    def stop_rerank(self) -> None:
        self.calls.append("stop_rerank")

    def activate(self, variant) -> None:  # pragma: no cover, not exercised here
        self.calls.append("activate")

    def active_variant(self):  # pragma: no cover, not exercised here
        return None

    def stop(self) -> None:
        self.calls.append("stop")

    def request_scope(self, seconds: float):
        import contextlib

        self.calls.append("request_scope")
        return contextlib.nullcontext()


def progress(
    stage: str,
    *,
    multiview: int = 0,
    rerank: int = 0,
    inference: int = 0,
    retained: int = 0,
    measured: int = 0,
    desired: int = 2,
    cycle_id=None,
    failed: int = 0,
    multiview_not_remaining: int = 0,
    rerank_not_remaining: int = 0,
    inference_not_remaining: int = 0,
) -> InferenceJobProgress:
    return InferenceJobProgress(
        cycle_id=cycle_id if cycle_id is not None else uuid4(),
        stage=stage,  # type: ignore[arg-type]
        desired_targets=desired,
        multiview_completed=multiview,
        rerank_completed=rerank,
        rerank_skipped=0,
        inference_completed=inference,
        inference_skipped=0,
        failed_targets=failed,
        retained_complete_targets=retained,
        active_stage_seconds=1.0,
        measured_stage_completed=measured,
        multiview_not_remaining=multiview_not_remaining,
        rerank_not_remaining=rerank_not_remaining,
        inference_not_remaining=inference_not_remaining,
    )


class RecordingOwner:
    """Scripted ``OwnedWorkerRuntime`` driving the real ``WorkerInferenceRuntime`` adapter."""

    instances: list[RecordingOwner] = []

    def __init__(self, runner, *, root, directory, sleep=time.sleep, pid: int = 4242):
        self.starts: list[object] = []
        self.stops = 0
        self.pid = pid
        RecordingOwner.instances.append(self)

    def start(self, spec, *, attempts, interval, timeout):
        self.starts.append(spec)
        return self.pid

    def stop(self, *, timeout, interval):
        self.stops += 1
