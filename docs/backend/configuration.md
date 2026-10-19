# Configuration

TUNI Course Explorer reads portable values from the subsystem files and machine-local values from the environment file, and fails a settings read when a required value is missing or malformed.

The repository holds one subsystem file per configuration subsystem under `config/`. Values that must change when a copy is set up on another machine live outside those files, in the environment file at the repository root. One [settings owner](/docs/reference/glossary.md#configuration) composes both, so an ordinary command reads its configuration with no manual sourcing step.

## Where values live

The eight subsystem files under `config/` each own the portable settings of one subsystem. The two hub files under `config/derived/` hold the embedding hub vectors, and `config/wiki.json` selects which pages the documentation wiki renders.

| File | Owns |
|---|---|
| `config/curriculum.toml` | Raw capture location and checkpoint policy, the public curriculum source, normalization, and the local ingestion controller state root |
| `config/database.toml` | PostgreSQL connection components, the selected-dataset switch, and the administrative state root |
| `config/search.toml` | The embedding runtime and generation contract, the local embedding controller state root, the two embedding hub references, and the search, comparison, recommendation, and route policy |
| `config/translation.toml` | The translation runtime and provenance contract, the translation controller state root and health attempts, and the shared worker health interval and stop timeout |
| `config/inference.toml` | The inference runtime contract, the local fit keys, the candidate selection and rerank policy, and the inference controller policy |
| `config/worker.toml` | The worker connection, setup, dataset, and local lifecycle policy |
| `config/admin_web.toml` | The Administration backend's loopback bind, exact HTTPS origin, session lifetimes, anonymous session creation limit, command-log entry limit, console poll interval, App link address, and GitHub repository address |
| `config/web.toml` | The web bind, process count, browser-drawing limit, the two served feature switches, and the usage-record retention |

The tracked templates for these paths live under `examples/`. An operator copies `examples/config/*.toml`, `examples/config/wiki.json`, and `examples/config/derived/*.json` into `config/`, and `examples/.env.example` into the environment file at the repository root. Git ignores these working copies, so each checkout carries its own settings without changing the templates. The wider setup steps are described in [Installation](/docs/getting-started/installation.md).

Each subsystem file holds top-level keys whose names are the settings the code reads. A key defined in two files is rejected before any setting loads. Environment keys compare case-insensitively, matching the runtime composition, so one key written in two cases is refused as one key assigned twice.

![The settings owner reads the subsystem files, including the Administration backend's `config/admin_web.toml`, the hub files, the environment file, and the process environment. It hands settings to the stages, the web server, the Administration backend, and the Compose environment file, which feeds Docker Compose. Dashed arrows show that the example files are copied at setup into the subsystem files and the hub files.](/docs/diagrams/configuration-sources.svg)

The Administration backend loads its own family from `config/admin_web.toml` in its own process. No administration key reaches the serving web process, whose launcher composes its own families alone.

## Deciding between a subsystem file and the environment file

One test decides where a value belongs. A value that must change when the copy is set up on another machine goes in the environment file. Every other value goes in the subsystem file that owns the value.

The machine-local values are the database password, the three worker connection values and the two systemd user unit identities of this checkout. The tracked template `examples/.env.example` carries these keys:

| Key | Value |
|---|---|
| `POSTGRES_PASSWORD` | The database password |
| `TRANSLATION_CONTROLLER_SSH_TARGET` | How the administration command reaches the worker |
| `TRANSLATION_CONTROLLER_WSL_DISTRIBUTION` | The runtime environment on the worker that runs the stage |
| `TRANSLATION_CONTROLLER_WORKER_PROJECT_ROOT` | The worker checkout location |
| `ADMIN_SITE_WEB_SERVICE_UNIT` | The systemd user unit that runs this checkout's web process |
| `ADMIN_SITE_ADMIN_SERVICE_UNIT` | The systemd user unit that runs this checkout's administration process |

`ADMIN_SITE_WEB_SERVICE_UNIT` and `ADMIN_SITE_ADMIN_SERVICE_UNIT` are each one plain service basename, such as `tuni-course-explorer-web.service` and `tuni-course-explorer-admin-web.service`, rather than a path or a command. A value that is not one service basename fails the settings read. Only the administration command reads them, to report the state of the web unit, to run the App rebuild and the administration rebuild. The administration rebuild builds the administration console and restarts the administration backend. The web process receives no administration value and reads no site unit identity.

The two rebuild scopes apply a saved file differently. The App rebuild restarts the site's web server, so a save that changes a value of the serving process takes effect at that step. The administration rebuild queues the restart of the administration backend, so a save that changes a value of that backend takes effect at that step.

> [!WARNING]
> The database password belongs in the ignored environment file. Subsystem files hold portable settings, and their tracked templates must be credential-free.

Everything else is portable. The two embedding hub values are a special case, since a subsystem file holds only their path and the settings owner resolves the referenced JSON artifact. `config/search.toml` points at `config/derived/embedding-hub.json` and `config/derived/embedding-outcomes-hub.json`. A similarity read that finds a hub file missing or malformed fails. The pages linked below name the keys a reader is most likely to change.

## Automatic loading

A process reads the subsystem files and the environment file when it builds its settings, so no shell export step is needed. When the same key is set in more than one place, the process environment takes precedence over the environment file, and the environment file takes precedence over the subsystem files. A missing required value or an invalid value fails the read with a clear error.

Every settings family validates its own values before it is returned. A bind address other than `127.0.0.1`, an academic year bound that is not two consecutive four-digit years, a port outside 1 to 65535, a worker path that is not absolute, a state root that is not repository-relative, or an administration origin that is not one exact `https://` origin without credentials, path, query or fragment all fail at load. The settings classes and the composition order are described in [Settings loading](/docs/backend/settings-loading.md).

## The administration backend's own file

`config/admin_web.toml` holds the 11 keys of the Administration backend. Every key is required and validated, so a site states its own origin.

| Key | File | Effect |
|---|---|---|
| `ADMIN_WEB_HOST` | `config/admin_web.toml` | The loopback address the backend binds. The example sets `127.0.0.1`. |
| `ADMIN_WEB_PORT` | `config/admin_web.toml` | The valid TCP port the backend binds. The example sets 8039. |
| `ADMIN_WEB_ORIGIN` | `config/admin_web.toml` | The exact external HTTPS origin the backend answers for, compared by scheme, host and port. The example sets `https://localhost:8039`. |
| `ADMIN_WEB_SESSION_IDLE_MINUTES` | `config/admin_web.toml` | The idle lifetime of one server-side session. The example sets 30. |
| `ADMIN_WEB_SESSION_MAX_HOURS` | `config/admin_web.toml` | The total lifetime of one session from its creation. The example sets 12. |
| `ADMIN_WEB_ANONYMOUS_SESSION_LIMIT` | `config/admin_web.toml` | The fresh anonymous sessions one backend process admits in the window, as a positive integer count. The example sets 10. |
| `ADMIN_WEB_ANONYMOUS_SESSION_WINDOW_SECONDS` | `config/admin_web.toml` | The length of that server-wide sliding window in seconds, as a positive integer. The example sets 60. |
| `ADMIN_WEB_COMMAND_LOG_LIMIT` | `config/admin_web.toml` | The entries the command log retains. The example sets 200. |
| `ADMIN_WEB_POLL_SECONDS` | `config/admin_web.toml` | The interval the console waits after one completed panel read before its next read of that panel. The example sets 60. |
| `ADMIN_WEB_APP_URL` | `config/admin_web.toml` | The absolute HTTP or HTTPS address the console's App link points at, at the root and without credentials, wildcard, whitespace, query or fragment. The example sets `http://localhost:8037/`. |
| `ADMIN_WEB_REPOSITORY_URL` | `config/admin_web.toml` | The HTTPS GitHub owner and repository address the console's GitHub link opens. |

`ADMIN_WEB_ANONYMOUS_SESSION_LIMIT` and `ADMIN_WEB_ANONYMOUS_SESSION_WINDOW_SECONDS` set the anonymous session creation limit for a backend process, shared by every client. A fresh anonymous session granted at `GET /auth/session` consumes one count, and a live anonymous or signed-in session consumes none. The counted creation times live in the process's memory, so a backend restart clears the count. [Console access and records](/docs/operations/admin-console/access-and-records.md) states the response when the limit is reached.

The Administration backend reads this family through the same settings owner, and the course-exploration launcher composes its own families alone, so no administration key reaches the serving web process. The Administration lock path and its failed-attempt limit are fixed in code rather than configuration, as [Console access and records](/docs/operations/admin-console/access-and-records.md) states.

## Reading and writing a file

The administration command reads one configuration file and saves one key of it. A read of a subsystem file returns the values that file holds, so a hub key is returned as its reference table rather than the vector the table points at. A read of the environment file returns every assignment in plain text, as the file spells it.

A save names one configuration file, one key that file carries, and one JSON literal, such as setting `WEB_PORT` of `config/web.toml` to `18026`. `CURRENT_ACADEMIC_YEAR` in `config/curriculum.toml` is an ordinary key of that editor, and so are `WEB_EMBEDDINGS_ENABLED`, `WEB_INFERENCE_ENABLED` and `USAGE_RETENTION_DAYS` of `config/web.toml`, and every key of `config/admin_web.toml`. The literal matches the broad type the key holds: a boolean, an integer, a number, a string, an array or a table. An unlisted file, a key the file does not carry, JSON `null`, a non-finite number, a value of the wrong broad type and a value the owning settings family refuses all fail before the file changes.

The writer renders only the chosen key's text and leaves every other key with its comments, its order and its line endings. It validates the whole candidate through the settings families that own the edited key, so a value those families refuse fails before the file changes, and it replaces the file atomically. A malformed environment file refuses the save. [Settings loading](/docs/backend/settings-loading.md) describes the candidate sources, the environment-file read and the validation order. An environment-file save keeps the spelling, whitespace, comments and line endings the file holds. Every key that a settings family owns is writable, and every key of the environment file is writable. An environment-file write is published as mode 0600, and a subsystem file is published with its own permission bits. One save writes one key, so a file with several edits takes one save per key.

A file value and the effective value of a running process are different things. A process composes its settings when it builds them, and the process environment wins over the environment file, which wins over the subsystem files. A saved file reaches a process when that process next builds its settings, so restart a serving copy after a save that changes a bind, a port, a credential or a served feature switch.

The App rebuild runs four steps in order: it builds the frontend, recreates the database and embedding containers, restarts the web service, and checks the loopback bind of the restarted process. A save that changes a serving-process value takes effect at the restart step, and the bind check follows it. The administration rebuild applies a save of the administration backend's own values when it restarts that backend.

## The Compose environment file

The administration command runs Docker Compose with a Compose environment file. The file maps the raw database values and the embedding runtime values onto the keys the Compose file interpolates, and it is written to a mode-0700 directory as a mode-0600 file. Each Compose run gets its own file, and the command deletes the file and its directory when it returns. The administration side of each machine generates its own file, so the connection values reach only the machine that runs Compose.

## What the web server receives

The web server process receives only the settings it needs: the raw database settings, the normalization settings, the search settings, and the web settings, with the full similarity embedding settings added only when the site serves embedding features. Its own process environment holds `HOME`, `PATH`, and `LANG` and no administration or worker value, and the process reads no configuration file. The separation between the administration side and the web server is described in [System boundaries](/docs/architecture/boundaries.md).

## Subsystem keys

The keys a reader most often changes select data, set what the app shows, and bound the serving processes.

| Key | File | Effect |
|---|---|---|
| `CURRENT_ACADEMIC_YEAR` | `config/curriculum.toml` | Sets which curriculum periods count. |
| `ACTIVE_ACADEMIC_YEAR_WINDOW` | `config/curriculum.toml` | Sets the number of academic years inside which a listed version makes a course active. |
| `SELECTED_DATASET_ENABLED` | `config/database.toml` | Decides whether the stages and the web server read the configured database or the selected dataset. |
| `SEARCH_TIER_PRIORITY` | `config/search.toml` | Sets the order of the four search methods in the merged results. |
| `COMPARISON_HEAVY_OVERLAP_PERCENT` | `config/search.toml` | Sets the overlap threshold of the **Heavily overlapping** verdict. |
| `COMPARISON_PARTIAL_OVERLAP_PERCENT` | `config/search.toml` | Sets the overlap threshold of the **Partly overlapping** verdict. |
| `COMPARISON_SAME_AREA_PERCENT` | `config/search.toml` | Sets the overall-relatedness threshold of the **Same area, different content** verdict. |
| `COMPARISON_LOOSE_RELATED_PERCENT` | `config/search.toml` | Sets the overall-relatedness threshold of the **Loosely related** verdict. |
| `RECOMMENDATION_MIN_RELATEDNESS` | `config/search.toml` | Sets the relatedness floor of the Recommended list. |
| `RECOMMENDATION_NEAR_DUPLICATE_PERCENT` | `config/search.toml` | Sets the overlap share above which a candidate is a near-duplicate and left out of recommendations. |
| `WEB_HOST` | `config/web.toml` | The loopback address the web server binds. |
| `WEB_PORT` | `config/web.toml` | The TCP port the web server binds. |
| `WEB_WORKERS` | `config/web.toml` | The number of serving processes. |
| `WEB_EMBEDDINGS_ENABLED` | `config/web.toml` | Serves semantic matching, the Compare feature and the Recommended list. The example sets `true`. |
| `WEB_INFERENCE_ENABLED` | `config/web.toml` | Serves inferred data and its controls on every surface. The example sets `true`. |
| `USAGE_RETENTION_DAYS` | `config/web.toml` | The days of request records the usage report retains. A requested window in hours may not exceed that retention. |
| `ADMIN_WEB_HOST` | `config/admin_web.toml` | The loopback address the Administration backend binds. The example sets `127.0.0.1`. |
| `ADMIN_WEB_PORT` | `config/admin_web.toml` | The TCP port the backend binds. The example sets 8039. |
| `ADMIN_WEB_ORIGIN` | `config/admin_web.toml` | The exact external HTTPS origin of the administration site. The example sets `https://localhost:8039`. |
| `ADMIN_WEB_SESSION_IDLE_MINUTES` | `config/admin_web.toml` | The idle lifetime of one Administration session. The example sets 30. |
| `ADMIN_WEB_SESSION_MAX_HOURS` | `config/admin_web.toml` | The total lifetime of one Administration session. The example sets 12. |
| `ADMIN_WEB_ANONYMOUS_SESSION_LIMIT` | `config/admin_web.toml` | The count of fresh anonymous sessions one backend process admits in the sliding window. The example sets 10. |
| `ADMIN_WEB_ANONYMOUS_SESSION_WINDOW_SECONDS` | `config/admin_web.toml` | The length of that window in seconds. The example sets 60. |
| `ADMIN_WEB_COMMAND_LOG_LIMIT` | `config/admin_web.toml` | The entries the Command log retains. The example sets 200. |

Only the usage report reads the retention key, and a serving process holds no retention value.

The remaining keys for each subsystem are documented with their behavior:

- Ingestion and normalization: [Ingestion](/docs/backend/catalogue/ingestion.md)
- The data model: [Data model](/docs/backend/catalogue/data-model.md)
- Teaching text and translation: [Translation](/docs/backend/text-and-vectors/translation.md)
- Embedding generation and hubs: [Embeddings](/docs/backend/text-and-vectors/embeddings.md)
- Search, comparison, recommendations, and the route policy: [Search](/docs/backend/search-and-discovery/search.md), [Comparison](/docs/backend/search-and-discovery/comparison.md), [Recommendations](/docs/backend/search-and-discovery/recommendations.md), [Minimum route](/docs/backend/prerequisites/minimum-route.md)
- Inference runtime and selection: [Inference](/docs/backend/inference/inference.md)
- The read API: [Web API](/docs/backend/interfaces/web-api.md)
- Administration and worker policy: [Operator menu](/docs/operations/operator-menu.md), [Worker sessions](/docs/operations/worker-sessions.md)
