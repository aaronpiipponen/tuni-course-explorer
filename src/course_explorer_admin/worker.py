"""One detached bootstrap that runs exactly one lifecycle stage.

This module runs inside the detached process launched by ``lifecycle.run_lifecycle_command``. It
acquires the one short per-stage lock before its initial ownership check, preserves the live
requested intent, publishes ``running`` and then delegates exactly once to the stage's product
command through :class:`LifecycleContext`, which owns Compose service execution, SQL, work selection
and product service behavior. On a real error it records the content-free executing step,
safe exception class and any available integer status, then re-raises to the safe main. Terminal
publication clears only ``running_since`` and retains the exact process record, so a following
command observes the exit.
"""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Callable, Sequence
from datetime import datetime

from course_explorer.administration import utc_now
from course_explorer_admin import lifecycle, mechanics
from course_explorer_admin.lifecycle import (
    LifecycleContext,
    Stage,
    StageName,
)


def _terminal_state(
    state: lifecycle.LifecycleState,
    value: str,
    *,
    error_type: str | None = None,
    failure: lifecycle.LifecycleFailure | None = None,
    work_complete: bool | None = None,
    clock: Callable[[], datetime],
) -> lifecycle.LifecycleState:
    """Build one terminal state, preserving intent, process, progress and ownership.

    A supplied ``failure`` is the exact content-free breadcrumb for a failed run and supplies the
    current outcome class. Control and success publications pass no failure, which clears the
    current failure while preserving any retained stop failure.
    """
    now = clock()
    active = mechanics.active_seconds(
        state.active_seconds,
        state.running_since,
        running=state.lifecycle == "running",
        now=now,
    )
    if failure is not None:
        error_type = failure.error_type
    updates: dict[str, object] = {
        "lifecycle": value,
        "running_since": None,
        "active_seconds": active,
        "error_type": error_type,
        "failure": failure,
    }
    if work_complete is not None:
        updates["work_complete"] = work_complete
    return state.model_copy(update=updates)


def _publish_terminal(
    stage: Stage,
    root,
    value: str,
    *,
    error_type: str | None = None,
    failure: lifecycle.LifecycleFailure | None = None,
    work_complete: bool | None = None,
    clock: Callable[[], datetime],
) -> None:
    with mechanics.exclusive_action_lock(root, controller_name=stage.name, blocking=True):
        state = lifecycle.read_lifecycle_state(root)
        if state is None:
            return
        lifecycle.write_lifecycle_state(
            root,
            _terminal_state(
                state,
                value,
                error_type=error_type,
                failure=failure,
                work_complete=work_complete,
                clock=clock,
            ),
        )


def run_lifecycle_worker(
    stage: Stage,
    root,
    session_id: str,
    *,
    runner: mechanics.ProcessRunner | None = None,
    clock: Callable[[], datetime] = utc_now,
) -> lifecycle.LifecycleStatus:
    """Run one prepared or retained session and publish its terminal durable state."""
    process_runner = runner if runner is not None else mechanics.SubprocessRunner()
    refused = False
    with mechanics.exclusive_action_lock(root, controller_name=stage.name, blocking=True):
        state = lifecycle.read_lifecycle_state(root)
        if state is None or state.session_id != session_id:
            raise ValueError("lifecycle worker session is not current")
        session = lifecycle._read_session(root, session_id)
        if state.process is None or state.process.pid != os.getpid():
            raise ValueError("lifecycle worker is not the recorded owner")
        if state.requested_action != "run":
            # Publish the pending intent under the lock already held. The process record is
            # retained so the separate pause/stop command can observe its actual exit.
            lifecycle.write_lifecycle_state(
                root,
                _terminal_state(
                    state,
                    "stopped" if state.requested_action == "stop" else "paused",
                    clock=clock,
                ),
            )
            refused = True
        elif stage.name == "inference":
            # Inference is "starting" until its remote worker reports running. The
            # preparation checkpoints own that transition, so no transfer time is shown as work.
            lifecycle.write_lifecycle_state(
                root,
                state.model_copy(update={"lifecycle": "starting", "running_since": None}),
            )
        else:
            now = clock()
            lifecycle.write_lifecycle_state(
                root,
                state.model_copy(update={"lifecycle": "running", "running_since": now}),
            )
    if refused:
        return lifecycle.read_lifecycle_status(stage, root, clock=clock)

    context = LifecycleContext(root=root, session=session, runner=process_runner, clock=clock)
    try:
        complete = stage.run(context)
    except Exception as exc:
        _publish_terminal(
            stage,
            root,
            "failed",
            failure=lifecycle.lifecycle_failure(context.failure_step, exc),
            clock=clock,
        )
        raise
    if complete:
        _publish_terminal(stage, root, "completed", work_complete=True, clock=clock)
    else:
        state = lifecycle.read_lifecycle_state(root)
        intent = state.requested_action if state is not None else "pause"
        _publish_terminal(stage, root, "stopped" if intent == "stop" else "paused", clock=clock)
    return lifecycle.read_lifecycle_status(stage, root, clock=clock)


def make_stage(
    name: StageName, *, inference_stage_factory: Callable[[], Stage] | None = None
) -> Stage:
    """Return the one adapter for a stage name through a lazy stage-package import.

    ``inference_stage_factory`` is used only for ``inference``, so a caller that owns an additional
    explicit route supplies its own adapter without replacing the other three stages.
    """
    from course_explorer_admin import local_stages, remote_stages

    if name == "ingestion":
        return local_stages.IngestionStage()
    if name == "embedding":
        return local_stages.EmbeddingStage()
    if name == "translation":
        return remote_stages.translation_stage()
    if inference_stage_factory is not None:
        return inference_stage_factory()
    return remote_stages.inference_stage()


def main(
    argv: Sequence[str] | None = None,
    *,
    stage_factory: Callable[[StageName], Stage] | None = None,
) -> int:
    """Parse only the stage and session id, delegate once, and report status or a safe error.

    An absent ``stage_factory`` resolves to :func:`make_stage`. A supplied factory replaces the one
    stage construction only, so a caller injects an extra route without a second worker shell.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("ingestion", "embedding", "translation", "inference"))
    parser.add_argument("session_id")
    args = parser.parse_args(argv)
    resolve = stage_factory if stage_factory is not None else make_stage
    stage = resolve(args.stage)
    root = lifecycle.stage_state_root(args.stage)
    try:
        status = run_lifecycle_worker(stage, root, args.session_id)
    except Exception as exc:
        failure = lifecycle.lifecycle_failure(None, exc)
        print(
            json.dumps(
                {
                    "error": failure.error_type,
                    "step": failure.step,
                    "returncode": failure.returncode,
                }
            )
        )
        return 1
    print(status.model_dump_json())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
