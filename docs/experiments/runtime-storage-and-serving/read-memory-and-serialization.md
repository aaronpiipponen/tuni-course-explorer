# Read memory, compact projections and response serialization

This report measures the memory that full, projected and streamed reads retain, the size and parity of catalogue projections, and the cost of caches, raw-input reuse, float32 storage and compression.

**Evidence status:** Corrected. **Run date:** 21 October 2026.

## The question

The recommendation read returns stored teaching-text chunks for a basis and a candidate pool. Each chunk carries its embedding vector and metadata. The read can materialize a Python carrier for every row, project only the descriptive fields in SQL, or stream rows into one matrix. The first question is how much client memory each shape retains, and whether the smallest shape returns the same result.

A second group asks what representation costs. Prepared vector arrays can use float64 or float32. A normalized lexical projection can replace repeated normalization during search. A prepared cache can retain a matrix or one course's facts. The report measures the bytes and the parity of each, and it keeps the different memory measures apart.

The report also covers gzip levels for the serialized report, and the small settings, connection and serialization stages around the read. Those stages are context, not part of the read result.

The measurements use fixed cohorts and one pinned dataset. They make no HTTP, full-catalogue, retrieval-quality or semantic-quality claim.

## Fixed pools and conditions

The three bases are prefixes of one fixed representative order. The 50-course basis uses the first recovery capture. The fixed request used `basis="completed"`, `mode="all"`, `display_language="en"`, `include_inferred=false` and `active_only=true`. The selected set equals the completed set equals the basis. The candidate pools held 42, 435 and 1,874 ranked candidates.

The configured policy was `RECOMMENDATION_CHUNK_TOP_K = 40`, `RECOMMENDATION_MIN_RELATEDNESS = 0.33`, `RECOMMENDATION_NEAR_DUPLICATE_PERCENT = 90`, `RECOMMENDATION_OVERLAP_PENALTY_WEIGHT = 0.0`, `COMPARISON_OVERLAP_FLOOR = 0.20` and `COMPARISON_OVERLAP_CEILING = 0.90`. The search settings, embedding configuration, embedding hub and outcomes hub were pinned by digest. The dataset was pinned through its named receipt, the required schema head was checked, and the selected-dataset pointer was not resolved.

The catalogue holds 11,086 represented courses, of which 4,543 are active, and 9,901 eligible module versions. The vectors are stored BGE-M3 embeddings with 1,024 components, so no embedding model ran during the measurements.

| Basis | Basis full rows | Basis descriptive rows | Candidate full rows | Candidate descriptive rows | Retained results |
|---:|---:|---:|---:|---:|---:|
| 1 | 4 | 2 | 221 | 137 | 37 |
| 10 | 59 | 39 | 2,641 | 1,771 | 69 |
| 50 | 309 | 209 | 11,405 | 7,657 | 319 |

A full row is a stored chunk of any field, including the name field. A descriptive row is a content or learning-outcomes chunk. The product's recommendation command selects the content and learning-outcomes rows only, and the descriptive read matches that shape.

## Measurement units

The report uses five memory measures, and they are not interchangeable.

| Measure | What it counts | What it leaves out |
|---|---|---|
| Array bytes | The NumPy buffer of a matrix, from `array.nbytes` | Object metadata, allocator rounding, interpreter pages |
| Resident memory | The process's resident pages, from `VmRSS` | Pages that were never touched or were swapped out |
| Process peak | The resident-memory high-water mark, from `VmHWM` | Nonresident pages and per-stage attribution. The peak is process-wide and retains the warmup. |
| Python-traced memory | Python allocations, from `tracemalloc` | Extension buffers and allocator arenas |
| Object-graph bytes | A `sys.getsizeof` walk over Python objects, each shared object once | Per-instance bytes of a dict-backed structure that the walk does not reach |

A carrier is one Python object that holds a stored chunk's values and its vector. A streamed read partitions the rows in SQL and fills one matrix, and at most one partition of carriers is alive. The matched comparison calls its streamed leg the bounded leg.

The stages of one read sequence nest inside one process and are not additive. Process memory includes the interpreter, libraries and allocator arenas. A resident delta is not the same as array bytes, and a cache bound that counts array or object-graph bytes is not a resident-set size.

## Full, descriptive and streamed reads

The full read selected every chunk field and returned one carrier per row. The descriptive read selected content and outcomes rows only and also returned carriers, as [Coverage and ranking](/docs/backend/search-and-discovery/coverage-and-ranking.md#recommendation-composition) describes. The streamed read filled one float32 matrix and held one partition at a time. The recommendation line measured the read-time saving of the projected read against the full read, which is described in [Recommendation vectorization and narrow reads](/docs/experiments/recommendations/vectorization-and-narrow-reads.md). This report measures what each read retains.

Recorded wall seconds, one warmup and one recorded pass per sequence. The read sequences are read-only and do not include the consumer.

| Basis | Full basis | Full candidate | Descriptive basis | Descriptive candidate | Streamed candidate, 128 rows | Streamed candidate, 512 rows |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 0.016 | 0.361 | 0.011 | 0.248 | 0.171 | 0.180 |
| 10 | 0.104 | 4.695 | 0.087 | 3.467 | 2.035 | 2.032 |
| 50 | 0.513 | 21.677 | 0.372 | 16.581 | 9.977 | 10.117 |

The streamed basis reads took 0.009, 0.046 and 0.225 s at 128 rows, and 0.009, 0.045 and 0.223 s at 512 rows. The timings are single recorded passes and do not replace the paired read timing of the recommendation line.

Resident growth for the 50-course basis. Each growth is measured from the resident size at the start of its sequence, and the resident size moves between sequences, so the growth and resident-after columns do not add down the table.

| Sequence | Resident growth (MB) | Resident after (MB) | Process peak (MB) |
|---|---:|---:|---:|
| Full basis read, 309 chunks | +3.7 | 143.6 | 157.7 |
| Full candidate read, 11,405 chunks | +233.9 | 374.4 | 753.2 |
| Descriptive basis read | 0.0 | 352.7 | 753.2 |
| Descriptive candidate read | +18.7 | 371.5 | 753.2 |
| Streamed candidate, 128 rows | 0.0 | 356.0 | 753.2 |
| Streamed candidate, 512 rows | +15.5 | 370.4 | 753.2 |

The growth on the candidate read for the three shapes is plotted below.

![Resident growth at the 50-course basis for the full carrier read, the descriptive read and the streamed 512-row read. The full carrier read adds 233.9 MB, and the descriptive and streamed reads add 18.7 and 15.5 MB.](/docs/charts/runtime-memory-candidate-retention.svg)

At the 50-course basis the full candidate read added 233.9 MB and set a 753.2 MB process peak. The descriptive candidate read added 18.7 MB. The streamed read held a 31,363,072-byte float32 matrix, 31.36 MB for 7,657 rows by 1,024 components, and added 15.5 MB at 512 rows. The 128-row partition added 0.0 MB. The two streamed deltas differ while the matrix is the same size, so the difference reflects allocator state, not matrix size.

The full candidate read holds every chunk as a carrier, so the 233.9 MB is carrier retention, not array bytes. The streamed read holds the matrix and one bounded partition. Resident memory did not return to the post-import baseline because Python allocator arenas remain resident, and this line makes no claim that freed carriers return memory to the operating system.

The streamed candidate read used two SQL statements of at most 1,000 triples each. At the 50-course basis it used 90 partitions at 128 rows and 23 at 512 rows, with a largest partition of 128 or 512 rows. Its chunk digest equals the saved descriptive digest, and the recorded streamed row counts equal the full-read counts. The full-row equality is recorded but not a code-enforced assertion, so a skipped non-descriptive row would not fail the comparison.

One retained database connection added no measurable client resident growth, and its delta rounds to zero. An additive estimate at twice the post-case resident size of the 50-course basis, 362.2 MB, is 724,369,408 bytes, 724.4 MB. It is arithmetic, not a simultaneous measurement.

## The matched bounded read

The matched comparison ran two legs in separate processes. Both used the same 50-course basis metadata, the same 50 basis triples, the same 1,874 candidate triples, the same 1,874 course summaries and the same float64 product-formula consumer. The rows were 309 basis rows and 11,405 candidate rows, of which 7,657 were descriptive.

The materialized leg read descriptive rows only, as the product descriptive read does, and matched both descriptive digests. The bounded leg streamed every stored row in partitions of at most 256 rows and matched the candidate all-row digest, the candidate descriptive digest and the basis descriptive digest. Its basis all-row digest covered 309 rows and equalled the earlier unfiltered basis read. Both legs produced the same ordered result digest and the same descriptive carrier digests.

| Parity against the product reference | Result |
|---|---|
| Result count | 319 of 319 |
| Exact payload matches | 319 of 319 |
| Membership changes | 0 |
| Order changes | 0 |
| Relatedness, score and overlap changes | 0, 0, 0 |
| Maximum absolute numeric delta | 0.0 |
| Course payload changes | 0 |
| Derived flag changes | 0 |
| Exact tie pairs preserved | 27 of 27 |
| Added or removed results | 0 |

Both legs scored 1,874 groups with chunks, 1,532 below the relatedness floor, 23 near-duplicates and 319 results.

| Leg | Warmup wall (s) | Recorded wall (s) | Fresh baseline RSS (MB) | Warmup growth (MB) | Recorded growth (MB) | Peak RSS (MB) |
|---|---:|---|---:|---:|---|---:|
| Materialized | 19.816 | 11.003, 11.069, 11.035 | 113.7 | 432.7 | 263.7, 252.1, 246.8 | 546.9 |
| Bounded | 23.699 | 13.000, 12.952, 13.259 | 113.9 | 53.5 | 9.8, 10.8, 5.0 | 171.5 |

The process peak and the largest recorded sample growth of the two legs are plotted below.

![Process peak and largest recorded sample growth for the materialized and bounded legs of the matched read at the 50-course basis. The bounded leg peaks at 171.5 MB against 546.9 MB for the materialized leg.](/docs/charts/runtime-memory-bounded-read-peak.svg)

The bounded leg lowered the process peak by 375.4 MB and each recorded sample growth by 241 to 254 MB. It was about 2 s slower per recorded sample, 17 to 20 percent, 10.0 s over the four sample runs and 9.3 s over the whole process.

These are the only paired values. The 753.2 MB peak from the earlier read sequence is not the materialized baseline. That sequence had run the full basis read and the full candidate read from a 139.8 MB post-representative baseline, and its peak belongs to the 11,405-row full carrier read. The matched materialized leg read 7,657 descriptive rows from a 113.7 MB fresh baseline and peaked at 546.9 MB. Reading 753.2 to 171.5 as a paired gain would attribute a difference in read shape, row count and process state to the bounded read.

The materialized carrier arithmetic is 255.0 MB from 7,657 descriptive rows at 33,309 bytes per measured carrier, consistent with the recorded growth. The bounded leg holds one candidate group's carriers and one row partition. The warmup sets the process high-water mark, which masks the per-sample peak excess, so the warmup growth and the per-sample resident deltas are the evidence.

## Array storage and float precision

Prepared bytes are reported from `array.nbytes`. The arrays were loaded from a derived file and never from the multi-hundred-megabyte capture JSON, so these deltas do not attribute capture decoding to preparation or cache cost.

| Basis | Prepared basis float64 (bytes) | Prepared basis float32 (bytes) | Candidate matrix float64 (bytes) | Candidate matrix float32 (bytes) | Float32 saving |
|---:|---:|---:|---:|---:|---:|
| 1 | 32,768 | 16,384 | 1,122,304 | 561,152 | 50 percent |
| 10 | 409,600 | 204,800 | 14,508,032 | 7,254,016 | 50 percent |
| 50 | 2,129,920 | 1,064,960 | 62,726,144 | 31,363,072 | 50 percent |

At the 50-course basis, loading the derived arrays added 63.9 MB resident. The float64 prepared basis added 3.5 MB, the float32 prepared basis added 1.6 MB, and the float32 candidate matrix added 31.5 MB. Releasing all arrays after a collection dropped resident memory by 94.0 MB and ended 6.5 MB above the pre-fixture baseline.

| Basis | float64 candidate matrix (MB) | float32 candidate matrix (MB) |
|---:|---:|---:|
| 1 | 1.12 | 0.56 |
| 10 | 14.51 | 7.25 |
| 50 | 62.73 | 31.36 |

The prepared candidate matrix size at each basis is plotted below.

![Prepared candidate matrix size in decimal megabytes for float64 and float32 storage on the three fixed bases. Float32 halves the bytes at every basis.](/docs/charts/runtime-memory-array-bytes.svg)

Float32 halves the array bytes at every basis. That is a byte result, not a parity result.

Every variant was compared with the product float64 scorer on the same captured pool. The float64 NumPy leg reproduced the retained set, order, exact ties and flags, and differed only in the last binary digits.

| Basis | Variant | Same set and order | Rank changes | Membership changes | Tie pairs | Max relatedness delta | Max overlap delta |
|---:|---|---|---:|---:|---:|---:|---:|
| 1 | float64 storage, float64 math | yes | 0 | 0 | 0 of 0 | 1.4e-14 | 3.6e-14 |
| 1 | float32 storage, float64 math | yes | 0 | 0 | 0 of 0 | 2.2e-07 | 3.8e-07 |
| 1 | float64 storage, float32 math | yes | 0 | 0 | 0 of 0 | 5.7e-06 | 3.3e-05 |
| 10 | float64 storage, float64 math | yes | 0 | 0 | 0 of 0 | 2.1e-14 | 3.6e-14 |
| 10 | float32 storage, float64 math | yes | 0 | 0 | 0 of 0 | 1.4e-07 | 3.8e-07 |
| 10 | float64 storage, float32 math | yes | 0 | 0 | 0 of 0 | 8.5e-06 | 2.8e-05 |
| 50 | float64 storage, float64 math | yes | 0 | 0 | 27 of 27 | 1.4e-14 | 5.7e-14 |
| 50 | float32 storage, float64 math | yes | 0 | 0 | 27 of 27 | 2.2e-07 | 2.6e-07 |
| 50 | float64 storage, float32 math | yes | 0 | 0 | 27 of 27 | 7.3e-06 | 3.2e-05 |

At the 50-course basis the smallest absolute relatedness margin was 0.0307 percentage points and the smallest near-duplicate margin was 0.135 percentage points. The float32 math overlap deltas in the table lie from 2.8e-5 to 3.3e-5 percentage points. The observed deltas stayed below both margins, and no sampled candidate crossed a threshold, changed membership, changed order or changed a derived flag.

That is a sampled classification on the fixed pools, not a guarantee for every input. No bitwise equality is claimed. Float32 storage and arithmetic are behavior-altering evidence only, not a lossless default.

The float64 leg's successful-case gate required the retained set, the order and the exact tie pairs. Derived-flag changes and exclusion-reason changes were recorded in every comparison and were empty on all three bases, so they are evidence rather than a hard gate.

## The normalized lexical projection

The projection pre-normalizes both official names and the code per course and module version, so a query does not repeat that normalization. It covers 11,086 represented courses and 9,901 eligible module versions.

### Shallow and retained size

The first recorded size was 5,092,095 bytes, 5.09 MB. It summed only `group_id`, `code`, `name_fi` and `name_en` per entry with `sys.getsizeof`. It excluded the three normalized strings that the projection adds, container and dataclass overhead, and it therefore understates the retained projection. It was not a measured full retention.

The later object-graph measurement counts each shared object once.

| Measure | Bytes | MB |
|---|---:|---:|
| Course projection | 12,440,135 | 12.4 |
| Module projection | 10,101,721 | 10.1 |
| Combined, shared strings once | 22,541,016 | 22.5 |
| Title token structures and their strings | 11,511,607 | 11.5 |
| Course projection strings | 9,341,295 | 9.3 |
| Module projection strings | 7,376,897 | 7.4 |

The title token structures are 51.1 percent of the combined graph and sit inside the course projection, so the rows do not add. The measured fuzzy call derives title tokens inside the product scorer, so these bytes are retained projection payload and not a measured tokenization saving. A pre-tokenized matcher would be their consumer, and that saving is unmeasured.

The build ran with the source rows and the catalogue report resident.

| Measure relative to the post-setup baseline | Bytes | MB |
|---|---:|---:|
| Resident growth after the build | 224,198,656 | 224.2 |
| Python-traced growth after the build | 93,182,154 | 93.2 |
| Resident-minus-traced residual | 131,016,502 | 131.0 |
| Peak resident growth | 236,904,448 | 236.9 |

The resident growth includes the source rows, allocator arenas and extension allocations. The Python-traced growth includes the source rows. The residual carries allocator arenas and extension allocations. The recorded process peak was 374.9 MB at the post-cell snapshot, and the whole-process maximum resident size was 424.1 MB after the object-graph accounting.

### Match parity and the corrected reference

Four queries ran under both app languages and both activity scopes, which gives 16 cells per matcher. The queries were a course code, two distinct course codes joined by a space, the fullwidth literal `ＯＨＪＥＬＭＯＩＮＴＩ` and the misspelled literal `tietokanta suunnittlu`.

The first comparison found 14 of 16 cells identical. The two differences were the Finnish active-only cells for the two literal queries. They came from a reference-scope error in the comparison, not from the projection. The reference lookup received the full represented-course list for both activity scopes. That lookup returns a supplied list unchanged and applies the activity scope only when it performs its own read. The reference therefore included inactive courses in the active-only cells while the projection filtered them. The product's unified search reads active-only summaries for that scope.

The correction gave the reference active summaries for the active-only cells and all summaries for the active-inclusive cells. All 16 cells were then identical for exact, substring and fuzzy matching, so 16 of 16 for each matcher. Source-field mismatches were 0. The course projection canonical payload and order matched the catalogue owner, and the module projection canonical payload and order also matched.

### Query timing and token structures

The later timing covered the three lexical methods in the English active-inclusive cells, with one warmup and three recorded samples per cell.

| Measure | Reference wall (s) | Projection wall (s) | Saving |
|---|---:|---:|---|
| First active course code | 0.3926 | 0.3510 | 10.6 percent |
| Two distinct active course codes | 0.4090 | 0.3707 | 9.4 percent |
| Fullwidth literal | 0.3961 | 0.3565 | 10.0 percent |
| Misspelled literal | 0.3989 | 0.3561 | 10.7 percent |

The projection saved 9.4 to 10.7 percent of wall time in those four cells. An earlier timing on four default-language cells measured 4 percent to 18 percent. The two timing sets cover different cells and are not compared.

The difference is consistent with a reference that is recomputed on each call and a projection that reuses stored normalized strings. That is an interpretation of the timing, not a separate measurement.

Module owner facts and order matched. Module matching equality was not measured, because no module matching function was exposed to the comparison.

## Prepared caches

Two measurements retained prepared data in a bounded cache. Neither is the product chunk cache. The product's chunk cache and its retained budget are a separate line of work, described in [Descriptive chunk caching](/docs/experiments/runtime-storage-and-serving/descriptive-chunk-caching.md), and are not a result of these measurements.

### Prepared matrices

Two prepared candidate matrices from the fixed 50-course basis vectors, 31,363,072 and 31,358,976 bytes, or 31.36 MB each, were requested through a bounded cache with a 2 s expiry and six calls per policy. The policies ran sequentially in one process, so allocator state carries between them.

| Bound | Calls | Hits | Misses | Expiries | Evictions | Retained before clear | Resident before and after clear (MB) |
|---|---:|---:|---:|---:|---:|---:|---|
| None | 6 | 0 | 6 | 0 | 0 | 0 bytes | 196.5 to 196.5 |
| 33.6 MB | 6 | 1 | 5 | 1 | 3 | 31,358,976 bytes | 228.0 to 165.5 |
| 134.2 MB | 6 | 2 | 4 | 2 | 0 | 62,722,048 bytes | 259.4 to 196.9 |

A 33.6 MB bound holds one of the two matrices, so a second key evicts the first. A 134.2 MB bound holds both, and expiry removes each after the 2 s window. After clearing the 134.2 MB cache, resident memory fell by 62,488,576 bytes, 62.49 MB, which matches the two held matrices within allocator granularity. The 33.6 MB release is larger than its retained bytes because it follows the no-cache policy in the same process.

The bounds count array bytes. They are experimental accounting bounds, not resident-set sizes and not product budgets. The sequence started `tracemalloc` but recorded no Python-traced value. It records per-call resident memory rather than a post-baseline process peak. Cache Python-allocation retention and a cache-specific process peak are unmeasured.

### Course facts

Each entry was one course's immutable summary, normalized name and code, title tokens and every stored chunk carrier, with the dataset, the embedding configuration, the embedding hub and the exact source identity. No basis profile, eligibility, candidate pool or final compiled tree was cached.

Each policy ran one cold six-call sequence in a fresh process. The four requested courses were the candidates with the most stored chunk rows, ordered by row count and then group identity.

| Key | Chunk rows | Entry graph bytes | MB |
|---|---:|---:|---:|
| A | 25 | 828,510 | 0.83 |
| B | 20 | 663,776 | 0.66 |
| C | 18 | 597,782 | 0.60 |
| D | 16 | 531,942 | 0.53 |

| Bound | Misses | Hits | Expiries | Evictions | Retained graph before clear | Peak RSS (MB) | Post-clear RSS (MB) |
|---|---:|---:|---:|---:|---:|---:|---:|
| None | 6 | 0 | 0 | 0 | 0 bytes | 148.3 | 148.3 |
| 33.6 MB | 5 | 1 | 1 | 0 | 2,622,010 bytes | 159.6 | 159.6 |
| 134.2 MB | 5 | 1 | 1 | 0 | 2,622,010 bytes | 159.9 | 159.9 |

The four entries total 2,622,010 bytes, 2.62 MB, far below the 33.6 MB bound. The 33.6 MB and 134.2 MB bounds are not exercised at the measured per-course payload size and no eviction occurs. Whole-entry arithmetic at the largest measured entry gives 40 entries at 33.6 MB and 161 entries at 134.2 MB. The bounds count object-graph bytes, not resident memory.

A cold miss issued one SQL statement, and a hit issued none. The first A call took 0.203 to 0.214 s, each other cold miss 0.136 to 0.162 s, the hit 0.000 s and the expired A call 0.198 to 0.199 s.

Expiry works on access. Key A expired after the 2 s window and was re-read on the sixth call. The deadlines of B, C and D also passed before that call, and those entries stay retained until their key is requested or the cache clears.

Post-clear resident memory was 15.9 to 16.2 MB above the fresh baseline, while the Python-traced figure returned to about 0.11 MB above it. The no-cache process ended 5.0 MB above its baseline. Entry sizing walks allocate a transient identity set, so a call's resident growth and time include that accounting work. A cache budget must come from the intended entry count, and no eviction cost is measured.

## Direct-prerequisite raw-input reuse

The first comparison used a fixed single-course basis with five candidate ids and five first-pass compilations. The first pass read 63 SQL statements and retained 122 canonical courses, five modules, five inferred reads and 106 equivalence reads. The serialized JSON character count of the retained courses and modules was 424,688. That figure excludes the inferred and equivalence cache entries and is not a UTF-8 byte measure. An additive figure at twice that count is 849,376 characters and has the same scope.

The first pass made no candidate eligible, so the product's official second pass had zero targets. The shared-context and fresh-context official passes both executed zero statements and returned empty lists. Their result digests match trivially, and the comparison did not answer the reuse question. The raw-input retention and read count were measured, and the reuse saving was unmeasured on that basis.

The later comparison used one fixed basis source with five nonempty candidate targets and five compilations. The projection read used five statements.

| Pass | SQL statements | Wall range over recorded samples (s) | Compilations | Output digest |
|---|---:|---|---:|---|
| Shared-context cold | 63 | 0.4568 to 0.5743 | 5 | Identical |
| Shared-context reused | 0 | 0.0582 to 0.0816 | 5 | Identical |
| Fresh-context cold | 63 | 0.4167 to 0.4692 | 5 | Identical |

The three full compilation digests are identical. The reused pass saved all 63 statements, and the fresh pass issued the same 63. The reuse saved about 0.40 to 0.49 s per pass on this basis.

| Retained raw context | Count |
|---|---:|
| Courses | 122 |
| Modules | 5 |
| Inferred reads | 5 |
| Equivalence reads | 106 |
| Retained missing courses | 0 |
| Retained missing modules | 0 |
| Total Python object graph | 889,691 bytes |

The fresh-context graph was 889,636 bytes. The 55-byte difference is not attributed further, and the fact counts are identical. The process peak was 148.86 MB, and the first sample added 13.0 MB over the post-setup baseline. An arithmetic doubling of the retained context is 1,779,382 bytes, and twice the process peak is 297.71 MB. Both are arithmetic, not simultaneous measurements.

The cached values are raw course and module inputs and retained absence. Policy enters the compilation context: `include_inferred`, `active_only`, the retained ids and the caller's selected and completed sets. A dataset-keyed cache of final compilations would be a caller-state or eligibility cache, so final compiled trees are not a safe dataset-only cached fact. Only policy-independent raw source projections are reusable.

## Compression levels

Both payloads decode to identical SHA-256 bytes at every level. Times are wall medians of three recorded samples after one warmup.

| Payload | Bytes | Level 1 | Level 6 | Level 9 |
|---|---:|---|---|---|
| Saved basis-50 report | 152,191 | 39,606 bytes, 0.00148 s | 34,405 bytes, 0.00304 s | 33,662 bytes, 0.00438 s |
| Synthetic report-shaped JSON | 1,274,526 | 135,821 bytes, 0.00703 s | 120,774 bytes, 0.01510 s | 116,275 bytes, 0.03248 s |

The compressed sizes are plotted below.

![Compressed size in bytes at gzip levels 1, 6 and 9 for the saved basis-50 report and the synthetic report-shaped JSON payload. Level 1 is largest and level 9 smallest on both payloads.](/docs/charts/runtime-memory-gzip-size.svg)

Level 1 was the cheapest in CPU. Level 6 reduced size by 13.0 percent on the saved payload and 11.1 percent on the synthetic payload against level 1, at about 2.1 times the CPU. Level 9 reduced a further 2.2 and 3.7 percent against level 6, at 1.4 and 2.2 times the CPU of level 6. The measurement supports level 6 as the size and CPU compromise on both payloads.

The product compresses responses of at least 500 bytes at level 6, through the middleware that [Web server](/docs/backend/interfaces/web-server.md) describes. The measurement covers already-serialized bytes only. It excludes report serialization, HTTP transfer and the event-loop middleware path, so no HTTP performance claim follows.

## Settings, connections and serialization in context

The read sits inside a wider composition. A separate measurement resolved the dataset through its named receipt, created an engine, checked the schema head, read summaries and chunks, prepared arrays, scored and serialized the report. It ran fresh, reused and prepared modes on the same three pools.

Recorded wall medians, seconds. The outer total is measured directly. Stage values are nested segments and are not additive independent timings.

| Basis | Fresh | Reused | Prepared |
|---:|---:|---:|---:|
| 1 | 0.1868 | 0.1207 | 0.0526 |
| 10 | 1.5798 | 1.5215 | 0.7880 |
| 50 | 10.5724 | 10.7306 | 6.6311 |

Reused against fresh changed the measured composition by -35.37, -3.69 and +1.50 percent. Prepared against fresh changed it by -71.83, -50.12 and -37.28 percent. Engine reuse alone is not a consistent saving on this pool.

The following stage breakdown is for the 50-course basis, in wall seconds.

| Segment | Fresh | Reused | Prepared |
|---|---:|---:|---:|
| Named receipt and settings resolution | 0.0063 | 0.0063 | not run |
| Engine creation | 0.0004 | outside samples | not run |
| First connect and schema head | 0.0233 | outside samples | not run |
| Summary read | 0.2402 | 0.2328 | not run |
| Basis chunk read | 0.0756 | 0.0706 | not run |
| Candidate chunk read | 4.0299 | 3.9531 | not run |
| Engine disposal | 0.0004 | outside samples | not run |
| Preparation | 0.0011 | 0.0011 | 0.2133 |
| Scoring | 6.1915 | 6.4572 | 6.4137 |
| Serialization | 0.0041 | 0.0041 | 0.0040 |
| Total | 10.5724 | 10.7306 | 6.6311 |

Resolution, engine creation, the head check and disposal stay in the millisecond range. Serialization stayed at or below 4.1 ms on every basis, and it covers the report model dump and JSON encoding. It excludes the serving identity wrapper, and no HTTP request ran. The candidate chunk read and the scorer carry most of the composed time at bases 10 and 50.

| Basis | Fresh peak (MB) | Reused peak (MB) | Prepared peak (MB) |
|---:|---:|---:|---:|
| 1 | 134.2 | 134.1 | 121.9 |
| 10 | 370.5 | 371.3 | 371.9 |
| 50 | 1,187.0 | 1,186.9 | 1,187.0 |

The 50-course basis processes peaked at about 1,187 MB in all three modes, inside the 2.147 GB address-space limit. The peak is process-wide.

Fresh processes opened four connections, reused processes one and prepared processes none. Every connection reported a read-only transaction and a 30 s statement timeout. Every read rolled back, and no write was attempted. Prepared mode's preparation took 0.0024, 0.0674 and 0.2133 s. It reconstitutes saved carriers, then scores and serializes without database I/O. It is experiment-local reuse, not a product cache, pool or invalidation policy.

Helper import and capture decode are setup, not composition. Helper import took 0.058 to 0.077 s per process. Capture decode and fixed-input verification took 0.34 to 0.35 s for basis 1, 3.24 to 3.27 s for basis 10 and 13.82 to 14.39 s for basis 50. Named-receipt resolution in setup took 0.0112 to 0.0118 s. The reused engine setup took 0.095 to 0.101 s for creation and 0.029 to 0.031 s for the first connection and head check. The cheap operations measured 0.0058 to 0.0061 s for receipt resolution, 0.0002 s for engine creation and disposal, and 0.0013 to 0.0014 s for the live selected-pointer metadata read.

These values come from a different sample set from the read and array measurements. They do not add to them.

## Failed attempts and corrections

| Set | Process | Failure | Correction | Outcome |
|---|---|---|---|---|
| Memory | Imports | `KeyError: 'rss_after_bytes'` | Compared the first record with the initial resident snapshot | Recorded, and only the imports case changed |
| Memory | Lexical | `AttributeError: 'CourseSummary' object has no attribute 'summary'` | Read `group_id` for the exact and substring results | Recorded, and only the lexical case changed |
| Memory | Reads 1 | `InputMismatch: the full basis read differs from the saved carriers` | The saved basis digest covers the filtered set while the saved candidate digest is unfiltered. The fix compared the filtered basis read with the saved digest and kept the unfiltered read for memory | Reads 1 was rerun, and reads 10 and 50 ran on the fixed code |
| Composition | First attempt | Resolved a different selected dataset identity and stopped before a connection | Pinned the capture through its named receipt | Nine-cell matrix completed |
| Composition | Recovery basis 1 fresh | The candidate descriptive read digest differed from the saved carrier digest | The saved candidate carriers include name chunks while the descriptive read projects content and outcomes only. The fix compared the descriptive read with the descriptive fields and kept the full digests as identity evidence | Rerun recorded |
| Pool setup | Basis 50 capture | `MemoryError` while serializing the fixed input at 1,399.3 MB | Wrote JSON in bounded chunks and took the digest from the exact-file write | The first recovery capture supplied the pool |

Sixteen processes ran in the memory set: one setup, 12 measurement processes and three corrections. No process was killed by the outer limit and no sample timer fired. The largest peak was 1,305.6 MB and the longest process 82.50 s. The matched comparison ran seven processes, none failed and no correction ran. The composition set ran a first attempt that stopped on a dataset identity mismatch, then nine recovery measurement processes, one of which failed on a readback comparison. One read-only diagnostic process and one corrected rerun followed. No process exceeded 180 s, no sample exceeded 60 s and no process exceeded the 2.147 GB address-space limit.

No failed process was retried without a diagnosed defect.

| Earlier record | Correction | Result that stands |
|---|---|---|
| The first projection size was 5.09 MB | The sum covered four strings per entry and omitted three normalized strings, containers and dataclass overhead | The full object graph is 22.5 MB, 12.4 MB for courses plus 10.1 MB for modules with shared strings once |
| 14 of 16 lexical cells were identical, with two non-identical cells | The reference received an unscoped course list in the active-only cells | The corrected comparison gives 16 of 16 for exact, substring and fuzzy, so the two earlier differences were a reference-scope error in the comparison |
| The 753.2 MB process peak was read as the full-read baseline for 171.5 MB | That peak belongs to an earlier full candidate read of 11,405 rows from a 139.8 MB baseline. The matched materialized leg reads 7,657 descriptive rows from a 113.7 MB baseline | The paired result is 546.9 to 171.5 MB, a 375.4 MB lowering |
| The 33.6 and 134.2 MB cache bounds were read as product budgets | Matrix bounds count array bytes, while the separate course-facts cache counts object-graph bytes | The smaller matrix bound holds one matrix and evicts when the second key is read. The larger holds both. Neither bound is exercised by the four course facts of 0.53 to 0.83 MB, which cause no eviction. |
| The direct-prerequisite reuse comparison had zero eligible targets | Both official passes ran zero statements and returned empty lists, so the digests match trivially | The later nonempty comparison removes all 63 statements, keeps the compilation digest and retains 0.89 MB of raw facts |

## What the evidence supports

The observation is that the full carrier read is the dominant client memory cost in this line. At the 50-course basis it added 233.9 MB and set a 753.2 MB process peak. The descriptive read added 18.7 MB, and the streamed read held a 31.36 MB matrix and one partition.

The observation is that the matched bounded read reproduces the product result on the fixed pool. It returned 319 of 319 results with no membership, order, value or flag change and all 27 exact tie pairs, at a 171.5 MB peak against 546.9 MB. The measured cost was about 2 s per recorded sample, or 17 to 20 percent slower.

The observation is that float32 halves the array bytes on every basis, and that the sampled float32 deltas stayed below the measured margins. The interpretation is that this is behavior-altering evidence and not a lossless default, because a threshold could flip on another input.

The observation is that the normalized projection holds 22.5 MB of object graph, of which 11.5 MB is title token structures, and that the corrected comparison matched all 16 cells for each matcher. The timing observation is 9.4 to 10.7 percent of wall time in four English active-inclusive cells.

The observation is that the four measured course facts are 0.53 to 0.83 MB each, and that the 33.6 and 134.2 MB bounds were not exercised. The observation is that reused raw context removed all 63 compile statements and reproduced the compilation digest with 0.89 MB of retained facts on one basis.

The observation is that gzip level 6 reduced size by 13.0 and 11.1 percent against level 1 at about 2.1 times the CPU, and that level 9 reduced a further 2.2 and 3.7 percent at 1.4 and 2.2 times the CPU of level 6. Every level decoded to identical bytes. This is a compression result, not an HTTP result.

## Where the line ended

The matched comparison drew no product memory budget, cache budget or float32 promotion. It left the memory bound open for a later selection. The projection and the two prepared caches stayed experimental. No product, schema, model or configuration change was made in the matched run.

The product's chunk cache and its retained budget are a separate line of work and are not a result of these measurements. Worker and concurrency settings stayed untuned.

The memory result that stands is the pair 546.9 to 171.5 MB, with exact product parity and a cost of about 2 s per sample. The full-read result that stands is 233.9 MB of carrier growth and a 753.2 MB peak in its own sequence. The projection result that stands is 22.5 MB of object graph and 16 of 16 cells for each matcher. The reuse result that stands is 63 statements removed and an identical compilation digest on one basis.

## Limitations

- The pools are fixed captured outputs on one pinned dataset. The line makes no full-catalogue, retrieval, semantic-quality, whole-request or HTTP claim.
- Process resident memory is process-wide. It includes the interpreter, libraries, capture decoding, earlier sequences and allocator arenas. Array bytes, object-graph bytes and resident memory are reported separately and are not interchangeable.
- Read and array timings are single recorded passes after one warmup. They do not replace the paired read timing of the recommendation line.
- The full-row equality of the streamed read is recorded but not a code-enforced assertion. A skipped non-descriptive row would not fail it.
- The fixed basis has no all-row digest. The bounded leg's basis all-row count and digest are recorded observations, not a fixed check.
- The two read legs ran in separate processes. Their match rests on identical ordered output and carrier digests and exact product-reference parity.
- Warmup sets the process high-water mark, so the per-sample peak excess is masked. The warmup growth and the per-sample resident deltas are the evidence.
- Float32 is sampled on fixed pools. The margins are 0.0307 and 0.135 percentage points. There is no guarantee for other inputs and no bitwise equality.
- The projection bytes are a `sys.getsizeof` object-graph estimate. A dict-backed projection adds per-instance bytes.
- The lexical resident delta includes the represented summaries, the catalogue report and temporary build objects. The process peak of 374.9 MB is the post-cell `VmHWM`, and the whole-process maximum resident size is 424.1 MB.
- The recorded residual description listed the source rows with the residual. Those rows sit inside the Python-traced growth. The measured values are unaffected.
- The projection timing covers the three lexical methods in four cells. It excludes database reads and HTTP. Module matching equality is unmeasured.
- The cache bounds count array bytes or object-graph bytes, not resident memory. They are not product budgets. Neither bound is exercised at the measured per-course payload, and no eviction cost is measured.
- Cache expiry works on access. Expired entries stay retained until requested or cleared. Entry sizing adds a transient identity set to each call.
- The prepared composition is experiment-local reuse. It creates no product cache, pool or invalidation policy.
- The direct-prerequisite reuse comparison uses one fixed basis course and one candidate projection, with a warm database cache. It covers five targets and one basis.
- The dataset was pinned through a named receipt rather than the selected-dataset pointer, so resolution cost differs from the product's resolution.
- The 50-course pool came from a recovery capture whose earlier serialization raised `MemoryError`, with the timer deviation stated in [Setup details](#setup-details).
- The array case loaded the configured hub vectors for preparation shape and timing without an identity comparison. Its byte figures do not depend on hub values.
- The setup stage read saved capture files, a saved enforcement probe, a free-memory reading and an installed dependency version, so it did not run without input-file access.
- No container, fixture, model, embedding, inference, worker, administration or product service ran. No global cache or kernel tuning occurred.
- The composition excludes the serving identity wrapper and response delivery. Only the product scorer ran, with no centroid, NumPy or alternative scoring variant.

## Setup details

| Item | Value |
|---|---|
| Hardware | 4-core aarch64 server, 23.6 GB of RAM |
| Python | 3.14.3 |
| NumPy | 2.4.6 |
| Vectors | Stored BGE-M3 embeddings with 1,024 components, and no embedding model ran |
| Thread limits | `OPENBLAS_NUM_THREADS=1`, `OMP_NUM_THREADS=1`, `MKL_NUM_THREADS=1`, `BLIS_NUM_THREADS=1` and `VECLIB_MAXIMUM_THREADS=1` |
| SQL policy | Read-only transaction with a 30 s statement timeout |
| Address-space limit | 2.147 GB (2,147,483,648 bytes), verified in every process |
| Process limit | 180 s |
| Sample limit | One fatal 60 s timer per whole sample |
| Dataset | Pinned through its named receipt, with the schema head required and the selected-dataset pointer not resolved |
| Catalogue | 11,086 represented courses, 4,543 active, and 9,901 eligible module versions |
| Headroom | 10.4 to 10.6 GB in the memory set and 10.28 to 10.39 GB in the matched set, both against a 3.22 GB requirement |

The memory and composition sets used a disposable environment that exposed NumPy and the project packages read-only. The matched set used the repository environment. No package install or upgrade ran, and the product environment, dependencies and configuration were not modified.

Each process ran alone after a free-memory check. The memory set's 60 s sample timer enclosed the number variants and reference, the lexical timing loop, the gzip samples and every reads sequence. The array stages, the cache six-call sequence and the prerequisite passes ran without an in-process timer. Their longest recorded stage was 0.107 s for arrays, 0.376 s for the prerequisite first pass, and the cache process took 14.03 s including 12.6 s of expiry sleeps. The composition set used one fatal 60 s timer per sample that enclosed serialization and was not reset for individual stages. Its longest recorded sample was 10.73 s, its longest warmup sample 10.88 s and its longest process 62.49 s.

The 50-course pool uses the first recovery capture. The first capture attempt completed the product command and then raised `MemoryError` while serializing the fixed input at a 1,399.3 MB process peak. The recovery used one fatal 60 s timer around the product command and a separate fatal 60 s timer around capture serialization, where one cumulative 60 s timer through serialization was intended. The command timer ended before the scorer-only repetitions and capture assembly, and the serialization timer started afterwards. The 180 s process limit and the 2.147 GB address-space limit held, and no cumulative-cap pass is claimed.

## Untested questions

Each question below is untested.

- Whether the float32 deltas stay below the 0.0307 and 0.135 percentage-point margins on other pools, other languages or other query inputs.
- Whether a pre-tokenized matcher consumes the 11.5 MB title token graph and saves query time.
- Whether a cache budget based on an intended entry count evicts under load, and what that eviction costs.
