# Settings loading

The configuration layer loads each settings family from the subsystem files, the device-local environment file, and process overrides, and validates the values before use.

## Settings classes

Every class in the table below lives in `src/course_explorer/config.py` and subclasses `ConfiguredSettings`. The same file also defines `InferenceLocalVariantSettings`, which subclasses `BaseModel` instead and types the `INFERENCE_LOCAL_VARIANTS` field. The TOML file column names the runtime file that carries the class's keys. Its tracked template lives under `examples/config/`.

| Class | TOML file | Purpose |
|---|---|---|
| `WebAppSettings` | `config/web.toml` | The one external app address shared by the administration App link and the feedback exact-site boundary, with its derived origin |
| `WebSettings` | `config/web.toml` | The inherited app address, loopback bind, process count and malloc arena cap, child respawn bounds, browser-drawing limit, the two retained-cache byte regions, the four request-input bounds, and the two served feature switches |
| `UsageSettings` | `config/web.toml` | The retention window of the per-request usage records |
| `AdmissionSettings` | `config/admission.toml`, and `config/web.toml` for the shared `WEB_WORKERS` key | The front router's admission policy of the read-only API and the shared `WEB_WORKERS` worker count |
| `AdminWebSettings` | `config/admin_web.toml`, and `config/web.toml` for the inherited app address | Administration loopback bind, exact HTTPS origin, session lifetimes, the anonymous session creation limit, the command-log entry limit, the console poll interval, the GitHub repository address and the console's App link address |
| `DatabaseSettings` | `config/database.toml` | Curriculum PostgreSQL connection components, the configured example database name, and the administrative state root |
| `FeedbackSettings` | `config/feedback.toml` | The feedback application store connection and the attachment root |
| `FeedbackIntakeSettings` | `config/web.toml` for the inherited app address, `config/feedback.toml` for the destination and intake policy | The feedback site origin derived from the app address, destination repository and visibility, the two hourly submission allowances and the request body bound |
| `FeedbackDestinationSettings` | `config/feedback.toml` | The destination repository and visibility shared by the intake and sender families |
| `FeedbackSenderCredentialsSettings` | `config/feedback.toml` for the timeout, the environment file for `FEEDBACK_GITHUB_TOKEN` | The required sender token and the bound of one GitHub publication attempt |
| `FeedbackSenderSettings` | The destination and the credential families | The sender's destination, credential and attempt timeout composed together |
| `AdministrativeDatasetSettings` | `config/database.toml` with the derived prefixes in `config/worker.toml` | Dataset-role state root, the two derived database-name prefixes, and the database operation timeout `ADMIN_DATABASE_OPERATION_TIMEOUT_SECONDS` |
| `AdministrativeSiteSettings` | `config/admin_web.toml` | The two systemd service identities of this site's web and administration processes, and the manager scope of the feature web unit |
| `CaptureSettings` | `config/curriculum.toml` | Raw capture location and checkpoint response count |
| `KoriSettings` | `config/curriculum.toml` | Anonymous public Kori source, batching, retry, and academic-year bounds |
| `NormalizationSettings` | `config/curriculum.toml` | Current academic year, activity window, and course-guide base |
| `LocalLifecycleSettings` | `config/curriculum.toml` and `config/search.toml` for state roots, `config/worker.toml` for timing | Local stage state roots and bounded startup, polling, and stop policy |
| `EmbeddingRuntimeSettings` | `config/search.toml` | Loopback embedding runtime, generation chunking, and pinned artifact identity |
| `SearchSettings` | `config/search.toml` | Search tier order, the request policy of one search query embedding, comparison thresholds, recommendation policy, and the route compact-node limit |
| `TranslationSettings` | `config/translation.toml` | Loopback translation runtime, model identity, and generation limits |
| `TranslationControllerSettings` | `config/translation.toml` for its own root and attempts, `config/worker.toml` for the connection base | Translation controller state root and health attempts |
| `InferenceSettings` | `config/inference.toml` | Loopback generation runtime, the two local fit keys, and closed policy literals |
| `InferenceContextSettings` | `config/inference.toml` | Multiview evaluation fields and the fusion rank offset |
| `InferenceSelectionSettings` | `config/inference.toml` | Embedding pool depth and final candidate ceiling |
| `InferenceRerankSettings` | `config/inference.toml` | Loopback cross-encoder runtime and its serving contract |
| `InferenceRerankInputSettings` | `config/inference.toml` | Cross-encoder query and document bounds and text layout |
| `InferenceControllerSettings` | `config/inference.toml` for its own root and attempts, `config/worker.toml` for the connection base | Inference controller state root and health attempts |
| `WorkerConnectionSettings` | `config/worker.toml` for the worker identity and connect timeout, `config/translation.toml` for the health interval and stop timeout | Worker connection shared by both remote stages |
| `WorkerSetupSettings` | `config/worker.toml` | Expected worker repository origin and the setup timeout |
| `WorkerRuntimeSettings` | `config/worker.toml` | Portable generation CPU thread geometry `WORKER_RUNTIME_THREADS` and `WORKER_RUNTIME_THREADS_BATCH` |
| `WorkerGpuRebootSettings` | `config/worker.toml` | The shared checkpoint-reboot interval |

A code-owned default exists only where a field declares one. `EmbeddingRuntimeSettings` is the one embedding family, so the Compose environment file and a generation run load it without a dataset's serving artifacts. A similarity consumer receives its hub pair from the current serving artifact build, not from these settings.

The search command projects the query embedding request policy onto the embedding settings it loaded. `SEARCH_EMBEDDING_REQUEST_TIMEOUT_SECONDS` and `SEARCH_EMBEDDING_MAX_ATTEMPTS` of `SearchSettings` replace the loaded timeout and attempt count through `model_copy`, and that projection is the only settings the one `EmbeddingProvider` of the request receives. The caller passes the opened build's catalogue hub beside the settings. `SearchSettings` validates both values before the copy, and the copy itself runs no further validation.

## The shared base and its file sources

`ConfiguredSettings` subclasses `pydantic_settings.BaseSettings` with `extra="ignore"`, an empty `env_prefix`, and `hide_input_in_errors=True`. Its `settings_customise_sources` returns the composed source tuple, in descending precedence:

1. `init_settings`, the constructor inputs.
2. `env_settings`, the process environment.
3. `LocalConfigurationSource`, the device-local `.env`.
4. The projected subsystem-file values, a callable that reads them through `configuration.read_public_configuration`.
5. Each field's own code default.

Each configurable field declares a `validation_alias`, and the alias is the configuration key. A field fixed in the code declares none, such as `embedding_dimension` on `EmbeddingRuntimeSettings`. The excerpt below shows the fields `WebSettings` declares, in addition to the inherited `WEB_APP_URL` field, before its host and port validators.

```python
class WebSettings(WebAppSettings):
    model_config = SettingsConfigDict(extra="ignore", env_prefix="")

    web_host: str = Field(validation_alias="WEB_HOST")
    web_port: int = Field(validation_alias="WEB_PORT")
    web_workers: int = Field(validation_alias="WEB_WORKERS", gt=0)
    web_malloc_arena_max: int = Field(validation_alias="WEB_MALLOC_ARENA_MAX", gt=0)
    web_respawn_exit_limit: int = Field(validation_alias="WEB_RESPAWN_EXIT_LIMIT", gt=0)
    web_respawn_window_seconds: int = Field(validation_alias="WEB_RESPAWN_WINDOW_SECONDS", gt=0)
    prerequisite_graph_max_elements: int = Field(
        validation_alias="PREREQUISITE_GRAPH_MAX_ELEMENTS", gt=0
    )
    embeddings_enabled: bool = Field(validation_alias="WEB_EMBEDDINGS_ENABLED")
    inference_enabled: bool = Field(validation_alias="WEB_INFERENCE_ENABLED")
    web_next_course_report_cache_bytes: int = Field(
        validation_alias="WEB_NEXT_COURSE_REPORT_CACHE_BYTES", gt=0
    )
    web_query_embedding_cache_bytes: int = Field(
        validation_alias="WEB_QUERY_EMBEDDING_CACHE_BYTES", gt=0
    )
    web_request_max_course_items: int = Field(validation_alias="WEB_REQUEST_MAX_COURSE_ITEMS", gt=0)
    web_request_max_identifier_length: int = Field(
        validation_alias="WEB_REQUEST_MAX_IDENTIFIER_LENGTH", gt=0
    )
    web_request_max_query_length: int = Field(validation_alias="WEB_REQUEST_MAX_QUERY_LENGTH", gt=0)
    web_request_body_max_bytes: int = Field(validation_alias="WEB_REQUEST_BODY_MAX_BYTES", gt=0)
```

`WEB_MALLOC_ARENA_MAX` requires a positive integer and is the number of glibc malloc arenas per web process. The launcher adds it to the child environment as `MALLOC_ARENA_MAX`, which glibc reads at process start, and the front router and every forked worker inherit it. The example sets 2.

`WEB_EMBEDDINGS_ENABLED` and `WEB_INFERENCE_ENABLED` are required booleans with no code default, so a site states both values in its own `config/web.toml`. The example file sets both to `true`. The four request-input bounds `WEB_REQUEST_MAX_COURSE_ITEMS`, `WEB_REQUEST_MAX_IDENTIFIER_LENGTH`, `WEB_REQUEST_MAX_QUERY_LENGTH` and `WEB_REQUEST_BODY_MAX_BYTES` each require a positive value, and `web_request_body_max_bytes` is the bound the front router reads for every request body except the feedback submission. The feedback path reads its own bound, `FEEDBACK_MAX_REQUEST_BYTES` in `config/feedback.toml`.

The supervisor resolves one `ServingSettings` bundle and every worker reads it instead of loading a family or resolving the pointer itself. The bundle holds the `WebSettings` value, the `SearchSettings` value, the `EmbeddingRuntimeSettings` value or `None` on a site with embedding features off, the configured academic year start, the resolved serving dataset, the embedding configuration identity and the shared query-embedding client. The identity and the client are `None` on a site with the embedding features off. The resolved dataset carries its connection settings and its serving identity. [Web supervisor](/docs/backend/interfaces/web-supervisor.md#startup-and-validation) states where the bundle is built, and [Serving state](/docs/backend/interfaces/serving-state.md) states what the dataset value supplies.

`WebAppSettings` declares the required `WEB_APP_URL` field with `validate_web_app_url`, and its read-only `web_app_origin` property returns that value without its optional root slash. The validator strips that one slash and delegates to `_require_exact_origin` with the loopback-HTTP allowance, so the address is one root HTTP or HTTPS address with no credentials, wildcard, whitespace, query or fragment, and HTTPS is required unless the hostname is `localhost`, `127.0.0.1` or `::1`. The value is kept as it is spelled for the App link, while the property supplies the exact origin. `WebSettings`, `AdminWebSettings` and `FeedbackIntakeSettings` subclass it, so one alias serves all three consumers and `CONFIGURATION_SETTINGS_FAMILIES` needs no separate base entry.

`AdminWebSettings` declares `ADMIN_WEB_HOST`, `ADMIN_WEB_PORT`, `ADMIN_WEB_ORIGIN`, `ADMIN_WEB_SESSION_IDLE_MINUTES`, `ADMIN_WEB_SESSION_MAX_HOURS`, `ADMIN_WEB_ANONYMOUS_SESSION_LIMIT`, `ADMIN_WEB_ANONYMOUS_SESSION_WINDOW_SECONDS`, `ADMIN_WEB_COMMAND_LOG_LIMIT`, `ADMIN_WEB_POLL_SECONDS` and `ADMIN_WEB_REPOSITORY_URL`, and it inherits `WEB_APP_URL`. The host validator reuses the loopback predicate, the port validator reuses the TCP-port predicate, the two session lifetimes, the anonymous-session count and window, the log limit and the poll interval must be positive, and `ADMIN_WEB_ORIGIN` must be one exact `https://` origin whose spelling equals `https://` plus its parsed netloc. `ADMIN_WEB_REPOSITORY_URL` is one HTTPS GitHub owner and repository address. `AdministrativeSiteSettings` declares `ADMIN_SITE_WEB_SERVICE_UNIT`, `ADMIN_SITE_ADMIN_SERVICE_UNIT` and `ADMIN_SITE_WEB_SERVICE_SCOPE`, which it reads from the same file. The administration backend loads this family in its own process through the ordinary automatic composition, so no administration key travels the web launcher's allowlist.

`LocalConfigurationSource` subclasses `EnvSettingsSource` and replaces only the value mapping, reading `configuration.read_local_configuration`. `read_public_configuration` selects exactly the aliases a class declares and reads no other file.

Inside a candidate configuration block the hook checks `configuration.candidate_settings_sources` before the marker. The returned sources are the constructor inputs, a `LocalConfigurationSource` that reads the held candidate local mapping in place of the file, and a callable that projects the held candidate public values onto the class's aliases. No process environment is a source there, so a process override and the handoff marker cannot supply a value the candidate omits.

Setting `COURSE_EXPLORER_SETTINGS_SOURCE=environment` makes `settings_customise_sources` return only the constructor and process sources, so an isolated child reads no file. `src/course_explorer_web/launch.py` uses that marker. It loads the site's web settings, composes the seven required families the web server needs, adds `EmbeddingRuntimeSettings()` only when `WEB_EMBEDDINGS_ENABLED` is true, serializes each field through `configuration.environment_value`, retains only `HOME`, `PATH`, and `LANG` from the inherited environment, sets `PYTHONPATH` to the `src` directory that holds the loaded package, adds `MALLOC_ARENA_MAX` from the web setting, and execs `python -m course_explorer_web`, whose supervisor starts one front router and its worker processes.

The seven families are the raw database, normalization, search, web, admission, feedback connection and feedback intake settings. A site with embedding features off therefore composes no embedding family, while its supervisor opens the artifact build for the catalogue and study fragments alone. A site that serves them opens the hub pair, the shared stores and the packed search group count beside those two files.

The launcher hands over no `UsageSettings` value, because the retention key belongs to the usage report alone, it supplies one value for the shared `WEB_WORKERS` key that both settings families read, and it supplies one `WEB_APP_URL` value that the web and feedback intake families both read. It forwards no `FEEDBACK_GITHUB_TOKEN`, `FEEDBACK_GITHUB_TIMEOUT_SECONDS`, administration key or worker key. A feedback request reads `config/feedback-form.json` through the feedback service, because that file is the feedback definition rather than a settings source.

## The paired database resolver

`load_database_settings_with_identity(*, role="selected")` in `src/course_explorer/config.py` returns one database settings value together with the named role's dataset identity. A Selected bootstrap state root with neither pointer returns the configured connection and `None`. Otherwise it resolves the named role once through its pointer under the configured `ADMIN_STATE_ROOT`, replaces `POSTGRES_DB` with the receipt's database name, and returns the receipt's dataset id beside the settings. Working requires its receipt.

`load_database_settings(*, role="selected")` is the ordinary loader and returns the first item of that pair. Every feature read that only needs a connection keeps Selected. The serving supervisor calls the paired resolver once for Selected and stores the result in its settings bundle, so a dataset route reads one connection and one identity that cannot name different datasets. The stages, the worker session source and their reports call the resolver for Working. Resolution opens no database, and one call resolves the role's pointer once.

`load_feedback_settings()` reads `FeedbackSettings` through the same automatic composition. The class carries the feedback application store host, port, name, user and password and the attachment root, with no dataset-role field. Its `sqlalchemy_url` property builds one `URL` from those components. `src/course_explorer/db/session.py` accepts any settings value that exposes that property as a `DatabaseConnectionSettings`, so `create_database_engine` and `database_context` serve the curriculum database and the feedback application store through one resource lifetime.

`load_feedback_intake_settings()` reads `FeedbackIntakeSettings` through the same composition. The class inherits the one app address, so its exact site origin is `web_app_origin`, and it inherits the destination repository and visibility from `FeedbackDestinationSettings` beside two positive hourly submission allowances and a positive request body bound. The origin uses the inherited validation: HTTPS unless the hostname is `localhost`, `127.0.0.1` or `::1`, and no wildcard, whitespace, credentials, path, query, fragment or invalid TCP port. The repository validator requires one `owner/repository` name.

`load_feedback_sender_settings()` reads `FeedbackSenderSettings`, which composes `FeedbackDestinationSettings` with `FeedbackSenderCredentialsSettings`. The credential class carries the required nonblank `FEEDBACK_GITHUB_TOKEN` secret and the positive finite `FEEDBACK_GITHUB_TIMEOUT_SECONDS`, so a full sender load validates the destination and the credential together. `FeedbackSettings`, `FeedbackIntakeSettings` and `FeedbackSenderCredentialsSettings` are registered in `CONFIGURATION_SETTINGS_FAMILIES`, so the configuration editor validates a feedback connection, destination, attachment-root, token or timeout save through the family that owns the edited alias. Destination saves and intake loads need no token, while a credential save validates the required secret, and a timeout save in the same family validates it too.

`load_feedback_definition(root)` in `src/course_explorer/feedback/definition.py` reads `config/feedback-form.json` and validates the ordered fields, the bilingual labels, the field and option identifiers, the upload limits and the issue mapping into closed models. The definition loads fresh when a feedback service is composed, and no second copy is stored.

`COURSE_EXPLORER_WEB_GENERATION` is a handoff inside the process, not a settings alias. The feature web entry point creates it before it starts its worker processes, and `src/course_explorer_web/dataset.py` combines it with the selected dataset identity into the opaque identity the browser reads. It is not part of `config/web.toml`, the environment file, the launcher's alias allowlist or the configuration editor.

## Composition order

`src/course_explorer/configuration.py` is the sole file-source owner. It holds the ordered `PUBLIC_CONFIG_FILES` tuple and `_read_merged_public_configuration_cached`, which reads every registered file and merges them through `_merge_configuration_documents`, the one merge that rejects an alias defined in more than one file. The two serving files end the tuple, web before admission, so the loopback bind and the admission policy compose after the shared files. The merged read and `_read_local_configuration_cached` are both cached by checkout root for the process lifetime, and `clear_configuration_caches` drops both.

`_project_configuration` selects the requested aliases from merged values. `read_configuration_documents` returns each registered file as its own parsed document, and it parses supplied replacement text in place of one file's read, so a candidate file is validated against the same document set without writing it. `parse_local_configuration` parses environment-file text into its assignments without interpolation, and it refuses a malformed binding and a key assigned more than once under the runtime's case-insensitive names while keeping each mapping key's spelling.

`uv run python -m course_explorer.configuration shell` prints one `export` line per non-secret alias from the subsystem files, using a process override from `os.environ` when one is present. The exports include the worker and site identities, because those are non-secret subsystem values. It does not read the environment file or export its credential aliases, which include the curriculum database password, the feedback application store password and the feedback sender token.

## Validation rules

Cross-field checks that a reader is most likely to meet:

| Class | Check |
|---|---|
| `KoriSettings` | The first academic year must not exceed the current academic year |
| `EmbeddingRuntimeSettings` | `EMBEDDING_CHUNK_OVERLAP_CHARACTERS` must be smaller than `EMBEDDING_CHUNK_MAX_CHARACTERS` |
| `TranslationSettings` | `TRANSLATION_MAX_TOKENS` must be smaller than `TRANSLATION_CONTEXT_SIZE` |
| `InferenceSettings` | Exactly two ordered local fit keys, unique alias and port, increasing context, MTP count on the first key only |
| `InferenceSettings` | `INFERENCE_MAX_TOKENS` plus `INFERENCE_FIT_HEADROOM_TOKENS` must be smaller than every local fit key context |
| `InferenceSettings` | The retry base and the retry poll interval must not exceed `INFERENCE_RETRY_MAX_BACKOFF_SECONDS` |
| `InferenceSettings` | `INFERENCE_PRIMARY_ARTIFACT_PATH` basename must equal `INFERENCE_PRIMARY_ARTIFACT_FILE` |
| `InferenceRerankSettings` | `INFERENCE_RERANK_BATCH_SIZE` must not exceed `INFERENCE_RERANK_CONTEXT_SIZE`, and the artifact path basename must equal `INFERENCE_RERANK_ARTIFACT_FILE` |
| `AdministrativeDatasetSettings` | The dataset and worker database prefixes must be distinct |
| `WebAppSettings` | `WEB_APP_URL` must be one root HTTP or HTTPS address whose origin, without the optional root slash, matches its parsed scheme and netloc, with HTTPS unless the hostname is a loopback host |
| `AdminWebSettings` | `ADMIN_WEB_ORIGIN` must be one exact HTTPS origin without credentials, path, query or fragment, and its spelling must equal its parsed scheme and netloc. `ADMIN_WEB_REPOSITORY_URL` must be one HTTPS GitHub owner and repository address. The inherited `WEB_APP_URL` follows the `WebAppSettings` rule |
| `SearchSettings` | `SEARCH_TIER_PRIORITY` must contain all four search methods once, and each comparison threshold must be below its upper neighbour |
| `WebSettings` | The report region `WEB_NEXT_COURSE_REPORT_CACHE_BYTES`, the query-embedding region `WEB_QUERY_EMBEDDING_CACHE_BYTES` and the four request-input bounds must be positive |
| `AdmissionSettings` | `ADMISSION_ENABLED` requires `WEB_WORKERS` of at least 2, `ADMISSION_SCORE_HEADROOM` must be at most `ADMISSION_SCORE_RELEASE`, which must be below `ADMISSION_SCORE_SATURATION`, and each cost curve's knee basis must be above its origin basis |

Field-level checks bound ports to 1 to 65535, require loopback hosts, require absolute worker paths and repository-relative state roots, and require lowercase 40-character revisions and 64-character SHA-256 identities.

## The configuration editor

`src/course_explorer_admin/configuration.py` owns the operator's one-key editor, and its three reports carry the file listing, one file's values and one saved key. A save builds the settings families whose validation aliases contain the edited key, comparing the key and the aliases without case, inside one candidate configuration block. The block's sources read the held snapshot, so a family load opens no configuration file.

The families in `CONFIGURATION_SETTINGS_FAMILIES` of `src/course_explorer/config.py` are the base inventory, and a caller adds the families of a package the base product does not import as its own tuple. `AdministrativeSiteSettings` is a member of that inventory, and its three keys live in the registered `config/admin_web.toml`, so an edit of any of them validates through the family that owns it.

`FeedbackSettings` owns the feedback connection and attachment-root keys of the registered `config/feedback.toml`, and `FeedbackIntakeSettings` owns its destination and intake keys and inherits the `WEB_APP_URL` key of `config/web.toml`, so those keys are editable in the same way. The feedback definition is not a TOML file, so the editor neither lists nor writes it.

`AdministrativeSiteSettings` declares the two service unit names and `ADMIN_SITE_WEB_SERVICE_SCOPE`, whose only values are `user` and `system` and whose default is `user`. `WebSettings` inherits the app address from `WebAppSettings` and owns the two web feature-switch keys and `UsageSettings` owns the web file's usage-retention key, so the editor reads and saves them like any other key of `config/web.toml`. An edit of `WEB_APP_URL` validates through `WebSettings`, `AdminWebSettings` and `FeedbackIntakeSettings`, the three families that inherit it.

`AdmissionSettings` owns the admission keys of `config/admission.toml`, and an edit of the shared `WEB_WORKERS` key validates both `WebSettings` and `AdmissionSettings`. `AdminWebSettings` owns the 10 administration keys of the registered `config/admin_web.toml`, and `AdministrativeSiteSettings` owns the three site keys, so those 13 keys are editable in the same way.

A subsystem-file save reads the environment file freshly through `configuration.read_candidate_local_configuration`, which decodes the file without newline translation and parses it through `parse_local_configuration` on every call. A malformed binding and a key assigned more than once in that file, ignoring case, both refuse the save, so the candidate never uses the values a runtime cache holds. An environment-file save locates the stored binding without case and preserves the spelling, whitespace, comments and line endings the file holds. The runtime reader `configuration.read_local_configuration` holds its cached `dotenv_values` mapping for the process lifetime.

An environment-file save also accepts a credential key that a settings family owns while the file does not carry it. The writer appends one quoted assignment in the first line-ending style the file holds, leaves every other byte as it is, and validates the whole candidate through the owning family. A key that a family owns without being a credential, and a key that no family owns, are refused when the file does not carry them. A value that is not a JSON string is refused before either environment-file branch renders it.

A subsystem-file candidate omits every local name whose lowercase spelling matches the edited alias, so an environment-file value of any case cannot mask that candidate, and an environment-file edit validates its freshly rendered assignments instead. Other local values hold their precedence, so a key that needs a credential validates. A key of a registered file that no listed family declares fails instead of claiming a validation, and a key of the environment file that no family declares carries its string and file grammar alone when the file already carries it.

`configuration.configuration_candidate` holds the merged public values and local values in a `ContextVar`. The merge inside it rejects a candidate that repeats an alias. The snapshot holds the merged public values and the local values, and the block resets its token in the `finally` branch.

## The Compose environment file

`src/course_explorer_admin/compose.py` owns the one generated environment file for Docker Compose. `compose_environment()` projects `load_raw_database_settings()` and `load_embedding_runtime_settings()` onto the interpolation aliases in `docker-compose.yml`. `_write_bridge` writes `compose.env` with `os.open(..., 0o600)` inside a `tempfile.mkdtemp` directory changed to mode 0700, and `main` passes it as `--env-file` to `sudo docker compose`. `_quote_bridge_value` renders each value in single quotes, rejects a value carrying a line break, and escapes an inner quote. A caller-supplied `COMPOSE_PROJECT_NAME` is forwarded as `--project-name` rather than written into the file. The `finally` block removes the directory after the subprocess returns.

## Adding a setting

1. Add a field with a `validation_alias` to the settings class that owns the family, or to another class in `src/course_explorer/config.py` with a `load_*` function beside it.
2. Add the key and its value to the matching file under `examples/config/`.
3. Add the class to `CONFIGURATION_SETTINGS_FAMILIES` in `src/course_explorer/config.py` when a registered subsystem file carries its keys, so the configuration editor can save them.
4. Add or extend a test under `tests/config/`.

When that class must be reachable from the administration side, extend the owning caller rather than adding a second source path, and put credentials in the environment file rather than the subsystem files or their templates.

## Tests

`tests/config/` holds the settings tests. `test_configuration_sources.py` covers automatic composition, override precedence, the example usage retention and its process override, the administration family's example values and its process override, the candidate sources and the handoff marker, duplicate-alias rejection, the Compose environment file and its cleanup, and the `configuration shell` export. `test_settings.py` covers loopback rejection across the local families, the administration family included. `test_inference_settings.py` covers the two-key inference identity and the rerank identity. `tests/config/_support.py` projects the committed example tree into the fixture maps, and `write_example_config_tree` in `tests/support/__init__.py` materializes it under a temporary root. `tests/admin/test_configuration.py` covers the editor's reads, one-key saves and refused candidates.
