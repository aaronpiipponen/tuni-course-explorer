"""One opt-in PostgreSQL proof of partial inference worker publication.

This contract drives the real worker ``run``/``finalize`` entrypoints against a genuine disposable
``*_test`` database. Only the model/selection boundaries and the external process ownership
observation are synthetic: the real scheduling checkpoints, proposal composer, sole cohort publisher
and final inferred store run as-is. It proves that a stop mid-inference publishes the
partial retained result without finishing a cycle or bulk-marking courses, and that a repeat
finalize adds no model work.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest
from sqlalchemy import Engine, func, select

from course_explorer.administration import administrative_json, atomic_write_private_text
from course_explorer.config import (
    load_administrative_dataset_settings,
)
from course_explorer.db.models import (
    InferenceModelAttempt,
    InferenceProposal,
    InferredPrerequisiteSet,
)
from course_explorer.db.session import session_scope
from course_explorer.inference.scheduling_repository import InferenceSchedulingRepository
from course_explorer_admin import mechanics, worker_session
from course_explorer_admin.inference import controller_worker as worker_module
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
from course_explorer_admin.worker_session import publish_worker_control, write_worker_control
from tests.datasets._support import sample_verification
from tests.inference._job_support import CANDIDATES, prepare_job_case
from tests.inference._scheduling_support import reconcile

pytestmark = [
    pytest.mark.integration,
]

SESSION_ID = "0123456789abcdef0123456789abcdef"
REVISION = "a" * 40
INITIAL_ID = "0" * 32


class _Runner:
    """Local process runner for worker checkout validation only."""

    def run(self, argv, *, cwd=None, env=None, stdin_path=None, stdout_path=None, timeout=None):
        import subprocess

        command = tuple(argv)
        output = b""
        if command[:3] == ("git", "branch", "--show-current"):
            output = b"course-search\n"
        elif command[:2] == ("git", "rev-parse"):
            output = (REVISION + "\n").encode()
        elif command[:2] == ("git", "status"):
            output = b""
        return subprocess.CompletedProcess(list(command), 0, stdout=output, stderr=b"")


@pytest.mark.parametrize("with_done_target", [False, True])
def test_partial_worker_publication_preserves_unfinished_cycle_and_real_results(
    database: tuple[Engine, object],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    with_done_target: bool,
) -> None:
    """A stopped partial worker run publishes real retained results without finishing the cycle."""
    engine, factory = database
    # The canonical shell environment already provides every public config file value and the
    # machine-local worker identity. This test only redirects the administrative state root to a
    # unique scratch location and points the raw session-name check at the derived worker DB.

    with monkeypatch.context() as m:
        admin_state = f"data/admin-tests/{uuid.uuid4().hex}"
        m.setenv("ADMIN_STATE_ROOT", admin_state)
        m.setenv("INGESTION_CONTROLLER_STATE_ROOT", f"{admin_state}/ingestion")
        m.setenv("EMBEDDING_CONTROLLER_STATE_ROOT", f"{admin_state}/embedding")
        m.setenv("TRANSLATION_CONTROLLER_STATE_ROOT", f"{admin_state}/translation")
        m.setenv("INFERENCE_CONTROLLER_STATE_ROOT", f"{admin_state}/inference")
        m.setenv("TRANSLATION_CONTROLLER_WORKER_PROJECT_ROOT", str(tmp_path / "worker"))

        _repository, fake_runtime, _boundary = prepare_job_case(
            factory,
            monkeypatch,
            ("inf-t1", "inf-t2", "inf-t3") if with_done_target else ("inf-t1", "inf-t2"),
        )
        if with_done_target:
            # A third target is explicitly disposed done before the worker run. It must contribute
            # complete coverage with no model work, never a measured generation completion.
            reconcile(factory)
            assert (
                InferenceSchedulingRepository(factory)
                .set_target_disposition("inf-t3", "done")
                .disposition
                == "done"
            )
        expected_retained = 2 if with_done_target else 1

        configured = load_administrative_dataset_settings()
        database_name = configured.database_name(SESSION_ID, worker=True)
        session = WorkerDatasetSession(
            schema_version=1,
            session_id=SESSION_ID,
            revision=REVISION,
            branch="course-search",
            database_name=database_name,
            stage="inference",
            source_dataset_id=INITIAL_ID,
            course_limit=None,
            input_snapshot=_snapshot(),
        )
        directory = worker_dataset_session_directory(SESSION_ID)
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        atomic_write_private_text(directory / "session.json", administrative_json(session))
        atomic_write_private_text(
            directory / "policy.json",
            administrative_json(
                InferenceControllerPolicy(
                    schema_version=2,
                    session_id=SESSION_ID,
                    revision=REVISION,
                    configuration_sha256=inference_configuration_sha256(),
                )
            ),
        )
        write_worker_control(
            directory,
            WorkerControl(
                schema_version=1,
                session_id=SESSION_ID,
                revision=REVISION,
                requested_action="run",
            ),
        )
        atomic_write_private_text(
            directory / "state.json",
            administrative_json(
                InferenceControllerWorkerState(
                    schema_version=2,
                    session_id=SESSION_ID,
                    revision=REVISION,
                    lifecycle="prepared",
                    desired_count=None,
                    completed_count=None,
                    active_seconds=0.0,
                )
            ),
        )
        # The explicit test DB boundary: worker engine construction returns the fixture engine, while
        # the raw session-name check runs against the session's derived database name. The
        # shared schema barrier also builds its engine through this owner, so bind it to the same
        # disposable engine and leave the real checker intact.
        m.setenv("POSTGRES_DB", database_name)
        m.setattr(worker_module, "create_database_engine", lambda _settings: engine)
        m.setattr(worker_session, "create_database_engine", lambda _settings: engine)
        m.setattr(worker_module, "WorkerInferenceRuntime", lambda *a, **k: fake_runtime)
        m.setattr(worker_session, "require_worker_checkout", lambda *a, **k: None)

        worker_live = {"value": False}
        real_owned_alive = mechanics.owned_process_is_alive
        own_pid = os.getpid()
        own_argv = mechanics.read_process_command_line(own_pid)

        def scoped_owned_alive(record) -> bool:
            if record.pid == own_pid and tuple(record.argv) == own_argv:
                return worker_live["value"]
            return real_owned_alive(record)

        m.setattr(mechanics, "owned_process_is_alive", scoped_owned_alive)

        real_job = worker_module.run_inference_job

        def wrapping_job(
            factory,
            *,
            runtime,
            before_unit,
            before_request,
            on_checkpoint,
            on_generation_attempt_checkpoint,
            oversize_route,
            clock,
        ):
            def wrapped(progress):
                on_checkpoint(progress)
                if progress.stage == "inference" and progress.measured_stage_completed == 1:
                    publish_worker_control(directory, session, "stop")

            return real_job(
                factory,
                runtime=runtime,
                before_unit=before_unit,
                before_request=before_request,
                on_checkpoint=wrapped,
                on_generation_attempt_checkpoint=on_generation_attempt_checkpoint,
                oversize_route=oversize_route,
                clock=clock,
            )

        m.setattr(worker_module, "run_inference_job", wrapping_job)

        worker_live["value"] = True
        code = worker_session.run_worker_session(
            worker_module.InferenceWorkerStage(), SESSION_ID, runner=_Runner()
        )
        worker_live["value"] = False
        assert code == 0

        repository = InferenceSchedulingRepository(factory)
        cycle = repository.read_cycle(repository.read_coverage().cycle_id)
        assert cycle.stage != "complete"
        assert cycle.stage == "inference"
        coverage = repository.read_coverage()
        assert coverage.retained_complete_targets == expected_retained
        assert coverage.published_targets == (1 if with_done_target else 0)
        assert coverage.operator_done_targets == (1 if with_done_target else 0)
        markers = {record.group_id: record for record in repository.read_processing()}
        assert all(markers[group_id].processed is False for group_id in CANDIDATES)
        with session_scope(factory) as db_session:
            assert db_session.scalar(select(func.count()).select_from(InferenceProposal)) == 1

        # Public finalize publishes the genuine partial cohort through the sole publisher.
        finalized = worker_session.finalize_worker_session(
            worker_module.InferenceWorkerStage(), SESSION_ID, runner=_Runner()
        )
        assert finalized.lifecycle == "imported"
        coverage = repository.read_coverage()
        assert coverage.retained_complete_targets == expected_retained
        assert coverage.published_targets == expected_retained
        assert coverage.operator_done_targets == (1 if with_done_target else 0)
        assert finalized.completed_count == expected_retained
        assert repository.read_cycle(cycle.cycle_id).stage != "complete"
        markers = {record.group_id: record for record in repository.read_processing()}
        assert all(markers[group_id].processed is False for group_id in CANDIDATES)
        with session_scope(factory) as db_session:
            attempts = db_session.scalar(select(func.count()).select_from(InferenceModelAttempt))
            inferred = db_session.scalar(select(func.count()).select_from(InferredPrerequisiteSet))
        assert attempts == 1
        assert inferred == 1

        # A repeated finalize reuses the receipt and adds no model work.
        again = worker_session.finalize_worker_session(
            worker_module.InferenceWorkerStage(), SESSION_ID, runner=_Runner()
        )
        assert again.lifecycle == "imported"
        with session_scope(factory) as db_session:
            assert (
                db_session.scalar(select(func.count()).select_from(InferenceModelAttempt))
                == attempts
            )


def _snapshot():
    from course_explorer.datasets import DatabaseSnapshot

    return DatabaseSnapshot(
        schema_version=1,
        session_id=SESSION_ID,
        revision=REVISION,
        database_name="course_explorer_test",
        dump_sha256="c" * 64,
        verification=sample_verification(),
    )
