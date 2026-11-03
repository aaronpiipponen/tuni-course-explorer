# The example dataset

The example dataset is invented, and the loader imports it into the configured database and writes its bundled vectors and serving artifacts in separate actions.

## What the loader needs

- A copy set up by the [Installation](/docs/getting-started/installation.md) steps, with the Python dependencies installed and the configuration and environment files in place.
- The database service running, and the database at the checkout's migration head. The first step below applies the migration.
- A bootstrap dataset state root under `ADMIN_STATE_ROOT`: no Selected or Working pointer and no dataset or session records. The loader refuses an enrolled root. The example configuration sets `POSTGRES_DB` and `EXAMPLE_POSTGRES_DB` to `course_explorer`.

## Leaving example mode

The example path serves the configured database while the state root stays bootstrap. A deployment starts with the example dataset when `POSTGRES_DB` equals `EXAMPLE_POSTGRES_DB`.

To prepare a real dataset, give the configured database a different name in `config/database.toml`, create that database with `createdb` or start from a cleared disposable volume, and run `setup datasets`. A name other than the configured example name makes deploy enrollment and the explicit setup enroll the database as Selected. Clearing a volume also clears `ADMIN_STATE_ROOT` when that root lives on the same volume, so the state root becomes bootstrap and must be enrolled again.

## The loader actions

The loader imports the fixture through the same capture and normalization path a real capture uses. `scripts/mock_data.py` parses one action with its options and delegates once to `course_explorer.mock_data.run_mock_data_command`. [The example data loader](/docs/backend/interfaces/administration-commands.md#the-example-data-loader) describes where the action sits beside the administration commands, and [command adapters](/docs/backend/interfaces/command-adapters.md) lists the return type of each action.

| Action | What it does | What it prints |
|---|---|---|
| `load-curriculum` | Registers the fixture as one completed capture under the raw root, then applies the normalization batch to the configured database. | One JSON line: the normalization report, with the run identity, the period, canonical course, active-course, module, and version counts, and the per-version classification counts. |
| `load` | Runs the `load-curriculum` work and then imports the bundled vectors into the same database through the embedding reconciliation owner. | One JSON line: the embedding coverage of the dataset, with `total_chunk_count`, `pending_count`, `completed_count`, `failed_count`, and one `fields` row per field, language, and text origin. |
| `write-artifacts` | Prepares the fixture capture like the loader and builds the serving artifact set for the site's embedding switch through the one artifact builder. | One JSON line: the `ServingArtifactsReport` with every built path and count. |
| `write-bundle` | Prepares the fixture capture and rewrites the tracked bundled vector file from the stored vectors of that fixture. | Nothing. |

The two options:

| Option | Default | Holds |
|---|---|---|
| `--fixture-dir` | `data/mock` | The directory that holds the authored curriculum documents and the bundled vector file. |
| `--raw-root` | `data/mock-import` | The repository-relative root that holds the capture the loader registers or reuses. |

Each action reads the fixture and sends no request to the curriculum source and none to the embedding service.

## Loading the example dataset

1. Apply the schema migrations.

   ```bash
   uv run python -m alembic upgrade head
   ```

   The migration creates or updates the database the settings name, at the single head revision of the checkout. The loader requires the database at that head and refuses a database at any other revision, so run this step after an update to the checkout.

   > [!IMPORTANT]
   > Clear every dataset pointer and dataset or session record under `ADMIN_STATE_ROOT` before an import action. The loader refuses an enrolled root, and the example configuration starts at `data/admin` with no dataset state.

2. Load the curriculum and its vectors.

   ```bash
   uv run python scripts/mock_data.py load
   ```

   The loader imports the fixture through the capture and normalization path, adds the bundled vectors of its chunks, and prints one JSON line holding the embedding coverage of the loaded dataset, with the total, pending, completed, and failed chunk counts and one row per field, language, and text origin.

## Loading the curriculum alone

The `load-curriculum` action stops after the curriculum and leaves the vectors out, so the dataset holds courses, modules, and rules with no embeddings.

```bash
uv run python scripts/mock_data.py load-curriculum
```

It prints the normalization report, which counts the periods, canonical courses, active courses, modules, and versions the batch wrote, with the per-version classification counts. The action sends no request to the embedding service.

## Re-running an import action

A second `load` on an already-loaded database completes and prints the same coverage. The loader reuses the sole retained capture under `--raw-root` when its stored responses match the fixture, requires the stored curriculum to be exactly the fixture's, and completes nothing that is already stored.

The reuse is conditional, and the failure messages name the condition:

| Situation | What the loader does |
|---|---|
| The database holds no course, module, or source snapshot | The import proceeds. |
| The database holds exactly the fixture's canonical groups and source rows | The import proceeds and reuses the retained capture. |
| The database holds any other curriculum | It refuses with `database already holds curriculum outside the fictional mock fixture`. |
| The retained capture holds different response bytes than the fixture | It refuses with `retained mock import manifest does not match the current fixture`. |
| More than one capture is retained under `--raw-root` | It refuses with `multiple mock import manifests are ambiguous`. |

## Writing the serving artifacts and the bundled vectors

`write-artifacts` calls the same `build_serving_artifacts()` owner the administrative command uses, so it writes the same files, and on an embeddings-on site the same derived tables, into one artifact family under the configured admin state root. It writes no tracked file, so a deployment leaves the checkout as it is. [Serving artifact build](/docs/backend/text-and-vectors/serving-artifact-build.md) lists the files and the tables.

```bash
uv run python scripts/mock_data.py load
uv run python scripts/mock_data.py write-artifacts
```

On a site that serves the embedding features, run the artifact action when the stored vectors changed and the hub files, the centroid rows and the neighbour rows must match them again. The bundled file is the artifact an import reads, so a bundle that does not name the fixture's chunks fails the import:

| Situation | Message |
|---|---|
| The bundle names a different chunk set than the fixture | `bundled mock embeddings do not match the current fixture chunks` |
| The bundle was built from a different teaching text | `bundled mock embeddings input identity does not match the current fixture` |

On a site that serves the embedding features, the artifact action needs complete embedding coverage of the configured database: every desired chunk of a represented course must hold a completed compatible vector. A database with no current chunk builds with two empty hubs and zero counts, and a database that has current chunks needs at least one learning-outcomes chunk among them. An embeddings-off site builds the same action over incomplete coverage.

`write-bundle` rewrites the tracked bundled vector file `data/mock/embeddings.json` from the stored vectors of the prepared fixture, under the configured embedding configuration. It is the explicit rewrite of a tracked file, and no build or deploy path runs it.

```bash
uv run python scripts/mock_data.py write-bundle
```

The action prints nothing. It and `write-artifacts` each prepare the fixture capture and refuse a database that holds curriculum outside the fixture before any file is written, with the same message as the loader.

The builder writes every file of one build before the dataset tables change. On an embeddings-on site the table replacement and the `current` switch commit as one unit, and an embeddings-off site replaces no table. [Serving artifact build](/docs/backend/text-and-vectors/serving-artifact-build.md) states the files and the transaction, and [Administration commands](/docs/backend/interfaces/administration-commands.md#the-serving-artifact-command) states what a failed build restores.

The supervisor opens the artifact build and both catalogue bodies once before it forks its workers. On a site that serves the embedding features that opened set holds the build's shared centroid and chunk stores, and a site with them off holds the catalogue and the study fragments alone. A completed build reaches serving after the full supervisor restart that [the operations overview](/docs/operations/README.md#derived-files-served-data-and-the-web-restart) describes, and that restart changes the serving dataset identity the feature read reports. A browser reads data that an import or a stage changed in place on its next uncached read or reload after that restart. [Embeddings](/docs/backend/text-and-vectors/embeddings.md#the-hubs) describes what the two hubs are and [Course centroids](/docs/backend/text-and-vectors/embeddings.md#course-centroids) describes the centroid rows.

## The example data loader

The loader prints its own failure message.

| Message | Cause | Fix |
|---|---|---|
| `mock data import requires a bootstrap dataset state root` | A Selected or Working pointer or dataset records exist under `ADMIN_STATE_ROOT`. | Clear the dataset state for the example path, then run the action again. |
| `the received database does not match the executing checkout's single Alembic head` | The loader opened a database that is not at the checkout's migration head. | Run `uv run python -m alembic upgrade head`, then run the action again. |
| `database already holds curriculum outside the fictional mock fixture` | The configured database holds curriculum that is not the example dataset. | Point the loader at an empty configured database, or use the prepared-dataset path. |
| `retained mock import manifest does not match the current fixture` | The capture retained under `--raw-root` holds different response bytes than the fixture. | Remove the retained capture directory, or point `--raw-root` at an empty path. |
| `multiple mock import manifests are ambiguous` | More than one capture is retained under `--raw-root`. | Leave the one capture the run continues and remove the others, or point `--raw-root` at an empty path. |
| `bundled mock embeddings do not match the current fixture chunks` | The bundled vector file names a different chunk set than the fixture. | Restore the bundled file that matches the fixture, or rebuild it with `write-bundle` from a database whose stored vectors match the fixture's chunks. |

[Installation](/docs/getting-started/installation.md) lists the failures of the dependency, copy, and serving steps.
