# Lifecycle core

The lifecycle core owns the one detached five-action lifecycle that the ingestion, embedding, translation, and inference stages all share.

## The contracts

`src/course_explorer_admin/lifecycle.py` holds the algorithm and every DTO of the lifecycle contract. The DTOs are frozen and closed, so an unknown field fails a load.

| Symbol | Role |
|---|---|
| `LifecycleSession` | The immutable receipt of one session: `session_id`, `stage`, `revision`, `identity_sha256`, `options`, `created_at`. |
| `LifecycleState` | The one mutable current state: `session_id`, `lifecycle`, `requested_action`, `process`, `progress`, `work_complete`, `owned_services`, `worker`, `active_seconds`, `running_since`, `error_type`, `failure`, `stop_failure`. |
| `LifecycleStatus` | The operator projection. It adds `interrupted` to the lifecycle values and carries `items_per_second` and `eta_seconds`. |
| `Stage` | The protocol each adapter implements: `name`, `services`, `temporary_services`, `retains_after_stop`, `server_worker_module`, `select_options`, `identity_sha256`, `initial_progress`, `require_prepared`, `require_database`, `run`, `release`, `finalize`. |
| `LifecycleContext` | The handle a detached worker uses: `read_state`, `admit`, `checkpoint`, `record_worker`, and `failure_step`. |
| `StageOptions` and `StageProgress` | Discriminated unions on `kind`, one variant per stage. |
| `LifecycleFailure` and `FailureStep` | The content-free failure breadcrumb and its closed step vocabulary. |

`StageProgress` carries `IngestionProgress` with its capture and verification counts, `EmbeddingProgress` with its reconciled, pending, completed, failed, and generated counts and its last measured pace, `TranslationProgress` and `InferenceProgress` with the last mirrored worker status, and `InferenceProgress.preparation` with the server-side preparation step.

## One immutable receipt and one current state

`stage_state_root(stage)` resolves the configured root for each stage and appends `current`. The four keys are `INGESTION_CONTROLLER_STATE_ROOT`, `EMBEDDING_CONTROLLER_STATE_ROOT`, `TRANSLATION_CONTROLLER_STATE_ROOT`, and `INFERENCE_CONTROLLER_STATE_ROOT`, and the administrative root is `ADMIN_STATE_ROOT`.

- `state.json` is the single mutable record. Every write goes through `write_lifecycle_state`, which publishes one canonical JSON line atomically at mode 0600 through the file writer in `course_explorer.administration`.
- `<root>/<session_id>/session.json` is the immutable receipt of one session, written once under the same critical section that reserves the stage. `session_directory` derives and validates the session path, accepting only a 32-character lowercase hexadecimal identity, and the caller that reserves the session creates the directory at mode 0700.
- `read_lifecycle_state` returns `None` for an absent state file. That means a fresh root, and never completeness.

## Identity and compatibility

`local_stages.stage_identity_sha256` hashes the stage name, a stage configuration hash, the selected `postgres_db`, and the options. `ingestion_configuration_sha256` covers the Kori source, request-shape, and academic-year fields and the normalization settings, `embedding_configuration_sha256` covers the embedding runtime settings, and the translation and inference adapters supply their own configuration hashes.

`_require_compatible` runs when a start continues a retained session and when resume re-arms one. It compares the retained receipt's `identity_sha256` with `stage.identity_sha256(session.options)`, and for a retained ingestion session it also calls `require_retained_ingestion_manifest`, which re-reads the retained manifest, requires a regular non-symlink file, and compares its SHA-256 with the recorded one. That comparison is the one manifest check before a continued or resumed ingestion action.

`_start_action` decides in one order: an absent state creates a fresh session, a live owned process or a completed state returns the current status, an idle state whose work is complete or whose stage does not retain work creates a fresh session, and anything else passes the compatibility check and continues the retained session.

## Locks, intent, and checkpoints

`mechanics.exclusive_action_lock(root, controller_name=..., blocking=...)` creates the mode-0700 root and its mode-0600 `controller.lock` when absent and takes an exclusive `flock`. `create=False` leaves an uninitialized root untouched for a read-only caller. Every state writer takes the lock, so the detached worker and the foreground commands serialize on one file.

`_publish_starting` reads the current state once and requires exact equality with `expected_state`. A different snapshot refuses without retry or merge, and the fresh session directory and receipt are created inside the same critical section. `_set_intent(stage, root, action, preserve_stop=True)` is what pause uses, so a pause and a checkpoint leave a pending stop in place.

`LifecycleContext.admit` is the read-only run-intent check a stage calls before the next unit, retry, or request. `checkpoint` replaces the progress and the accumulated active seconds under the lock, and `record_worker` replaces only the worker ownership record while preserving intent.

## The detached worker and its owner

`_self_process_record` records the invoking command as the owner. `_launch_and_wait` spawns `python -m <stage.server_worker_module> <stage> <session_id>` with `start_new_session=True`, writes standard output and standard error to `runner.out` and `runner.err` in the session directory for every stage except inference, and to the null device for inference, and publishes the child's `mechanics.OwnedProcessRecord`, which binds the PID to the kernel boot identity and the exact argv.

`mechanics.owned_process_is_alive` proves ownership by boot identity and an exact command-line match. A dead PID, an empty command line, or a record from an earlier boot is not live, and a live PID whose command line differs from the record raises instead of being signalled.

`course_explorer_admin.worker` is the detached bootstrap. It takes the lock, checks that it is the recorded owner, preserves the requested intent, publishes `running` (or `starting` for inference until its checkpoints show a running worker), and delegates once to `stage.run(context)`. Its terminal publication writes `completed`, or `stopped` or `paused` from the recorded intent, or `failed` with `lifecycle_failure(context.failure_step, exc)`. The stage adapters set `context.failure_step` before each phase, so a failure names the phase that was executing.

## The status projection

`read_lifecycle_status` reads the state, its single named receipt, and the liveness of the exact owned process, and writes nothing. `_project_lifecycle` returns `interrupted` when the recorded lifecycle is `starting` or `running` and the process is not live. `_status_from_state` drops the session identity for an `idle` state while keeping the progress, and `_rate_eta` derives the rate and the projected remaining time per progress variant. An inference status takes its active seconds from the mirrored worker and excludes the preparation steps.

## Local and remote adapters

`local_stages.IngestionStage` and `local_stages.EmbeddingStage` implement the protocol for the two stages that run on the machine that runs the administration command. Both use `course_explorer_admin.worker` as their `server_worker_module`, request the `db` service, and retain their work after a stop. The embedding adapter adds `embedding` to `services` and `temporary_services`, and its `require_prepared` validates the pinned artifact file against `EMBEDDING_ARTIFACT_SHA256`. `run_ingestion_command` prunes every raw capture run that the idle state does not retain, through `local_stages._cleanup_ingestion_raw`.

`remote_stages.RemoteStage` extends the same core with worker bring-up, the detached worker run, the progress mirror, the foreground release hook for pause, and the foreground finalize hook for stop. Translation uses `course_explorer_admin.translation.controller_worker` and inference uses `course_explorer_admin.inference.controller_worker` as their `worker_module`. The adapter tracks the worker lifecycle values in `_RESUMABLE`, `_RESUME_ACCEPTED`, `_PAUSE_ACCEPTED`, `_STOP_ACCEPTED`, `_FINALIZE_ACCEPTED`, and `_CLEANUP_ACCEPTED`, and `_mutation_with_reconcile` retries a lost mutation acknowledgment by reading the real status first.

`WorkerResources` records only what the session created or started, and each bit is monotonic so an ordinary retry never repeats an upload or a start. The transport in `src/course_explorer_admin/transport.py` owns the worker helpers, and `WorkerRecovery` bounds one episode of retries. `WorkerAvailabilityError`, `WorkerConnectionLost`, and `WorkerRecoveryCancelled` carry the outcome.

## Stop, finalize, and failure evidence

`_stop_action` runs one ordered sequence and records a `FailureStep` before each phase: the session read (`session`), the intent (`intent`), the exit wait (`await_exit`), the stage finalize (`finalize`), the owned services (`services`), the local runner logs (`local_cleanup`), and the idle publication (`idle`). `_unload_temporary_services` clears `owned_services` and the dead process record only after the release succeeded, so a failed release leaves ownership and the recoverable state in place.

A remote run records `capture`, `launch`, `status`, and `reboot`, and a remote finalize records `transport`, `bring_up`, `worker_finalize`, `return`, `worker_cleanup`, `release`, and `local_cleanup`. It stops and finalizes the worker session, returns and retains the returned database when the worker reports `imported`, uploads the server receipt, calls the worker cleanup, releases the owned resources, and unlinks the local scratch with `_unlink_local_scratch`. `_publish_stop_failed` persists the `stop_failure` record, and only a completed stop clears it.

The loaded-model clock and the restart handshake live in `src/course_explorer_admin/reboot.py`: `WorkerGpuClock` opens and closes loaded segments, `checkpoint` publishes a `WorkerGpuCheckpoint` at a completed unit or a committed failed generation attempt, and `worker_gpu_reboot_due` reads the record without writing it. `src/course_explorer_admin/runtime.py` owns the model child through `OwnedWorkerRuntime` and exposes the activation protocol through `WorkerInferenceRuntime`. `mechanics.model_request_scope` bounds one model request with a real elapsed-time alarm on the main thread.

## Safe output

`commands.format_operator_error` emits only the exception class name and, for a `CalledProcessError`, the integer return code. `commands.operator_guidance` returns fixed text per operation. `commands.REPORT_SCOPE` and `commands.worker_origin_notice` are the two fixed notices. `lifecycle.lifecycle_failure` extracts the step, the class name, and an available status from a `CalledProcessError`, a `WorkerAvailabilityError`, or any other exception, and stores nothing else.

## Where to change behavior and its tests

| Behavior | Owner | Tests |
|---|---|---|
| The five-action algorithm, the state and receipt schemas, the projection, and the idle raw pruning calls | `lifecycle.py`, `local_stages.py` | `tests/admin/test_lifecycle.py` |
| The lock, the process runner, liveness, the timeout budget, and the Compose prefix | `mechanics.py` | `tests/admin/test_mechanics.py` |
| The remote bring-up, launch, mirror, release, and finalize order | `remote_stages.py` | `tests/admin/test_remote_lifecycle.py` |
| The menu, the dispatcher, the reports, and the safe failure presentation | `commands.py`, `cli.py` | `tests/admin/test_operator_menu.py`, `tests/admin/test_operator_commands.py` |
| The loaded-model clock and the restart handshake | `reboot.py` | `tests/admin/test_checkpoint_reboot.py` |
| The owned model child and the mode switch | `runtime.py` | `tests/admin/test_runtime.py` |
| The file, clock, and path primitives | `course_explorer/administration.py` | `tests/administration/test_administration.py` |

A stage adapter implements the `Stage` protocol and delegates to the one core. A change to the state or receipt schema belongs in `lifecycle.py` with the closed DTO, and a change to an adapter's product decisions belongs in that adapter instead.
