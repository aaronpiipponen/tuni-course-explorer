# Data preparation

Data preparation fills the database behind a running copy, either from the example dataset or from the public curriculum source, as ordered procedures.

## What the steps need

- A copy set up by the [Installation](/docs/getting-started/installation.md) steps, with the Python dependencies installed, the configuration and environment files in place, and the database and embedding services built.
- A prepared worker for the prepared-dataset path, which [Preparing the worker](#preparing-the-worker) describes.

## The two paths

Two different sources can fill the database, and each has its own command and its own setting.

| Path | Source of the data | Database it fills | Commands |
|---|---|---|---|
| The example dataset | The invented fixture under `data/mock/` | The configured database, named by `POSTGRES_DB` in `config/database.toml` | `uv run python scripts/mock_data.py` |
| A prepared dataset | The public curriculum source and the model stages | The selected dataset, named by the pointer under `ADMIN_STATE_ROOT` | `uv run python scripts/admin.py` |

The example dataset path needs no request to the curriculum source, and no model runs. The prepared dataset path captures the source, normalizes what it captured, embeds the teaching text, and runs the two worker stages to add translations and inferred prerequisites.

> [!IMPORTANT]
> The two paths use the selected-dataset switch `SELECTED_DATASET_ENABLED` in `config/database.toml` in opposite ways. The loader writes the configured database and refuses a configuration with the switch set to true. The prepared-dataset path sets the switch to true, because it stages and reports on the selected dataset.

Every command on this page runs from the checkout root, and every administration command prints one JSON report line.

## The example dataset

The example dataset is invented, and the loader imports it through the same capture and normalization path a real capture uses. `scripts/mock_data.py` parses one action with its options and delegates once to `course_explorer.mock_data.run_mock_data_command`. [The example data loader](/docs/backend/interfaces/command-line.md#the-example-data-loader) describes where the action sits beside the feature commands, and [command adapters](/docs/backend/interfaces/command-adapters.md) lists the return type of each action.

### The loader actions

| Action | What it does | What it prints |
|---|---|---|
| `load-curriculum` | Registers the fixture as one completed capture under the raw root, then applies the normalization batch to the configured database. | One JSON line: the normalization report, with the run identity, the period, canonical course, active-course, module, and version counts, and the per-version classification counts. |
| `load` | Runs the `load-curriculum` work and then imports the bundled vectors into the same database through the embedding reconciliation owner. | One JSON line: the embedding coverage of the dataset, with `total_chunk_count`, `pending_count`, `completed_count`, `failed_count`, and one `fields` row per field, language, and text origin. |
| `write-artifacts` | Prepares the fixture capture like the loader, reads the stored vectors of the configured database, and writes the bundled vector file and both hub files. It writes no database row. | Nothing, and the command returns 0. |

The three options:

| Option | Default | Holds |
|---|---|---|
| `--fixture-dir` | `data/mock` | The directory that holds the authored curriculum documents and the bundled vector file. |
| `--raw-root` | `data/mock-import` | The repository-relative root that holds the capture the loader registers or reuses. |
| `--hubs-dir` | `config/derived` | The directory that receives the two hub files. |

Each action reads the fixture and sends no request to the curriculum source and none to the embedding service.

### Loading the example dataset

1. Apply the schema migrations.

   ```bash
   uv run python -m alembic upgrade head
   ```

   The migration creates or updates the database the settings name, at the single head revision of the checkout. The loader requires the database at that head and refuses a database at any other revision, so run this step after an update to the checkout.

   > [!IMPORTANT]
   > Set `SELECTED_DATASET_ENABLED` to false in `config/database.toml` before an import action. The loader refuses a configuration with the switch set to true, and the example file sets it to false.

2. Load the curriculum and its vectors.

   ```bash
   uv run python scripts/mock_data.py load
   ```

   The loader imports the fixture through the capture and normalization path, adds the bundled vectors of its chunks, and prints one JSON line holding the embedding coverage of the loaded dataset, with the total, pending, completed, and failed chunk counts and one row per field, language, and text origin.

### Loading the curriculum alone

The `load-curriculum` action stops after the curriculum and leaves the vectors out, so the dataset holds courses, modules, and rules with no embeddings.

```bash
uv run python scripts/mock_data.py load-curriculum
```

It prints the normalization report, which counts the periods, canonical courses, active courses, modules, and versions the batch wrote, with the per-version classification counts. The action sends no request to the embedding service.

### Re-running an import action

A second `load` on an already-loaded database completes and prints the same coverage. The loader reuses the sole retained capture under `--raw-root` when its stored responses match the fixture, requires the stored curriculum to be exactly the fixture's, and completes nothing that is already stored.

The reuse is conditional, and the failure messages name the condition:

| Situation | What the loader does |
|---|---|
| The database holds no course, module, or source snapshot | The import proceeds. |
| The database holds exactly the fixture's canonical groups and source rows | The import proceeds and reuses the retained capture. |
| The database holds any other curriculum | It refuses with `database already holds curriculum outside the fictional mock fixture`. |
| The retained capture holds different response bytes than the fixture | It refuses with `retained mock import manifest does not match the current fixture`. |
| More than one capture is retained under `--raw-root` | It refuses with `multiple mock import manifests are ambiguous`. |

### Writing the bundled vectors and the hubs

`write-artifacts` writes three files from the stored vectors of the configured database: the bundled vector file at `data/mock/embeddings.json`, and the two hub files under `--hubs-dir`. The hub files are `embedding-hub.json` and `embedding-outcomes-hub.json`, and they are the files that `EMBEDDING_HUB_VECTOR` and `EMBEDDING_OUTCOMES_HUB_VECTOR` in `config/search.toml` name.

```bash
uv run python scripts/mock_data.py load
uv run python scripts/mock_data.py write-artifacts --hubs-dir config/derived
```

Run the action when the fixture or its stored vectors changed and the bundled file and the hub files must match them again. The bundled file is the artifact an import reads, so a bundle that does not name the fixture's chunks fails the import:

| Situation | Message |
|---|---|
| The bundle names a different chunk set than the fixture | `bundled mock embeddings do not match the current fixture chunks` |
| The bundle was built from a different teaching text | `bundled mock embeddings input identity does not match the current fixture` |

The action needs complete embedding coverage of the configured database: every desired chunk of a represented course must hold a completed compatible vector, and at least one learning-outcomes chunk must exist. Both hub means are computed and both temporary files are staged before either hub destination changes, so a dataset that is not ready leaves the bundled file and both hub files as they are. The bundled file is written before the hub files are staged, and the staged hub files then replace their destinations in sequence. A failure during that sequence can leave the two hub destinations in different states, with the catalogue hub updated and the outcomes hub holding its earlier content. A database that holds curriculum outside the fixture is refused before any file is touched, with the same message as the loader.

The values in the hub files reach a running site when its process starts. Restart the web server after a hub write, as [the operations overview](/docs/operations/README.md#derived-files-and-the-web-restart) describes. [Embeddings](/docs/backend/text-and-vectors/embeddings.md#the-hubs) describes what the two hubs are.

## A prepared dataset from the public curriculum source

This path fills the selected dataset with official data through the administration command. Run the commands in this order.

```bash
uv run python scripts/admin.py setup datasets
uv run python scripts/admin.py ingestion start
uv run python scripts/admin.py ingestion status
uv run python scripts/admin.py ingestion stop
uv run python scripts/admin.py embedding start
uv run python scripts/admin.py embedding status
uv run python scripts/admin.py embedding stop
uv run python scripts/admin.py hubs
uv run python scripts/admin.py coverage teaching-text
uv run python scripts/admin.py summary catalogue
```

Each command prints one JSON report. A run can also be paused with `pause` and continued with `resume` in place of `stop`, as [Stage lifecycle](/docs/operations/stage-lifecycle.md) describes. The same operations are entries of the numbered [operator menu](/docs/operations/operator-menu.md), which `uv run python scripts/admin.py` with no argument opens. A failure prints one JSON line holding the exception class name, plus one fixed line of guidance, and returns 1.

### The settings to change

| Step | File | Key | Holds |
|---|---|---|---|
| Every step | `config/database.toml` | `SELECTED_DATASET_ENABLED` | Set it to true, so each process resolves the selected dataset through the pointer under `ADMIN_STATE_ROOT`. The reports refuse while it is false. |
| Enrollment | `config/database.toml` | `ADMIN_STATE_ROOT` | The repository-relative root that holds the pointer, the dataset receipts, and the session evidence. The example sets `data/admin`. |
| Ingestion | `config/curriculum.toml` | `RAW_DATA_ROOT` | The repository-relative root that holds one directory per capture run. The example sets `data/raw`. |
| Ingestion | `config/curriculum.toml` | `KORI_BASE_URL` | The curriculum source base. The settings accept the anonymous canonical `https://sisu.tuni.fi/kori` alone. |
| Ingestion | `config/curriculum.toml` | `TUNI_UNIVERSITY_ID` | The university root the capture starts from. The example file carries a placeholder value. |
| Ingestion | `config/curriculum.toml` | `KORI_FIRST_ACADEMIC_YEAR` | The first academic year of the capture, written as a four-digit range such as `2006-2007`. |
| Ingestion | `config/curriculum.toml` | `CURRENT_ACADEMIC_YEAR` | The reference academic year of the run. Normalization chooses the representative version against it, and the first year must not be after it. |
| Ingestion | `config/curriculum.toml` | `ACTIVE_ACADEMIC_YEAR_WINDOW` | The number of academic years inside which a listed version makes a course active. The example sets 3. |
| Embedding | `config/search.toml` | `EMBEDDING_ARTIFACT_PATH`, `EMBEDDING_ARTIFACT_SHA256` | The pinned embedding model file and its digest. An embedding start requires the file at that path to match the digest. |
| Hubs | `config/search.toml` | `EMBEDDING_HUB_VECTOR`, `EMBEDDING_OUTCOMES_HUB_VECTOR` | The two hub files the hub write fills, by path. The example names them under `config/derived/`. |

The same files hold the request pacing, the retry bounds, and the stage state roots, and their example values apply to the public source. [Configuration](/docs/backend/configuration.md) describes how the settings owner reads the subsystem files and the [environment file](/docs/reference/glossary.md#configuration).

### Enroll the dataset

`setup datasets` selects a database as a dataset, once.

```bash
uv run python scripts/admin.py setup datasets
```

It starts the server database service when it is not running, migrates the configured database to the checkout's migration head, verifies it, writes the receipt, and selects it. The report is one JSON line: the dataset receipt, holding the dataset id, the database name, the enrollment kind, the checkout revision, and a verification with the migration head, the row count of every table, the catalogue summary, and the teaching-text, embedding, and inference coverage reads. The initial enrollment carries the zero dataset id, no predecessor, and no dump digest.

An already-selected dataset is reused and returned as it is, and nothing is written. [Datasets](/docs/operations/datasets.md#enrolling-a-dataset) describes the receipt and the interrupted enrollment.

> [!IMPORTANT]
> Enroll before the first stage start. With `SELECTED_DATASET_ENABLED` true, a stage start, a worker session, and every dataset verification resolve the selected dataset through the pointer, and a missing pointer fails with setup guidance.

### Ingestion

Ingestion runs as one stage with two steps: the capture stores exactly what the curriculum source returned, and normalization validates the completed capture and converts it into official courses, modules, versions, and rules. [Ingestion](/docs/backend/catalogue/ingestion.md) describes the two steps.

1. Start the stage.

   ```bash
   uv run python scripts/admin.py ingestion start
   ```

   The command reserves the stage, starts the database service when it is not running, and launches one detached worker. It returns once the launch is acknowledged, and the work continues in that worker. The report holds the stage name, the lifecycle, the session id, the checkout revision, the options, and the progress.

   The start requires the configured source base and university root, and the database at the checkout's migration head.

2. Read the status.

   ```bash
   uv run python scripts/admin.py ingestion status
   ```

   The status reads the recorded state and writes nothing. Its progress names the step the run reached, one of `selecting`, `verification`, `capture`, `before_normalization`, `normalization`, and `complete`, with the count of stored responses and the count of verified responses. The same report carries a measured rate and a projected remaining time when the recorded progress supports them.

3. Stop the stage.

   ```bash
   uv run python scripts/admin.py ingestion stop
   ```

   The stop publishes a stop request, waits for the owned worker to exit, finalizes the completed work, releases the services the session started, and returns the stage to idle. The report is the idle status.

> [!IMPORTANT]
> A stop with partial coverage is a valid end of a run. The stage returns to idle with the pending rows marked, the completed capture is retained, and the next start continues that capture rather than beginning a fresh one. [Stage lifecycle](/docs/operations/stage-lifecycle.md#the-boundaries-of-a-run) lists the boundaries at which a stop takes effect.

> [!WARNING]
> An ingestion stop that reaches idle deletes every raw capture run under `RAW_DATA_ROOT` except the one the stage retains for an incomplete capture. After a completed capture, no raw capture run is retained. The rows of the selected dataset are not touched, and a failed stop deletes nothing.

### Embedding

1. Start the stage.

   ```bash
   uv run python scripts/admin.py embedding start
   ```

   The stage starts the database service and the embedding service it owns, and it stops that embedding service when the run ends. Its report is the lifecycle status of the started session. The start requires the file at `EMBEDDING_ARTIFACT_PATH` to be a regular file that matches `EMBEDDING_ARTIFACT_SHA256`, and the database at the checkout's migration head. A missing or mismatching file refuses the start before any service starts.

2. Stop the stage after the vectors are stored.

   ```bash
   uv run python scripts/admin.py embedding stop
   ```

   A stop takes effect after the vectors of one batch are stored, so a partial run leaves the pending chunks for the next start. The vectors commit when the run completes, so finalization writes nothing more. The report is the idle status.

### Hubs and the web restart

```bash
uv run python scripts/admin.py hubs
```

The command computes both embedding hub means from the stored chunk vectors of the selected dataset and writes the two files that the hub keys in `config/search.toml` name. Its report holds `catalogue_path`, `outcomes_path`, `chunk_count`, and `outcomes_chunk_count`. Both means are computed before the first write, so incomplete coverage writes neither file.

> [!IMPORTANT]
> Restart the web server after the hub write. A serving process of a site that serves embedding features reads both hub files when it starts and holds those values while it runs, so the written values reach the site at the next start. A copy under systemd restarts with `systemctl --user restart tuni-course-explorer-web.service`, and a foreground copy is stopped and started again. [Self-hosting](/docs/getting-started/self-hosting.md) gives the unit commands.

### Coverage and summaries

The read-only reports read the selected dataset, not the progress of a stage that has not returned.

```bash
uv run python scripts/admin.py coverage teaching-text
uv run python scripts/admin.py coverage embedding
uv run python scripts/admin.py coverage inference
uv run python scripts/admin.py summary catalogue
uv run python scripts/admin.py summary inference
```

Each command prints one JSON report and one fixed scope line to standard error. The teaching-text coverage counts the effective text of the represented courses per field and language and lists the stale translations. The embedding coverage counts the total, pending, completed, and failed chunks. The catalogue summary counts the periods, courses, active courses, course versions, modules, and module versions. The inference summary counts the eligible, retained, published, and uncovered target courses with the retained cycle and its failures. [The operator menu](/docs/operations/operator-menu.md#coverage-and-summaries) lists the same entries.

### Migrating the selected dataset

```bash
uv run python scripts/admin.py migrate datasets
```

The migration is explicit maintenance. It applies the checkout's migration head to the selected database and returns a fresh verification of that database.

> [!IMPORTANT]
> Every stage must be idle with no live recorded process before the migration, and the server database service must be running. The command refuses before it changes anything when a stage is not idle or holds a live process. [The schema head and migration](/docs/operations/datasets.md#the-schema-head-and-migration) describes the guard.

## The worker stages

Translation and inference run on the worker, a separate machine that holds its own copy of the selected dataset and runs the model runtimes. Each run of one of them is a worker session, and the selected dataset changes only at the verified return of that session. [Worker sessions](/docs/operations/worker-sessions.md) describes the session in full.

### The worker connection settings

What the operator configures for the worker:

| File | Key | Holds |
|---|---|---|
| `.env` | `TRANSLATION_CONTROLLER_SSH_TARGET` | The SSH target of the worker. The example file carries a placeholder value. |
| `.env` | `TRANSLATION_CONTROLLER_WSL_DISTRIBUTION` | The WSL distribution on that target that holds the checkout. The example file carries a placeholder value. |
| `.env` | `TRANSLATION_CONTROLLER_WORKER_PROJECT_ROOT` | The absolute path of the project checkout inside that distribution. The example file carries a placeholder value. |
| `config/worker.toml` | `WORKER_SETUP_PROJECT_URL` | The expected origin URL. The worker update and the preflight compare the worker checkout origin against it, and the example file carries a placeholder value. |
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
- The checkout has no uncommitted or untracked changes and sits on the selected origin branch, because the update is a fast-forward pull and refuses a local branch that is ahead of or diverged from its origin.
- Docker and Docker Compose are available, because the pinned database image runs through the Compose bridge.

[Worker transport and datasets](/docs/operations/worker-transport.md) describes the transport and the connection values.

### Preparing the worker

1. Prepare or update the worker.

   ```bash
   uv run python scripts/admin.py setup worker
   ```

   The command fast-forwards the worker checkout to one origin branch, installs its locked project environment, streams the setup bootstrap, and prepares the pointed resources: the configured system packages, the pinned database service image, the pinned model artifacts, and the pinned runtimes. Its report holds the worker branch, its revision, whether the server checkout branch differs from its origin counterpart, and the resource readiness.

   `--branch BRANCH` selects the origin branch, and the default is `main`. `--code-only` updates the code and its locked environment without preparing the pointed resources, and its report carries no resource readiness. The same operation is [an operator menu entry](/docs/operations/operator-menu.md#setup-and-preflight).

2. Check the prepared worker without changing it.

   ```bash
   uv run python scripts/admin.py preflight
   ```

   The preflight reads the prepared code and the prepared resources and installs nothing. It prints the same report shape and returns 1 when a resource is missing, with `resources.ready` false and `resources.missing` naming the components. A missing component is prepared by the setup command above.

> [!IMPORTANT]
> Prepare the worker before the first remote stage start. A start validates the prepared checkout and the received database, and it never fetches, installs, or downloads.

### Translation

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

### Inference

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

### The return and the rotation

Every remote stage ends the same way. The worker exports a fresh snapshot of its database, the command downloads it and checks it against the snapshot taken when the session started, restores it into the derived server database, writes the returned receipt, selects it, and rotates the older datasets. The worker database is dropped once the server receipt exists.

> [!WARNING]
> The rotation retains the selected dataset and its immediate predecessor, and it deletes the database and the retained dump of every older dataset in the receipt chain. The rows of a dataset outside the retained pair are not recoverable from the chain. Rotation deletes a database and its dump alone, and the receipt of every dataset is read from the state root. [Rotation](/docs/operations/datasets.md#rotation) lists the guards and the outcomes.

## Troubleshooting

### The example data loader

The loader prints its own failure message.

| Message | Cause | Fix |
|---|---|---|
| `mock data import refuses a selected-dataset enabled configuration` | `SELECTED_DATASET_ENABLED` is true in `config/database.toml`. | Set it to false for the example dataset path, then run the action again. |
| `the received database does not match the executing checkout's single Alembic head` | The loader opened a database that is not at the checkout's migration head. | Run `uv run python -m alembic upgrade head`, then run the action again. |
| `database already holds curriculum outside the fictional mock fixture` | The configured database holds curriculum that is not the example dataset. | Point the loader at an empty configured database, or use the prepared-dataset path. |
| `retained mock import manifest does not match the current fixture` | The capture retained under `--raw-root` holds different response bytes than the fixture. | Remove the retained capture directory, or point `--raw-root` at an empty path. |
| `multiple mock import manifests are ambiguous` | More than one capture is retained under `--raw-root`. | Leave the one capture the run continues and remove the others, or point `--raw-root` at an empty path. |
| `bundled mock embeddings do not match the current fixture chunks` | The bundled vector file names a different chunk set than the fixture. | Restore the bundled file that matches the fixture, or rebuild it with `write-artifacts` from a database whose stored vectors match the fixture's chunks. |

### The administration command

A failure of an administration command prints one JSON line holding the exception class name, such as `{"error":"DatabaseSchemaMismatchError"}`, plus the return code of a failed subprocess, and then one fixed line of guidance for the operation. The guidance names the next step.

| Operation | Guidance line |
|---|---|
| Any operation with a missing or invalid setting | `check config/*.toml and this device's ignored .env, then retry the same command` |
| `setup datasets`, `setup worker`, `preflight` | `finish or stop retained stages before updates, then check the prepared clean checkout and the configured origin` |
| A stage action | `inspect this tool's status, then retry its ordinary stop or resume as appropriate` |
| `migrate datasets` | `ordinary-stop all four stages, ensure the server db is running, then retry` |
| `dispose inference` | `ordinary-stop all four stages, select the verified returned selected dataset and keep the server db running at the current schema, then retry` |
| `hubs` | `complete the embedding stage on the selected dataset, ensure the server db is running, then retry and restart the web server` |
| `coverage`, `summary` | `enroll the selected dataset and ensure the server PostgreSQL service is running` |

`DatabaseSchemaMismatchError` means the selected database is not at the checkout's migration head. Run `uv run python scripts/admin.py migrate datasets` once every stage is idle.

[Installation](/docs/getting-started/installation.md) lists the failures of the dependency, copy, and serving steps, and the [operator menu](/docs/operations/operator-menu.md#failures-and-exit-status) states the exit statuses of the administration command.
