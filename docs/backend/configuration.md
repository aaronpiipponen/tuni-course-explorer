# Configuration

TUNI Course Explorer reads portable values from the subsystem files and machine-local values from the environment file, and fails a settings read when a required value is missing or malformed.

The repository keeps one subsystem file per configuration subsystem under `config/`. Values that must change when a copy is set up on another machine live outside those files, in the environment file at the repository root. One [settings owner](/docs/reference/glossary.md#configuration) composes both, so an ordinary command reads its configuration with no manual sourcing step.

## Where values live

The seven subsystem files under `config/` each own the portable settings of one subsystem. The two hub files under `config/derived/` hold the embedding hub vectors, and `config/wiki.json` selects which pages the documentation wiki renders.

| File | Owns |
|---|---|
| `config/curriculum.toml` | Raw capture location and checkpoint policy, the public curriculum source, normalization, and the local ingestion controller state root |
| `config/database.toml` | PostgreSQL connection components, the selected-dataset switch, and the administrative state root |
| `config/search.toml` | The embedding runtime and generation contract, the local embedding controller state root, the two embedding hub references, and the search, comparison, recommendation, and route policy |
| `config/translation.toml` | The translation runtime and provenance contract, the translation controller state root and health attempts, and the shared worker health interval and stop timeout |
| `config/inference.toml` | The inference runtime contract, the local fit keys, the candidate selection and rerank policy, and the inference controller policy |
| `config/worker.toml` | The worker connection, setup, dataset, and local lifecycle policy |
| `config/web.toml` | The web bind, process count, and browser-drawing limit |

The tracked templates for these paths live under `examples/`. An operator copies `examples/config/*.toml`, `examples/config/wiki.json`, and `examples/config/derived/*.json` into `config/`, and `examples/.env.example` into the environment file at the repository root. Git ignores these working copies, so each checkout carries its own settings without changing the templates. The wider setup steps are described in [Installation](/docs/getting-started/installation.md).

Each subsystem file holds top-level keys whose names are the settings the code reads. A key defined in two files is rejected before any setting loads.

![The settings owner reads the subsystem files, the hub files, the environment file, and the process environment. It hands settings to the stages, the web server, and the Compose environment file, which feeds Docker Compose. A dashed arrow shows that the example files are copied at setup into the subsystem files and the hub files.](/docs/diagrams/configuration-sources.svg)

## Deciding between a subsystem file and the environment file

One test decides where a value belongs. A value that must change when the copy is set up on another machine goes in the environment file. Every other value goes in the subsystem file that owns the value.

The machine-local values are the database password and the three worker connection values. The tracked template `examples/.env.example` carries exactly these keys:

| Key | Value |
|---|---|
| `POSTGRES_PASSWORD` | The database password |
| `TRANSLATION_CONTROLLER_SSH_TARGET` | How the administration command reaches the worker |
| `TRANSLATION_CONTROLLER_WSL_DISTRIBUTION` | The runtime environment on the worker that runs the stage |
| `TRANSLATION_CONTROLLER_WORKER_PROJECT_ROOT` | The worker checkout location |

> [!WARNING]
> Credentials belong in the ignored environment file. Subsystem files hold portable settings, and their tracked templates must be credential-free.

Everything else is portable. The two embedding hub values are a special case, since a subsystem file holds only their path and the settings owner resolves the referenced JSON artifact. `config/search.toml` points at `config/derived/embedding-hub.json` and `config/derived/embedding-outcomes-hub.json`. A similarity read that finds a hub file missing or malformed fails. The pages linked below name the keys a reader is most likely to change.

## Automatic loading

A process reads the subsystem files and the environment file when it builds its settings, so no shell export step is needed. When the same key is set in more than one place, the process environment takes precedence over the environment file, and the environment file takes precedence over the subsystem files. A missing required value or an invalid value fails the read with a clear error.

Every settings family validates its own values before it is returned. A bind address other than `127.0.0.1`, an academic year bound that is not two consecutive four-digit years, a port outside 1 to 65535, a worker path that is not absolute, or a state root that is not repository-relative all fail at load. The settings classes and the composition order are described in [Settings loading](/docs/backend/settings-loading.md).

## The Compose environment file

The administration command runs Docker Compose with a Compose environment file. The file maps the raw database values and the embedding runtime values onto the keys the Compose file interpolates, and it is written to a mode-0700 directory as a mode-0600 file. Each Compose run gets its own file, and the file and its directory are removed when the command returns. The administration side of each machine generates its own file, so the connection values stay local to the machine that runs Compose.

## What the web server receives

The web server process receives only the settings it needs: the raw database settings, the normalization settings, the full similarity embedding settings, the search settings, and the web settings. Its own process environment holds `HOME`, `PATH`, and `LANG` and no administration or worker value, and the process reads no configuration file. The separation between the administration side and the web server is described in [System boundaries](/docs/architecture/boundaries.md).

## Subsystem keys

The keys a reader most often changes are the ones that select data and set what the app shows. `CURRENT_ACADEMIC_YEAR` and `ACTIVE_ACADEMIC_YEAR_WINDOW` in `config/curriculum.toml` set which curriculum periods count and how long a listed version keeps a course active. `SELECTED_DATASET_ENABLED` in `config/database.toml` decides whether the stages and the web server read the configured database or the selected dataset. `SEARCH_TIER_PRIORITY` and the comparison and recommendation thresholds in `config/search.toml` set the merged result order and the meter outcomes. `WEB_HOST`, `WEB_PORT`, and `WEB_WORKERS` in `config/web.toml` set the bind and the process count.

The remaining keys for each subsystem are documented with their behavior:

- Ingestion and normalization: [Ingestion](/docs/backend/catalogue/ingestion.md)
- The data model: [Data model](/docs/backend/catalogue/data-model.md)
- Teaching text and translation: [Translation](/docs/backend/text-and-vectors/translation.md)
- Embedding generation and hubs: [Embeddings](/docs/backend/text-and-vectors/embeddings.md)
- Search, comparison, recommendations, and the route policy: [Search](/docs/backend/search-and-discovery/search.md), [Comparison](/docs/backend/search-and-discovery/comparison.md), [Recommendations](/docs/backend/search-and-discovery/recommendations.md), [Minimum route](/docs/backend/prerequisites/minimum-route.md)
- Inference runtime and selection: [Inference](/docs/backend/inference/inference.md)
- The read API: [Web API](/docs/backend/interfaces/web-api.md)
- Administration and worker policy: [Operator menu](/docs/operations/operator-menu.md), [Worker sessions](/docs/operations/worker-sessions.md)
