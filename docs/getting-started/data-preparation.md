# Preparing a dataset from the curriculum source

The preparation path fills the selected dataset with official curriculum data through the administration command and its four stages.

## What the path needs

- A copy set up by the [Installation](/docs/getting-started/installation.md) steps, with the Python dependencies installed, the configuration and environment files in place, and the database and embedding services built.
- `SELECTED_DATASET_ENABLED` set to true in `config/database.toml`, so each process resolves the selected dataset through the pointer under `ADMIN_STATE_ROOT`. The settings table below lists this key with the others.
- A prepared worker for translation and inference, which [Preparing the worker](/docs/getting-started/worker-stages.md#preparing-the-worker) describes.

## The commands in order

The block runs the path once, from enrollment to the first coverage and summary read. Run the commands in this order.

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

Every command on this page runs from the checkout root. Each command prints one JSON report, and a failure prints one JSON line holding the exception class name, plus one fixed line of guidance, and returns 1.

A run can also be paused with `pause` and continued with `resume` in place of `stop`, as [Stage lifecycle](/docs/operations/stage-lifecycle.md) describes. After a stage has filled the selected dataset, an in-place change reaches a browser holding cached reads on its next uncached read or reload after the feature web server restarts. A dataset promotion changes the reported identity on the next uncached read without a restart. The same operations are entries of the numbered [operator menu](/docs/operations/operator-menu.md), which `uv run python scripts/admin.py` with no argument opens.

## The settings to change

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

## Enroll the dataset

`setup datasets` selects a database as a dataset, once.

```bash
uv run python scripts/admin.py setup datasets
```

It starts the server database service when it is not running, migrates the configured database to the checkout's migration head, verifies it, writes the receipt, and selects it. The report is one JSON line: the dataset receipt, holding the dataset id, the database name, the enrollment kind, and a verification with the migration head, the row count of every table, the catalogue summary, and the teaching-text, embedding, and inference coverage reads. The initial enrollment carries the zero dataset id, no predecessor, and no dump digest.

An already-selected dataset is reused and returned as it is, and nothing is written. [Datasets](/docs/operations/datasets.md#enrolling-a-dataset) describes the receipt and the interrupted enrollment.

> [!IMPORTANT]
> Enroll before the first stage start. With `SELECTED_DATASET_ENABLED` true, a stage start, a worker session, and every dataset verification resolve the selected dataset through the pointer, and a missing pointer fails with setup guidance.

## Ingestion

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

## Embedding

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

## Hubs and the web restart

```bash
uv run python scripts/admin.py hubs
```

The command computes both embedding hub means from the stored chunk vectors of the selected dataset and writes the two files that the hub keys in `config/search.toml` name. Its report holds `catalogue_path`, `outcomes_path`, `chunk_count`, and `outcomes_chunk_count`. Both means are computed before the first write, so incomplete coverage writes neither file.

> [!IMPORTANT]
> Restart the web server after the hub write. A serving process of a site that serves embedding features reads both hub files when it starts and holds those values while it runs, so the written values reach the site at the next start. A web unit under the user manager restarts with `systemctl --user restart tuni-course-explorer-web.service`, one under the system manager with `sudo systemctl restart tuni-course-explorer-web.service`, and a foreground copy is stopped and started again. [The site web unit](/docs/getting-started/self-hosting.md#the-site-web-unit) gives both unit procedures.

## Coverage and summaries

The read-only reports read the selected dataset, not the progress of a stage that has not returned.

```bash
uv run python scripts/admin.py coverage teaching-text
uv run python scripts/admin.py coverage embedding
uv run python scripts/admin.py coverage inference
uv run python scripts/admin.py summary catalogue
uv run python scripts/admin.py summary inference
```

Each command prints one JSON report and one fixed scope line to standard error. The teaching-text coverage counts the effective text of the represented courses per field and language and lists the stale translations. The embedding coverage counts the total, pending, completed, and failed chunks. The catalogue summary counts the periods, courses, active courses, course versions, modules, and module versions. The inference summary counts the eligible, retained, published, and uncovered target courses with the retained cycle and its failures. [The operator menu](/docs/operations/operator-menu.md#coverage-and-summaries) lists the same entries.

## Migrating the selected dataset

```bash
uv run python scripts/admin.py migrate datasets
```

The migration is explicit maintenance. It applies the checkout's migration head to the selected database and returns a fresh verification of that database.

> [!IMPORTANT]
> Every stage must be idle with no live recorded process before the migration, and the server database service must be running. The command refuses before it changes anything when a stage is not idle or holds a live process. [The schema head and migration](/docs/operations/datasets.md#the-schema-head-and-migration) describes the guard.

## The administration command

A failure of an administration command prints one JSON line holding the exception class name, such as `{"error":"DatabaseSchemaMismatchError"}`, plus the return code of a failed subprocess, and then one fixed line of guidance for the operation. The guidance names the next step.

| Operation | Guidance line |
|---|---|
| Any operation with a missing or invalid setting | `check config/*.toml and this device's ignored .env, then retry the same command` |
| `setup datasets`, `setup worker`, `preflight` | `finish or stop retained stages before updates, then check the checkout branch and the configured origin` |
| A stage action | `inspect this tool's status, then retry its ordinary stop or resume as appropriate` |
| `migrate datasets` | `ordinary-stop all four stages, ensure the server db is running, then retry` |
| `dispose inference` | `ordinary-stop all four stages, select the verified returned selected dataset and keep the server db running at the current schema, then retry` |
| `target inference` | `select the dataset, ensure the server db is running at the current schema, then retry the target read` |
| `hubs` | `complete the embedding stage on the selected dataset, ensure the server db is running, then retry and restart the web server` |
| `coverage`, `summary` | `enroll the selected dataset and ensure the server PostgreSQL service is running` |

`DatabaseSchemaMismatchError` means the selected database is not at the checkout's migration head. Run `uv run python scripts/admin.py migrate datasets` once every stage is idle.

[Installation](/docs/getting-started/installation.md) lists the failures of the dependency, copy, and serving steps, and the [operator menu](/docs/operations/operator-menu.md#failures-and-exit-status) states the exit statuses of the administration command.
