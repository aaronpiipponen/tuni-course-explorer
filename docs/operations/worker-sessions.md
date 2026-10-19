# Worker sessions

A worker session is one run of a remote stage on the worker, from the prepared copy of the selected dataset to the verified return of the result.

## What a session binds

The translation and inference stages are [remote stages](/docs/reference/glossary.md#administration). Each run of one of them is a [worker session](/docs/reference/glossary.md#administration), and one session binds the identity of the source dataset, the revision of the server checkout, the stage, the derived worker database, and the full input snapshot of the selected dataset.

The worker database name is derived from the session id with `ADMIN_WORKER_DATABASE_PREFIX`, and the name of the returned server database with `ADMIN_DATASET_DATABASE_PREFIX`. Both prefixes are in `config/worker.toml`. The session evidence lives under `ADMIN_STATE_ROOT`, which is in `config/database.toml`, and the worker holds the same evidence under its own copy of that path.

Each read of the session record checks the session identity, and each read of the control record and the worker state checks the session identity and the revision. A mismatch fails before any model or command work.

## Explicit setup and the recurring start

Worker preparation and the recurring stage work are two separate operations.

`uv run python scripts/admin.py setup worker` fast-forwards the worker checkout to one origin branch, installs its locked environment, and prepares its pointed resources: the configured system packages, the database service image, the pinned model artifacts, and the pinned runtimes. `--branch BRANCH` selects the origin branch, and `--code-only` updates the code and its locked environment without preparing the pointed resources.

`uv run python scripts/admin.py preflight` is the read-only check of the prepared code and the prepared resources. It changes nothing and returns a nonzero exit status when a resource is missing.

The recurring start never fetches, installs, or downloads. It validates that the worker checkout is a clean prepared tree, checks the installed locked environment without syncing it, and runs every worker helper without dependency resolution or download.

```bash
uv run python scripts/admin.py setup datasets
uv run python scripts/admin.py setup worker
uv run python scripts/admin.py preflight
uv run python scripts/admin.py translation start
uv run python scripts/admin.py translation status
uv run python scripts/admin.py translation stop
```

Prerequisites: the tracked subsystem files under `config/` and the ignored environment file hold the values these commands read, a dataset is selected, and the worker account runs the setup commands without an interactive prompt. The [Operator menu](/docs/operations/operator-menu.md#setup-and-preflight) lists the same entries with their machine commands.

## Starting a session

A start captures a session when the stage holds none. The administration command dumps the selected dataset, including the embedding table data, into the session directory, records the digest of that dump and a verification of the selected database, records the revision of the server checkout, and publishes the session record. A reservation that already holds session evidence is refused before any dump.

Preparation brings the worker up in order:

1. One keepalive process starts and holds the session's environment open.
2. The session starts the worker database service when it is not already running and records that it did. A database service that is already running without recorded ownership refuses the session.
3. The remote session directory is created once.
4. The session record, the stage policy, and the input dump are uploaded. An upload reuses a byte-identical file already on the worker.

The worker then restores the input dump into its derived database and checks the restored database against the input snapshot. A mismatch fails the session.

A worker run requires its own clean prepared checkout and a received database at the migration head of the worker code. A mismatch fails before any model or command work and changes no state.

The launch runs exactly one detached worker helper, which writes its log beside the session. A lost launcher response is reconciled from the worker status within the recovery bound, and the launcher is never run a second time. A fresh preparation is one-shot for the same reason, so a lost acknowledgement fails loudly rather than repeating a restore.

While the session runs, the stage mirrors the worker status into its own durable progress. The mirror is read-only, and it forwards no control to the worker.

## Cooperative control and checkpoints

The worker reads one control record. It names the session, the revision, and one requested action: run, pause, or stop. The record is published atomically under a per-session lock.

A stop always writes stop. A pause never overwrites a pending stop, and nothing clears a pending pause or stop except an explicit re-arm, which only a locked resume performs.

The worker stage reads the control at its own checkpoints. Translation takes a pause or a stop between two cells, and inference takes one after a completed unit of work. [Stage lifecycle](/docs/operations/stage-lifecycle.md#pause-and-stop) lists the boundary of each stage. A control request therefore takes effect at the next checkpoint, and no run ends inside a unit of work.

A checkpoint records the worker state and the completed count, and it keeps the retained output. When a pause or a stop ends the run at a checkpoint, the stage unloads the model runtime it started and publishes the terminal lifecycle for the control request it read. That retained output is the progress of the session, so a resumed session carries the work the session finished. [Translation](/docs/backend/text-and-vectors/translation.md#the-output-it-publishes) describes the retained file and the import that writes it into the worker's copy.

A stage status reads the durable state and the owned process, and it writes nothing. A starting or running record whose owned runner process is not alive is reported as interrupted, and that projection writes no state.

## Pause, stop, and the return

A pause publishes a pause request, waits for the worker to exit, and releases the resources the session started. The session record, the state, the retained output, and the other evidence stay, so a resume can re-arm the work.

A stop is the authoritative end of a session. It publishes a stop request, waits for the worker to exit, and finalizes the session through its owning writer. The worker import writes the retained output into the worker's own copy of the dataset, and the inference stage publishes the accepted proposals and equivalence groups there. A session that already holds an import receipt is never imported a second time.

The return follows the import, and it verifies before it promotes. The worker exports a fresh snapshot of the quiescent worker database, and the administration command downloads it, checks the digest and a fresh verification against that snapshot, restores it into the derived server database, writes the returned dataset receipt, selects the returned dataset, and rotates older datasets.

![The selected dataset becomes a verified input copy that the worker restores into its own copy, where the remote stage runs and records checkpoints. The stage exports a verified return snapshot, that snapshot is restored and promoted as the selected dataset, and the worker copy is dropped only after the verified receipt exists. A worker session box owns the session commands, and its dashed links show the run control and the finalize and cleanup it performs.](/docs/diagrams/worker-session-return.svg)

Only after the verified receipt exists does the session's cleanup drop the exact worker database, together with the transferred and generated evidence of the session. The owned resources and the local scratch go last.

A dataset return updates the selected dataset that the configured copy resolves through its pointer. [Datasets](/docs/operations/datasets.md) describes the receipt chain, the promotion, and the rotation.

> [!CAUTION]
> A stop that fails before the return completes leaves the selection in place and keeps the worker copy, the retained output, and the session evidence. The next stop verifies the recorded state again and continues from there.


### Resume and stop of a session that is not running

A resume acts on a session that is prepared, paused, interrupted, stopped, or failed, and a stop acts on one that is prepared, interrupted, or paused as well as a live one. Neither launches anything: a resume re-arms the control to run, and the next start or resume launch runs the worker.

| Situation | Resume | Stop |
|---|---|---|
| The session is cleaned | Refused | Refused |
| The session holds an import receipt | The imported status is returned, and nothing is re-armed | Not applicable, the session is finalized |
| The session holds return evidence without an import | Refused | Not applicable |
| A runner process is alive when the lock is taken | Refused | Refused |
| The run ended on its own in the meantime | The real status is returned as it is | The real status is returned as it is |
| Otherwise | The model runtime the session started is stopped, and the control is re-armed to run | The model runtime the session started is stopped, and the session is recorded as stopped with its retained count |

Both wait for an exiting runner first and then decide under the session lock. A resume also requires the worker's prepared checkout and a received database at the migration head before it re-arms.

## Owned resources only

A session records only the resources it created or started: its keepalive process and the boot it ran in, whether it started or attempted to start the worker database service, whether it created the remote session directory, and whether the worker was prepared. Release touches only those.

A database service that another run started before the session is left alone. A worker database service that is already running without recorded ownership refuses the session, so release can never act on a resource the session did not create.

## Lost connection and recovery

Each worker step gets one ordinary invocation. A transient availability loss admits retries inside one bounded recovery episode whose budget is the configured remote-stage stop timeout, `TRANSLATION_CONTROLLER_STOP_TIMEOUT_SECONDS` in `config/translation.toml`, which the example sets to 660 seconds. The retries are spaced by `TRANSLATION_CONTROLLER_HEALTH_INTERVAL_SECONDS`, which the example sets to 2 seconds.

A completed worker helper that reports a nonzero status is a genuine failure and not an availability loss. It propagates at once, and its class and integer status are recorded in the stage failure record together with the step that was executing. A missing or malformed configuration value fails the same way.

An invocation that never reaches a reportable completion and does not recover inside the budget fails the step as a lost connection, and the available status is recorded. The session evidence, the retained output, and the owned resources stay, so a stop can verify the real state and return what the worker holds.

Every retry rechecks whether the run is wanted, so a pause or a stop that arrives during a recovery episode cancels the remaining retries instead of starting one more attempt. One recovery budget covers the initial bring-up and launch, and each mirrored status iteration gets its own budget.

The stage reports the content-free failure record on every status read, and a completed stop clears it. The record holds the executing step, the exception class, and an available integer status. [Stage lifecycle](/docs/operations/stage-lifecycle.md#failures-and-recovery) lists the steps.

## The periodic reboot

A [periodic reboot](/docs/reference/glossary.md#administration) restarts the worker after a configured amount of model run time. The clock of the session counts only the time a local model is loaded on the worker, it accumulates across model switches and pauses, and it samples at a completed unit of work and at every recorded failed generation attempt. Repeated local failures therefore reach the restart as well.

`WORKER_GPU_REBOOT_INTERVAL_MINUTES` in `config/worker.toml` sets the interval, and the example sets 120 minutes.

When a sample reaches the interval, the worker publishes a paused state with the restart due. The administration command releases the resources the session owns, restarts the worker once, proves that the worker came back, brings the session's resources up again, and launches the same session with its pending work. The session identity, the retained output, and the receipt do not change.

A pause or a stop that arrives before the restart issues no restart. The clock record belongs to one session and one worker boot, and a record from another boot reports not due and is not rewritten until a real checkpoint. [Inference scheduling and disposition](/docs/backend/inference/inference-scheduling.md#the-periodic-reboot) states the timing rule for the inference stage.

The stage status carries the last mirrored `reboot_due` value inside the progress member's worker status, and that value is unknown while the progress member carries no worker status. It is the last observation the session recorded rather than a current read of the worker, and a status read never turns it into a worker request.

## Status and report scope

`uv run python scripts/admin.py <stage> status` reads the durable state and the owned process. It starts no service and reaches no worker, so a remote stage reports the last status its run recorded.

A remote stage's status therefore refreshes from server state alone, while its two worker logs are read on demand. `uv run python scripts/admin.py logs read inference SESSION_ID worker-runner --lines N` and the same command with `worker-runtime` read the worker's own `runner.log` and `runtime.log` over the transport, and `keepalive` reads the shared session directory's `keepalive.log`. [Operator menu](/docs/operations/operator-menu.md#the-fixed-log-reads) lists every source and its refusals.

The server-side logs live beside the session receipt. A local stage's detached worker writes `runner.out` and `runner.err` there, and the keepalive log of a remote session sits in the shared session directory. The inference stage launches its server process with its output sent to the null device, so its two runner streams are reported as unavailable rather than written. A stop removes the two runner streams and the keepalive log with the rest of the session's scratch.

The coverage reports and the summaries read the selected dataset. The progress of a remote stage that has not returned is read from that stage's status instead, and the [Operator menu](/docs/operations/operator-menu.md#coverage-and-summaries) states that scope for every report entry.

## What a session keeps

A session keeps its evidence on both sides until its cleanup runs.

| Evidence | What it holds |
|---|---|
| Session record | The identity of the session, the source dataset, the revision, the stage, and the input snapshot |
| Stage policy | The configuration identity the stage binds to the session |
| Input snapshot and dump | The verified copy of the selected dataset that the worker restored |
| Control record | The requested action of the session |
| Worker state | The lifecycle, the completed count, and the measured active time of the run |
| Ownership records | The runner and runtime processes the session owns |
| Retained output | The finished work of the session, which its import writes into the worker's copy |
| Return snapshot and dump | The verified export of the worker database at the return |
| Import receipt | The proof that the retained output reached the worker's copy |
| Returned dataset receipt | The proof that the return passed the server verification |
