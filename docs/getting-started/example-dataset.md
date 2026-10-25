# The example dataset

The example dataset is invented, and the loader imports it into the configured database and writes its bundled vectors and both hub files in separate actions.

## What the loader needs

- A copy set up by the [Installation](/docs/getting-started/installation.md) steps, with the Python dependencies installed and the configuration and environment files in place.
- The database service running, and the database at the checkout's migration head. The first step below applies the migration.
- `SELECTED_DATASET_ENABLED` set to false in `config/database.toml`. The loader refuses a configuration with the switch set to true, and the example file sets it to false.

## The loader actions

The loader imports the fixture through the same capture and normalization path a real capture uses. `scripts/mock_data.py` parses one action with its options and delegates once to `course_explorer.mock_data.run_mock_data_command`. [The example data loader](/docs/backend/interfaces/command-line.md#the-example-data-loader) describes where the action sits beside the feature commands, and [command adapters](/docs/backend/interfaces/command-adapters.md) lists the return type of each action.

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

## Loading the example dataset

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

## Writing the bundled vectors and the hubs

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

The action needs complete embedding coverage of the configured database: every desired chunk of a represented course must hold a completed compatible vector, and at least one learning-outcomes chunk must exist. Both hub means are computed and both temporary files are staged before either hub destination changes, so a dataset that is not ready leaves the bundled file and both hub files as they are.

The bundled file is written before the hub files are staged, and the staged hub files then replace their destinations in sequence. A failure during that sequence can leave the two hub destinations in different states, with the catalogue hub updated and the outcomes hub holding its earlier content. A database that holds curriculum outside the fixture is refused before any file is touched, with the same message as the loader.

The values in the hub files reach a running site when its process starts. Restart the web server after a hub write, as [the operations overview](/docs/operations/README.md#derived-files-served-data-and-the-web-restart) describes. The same restart changes the serving dataset identity that the feature read reports, and a browser reads data that an import or a stage changed in place on its next uncached read or reload after that restart. [Embeddings](/docs/backend/text-and-vectors/embeddings.md#the-hubs) describes what the two hubs are.

## The example data loader

The loader prints its own failure message.

| Message | Cause | Fix |
|---|---|---|
| `mock data import refuses a selected-dataset enabled configuration` | `SELECTED_DATASET_ENABLED` is true in `config/database.toml`. | Set it to false for the example dataset path, then run the action again. |
| `the received database does not match the executing checkout's single Alembic head` | The loader opened a database that is not at the checkout's migration head. | Run `uv run python -m alembic upgrade head`, then run the action again. |
| `database already holds curriculum outside the fictional mock fixture` | The configured database holds curriculum that is not the example dataset. | Point the loader at an empty configured database, or use the prepared-dataset path. |
| `retained mock import manifest does not match the current fixture` | The capture retained under `--raw-root` holds different response bytes than the fixture. | Remove the retained capture directory, or point `--raw-root` at an empty path. |
| `multiple mock import manifests are ambiguous` | More than one capture is retained under `--raw-root`. | Leave the one capture the run continues and remove the others, or point `--raw-root` at an empty path. |
| `bundled mock embeddings do not match the current fixture chunks` | The bundled vector file names a different chunk set than the fixture. | Restore the bundled file that matches the fixture, or rebuild it with `write-artifacts` from a database whose stored vectors match the fixture's chunks. |

[Installation](/docs/getting-started/installation.md) lists the failures of the dependency, copy, and serving steps.
