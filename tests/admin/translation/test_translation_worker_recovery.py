"""Translation worker retained-work recovery contracts.

These contracts cover the durable recovery seams of the worker entrypoints: strict finalize
output validation, interrupted-stop output/state reconciliation, dead-runner status projection,
publication-window recovery, locked ownership revalidation, retained-output relaunch, duplicate and
completed refusal, unacknowledged-control timeout, and quiescent partial stop. They reuse the
stage-local fixture owners in ``_worker_support``. The disposable-database tests prove real SQL
persistence.
"""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from pathlib import Path

import pytest

from course_explorer.administration import administrative_json, atomic_write_private_text
from course_explorer.teaching_text.service import TranslationImportReport
from course_explorer_admin import mechanics, worker_session
from course_explorer_admin.translation import controller_worker as worker_module
from course_explorer_admin.translation.controller import (
    TranslationControllerImportReceipt,
    TranslationControllerStatus,
)
from tests.admin.translation._worker_support import (
    REVISION,
    SESSION_ID,
    STARTED_AT,
    FakeOwnedRuntime,
    FakeRunner,
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
    write_state,
)


def test_interrupted_stop_reconciles_output_published_before_state(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An interrupted stop imports the atomic output whose state count lagged by one write."""
    configure(monkeypatch, tmp_path)
    session_value = session()
    directory, session_value = seed_directory(tmp_path, session_value)
    write_control(directory, "run")
    write_state(
        directory,
        lifecycle="running",
        runner_pid=999999,
        runtime_pid=4242,
        running_since=STARTED_AT,
        desired_count=2,
        completed_count=0,
    )
    write_output(directory, [entry("Name")])
    monkeypatch.setattr(mechanics, "pid_is_alive", lambda pid: False)
    monkeypatch.setattr(
        worker_module, "run_translation_command", lambda **kwargs: pytest.fail("no provider")
    )
    monkeypatch.setattr(
        worker_module,
        "select_translation_work",
        lambda *a, **k: pytest.fail("no selection during interrupted stop"),
    )

    status = worker_session.request_worker_action(
        worker_module.TranslationWorkerStage(), SESSION_ID, "stop", runner=FakeRunner()
    )

    assert status.lifecycle == "stopped"
    assert status.completed_count == 1
    state = json.loads((directory / "state.json").read_text(encoding="utf-8"))
    assert state["lifecycle"] == "stopped"
    assert state["completed_count"] == 1
    assert state["runner_pid"] is None and state["runtime_pid"] is None

    # A retained count above the recorded desired count fails without rewriting state.
    write_output(directory, [entry("Name"), entry("Other")])
    write_state(
        directory,
        lifecycle="running",
        runner_pid=999999,
        runtime_pid=4242,
        running_since=STARTED_AT,
        desired_count=1,
        completed_count=0,
    )
    before = (directory / "state.json").read_bytes()
    with pytest.raises(ValueError):
        worker_session.request_worker_action(
            worker_module.TranslationWorkerStage(), SESSION_ID, "stop", runner=FakeRunner()
        )
    assert (directory / "state.json").read_bytes() == before


def test_status_projects_dead_runner_as_interrupted_without_writing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A schema-2 runner record is observed live/dead/foreign, a dead one projects interrupted,
    and a valid runnerless pause projects paused without rewriting any file."""
    configure(monkeypatch, tmp_path)
    session_value = session()
    directory, session_value = seed_directory(tmp_path, session_value)
    write_state(
        directory,
        schema_version=2,
        lifecycle="running",
        runner_pid=999999,
        runtime_pid=4242,
        running_since=STARTED_AT,
        desired_count=2,
        completed_count=1,
    )
    write_runner_record(directory, 999999)
    script_owned_process_is_alive(monkeypatch, set())
    before = (directory / "state.json").read_bytes()

    status = worker_session.read_worker_status(worker_module.TranslationWorkerStage(), SESSION_ID)

    assert status.lifecycle == "interrupted"
    assert status.completed_count == 1
    assert status.active_seconds == 0.0
    assert (directory / "state.json").read_bytes() == before

    # A live runner record projects its real lifecycle.
    script_owned_process_is_alive(monkeypatch, {999999})
    assert (
        worker_session.read_worker_status(
            worker_module.TranslationWorkerStage(), SESSION_ID
        ).lifecycle
        == "running"
    )

    # A record that does not match the recorded runner PID is foreign evidence and fails loudly.
    write_state(
        directory,
        schema_version=2,
        lifecycle="running",
        runner_pid=123,
        runtime_pid=4242,
        running_since=STARTED_AT,
        desired_count=2,
        completed_count=1,
    )
    with pytest.raises(ValueError):
        worker_session.read_worker_status(worker_module.TranslationWorkerStage(), SESSION_ID)

    # A valid runnerless schema-2 pause is unloaded and paused. The public
    # status derives remaining/rate/ETA only from positive timing, never an invented value.
    write_state(
        directory,
        schema_version=2,
        lifecycle="paused",
        desired_count=3,
        completed_count=1,
        active_seconds=0.0,
    )
    paused_before = (directory / "state.json").read_bytes()
    paused = worker_session.read_worker_status(worker_module.TranslationWorkerStage(), SESSION_ID)
    assert paused.lifecycle == "paused"
    assert paused.remaining_count == 2
    assert paused.items_per_second is None
    assert paused.projected_remaining_seconds is None
    assert (directory / "state.json").read_bytes() == paused_before

    write_state(
        directory,
        schema_version=2,
        lifecycle="paused",
        desired_count=3,
        completed_count=1,
        active_seconds=2.0,
    )
    measured_status = worker_session.read_worker_status(
        worker_module.TranslationWorkerStage(), SESSION_ID, clock=lambda: STARTED_AT
    )
    assert measured_status.remaining_count == 2
    assert measured_status.items_per_second == 0.5
    assert measured_status.projected_remaining_seconds == 4.0

    # The public main prints one round-trippable text-free status line.
    assert worker_module.main(["status", SESSION_ID]) == 0
    out = capsys.readouterr().out
    assert out.count("\n") == 1
    assert "path" not in out and "pid" not in out and "host" not in out and "Nimi" not in out
    assert TranslationControllerStatus.model_validate_json(out) == measured_status


def test_interrupted_runner_record_publication_remains_recoverable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A dead runner record that disagrees with a stale display PID is ordinary interruption:
    status projects interrupted without rewriting bytes, explicit resume re-arms, and the
    ordinary same-session run proceeds over the retained checkpoint."""
    configure(monkeypatch, tmp_path)
    session_value = session()
    directory, session_value = seed_directory(tmp_path, session_value)
    write_control(directory, "run")
    write_state(
        directory,
        schema_version=2,
        lifecycle="running",
        runner_pid=111111,
        runtime_pid=222222,
        running_since=STARTED_AT,
        desired_count=2,
        completed_count=0,
    )
    # The publication window: the runner record was written for a different process that is
    # already dead, while state carries the stale display PID.
    write_runner_record(directory, 333333)
    script_owned_process_is_alive(monkeypatch, set())
    monkeypatch.setattr(mechanics, "pid_is_alive", lambda pid: False)
    before = (directory / "state.json").read_bytes()

    status = worker_session.read_worker_status(worker_module.TranslationWorkerStage(), SESSION_ID)
    assert status.lifecycle == "interrupted"
    assert (directory / "state.json").read_bytes() == before

    FakeOwnedRuntime.instances = []
    monkeypatch.setattr(worker_module, "OwnedWorkerRuntime", FakeOwnedRuntime)
    worker_session.request_worker_action(
        worker_module.TranslationWorkerStage(), SESSION_ID, "resume", runner=FakeRunner()
    )
    assert load_control(directory).requested_action == "run"
    assert (directory / "state.json").read_bytes() == before

    observed: list[str] = []

    def fake_run(**kwargs):
        observed.append(load_control(directory).requested_action)
        return report(desired=2, generated=2, output=2)

    monkeypatch.setattr(worker_module, "run_translation_command", fake_run)
    FakeOwnedRuntime.instances = []
    assert (
        worker_session.run_worker_session(
            worker_module.TranslationWorkerStage(), SESSION_ID, runner=FakeRunner()
        )
        == 0
    )
    assert observed == ["run"]
    assert FakeOwnedRuntime.instances[0].started


def test_worker_actions_revalidate_locked_ownership_and_lifecycle(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Evidence injected exactly at lock entry is refused by every locked decision path: a
    live record blocks export/cleanup/unloaded stop with bytes preserved and no drop, and
    a completed race is returned by resume without rewriting control."""
    configure(monkeypatch, tmp_path)
    session_value = session()
    directory, session_value = seed_directory(tmp_path, session_value)
    monkeypatch.setattr(
        worker_module,
        "load_raw_database_settings",
        lambda: type("S", (), {"postgres_user": "course_explorer"})(),
    )
    live: set[int] = set()
    script_owned_process_is_alive(monkeypatch, live)

    inject: dict[str, object] = {"fn": lambda: None}
    real_lock = mechanics.exclusive_action_lock

    @contextmanager
    def lock_at_entry(root, *, controller_name, create=True, blocking=False):
        with real_lock(root, controller_name=controller_name, create=create, blocking=blocking):
            # Inject only under the session instance lock. The shared control publisher takes its
            # own disjoint controls lock, which is not a locked work-decision boundary.
            if root == directory:
                inject["fn"]()  # type: ignore[operator]
            yield

    monkeypatch.setattr(mechanics, "exclusive_action_lock", lock_at_entry)

    def inject_live_runner() -> None:
        write_runner_record(directory, 555)
        live.add(555)

    # Cleanup: the same live record refuses before the receipt-gated drop.
    (directory / "runner.json").unlink(missing_ok=True)
    live.clear()
    write_state(
        directory, schema_version=2, lifecycle="stopped", desired_count=1, completed_count=1
    )
    digest = write_output(directory, [entry("Name")])
    atomic_write_private_text(
        directory / "import-receipt.json",
        administrative_json(
            TranslationControllerImportReceipt(
                schema_version=1,
                session_id=SESSION_ID,
                revision=REVISION,
                output_count=1,
                output_sha256=digest,
                import_report=TranslationImportReport(
                    requested_count=1, inserted_count=1, updated_count=0, unchanged_count=0
                ),
            )
        ),
    )
    runner = FakeRunner()
    state_before = (directory / "state.json").read_bytes()
    output_before = (directory / "output.json").read_bytes()
    inject["fn"] = inject_live_runner
    with pytest.raises(ValueError):
        worker_session.cleanup_worker_session(
            worker_module.TranslationWorkerStage(), SESSION_ID, runner=runner
        )
    assert not any("dropdb" in call for call in runner.calls)
    assert (directory / "state.json").read_bytes() == state_before
    assert (directory / "output.json").read_bytes() == output_before
    assert (directory / "runner.json").exists()

    # Unloaded stop: a live record refuses before counting or stopping a runtime, and the
    # already published stop request holds through the refusal.
    (directory / "runner.json").unlink()
    live.clear()
    write_state(
        directory, schema_version=2, lifecycle="prepared", desired_count=2, completed_count=0
    )
    write_control(directory, "run")
    state_before = (directory / "state.json").read_bytes()
    inject["fn"] = inject_live_runner
    with pytest.raises(ValueError):
        worker_session.request_worker_action(
            worker_module.TranslationWorkerStage(), SESSION_ID, "stop", runner=FakeRunner()
        )
    assert (directory / "state.json").read_bytes() == state_before
    assert load_control(directory).requested_action == "stop"

    # Resume: a completed race injected at lock entry is returned as-is, not re-armed.
    (directory / "runner.json").unlink()
    (directory / "runtime.json").unlink(missing_ok=True)
    (directory / "import-receipt.json").unlink(missing_ok=True)
    live.clear()
    write_state(
        directory, schema_version=2, lifecycle="stopped", desired_count=2, completed_count=1
    )
    write_control(directory, "run")
    control_before = (directory / "control.json").read_bytes()

    def inject_completed() -> None:
        write_state(
            directory,
            schema_version=2,
            lifecycle="completed",
            desired_count=2,
            completed_count=2,
        )

    inject["fn"] = inject_completed
    completed = worker_session.request_worker_action(
        worker_module.TranslationWorkerStage(), SESSION_ID, "resume", runner=FakeRunner()
    )
    assert completed.lifecycle == "completed"
    assert completed.session_id == SESSION_ID
    assert (directory / "control.json").read_bytes() == control_before


def test_worker_relaunch_reuses_checkpointed_output_without_duplicate_work(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A relaunched retained session re-enters the one worker path over retained output."""
    configure(monkeypatch, tmp_path)
    session_value = session()
    directory, session_value = seed_directory(tmp_path, session_value)
    write_control(directory, "run")
    write_state(
        directory,
        lifecycle="stopped",
        desired_count=2,
        completed_count=1,
    )
    monkeypatch.setattr(mechanics, "pid_is_alive", lambda pid: False)
    FakeOwnedRuntime.instances = []
    monkeypatch.setattr(worker_module, "OwnedWorkerRuntime", FakeOwnedRuntime)

    calls: list[dict] = []

    def fake_run(**kwargs):
        calls.append(kwargs)
        return report(desired=1, generated=1, output=1)

    monkeypatch.setattr(worker_module, "run_translation_command", fake_run)

    assert (
        worker_session.run_worker_session(
            worker_module.TranslationWorkerStage(), SESSION_ID, runner=FakeRunner()
        )
        == 0
    )
    assert calls and calls[0]["output_path"] == directory / "output.json"
    assert FakeOwnedRuntime.instances[0].started
    state = json.loads((directory / "state.json").read_text(encoding="utf-8"))
    assert state["lifecycle"] == "completed"
    assert state["runner_pid"] is None


def test_worker_relaunch_rejects_live_duplicate_and_completed_state(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A live runner or already completed work is never relaunched in a second process."""
    configure(monkeypatch, tmp_path)
    session_value = session()
    directory, session_value = seed_directory(tmp_path, session_value)
    write_control(directory, "run")
    write_state(
        directory,
        lifecycle="running",
        runner_pid=999999,
        runtime_pid=4242,
        running_since=STARTED_AT,
        desired_count=2,
        completed_count=1,
    )
    write_runner_record(directory, 999999)
    script_owned_process_is_alive(monkeypatch, {999999})
    with pytest.raises(ValueError):
        worker_session.run_worker_session(
            worker_module.TranslationWorkerStage(), SESSION_ID, runner=FakeRunner()
        )

    write_state(directory, lifecycle="completed", desired_count=2, completed_count=2)
    with pytest.raises(ValueError):
        worker_session.run_worker_session(
            worker_module.TranslationWorkerStage(), SESSION_ID, runner=FakeRunner()
        )

    # A concurrent holder of the session instance lock refuses the second launch before any
    # state or ownership record is written.
    (directory / "runner.json").unlink(missing_ok=True)
    write_state(
        directory, schema_version=2, lifecycle="prepared", desired_count=2, completed_count=0
    )
    before_state = (directory / "state.json").read_bytes()
    with mechanics.exclusive_action_lock(directory, controller_name="translation worker"):
        with pytest.raises(RuntimeError):
            worker_session.run_worker_session(
                worker_module.TranslationWorkerStage(), SESSION_ID, runner=FakeRunner()
            )
    assert (directory / "state.json").read_bytes() == before_state
    assert not (directory / "runner.json").exists()


def test_worker_action_timeout_fails_and_preserves_state(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An unacknowledged pause raises instead of reporting a lifecycle never reached."""
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
    script_owned_process_is_alive(monkeypatch, {os.getpid(), 4242})
    before = (directory / "state.json").read_bytes()

    # The explicit monotonic control deadline advances past the stop bound deterministically.
    moments = iter([0.0, 1000.0])
    monkeypatch.setattr(worker_session.time, "monotonic", lambda: next(moments))

    with pytest.raises(RuntimeError):
        worker_session.request_worker_action(
            worker_module.TranslationWorkerStage(),
            SESSION_ID,
            "pause",
            runner=FakeRunner(),
            sleep=lambda seconds: None,
        )
    assert (directory / "state.json").read_bytes() == before
    assert load_control(directory).requested_action == "pause"


def test_prepared_and_interrupted_stop_run_no_provider_work(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An exiting unloaded pause is waited out before the checkpoint is stopped, with no provider
    call and no work selection."""
    configure(monkeypatch, tmp_path)
    session_value = session()
    directory, session_value = seed_directory(tmp_path, session_value)
    write_control(directory, "run")
    write_state(directory, schema_version=2, lifecycle="paused", desired_count=2, completed_count=0)
    monkeypatch.setattr(
        worker_module, "run_translation_command", lambda **kwargs: pytest.fail("no provider")
    )
    monkeypatch.setattr(
        worker_module,
        "select_translation_work",
        lambda *a, **k: pytest.fail("no work selection during stop"),
    )

    # An exiting paused runner record may be live. Stop publishes control first and waits only
    # for that runner to exit.
    write_runner_record(directory, 999999)
    live = {999999}
    monkeypatch.setattr(mechanics, "owned_process_is_alive", lambda record: record.pid in live)

    def exit_runner(seconds: float) -> None:
        live.clear()

    status = worker_session.request_worker_action(
        worker_module.TranslationWorkerStage(),
        SESSION_ID,
        "stop",
        runner=FakeRunner(),
        sleep=exit_runner,
    )
    assert status.lifecycle == "stopped"
    state = json.loads((directory / "state.json").read_text(encoding="utf-8"))
    assert state["lifecycle"] == "stopped"
    assert state["runner_pid"] is None
    assert state["runtime_pid"] is None
