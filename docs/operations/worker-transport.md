# Worker transport and datasets

This page maps the modules that carry one worker session over the transport boundary and own the dataset receipts, snapshots, and rotation.

## Module owners

| Module | Owns |
|---|---|
| `src/course_explorer_admin/transport.py` | The one SSH/WSL command and file transport, its recovery budget, and the transport error classes |
| `src/course_explorer_admin/logs.py` | The session listing, and the fixed bounded log reads the two worker sources reach through that transport |
| `src/course_explorer_admin/remote.py` | The worker session, control, and status DTOs, the worker-side prepare/export/cleanup helpers, and the worker dataset CLI |
| `src/course_explorer_admin/worker_session.py` | The shared worker-side lifecycle shell, its subcommands, and the identity, quiescence, and cleanup guards |
| `src/course_explorer_admin/remote_stages.py` | The server-side translation and inference adapters over the lifecycle core |
| `src/course_explorer_admin/snapshots.py` | The dump and restore command mechanics and the embedding-data rule |
| `src/course_explorer_admin/datasets.py` | Receipt and role-pointer writes, enrollment, role migration, copy, return retention, and rotation |
| `src/course_explorer/datasets.py` | The dataset DTOs, pointer resolution, the schema-head check, and the verification read |
| `src/course_explorer_admin/provisioning.py` | Explicit worker code update, preparation, and read-only preflight |
| `src/course_explorer_admin/provisioning_worker.py` | Worker-side resource readiness and preparation, and the prepared-runtime check |
| `src/course_explorer_admin/reboot.py` | The loaded-GPU checkpoint clock and the worker restart handshake |
| `src/course_explorer_admin/runtime.py` | The owned model runtime shared by the two worker stages |

The behavior these owners implement is described in [Worker sessions](/docs/operations/worker-sessions.md) and [Datasets](/docs/operations/datasets.md).

## The transport abstraction

`SshWslTransport(runner: mechanics.ProcessRunner, settings: WorkerConnectionSettings)` owns four boundaries.

| Method | Boundary |
|---|---|
| `run(argv, *, cwd, env=None, stdin_path=None, timeout=None)` | One command with captured stdout and a classified result |
| `start_detached(argv, *, cwd, env, output_path, timeout=None)` | One detached command and its log file |
| `upload(source, destination, *, reuse_matching=False, timeout=None)` | One file streamed to the worker and renamed into place |
| `download(source, destination, *, timeout=None)` | One file streamed back to an atomic local mode-0600 file |

The keepalive methods are `start_keepalive`, `keepalive_is_alive`, `stop_keepalive`, and `terminate_remote_keepalive`. The worker-host identity methods are `read_windows_boot_id` and `request_windows_reboot`.

Every command body runs through one wrapper that installs an exit trap before the working directory change. The trap emits exactly one `COURSE_EXPLORER_TRANSPORT_RESULT <phase> <status>` record on standard error, where the phase is `bootstrap` before the payload starts and `command` after. `_classify` reads the process status and the records: a zero status must carry exactly one zero `command` record, a nonzero status with a valid nonzero record raises `WorkerCommandError`, and a nonzero status without a record raises `WorkerAvailabilityError`. Any other shape raises `ValueError`, so an unproven completion is never mistaken for a success. The wrapper rejects an environment override whose key is not on `_WORKER_ENVIRONMENT_ALLOWLIST`, which holds the stage state roots, the derived database name, the GPU detection flag, and the checkpoint-reboot interval.

`WorkerRecovery` owns one retry-admission budget. `begin()` fixes one deadline of `connection.stop_timeout_seconds`, `remaining()` reports what is left of it, and `call(operation)` retries only `WorkerAvailabilityError` while the budget lasts and the optional `run_allowed` admission holds. `WorkerConnectionLost` is the expired-recovery subclass, and `WorkerRecoveryCancelled` is raised when live run intent is withdrawn.

The connection values name where the transport goes. `TRANSLATION_CONTROLLER_SSH_CONNECT_TIMEOUT_SECONDS` bounds one connect attempt, `TRANSLATION_CONTROLLER_STOP_TIMEOUT_SECONDS` is the recovery and stop bound, and `TRANSLATION_CONTROLLER_HEALTH_INTERVAL_SECONDS` spaces the retries and polls. The target, the environment, and the worker checkout path are non-secret worker identity values in `config/worker.toml`, so a machine change does not change shared code.

Transport protocols at the level the module fixes them: each command is one SSH invocation against the configured worker target, and each command body runs inside the configured environment on the worker. The boot identity read and the restart request use the same target without the command wrapper. The keepalive is one detached local SSH child that holds a remote sleep open for the session, and `terminate_remote_keepalive` stops the exact session-named remote process.

## The fixed worker log read

`course_explorer_admin.logs` owns one bounded read of a fixed session log, and it uses the same transport without the lifecycle helpers. `read_session_log(stage, session_id, source, *, lines, runner)` resolves the lifecycle session receipt of the chosen stage for every source. The `keepalive` source also resolves the recorded canonical worker session, and the `worker-runner` and `worker-runtime` sources derive the worker path server side from `remote_worker_session_directory`, so no caller supplies a path. A worker source runs exactly one `transport.run(("bash", "-c", script), cwd=PurePosixPath(str(connection.worker_project_root)), timeout=connection.stop_timeout_seconds)` with no environment override.

For a worker source, the script is one line, and it is the only worker command of that read. It walks the derived path's ancestors from the root to the log's parent, refusing a symlink before it checks existence and requiring each present ancestor to be a searchable directory, then it refuses a symlink at the log path itself and requires a regular file there, and it prints the last lines with `tail -n COUNT -- PATH`. Every ancestor path is quoted, each ancestor refusal exits 1, an absent ancestor or an absent log exits 3, and a tail failure exits 1.

Only a command-phase exit status of 3 is classified as an absent log, which the read reports as unavailable with no text. A read failure, a timeout, a connection or protocol failure and a decode failure propagate to the caller, and no captured output reaches the failure line.

This read installs nothing, prepares nothing, reads no worker status, starts no keepalive and retries nothing, so it needs no `uv` invocation, no dependency check, no prepared checkout and no recovery episode.

## The session lifecycle seam

`WorkerStage` in `src/course_explorer_admin/worker_session.py` is the seam a worker stage implements. Its methods are `connection`, `load_session`, `load_state`, `require_policy`, `publish_prepared`, `run`, `read_import_receipt`, `finalize`, `status`, `stop_updates`, and `require_cleanup_evidence`, and its attributes name the stage, the controller lock name, and the artifacts that cleanup removes.

| Function | Owns |
|---|---|
| `prepare_worker_session(stage, session, *, runner)` | The canonical prepare and the already-prepared acknowledgement |
| `run_worker_session(stage, session_id, *, runner, ...)` | One session run under the session instance lock |
| `request_worker_action(stage, session_id, action, *, runner, ...)` | Pause, resume, and stop, and their acknowledgement |
| `finalize_worker_session(stage, session_id, *, runner)` | The one import and publication of a terminal session |
| `cleanup_worker_session(stage, session_id, *, runner)` | The receipt-gated drop and evidence removal |
| `read_worker_status(stage, session_id, *, clock)` | The read-only operator status |
| `project_worker_lifecycle(state, *, directory)` | The interrupted projection of a vanished runner |
| `await_worker_quiescence(...)` and `require_worker_quiescence(state, directory)` | The bounded exit wait and the locked re-proof |
| `require_worker_database_schema(session)` | The received-database schema-head precondition |
| `worker_main(stage)` | The prepare, run, pause, resume, status, finalize, cleanup, and stop subcommands |

The server-side adapter is `remote_stages.RemoteStage`. `run(context)` captures the session, brings the worker up, launches the run, and mirrors progress until a terminal status. `release(context)` is the pause path, and `finalize(context)` is the stop path that finalizes, returns, cleans, and releases. `_bring_up(context, transport, connection, session, *, recovery)` starts the keepalive, the worker database service, the remote session directory, the uploads, the check of the locked environment, and the worker restore. `_launch(...)` re-arms a retained session and starts the detached run, and `_await_launch_acknowledgment(...)` resolves a lost launcher response from read-only status. `_mutation_with_reconcile(operation, read_status, accepted)` reads the real status before a retry, and the closed accepted sets are `_RESUME_ACCEPTED`, `_PAUSE_ACCEPTED`, `_STOP_ACCEPTED`, `_FINALIZE_ACCEPTED`, and `_CLEANUP_ACCEPTED`. `_transport(runner, connection)` is the single construction point, and `_worker_helper(...)` wraps every worker invocation in `uv run --no-sync --offline --no-python-downloads`.

Where to change what:

| Behavior | Owner |
|---|---|
| Adding a remote stage | A `WorkerStage` implementation plus a `RemoteStage` built in `remote_stages.py` |
| The control vocabulary | `WorkerControl` in `remote.py` and `publish_worker_control` in `worker_session.py` |
| The worker subcommand set | `worker_main` in `worker_session.py` |
| The transport or its recovery budget | `transport.py` |
| The session identity fields | `WorkerDatasetSession` in `remote.py` |

## Worker commands

These commands run on the worker. The first two act on the session directory of one prepared session, and the third reads the worker's resources and takes no session.

```bash
uv run --no-sync --offline --no-python-downloads python -m course_explorer_admin.translation.controller_worker status SESSION_ID
uv run --no-sync --offline --no-python-downloads python -m course_explorer_admin.remote prepare SESSION_ID
uv run --no-sync --offline --no-python-downloads python -m course_explorer_admin.provisioning_worker check
```

`course_explorer_admin.remote` exposes `prepare`, `export`, and `cleanup`. The stage worker modules expose `prepare`, `run`, `pause`, `resume`, `status`, `finalize`, `cleanup`, and `stop` through the shared shell. `course_explorer_admin.provisioning_worker` exposes `check` and `prepare`.

## Dataset owners and predicates

`src/course_explorer/datasets.py` owns the DTOs and the read-only checks. `DatasetReceipt.validate_kind_identity` enforces the initial, returned and copied receipt shapes, `DatasetPointer` is the strict pointer, `DatabaseSnapshot` binds a dump digest to a session and a verification, and `DatasetVerification` carries the migration head, the table row counts, the catalogue summary, and the coverage reads. One public dataset read applies the state-tree guard once and passes the checked root down, so one listing does not walk the tree once per pointer and receipt. `read_dataset_role(state_root, role)` reads one role and decides bootstrap, `resolve_dataset_role(state_root, role)` raises the role guidance, `resolve_selected_dataset(state_root)` delegates to that resolver, `read_dataset_receipt(state_root, dataset_id)` reads one confined receipt after the state guard, `dataset_state_refusal(state_root)` reports a redirected state tree, `require_selected_dataset_root(state_root)` refuses one, `require_database_schema(connection)` compares the current migration head and raises `DatabaseSchemaMismatchError`, and `read_dataset_verification(settings)` opens one disposable engine for the verification read.

`src/course_explorer_admin/datasets.py` owns every write. `admin_state_path(settings)` returns the repository-relative state root, `admin_state_root(settings)` resolves it and refuses the backups boundary, `initialize_selected_dataset(*, runner)` enrolls the initial dataset, `ensure_selected_dataset(*, runner)` applies the example-database exception for deploy, `migrate_dataset(role, *, runner)` applies the head with the Working idle guard, `copy_to_working(source_dataset_id, *, runner)` creates a verified copy and publishes Working, `retain_returned_dataset(session, snapshot, dump, *, runner)` restores, verifies, writes the returned receipt, publishes Working, and rotates, `require_returned_dataset_receipt(receipt, session, *, server_database)` is the receipt predicate, `read_optional_dataset_receipt(root, dataset_id)` tells an absent receipt from a malformed one, `require_droppable_database(database_name)` refuses a protected name, `_retain_dump(source, destination)` copies a dump into its confined path, `_walk_chain(receipts, start)` validates one chain through the action's receipt index, and `_rotate_locked(settings, root, runner)` drops the databases outside both role pairs.

`src/course_explorer_admin/remote.py` owns the session-side dataset work. `create_worker_dataset_session(stage, *, session_id, course_limit=None, runner)` snapshots the Working dataset, `prepare_worker_database(session, *, runner)` restores the uploaded input dump and checks it against the snapshot digest, `export_worker_database(session, *, runner)` verifies and exports the return snapshot, `return_worker_database(session, *, transport, runner)` downloads and retains it, and `cleanup_returned_worker_database(session, receipt, *, runner)` drops the exact worker database after the recorded session, the receipt and the return snapshot agree on their session and database identity. `worker_dataset_session_directory(session_id)` and `remote_worker_session_directory(connection, session_id)` own the two session path forms.

`src/course_explorer_admin/snapshots.py` owns the process commands. `dump_database(*, runner, root, settings, destination, include_embeddings, timeout=None)` dumps into a fresh temporary, publishes it at mode 0600 and returns its producer digest, `restore_database(...)` creates or verifies a target and restores into it, checks a supplied expected digest once, and compares the restored database's verification with the supplied snapshot verification, and `database_dump_contains_embedding_data(listing)` matches `_EMBEDDING_TABLE_DATA_PATTERN` for the embedding-data policy. A transferred or moved dump is restored with its snapshot digest, while a same-operation copy passes no separate digest and relies on the producer digest stored in the receipt and the restore verification.

Where to change what:

| Behavior | Owner |
|---|---|
| The receipt, snapshot, or verification shape | `src/course_explorer/datasets.py` |
| Enrollment, copy, return, or rotation | `src/course_explorer_admin/datasets.py` |
| The dump and restore commands | `src/course_explorer_admin/snapshots.py` |
| The derived database names | `AdministrativeDatasetSettings.dataset_database_prefix` and `worker_database_prefix` in `src/course_explorer/config.py` |

## The checkpoint clock and the model runtime

`reboot.WorkerGpuClock(directory, *, session_id, settings, monotonic=time.monotonic)` counts loaded seconds only. `loaded()` opens one segment, `unloaded()` closes it, `checkpoint()` samples the open segment and publishes `WorkerGpuCheckpoint` as `gpu-clock.json`, and `due` reports the last published sample. `worker_gpu_reboot_due(directory, *, session_id, settings)` is the read-only due check, and `reboot_windows_worker(transport, connection, *, run_allowed, recovery=None, sleep=..., monotonic=...)` issues one restart request and proves a changed boot plus a healthy worker environment before it returns.

`runtime.OwnedWorkerRuntime(runner, *, root, directory, sleep=...)` owns one model child through the `runtime.json` ownership record. `start(spec, *, attempts, interval, timeout)` reuses a live identical record or spawns after `provisioning_worker.require_prepared_runtime`, and `stop(*, timeout, interval)` retires only a proved-owned process. `WorkerInferenceRuntime` adds `activate`, `stop`, `start_rerank`, `stop_rerank`, and `request_scope` over that owner, and the inference stage passes its `WorkerGpuClock` in so a mode switch closes and opens the loaded segment.

## Tests that pin this behavior

| Test module | Covers |
|---|---|
| `tests/admin/test_remote_lifecycle.py` | The due reboot and the same-session resume, the pending-pause suppression, the bounded mirror failure and its diagnostics, the stop recovery, the failed return, and the genuine helper error |
| `tests/admin/test_datasets.py` | Enrollment idempotency, the pointer-only interruption, Working assignment on return, copy and deletion authorities, both role pairs and rotation, the redirected collection, listing availability, Working deletion, and the serialized worker export |
| `tests/admin/test_dataset_database.py` | The real dump, restore, copy and return round trip, vector and verification preservation, role-pair rotation, and the guarded role migration |
| `tests/admin/test_worker_setup.py` | The fast-forward code update, preservation of user work in a dirty checkout, the read-only resource check, and the artifact verification |
| `tests/admin/test_checkpoint_reboot.py` | The clock arithmetic and the changed-boot plus healthy-environment requirement |
| `tests/admin/test_log_reads.py` | Each fixed local source, a redirected session directory chain, the classified absent worker log beside a genuine read failure, the symlink refusals, and the one fixed worker command |
| `tests/admin/test_runtime.py` | The configured runtime builders, the ownership record, the occupied port, the reused foreign PID, and the record from another boot |
| `tests/datasets/test_datasets.py` | The pointer resolution, the presence-based roles, the cached-alias guard, and the failure shapes |
