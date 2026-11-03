# Configuration

course-explorer reads non-secret values from the subsystem files and credentials from the environment file, and fails a settings read when a required value is missing or malformed.

The repository holds one subsystem file per configuration subsystem under `config/`. Credentials live outside those files, in the environment file at the repository root. One [settings owner](/docs/reference/glossary.md#configuration) composes both, so an ordinary command reads its configuration with no manual sourcing step.

## Where values live

The ten subsystem files under `config/` each own the non-secret settings of one subsystem. `config/wiki.json` selects which pages the documentation wiki renders, and the feedback definition lives in `config/feedback-form.json`. The embedding hub vectors are files of a serving artifact build, not configuration.

| File | Owns |
|---|---|
| `config/curriculum.toml` | Raw capture location and checkpoint policy, the public curriculum source, normalization, and the local ingestion controller state root |
| `config/database.toml` | PostgreSQL connection components, the configured example database name, and the administrative state root |
| `config/search.toml` | The embedding runtime and generation contract, the local embedding controller state root, and the search, comparison, recommendation, and route policy |
| `config/translation.toml` | The translation runtime and provenance contract, the translation controller state root and health attempts, and the shared worker health interval and stop timeout |
| `config/inference.toml` | The inference runtime contract, the local fit keys, the candidate selection and rerank policy, and the inference controller policy |
| `config/worker.toml` | The worker SSH target, WSL distribution and checkout path, the worker connection, setup, dataset, and local lifecycle policy |
| `config/admin_web.toml` | The Administration backend's loopback bind, exact HTTPS origin, session lifetimes, anonymous session creation limit, command-log entry limit, console poll interval, GitHub repository address, and this site's web and administration unit identities with the web unit's manager scope |
| `config/feedback.toml` | The feedback application store connection, the attachment root, the destination repository and visibility, the GitHub attempt timeout, and the submission allowances and body bound |
| `config/web.toml` | The external app address shared by the administration App link and the feedback exact-site boundary, the web bind, process count and malloc arena cap, child respawn bounds, browser-drawing limit, the two served feature switches, the two retained-cache byte regions, the four request-input bounds, and the usage-record retention |
| `config/admission.toml` | Admission control of the read-only API: the serving switch, the load score that places the site in a regime, the counter lifetimes, the per-user light and heavy limits, the heavy queue caps, and the cost curves |

The tracked templates for these paths live under `examples/`. An operator copies `examples/config/*.toml`, `examples/config/wiki.json` and `examples/config/feedback-form.json` into `config/`, and `examples/.env.example` into the environment file at the repository root. Git ignores these working copies, so each checkout carries its own settings without changing the templates. The wider setup steps are described in [Installation](/docs/getting-started/installation.md).

The `self-host example` workflow copies every absent template and leaves every present working file as it is. It writes the user-dependent keys it is given: `WEB_APP_URL`, the optional `FEEDBACK_GITHUB_TOKEN`, and, in user mode, `ADMIN_SITE_WEB_SERVICE_UNIT`, `ADMIN_SITE_ADMIN_SERVICE_UNIT` and `ADMIN_SITE_WEB_SERVICE_SCOPE`. When it creates the environment file, it generates `POSTGRES_PASSWORD` and `FEEDBACK_POSTGRES_PASSWORD` with `secrets.token_urlsafe(32)` and publishes the file at mode 0600. Every other value comes from the copied example file. A supplied publication token refuses when the environment file already exists, because that file owns its sender credential.

The `self-host real-database` workflow copies nothing. It refuses when a prepared working file is absent, so the example workflow prepares the working files first.

Each subsystem file holds top-level keys whose names are the settings the code reads. A key defined in two files is rejected before any setting loads. Environment keys compare case-insensitively, matching the runtime composition, so one key written in two cases is refused as one key assigned twice.

![The example files are copied at setup into the subsystem files and the environment file. The settings owner reads the subsystem files and the environment file, whose values the process environment overrides, and hands settings to the web server, the stages and the Compose environment file, which feeds Docker Compose. The Administration backend loads its own family from `config/admin_web.toml` in its own process, and a serving artifact build writes the hub pair that the web server reads.](/docs/diagrams/configuration-sources.svg)

The Administration backend loads its own family from `config/admin_web.toml` in its own process. No administration key reaches the serving web process, whose launcher composes its own families alone.

## Deciding between a subsystem file and the environment file

One test decides where a value belongs. The ignored environment file holds credentials only: passwords, tokens and other actual secrets. Every non-secret value, including machine and site identity, goes in the subsystem file that owns the value.

The ignored environment file holds the two database passwords and any provider credential the site uses. The tracked template `examples/.env.example` carries credential placeholders:

| Key | Value |
|---|---|
| `POSTGRES_PASSWORD` | The curriculum database password |
| `FEEDBACK_POSTGRES_PASSWORD` | The password of the feedback application store |
| `FEEDBACK_GITHUB_TOKEN` | The GitHub credential that only the feedback sender reads |

Worker identity is non-secret subsystem configuration. `config/worker.toml` holds `TRANSLATION_CONTROLLER_SSH_TARGET`, `TRANSLATION_CONTROLLER_WSL_DISTRIBUTION` and `TRANSLATION_CONTROLLER_WORKER_PROJECT_ROOT`: how the administration command reaches the worker, the WSL distribution that runs the stage, and the worker checkout location. The target and the distribution are each 1 to 64 ASCII letters, digits, underscore, dot or hyphen. The project root is an absolute POSIX path without dot components or percent characters.

Site identity is non-secret subsystem configuration too. `config/admin_web.toml` holds `ADMIN_SITE_WEB_SERVICE_UNIT`, `ADMIN_SITE_ADMIN_SERVICE_UNIT` and `ADMIN_SITE_WEB_SERVICE_SCOPE`. The two unit keys are each one plain service basename, such as `tuni-course-explorer-web.service` and `tuni-course-explorer-admin-web.service`, rather than a path or a command. A value that is not one service basename fails the settings read. `ADMIN_SITE_WEB_SERVICE_SCOPE` selects the manager of the feature web unit alone, accepts `user` or `system`, and defaults to `user`. The administration unit always belongs to the user manager. Only the administration command reads these keys, to report the state of the web unit, to run the App rebuild and the administration rebuild. The administration rebuild builds the administration console and restarts the administration backend. The web process receives no administration value and reads no site unit identity.

A system-scope App rebuild restarts the feature unit with `sudo -n /usr/bin/systemctl restart`, so the host installs the exact passwordless grant for that one unit and command. A user-scope rebuild runs `systemctl --user restart`. [The site web unit](/docs/getting-started/self-hosting.md#the-site-web-unit) states both unit installations and the grant.

The two rebuild scopes apply a saved file differently. The App rebuild restarts the site's web server, so a save that changes a value of the serving process takes effect at that step. The administration rebuild queues the restart of the administration backend, so a save that changes a value of that backend takes effect at that step.

> [!WARNING]
> The database passwords belong in the ignored environment file. Subsystem files hold non-secret settings, and their tracked templates must be credential-free.

Every other value is non-secret. The two embedding hubs are not settings: a similarity read opens the current serving artifact build and reads the pair it carries. A read that finds the build or a hub file missing or malformed fails. The pages linked below name the keys a reader is most likely to change.

## Automatic loading

A process reads the subsystem files and the environment file when it builds its settings, so no shell export step is needed. When the same key is set in more than one place, the process environment takes precedence over the environment file, and the environment file takes precedence over the subsystem files. A missing required value or an invalid value fails the read with a clear error.

Every settings family validates its own values before it is returned. A bind address other than `127.0.0.1`, an academic year bound that is not two consecutive four-digit years, a port outside 1 to 65535, a worker path that is not absolute, a state root that is not repository-relative, an administration origin that is not one exact `https://` origin without credentials, path, query or fragment, or an app address with credentials, a path other than the root, a wildcard, whitespace, query or fragment all fail at load. The settings classes and the composition order are described in [Settings loading](/docs/backend/settings-loading.md).

## The administration backend's own file

`config/admin_web.toml` holds the 10 administration keys of the Administration backend and the three site identities of this checkout. Every key is validated, and all but `ADMIN_SITE_WEB_SERVICE_SCOPE` are required, so a site states its own origin and its own units. The console's App link reads `WEB_APP_URL` from `config/web.toml`.

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
| `ADMIN_WEB_REPOSITORY_URL` | `config/admin_web.toml` | The HTTPS GitHub owner and repository address the console's GitHub link opens. |
| `ADMIN_SITE_WEB_SERVICE_UNIT` | `config/admin_web.toml` | The systemd unit that runs this checkout's web process. |
| `ADMIN_SITE_ADMIN_SERVICE_UNIT` | `config/admin_web.toml` | The systemd unit that runs this checkout's administration process. |
| `ADMIN_SITE_WEB_SERVICE_SCOPE` | `config/admin_web.toml` | The manager that owns the web unit: `user` or `system`, with `user` as the default. |

`ADMIN_WEB_ANONYMOUS_SESSION_LIMIT` and `ADMIN_WEB_ANONYMOUS_SESSION_WINDOW_SECONDS` set the anonymous session creation limit for a backend process, shared by every client. A fresh anonymous session granted at `GET /auth/session` consumes one count, and a live anonymous or signed-in session consumes none. The counted creation times live in the process's memory, so a backend restart clears the count. [Console access and records](/docs/operations/admin-console/access-and-records.md) states the response when the limit is reached.

The Administration backend reads this family through the same settings owner, and the course-exploration launcher composes its own families alone, so no administration key reaches the serving web process. The Administration lock path and its failed-attempt limit are fixed in code rather than configuration, as [Console access and records](/docs/operations/admin-console/access-and-records.md) states.

## The feedback application store

`config/feedback.toml` holds the feedback application store connection, the attachment root, the destination metadata, the GitHub attempt timeout and the intake policy. The connection names a separate database from the curriculum store, so dataset replacement, reset, import, worker round trips and rotation never reach feedback records. `FEEDBACK_POSTGRES_HOST`, `FEEDBACK_POSTGRES_PORT`, `FEEDBACK_POSTGRES_DB`, `FEEDBACK_POSTGRES_USER`, `FEEDBACK_ATTACHMENTS_ROOT`, `FEEDBACK_GITHUB_REPOSITORY`, `FEEDBACK_GITHUB_VISIBILITY`, `FEEDBACK_GITHUB_TIMEOUT_SECONDS`, `FEEDBACK_BROWSER_SUBMISSIONS_PER_HOUR`, `FEEDBACK_SITE_SUBMISSIONS_PER_HOUR` and `FEEDBACK_MAX_REQUEST_BYTES` are non-secret. `FEEDBACK_POSTGRES_PASSWORD` and `FEEDBACK_GITHUB_TOKEN` belong in the ignored environment file.

| Key | Effect |
|---|---|
| `FEEDBACK_POSTGRES_HOST` | The host of the feedback application store. The example sets `127.0.0.1`. |
| `FEEDBACK_POSTGRES_PORT` | The valid TCP port of the feedback application store. The example sets 5433. |
| `FEEDBACK_POSTGRES_DB` | The name of the feedback application store. |
| `FEEDBACK_POSTGRES_USER` | The user of the feedback application store. |
| `FEEDBACK_ATTACHMENTS_ROOT` | The directory that holds stored image files. A relative path resolves against the checkout root, an absolute path is used as written, and a leading `~/` resolves against the home directory. |
| `FEEDBACK_GITHUB_REPOSITORY` | The destination in `owner/repository` form, never a URL. Feedback intake reports it and the sender publishes to it. |
| `FEEDBACK_GITHUB_VISIBILITY` | The configured destination visibility: `public` or `private`. |
| `FEEDBACK_GITHUB_TIMEOUT_SECONDS` | The bound of one GitHub issue creation attempt, as a positive finite second count, 120 in the example. |
| `FEEDBACK_BROWSER_SUBMISSIONS_PER_HOUR` | The admitted submission attempts of one browser in one rolling hour. A positive count, 5 in the example. |
| `FEEDBACK_SITE_SUBMISSIONS_PER_HOUR` | The admitted submission attempts of the whole site in one rolling hour. A positive count, 30 in the example. |
| `FEEDBACK_MAX_REQUEST_BYTES` | The bound of one submission request body, covering a declared and a streamed body. A positive byte count, 25165824 in the example. |

The front router compares a submission's single Host and Origin with the exact origin derived from `WEB_APP_URL` in `config/web.toml`, without the address's optional root slash. The feedback definition read reports the configured repository, visibility and body bound.

The feedback destination family owns the repository and visibility for both feedback families. The intake family adds the intake policy and the inherited app address, and needs no sender credential. The sender credential family owns `FEEDBACK_GITHUB_TOKEN` and `FEEDBACK_GITHUB_TIMEOUT_SECONDS`, and the token is a required nonblank secret. The sender family composes the destination and the credential for the sender process, so a full sender load validates both, while a destination save, a feedback definition read and an intake load need no token. [Settings loading](/docs/backend/settings-loading.md) names the classes and the composition order. The serving launcher composes neither sender family and forwards no token. A serving process receives no destination token, administration key or worker key.

`config/feedback-form.json` holds the feedback definition: the bilingual labels and options, each select option's optional `publicIssueByDefault`, the field kinds and limits, the unchosen select placeholder and the GitHub issue mapping. The array order is the authority for field order, and the feedback definition is read fresh when the feedback service is composed. The file is edited directly and is not part of the one-key TOML editor. Each stored image is written beneath `<attachments-root>/<field-id>/<feedback-id>/<generated-filename>`, and the feedback service reads and removes those files. The submitted display filename is kept in the attachment row alone and never names the stored file.

The same feedback definition drives the operator reads. Every field of kind `select` provides one listing filter in the feedback definition's order, and a supplied filter must name one of that field's current option values. Every field of kind `text` or `textarea` is searched identically, as one case-insensitive literal substring, and the feedback definition's order sets which matching field groups a submission first. A field the feedback definition does not carry provides no filter and no search, and stored answers of another field ID are outside both reads.

[Tables and migrations](/docs/backend/catalogue/tables-and-migrations.md#the-feedback-application-store-schema) describes the feedback tables, their own metadata and the separate migration chain.

## Reading and writing a file

The administration command reads one configuration file and saves one key of it. A read of a subsystem file returns the values that file holds, so a TOML table is returned as that table rather than resolved. A read of the environment file returns every assignment in plain text, as the file spells it.

A save names one configuration file, one key, and one JSON literal, such as setting `WEB_PORT` of `config/web.toml` to `18026`. A subsystem file takes only a key it already carries, while the environment file also accepts an absent credential alias that a settings family owns. `CURRENT_ACADEMIC_YEAR` in `config/curriculum.toml` is an ordinary key of that editor, and so are `WEB_APP_URL`, `WEB_EMBEDDINGS_ENABLED`, `WEB_INFERENCE_ENABLED` and `USAGE_RETENTION_DAYS` of `config/web.toml`, the three worker identities of `config/worker.toml`, the admission keys of `config/admission.toml`, and every administration and site key of `config/admin_web.toml`. The literal matches the broad type the key holds: a boolean, an integer, a number, a string, an array or a table. An unlisted file, a key a subsystem file does not carry, a key the environment file does not carry and no settings family owns, JSON `null`, a non-finite number, a value of the wrong broad type and a value the owning settings family refuses all fail before the file changes.

The writer renders only the chosen key's text and leaves every other key with its comments, its order and its line endings. It validates the whole candidate through the settings families that own the edited key, so a value those families refuse fails before the file changes, and it replaces the file atomically. A malformed environment file refuses the save. [Settings loading](/docs/backend/settings-loading.md) describes the candidate sources, the environment-file read and the validation order.

An environment-file save preserves the spelling, whitespace, comments and line endings the file holds. A credential key that a settings family owns is writable whether or not the environment file already carries it, and an absent key is appended as one quoted assignment in the file's first line-ending style. A key that a settings family owns and that is not a credential is refused when the file does not carry it. A key of the environment file that no settings family owns is writable only when the file already carries it. An environment-file write is published as mode 0600, and a subsystem file is published with its own permission bits.

A `config set` invocation writes one key, and the operator menu's configuration entry does the same, so a file with several edits takes one save per key through the command. [The configuration editor](/docs/operations/admin-console/settings.md#configuration-editor) states how the console saves several changed keys.

A file value and the effective value of a running process are different things. A process composes its settings when it builds them, and the process environment wins over the environment file, which wins over the subsystem files. A saved file reaches a process when that process next builds its settings, so restart a serving copy after a save that changes a bind, a port, a credential or a served feature switch.

The App rebuild runs four steps in order: it builds the frontend, recreates the database and embedding containers, restarts the web service, and checks the loopback bind of the restarted process. A save that changes a serving-process value takes effect at the restart step, and the bind check follows it. The administration rebuild applies a save of the administration backend's own values when it restarts that backend.

## The Compose environment file

The administration command runs Docker Compose with a Compose environment file. The file maps the raw database values and the embedding runtime values onto the keys the Compose file interpolates, and it is written to a mode-0700 directory as a mode-0600 file. Each Compose run gets its own file, and the command deletes the file and its directory when it returns. The administration side of each machine generates its own file, so the connection values reach only the machine that runs Compose.

## What the web server receives

The web server process receives only the settings it needs: the raw database settings, the normalization settings, the search settings, the web settings, the admission settings and the feedback connection and intake settings, with the full similarity embedding settings added only when the site serves embedding features. Its own process environment holds `HOME`, `PATH`, `LANG`, `PYTHONPATH` with the `src` directory that holds the loaded package, and `MALLOC_ARENA_MAX` from the arena setting. It holds no administration or worker value, and the process reads no settings file. A feedback request reads `config/feedback-form.json` through the feedback service, because the feedback definition is not a settings source. The separation between the administration side and the web server is described in [System boundaries](/docs/architecture/boundaries.md).

## Subsystem keys

The keys a reader most often changes select data, set what the app shows, and bound the serving processes.

Admission costs are total server core-seconds of the serving process, the database and the embedding service together, and a prerequisite graph's cost is its measured elapsed seconds. The load score is a weighted sum of the whole host's CPU utilisation and the light and heavy requests counted in one window, and it places the site in one of the three regimes.

| Key | File | Effect |
|---|---|---|
| `CURRENT_ACADEMIC_YEAR` | `config/curriculum.toml` | Sets which curriculum periods count. |
| `ACTIVE_ACADEMIC_YEAR_WINDOW` | `config/curriculum.toml` | Sets the number of academic years inside which a listed version makes a course active. |
| `EXAMPLE_POSTGRES_DB` | `config/database.toml` | Names the configured database that deploy enrollment leaves unenrolled for the example dataset. |
| `SEARCH_TIER_PRIORITY` | `config/search.toml` | Sets the order of the four search methods in the merged results. |
| `COMPARISON_HEAVY_OVERLAP_PERCENT` | `config/search.toml` | Sets the overlap threshold of the **Heavily overlapping** verdict. |
| `COMPARISON_PARTIAL_OVERLAP_PERCENT` | `config/search.toml` | Sets the overlap threshold of the **Partly overlapping** verdict. |
| `COMPARISON_SAME_AREA_PERCENT` | `config/search.toml` | Sets the overall-relatedness threshold of the **Same area, different content** verdict. |
| `COMPARISON_LOOSE_RELATED_PERCENT` | `config/search.toml` | Sets the overall-relatedness threshold of the **Loosely related** verdict. |
| `RECOMMENDATION_MIN_RELATEDNESS` | `config/search.toml` | Sets the relatedness floor of the Recommended list. |
| `RECOMMENDATION_RELATEDNESS_CEILING` | `config/search.toml` | Sets the raw relatedness that reads as 100 in the displayed **Similarity** meter, so the floor keeps its own percentage and a close match reads high. |
| `RECOMMENDATION_NEAR_DUPLICATE_PERCENT` | `config/search.toml` | Sets the overlap share above which a candidate is a near-duplicate and left out of recommendations. |
| `SEARCH_HNSW_ITERATIVE_SCAN` | `config/search.toml` | Sets the iterative-scan mode of the serving artifact build's nearest query to `relaxed_order` or `strict_order`, so the scan collects further candidates until enough rows survive the build's field and language filters. A recommendation read filters the stored rows by activity and by the excluded courses. |
| `SEARCH_HNSW_MAX_SCAN_TUPLES` | `config/search.toml` | Sets the greatest number of HNSW candidates one nearest-neighbour scan of the serving artifact build reads. |
| `SEARCH_NEIGHBOR_TABLE_ROWS_PER_CHUNK` | `config/search.toml` | Sets the nearest-neighbour rows the serving artifact build stores per query chunk. A recommendation read filters those rows and keeps its own top-K. |
| `WEB_APP_URL` | `config/web.toml` | The external root address of this site. The administration console's App link opens it, and the feedback exact Host and Origin boundary is this address without its optional root slash. HTTPS is required unless the hostname is a loopback host. |
| `WEB_HOST` | `config/web.toml` | The loopback address the web server binds. |
| `WEB_PORT` | `config/web.toml` | The TCP port the web server binds. |
| `WEB_WORKERS` | `config/web.toml` | The number of worker processes behind the front router. The router serves the configured loopback port, and each worker process listens on an ephemeral loopback port. The admission settings read the same key. |
| `WEB_MALLOC_ARENA_MAX` | `config/web.toml` | The glibc malloc arenas per web process, as a positive integer. The launcher passes it to the supervisor, and the front router and every forked worker inherit it. Fewer arenas cap the free heap each worker retains under concurrency. The example sets 2. |
| `WEB_RESPAWN_EXIT_LIMIT` | `config/web.toml` | The exits of one role, the router or one worker slot, inside the respawn window that stop the web unit instead of starting another replacement. The example sets 3. |
| `WEB_RESPAWN_WINDOW_SECONDS` | `config/web.toml` | The length of the sliding window in seconds over which the supervisor counts the exits of one role. The example sets 60. |
| `WEB_NEXT_COURSE_REPORT_CACHE_BYTES` | `config/web.toml` | The bytes of the shared next-course report region. Every worker reads and writes the same region, and clock eviction keeps it under the bound. The example sets 100663296. |
| `WEB_QUERY_EMBEDDING_CACHE_BYTES` | `config/web.toml` | The bytes of the shared query-embedding region. On a site that serves the embedding features every worker reads and writes the same region, and clock eviction keeps it under the bound. The example sets 50331648. |
| `WEB_REQUEST_MAX_COURSE_ITEMS` | `config/web.toml` | The identities one course list of a request may carry, and the entries of one `module_versions` map, as a positive count. A request over it answers status 422. The example sets 500. |
| `WEB_REQUEST_MAX_IDENTIFIER_LENGTH` | `config/web.toml` | The characters of one identity, official code, map key or module-version value, as a positive count. A request over it answers status 422. The example sets 40. |
| `WEB_REQUEST_MAX_QUERY_LENGTH` | `config/web.toml` | The characters of one search query text, as a positive count. A request over it answers status 422. The example sets 500. |
| `WEB_REQUEST_BODY_MAX_BYTES` | `config/web.toml` | The bytes of one request body the front router reads, as a positive byte count. A larger body answers status 413 before any worker process or admission decision. The example sets 73728. |
| `WEB_EMBEDDINGS_ENABLED` | `config/web.toml` | Decides whether the site serves semantic matching, the Compare feature and the Recommended list, and which artifacts the serving artifact build writes and the supervisor opens. [Serving artifact build](/docs/backend/text-and-vectors/serving-artifact-build.md#the-embedding-switch) states each mode. The example sets `true`. |
| `WEB_INFERENCE_ENABLED` | `config/web.toml` | Serves inferred data and its controls on every surface. The inference stage has no serving artifact and no coverage gate, so partial coverage is served while the switch is on. The example sets `true`. |
| `USAGE_RETENTION_DAYS` | `config/web.toml` | The days of request records the usage report retains. A requested window in hours may not exceed that retention. |
| `ADMISSION_ENABLED` | `config/admission.toml` | Serve through the front router's admission control. With it off only the classification is skipped and the request body bound still applies. When it is true the configuration requires `WEB_WORKERS` of at least 2. The example sets `true`. |
| `ADMISSION_IDENTITY_TTL_SECONDS`, `ADMISSION_COOKIE_MAX_AGE_SECONDS`, `ADMISSION_RETRY_AFTER_SECONDS`, `ADMISSION_WINDOW_SECONDS` | `config/admission.toml` | The idle lifetime of a per-user counter, the browser cookie's life, the seconds a refusal states, and the heavy budget window. The example sets 3600, 2592000, 5 and 60. |
| `ADMISSION_LOAD_WINDOW_SECONDS`, `ADMISSION_SCORE_CPU_WEIGHT`, `ADMISSION_SCORE_LIGHT_WEIGHT`, `ADMISSION_SCORE_HEAVY_WEIGHT` | `config/admission.toml` | The seconds of one-second host CPU samples and admitted light and heavy activity that the load score measures, the score per unit of whole-host CPU utilisation, and the score per light and per heavy request counted in that window. The example sets 60, 1.0, 0.012 and 0.004. |
| `ADMISSION_SCORE_HEADROOM`, `ADMISSION_SCORE_SATURATION`, `ADMISSION_SCORE_RELEASE`, `ADMISSION_LIGHT_LOAD_FLOOR` | `config/admission.toml` | The score at or below which the site is in the headroom regime, the score at or above which it is in the saturated regime, the score below which a saturated site returns to the middle regime, and the fraction of the headroom light limits that applies at saturation. `ADMISSION_SCORE_HEADROOM` must be at most `ADMISSION_SCORE_RELEASE`, and `ADMISSION_SCORE_RELEASE` must be below `ADMISSION_SCORE_SATURATION`. The example sets `ADMISSION_SCORE_HEADROOM` to 0.60, `ADMISSION_SCORE_SATURATION` to 1.05, `ADMISSION_SCORE_RELEASE` to 0.90 and `ADMISSION_LIGHT_LOAD_FLOOR` to 0.25. |
| `ADMISSION_LIGHT_OPERATIONS_PER_MINUTE`, `ADMISSION_LIGHT_BURST`, `ADMISSION_LIGHT_CONCURRENCY` | `config/admission.toml` | The per-user light rate, burst and concurrency at headroom. The example sets 120, 20 and 8. |
| `ADMISSION_HEAVY_BUDGET_CORE_SECONDS`, `ADMISSION_HEAVY_BUDGET_SATURATED_CORE_SECONDS`, `ADMISSION_HEAVY_SLOTS`, `ADMISSION_HEAVY_QUEUE_HEADROOM_LIMIT`, `ADMISSION_HEAVY_QUEUE_MIDDLE_LIMIT`, `ADMISSION_HEAVY_QUEUE_SATURATED_LIMIT` | `config/admission.toml` | The per-user heavy budget per window at headroom and at saturation, the global heavy slots at headroom, and the waiting tickets the queue admits at headroom, in the middle regime and at saturation. The slot arithmetic caps the heavy slots at one fewer than `WEB_WORKERS`, so one worker process is always free of heavy work. The example sets 120, 40, 3, 64, 32 and 16. |
| `ADMISSION_RECOMMENDATION_ACTIVE_HEAVY_BASIS`, `ADMISSION_RECOMMENDATION_INACTIVE_HEAVY_BASIS`, `ADMISSION_NEXT_COURSES_ACTIVE_HEAVY_BASIS`, `ADMISSION_NEXT_COURSES_INACTIVE_HEAVY_BASIS`, `ADMISSION_GRAPH_HEAVY_SECONDS`, `ADMISSION_SEARCH_INACTIVE_COST_CORE_SECONDS` | `config/admission.toml` | The basis size from which a recommendation and a next-courses request are heavy in each scope, the elapsed seconds from which a graph is heavy, and the fixed cost of a search that includes inactive courses. The example sets 92, 59, 317, 121, 1.0 and 0.22689. |
| `ADMISSION_RECOMMENDATION_ORIGIN_BASIS`, `ADMISSION_RECOMMENDATION_ACTIVE_KNEE_BASIS`, `ADMISSION_RECOMMENDATION_INACTIVE_KNEE_BASIS` | `config/admission.toml` | The recommendation curve's origin basis and the knee basis of each scope. Each knee must be above the origin. The example sets 3, 181 and 244. |
| `ADMISSION_RECOMMENDATION_ACTIVE_ORIGIN_COST`, `ADMISSION_RECOMMENDATION_ACTIVE_SLOPE`, `ADMISSION_RECOMMENDATION_ACTIVE_TAIL_COST`, `ADMISSION_RECOMMENDATION_ACTIVE_TAIL_SLOPE` | `config/admission.toml` | The active-only recommendation curve: origin cost, slope, tail cost and tail slope. The example sets 0.28268, 0.00808, 1.72143 and 0.00499. |
| `ADMISSION_RECOMMENDATION_INACTIVE_ORIGIN_COST`, `ADMISSION_RECOMMENDATION_INACTIVE_SLOPE`, `ADMISSION_RECOMMENDATION_INACTIVE_TAIL_COST`, `ADMISSION_RECOMMENDATION_INACTIVE_TAIL_SLOPE` | `config/admission.toml` | The recommendation curve that includes inactive courses, with the same four values. The example sets 0.10363, 0.01625, 4.01941 and 0.00817. |
| `ADMISSION_NEXT_COURSES_ORIGIN_BASIS`, `ADMISSION_NEXT_COURSES_ACTIVE_KNEE_BASIS`, `ADMISSION_NEXT_COURSES_INACTIVE_KNEE_BASIS` | `config/admission.toml` | The next-courses curve's origin basis and the knee basis of each scope. Each knee must be above the origin. The example sets 3, 230 and 398. |
| `ADMISSION_NEXT_COURSES_ACTIVE_ORIGIN_COST`, `ADMISSION_NEXT_COURSES_ACTIVE_SLOPE`, `ADMISSION_NEXT_COURSES_ACTIVE_TAIL_COST`, `ADMISSION_NEXT_COURSES_ACTIVE_TAIL_SLOPE` | `config/admission.toml` | The active-only next-courses curve. The example sets 0.10883, 0.00358, 0.92217 and 0.0009. |
| `ADMISSION_NEXT_COURSES_INACTIVE_ORIGIN_COST`, `ADMISSION_NEXT_COURSES_INACTIVE_SLOPE`, `ADMISSION_NEXT_COURSES_INACTIVE_TAIL_COST`, `ADMISSION_NEXT_COURSES_INACTIVE_TAIL_SLOPE` | `config/admission.toml` | The next-courses curve that includes inactive courses. The example sets 0.05998, 0.00803, 3.23171 and 0.00061. |

The administration keys and the three site identities have their own table, with their effects and example values, in [The administration backend's own file](#the-administration-backends-own-file).

Only the usage report reads the retention key at runtime, and the configuration editor lists and saves it in `config/web.toml`. A serving process holds no retention value.

Further keys of each subsystem are documented with the behavior they set:

- Ingestion and normalization: [Ingestion](/docs/backend/catalogue/ingestion.md)
- The data model: [Data model](/docs/backend/catalogue/data-model.md)
- Teaching text and translation: [Translation](/docs/backend/text-and-vectors/translation.md)
- Embedding generation and hubs: [Embeddings](/docs/backend/text-and-vectors/embeddings.md)
- Search, comparison, recommendations, and the route policy: [Search](/docs/backend/search-and-discovery/search.md), [Comparison](/docs/backend/search-and-discovery/comparison.md), [Recommendations](/docs/backend/search-and-discovery/recommendations.md), [Minimum route](/docs/backend/prerequisites/minimum-route.md)
- Inference runtime, generation, selection and rerank: [Inference](/docs/backend/inference/inference.md), [Inference scheduling and disposition](/docs/backend/inference/inference-scheduling.md)
- The read API: [Web API](/docs/backend/interfaces/web-api.md)
- Administration and worker policy: [Operator menu](/docs/operations/operator-menu.md), [Worker sessions](/docs/operations/worker-sessions.md)
