# Embedding generation

The embedding stage reads the effective text catalogue, chunks it, embeds the pending chunks through the loopback service, and stores one vector per chunk.

## Provider contract

`src/course_explorer/embeddings/provider.py` owns `EmbeddingProvider`, the single synchronous HTTP client for the loopback embedding service. The constructor takes `EmbeddingRuntimeSettings` and optional `transport`, `sleep`, `before_request`, and `request_scope` hooks, and opens one `httpx.Client` with `base_url` set from `EmbeddingRuntimeSettings.base_url`, the configured request timeout, and redirects off.

`EmbeddingProvider.embed(texts)` rejects an empty batch and a blank text with `ValueError` and rejects a closed client with `EmbeddingRequestError`. It posts one payload to the service's `v1/embeddings` path:

```json
{"input": ["Text to embed"], "model": "BAAI/bge-m3", "encoding_format": "float"}
```

The call runs through `request_json_with_retries` in `src/course_explorer/http_retry.py` with `retry_contract_errors=False`. The shared retry policy retries an `httpx.TransportError` and a 429 or 5xx status only, treats `EMBEDDING_MAX_ATTEMPTS` as the total attempt count with the first call included, and sleeps `EMBEDDING_RETRY_BACKOFF_SECONDS * 2 ** failed_index` before the retry that follows zero-based attempt `failed_index`. Every other status is terminal. Both the status verdict and the transport verdict raise `EmbeddingRequestError` carrying the fixed `POST /v1/embeddings` prefix and no body or header text.

The body is decoded by `decode_json_response` with `contract_error=EmbeddingContractError`, so a body that is not JSON raises a contract error that holds no response text. The decoded value is validated against `_EmbeddingResponse` and `_EmbeddingData`, two strict Pydantic models that ignore extra fields and forbid coercion. `embed` then requires the model to equal `EMBEDDING_MODEL` when the response names one, one uniquely indexed result per input, exactly `settings.embedding_dimension` components per vector, and a finite value in every component. Each violation raises `EmbeddingContractError`. The returned vectors are ordered by response index, so they line up with the input batch.

`before_request` is a pure admission callback. A refusal before the first request raises `RequestNotStarted` before any I/O, and a refusal during a backoff raises the terminal request error instead of sleeping again. `request_scope` wraps every attempt. `close()` is idempotent, and the class is a context manager.

## Chunk inputs and the work key

`src/course_explorer/embeddings/generation.py` owns the product-neutral contracts.

`chunk_teaching_text(text, *, max_characters, overlap_characters)` returns one tuple of chunks. A text at or below `max_characters` becomes the single chunk itself. A longer text yields windows `text[start : start + max_characters]` with `step = max_characters - overlap_characters`, stopping once a window reaches the end. A window whose `strip()` is empty is dropped. The returned chunks are exact substrings of the input. The function rejects a blank text, a window below one, and an overlap that is negative or not smaller than the window.

`build_course_embedding_chunks(catalogue, settings, *, group_ids=None)` walks `EffectiveTeachingTextCatalogue.courses` in catalogue order and each course's `texts` cells in cell order, producing `CourseEmbeddingChunkInput` rows in catalogue, cell, and chunk-index order. An explicit `group_ids` scope must be a subset of `catalogue.canonical_group_ids`, and an unknown identifier raises `ValueError`. Each row carries the group id, the representative's `sisu_course_unit_id` and `representative_source_hash`, the field, the language, the chunk index, the text origin, the chunk text, `cell.text_hash` as `effective_text_hash`, `cell.source_text_hash`, `teaching_text_sha256(piece)` as `chunk_text_hash`, the translation provenance of the cell, and `embedding_model`, `embedding_artifact_sha256`, and `embedding_configuration_hash` from the settings.

`src/course_explorer/teaching_text/service.py` supplies the cells. `TeachingTextService.build_catalogue` resolves one cell per field and language over the projected teaching catalogue in `CurriculumRepository.list_teaching_courses`, and `_resolve_cell` returns the official text when `official_teaching_text` finds a non-blank value, otherwise a derived row whose recorded source hash equals the hash of the official source text. A stale row is reported and left out.

## The configuration hash

`embedding_configuration_sha256(settings)` hashes six values through `json_sha256(payload, ensure_ascii=True)`: `embedding_model`, `embedding_artifact_sha256`, `embedding_dimension`, `embedding_pooling`, `embedding_normalization`, and `embedding_runtime_revision`. The request timeout, the attempt count, the backoff, the generation batch size, the chunk window, and the chunk overlap are outside the digest. A change to the window or the overlap reaches an affected chunk through its chunk text hash, and the batch size and the timeout change how the work is sent rather than what a vector means. `EmbeddingRuntimeSettings.embedding_dimension` is `Literal[COURSE_EMBEDDING_DIMENSION]`, fixed in `src/course_explorer/constants.py`.

Every chunk row stores the digest, and every read compares it with the digest of the running settings, so a change to one hashed value makes the stored rows incompatible and the next run re-embeds the catalogue. `EmbeddingStage.identity_sha256` folds the same digest into the stage identity, so a pin change also gives the stage a distinct identity.

## The chunk store and reconciliation

`src/course_explorer/embeddings/repository.py` owns `CourseEmbeddingRepository`, the writer and reader for the `course_embedding_chunks` table declared by `CourseEmbeddingChunk` in `src/course_explorer/db/models.py`.

| Method | Behavior |
|---|---|
| `reconcile(canonical_group_ids, chunks)` | One transaction over the scoped canonical courses. It maps each group to its versions, loads the stored rows of those versions, keys the desired chunks by `(course_version_id, field, language, chunk_index)`, deletes rows outside the desired set, and inserts, reuses, retries, or resets each desired chunk through `_reconcile_desired_rows`. It returns `EmbeddingReconciliation` with the counts and the pending rows ordered by group, representative source, field, language, and chunk index. |
| `begin_attempt(row_ids)` | Resets the exact rows to pending with a null vector before their provider call. |
| `complete(results)` | Stores each `CourseEmbeddingResult` vector on its row and marks the row completed. |
| `fail(row_ids)` | Marks the rows failed and clears any vector. |
| `coverage(canonical_group_ids=None)` | One `GROUP BY` over field, language, origin, and status, returning `CourseEmbeddingCoverageReport`. `None` covers the whole catalogue, an explicit collection scopes the read, and an empty collection returns the all-zero report. |
| `read_chunk_keys(row_ids)` | Projects each row's `(group_id, field, language, chunk_index)` key without loading text or vectors. |
| `require_current_chunks(chunks)` | A projected readiness read that raises `ValueError` when a desired chunk is missing, not completed, without a vector, or not matching its key. It reads identity and provenance columns plus `embedding IS NOT NULL` in `_READINESS_BATCH_SIZE` batches of 1000 identities per statement. |

`_matches` requires the stored text and the identity fields to equal the desired chunk. `_matches_identity` compares the origin, the representative source hash, the effective, source, and chunk text hashes, the translation method, model, and timestamp, the embedding model, the artifact checksum, and the configuration hash. `_apply` writes every mutable work field on a reset row.

`require_current_chunks` gates the example artifact writer in `src/course_explorer/mock_data.py` and the inference job in `src/course_explorer/inference/job.py`. The lifecycle states come from `CourseEmbeddingStatus` in `src/course_explorer/enums.py`. The column set, the checks, and the HNSW index over `embedding` are listed in [Tables and migrations](/docs/backend/catalogue/tables-and-migrations.md).

## The generation service

`CourseEmbeddingService` takes a `TeachingTextService`, a `CourseEmbeddingRepository`, an `EmbeddingProvider`, and `EmbeddingRuntimeSettings`. `run(*, before_pending_batch=None, on_checkpoint=None)` performs one idempotent pass:

1. `teaching_text.build_catalogue()` resolves the catalogue, and its canonical group ids become the scope.
2. `build_course_embedding_chunks(catalogue, settings, group_ids=scope)` assembles the desired chunks.
3. `repository.reconcile(scope, chunks)` returns the reconciliation and the pending rows.
4. `on_checkpoint` receives one `CourseEmbeddingProgress` with the desired count, the reused count, the vectors stored so far, and the scoped coverage. The callback runs at reconciliation and after each committed or recorded batch, so every checkpoint describes committed rows only.
5. The pending rows are embedded in slices of `embedding_generation_batch_size`. For each slice, `before_pending_batch` is consulted, `repository.begin_attempt(row_ids)` resets the rows, `provider.embed(texts)` returns the vectors, and `repository.complete(results)` stores them. A `False` from `before_pending_batch` returns `None` and leaves the remaining slices untouched. A `RequestNotStarted` publishes the coverage and returns `None` with the attempted rows left pending. Any other exception marks the slice failed through `repository.fail(row_ids)`, publishes, and re-raises.
6. `run` returns a `CourseEmbeddingRunReport` with `canonical_course_count`, `representative_course_count`, `unembeddable_course_count` (representatives whose resolved cell tuple is empty), `desired_chunk_count`, the reconciliation counts, `embedded_count`, and the final scoped coverage.

`run_course_embedding_command` in `src/course_explorer/embeddings/commands.py` is the single composition path. It opens the database context from `load_database_settings`, builds `CourseEmbeddingRepository`, `TeachingTextService` over `CurriculumRepository` and `DerivedTranslationRepository`, loads `EmbeddingRuntimeSettings` through `load_embedding_runtime_settings`, and runs the service inside an `EmbeddingProvider` context manager. It forwards both lifecycle callbacks and the provider's admission and request-scope hooks.

## Scoped vector reads and hubs

`src/course_explorer/embeddings/read.py` owns the request-time projection of stored chunk vectors.

| Symbol | Behavior |
|---|---|
| `TeachingEmbeddingChunk` | The read carrier: group id, field, language, chunk index, origin, the stored character count, and the vector. |
| `TeachingEmbeddingRepository.get_chunks(represented, *, embedding_configuration_hash)` | Returns every completed, vector-backed row whose `(group_id, sisu_course_unit_id, representative_source_hash)` matches a requested record and whose configuration hash equals the supplied digest, ordered by group, field, language, and chunk index. An empty request returns before opening a session. |
| `TeachingEmbeddingRepository.find_nearest_chunks(basis_chunks, *, embedding_configuration_hash, top_k, active_only, excluded_group_ids)` | Builds an inline `values` list of `(query_index, language, embedding)` rows and ranks completed compatible content and outcomes chunks of the same language by `cosine_distance` in a lateral subquery limited to `top_k`, then returns `TeachingEmbeddingNeighbor` rows ordered by query index and descending score. |
| `centre_chunks(chunks, hub, *, outcomes_hub=None)` | Replaces each vector with `vector - hub`, using the outcomes hub for the outcomes field when one is supplied. |

`src/course_explorer/embeddings/hub.py` owns the arithmetic. `mean_unit_vectors(vectors)` normalizes each vector to unit length and returns the component-wise mean, raising `ValueError` on empty input, mismatched dimensions, a non-finite component, or a zero-norm vector. `subtract_hub(vector, hub)` returns `vector - hub` at equal dimensions, and `subtract_hub_for_field(vector, field, hub, outcomes_hub)` selects the outcomes hub for the outcomes field.

Consumers:

- `src/course_explorer/search/repository.py` (`SemanticSearchRepository.search`) computes the exact best-chunk cosine of the hub-centred query over completed compatible rows and groups by canonical course and representative.
- `src/course_explorer/search/service.py` (`CourseSearchService`) embeds one query through the same `EmbeddingProvider` and passes `embedding_configuration_sha256` of the running settings.
- `src/course_explorer/comparison/commands.py` and `src/course_explorer/recommendations/commands.py` read chunks through `get_chunks` and `find_nearest_chunks` and centre them with both hubs.

## Hub computation and writing

`src/course_explorer/embeddings/hub_files.py` owns the hub computation over current chunk vectors and the writing of the two hub files.

| Symbol | Behavior |
|---|---|
| `CurrentChunkVectors` | The carrier: the desired `CourseEmbeddingChunkInput` rows of the catalogue with one stored vector per row, aligned by position. |
| `EmbeddingHubs` | The result: `catalogue`, `outcomes`, `chunk_count`, and `outcomes_chunk_count`. |
| `EmbeddingHubReport` | The frozen report DTO that forbids extra fields: `catalogue_path`, `outcomes_path`, `chunk_count`, and `outcomes_chunk_count`. |
| `read_current_chunk_vectors(factory, embedding)` | Builds the catalogue through `TeachingTextService` over `CurriculumRepository` and `DerivedTranslationRepository`, builds the desired chunks with `build_course_embedding_chunks`, requires them through `CourseEmbeddingRepository.require_current_chunks`, reads the stored vectors through `TeachingEmbeddingRepository.get_chunks` with `embedding_configuration_sha256(embedding)`, keys them by `(group_id, field, language, chunk_index)`, and raises `ValueError` when a desired key has no compatible stored vector. |
| `compute_embedding_hubs(current)` | Selects the outcomes-field rows and returns `EmbeddingHubs` from `mean_unit_vectors` over every vector and over the outcomes vectors, raising `ValueError` for an empty input in either call. |
| `write_hub_file(path, hub)` | Creates the parent directory and writes one compact JSON number array with `ensure_ascii=True` and a trailing newline. |
| `write_hub_files(catalogue_path, outcomes_path, hubs)` | Publishes both hubs as one write: each hub goes through `write_hub_file` into a temporary file named after its destination, both temporary files replace their destinations, and a `finally` block removes every temporary file, so a failure leaves both destinations holding the content they had when the publish started. |

`run_administrative_hubs()` in `src/course_explorer_admin/commands.py` is the command path. It resolves `repository_root()` and both repository-relative paths through `hub_reference_path(root, alias)` in `src/course_explorer/configuration.py`, opens the selected database context from `_selected_dataset_settings()`, reads the current vectors through `load_embedding_runtime_settings()`, calls `compute_embedding_hubs`, and writes both files with `write_hub_files(root / catalogue_path, root / outcomes_path, hubs)`. Both means are computed before the first write, so a readiness or arithmetic `ValueError` leaves both files untouched. It returns `EmbeddingHubReport` with the two posix paths and the two chunk counts. `src/course_explorer_admin/cli.py` declares the `hubs` subparser, dispatches it to `run_administrative_hubs`, and passes `hubs` as the operation to the error guidance, and `scripts/admin.py` documents `uv run python scripts/admin.py hubs`.

`operator_guidance("hubs")` returns the fixed guidance for a failed command: complete the embedding stage on the selected dataset, keep the server database running, retry, and restart the web server.

`_tool_menu` in `src/course_explorer_admin/commands.py` builds the embedding tool options as `("6", "Write hubs")` inserted before the trailing `("0", "Back")` row. Choosing `6` on the embedding tool calls `run_administrative_hubs` with the `hubs` operation. The ingestion, translation, and inference tools use the base options and offer no hub entry.

`write_mock_artifacts` in `src/course_explorer/mock_data.py` computes the two hubs through the same `read_current_chunk_vectors` and `compute_embedding_hubs` and writes them with `write_hub_files`, so the example data preparation and the command share one implementation. `scripts/mock_data.py` exposes it as the `write-artifacts` action, whose `--hubs-dir` option defaults to `config/derived`.

## Commands, the local stage, and the service image

`EmbeddingStage` in `src/course_explorer_admin/local_stages.py` is the local adapter. It declares `name = "embedding"`, the Compose services `db` and `embedding`, `embedding` as a temporary service, and `retains_after_stop = True`. `identity_sha256` combines the stage name with `embedding_configuration_sha256(load_embedding_runtime_settings())` and the session options. `require_prepared` runs `_require_prepared_artifact`, which requires the configured artifact to be a regular file that is not a symlink and to match `EMBEDDING_ARTIFACT_SHA256`. `require_database` calls `require_selected_database_schema`. `run` converts each `CourseEmbeddingProgress` into an `EmbeddingProgress` checkpoint and passes `context.admit` as both the batch and the request admission callback and `mechanics.model_request_scope` as the request scope. `finalize` writes nothing, because the service commits each batch.

`run_embedding_command(action, ...)` runs one lifecycle action through `run_lifecycle_command` with the stage state root from `stage_state_root("embedding")`, and `run_administrative_command` in `src/course_explorer_admin/commands.py` dispatches the `embedding` stage to it. `run_administrative_coverage("embedding")` returns `CourseEmbeddingRepository(factory).coverage()`. The same module projects the runtime values for Compose through `compose_environment()` in `src/course_explorer_admin/compose.py`, which reads `load_embedding_runtime_settings()`.

```bash
uv run python scripts/admin.py embedding start
uv run python scripts/admin.py embedding status
uv run python scripts/admin.py coverage embedding
```

`docker/embedding/Dockerfile` builds from the digest-pinned `EMBEDDING_SERVER_IMAGE`, checks the base reference for an `@sha256:` digest during the build, labels the image with `EMBEDDING_RUNTIME_REVISION`, and installs `docker/embedding/entrypoint.sh` as the entrypoint. The entrypoint requires the artifact checksum, runtime revision, model, host, port, threads, context size, pooling, and normalization values, accepts `127.0.0.1` as the host, checks each value's shape, verifies `/models/embedding.gguf` against `EMBEDDING_ARTIFACT_SHA256` with `sha256sum --check --strict`, checks that `llama-server --version` reports the first nine characters of `EMBEDDING_RUNTIME_REVISION`, and execs the server with the model alias, host, port, threads, thread batch size, context size as the batch and micro-batch size, pooling, embedding normalization, one parallel slot, embedding mode, no device, offline mode, polling off, and no user interface. `examples/docker-compose.yml` builds that image, mounts the artifact read-only as `/models/embedding.gguf`, uses host networking, drops all capabilities, sets `no-new-privileges`, and health-checks the service's `/health` path on the configured loopback port.

## Tests

| File | Covers |
|---|---|
| `tests/embeddings/test_course_embedding_generation.py` | Deterministic bounded chunking with overlap and dropped blank windows, the field, language, and origin separation with exact provenance, prerequisite text kept out of every chunk, scoped assembly with unknown-scope rejection, and the configuration-hash fields. |
| `tests/embeddings/test_embedding_provider.py` | Reordering by response index, a terminal 4xx that is not retried and does not echo its body, missing results, an extra component, a non-finite component, and a model mismatch, idempotent close with use after close, and the two admission paths. |
| `tests/embeddings/test_course_embedding_repository.py` | Opt-in PostgreSQL proofs of batched embedding and rerun reuse with no provider call, translation and representative changes that reset and delete rows, pause and restart at a batch checkpoint, failed and interrupted batches that retry, and the projected readiness read. |
| `tests/embeddings/_repository_support.py` | Composes the real service and repository over a recording `FakeProvider` and the real curriculum reads. |
| `tests/embeddings/test_embedding_service.py` | The live contract test of the running service, gated by `COURSE_EXPLORER_RUN_LIVE_EMBEDDING_TESTS=1`: dimension, finiteness, unit length, repeatability of one text, a Finnish and an English input, and a token-dense maximal character chunk. |
| `tests/db/test_teaching_embedding_schema.py` | The chunk origin, lifecycle, hash, and dimension constraints and the cascade from a deleted course version. |
| `tests/search/test_semantic_search_repository.py` | The exact-cosine read over representative chunks, the configuration-hash and lifecycle filters, the inactive scope, and the scoped vector and neighbor reads. |
| `tests/comparison/` and `tests/recommendations/` | The hub-centred consumers of the stored vectors. |
| `tests/embeddings/test_embedding_hub_files.py` | The catalogue mean over every current vector and the outcomes mean over outcomes chunks only, the compact JSON output with its trailing newline, and the rejection of a dataset without outcome chunks. |
| `tests/admin/test_operator_commands.py` | The `hubs-cli` case: the `hubs` machine command delegates once to `run_administrative_hubs` and emits its report JSON. |
| `tests/admin/test_operator_menu.py` | The `embedding-write-hubs` case: only the embedding tool offers `6 Write hubs`, and choosing it calls the writer once. |
