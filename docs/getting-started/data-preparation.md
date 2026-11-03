# Preparing a dataset from the curriculum source

The preparation path fills the Working dataset with official curriculum data through the administration command's four stages while the site serves the Selected dataset.

## What the path needs

- A copy set up by the [Installation](/docs/getting-started/installation.md) steps, with the Python dependencies installed, the configuration and environment files in place, and the database and embedding services built.
- A Selected dataset enrolled under `ADMIN_STATE_ROOT`, and a copy of it assigned to Working. The real-database workflow enrolls the initial Selected dataset, so `POSTGRES_DB` names the example database and no second enrollment runs. A configured-database deployment that sets `POSTGRES_DB` to a real name enrolls it with `setup datasets`.
- A prepared worker for translation and inference, which [Preparing the worker](/docs/getting-started/worker-stages.md#preparing-the-worker) describes.

## The commands in order

The block runs the path once, from the copy to the first coverage and summary read. Run the commands in this order after the real-database workflow enrolled Selected.

```bash
uv run python scripts/admin.py datasets list
uv run python scripts/admin.py datasets copy-to-working SOURCE_DATASET_ID
uv run python scripts/admin.py ingestion start
uv run python scripts/admin.py ingestion status
uv run python scripts/admin.py ingestion stop
uv run python scripts/admin.py embedding start
uv run python scripts/admin.py embedding status
uv run python scripts/admin.py embedding stop
uv run python scripts/admin.py coverage teaching-text --role working
uv run python scripts/admin.py summary catalogue --role working
```

Every command on this page runs from the checkout root. Each command prints one JSON report, and a failure prints one JSON line holding the exception class name, plus one fixed line of guidance, and returns 1.

A run can also be paused with `pause` and continued with `resume` in place of `stop`, as [Stage lifecycle](/docs/operations/stage-lifecycle.md) describes. The stages write Working, so the site's Selected dataset and its serving artifacts are untouched while the pipeline runs. A Selected pointer change follows the restart procedure that [Operations](/docs/operations/README.md#derived-files-served-data-and-the-web-restart) states. The same operations are entries of the numbered [operator menu](/docs/operations/operator-menu.md), which `uv run python scripts/admin.py` with no argument opens.

## The settings to change

| Step | File | Key | Holds |
|---|---|---|---|
| Enrollment and copy | `config/database.toml` | `ADMIN_STATE_ROOT` | The repository-relative root that holds both role pointers, the dataset receipts, and the session evidence. The example sets `data/admin`. |
| Enrollment | `config/database.toml` | `EXAMPLE_POSTGRES_DB` | The configured database that the example workflow leaves unenrolled. The real-database workflow leaves `POSTGRES_DB` at this name and enrolls the named database through the Selected pointer. A configured-database deployment sets `POSTGRES_DB` to a different name and enrolls it with `setup datasets`. |
| Ingestion | `config/curriculum.toml` | `RAW_DATA_ROOT` | The repository-relative root that holds one directory per capture run. The example sets `data/raw`. |
| Ingestion | `config/curriculum.toml` | `KORI_BASE_URL` | The curriculum source base. The settings accept the anonymous canonical `https://sisu.tuni.fi/kori` alone. |
| Ingestion | `config/curriculum.toml` | `TUNI_UNIVERSITY_ID` | The university root the capture starts from. The example file carries a placeholder value. |
| Ingestion | `config/curriculum.toml` | `KORI_FIRST_ACADEMIC_YEAR` | The first academic year of the capture, written as a four-digit range such as `2006-2007`. |
| Ingestion | `config/curriculum.toml` | `CURRENT_ACADEMIC_YEAR` | The reference academic year of the run. Normalization chooses the representative version against it, and the first year must not be after it. |
| Ingestion | `config/curriculum.toml` | `ACTIVE_ACADEMIC_YEAR_WINDOW` | The number of academic years inside which a listed version makes a course active. The example sets 3. |
| Embedding | `config/search.toml` | `EMBEDDING_ARTIFACT_PATH`, `EMBEDDING_ARTIFACT_SHA256` | The pinned embedding model file and its digest. An embedding start requires the file at that path to match the digest. |

The same files hold the request pacing, the retry bounds, and the stage state roots, and their example values apply to the public source. [Configuration](/docs/backend/configuration.md) describes how the settings owner reads the subsystem files and the [environment file](/docs/reference/glossary.md#configuration).

## Enroll the dataset

The real-database workflow enrolls one named empty database as the initial Selected dataset. The database name comes from the workflow input, and `POSTGRES_DB` in `config/database.toml` names the example database. The report is one JSON line holding the site's external root address and the zero dataset id of the enrolled Selected dataset.

A configured-database deployment enrolls its configured database with `setup datasets` instead.

```bash
uv run python scripts/admin.py setup datasets
```

It starts the server database service when it is not running, migrates the configured database to the checkout's migration head, verifies it, writes the receipt, and selects it. An already-selected dataset is reused and returned as it is, and nothing is written.

`datasets list` prints the receipt id. `datasets copy-to-working SOURCE_DATASET_ID` creates a verified copy and publishes it as Working, which the stages then write. Every stage must be idle before the copy. [Datasets](/docs/operations/datasets.md#enrolling-a-dataset) describes the receipt, the named initial enrollment and the interrupted enrollment.

> [!IMPORTANT]
> Enroll and copy before the first stage start. A stage start, a worker session and every pipeline verification resolve the Working pointer, and a missing Working dataset fails with copy guidance.

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
> An ingestion stop that reaches idle deletes every raw capture run under `RAW_DATA_ROOT` except the one the stage retains for an incomplete capture. After a completed capture, no raw capture run is retained. The rows of the Working dataset are not touched, and a failed stop deletes nothing.

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

   A stop takes effect after the vectors of one batch are stored, so a partial run leaves the pending chunks for the next start. Each completed batch commits its own vectors, so a stopped run retains every batch it finished. The report is the idle status.

## Serving artifacts and the web restart

```bash
uv run python scripts/admin.py serving-artifacts
```

The command builds the serving artifact set for the site's embedding switch. Its report holds the artifact paths and counts, on a site that serves the embedding features the embedding paths and counts including `search_group_count` and `search_block_count`, and in both modes the study-fragment values. On a site that serves the embedding features, an incomplete current embedding coverage fails the build. [Serving artifact build](/docs/backend/text-and-vectors/serving-artifact-build.md#the-embedding-switch) states what each mode writes, the artifact family and the build transaction, and [Administration commands](/docs/backend/interfaces/administration-commands.md#the-serving-artifact-command) states what a failed build restores and how `--prune` cleans up after it.

The embedding menu and the console preparation action run the same build for the served dataset. This standalone build maintains a served dataset. It is not how pipeline work is published, because the stages write Working. Publish Working with `datasets copy-to-selected`, which builds the copy and then switches, restarts and proves it, as [Datasets](/docs/operations/datasets.md) states. `--dataset ID` builds an in-pipeline dataset. `--prune` is separate housekeeping after a successful restart. It builds nothing, changes no table or `current` target, and removes the obsolete builds, the other year families' builds and owned temporary outputs of the target database, while keeping the `current` build, unknown files and other dataset namespaces. [Serving artifact build](/docs/backend/text-and-vectors/serving-artifact-build.md#the-artifact-family-the-build-directory-and-the-embedding-directory) states which embedding directories it retains in each mode.

> [!IMPORTANT]
> A completed build reaches the site after the full supervisor restart that [Operations](/docs/operations/README.md#derived-files-served-data-and-the-web-restart) states, and `serving-artifacts --prune` runs after that restart succeeds. The artifact command replaces no running worker and restarts no unit.

## Coverage and summaries

The read-only reports read the dataset role they name, not the progress of a stage that has not returned. The pipeline reports name Working.

```bash
uv run python scripts/admin.py coverage teaching-text --role working
uv run python scripts/admin.py coverage embedding --role working
uv run python scripts/admin.py coverage inference --role working
uv run python scripts/admin.py summary catalogue --role working
uv run python scripts/admin.py summary inference --role working
```

Each command prints one JSON report and one fixed scope line to standard error. The teaching-text coverage counts the effective text of the represented courses per field and language and lists the stale translations. The embedding coverage counts the total, pending, completed, and failed chunks. The catalogue summary counts the periods, courses, active courses, course versions, modules, and module versions. The inference summary counts the eligible, retained, published, and uncovered target courses with the retained cycle and its failures. [The operator menu](/docs/operations/operator-menu.md#coverage-and-summaries) lists the same entries.

## Migrating a dataset role

```bash
uv run python scripts/admin.py migrate selected
uv run python scripts/admin.py migrate working
```

The migration is explicit maintenance. It applies the checkout's migration head to the named role's database and returns a fresh verification of that database.

> [!IMPORTANT]
> Every stage must be idle with no live recorded process before a Working migration, and the server database service must be running. A Working migration refuses before it changes anything when a stage is not idle or holds a live process. A Selected migration does not read the stage state. [The schema head and migration](/docs/operations/datasets.md#the-schema-head-and-migration) describes the guard.

## The administration command

A failure prints one JSON line holding the exception class name, plus the return code of a failed subprocess, and then one fixed line of guidance for the operation. [Administration commands](/docs/backend/interfaces/administration-commands.md#the-administration-command) states the output and that each command prints its own fixed guidance, and [Operator menu](/docs/operations/operator-menu.md#failures-and-exit-status) states the exit statuses.

`DatabaseSchemaMismatchError` means the named role's database is not at the checkout's migration head. [The schema head and migration](/docs/operations/datasets.md#the-schema-head-and-migration) states the migration commands and their guards.

[Installation](/docs/getting-started/installation.md) lists the failures of the dependency, copy, and serving steps.
