# System context

TUNI Course Explorer serves an official course catalogue to a browser app along a read-only request path, while an administration command prepares that data on a separate path.

## The parts

Seven parts make up the system. The browser app keeps every profile in the browser state and sends every request to the web server. The web server serves the built browser app and answers the read API. The PostgreSQL database with pgvector holds the selected dataset: the courses, modules, teaching text, vectors, and inferred prerequisites that the app and the stages read. The embedding service is a container that runs a pinned embedding model and turns text into vectors. The administration command is the operator's entry point, with its numbered operator menu and its four stages. The worker is the separate machine that runs the translation and inference stages on its own copy of the selected dataset. The public curriculum source is the published course and module data that the ingestion stage captures.

Each part connects to the next by one of two paths. The request path runs from the browser app through the web server to the database and the embedding service. The preparation path runs from the administration command through the four stages to the same database.

![The browser app and the web server form the request path, which reads the PostgreSQL database with pgvector and embeds query text through the embedding service. The administration command and the worker form the preparation path, which fills the selected dataset, and the ingestion stage reads the public curriculum source while the worker runs the translation and inference stages.](/docs/diagrams/system-context.svg)

## The request path

A request starts in the browser app and ends in the web server. The web server serves the browser app's two shell documents and its compiled assets, and it answers ten read commands under `/api/`. Nothing on this path writes data, starts a stage, or reaches the worker.

A request reads the selected dataset through the connection values in the database subsystem file, `config/database.toml`. A semantic search also embeds the query text through the embedding service, reached at `EMBEDDING_HOST` and `EMBEDDING_PORT` in the search subsystem file, `config/search.toml`, and measures that vector against the stored vectors.

The web server holds no value that reaches the preparation work. The reads it exposes are listed in [Web API](/docs/backend/interfaces/web-api.md), and [System boundaries](/docs/architecture/boundaries.md) describes that separation.

## The preparation path

The preparation path runs outside the request path. It starts at the administration command, which an operator runs as the operator menu or as one machine command, and it works on the selected dataset through the stages. The ingestion stage captures the public curriculum source, validates the capture, and normalizes it into official courses, modules, versions, and rules. The stages then add the derived data the app reads.

The two local stages run on the machine that runs the administration command. Ingestion writes official data, and embedding writes the chunks and the vectors of the teaching text of each representative version.

The two remote stages run on the worker. The administration command prepares a worker session and hands the worker its own copy of the selected dataset. The finished copy returns as a whole, is verified, and becomes the selected dataset. [Stage lifecycle](/docs/operations/stage-lifecycle.md) describes the actions and [Worker sessions](/docs/operations/worker-sessions.md) describes the round trip.

## Where each stage runs

| Stage | Kind | Runs on | Fills |
|---|---|---|---|
| Ingestion | Local | The machine that runs the administration command | Official courses, modules, versions, and prerequisite rules |
| Embedding | Local | The same machine | Teaching-text chunks and their vectors |
| Translation | Remote | The worker | Translated teaching text beside the official text |
| Inference | Remote | The worker | Inferred prerequisites and equivalence groups |

A local stage reads and writes the selected dataset in place. A remote stage works on a copy and returns it, so the selected dataset changes as one whole at the dataset return.

## How the parts are configured

`SELECTED_DATASET_ENABLED` in the database subsystem file decides whether a process reads the configured database or the dataset named by the pointer under `ADMIN_STATE_ROOT`. The web server, the stages, and the operator reports all resolve the selected dataset through that one pointer.

The embedding service serves the request path and the embedding stage at the same time. Its model artifact and its runtime are pinned by image digest, artifact checksum, and revision, so a query vector and a stored chunk vector come from one model.

The database password and the three worker connection values live in the environment file, because they change from machine to machine. The other values live in the subsystem files. The settings owner composes both for every settings family. [Configuration](/docs/backend/configuration.md) describes the files and the keys, and the stored shapes are described in [Data model](/docs/backend/catalogue/data-model.md). The operator's own surface is the [Operator menu](/docs/operations/operator-menu.md).
