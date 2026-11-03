# Embeddings

An embedding is a vector that represents the meaning of a piece of teaching text, and this page describes how the embedding stage produces and stores those vectors.

## What is embedded

The embedding stage embeds the teaching text of each representative version as one embedding per [chunk](/docs/reference/glossary.md#capture-and-data-preparation). Three fields take part: the course name, the content, and the learning outcomes. Each field is embedded separately for Finnish and English, so one representative version contributes up to six cells, each split into one or more chunks.

The text of a cell is its effective text: the official text when the version carries it, otherwise a translation that is not stale. The stored chunk records whether its text is official or translated and, for a translation, the method, the model, and the time it was made.

Prerequisite text takes no part in an embedding. A semantic match reads the stored chunk vectors, so a topic search reaches a course through the text it teaches. [Teaching text and translation](/docs/backend/text-and-vectors/teaching-text.md) resolves the effective text, and [Representative versions and activity](/docs/backend/catalogue/representative-versions.md) selects the version that is embedded.

A representative version whose six cells are all empty contributes no chunk, and the run report counts those courses.

## The embedding service

The service is one container that runs the model named by `EMBEDDING_MODEL` in `config/search.toml`, `BAAI/bge-m3`, on the CPU. It binds the loopback address and port in `EMBEDDING_HOST` and `EMBEDDING_PORT`, and the settings accept only `127.0.0.1` as the host, so the service answers the local machine alone. The runtime image, the runtime revision, and the model artifact are each pinned: the image by its digest in `EMBEDDING_SERVER_IMAGE`, the runtime by the commit in `EMBEDDING_RUNTIME_REVISION`, and the artifact by the SHA-256 in `EMBEDDING_ARTIFACT_SHA256`.

The artifact at `EMBEDDING_ARTIFACT_PATH` must exist as a regular file and match its checksum before an embedding stage starts, and the service verifies the same checksum and its own runtime revision before it can listen. `EMBEDDING_ARTIFACT_URL` names the HTTPS location the artifact comes from, with no credentials, query string, or fragment in it.

Each request carries a batch of texts to the service's `v1/embeddings` endpoint together with the configured model, and the response holds one vector per input. A vector has 1024 components, the one dimension the settings and the vector column allow. The runtime normalizes each vector as `EMBEDDING_NORMALIZATION` sets, and the example value 2 returns a unit-length vector, so a stored vector has unit length.

A transport failure and a 429 or 5xx status of a generation request are retried up to `EMBEDDING_MAX_ATTEMPTS` attempts, the first attempt included, with a wait that grows between attempts. Every other status ends the request. A response that breaks the contract ends it as well: the body must be JSON, the results must match the inputs one for one with unique indices, every vector must hold exactly 1024 finite components, and a response that names a model must name the configured one. A batch that fails stores no vector and marks its chunks failed, so the next run retries them.

The same service embeds the text of a search query at request time, so a query vector and a stored vector come from one model. A serving process retains each validated query vector in a shared region keyed by the exact query text and the running embedding configuration identity, so a repeated query text of one supervisor returns the same vector without another request to the embedding service, and the region is bounded by `WEB_QUERY_EMBEDDING_CACHE_BYTES`. A query embedding request follows the search policy instead: `SEARCH_EMBEDDING_REQUEST_TIMEOUT_SECONDS` sets its timeout and `SEARCH_EMBEDDING_MAX_ATTEMPTS` sets its attempt count. That timeout bounds the network phases of the one request, so it is not a deadline for the whole search. [Search](/docs/backend/search-and-discovery/search.md#when-the-query-embedding-request-fails) describes the search path and what a failed request leaves in the report.

## Chunking

A text that fits one window forms a single chunk. A longer text is split into overlapping windows, so two consecutive chunks share the overlap and text that crosses a boundary appears in both. A window that holds blank characters only is left out, and every chunk is an exact piece of the text it came from. [Embedding generation](/docs/backend/text-and-vectors/embedding-generation.md#chunk-inputs-and-the-work-key) states the splitting rule.

## The generation run

A run builds the desired chunks from the current catalogue and compares them with the stored chunks of the same canonical courses. Chunks that already match are reused, chunks that need a vector are pending, and rows the run does not need are deleted. The pending chunks then go to the embedding service in batches of `EMBEDDING_GENERATION_BATCH_SIZE`.

![Effective text of each representative version is split into overlapping chunks, and a run reconciles the desired chunks with the stored chunks: matching chunks are reused, pending chunks go to the embedding service, and obsolete chunks are deleted. The chunk store of a dataset holds every chunk of that dataset with its vector, and the serving artifact build computes the authoritative hub pair from the stored vectors.](/docs/diagrams/embedding-generation.svg)

### Matching, pending, and obsolete chunks

Each stored chunk records the exact work it was made from, and a run reuses a chunk only when that record equals the work the current text and settings ask for. No request is sent for a reused chunk. A chunk whose recorded work differs takes the desired text and becomes pending. A desired chunk with no stored row becomes pending. A stored row whose key matches and whose status is pending or failed is pending work again, so a failed chunk is retried by the next run. [Embedding generation](/docs/backend/text-and-vectors/embedding-generation.md#the-chunk-store-and-reconciliation) lists the recorded fields.

A stored row that the desired set of the canonical scope does not contain is deleted from the dataset. That covers the chunks of a course version that is not the representative version and the chunks whose index lies beyond the last window of a shortened text.

A run over a catalogue whose chunks all match makes no request to the embedding service and reports every chunk as reused.

### Pause, stop, and failures

The run commits the vectors of each batch and publishes its progress at the batch boundary. A pause or a stop that takes effect at a boundary ends the run with the committed vectors and leaves the remaining chunks pending for the next run. A failure inside a batch marks that batch failed and ends the run with the error.

The run report counts the courses and chunks it worked on: the canonical, representative, and unembeddable course counts, the desired chunk count, the rows it added, matched, and deleted, the work it reset to pending, and the vectors it stored. The stage actions are described in [Stage lifecycle](/docs/operations/stage-lifecycle.md) and the [Operator menu](/docs/operations/operator-menu.md).

## The configuration hash

Every chunk records a hash of the configuration values that set what a vector means, and a run compares it with the hash of the running settings. When one of those values differs from the stored one, the chunk is embedded again, so a change to any pin re-embeds the whole catalogue from the one runtime the settings name. A change to the chunk window or the overlap re-embeds only the affected chunks, and a change to the batch size or the request timeout re-embeds nothing. [Embedding generation](/docs/backend/text-and-vectors/embedding-generation.md#the-configuration-hash) lists the hashed values and the digest.

## The hubs

Two vectors centre every similarity measurement in a dataset. The [embedding hub](/docs/reference/glossary.md#capture-and-data-preparation) is the mean of the unit vectors of the dataset's completed compatible chunks, and the outcomes hub is the same mean taken over its learning-outcomes chunks. A dataset with no completed compatible chunk has no mean, so both hubs are empty arrays and neither hub is required.

Stored chunk vectors share a common direction, so their raw similarity is high for any pair. The packed search relation holds its chunk vectors centred by the embedding hub, and a search centres the query vector with the same hub before it scans the relation. Comparison and recommendations centre the chunk rows they read by the hub of the field, which is the outcomes hub for learning outcomes. Two unrelated courses therefore score close to zero. [Comparison](/docs/backend/search-and-discovery/comparison.md) and [Recommendations](/docs/backend/search-and-discovery/recommendations.md) describe the meters that follow from those scores.

Each nonempty hub is a JSON array of 1024 numbers in the embedding directory of a versioned artifact family, and an empty dataset's hub is an empty JSON array in the same place. On a site that serves the embedding features, the administration command `serving-artifacts`, the **Build serving artifacts** entry under the **Embedding** tool, and the console preparation action compute both hubs from the current chunk vectors of the target dataset and write them into the hub pair of that directory. A confirmed `datasets copy-to-selected` promotion builds its copy through the same owner and then switches, restarts and proves it. [Serving artifact build](/docs/backend/text-and-vectors/serving-artifact-build.md) states the files the build writes, the artifact family and what a failed build restores. A completed build reaches serving after a full supervisor restart, as [the operations overview](/docs/operations/README.md#derived-files-served-data-and-the-web-restart) states.

For a dataset with current chunks, the command requires complete current embedding coverage of the dataset it builds: the Selected dataset, the configured database in bootstrap, or the named `--dataset` target. Every desired chunk of the represented courses must be a completed chunk with a compatible stored vector, and at least one learning-outcomes chunk must exist. It runs after an embedding run that completes the coverage of that dataset. A dataset with no represented course has no desired chunk, so it builds both hubs empty.

The embedding stage writes the Working dataset. It changes no served vector, artifact file or serving identity. The site serves the Selected dataset's stored vectors and artifact set. A Working embedding run reaches the site after that dataset is promoted to Selected, which builds its serving artifacts, restarts the web unit and proves the served catalogue.

```bash
uv run python scripts/admin.py serving-artifacts
```

The example data preparation computes both hubs from the same stored vectors through the same functions. A read that opens the build fails with the build guidance when the pair or a hub file is absent, when a hub file is not a JSON array, when a nonempty hub file does not hold numeric components, or when a nonempty hub does not hold exactly 1024 finite components. [Serving artifact build](/docs/backend/text-and-vectors/serving-artifact-build.md#the-embedding-switch) states the open and the switch.

## Course centroids

On a site that serves the embedding features, the same `serving-artifacts` command writes one course centroid per represented course with a descriptive content or outcomes chunk. A centroid is the unit mean of the course's hub-centred, unit-normalized descriptive chunk vectors. The row carries the representative identity, the embedding configuration hash and the chunk count.

The serving-artifact build replaces the stored centroid rows and writes the same centroids into the shared centroid file of the build. The recommendation command maps that file through `SharedServingStore` and applies the relatedness floor before it reads candidate summaries and full chunks, so no process builds its own centroid matrix. A missing store or another embedding configuration fails when the artifact set opens, with guidance to run `serving-artifacts`. [Serving artifact build](/docs/backend/text-and-vectors/serving-artifact-build.md#the-hubs-and-the-centroids) states the transaction and the files.

## Embedding coverage

The embedding coverage of a dataset counts its chunk rows by lifecycle state: the total, and the pending, completed, and failed counts for each combination of field, language, and text origin. A generation run reports the coverage of the courses it ran over, and the operator menu reports the embedding coverage of the named role as one coverage report. [Data model](/docs/backend/catalogue/data-model.md) describes the table behind the counts.

A similarity read uses completed rows whose configuration hash equals the configured one. A pending chunk and a failed chunk contribute no score, so a semantic search covers the text the embedding stage has already stored.

## Configuration keys

`config/search.toml` holds the embedding runtime and the generation values. The keys this page describes are:

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

The embedding runtime launch applies the configured `EMBEDDING_CONTEXT_SIZE` value to the context, the batch size and the micro-batch size, as [Machine translation as retrieval-preserving transformation](/docs/experiments/search-and-translation/translation-and-retrieval.md#batch-sizes-and-the-embedding-runtime) records.

The generation mechanism, the hash fields, and the store operations are described in [Embedding generation](/docs/backend/text-and-vectors/embedding-generation.md), and the build that writes the hub pair, the centroids, the shared stores, the study fragments and the packed search relation on a site that serves the embedding features in [Serving artifact build](/docs/backend/text-and-vectors/serving-artifact-build.md). [Ingestion](/docs/backend/catalogue/ingestion.md) describes which official change makes the next embedding run rework a chunk, [Search](/docs/backend/search-and-discovery/search.md) and [Comparison](/docs/backend/search-and-discovery/comparison.md) describe the consumers, and [Data model](/docs/backend/catalogue/data-model.md) describes the stored chunk rows.
