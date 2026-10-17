# Settings loading

The configuration layer loads each settings family from the subsystem files, the device-local environment file, and process overrides, and validates the values before use.

## Settings classes

Every class in the table below lives in `src/course_explorer/config.py` and subclasses `ConfiguredSettings`. The same file also defines `InferenceLocalVariantSettings`, which subclasses `BaseModel` instead and types the `INFERENCE_LOCAL_VARIANTS` field. The TOML file column names the runtime file that carries the class's keys. Its tracked template lives under `examples/config/`.

| Class | TOML file | Purpose |
|---|---|---|
| `WebSettings` | `config/web.toml` | Loopback bind, process count, and browser-drawing limit |
| `DatabaseSettings` | `config/database.toml` | PostgreSQL connection components, the selected-dataset switch, and the administrative state root |
| `AdministrativeDatasetSettings` | `config/database.toml` with the derived prefixes in `config/worker.toml` | Selected-dataset state root, the two derived database-name prefixes, and the database operation timeout |
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
```

`LocalConfigurationSource` subclasses `EnvSettingsSource` and replaces only the value mapping, reading `configuration.read_local_configuration`. `read_public_configuration` selects exactly the aliases a class declares, so a runtime/generation reader never opens either hub artifact. Only when a selected projection contains `EMBEDDING_HUB_VECTOR` or `EMBEDDING_OUTCOMES_HUB_VECTOR` does `configuration._resolve_hub_reference` read the referenced JSON array, rejecting an absolute path, a non-list payload, and unreadable or invalid JSON.

Setting `COURSE_EXPLORER_SETTINGS_SOURCE=environment` makes `settings_customise_sources` return only the constructor and process sources, so an isolated child reads no file. `src/course_explorer_web/launch.py` uses that marker. It composes the five families the web server needs, serializes each field through `configuration.environment_value`, keeps only `HOME`, `PATH`, and `LANG` from the inherited environment, and execs `python -m course_explorer_web`.

## Composition order

`src/course_explorer/configuration.py` is the sole file-source owner. It holds the ordered `PUBLIC_CONFIG_FILES` tuple and `_read_merged_public_configuration_cached`, which reads every file and rejects an alias defined in more than one file. The merged read and `_read_local_configuration_cached` are both cached by checkout root for the process lifetime, and `clear_configuration_caches` drops both.

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
| `SearchSettings` | `SEARCH_TIER_PRIORITY` must contain all four search methods once, and each comparison threshold must stay below its upper neighbour |

Field-level checks bound ports to 1 to 65535, require loopback hosts, require absolute worker paths and repository-relative state roots, and require lowercase 40-character revisions and 64-character SHA-256 identities.

## The Compose environment file

`src/course_explorer_admin/compose.py` owns the one generated environment file for Docker Compose. `compose_environment()` projects `load_raw_database_settings()` and `load_embedding_runtime_settings()` onto the interpolation aliases in `docker-compose.yml`. `_write_bridge` writes `compose.env` with `os.open(..., 0o600)` inside a `tempfile.mkdtemp` directory changed to mode 0700, and `main` passes it as `--env-file` to `sudo docker compose`. `_quote_bridge_value` renders each value in single quotes, rejects a value carrying a line break, and escapes an inner quote. A caller-supplied `COMPOSE_PROJECT_NAME` is forwarded as `--project-name` rather than written into the file. The `finally` block removes the directory after the subprocess returns.

## Adding a setting

1. Add a field with a `validation_alias` to the settings class that owns the family, or to a new class in `src/course_explorer/config.py` and a `load_*` function beside it.
2. Add the key and its value to the matching file under `examples/config/`.
3. Add or extend a test under `tests/config/`.

When the new class must be reachable from the administration side, extend the owning caller rather than adding a second source path, and put machine-local values in the environment file rather than the subsystem files or their templates.

## Tests

`tests/config/` holds the settings tests. `test_configuration_sources.py` covers automatic composition, override precedence, the hub-free runtime load, duplicate-alias rejection, the Compose environment file and its cleanup, and the `configuration shell` export. `test_settings.py` covers loopback rejection across the local families. `test_inference_settings.py` covers the two-key inference identity and the rerank identity. `tests/config/_support.py` projects the committed example tree into the fixture maps, and `tests/support/write_example_config_tree` materializes it under a temporary root.
