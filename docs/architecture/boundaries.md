# System boundaries

TUNI Course Explorer separates the read-only request path, the browser-held user state, official data, and the preparation work, and each separation is enforced in code.

The preparation side fills the selected dataset, and the read-only side serves requests from it. The database that holds the selected dataset is the only thing both sides touch: the stages write it, and the web server reads it.

![A preparation side holds the administration command and the worker, a read-only side holds the browser app and the web server, and a database between them holds the selected dataset. The administration command writes the dataset, the web server reads it, the browser app sends requests with the user state, and the administration command runs the remote stages on the worker. The accent outline marks the read-only side.](/docs/diagrams/system-boundaries.svg)

## A read-only web server

No route of the web server writes data, starts or controls a stage, or reaches the worker. The route set is fixed: ten read commands under `/api/`, two shell documents for the browser app, and one mounted asset directory. The package imports no administration module, no translation module, and no ingestion or embedding command module.

The launcher passes only named settings into the server process: the five settings families the process needs, the inherited `HOME`, `PATH`, and `LANG`, and the environment-only marker. A child built that way reads no configuration file, so no other value reaches it. The web package tests assert the exact route set, the forbidden imports, and the setting allowlist.

The reason is that the request path serves readers only. Model credentials, stage control, and the worker connection stay with the administration command.

## User state in the browser

The selected and completed courses, the exclusions, the structure edits, the open tab, and the app language live in profiles in the browser's local storage. They reach the server only as request inputs, and a route that needs courses accepts the canonical identities and the toggles the browser sends. The server stores no profile and returns none, so the profiles belong to the browser that holds them.

## Official and inferred data apart

Official data is what the ingestion stage writes from the public curriculum source. Inferred prerequisites and equivalence groups are stored in their own tables with their own coverage state, and the inference stage writes inferred output without modifying an official row. University facts and derived claims never share a store, so the interface can mark each derived claim as such. The app shows inferred prerequisites only behind the **Inferred** toggle and marks each one **inferred**.

A translation is stored beside the text it was made from and does not replace it. Official text takes precedence, and a stale translation is reported and never used. [Data model](/docs/backend/catalogue/data-model.md) describes the stores, and [Inference](/docs/backend/inference/inference.md) describes what the inference stage reads and writes.

## Inference on local models

The inference stage runs language models on the worker, and the web server holds no model or worker credential. The inference subsystem file pins each artifact by revision and SHA-256 and names the loopback address and port the provider posts to.

Fit decides which local model receives a target. A target call starts only when its prompt tokens plus the configured output cap and headroom fit inside the context of one configured local key. A packet that fits no configured key is never shortened. It fails that target as one capacity failure, and the whole packet is either sent or reported as failed. The key list, the output cap, and the headroom are described in [Inference scheduling and disposition](/docs/backend/inference/inference-scheduling.md).

The web server receives none of these settings. Its launcher composes the database, normalization, embedding, search, and web families, so no inference value and no worker connection value can reach the serving process.

## Configuration ownership

The subsystem files hold portable settings, which do not have to change when setting up another machine. The environment file holds values that must change per machine: the database password and the three worker connection values. Tracked templates live under `examples/config/`, and the runtime copies under `config/` are ignored by Git. A checkout can customize its portable settings without changing the templates. Each value is validated before the process that reads it starts work, and a missing or malformed value fails the read. [Configuration](/docs/backend/configuration.md) lists the files and the keys.

## One current schema and format

Every process reads the database schema, the file formats, and the state files of the running code, and a mismatch fails before work starts. A database that is not at the executing checkout's single migration head is refused with fixed guidance, and a state file whose contents do not match its closed schema is refused rather than interpreted. The inference result contract accepts only the `v2` schema version, and a stored prerequisite expression outside the current node vocabulary fails the read.

Data and code move together through explicit setup and migration, so a read is answered against the schema and the formats of the running code alone.
