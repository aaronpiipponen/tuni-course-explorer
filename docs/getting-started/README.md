# Getting started

The getting-started pages set up a copy of TUNI Course Explorer, fill its database, and prepare the worker.

## What the area covers

The pages follow one copy from its first install to a served site with a filled database and a prepared worker. [Installation](/docs/getting-started/installation.md) installs the tools and the working files, builds the browser apps, starts the database and the embedding service, and loads the example dataset. [Self-hosting](/docs/getting-started/self-hosting.md) runs the copy as a site, with its own units, settings, administration account, console build, and HTTPS reverse proxy.

Two pages then fill the database from one of two sources. The last page prepares the worker and describes the stages that run there. A copy serves the data it is given: the example dataset is invented, and the prepared dataset holds official data.

## What the steps need

- A copy set up by the [Installation](/docs/getting-started/installation.md) steps, with the Python dependencies installed, the configuration and environment files in place, and the database and embedding services built.
- A prepared worker for the prepared-dataset path, which [Preparing the worker](/docs/getting-started/worker-stages.md#preparing-the-worker) describes.

## The two paths

Two different sources can fill the database, and each has its own command and its own setting.

| Path | Source of the data | Database it fills | Command script |
|---|---|---|---|
| The example dataset | The invented fixture under `data/mock/` | The configured database, named by `POSTGRES_DB` in `config/database.toml` | `uv run python scripts/mock_data.py` |
| A prepared dataset | The public curriculum source and the model stages | The selected dataset, named by the pointer under `ADMIN_STATE_ROOT` | `uv run python scripts/admin.py` |

The example dataset path needs no request to the curriculum source, and no model runs. The prepared dataset path captures the source, normalizes what it captured, embeds the teaching text, and runs the two worker stages to add translations and inferred prerequisites.

> [!IMPORTANT]
> The two paths use the selected-dataset switch `SELECTED_DATASET_ENABLED` in `config/database.toml` in opposite ways. The loader writes the configured database and refuses a configuration with the switch set to true. The prepared-dataset path sets the switch to true, because it stages and reports on the selected dataset.

Every command on these pages runs from the checkout root, and every administration command prints one JSON report line.

## In reading order

1. [Installation](/docs/getting-started/installation.md) installs the Python and browser dependencies, copies the working files from `examples/`, builds the browser apps, places the embedding model, starts the database and the embedding service, loads the example dataset, and starts the web server and the administration backend in the foreground.
2. [Self-hosting](/docs/getting-started/self-hosting.md) runs that copy as a served site: it installs the web and administration units, sets the site and administration settings, creates the administration account, builds the console, and places an HTTPS reverse proxy in front.
3. [The example dataset](/docs/getting-started/example-dataset.md) describes the loader that fills the configured database from the invented fixture and the action that writes the bundled vectors and both hub files.
4. [Preparing a dataset from the curriculum source](/docs/getting-started/data-preparation.md) enrolls the selected dataset, runs the ingestion and embedding stages, writes the hubs, reads the coverage and summary reports, and migrates the dataset schema.
5. [Worker stages](/docs/getting-started/worker-stages.md) prepares the worker, runs translation and inference, and returns the finished copy of the selected dataset.
