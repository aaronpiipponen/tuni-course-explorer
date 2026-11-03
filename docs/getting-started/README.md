# Getting started

The getting-started pages set up course-explorer, fill its database, and prepare the worker.

## What the area covers

The pages follow one copy from its first install to a served site with a filled database and a prepared worker. [Installation](/docs/getting-started/installation.md) runs the four steps: clone the checkout, prepare the environment, run the example workflow and run the real-database workflow. [Self-hosting](/docs/getting-started/self-hosting.md) runs the copy as a site, with its own units, settings, administration account, console build, and HTTPS reverse proxy.

Two pages then fill the database from one of two sources. The last page prepares the worker and describes the stages that run there. A copy serves the data it is given: the example dataset is invented, and the prepared dataset holds official data.

## What the steps need

- A copy set up by the [Installation](/docs/getting-started/installation.md) steps, with the Python dependencies installed, the configuration and environment files in place, and the database and embedding services built.
- The real-database workflow for a prepared dataset, which enrolls one empty Selected database.
- A prepared worker for the prepared-dataset path, which [Preparing the worker](/docs/getting-started/worker-stages.md#preparing-the-worker) describes.

## The two paths

Two different sources can fill the database, and each has its own workflow and its own state.

| Path | Source of the data | Database it fills | Command script |
|---|---|---|---|
| The example dataset | The invented fixture under `data/mock/` | The configured database, named by `POSTGRES_DB` in `config/database.toml` | `uv run python scripts/mock_data.py` |
| A prepared dataset | The public curriculum source and the model stages | The Working dataset, named by its pointer under `ADMIN_STATE_ROOT`. The Selected dataset serves the site. | `uv run python scripts/admin.py` |

The example dataset path needs no request to the curriculum source, and no model runs. The prepared dataset path captures the source, normalizes what it captured, embeds the teaching text, and runs the two worker stages to add translations and inferred prerequisites.

> [!IMPORTANT]
> The two paths start from different state. The example workflow enrolls nothing and serves the configured database directly. The real-database workflow enrolls one empty Selected database. The prepared-dataset path copies Selected to Working, and its stages write Working while the site continues to serve Selected.

Every command on these pages runs from the checkout root. An administration machine command prints one JSON report line, and running the administration command with no argument opens the numbered operator menu, which prints its entries.

## In reading order

1. [Installation](/docs/getting-started/installation.md) runs four steps: clone the checkout, prepare the Python and browser dependencies, run the example workflow, and run the real-database workflow. The example workflow writes the working files, generates both database passwords, creates the administration account, downloads the pinned model after confirmation, builds both backends, and proves the example site. The real-database workflow creates one empty database, enrolls it as Selected, builds it and proves it.
2. [Self-hosting](/docs/getting-started/self-hosting.md) runs that copy as a served site: it states the user-unit identities, the two startup modes, the site and administration settings, and the HTTPS reverse proxy.
3. [The example dataset](/docs/getting-started/example-dataset.md) describes the loader that fills the configured database from the invented fixture, the action that builds the serving artifact set for the site's embedding switch, and the explicit rewrite of the tracked bundled vectors.
4. [Preparing a dataset from the curriculum source](/docs/getting-started/data-preparation.md) copies the Selected dataset to Working, runs the ingestion and embedding stages, reads the coverage and summary reports, and migrates a dataset role.
5. [Worker stages](/docs/getting-started/worker-stages.md) prepares the worker, runs translation and inference, and returns the finished copy of the Working dataset.
