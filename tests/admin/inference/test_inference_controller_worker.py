"""Inference worker-session contracts.

These contracts drive the public worker entrypoints over synthetic external process/job/runtime
boundaries. They prove that the sole product job receives live control gates and the real runtime
adapter, that checkpoint observations carry the recorded fields, and that interruption/finalize/cleanup
preserve durable authority. They reuse the stage-local fixture owners in ``_worker_support``. The
opt-in ``test_inference_worker_database.py`` proves real SQL persistence.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from course_explorer.administration import administrative_json, atomic_write_private_text
from course_explorer.config import load_inference_settings
from course_explorer_admin import runtime as runtime_module
from course_explorer_admin import worker_session
from course_explorer_admin.inference import controller_worker as worker_module
from course_explorer_admin.inference.controller import InferenceControllerWorkerState
from course_explorer_admin.reboot import WorkerGpuCheckpoint
from course_explorer_admin.remote import WorkerControl
from course_explorer_admin.worker_session import write_worker_control
from tests.admin.inference._worker_support import (
    REVISION,
    SESSION_ID,
    FakeEngine,
    FakeRepository,
    FakeRunner,
    RecordingOwner,
    progress,
    raw_settings,
    seed_session,
)


@pytest.mark.parametrize("checkpoint_kind", ["completed", "failed"])
def test_gpu_interval_yields_after_ce_and_generation_checkpoints(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, checkpoint_kind: str
) -> None:
    """The real adapter accrues only loaded CE/generation time and yields an unloaded paused state."""
    directory = seed_session(monkeypatch, tmp_path)
    monkeypatch.setenv("WORKER_GPU_REBOOT_INTERVAL_MINUTES", "1")
    monkeypatch.setattr(worker_module, "create_database_engine", lambda _settings: FakeEngine())
    monkeypatch.setattr(worker_module, "create_session_factory", lambda engine: object())
    monkeypatch.setattr(worker_module, "InferenceSchedulingRepository", FakeRepository)
    monkeypatch.setattr(worker_session, "require_worker_checkout", lambda *a, **k: None)
    stable_boot = uuid4()
    monkeypatch.setattr(worker_module.mechanics, "current_boot_id", lambda: stable_boot)
    monkeypatch.setattr(worker_module.mechanics, "read_process_command_line", lambda pid: ("x",))

    monkeypatch.setattr(worker_session, "load_raw_database_settings", raw_settings)
    RecordingOwner.instances = []
    monkeypatch.setattr(runtime_module, "OwnedWorkerRuntime", RecordingOwner)
    monkeypatch.setattr(worker_session, "OwnedWorkerRuntime", RecordingOwner)

    now = {"value": 0.0}

    def monotonic() -> float:
        return now["value"]

    cycle = uuid4()
    first_variant = load_inference_settings().inference_local_variants[0]

    def fake_run(
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
        assert before_unit is not before_request
        assert before_unit() is True
        assert before_request() is True
        # A multiview checkpoint before any runtime load invents no GPU use.
        on_checkpoint(progress("multiview", multiview=1, retained=1, cycle_id=cycle))
        # CE scoring opens a real loaded segment. Its completed checkpoint samples it.
        runtime.start_rerank()
        now["value"] = 20.0
        on_checkpoint(progress("rerank", rerank=1, retained=1, cycle_id=cycle))
        # Time passing inside a unit never denies the request, only the next unit.
        now["value"] = 100.0
        assert before_request() is True
        # Unloading plus a long CPU dwell accrue nothing. Generation reloads.
        runtime.stop_rerank()
        now["value"] = 2000.0
        runtime.activate(first_variant)
        now["value"] = 2045.0
        if checkpoint_kind == "completed":
            on_checkpoint(progress("inference", inference=1, retained=2, cycle_id=cycle))
        else:
            # A committed failed generation attempt samples the same clock with no completion.
            on_generation_attempt_checkpoint()
            on_checkpoint(progress("inference", retained=1, cycle_id=cycle))
        assert before_unit() is False
        # The sole normal unload is the job's finally.
        runtime.stop()
        return SimpleNamespace(stage="inference")

    monkeypatch.setattr(worker_module, "run_inference_job", fake_run)

    code = worker_session.run_worker_session(
        worker_module.InferenceWorkerStage(), SESSION_ID, runner=FakeRunner(), monotonic=monotonic
    )
    assert code == 0, (directory / "state.json").read_text(encoding="utf-8")
    checkpoint = WorkerGpuCheckpoint.model_validate_json(
        (directory / "gpu-clock.json").read_text(encoding="utf-8")
    )
    assert checkpoint.loaded_seconds == 145.0
    state = InferenceControllerWorkerState.model_validate_json(
        (directory / "state.json").read_text(encoding="utf-8")
    )
    assert state.lifecycle == "paused"
    # A failed-attempt checkpoint never inflates the completed coverage count.
    assert state.completed_count == (2 if checkpoint_kind == "completed" else 1)
    assert state.progress is not None and state.progress.stage == "inference"
    status = worker_session.read_worker_status(worker_module.InferenceWorkerStage(), SESSION_ID)
    assert status.lifecycle == "paused"
    assert status.reboot_due is True
    owner = RecordingOwner.instances[-1]
    assert [spec.mode for spec in owner.starts] == ["rerank", "generation"]
    assert owner.stops >= 2


def test_interrupted_resume_retires_owned_runtime_before_rearming(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A dead runner with a live owned runtime is retired, then re-armed, without generation."""
    directory = seed_session(monkeypatch, tmp_path, lifecycle="running")
    monkeypatch.setenv("TRANSLATION_CONTROLLER_STOP_TIMEOUT_SECONDS", "0.01")
    monkeypatch.setenv("TRANSLATION_CONTROLLER_HEALTH_INTERVAL_SECONDS", "0.005")
    write_worker_control(
        directory,
        WorkerControl(
            schema_version=1,
            session_id=SESSION_ID,
            revision=REVISION,
            requested_action="pause",
        ),
    )
    atomic_write_private_text(
        directory / "runtime.json",
        administrative_json(
            worker_module.mechanics.OwnedProcessRecord(
                schema_version=1,
                pid=4242,
                argv=("synthetic-owned-runtime",),
                boot_id=worker_module.mechanics.current_boot_id(),
            )
        ),
    )
    state_before = (directory / "state.json").read_bytes()
    live = {"runtime": True}
    original_observer = worker_module.mechanics.owned_process_is_alive

    def observe(record):
        if record.pid == 4242 and record.argv == ("synthetic-owned-runtime",):
            return live["runtime"]
        return original_observer(record)

    monkeypatch.setattr(worker_module.mechanics, "owned_process_is_alive", observe)
    stopped: list[str] = []

    class Owner:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def stop(self, *, timeout: float, interval: float) -> None:
            stopped.append("owned stop")
            live["runtime"] = False
            (directory / "runtime.json").unlink(missing_ok=True)

    monkeypatch.setattr(worker_session, "OwnedWorkerRuntime", Owner)

    def fail_run(*args, **kwargs):
        raise AssertionError("retained resume must not run the inference job")

    monkeypatch.setattr(worker_module, "run_inference_job", fail_run)

    assert (
        worker_session.read_worker_status(
            worker_module.InferenceWorkerStage(), SESSION_ID
        ).lifecycle
        == "interrupted"
    )
    result = worker_session.request_worker_action(
        worker_module.InferenceWorkerStage(),
        SESSION_ID,
        "resume",
        runner=FakeRunner(),
        sleep=lambda _: None,
    )

    assert stopped == ["owned stop"]
    assert live["runtime"] is False
    assert not (directory / "runtime.json").exists()
    control = WorkerControl.model_validate_json(
        (directory / "control.json").read_text(encoding="utf-8")
    )
    assert control.requested_action == "run"
    # Resume re-arms only, so the result lifecycle is interrupted.
    assert result.lifecycle == "interrupted"
    assert (directory / "state.json").read_bytes() == state_before
