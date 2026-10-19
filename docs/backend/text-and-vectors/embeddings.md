# Embeddings

An embedding is a vector that represents the meaning of a piece of teaching text, and this page describes how the embedding stage produces and stores those vectors.

## What is embedded

The embedding stage embeds the teaching text of each representative version as one embedding per [chunk](/docs/reference/glossary.md#capture-and-data-preparation). Three fields take part: the course name, the content, and the learning outcomes. Each field is embedded separately for Finnish and English, so one representative version contributes up to six pieces of text.

The text of a cell is its effective text: the official text when the version carries it, otherwise a translation that is not stale. The stored chunk records whether its text is official or translated and, for a translation, the method, the model, and the time it was made.

Prerequisite text takes no part in an embedding. A semantic match reads the stored chunk vectors, so a topic search reaches a course through the text it teaches. [Teaching text and translation](/docs/backend/text-and-vectors/teaching-text.md) resolves the effective text, and [Representative versions and activity](/docs/backend/catalogue/representative-versions.md) selects the version that is embedded.

A representative version whose six cells are all empty contributes no chunk, and the run report counts those courses.

## The embedding service

The service is one container that runs the model named by `EMBEDDING_MODEL` in `config/search.toml`, `BAAI/bge-m3`, on the CPU. It binds the loopback address and port in `EMBEDDING_HOST` and `EMBEDDING_PORT`, and the settings accept only `127.0.0.1` as the host, so the service answers the local machine alone. The runtime image, the runtime revision, and the model artifact are each pinned: the image by its digest in `EMBEDDING_SERVER_IMAGE`, the runtime by the commit in `EMBEDDING_RUNTIME_REVISION`, and the artifact by the SHA-256 in `EMBEDDING_ARTIFACT_SHA256`.

The artifact at `EMBEDDING_ARTIFACT_PATH` must exist as a regular file and match its checksum before an embedding stage starts, and the service verifies the same checksum and its own runtime revision before it can listen. `EMBEDDING_ARTIFACT_URL` names the HTTPS location the artifact comes from, with no credentials, query string, or fragment in it.

Each request carries a batch of texts to the service's `v1/embeddings` endpoint together with the configured model, and the response holds one vector per input. A vector has 1024 components, the one dimension the settings and the vector column allow, and a stored vector has unit length.

A transport failure and a 429 or 5xx status of a generation request are retried up to `EMBEDDING_MAX_ATTEMPTS` attempts, the first attempt included, with a wait that grows between attempts. Every other status ends the request. A response that breaks the contract ends it as well: the body must be JSON, the results must match the inputs one for one with unique indices, every vector must hold exactly 1024 finite components, and a response that names a model must name the configured one. A batch that fails stores no vector and marks its chunks failed, so the next run retries them.

The same service embeds the text of a search query at request time, so a query vector and a stored vector come from one model. A query embedding request follows the search policy instead: `SEARCH_EMBEDDING_REQUEST_TIMEOUT_SECONDS` sets its timeout and `SEARCH_EMBEDDING_MAX_ATTEMPTS` sets its attempt count. That timeout bounds the network phases of the one request, so it is not a deadline for the whole search. [Search](/docs/backend/search-and-discovery/search.md#when-the-query-embedding-request-fails) describes the search path and what a failed request leaves in the report.

## Chunking

A text that fits one window forms a single chunk. A longer text is split into windows of `EMBEDDING_CHUNK_MAX_CHARACTERS` characters that step forward by the window minus `EMBEDDING_CHUNK_OVERLAP_CHARACTERS`, so two consecutive chunks share the overlap and text that crosses a boundary appears in both. A window that holds blank characters only is left out, and every chunk is an exact piece of the text it came from. The example sets a window of 1200 characters and an overlap of 120 characters.

## The generation run

A run builds the desired chunks from the current catalogue and compares them with the stored chunks of the same canonical courses. Chunks that already match are reused, chunks that need a vector are pending, and rows the run does not need are deleted. The pending chunks then go to the embedding service in batches of `EMBEDDING_GENERATION_BATCH_SIZE`.

![Effective text of each representative version is split into overlapping chunks, and a run reconciles the desired chunks with the stored chunks: matching chunks are reused, pending chunks go to the embedding service, and obsolete chunks are deleted. The chunk store holds every chunk of the selected dataset with its vector, and the hub files are computed from those vectors by the administration hub command.](/docs/diagrams/embedding-generation.svg)

### Matching, pending, and obsolete chunks

Each stored chunk records the exact work it was made from: its field, language, and chunk index, the origin of the text, the text itself, the source hash of the representative version, the hash of the effective text, the source text hash, the hash of the chunk text, the provenance of a translation, the model, the artifact checksum, and the hash of the configuration values that set vector semantics.

A completed chunk whose recorded work equals the desired work is reused, and no request is sent for it. A chunk whose recorded work differs takes the desired text and becomes pending. A desired chunk with no stored row becomes pending. A stored row whose key matches and whose status is pending or failed is pending work again, so a failed chunk is retried by the next run.

A stored row that the desired set of the canonical scope does not contain is deleted from the dataset. That covers the chunks of a course version that is not the representative version and the chunks whose index lies beyond the last window of a shortened text.

A run over a catalogue whose chunks all match makes no request to the embedding service and reports every chunk as reused.

### Pause, stop, and failures

The run commits the vectors of each batch and publishes its progress at the batch boundary. A pause or a stop that takes effect at a boundary ends the run with the committed vectors and leaves the remaining chunks pending for the next run. A failure inside a batch marks that batch failed and ends the run with the error.

The run report counts the courses and chunks it worked on: the canonical, representative, and unembeddable course counts, the desired chunk count, the rows it added, matched, and deleted, the work it reset to pending, and the vectors it stored. The stage actions are described in [Stage lifecycle](/docs/operations/stage-lifecycle.md) and the [Operator menu](/docs/operations/operator-menu.md).

## The configuration hash

Every chunk records a hash of the configuration values that set what a vector means: the model, the artifact checksum, the dimension, the pooling, the normalization, and the runtime revision. When one of those values differs from the stored one, the chunk is embedded again, so a change to any pin re-embeds the whole catalogue from the one runtime the settings name. The batch size, the chunk window, the overlap, and the request timeout are not part of the hash. A change to the window or the overlap reaches an affected chunk through its chunk text hash, and the batch size and the timeout change how the work is sent rather than what a vector means.

## The hubs

Two vectors centre every similarity measurement in a dataset. The [embedding hub](/docs/reference/glossary.md#capture-and-data-preparation) is the mean of the unit vectors of the dataset's completed compatible chunks, and the outcomes hub is the same mean taken over its learning-outcomes chunks.

Stored chunk vectors share a common direction, so their raw similarity is high for any pair. Search subtracts the embedding hub from the query vector and from the stored vectors, and comparison and recommendations subtract the hub of the field, which is the outcomes hub for learning outcomes. Two unrelated courses therefore score close to zero. [Comparison](/docs/backend/search-and-discovery/comparison.md) and [Recommendations](/docs/backend/search-and-discovery/recommendations.md) describe the meters that follow from those scores.

Each hub is a JSON array of 1024 numbers under `config/derived/` in the example, and the keys `EMBEDDING_HUB_VECTOR` and `EMBEDDING_OUTCOMES_HUB_VECTOR` in `config/search.toml` hold the path of one file each. The administration command `hubs`, and the **Write hubs** entry under the **Embedding** tool in the operator menu, compute both hubs from the current chunk vectors of the selected dataset and write them to those two paths. Readiness checks and both mean calculations finish before the first file is written, so a failed check or calculation leaves both files untouched.

The command requires the selected dataset and complete current embedding coverage: every desired chunk of the represented courses must be a completed chunk with a compatible stored vector, and at least one learning-outcomes chunk must exist. It runs after an embedding run that completes the coverage of the selected dataset.

```bash
uv run python scripts/admin.py hubs
```

The example data preparation computes both hubs from the same stored vectors through the same functions. A read that needs a hub fails when the file is absent, when the file is not a list of numbers, or when it does not hold exactly 1024 finite components. [Configuration](/docs/backend/configuration.md) describes how the settings owner resolves a hub reference.

> [!IMPORTANT]
> A web server whose site serves embedding features reads both hubs when its process starts and keeps those values while it runs. Restart the web server after writing the hubs so it reads the files again.

## Embedding coverage

The embedding coverage of a dataset counts its chunk rows by lifecycle state: the total, and the pending, completed, and failed counts for each combination of field, language, and text origin. A generation run reports the coverage of the courses it ran over, and the operator menu reports the embedding coverage of the selected dataset as one coverage report. [Data model](/docs/backend/catalogue/data-model.md) describes the table behind the counts.

A similarity read uses completed rows whose configuration hash equals the configured one. A pending chunk and a failed chunk contribute no score, so a semantic search covers the text the embedding stage has already stored.

## Configuration keys

`config/search.toml` holds the embedding runtime, the generation values, and the two hub references. The keys this page describes are:

| Key | Meaning |
|---|---|
| `EMBEDDING_HOST` | The loopback address the service binds. The example sets `127.0.0.1`, the only value the settings allow. |
| `EMBEDDING_PORT` | The port of the service. The example sets 8081. |
| `EMBEDDING_MODEL` | The model identity carried by every request. The example sets `BAAI/bge-m3`. |
| `EMBEDDING_POOLING` | The pooling the runtime applies: `cls`, `mean`, or `last`. The example sets `cls`. |
| `EMBEDDING_NORMALIZATION` | The normalization the runtime applies, from -1 upward. The example sets 2. |
| `EMBEDDING_THREADS` | How many threads the runtime uses. The example sets 2. |
| `EMBEDDING_CONTEXT_SIZE` | The context window of the runtime, which also sets its batch and micro-batch size. The example sets 2048. |
| `EMBEDDING_REQUEST_TIMEOUT_SECONDS` | How long one generation request may take, up to 600 seconds. The example sets 600. |
| `EMBEDDING_MAX_ATTEMPTS` | How many attempts one generation request gets, the first included, from 1 to 5. The example sets 3. |
| `EMBEDDING_RETRY_BACKOFF_SECONDS` | The wait before the first retry, doubled for each further retry, up to 10 seconds. The example sets 0.5. |
| `EMBEDDING_GENERATION_BATCH_SIZE` | How many chunks one request carries, from 1 to 128. The example sets 32. |
| `EMBEDDING_CHUNK_MAX_CHARACTERS` | The length of one chunk window, from 2 to 8192 characters. The example sets 1200. |
| `EMBEDDING_CHUNK_OVERLAP_CHARACTERS` | How many characters two consecutive chunks share. It is smaller than the window, and the example sets 120. |
| `EMBEDDING_ARTIFACT_URL` | The HTTPS location of the model artifact, without credentials, query string, or fragment. |
| `EMBEDDING_ARTIFACT_PATH` | The file the service reads the model from, checked against its checksum before a stage starts. |
| `EMBEDDING_ARTIFACT_SHA256` | The SHA-256 the artifact file must match. |
| `EMBEDDING_SERVER_IMAGE` | The runtime image, pinned by digest. |
| `EMBEDDING_RUNTIME_REVISION` | The runtime revision the image must report. |
| `EMBEDDING_CONTROLLER_STATE_ROOT` | The repository-relative directory of the embedding stage state. |
| `EMBEDDING_HUB_VECTOR` | The path of the embedding hub file. |
| `EMBEDDING_OUTCOMES_HUB_VECTOR` | The path of the outcomes hub file. |

The generation mechanism, the hash fields, and the store operations are described in [Embedding generation](/docs/backend/text-and-vectors/embedding-generation.md). [Ingestion](/docs/backend/catalogue/ingestion.md) describes which official change makes the next embedding run rework a chunk, [Search](/docs/backend/search-and-discovery/search.md) and [Comparison](/docs/backend/search-and-discovery/comparison.md) describe the consumers, and [Data model](/docs/backend/catalogue/data-model.md) describes the stored chunk rows.
