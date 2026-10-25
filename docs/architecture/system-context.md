# System context

TUNI Course Explorer serves an official course catalogue to a browser app and to a signed-in administration console, while an administration command prepares that data on a separate path.

## The parts

Nine parts make up the course request and preparation paths and the administration surface.

The browser app holds every profile in the browser state and sends every request to the web server. The web server serves the built browser app and answers the read API. The PostgreSQL database with pgvector holds the selected dataset: the courses, modules, teaching text, vectors, and inferred prerequisites that the app and the stages read. The embedding service is a container that runs a pinned embedding model and turns text into vectors.

The administration command is the operator's entry point, with its numbered operator menu and its four stages. The worker is the separate machine that runs the translation and inference stages on its own copy of the selected dataset. The public curriculum source is the published course and module data that the ingestion stage captures.

The Administration console is the signed-in browser application with its five tabs. The Administration backend is the loopback process that serves the console, admits each request and runs its fixed commands through the administration command.

The parts connect along two paths and one command boundary. The request path runs from the browser app through the web server to the database and the embedding service. The preparation path runs from the administration command through the four stages to the same database. The administration surface reaches the preparation work through the fixed `scripts/admin.py` commands that the Administration backend runs through the administration command.

![The browser app and the web server form the request path, which reads the PostgreSQL database with pgvector and embeds query text through the embedding service, and the accent outline marks that path. The administration console and the administration backend form the administration surface, and the backend runs fixed commands through the administration command. The administration command and the worker form the preparation path, which fills the selected dataset: the administration command captures the public curriculum source through its ingestion stage, and the worker runs the translation and inference stages on its copy.](/docs/diagrams/system-context.svg)

## The request path

A request starts in the browser app and ends in the web server. The web server runs one front router on the configured loopback port and the configured worker processes on ephemeral loopback ports. The router serves the browser app's two shell documents and its compiled assets, and the worker processes answer eight dataset command reads and one feature read under `/api/`. Nothing on this path writes authoritative catalogue or user data, starts a stage, or reaches the worker. One middleware in the router appends one request record per request to the site's own usage file, and the router holds its transient admission counters, activity timestamps, tickets and graph costs in process memory. Neither write is catalogue or user data.

The reads enforce the site's two feature switches. The **Semantic** search method, the Compare feature and the Recommended list are served only while the embedding switch is on, the inferred data only while the inference switch is on, and the feature read reports that pair and the identity of the resolved dataset to the browser. Every cached read reports the same identity, and it is the freshness boundary of the browser's in-memory read cache.

A restarted feature web server changes the identity, and a selected-receipt switch changes it on the next read without a restart. An idle tab discovers neither change until an uncached read, and an in-place change to served data in either database mode requires a restart and then an uncached read or a reload.

A request reads the selected dataset through the connection values in the database subsystem file, `config/database.toml`. A semantic search also embeds the query text through the embedding service, reached at `EMBEDDING_HOST` and `EMBEDDING_PORT` in the search subsystem file, `config/search.toml`, and measures that vector against the stored vectors.

The minimum route is calculated in the browser. The graph response carries the solver structure, and the web route adds the serving dataset identity and the configured allocation limit beside the report. The browser runs the shared TypeScript solver in a background worker for an explicit calculation. The machine route command runs that same solver through Node outside the request path, so the serving process starts no solver and exposes no route endpoint.

The narrowing boxes filter one cached minimal official catalogue in the browser. The catalogue carries canonical identity, code, FI and EN names, credits and the activity flag for each course, and for each module group that has an eligible version, every version eligible for the current academic year with its `sisu_module_id`, `module_type`, code, FI and EN names, `validity_start`, `validity_end` and curriculum periods. It carries no teaching text, description or prerequisite. The matching and ordering port the official substring rule, so typing sends no narrowing request.

The web server holds no value that reaches the preparation work. The reads it exposes are listed in [Web API](/docs/backend/interfaces/web-api.md), and [System boundaries](/docs/architecture/boundaries.md) describes that separation.

## The preparation path

The preparation path runs outside the request path. It starts at the administration command, which an operator runs as the operator menu or as one machine command, and it works on the selected dataset through the stages. The ingestion stage captures the public curriculum source, validates the capture, and normalizes it into official courses, modules, versions, and rules. The stages then add the derived data the app reads.

The two local stages run on the machine that runs the administration command. Ingestion writes official data, and embedding writes the chunks and the vectors of the teaching text of each representative version.

The two remote stages run on the worker. The administration command prepares a worker session and hands the worker its own copy of the selected dataset. The finished copy returns as a whole, is verified, and becomes the selected dataset. [Stage lifecycle](/docs/operations/stage-lifecycle.md) describes the actions and [Worker sessions](/docs/operations/worker-sessions.md) describes the round trip.

## The administration surface

A deployment also runs an administration surface, with its own frontend, its own backend package, its own configuration and its own serving process. It reaches the system through the fixed `scripts/admin.py` commands alone, with validated parameters and no shell or free-form command text. It therefore owns no direct connection to the database, no second controller over the four stages and no path to the worker beyond the command it runs. Its reads and actions return the report of the command.

The backend package `src/course_explorer_admin_web/` serves that surface. One process binds the loopback address and port of `config/admin_web.toml` and answers the three authentication routes under `/auth/`. An admission middleware checks the durable lock, the exact Host and Origin, the CSRF token of a state-changing method and the session rule of the address before any route. The built shell and its built assets are the one read-only exception to the session requirement. `GET /auth/session` reuses a live session or creates an anonymous one within the [server-wide creation limit](/docs/operations/admin-console/access-and-records.md#the-anonymous-session-creation-limit), which answers `429` while the limit is spent. The sessions live in that process's memory, and the failed-attempt count, the lock and the command log are files under `data/admin-web/`. The course-exploration web server holds no administration route, no administration file and no worker connection value. [Console access and records](/docs/operations/admin-console/access-and-records.md) states the admission order and both records.

The parts described here are the course request and preparation paths and the administration surface. [System boundaries](/docs/architecture/boundaries.md) states the administration boundary, and [Operations](/docs/operations/README.md) describes the operator's access to both surfaces.

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

The database password, the three worker connection values, the two systemd service identities of this checkout and the manager scope of the feature web unit live in the environment file, because they change from machine to machine. The feature web unit runs under that scope, and the administration unit always runs under the user manager. The other values live in the subsystem files, including the 11 keys of the administration backend's own `config/admin_web.toml`. The settings owner composes both for every settings family. [Configuration](/docs/backend/configuration.md) describes the files and the keys, and the stored shapes are described in [Data model](/docs/backend/catalogue/data-model.md). The operator's own surface is the [Operator menu](/docs/operations/operator-menu.md).
