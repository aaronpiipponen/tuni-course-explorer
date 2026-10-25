# System boundaries

TUNI Course Explorer separates the course-exploration request path, the browser-held user state, official data, the preparation work, and the administration surface, and each separation is enforced in code.

The administration side runs the preparation work and fills the selected dataset, and the read-only side serves requests from it. The two paths meet at two shared artifacts. The PostgreSQL database with pgvector holds the selected dataset: the stages write it, and the web server reads it. The usage file under `data/usage/requests` is the second: the front router appends one request record per request, and the administration command's usage report reads and prunes it. The reads of the web server write nothing to the database. The web server runs one front router and its worker processes, and the router holds transient admission counters in its own process memory, which no administration surface reads.

![An administration side holds the administration console, the administration backend, the administration command and the worker, and the accent-outlined read-only side holds the browser app and the web server. A database between them holds the selected dataset, which the administration command writes and the web server reads. A usage file holds the request records that the web server appends and the administration command reads and prunes.](/docs/diagrams/system-boundaries.svg)

## A read-only web server

No route of `src/course_explorer_web/` writes authoritative data, starts or controls a stage, or reaches the worker. The route set is fixed: eight dataset command reads and one feature read under `/api/`, two shell documents for the browser app, and one mounted asset directory. The feature read reports the site's two serving switches and the serving dataset identity, and it runs no command. The package imports no administration module, no translation module, and no ingestion or embedding command module. The front router appends one request record per request to the site's own usage file and holds the admission counters, tickets and graph costs in its process memory. Those two writes are the serving path's writes, and the counters hold no catalogue or user data.

The launcher passes only named settings into the server process: the five settings families every site needs, the embedding family on a site that serves embedding features, the inherited `HOME`, `PATH`, and `LANG`, and the environment-only marker. A child built that way reads no configuration file, so no other value reaches it. The `course_explorer_web` tests assert the exact route set, the forbidden imports, the setting allowlist, and one recorded usage line per HTTP outcome.

The minimum route is calculated in the browser from the graph report, and the machine route command runs the same TypeScript solver through Node outside this package. Neither the route calculation nor its result reaches a server route, so the serving process holds no fallback solver. The narrowing boxes filter one cached minimal official catalogue in the browser. The catalogue route serves that minimal official catalogue: canonical identity, code, FI and EN names, credits and the activity flag for each course, and for each module group that has an eligible version, every version eligible for the current academic year with its `sisu_module_id`, `module_type`, code, FI and EN names, `validity_start`, `validity_end` and curriculum periods. The filter applies the official matching and ordering in the browser without another server request.

The reason is that the request path serves readers only. Model credentials, stage control, and the worker connection belong to the administration command.

## Feature switches

Two validated keys in `config/web.toml` decide which features a site's reads serve: `WEB_EMBEDDINGS_ENABLED` governs semantic matching, the Compare feature and the Recommended list of Discover, and `WEB_INFERENCE_ENABLED` governs every read and every mark of inferred data. Both are required and have no default, so each site states them.

The serving backend enforces them. A disabled embedding feature refuses the comparison and recommendation reads with status 403 before their command runs, and a search on such a site composes no semantic method, no embedding provider and no stored-vector read. A disabled inference feature is applied to the request input that toggles inferred data, so those reads compile official prerequisites alone. The browser hides the controls the site does not serve, and the stored data and the saved browser preferences are the same either way.

## Request usage records

The front router appends one request record per request to the ignored `data/usage/requests` of its own checkout, through one pure ASGI middleware around its forwarding handler. One record holds the hour, the route, the status and the duration, and no IP address, query, user agent or course data. A route label is one of the nine fixed API paths or the two shell paths, `/assets` for the mounted asset directory, or `unmatched`, so a requested path, asset name or query is never retained.

A fixed command under `scripts/admin.py` reports the request count and the mean duration by window and route and prunes the records past the configured retention, outside the request path. That read and the serving append take one exclusive lock on the same file, so a record that arrives while a report rewrites the file is preserved. The request record is the only durable record the serving path adds. The admission counters live in the front router's process memory, and no administration surface reads them. The Administration backend writes the command log in its own file under `data/admin-web/`, and [Console access and records](/docs/operations/admin-console/access-and-records.md) states both records.

## The administration surface

A deployment runs a separate administration surface: an Administration console, an Administration backend with its own package `src/course_explorer_admin_web/`, and its own configuration and serving process. The backend reaches the system through the fixed `scripts/admin.py` commands alone, with validated parameters and no shell or free-form command text. It therefore holds no direct connection to the database, no second controller over the stages and no service path of its own. It binds loopback alone.

The Administration backend authenticates its own operator. Each site holds one account with a username and an argon2id password hash, and one fixed command sets the password. Sessions live in the backend process's memory and expire at a configured idle lifetime and a configured total lifetime. The session cookie is HttpOnly, Secure, SameSite=Strict and scoped to its site. Every request must carry exactly one Host header equal to the configured origin's host and port, and every state-changing request needs a valid CSRF token and an exact Origin match.

The backend owns that boundary. One process binds the configured loopback address, serves the three authentication routes under `/auth/`, and serves the built console from `/` and from one mounted `/assets` directory. One admission middleware applies the lock, the exact Host and Origin check, and the CSRF token of a state-changing method before any route runs, so an unknown address and a mounted file are covered like a route. [Administration backend](/docs/backend/interfaces/admin-backend.md) names the middleware and its admission order.

The built shell and its built assets are the one read-only exception to the session requirement: a `GET` or `HEAD` of exactly `/` or of a path beneath `/assets/` is admitted before its cookie is read, and that request runs no command and records nothing. Every other address needs an authenticated live session, apart from `GET /auth/session`, which reuses its session or creates an anonymous one within the [anonymous session creation limit](/docs/operations/admin-console/access-and-records.md#the-anonymous-session-creation-limit), and `POST /auth/login`, which needs a live session of any kind.

Every feature route runs fixed commands of one closed command union. A single-command route runs exactly one of them. The route of the administration rebuild runs two: its build command answers the request, and only its successful response attaches the separate restart command as a background task that the framework runs after the final response body send. Sessions live in that process's memory, so a restart ends them, which is the sign-out that the administration rebuild causes. The failed-attempt count, the lock and the command log are files under `data/admin-web/`.

The [Console access and records](/docs/operations/admin-console/access-and-records.md) page states the admission order, the session rules, the lock and both records.

The console's frontend is a separate React application with its own build and its own manifest, built from `admin-web/` into `admin-web/dist`, so the course-exploration server can serve no admin file and the console holds no course-exploration asset. [Administration console code](/docs/frontend/admin-console.md) describes the build.

Three consecutive failed sign-ins create the Administration lock `data/admin-web/lock`. While that file exists, every request to that site is refused with a bare `403` and an empty body, before sign-in, any route and any static file, authenticated or not. The file lives on disk, so a restart and a reboot do not clear it, and only deleting the whole file ends the lock.

The enforced assertions on this page belong to two packages. The course-exploration web package refuses both administration packages by import, and its tests cover the route set, the setting allowlist and one usage record per request, with the usage report covered by the report's own tests. The Administration backend's tests cover its admission, its fixed commands, its routes and its command-log read. [Invariants and their enforcement](/docs/architecture/invariants.md) names the module that owns each rule and the tests that cover it, and [Administration backend](/docs/backend/interfaces/admin-backend.md) names the package and its test files. [System context](/docs/architecture/system-context.md) places the administration surface among the parts, [Administration console code](/docs/frontend/admin-console.md) describes the separate build, and [Operations](/docs/operations/README.md) states the operator's access and the record contract.

## User state in the browser

The selected and completed courses, the exclusions, the structure edits, and the app language live in profiles in the browser's local storage. They reach the server only as request inputs, and a route that needs courses accepts the canonical identities and the toggles the browser sends. The server stores no profile and returns none, so the profiles belong to the browser that holds them. The open tab lives in the browser tab's own session storage and reaches no server either.

## Official and inferred data apart

Official data is what the ingestion stage writes from the public curriculum source. Inferred prerequisites and equivalence groups are stored in their own tables with their own coverage state, and the inference stage writes inferred output without modifying an official row. University facts and derived claims never share a store, so the interface can mark each derived claim as such. The app shows inferred prerequisites only behind the **Inferred** toggle, on a site that serves inference features, and marks each one **inferred**.

A translation is stored beside the text it was made from and does not replace it. Official text takes precedence, and a stale translation is reported and never used. [Data model](/docs/backend/catalogue/data-model.md) describes the stores, and [Inference](/docs/backend/inference/inference.md) describes what the inference stage reads and writes.

## Inference on local models

The inference stage runs language models on the worker, and the web server holds no model or worker credential. The inference subsystem file pins each artifact by revision and SHA-256 and names the loopback address and port the provider posts to.

Fit decides which local model receives a target. A target call starts only when its prompt tokens plus the configured output cap and headroom fit inside the context of one configured local key. A packet that fits no configured key is never shortened. It fails that target as one capacity failure, and the whole packet is either sent or reported as failed. The key list, the output cap, and the headroom are described in [Inference scheduling and disposition](/docs/backend/inference/inference-scheduling.md).

The web server receives none of these settings. Its launcher composes the database, normalization, search, web, and admission families, and adds the embedding family only on a site that serves embedding features, so no inference value and no worker connection value can reach the serving process.

## Configuration ownership

The subsystem files hold portable settings, which do not have to change when setting up another machine. The environment file holds values that must change per machine: the database password, the three worker connection values, the two administration site unit identities `ADMIN_SITE_WEB_SERVICE_UNIT` and `ADMIN_SITE_ADMIN_SERVICE_UNIT`, and the feature web unit's manager scope `ADMIN_SITE_WEB_SERVICE_SCOPE`. Tracked templates live under `examples/config/`, and the runtime copies under `config/` are ignored by Git. A checkout can customize its portable settings without changing the templates. Each value is validated before the process that reads it starts work, and a missing or malformed value fails the read. [Configuration](/docs/backend/configuration.md) lists the files and the keys.

## One current schema and format

Every process reads the database schema, the file formats, and the state files of the running code, and a mismatch fails before work starts. A database that is not at the executing checkout's single migration head is refused with fixed guidance, and a state file whose contents do not match its closed schema is refused rather than interpreted. The inference result contract accepts only the `v2` schema version. The browser reads only its schema-3 envelope and `/3` profile and state files, and the separate Sisu `/1` capture. A stored value or file of another shape fails validation and is left as it is. The recovery screen exports the stored envelope text exactly as stored or resets browser storage after confirmation, and an import file of another type or shape is refused at the file input and never reaches recovery. A stored prerequisite expression outside the current node vocabulary fails the read.

Data and code move together through explicit setup and migration, so a read is answered against the schema and the formats of the running code alone.
