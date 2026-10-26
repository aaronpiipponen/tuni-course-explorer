# Exact and approximate semantic retrieval

Four fixed stored vectors are the queries in a comparison of exact SQL, centred SQL, bounded NumPy and approximate HNSW retrieval on one 58,962-chunk catalogue.

**Evidence status:** Comparative. **Run date:** 21 October 2026.

## The question

The experiment asked whether an exact semantic read can be made cheaper without changing its result, and what recall a bounded approximate HNSW read loses against the exact read. It compared five reads on the same fixed vectors and the same source catalogue snapshot:

- the [semantic search](/docs/backend/search-and-discovery/search.md#semantic) read the product serves, used as the reference or exact oracle
- a representative-filter pushdown that applies the product's representative grouping and identity filter inside SQL
- a centred SQL read over a fixture column that stores the hub-subtracted vector
- a bounded exact NumPy read over every compatible chunk
- an approximate HNSW index over the centred vectors, at two candidate bounds and two `ef_search` values

The comparison measured result sets, order, score differences and recall. It also measured fixture setup, read time, arithmetic time and index build time, and the memory and storage of each fixture. No product setting changed, and no approximate configuration is a product setting.

## Catalogue and fixed queries

The catalogue copy held 11,086 represented courses, of which 4,543 were active, and 58,962 compatible teaching-text [chunks](/docs/reference/glossary.md#capture-and-data-preparation). A chunk was compatible when it was completed, carried a vector, and matched the embedding configuration hash of the run.

Four stored descriptive chunk vectors were frozen before the comparison. Each came from a different canonical course, one from learning outcomes and three from content, all in English at chunk index 0. The vectors are query inputs for a vector-query measurement. They are not embeddings of any lexical string, and they are not a semantic-quality oracle.

| Query | Source field | Language | Chunk index | Exact results |
|---|---|---|---:|---:|
| vector-1 | outcomes | en | 0 | 240 |
| vector-2 | content | en | 0 | 168 |
| vector-3 | content | en | 0 | 479 |
| vector-4 | content | en | 0 | 592 |

The exact results column is the number of courses the exact read returned at the 0.3 threshold after the representative filter. The comparison included active and inactive courses. The product order places active courses first, then descending score, then canonical identity.

## Scoring and centring

The embedding hub is the mean of the catalogue's unit chunk vectors. Semantic search subtracts the hub from the query vector and from each stored vector, then measures cosine similarity. The score for one course is the maximum over its current representative chunks.

```text
hub = mean of the catalogue's unit chunk vectors
score(q, course) = max over chunk vectors v of course of cos(v - hub, q - hub)
cos(a, b) = (a . b) / (||a|| ||b||)
```

The [semantic read and the service](/docs/backend/search-and-discovery/search-queries.md#the-semantic-read-and-the-service) show the SQL form as `1 - ((c - hub) <=> (q - hub))`, where `<=>` is the cosine distance operator. The product read groups by canonical course and current representative identity, keeps a course when its best chunk reaches the threshold, and returns every such course. `SEMANTIC_SEARCH_MIN_SCORE` sets the threshold, and the example sets 0.30. A score runs from -1 to 1, and an unrelated course scores close to zero after centring.

The product read computes the subtraction in SQL. The centred SQL leg instead read a fixture column that already held `embedding - hub`, with no vector index. The approximate leg built an HNSW index on that centred column. The exact, pushdown and centred SQL reads ran without a vector index. The HNSW leg built the only vector index.

## Exact read and representative pushdown

The reference is the product semantic read, run through the product search service with a test provider that returned the fixed query vector. No embedding request ran, so the reference timing covers the database read, the representative filter and the order, not the embedding service.

The representative-filter pushdown moved the representative grouping and identity join into SQL and applied the same threshold and order. It preserved the exact set, order and scores on all four vectors.

| Query | Oracle results | Pushdown results | Same set | Same order | Max score delta | Recall |
|---|---:|---:|---|---|---:|---:|
| vector-1 | 240 | 240 | yes | yes | 0.0 | 1.0 |
| vector-2 | 168 | 168 | yes | yes | 0.0 | 1.0 |
| vector-3 | 479 | 479 | yes | yes | 0.0 | 1.0 |
| vector-4 | 592 | 592 | yes | yes | 0.0 | 1.0 |

Recorded wall medians show the pushdown was slower than the reference on every query. It is equivalent on these cases, but it is not a measured speed benefit.

| Query | Exact product read (s) | Representative pushdown (s) | Centred SQL read (s) |
|---|---:|---:|---:|
| vector-1 | 0.5699 | 0.8105 | 0.4898 |
| vector-2 | 0.5756 | 0.6939 | 0.4928 |
| vector-3 | 0.6202 | 0.6953 | 0.4927 |
| vector-4 | 0.5863 | 0.7159 | 0.5023 |

The chart shows the single-query wall time for the three reads.

![Single-query wall time for the exact, pushdown and centred reads on four fixed vectors, showing the pushdown slower than the exact read and the centred read faster.](/docs/charts/semantic-retrieval-read-latency.svg)

The exact fixture copied the corpus in 12.7 s and completed setup in 18.0 s. The centred fixture completed setup in 18.65 s. The recorded medians come from three passes after one warmup.

## Centred SQL and bounded exact NumPy

The centred SQL read matched the exact oracle on set and order for all four vectors. The bounded NumPy read scored every compatible chunk in batches of 512 and kept the maximum score for each chunk identity. It matched the set and order on all four vectors, with score differences below 3.1e-7.

| Query | Centred SQL set and order | NumPy set and order | NumPy max score delta | NumPy recall |
|---|---|---|---:|---:|
| vector-1 | exact | same | 1.42e-7 | 1.0 |
| vector-2 | exact | same | 1.87e-7 | 1.0 |
| vector-3 | exact | same | 1.37e-7 | 1.0 |
| vector-4 | exact | same | 2.98e-7 | 1.0 |

No threshold crossing and no set difference occurred. The centred SQL medians were 0.4898 s, 0.4928 s, 0.4927 s and 0.5023 s, about 0.08 s to 0.13 s faster per query than the exact reference.

The NumPy pass median was 17.78 s of fixture read and 3.93 s of arithmetic over 58,962 chunks in 116 batches. The read is shared across all four queries in one pass. It is not one product request, so the figures are not a single-query latency. At this corpus size, the shared read is far slower than the centred SQL read.

## Approximate HNSW

HNSW is a graph index for approximate nearest-neighbour search. One index was built on the centred vector column with `vector_cosine_ops`, `m` 16 and `ef_construction` 64. The build took 95.8 s and the index occupied 369.65 MB. The fixture setup took 19.68 s, and the build ran under a 120 s statement timeout. The query plan used the index on all 16 configuration-and-query checks.

The candidate bound is the SQL `LIMIT` on chunk rows. `ef_search` is the size of the dynamic candidate list the HNSW search explores. Neither value is a course result cutoff. Candidate course counts are before the 0.3 score threshold. Set equality and recall compare the final course results after that threshold with the exact results, the same 240, 168, 479 and 592 courses from the reference.

| Candidates | `ef_search` | Query | Candidate chunks | Candidate courses | Exact results | Recall | Same set |
|---:|---:|---|---:|---:|---:|---:|---|
| 128 | 128 | vector-1 | 128 | 72 | 240 | 0.3000 | no |
| 128 | 128 | vector-2 | 128 | 67 | 168 | 0.3988 | no |
| 128 | 128 | vector-3 | 128 | 107 | 479 | 0.2234 | no |
| 128 | 128 | vector-4 | 128 | 106 | 592 | 0.1791 | no |
| 128 | 512 | vector-1 | 128 | 72 | 240 | 0.3000 | no |
| 128 | 512 | vector-2 | 128 | 67 | 168 | 0.3988 | no |
| 128 | 512 | vector-3 | 128 | 107 | 479 | 0.2234 | no |
| 128 | 512 | vector-4 | 128 | 106 | 592 | 0.1791 | no |
| 512 | 128 | vector-1 | 135 | 76 | 240 | 0.3167 | no |
| 512 | 128 | vector-2 | 133 | 71 | 168 | 0.4226 | no |
| 512 | 128 | vector-3 | 171 | 139 | 479 | 0.2902 | no |
| 512 | 128 | vector-4 | 130 | 107 | 592 | 0.1807 | no |
| 512 | 512 | vector-1 | 512 | 312 | 240 | 1.0000 | yes |
| 512 | 512 | vector-2 | 512 | 336 | 168 | 0.9940 | no |
| 512 | 512 | vector-3 | 512 | 277 | 479 | 0.5783 | no |
| 512 | 512 | vector-4 | 512 | 305 | 592 | 0.5152 | no |

Recall is the share of the exact oracle's course results that the approximate read returned. No approximation added a course that the oracle did not contain, and every retained candidate had the exact score. The losses are candidate omissions and their order effects.

The two bounds interact. At candidate 128, `ef_search` 128 and 512 produced the same candidate count and the same recall on every vector. The `LIMIT` stopped the scan at 128 chunks, so the larger `ef_search` did not add candidates. At candidate 512 and `ef_search` 128, the scan returned 130 to 171 chunks, so `ef_search` bounded the scan below the candidate cap. Recall at that setting was 0.3167, 0.4226, 0.2902 and 0.1807.

Only the largest setting, candidate 512 with `ef_search` 512, reached recall 1.0000 and the exact set, and only for vector-1. The other three queries at the same setting returned recall 0.9940, 0.5783 and 0.5152, and none had the same set. At every setting except 512/512, recall was between 0.1791 and 0.4226, and the approximate read omitted 58 to 82 percent of the exact results.

No approximate configuration was exact. The matrix contains no candidate bound or `ef_search` value that returned the exact set for all four queries, including the setting where one query reached recall 1.0000. No candidate bound, `ef_search` value or recall result is a product setting.

The chart groups recall by configuration and query.

![Recall against the exact oracle for four fixed vectors at four HNSW candidate and ef_search settings, showing recall 1.0 only for vector-1 at the largest setting.](/docs/charts/semantic-retrieval-hnsw-recall.svg)

The comparison reports set parity and recall. It does not report a separate order count or a query latency for HNSW.

## Memory and storage

The memory table covers the three retrieval fixtures. It reports the fixture setup time, the on-disk chunk relation, the cgroup peak, the peak resident set of the fixture backend and the process-wide peak resident set. The byte values are converted to MB.

| Leg | Fixture setup (s) | Chunk relation (MB) | cgroup peak (MB) | Backend peak RSS (MB) | Process peak RSS (MB) |
|---|---:|---:|---:|---:|---:|
| exact | 18.0 | 341.27 | 805.31 | 105.90 | 217.86 |
| centred NumPy | 18.65 | 341.27 | 805.31 | 92.45 | 240.42 |
| HNSW | 19.68 | 341.27 | 805.31 | 88.85 | 206.85 |

The cgroup limit was 805.31 MB. The exact and HNSW cgroup peaks were 4,096 bytes above the limit, and the container stayed alive. The peak is reported as read.

The 341.27 MB chunk relation is storage on disk, not SQL query working memory. The cgroup figure includes the fixture's page cache and index files. The backend figure covers one fixture backend per leg, not every backend or worker process. The process peak is process-wide and includes the fixture copy stream, the NumPy arrays in the centred leg and the case payloads.

The HNSW index occupies 369.65 MB on top of the 341.27 MB relation. The exact, centred NumPy and HNSW fixtures reported `temp_bytes` 0 at setup, so no temporary spill was recorded.

## Corrections and failed attempts

Five evidence clients and five client correction attempts ran, rather than the allowed eight measurement clients and two corrections. Four corrections were on the semantic path and one on the lexical path. A supervisor failure before any client started was a separate attempt. The total of 10 clients met the combined cap, but the correction category exceeded its allowance.

The four semantic corrections were:

- The first pushdown call used the raw stored vector as the query instead of the hub-centred vector. Its comparison was invalid. The corrected pushdown matched the oracle.
- The first NumPy cursor read selected from the chunk table without its course and version joins.
- The first NumPy pass passed pgvector `Vector` objects into the array instead of plain lists.
- The first NumPy scoring used `1 - cosine` in place of the cosine similarity.

The corrected NumPy run matched the exact set and order with the score differences in the table above.

The first fixture supervisor run failed before a client started. Its `awk` program used `index` as a variable name, which collided with a reserved name. Cleanup also met a sticky socket directory, and a separate cleanup removed two socket files. No measurement ran in that attempt.

## Embedding provider background

A feasibility measurement recorded before this comparison tested the CPU-only embedding service on its own. The service runs BGE-M3 (`BAAI/bge-m3`) with 1,024-component vectors on a two-thread aarch64 llama.cpp runtime. The measurement recorded a peak resident set of 1,117.51 MB, idle CPU of 0.0167 percent and an embedding-only warm p95 of 53.5 ms.

| Item | Value |
|---|---|
| Model | `BAAI/bge-m3`, 1,024 components |
| Runtime | CPU-only llama.cpp, 2 threads, aarch64 |
| Peak resident set | 1,117.51 MB |
| Idle CPU | 0.0167% |
| Warm p95, embedding only | 53.5 ms |

That boundary is one embedding request. It is not a search latency. The measurement compared the 53.5 ms with a 0.5 s full-search budget, but it did not measure the full search path.

The retrieval experiment made no embedding request. Its exact, pushdown and centred times start after the query vector exists, because the test provider returned the fixed vector. The 53.5 ms embedding time and the 0.49 s to 0.62 s exact and centred read times therefore have different boundaries. They are not added here, and their sum is not an end-to-end search latency.

## Setup details

The work ran on a 4-core aarch64 server with 23.6 GB of RAM. The embedding service is CPU-only, and the retrieval experiment used stored vectors, so no model inference ran during the retrieval measurements.

| Item | Value |
|---|---|
| Python | 3.14.3 |
| NumPy | 2.4.6, one BLAS thread |
| PostgreSQL | 18.6, aarch64 |
| pgvector | 0.8.6 |
| Fixture memory cap | 805.31 MB, no swap |
| Client address-space cap | 1.074 GB |
| Query sample limit | 60 s |
| Fixture setup limit | 120 s |
| Warmup and recorded passes | one warmup, three recorded passes |
| Query vector | BGE-M3, 1,024 components, unit length |
| Parallel query workers | 0 |

Each fixture ran in a disposable PostgreSQL container with no network and no published port. The catalogue snapshot was read with `transaction_read_only=on` and a 30 s statement timeout. The fixture copy and the index were written only inside the disposable database. The stored schema and data were not changed.

Database and CPU cache warmth was not controlled. The medians come from three recorded passes after one warmup. Each leg ran one client process, and no concurrent load was measured.

## What the results do not establish

- The four stored vectors are fixed chunk-query proxies. They establish no semantic, retrieval or recommendation quality.
- The exact reference ran on a copy of the compatible chunk rows, not on the catalogue database.
- The pushdown comparison covers four vectors and one catalogue snapshot.
- The NumPy read is shared across four queries per pass. It is not a single-request latency and not a memory bound for PostgreSQL.
- The backend memory figures cover one fixture backend per leg. They are not the memory of all backends or worker processes.
- The cgroup figures include page cache and index files. They are not an isolated query working-memory figure.
- The HNSW results are approximate. No candidate bound, `ef_search` value or recall result is a product setting or an exact result.
- The HNSW comparison reports recall and candidate counts, not a query latency.
- The search timings exclude the query embedding request.
- The experiment used one catalogue snapshot, four fixed vectors, one threshold and no concurrent load.
- [Lexical matching equivalence and collation](/docs/experiments/search-and-translation/lexical-matching-and-collation.md) covers the lexical SQL forms and their collation behavior.
- The provider feasibility measured embedding only. It did not measure the full search path.
- No product change was made, and no approximate configuration is a product setting.

## Open questions

- Whether a full search path that combines the 53.5 ms embedding request with the exact read meets the 0.5 s budget used in the provider feasibility. The two parts were measured separately and never joined. Untested.
- Whether the centred SQL advantage holds on a larger corpus or under concurrent load. The experiment used one corpus and no concurrency. Untested.
- Whether an index on the centred expression, rather than a separate centred column, can preserve exactness at a lower read cost. The experiment did not test an expression index. Untested.
