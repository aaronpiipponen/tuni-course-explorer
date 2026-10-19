# Settings loading

The configuration layer loads each settings family from the subsystem files, the device-local environment file, and process overrides, and validates the values before use.

## Settings classes

Every class in the table below lives in `src/course_explorer/config.py` and subclasses `ConfiguredSettings`. The same file also defines `InferenceLocalVariantSettings`, which subclasses `BaseModel` instead and types the `INFERENCE_LOCAL_VARIANTS` field. The TOML file column names the runtime file that carries the class's keys. Its tracked template lives under `examples/config/`.

| Class | TOML file | Purpose |
|---|---|---|
| `WebSettings` | `config/web.toml` | Loopback bind, process count, browser-drawing limit, and the two served feature switches |
| `UsageSettings` | `config/web.toml` | The retention window of the per-request usage records |
| `AdminWebSettings` | `config/admin_web.toml` | Administration loopback bind, exact HTTPS origin, session lifetimes, the anonymous session creation limit, the command-log entry limit, the console poll interval, the App link address and the GitHub repository address |
| `DatabaseSettings` | `config/database.toml` | PostgreSQL connection components, the selected-dataset switch, and the administrative state root |
| `AdministrativeDatasetSettings` | `config/database.toml` with the derived prefixes in `config/worker.toml` | Selected-dataset state root, the two derived database-name prefixes, and the database operation timeout |
| `AdministrativeSiteSettings` | The device-local environment file alone | The two systemd user units that run this site's web and administration processes |
| `CaptureSettings` | `config/curriculum.toml` | Raw capture location and checkpoint response count |
| `KoriSettings` | `config/curriculum.toml` | Anonymous public Kori source, batching, retry, and academic-year bounds |
| `NormalizationSettings` | `config/curriculum.toml` | Current academic year, activity window, and course-guide base |
| `LocalLifecycleSettings` | `config/curriculum.toml` and `config/search.toml` for state roots, `config/worker.toml` for timing | Local stage state roots and bounded startup, polling, and stop policy |
| `EmbeddingRuntimeSettings` | `config/search.toml` | Loopback embedding runtime, generation chunking, and pinned artifact identity |
| `EmbeddingSettings` | `config/search.toml` | The runtime contract plus both required hub vectors |
| `SearchSettings` | `config/search.toml` | Search tier order, the request policy of one search query embedding, comparison thresholds, recommendation policy, and the route compact-node limit |
| `TranslationSettings` | `config/translation.toml` | Loopback translation runtime, model identity, and generation limits |
| `TranslationControllerSettings` | `config/translation.toml` for its own root and attempts, `config/worker.toml` for the connection base | Translation controller state root and health attempts |
| `InferenceSettings` | `config/inference.toml` | Loopback generation runtime, the two local fit keys, and closed policy literals |
| `InferenceContextSettings` | `config/inference.toml` | Multiview evaluation fields and the fusion rank offset |
| `InferenceSelectionSettings` | `config/inference.toml` | Embedding pool depth and final candidate ceiling |
| `InferenceRerankSettings` | `config/inference.toml` | Loopback cross-encoder runtime and its serving contract |
| `InferenceRerankInputSettings` | `config/inference.toml` | Cross-encoder query and document bounds and text layout |
| `InferenceControllerSettings` | `config/inference.toml` for its own root and attempts, `config/worker.toml` for the connection base | Inference controller state root and health attempts |
| `WorkerConnectionSettings` | `config/worker.toml` for the connect timeout, `config/translation.toml` for the health interval and stop timeout, the local `.env` for the worker identity | Worker connection shared by both remote stages |
| `WorkerSetupSettings` | `config/worker.toml` | Expected worker repository origin and the setup timeout |
| `WorkerRuntimeSettings` | `config/worker.toml` | Portable generation CPU thread geometry |
| `WorkerGpuRebootSettings` | `config/worker.toml` | The shared checkpoint-reboot interval |

A code-owned default exists only where a field declares one. `EmbeddingRuntimeSettings` and `EmbeddingSettings` are two projections of one source, so the Compose environment file can be generated and a generation run can load the runtime contract before a dataset's hub artifacts exist. A similarity read through `EmbeddingSettings` fails when a hub artifact is missing.

The search command projects the query embedding request policy onto the embedding settings it loaded. `SEARCH_EMBEDDING_REQUEST_TIMEOUT_SECONDS` and `SEARCH_EMBEDDING_MAX_ATTEMPTS` of `SearchSettings` replace the loaded timeout and attempt count through `model_copy`, and that projection is the only settings the one `EmbeddingProvider` of the request receives. Every other similarity consumer reads the loaded embedding settings, which own the vector identity and both hubs. `SearchSettings` validates both values before the copy, and the copy itself runs no further validation.

## The shared base and its file sources

`ConfiguredSettings` subclasses `pydantic_settings.BaseSettings` with `extra="ignore"`, an empty `env_prefix`, and `hide_input_in_errors=True`. Its `settings_customise_sources` returns the composed source tuple, in descending precedence:

1. `init_settings`, the constructor inputs.
2. `env_settings`, the process environment.
3. `LocalConfigurationSource`, the device-local `.env`.
4. The projected subsystem-file values, a callable that reads them through `configuration.read_public_configuration`.
5. Each field's own code default.

Each configurable field declares a `validation_alias`, and the alias is the configuration key. A field fixed in the code declares none, such as `embedding_dimension` on `EmbeddingRuntimeSettings`. The excerpt below shows the fields of `WebSettings` from `src/course_explorer/config.py`, which continues with its host and port validators.

```python
class WebSettings(ConfiguredSettings):
    model_config = SettingsConfigDict(extra="ignore", env_prefix="")

    web_host: str = Field(validation_alias="WEB_HOST")
    web_port: int = Field(validation_alias="WEB_PORT")
    web_workers: int = Field(validation_alias="WEB_WORKERS", gt=0)
    prerequisite_graph_max_elements: int = Field(
        validation_alias="PREREQUISITE_GRAPH_MAX_ELEMENTS", gt=0
    )
    embeddings_enabled: bool = Field(validation_alias="WEB_EMBEDDINGS_ENABLED")
    inference_enabled: bool = Field(validation_alias="WEB_INFERENCE_ENABLED")
```

`WEB_EMBEDDINGS_ENABLED` and `WEB_INFERENCE_ENABLED` are required booleans with no code default, so a site states both values in its own `config/web.toml`. The example file sets both to `true`.

`AdminWebSettings` declares `ADMIN_WEB_HOST`, `ADMIN_WEB_PORT`, `ADMIN_WEB_ORIGIN`, `ADMIN_WEB_SESSION_IDLE_MINUTES`, `ADMIN_WEB_SESSION_MAX_HOURS`, `ADMIN_WEB_ANONYMOUS_SESSION_LIMIT`, `ADMIN_WEB_ANONYMOUS_SESSION_WINDOW_SECONDS`, `ADMIN_WEB_COMMAND_LOG_LIMIT`, `ADMIN_WEB_POLL_SECONDS`, `ADMIN_WEB_APP_URL` and `ADMIN_WEB_REPOSITORY_URL`, and it lives in the same file. The host validator reuses the loopback predicate, the port validator reuses the TCP-port predicate, the two session lifetimes, the anonymous-session count and window, the log limit and the poll interval must be positive, and `ADMIN_WEB_ORIGIN` must be one exact `https://` origin whose spelling equals `https://` plus its parsed netloc.

`ADMIN_WEB_APP_URL` is one absolute HTTP or HTTPS address with no credentials, a path other than the root, wildcard, whitespace, query or fragment marker, and `ADMIN_WEB_REPOSITORY_URL` is one HTTPS GitHub owner and repository address. The administration backend loads this family in its own process through the ordinary automatic composition, so no administration key travels the web launcher's allowlist.

`LocalConfigurationSource` subclasses `EnvSettingsSource` and replaces only the value mapping, reading `configuration.read_local_configuration`. `read_public_configuration` selects exactly the aliases a class declares, so a runtime/generation reader never opens either hub artifact. Only when a selected projection contains `EMBEDDING_HUB_VECTOR` or `EMBEDDING_OUTCOMES_HUB_VECTOR` does `configuration._resolve_hub_reference` read the referenced JSON array, rejecting an absolute path, a non-list payload, and unreadable or invalid JSON.

Inside a candidate configuration block the hook checks `configuration.candidate_settings_sources` before the marker. The returned sources are the constructor inputs, a `LocalConfigurationSource` that reads the held candidate local mapping in place of the file, and a callable that projects the held candidate public values onto the class's aliases. No process environment is a source there, so a process override and the handoff marker cannot supply a value the candidate omits.

Setting `COURSE_EXPLORER_SETTINGS_SOURCE=environment` makes `settings_customise_sources` return only the constructor and process sources, so an isolated child reads no file. `src/course_explorer_web/launch.py` uses that marker. It loads the site's web settings, composes the four required families the web server needs, adds `EmbeddingSettings()` only when `WEB_EMBEDDINGS_ENABLED` is true, serializes each field through `configuration.environment_value`, keeps only `HOME`, `PATH`, and `LANG` from the inherited environment, and execs `python -m course_explorer_web`. A site with embedding features off therefore composes no embedding family and needs no hub artifact. The launcher hands over no `UsageSettings` value, because the retention key belongs to the usage report alone.

## Composition order

`src/course_explorer/configuration.py` is the sole file-source owner. It holds the ordered `PUBLIC_CONFIG_FILES` tuple and `_read_merged_public_configuration_cached`, which reads every registered file and merges them through `_merge_configuration_documents`, the one merge that rejects an alias defined in more than one file. The merged read and `_read_local_configuration_cached` are both cached by checkout root for the process lifetime, and `clear_configuration_caches` drops both.

`_project_configuration` selects the requested aliases from merged values and resolves only the hub references the selection holds. `read_configuration_documents` returns each registered file as its own parsed document, and it parses supplied replacement text in place of one file's read, so a candidate file is validated against the same document set without writing it. `parse_local_configuration` parses environment-file text into its assignments without interpolation, and it refuses a malformed binding and a key assigned more than once under the runtime's case-insensitive names while keeping each mapping key's spelling.

`uv run python -m course_explorer.configuration shell` prints one `export` line per portable alias from the subsystem files, using a process override from `os.environ` when one is present. It does not read the environment file or export its machine-local aliases, which include the database password and the three worker connection values.

## Validation rules

Cross-field checks that a reader is most likely to meet:

| Class | Check |
|---|---|
| `KoriSettings` | The first academic year must not exceed the current academic year |
| `EmbeddingRuntimeSettings` | `EMBEDDING_CHUNK_OVERLAP_CHARACTERS` must be smaller than `EMBEDDING_CHUNK_MAX_CHARACTERS` |
| `EmbeddingSettings` | Each hub vector must have exactly 1024 finite components |
| `TranslationSettings` | `TRANSLATION_MAX_TOKENS` must be smaller than `TRANSLATION_CONTEXT_SIZE` |
| `InferenceSettings` | Exactly two ordered local fit keys, unique alias and port, increasing context, MTP count on the first key only |
| `InferenceSettings` | `INFERENCE_MAX_TOKENS` plus `INFERENCE_FIT_HEADROOM_TOKENS` must be smaller than every local fit key context |
| `InferenceSettings` | The retry base and the retry poll interval must not exceed `INFERENCE_RETRY_MAX_BACKOFF_SECONDS` |
| `InferenceSettings` | `INFERENCE_PRIMARY_ARTIFACT_PATH` basename must equal `INFERENCE_PRIMARY_ARTIFACT_FILE` |
| `InferenceRerankSettings` | `INFERENCE_RERANK_BATCH_SIZE` must not exceed `INFERENCE_RERANK_CONTEXT_SIZE`, and the artifact path basename must equal `INFERENCE_RERANK_ARTIFACT_FILE` |
| `AdministrativeDatasetSettings` | The dataset and worker database prefixes must be distinct |
| `AdminWebSettings` | `ADMIN_WEB_ORIGIN` must be one exact HTTPS origin without credentials, path, query or fragment, and its spelling must equal its parsed scheme and netloc. `ADMIN_WEB_REPOSITORY_URL` must be one HTTPS GitHub owner and repository address |
| `SearchSettings` | `SEARCH_TIER_PRIORITY` must contain all four search methods once, and each comparison threshold must stay below its upper neighbour |

Field-level checks bound ports to 1 to 65535, require loopback hosts, require absolute worker paths and repository-relative state roots, and require lowercase 40-character revisions and 64-character SHA-256 identities.

## The configuration editor

`src/course_explorer_admin/configuration.py` owns the operator's one-key editor, and its three reports carry the file listing, one file's values and one saved key. A save builds the settings families whose validation aliases contain the edited key, comparing the key and the aliases without case, inside one candidate configuration block. The block's sources read the held snapshot, so a family load opens no configuration file, while a selected hub alias resolves its referenced artifact through the owner.

The families in `CONFIGURATION_SETTINGS_FAMILIES` of `src/course_explorer/config.py` are the base inventory, and a caller adds the families of a package the base product does not import as its own tuple. `AdministrativeSiteSettings` is a member of that inventory although the environment file alone carries its keys, so an edit of either key validates through the family that owns it. `WebSettings` owns the two web feature-switch keys and `UsageSettings` owns the web file's usage-retention key, so the editor reads and saves all three like any other key of `config/web.toml`. `AdminWebSettings` owns every key of the registered `config/admin_web.toml`, so those 11 keys are editable in the same way.

A subsystem-file save reads the environment file freshly through `configuration.read_candidate_local_configuration`, which decodes the file without newline translation and parses it through `parse_local_configuration` on every call. A malformed binding and a key assigned more than once in that file, ignoring case, both refuse the save, so the candidate never uses the values a runtime cache holds. An environment-file save locates the stored binding without case and keeps the spelling, whitespace, comments and line endings the file holds. The runtime reader `configuration.read_local_configuration` holds its cached `dotenv_values` mapping for the process lifetime.

A subsystem-file candidate omits every local name whose lowercase spelling matches the edited alias, so an environment-file value of any case cannot mask that candidate, and an environment-file edit validates its freshly rendered assignments instead. Other local values hold their precedence, so a key that needs a machine-local value validates. A key of a registered file that no listed family declares fails instead of claiming a validation, and a key of the environment file that no family declares carries its string and file grammar alone.

`configuration.configuration_candidate` holds the candidate root, merged public values and local values in a `ContextVar`, and it resets its token in the `finally` branch. The merge inside it rejects a candidate that repeats an alias. A hub-key edit resolves its reference through the projection and validates through `EmbeddingSettings`, and it writes the reference value alone.

## The Compose environment file

`src/course_explorer_admin/compose.py` owns the one generated environment file for Docker Compose. `compose_environment()` projects `load_raw_database_settings()` and `load_embedding_runtime_settings()` onto the interpolation aliases in `docker-compose.yml`. `_write_bridge` writes `compose.env` with `os.open(..., 0o600)` inside a `tempfile.mkdtemp` directory changed to mode 0700, and `main` passes it as `--env-file` to `sudo docker compose`. `_quote_bridge_value` renders each value in single quotes, rejects a value carrying a line break, and escapes an inner quote. A caller-supplied `COMPOSE_PROJECT_NAME` is forwarded as `--project-name` rather than written into the file. The `finally` block removes the directory after the subprocess returns.

## Adding a setting

1. Add a field with a `validation_alias` to the settings class that owns the family, or to a new class in `src/course_explorer/config.py` and a `load_*` function beside it.
2. Add the key and its value to the matching file under `examples/config/`.
3. Add the class to `CONFIGURATION_SETTINGS_FAMILIES` in `src/course_explorer/config.py` when a registered subsystem file carries its keys, so the configuration editor can save them.
4. Add or extend a test under `tests/config/`.

When the new class must be reachable from the administration side, extend the owning caller rather than adding a second source path, and put machine-local values in the environment file rather than the subsystem files or their templates.

## Tests

`tests/config/` holds the settings tests. `test_configuration_sources.py` covers automatic composition, override precedence, the example usage retention and its process override, the administration family's example values and its process override, the candidate sources and the handoff marker, the hub-free runtime load, duplicate-alias rejection, the Compose environment file and its cleanup, and the `configuration shell` export. `test_settings.py` covers loopback rejection across the local families, the administration family included. `test_inference_settings.py` covers the two-key inference identity and the rerank identity. `tests/config/_support.py` projects the committed example tree into the fixture maps, and `tests/support/write_example_config_tree` materializes it under a temporary root. `tests/admin/test_configuration.py` covers the editor's reads, one-key saves and refused candidates.
