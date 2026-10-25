# Worker stages

The worker runs translation and inference on its own copy of the selected dataset, and each session returns that copy.

Translation and inference run on the worker, a separate machine that runs the model runtimes. Each run of one of them is a worker session, and the selected dataset changes only at the verified return of that session. [Worker sessions](/docs/operations/worker-sessions.md) describes the session in full.

## What the worker stages need

- A copy set up by the [Installation](/docs/getting-started/installation.md) steps, with the selected dataset enrolled. [Enroll the dataset](/docs/getting-started/data-preparation.md#enroll-the-dataset) describes the enrollment.
- `SELECTED_DATASET_ENABLED` set to true in `config/database.toml`, so each stage resolves the selected dataset through the pointer under `ADMIN_STATE_ROOT`.
- The worker connection settings below, and a prepared worker before the first remote stage start.

## The worker connection settings

What the operator configures for the worker:

| File | Key | Holds |
|---|---|---|
| `.env` | `TRANSLATION_CONTROLLER_SSH_TARGET` | The SSH target of the worker. The example file carries a placeholder value. |
| `.env` | `TRANSLATION_CONTROLLER_WSL_DISTRIBUTION` | The WSL distribution on that target that holds the checkout. The example file carries a placeholder value. |
| `.env` | `TRANSLATION_CONTROLLER_WORKER_PROJECT_ROOT` | The absolute path of the project checkout inside that distribution. The example file carries a placeholder value. |
| `config/worker.toml` | `WORKER_SETUP_PROJECT_URL` | The expected origin URL. The worker update compares both checkout origins against it, the preflight compares the server checkout origin against it, and the example file carries a placeholder value. |
| `config/worker.toml` | `TRANSLATION_CONTROLLER_SSH_CONNECT_TIMEOUT_SECONDS` | The bound on one connect attempt, 10 seconds in the example. |
| `config/worker.toml` | `WORKER_SETUP_TIMEOUT_SECONDS` | The bound on each remote install, download, or build step, four hours in the example. |
| `config/worker.toml` | `WORKER_GPU_REBOOT_INTERVAL_MINUTES` | The loaded-model run time after which the worker restarts, 120 minutes in the example. |
| `config/translation.toml` | `TRANSLATION_CONTROLLER_HEALTH_INTERVAL_SECONDS`, `TRANSLATION_CONTROLLER_STOP_TIMEOUT_SECONDS` | The retry and poll interval, 2 seconds in the example, and the recovery and stop bound, 660 seconds in the example. |
| `config/translation.toml`, `config/inference.toml` | The artifact keys | The pinned model files and runtimes the worker must hold, named by `TRANSLATION_ARTIFACT_PATH`, `TRANSLATION_ARTIFACT_SHA256`, `INFERENCE_PRIMARY_ARTIFACT_PATH`, `INFERENCE_PRIMARY_ARTIFACT_SHA256`, and the rerank artifact keys. |
| `config/translation.toml`, `config/inference.toml` | `TRANSLATION_CONTROLLER_STATE_ROOT`, `INFERENCE_CONTROLLER_STATE_ROOT` | The repository-relative roots that hold each controller's recorded state. |

What the code requires of the worker, and what each requirement follows from:

- The target accepts an SSH connection without a password prompt, because every remote command runs with batch mode set.
- The configured WSL distribution exists on that target and holds the checkout at the configured project root, because every remote command runs inside that distribution.
- The SSH target and the WSL distribution are each 1 to 64 ASCII letters, digits, underscore, dot, or hyphen.
- The project root is an absolute path without dot components or percent characters.
- The account runs `sudo` without a password prompt, because the setup bootstrap installs system packages and pulls the database service image through `sudo` over a transport that has no terminal.
- The checkout is on a non-detached Git branch, because the update reads the current branch before it switches to the selected origin branch. The update fetches the selected origin branch, refuses a local branch ahead of or diverged from the origin branch, switches the checkout onto the branch, and pulls the branch fast-forward. Git refuses an operation that would overwrite a local change.
- Docker and Docker Compose are available, because the pinned database image runs through the Compose bridge.

[Worker transport and datasets](/docs/operations/worker-transport.md) describes the transport and the connection values.

## Preparing the worker

1. Prepare or update the worker.

   ```bash
   uv run python scripts/admin.py setup worker
   ```

   The command fast-forwards the worker checkout to one origin branch, installs its locked project environment, streams the setup bootstrap, and prepares the pointed resources: the configured system packages, the pinned database service image, the pinned model artifacts, and the pinned runtimes. Its report holds the worker branch, its revision, whether the server checkout branch differs from its origin counterpart, and the resource readiness.

   `--branch BRANCH` selects the origin branch, and the default is `main`. `--code-only` updates the code and its locked environment without preparing the pointed resources, and its report carries no resource readiness. The operator menu offers the same operation, as [Setup and preflight](/docs/operations/setup-and-preflight.md) describes.

2. Check the prepared worker without changing it.

   ```bash
   uv run python scripts/admin.py preflight
   ```

   The preflight reads the branch and HEAD of the server checkout and of the worker checkout, checks the worker's locked environment, and reads the worker resources. It installs nothing, prints the same report shape, and returns 1 when the locked environment or a resource is missing, with `resources.ready` false and `resources.missing` naming the components. A missing component is prepared by the setup command above.

> [!IMPORTANT]
> Prepare the worker before the first remote stage start. A start validates the received database, and it never fetches, installs, or downloads.

## Translation

1. Start the stage.

   ```bash
   uv run python scripts/admin.py translation start
   ```

   The start captures a session: it dumps the selected dataset, transfers it to the worker, and the worker restores its own copy before the one detached worker helper translates. The report is the lifecycle status with the session id, the revision, the options, and the recorded progress.

2. Read the status.

   ```bash
   uv run python scripts/admin.py translation status
   ```

   The status reads the recorded state and reaches no worker, so it reports the last status the run recorded, with the worker's lifecycle and its completed count.

3. Stop the stage.

   ```bash
   uv run python scripts/admin.py translation stop
   ```

   The stop publishes a stop request, waits for the worker to exit, takes effect between two translated cells, finalizes the retained output into the worker's copy, returns that copy, and returns the stage to idle.

## Inference

1. Start the stage.

   ```bash
   uv run python scripts/admin.py inference start
   ```

   Inference proposes inferred prerequisites and equivalence groups for the target courses. The start takes a session over the selected dataset, and its progress names the preparation step of that session, `snapshot`, `transfer`, `restore`, or `job`, or the mirrored worker status once running work begins.

2. Read the status.

   ```bash
   uv run python scripts/admin.py inference status
   ```

   The status reads the recorded state and reaches no worker, so it reports the last status the run recorded.

3. Stop the stage.

   ```bash
   uv run python scripts/admin.py inference stop
   ```

   The stop publishes the finished proposals and equivalence groups into the worker's copy, returns that copy, and returns the stage to idle. [Inference scheduling and disposition](/docs/backend/inference/inference-scheduling.md) describes the cycle.

The stage holds one further entry, the operator decision for one target course:

```bash
uv run python scripts/admin.py dispose inference TARGET_ID {nothing|done|failed}
```

The decision requires every stage to be idle, a verified returned selected dataset, and the current schema head. [Operator disposition](/docs/backend/inference/inference-scheduling.md#operator-disposition) states what each decision does.

## The return and the rotation

Every remote stage ends the same way. The worker exports a fresh snapshot of its database, the command downloads it and checks it against the snapshot taken when the session started, restores it into the derived server database, writes the returned receipt, selects it, and rotates the older datasets. The worker database is dropped once the server receipt exists.

> [!WARNING]
> The rotation retains the selected dataset and its immediate predecessor, and it deletes the database and the retained dump of every older dataset in the receipt chain. The rows of a dataset outside the retained pair are not recoverable from the chain. Rotation deletes a database and its dump alone, and the receipt of every dataset is read from the state root. [Rotation](/docs/operations/datasets.md#rotation) lists the guards and the outcomes.
