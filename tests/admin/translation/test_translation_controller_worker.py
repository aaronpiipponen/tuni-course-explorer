"""Translation worker-side controller session contracts.

These contracts drive the real worker entrypoints over fake runners, providers, and runtimes. They
prove the request-scope wiring and zero-work path, checkpoint pause/unload and explicit re-arm, the
loaded-GPU yield, durable failure redaction, natural-terminal pause reporting, pending-control
durability, the real in-flight control race, and safe main-error suppression. They reuse the
stage-local fixture owners in ``_worker_support``. The disposable-database tests prove real SQL
persistence.
"""

from __future__ import annotations

import json
import os
import signal
from pathlib import Path

import httpx
import pytest

from course_explorer.enums import TeachingTextLanguage
from course_explorer.translation.provider import TranslationProvider
from course_explorer_admin import mechanics, worker_session
from course_explorer_admin.translation import controller_worker as worker_module
from tests.admin.translation._worker_support import (
    SESSION_ID,
    STARTED_AT,
    FakeOwnedRuntime,
    FakeRunner,
    _valid_chat_response,
    configure,
    entry,
    load_control,
    report,
    script_owned_process_is_alive,
    seed_directory,
    session,
    write_control,
    write_output,
    write_runner_record,
    write_runtime_record,
    write_state,
)


def test_pause_unloads_runner_and_runtime_at_checkpoint(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A pause is declined at the pure gate, the run unloads to a valid state2 checkpoint, and
    an explicit re-arm then lets the same retained run path execute without a gate sleep."""
    configure(monkeypatch, tmp_path)
    session_value = session()
    directory, session_value = seed_directory(tmp_path, session_value)
    write_control(directory, "run")
    write_state(directory, schema_version=2, lifecycle="prepared", desired_count=2)
    script_owned_process_is_alive(monkeypatch, set())
    FakeOwnedRuntime.instances = []
    monkeypatch.setattr(worker_module, "OwnedWorkerRuntime", FakeOwnedRuntime)

    def fake_run(
        *,
        output_path,
        course_limit,
        before_pending_item,
        on_checkpoint,
        before_request,
        request_scope,
    ):
        write_control(directory, "pause")
        assert before_pending_item() is False
        assert before_request() is False
        # The request timer is disarmed before any checkpoint write.
        assert signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0)
        on_checkpoint(1)
        return report(desired=1, generated=1, output=1)

    monkeypatch.setattr(worker_module, "run_translation_command", fake_run)

    assert (
        worker_session.run_worker_session(
            worker_module.TranslationWorkerStage(), SESSION_ID, runner=FakeRunner()
        )
        == 0
    )
    state = json.loads((directory / "state.json").read_text(encoding="utf-8"))
    assert state["schema_version"] == 2
    assert state["lifecycle"] == "paused"
    assert state["runner_pid"] is None and state["runtime_pid"] is None
    assert state["desired_count"] == 2 and state["completed_count"] == 1
    assert FakeOwnedRuntime.instances[0].started
    assert FakeOwnedRuntime.instances[0].stop_count >= 1

    # The paused checkpoint is re-armed explicitly, then the same retained run path executes.
    armed = worker_session.request_worker_action(
        worker_module.TranslationWorkerStage(), SESSION_ID, "resume", runner=FakeRunner()
    )
    assert armed.lifecycle == "paused"
    assert load_control(directory).requested_action == "run"

    FakeOwnedRuntime.instances = []
    observed: list[str] = []

    def resume_run(**kwargs):
        observed.append(load_control(directory).requested_action)
        return report(desired=1, generated=1, output=1)

    monkeypatch.setattr(worker_module, "run_translation_command", resume_run)
    assert (
        worker_session.run_worker_session(
            worker_module.TranslationWorkerStage(), SESSION_ID, runner=FakeRunner()
        )
        == 0
    )
    assert observed == ["run"]
    assert FakeOwnedRuntime.instances[0].started


def test_gpu_interval_yields_after_retained_translation_checkpoint(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A completed checkpoint over the loaded-GPU interval yields an unloaded paused state."""
    configure(monkeypatch, tmp_path)
    monkeypatch.setenv("WORKER_GPU_REBOOT_INTERVAL_MINUTES", "1")
    session_value = session()
    directory, session_value = seed_directory(tmp_path, session_value)
    write_control(directory, "run")
    write_state(directory, schema_version=2, lifecycle="prepared", desired_count=2)
    script_owned_process_is_alive(monkeypatch, set())
    FakeOwnedRuntime.instances = []
    monkeypatch.setattr(worker_module, "OwnedWorkerRuntime", FakeOwnedRuntime)

    now = {"value": 0.0}

    def monotonic() -> float:
        return now["value"]

    def fake_run(
        *,
        output_path,
        course_limit,
        before_pending_item,
        on_checkpoint,
        before_request,
        request_scope,
    ):
        assert before_pending_item() is True
        assert before_request() is True
        # The current item's request may finish. Its completed checkpoint crosses the interval.
        now["value"] = 61.0
        on_checkpoint(1)
        # The next item is refused by the latched due checkpoint, never by control.
        assert before_pending_item() is False
        assert before_request() is True
        return report(desired=1, generated=1, output=1)

    monkeypatch.setattr(worker_module, "run_translation_command", fake_run)

    code = worker_session.run_worker_session(
        worker_module.TranslationWorkerStage(), SESSION_ID, runner=FakeRunner(), monotonic=monotonic
    )
    assert code == 0, (directory / "state.json").read_text(encoding="utf-8")
    state = json.loads((directory / "state.json").read_text(encoding="utf-8"))
    assert state["schema_version"] == 2
    assert state["lifecycle"] == "paused"
    assert state["runner_pid"] is None and state["runtime_pid"] is None
    assert state["desired_count"] == 2 and state["completed_count"] == 1
    assert FakeOwnedRuntime.instances[0].started
    assert FakeOwnedRuntime.instances[0].stop_count >= 1
    # The run control is never overwritten by the yield.
    assert load_control(directory).requested_action == "run"
    # The persisted sample and derived status expose the due checkpoint.
    status = worker_session.read_worker_status(worker_module.TranslationWorkerStage(), SESSION_ID)
    assert status.lifecycle == "paused"
    assert status.reboot_due is True


def test_failure_stops_runtime_and_exposes_only_exception_type(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A worker exception terminates the runtime and stores only the safe exception class."""
    configure(monkeypatch, tmp_path)
    session_value = session()
    directory, session_value = seed_directory(tmp_path, session_value)
    write_control(directory, "run")
    write_state(directory, desired_count=2)
    FakeOwnedRuntime.instances = []
    monkeypatch.setattr(worker_module, "OwnedWorkerRuntime", FakeOwnedRuntime)

    def fake_run(**kwargs) -> object:
        raise RuntimeError("secret source text must never be stored")

    monkeypatch.setattr(worker_module, "run_translation_command", fake_run)

    assert (
        worker_session.run_worker_session(
            worker_module.TranslationWorkerStage(), SESSION_ID, runner=FakeRunner()
        )
        == 1
    )
    assert FakeOwnedRuntime.instances[0].stop_count >= 1
    state = json.loads((directory / "state.json").read_text(encoding="utf-8"))
    assert state["lifecycle"] == "failed"
    assert state["error_type"] == "RuntimeError"
    assert "secret" not in (directory / "state.json").read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("terminal_lifecycle", "extra"),
    (
        ("completed", {"desired_count": 2, "completed_count": 2}),
        ("failed", {"error_type": "RuntimeError"}),
    ),
)
def test_pause_returns_natural_terminal_race_without_timeout(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    terminal_lifecycle: str,
    extra: dict,
) -> None:
    """A worker that naturally reaches a terminal state is reported as terminal, not as paused."""
    configure(monkeypatch, tmp_path)
    session_value = session()
    directory, session_value = seed_directory(tmp_path, session_value)
    write_control(directory, "run")
    write_state(
        directory,
        schema_version=2,
        lifecycle="running",
        runner_pid=os.getpid(),
        runtime_pid=4242,
        running_since=STARTED_AT,
        desired_count=2,
        completed_count=0,
    )
    write_runner_record(directory, os.getpid())
    write_runtime_record(directory, 4242)
    script_owned_process_is_alive(monkeypatch, {os.getpid(), 4242})

    def race(_seconds: float) -> None:
        # The worker reaches its real terminal lifecycle and both owned processes exit.
        write_state(directory, schema_version=2, lifecycle=terminal_lifecycle, **extra)
        script_owned_process_is_alive(monkeypatch, set())

    status = worker_session.request_worker_action(
        worker_module.TranslationWorkerStage(), SESSION_ID, "pause", runner=FakeRunner(), sleep=race
    )

    assert status.lifecycle == terminal_lifecycle
    assert load_control(directory).requested_action == "pause"


@pytest.mark.parametrize("pending", ["pause", "stop"])
def test_pending_control_is_not_reset_by_worker_launch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, pending: str
) -> None:
    """A worker launch never resets a retained pending pause/stop, so it starts no model and
    reports the partial paused/stopped lifecycle rather than completed."""
    configure(monkeypatch, tmp_path)
    session_value = session()
    directory, session_value = seed_directory(tmp_path, session_value)
    write_control(directory, pending)
    write_state(
        directory, schema_version=2, lifecycle="stopped", desired_count=2, completed_count=0
    )
    script_owned_process_is_alive(monkeypatch, set())
    FakeOwnedRuntime.instances = []
    monkeypatch.setattr(worker_module, "OwnedWorkerRuntime", FakeOwnedRuntime)
    observed: list[str] = []

    def fake_run(**kwargs):
        observed.append(load_control(directory).requested_action)
        return report(desired=0, generated=0, output=0)

    monkeypatch.setattr(worker_module, "run_translation_command", fake_run)

    assert (
        worker_session.run_worker_session(
            worker_module.TranslationWorkerStage(), SESSION_ID, runner=FakeRunner()
        )
        == 0
    )
    assert observed == [pending]
    assert not FakeOwnedRuntime.instances[0].started
    state = json.loads((directory / "state.json").read_text(encoding="utf-8"))
    assert state["lifecycle"] == ("paused" if pending == "pause" else "stopped")

    # Only an explicit resume re-arms the retained session back to run.
    worker_session.request_worker_action(
        worker_module.TranslationWorkerStage(), SESSION_ID, "resume", runner=FakeRunner()
    )
    assert load_control(directory).requested_action == "run"


@pytest.mark.parametrize("outcome", ["success", "failure"])
def test_worker_control_race_preserves_inflight_success_and_real_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, outcome: str
) -> None:
    """A real provider request admitted under ``run`` commits its in-flight success after
    a pause flips mid-request, while a real transport failure after that pause starts no retry
    and is a genuine failure."""
    case_root = tmp_path / outcome
    case_root.mkdir()
    configure(monkeypatch, case_root)
    session_value = session()
    directory, session_value = seed_directory(case_root, session_value)
    write_control(directory, "run")
    write_state(directory, schema_version=2, lifecycle="prepared", desired_count=1)
    script_owned_process_is_alive(monkeypatch, set())
    FakeOwnedRuntime.instances = []
    monkeypatch.setattr(worker_module, "OwnedWorkerRuntime", FakeOwnedRuntime)
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        # Control flips to pause while the request is in flight.
        write_control(directory, "pause")
        if outcome == "failure":
            raise httpx.ConnectError("transport down")
        return httpx.Response(200, json=_valid_chat_response())

    def command_double(
        *,
        output_path,
        course_limit,
        before_pending_item,
        on_checkpoint,
        before_request,
        request_scope,
    ):
        # The real provider alone enters request_scope and consults admission. No second path.
        assert request_scope is mechanics.model_request_scope
        assert before_pending_item() is True
        provider = TranslationProvider(
            worker_module.load_translation_settings(),
            transport=httpx.MockTransport(handler),
            before_request=before_request,
            request_scope=request_scope,
        )
        with provider:
            text = provider.translate(
                "Nimi",
                source_language=TeachingTextLanguage.FI,
                target_language=TeachingTextLanguage.EN,
            )
        write_output(directory, [entry(text)])
        on_checkpoint(1)
        return report(desired=1, generated=1, output=1)

    monkeypatch.setattr(worker_module, "run_translation_command", command_double)

    code = worker_session.run_worker_session(
        worker_module.TranslationWorkerStage(), SESSION_ID, runner=FakeRunner()
    )

    # Exactly one request ran: no retry after the pause control change.
    assert calls["count"] == 1
    state = json.loads((directory / "state.json").read_text(encoding="utf-8"))
    if outcome == "success":
        assert code == 0
        assert state["lifecycle"] == "paused"
        assert state["completed_count"] == 1
        assert FakeOwnedRuntime.instances[0].stop_count >= 1
    else:
        assert code == 1
        assert state["lifecycle"] == "failed"
        assert state["error_type"] == "TranslationRequestError"


def test_worker_main_suppresses_unsafe_execution_errors(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A synthetic execution error prints only the class name, returns 1, leaks no traceback or
    untrusted text, prints no fabricated status, and leaves state/evidence untouched."""
    configure(monkeypatch, tmp_path)
    session_value = session()
    directory, session_value = seed_directory(tmp_path, session_value)
    write_control(directory, "run")
    write_state(directory, schema_version=2, lifecycle="prepared", desired_count=1)
    before_state = (directory / "state.json").read_bytes()
    before_session = (directory / "session.json").read_bytes()

    def boom(*args, **kwargs):
        raise RuntimeError("secret source text must never leak")

    monkeypatch.setattr(worker_session, "run_worker_session", boom)

    code = worker_module.main(["run", SESSION_ID])

    captured = capsys.readouterr()
    assert code == 1
    assert captured.err.strip() == "RuntimeError"
    assert "secret" not in captured.err and "Traceback" not in captured.err
    assert captured.out == ""
    assert (directory / "state.json").read_bytes() == before_state
    assert (directory / "session.json").read_bytes() == before_session
