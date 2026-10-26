# Recommendation vectorization and narrow reads

This report measures formula-preserving NumPy scoring, descriptive-only projected reads and centroid coverage against the chunk-pair baseline on three fixed recommendation pools.

**Evidence status:** Comparative. **Run date:** 21 October 2026.

## The question

The recommendation scorer turns chunk vectors into relatedness and coverage meters. Relatedness is the hub-centred cosine between the candidate course point, the unit mean of the candidate's centred chunk vectors, and the trimmed basis profile, reported as a percentage, as [Coverage and ranking](/docs/backend/search-and-discovery/coverage-and-ranking.md) defines it. Coverage is the character-weighted share of the candidate's descriptive text that has a close match in the basis. The coverage pools Finnish and English chunks together. The score is relatedness with the configured overlap penalty applied.

Two changes were measured one at a time and then together. The first replaces the scalar scorer with a float64 NumPy scorer that evaluates the same formula. The second replaces the all-field chunk read and its Python filter with a projected read that selects only content and outcomes rows in SQL. The measurements also ask whether centroid coverage adds runtime value after both changes. Centroid coverage replaces the chunk-pair coverage step with one centroid vector per course, the unit mean of its hub-centred chunk vectors.

Formula-preserving has a precise meaning here. The same inputs must return the same retained courses in the same order, with the same adjacent exact ties, the same median-trim membership, the same exclusion outcomes, the same derived flags and no missing chunk or profile. The numeric meters may differ in their last binary digits, because float64 array arithmetic and the scalar path accumulate in a different order. No tolerance was applied, no delta was rounded away and no bitwise equality is claimed.

The measurements compare scorers and reads on fixed pools. They do not measure retrieval quality, semantic correctness or a full HTTP request. A rank, value or membership match does not establish semantic correctness.

The near-duplicate test excludes a candidate whose strongest single-course overlap reaches `RECOMMENDATION_NEAR_DUPLICATE_PERCENT`, here 90 percent. The relatedness floor excludes a candidate below `RECOMMENDATION_MIN_RELATEDNESS`, here 0.33. With `RECOMMENDATION_OVERLAP_PENALTY_WEIGHT=0.0`, the score equals relatedness.

## Fixed pools

All measurements reused one fixed selection on one captured catalogue. The selection seed was 20261021. It fixed 200 stored active course identities with a compatible descriptive chunk, resolved their representative versions once, and took the first 50 compatible representatives in shortlist order. The one-course and 10-course bases are prefixes of that order. A pool is the ranked candidate set that the product's retrieval produced for one basis. The candidate pools are the product's saved retrieval and eligibility outputs. No extraction, selection, approximate nearest-neighbor retrieval (ANN) or pool variant ran for these measurements.

| Basis | Basis chunk rows | Ranked candidates | Retained by product | Candidate chunk rows |
|---|---:|---:|---:|---:|
| 1 | 2 | 42 | 37 | 137 |
| 10 | 39 | 435 | 69 | 1,771 |
| 50 | 209 | 1,874 | 319 | 7,657 |

The 50-course basis comes from the recovery capture that followed the failed attempt, and it carries the timer deviation stated below. The first attempt completed the product command and then raised `MemoryError` while saving its input under the 2.147 GB address-space limit, with a process peak of 1,399.3 MB. The attempt was not retried. The recovery capture supplied the pool, using a separate fatal 60 s timer for the product command and for serialization, where the intended boundary was one cumulative timer through serialization. No further recovery attempt ran.

The fixed request used `basis=completed`, `mode=all`, `display_language=en`, `include_inferred=false` and `active_only=true`, with the selected set equal to the completed set equal to each basis. The configured policy was `RECOMMENDATION_CHUNK_TOP_K=40`, `RECOMMENDATION_MIN_RELATEDNESS=0.33`, `RECOMMENDATION_NEAR_DUPLICATE_PERCENT=90`, `RECOMMENDATION_OVERLAP_PENALTY_WEIGHT=0.0`, `COMPARISON_OVERLAP_FLOOR=0.20` and `COMPARISON_OVERLAP_CEILING=0.90`. The search settings, embedding configuration, embedding hub and outcomes hub were pinned by digest before scoring and composition.

The captured catalogue holds teaching text in Finnish and English. The chunk rows are the descriptive content and outcomes chunks in both languages. Every basis course has a compatible descriptive chunk, and no candidate in the pools lacks chunks or a profile. The vectors are stored BGE-M3 embeddings with 1,024 components, so no embedding model ran during the measurements.

## Variants and timing boundaries

Three measurement families share the fixed pools but not their timing boundaries. The scorer-only process compared the product scalar scorer, the centroid coverage scorer and a float64 NumPy chunk scorer. The centroid scorer in that process was the Python implementation of the approximation. The read-only process compared the product chunk read with a descriptive-only projected read. The composition process compared two vectorized implementations, A with chunk-pair coverage and B with centroid coverage, on the same fresh read strategy.

| Measurement | Variants | Timer covers | Timer excludes |
|---|---|---|---|
| Scorer-only | Product scalar scorer, centroid scorer, float64 NumPy chunk scorer | Conversion, hub subtraction, unit normalization, course points, median trim, candidate loop conversion, matrix products, threshold arithmetic, result construction and sort | Capture loading, carrier construction, output dumps, JSON serialization, diagnostics, hashing and disk work |
| Read-only | Product full chunk read with Python field filtering, projected read with the field predicate | Both repository reads and the product leg's Python filtering | Next-course read, ANN retrieval, scoring, HTTP serving and connection startup |
| Composition | A chunk-pair float64 NumPy leg, B vectorized centroid float64 NumPy leg | Resolution, fresh engine, head check, summaries, projected reads, preparation, scoring, report construction, disposal and serialization | ANN, next-course read, capture observers, hashing, serving identity wrapper, response delivery and HTTP |

The scorer-only process called product, centroid and NumPy sequentially on identical captured inputs, inside one fatal 60 s timer. The fixed call order was product, centroid, then NumPy, so cache warmth may favor the later calls. The product and centroid calls started from the same raw carriers, settings and output type, so their preparation and result construction lay inside their timers. The NumPy primary timer included its basis conversion, hub subtraction, unit normalization, course points, median trim, candidate loop conversion, matrix products, threshold arithmetic, result construction and sort. Its basis and profile preparation took 0.0005 to 0.0127 s per sample and its candidate array work 0.0090 to 0.5171 s, both inside the primary timer.

The read-only process ran the product read on the captured representatives, filtered the result to `content` and `outcomes` in Python, then ran the projected read with that field predicate in SQL. One fatal 60 s timer enclosed both legs.

The composition process measured one complete leg at a time for each algorithm. Each leg resolved the dataset receipt and settings, created a fresh engine and session factory, checked the schema head on its first connection, read summaries and descriptive chunks, prepared its own arrays, scored, serialized and returned its carriers. No engine, connection, matrix or centroid was shared between legs. Each leg charged its array preparation and allocation inside its own timer, and no matrix or centroid was prepared outside it. A used the product chunk-pair formula. B computed centroid coverage with float64 NumPy and did not call the scalar centroid scorer, so the comparison is between two vectorized implementations with the same read strategy.

Composition used one paired warmup and three recorded pairs. The warmup order was chunk then centroid. The recorded orders were chunk then centroid, centroid then chunk, chunk then centroid. The warmup pair is excluded from the recorded medians, and its readback carriers were discarded. Database and CPU cache warmth is uncontrolled, and the alternating order balances a fixed first position across the three recorded pairs.

Scoring and reads each ran one warmup and three recorded pairs per basis. Each paired sample ran below the fatal 60 s timer, and every process ran below 180 s and the 2.147 GB address-space limit.

The dtype is float64. Work is bounded to one candidate against the fixed basis at a time, with no candidate chunk discarded. The chunk-pair count is an upper bound because a candidate below the relatedness floor never reaches the coverage products.

| Basis | Basis matrix | Course matrix | Largest candidate matrix | Candidate chunk rows | Chunk-pair upper bound |
|---|---|---|---:|---:|---:|
| 1 | 2 by 1024 | 1 by 1024 | 6 by 2 | 137 | 274 |
| 10 | 39 by 1024 | 10 by 1024 | 10 by 39 | 1,771 | 69,069 |
| 50 | 209 by 1024 | 50 by 1024 | 23 by 209 | 7,657 | 1,600,313 |

## Scorer-only results

The product scorer reproduced the saved product result set and values exactly on all three bases, with 37, 69 and 319 ordered results. The centroid scorer reproduced the saved centroid result set and values exactly on all three bases, including the 311-result 50-course output with its eight removals and 253 rank changes against the product.

Each process ran one warmup, excluded from the medians. Only the centroid warmup values were recorded.

| Basis | Product samples (s) | Centroid warmup (s) | Centroid samples (s) | NumPy samples (s) |
|---:|---|---|---|---|
| 1 | 0.047290, 0.048221, 0.047667 | 0.045158 | 0.045379, 0.047442, 0.045232 | 0.010129, 0.010639, 0.010033 |
| 10 | 0.743603, 0.754062, 0.768027 | 0.597809 | 0.605629, 0.605267, 0.608107 | 0.102998, 0.103500, 0.103783 |
| 50 | 6.268246, 6.570340, 6.950881 | 2.710192 | 2.706332, 2.703793, 2.701002 | 0.537343, 0.540319, 0.537979 |

Recorded wall medians.

| Basis | Product (s) | Centroid (s) | NumPy (s) | NumPy saving | Centroid saving |
|---:|---:|---:|---:|---|---|
| 1 | 0.047667 | 0.045379 | 0.010129 | 78.75 percent, 0.037538 s | 4.80 percent, 0.002288 s |
| 10 | 0.754062 | 0.605629 | 0.103500 | 86.27 percent, 0.650562 s | 19.68 percent, 0.148432 s |
| 50 | 6.570340 | 2.703793 | 0.537979 | 91.81 percent, 6.032361 s | 58.85 percent, 3.866547 s |

Recorded CPU medians.

| Basis | Product CPU (s) | Centroid CPU (s) | NumPy CPU (s) | NumPy saving | Centroid saving |
|---:|---:|---:|---:|---|---|
| 1 | 0.047425 | 0.045155 | 0.010099 | 78.70 percent, 0.037325 s | 4.79 percent, 0.002269 s |
| 10 | 0.752317 | 0.603801 | 0.103206 | 86.28 percent, 0.649111 s | 19.74 percent, 0.148516 s |
| 50 | 6.556544 | 2.692972 | 0.536910 | 91.81 percent, 6.019633 s | 58.93 percent, 3.863571 s |

NumPy lowered the wall median by 78.75 percent on the one-course basis, 86.27 percent on the 10-course basis and 91.81 percent on the 50-course basis. The centroid scorer lowered it by 4.80, 19.68 and 58.85 percent. CPU medians agree within 0.1 percentage point. The savings include array preparation and allocation, so they are not a comparison of matrix multiplication alone. The two wall-median savings series are plotted below.

![Wall-median saving against the product scorer for the float64 NumPy chunk scorer and the centroid coverage scorer on the three fixed pools, where the NumPy scorer saves more on every pool.](/docs/charts/recommendation-vectorization-scorer-savings.svg)

These are scorer-only measurements. They exclude capture loading, output dumps, JSON serialization, diagnostics, hashing and disk work equally from the three timers. They are not whole-request or HTTP latency.

## Numerical preservation

The NumPy scorer returned the product retained set and the product order on all three bases. No rank changed, no course was added or removed, and no derived flag changed. The numeric meters differ in their last binary digits.

| Basis | Common results | Relatedness values changed | Score values changed | Overlap values changed | Exactly equal values | Largest relatedness delta | Largest score delta | Largest overlap delta |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 37 | 15 | 15 | 21 | 60 of 111 | 1.42e-14 | 1.42e-14 | 3.55e-14 |
| 10 | 69 | 45 | 45 | 38 | 79 of 207 | 2.13e-14 | 2.13e-14 | 3.55e-14 |
| 50 | 319 | 179 | 179 | 161 | 438 of 957 | 1.42e-14 | 1.42e-14 | 5.68e-14 |

The exact nonzero relatedness and score deltas on the 50-course basis lie from -1.42e-14 to 1.42e-14, and the overlap deltas from -4.26e-14 to 5.68e-14. Every per-course value and delta is recorded. No tolerance was applied, and no nonzero delta was treated as zero.

Retained set, order and flags. Every candidate keeps the same retained or excluded outcome. Exclusion reasons for candidates excluded under both variants were not recomputed per candidate, so a reason change at the same excluded outcome is not measured. The saved product exclusion counts are five, 366 and 1,532 candidates below the relatedness floor, zero, zero and 23 near duplicates, and no missing chunk or missing profile.

Median trim. Membership was identical on all three bases, with one, five and 25 profile courses kept and the same course order.

Ties. The 50-course basis has 27 adjacent exact tie pairs covering 41 courses. The NumPy output has the same 27 pairs in the same order, so the exact tie structure and the name and code tie order are preserved. The one-course and 10-course bases have no adjacent exact tie pairs.

Thresholds. No candidate changed its retained or excluded outcome, so no threshold change altered the result set. The last-bit differences changed no rank, tie or derived flag.

Byte equality. The chunk output in the composition run did not match the saved product serialization digest. It differed only in the last binary digits of the numeric meters, so the bytes differ where the values differ.

## Narrow read results

| Basis | Product read samples (s) | Projected read samples (s) |
|---:|---|---|
| 1 | 0.076093, 0.077127, 0.076136 | 0.051742, 0.051826, 0.051551 |
| 10 | 1.030745, 1.029408, 1.039759 | 0.715631, 0.714826, 0.721176 |
| 50 | 5.356020, 5.315186, 5.278223 | 3.904262, 3.916760, 4.019332 |

| Basis | Product read wall median (s) | Projected read wall median (s) | Wall saving | Product read CPU median (s) | Projected read CPU median (s) | CPU saving |
|---:|---:|---:|---|---:|---:|---|
| 1 | 0.076136 | 0.051742 | 32.04 percent, 0.024394 s | 0.058361 | 0.037942 | 34.99 percent, 0.020420 s |
| 10 | 1.030745 | 0.715631 | 30.57 percent, 0.315114 s | 0.712520 | 0.451590 | 36.62 percent, 0.260930 s |
| 50 | 5.315186 | 3.916760 | 26.31 percent, 1.398427 s | 2.985184 | 1.940183 | 35.01 percent, 1.045002 s |

The projected read lowered the paired read wall median by 32.04 percent on the one-course basis, 30.57 percent on the 10-course basis and 26.31 percent on the 50-course basis. The CPU median fell by 34.99, 36.62 and 35.01 percent. The timer covers both repository reads and the product leg's Python field filtering. It excludes the next-course read, ANN retrieval, scoring, HTTP serving and connection startup. The wall-median and CPU-median savings are plotted below.

![Wall-median and CPU-median saving for the descriptive-only projected read against the product chunk read on the three fixed pools, where the CPU saving exceeds the wall saving on every pool.](/docs/charts/recommendation-vectorization-narrow-read-savings.svg)

The read returned the same descriptive carriers. The full row counts include name rows, which the projected read does not request.

| Basis | Basis descriptive carriers | Basis full rows | Candidate descriptive carriers | Candidate full rows |
|---:|---:|---:|---:|---:|
| 1 | 2 | 4 | 137 | 221 |
| 10 | 39 | 59 | 1,771 | 2,641 |
| 50 | 209 | 309 | 7,657 | 11,405 |

The complete ordered carrier tuples, including every embedding component, were identical between the product filtered read and the projected read on every recorded sample for both requests. The requested triples and counts matched, and the product read reproduced the saved capture and its full-row digests. No carrier value, order, metadata field or group field differed.

Each reads process opened one database connection. Every connection reported `default_transaction_read_only=on` and `statement_timeout=30s`. No write was attempted, and each process recorded 16 rollback events.

## Combined composition

A and B used the same fixed pools, the same projected reads and the same fresh-read strategy. A computes chunk-pair coverage with float64 NumPy. B computes centroid coverage with float64 NumPy over the same course centroids. Only the coverage step differs.

Recorded wall medians. Each leg total is measured directly. Nested segments share the leg total and are not additive independent timings. The pair total is recorded separately as an outer value.

| Basis | Chunk total (s) | Centroid total (s) | Chunk scoring (s) | Centroid scoring (s) | Pair total (s) |
|---:|---:|---:|---:|---:|---:|
| 1 | 0.144528 | 0.142583 | 0.010487 | 0.007827 | 0.449186 |
| 10 | 0.960810 | 0.954318 | 0.104383 | 0.102374 | 2.157925 |
| 50 | 4.968174 | 5.010143 | 0.551602 | 0.572786 | 10.560117 |

The centroid leg is 1.35 percent faster on the one-course basis, 0.68 percent faster on the 10-course basis and 0.84 percent slower on the 50-course basis. Those differences are 0.0019, 0.0065 and 0.0420 s of recorded wall median, below one percent of the pair and inside run noise. Neither leg total shows a meaningful centroid saving. The centroid scorer is 0.0027 s faster on the one-course basis, 0.0020 s faster on the 10-course basis and 0.0212 s slower on the 50-course basis.

Recorded CPU medians.

| Basis | Chunk total CPU (s) | Centroid total CPU (s) | Chunk scoring CPU (s) | Centroid scoring CPU (s) | Pair total CPU (s) |
|---:|---:|---:|---:|---:|---:|
| 1 | 0.107693 | 0.105979 | 0.010428 | 0.007786 | 0.374865 |
| 10 | 0.638805 | 0.636571 | 0.103899 | 0.101822 | 1.516058 |
| 50 | 2.743147 | 2.778918 | 0.549172 | 0.571234 | 6.117283 |

Nested array work, wall medians. The values lie inside the leg totals above.

| Basis | Chunk preparation (s) | Chunk candidate arrays (s) | Centroid preparation (s) | Centroid candidate arrays (s) | Centroid coverage (s) |
|---:|---:|---:|---:|---:|---:|
| 1 | 0.000546 | 0.009266 | 0.000541 | 0.006698 | 0.000107 |
| 10 | 0.003113 | 0.099280 | 0.003205 | 0.095866 | 0.000931 |
| 50 | 0.013793 | 0.527946 | 0.013874 | 0.539416 | 0.011950 |

The centroid coverage step itself took 0.000107, 0.000931 and 0.011950 s. B computes the coverage matrix for every candidate with chunks, including candidates that the relatedness floor later excludes, while A computes coverage only after its relatedness check. That difference is part of the measured B implementation.

Shared read and stage medians, wall seconds. The two algorithms run the same read code, so their columns differ only through fresh-engine and cache timing.

| Basis | Algorithm | Resolution | Engine | Head check | Summaries | Basis read | Candidate read | Disposal | Serialization |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | chunk | 0.006275 | 0.000418 | 0.023254 | 0.049432 | 0.006569 | 0.048177 | 0.000320 | 0.000488 |
| 1 | centroid | 0.006323 | 0.000416 | 0.022689 | 0.048424 | 0.006750 | 0.048475 | 0.000324 | 0.000498 |
| 10 | chunk | 0.006449 | 0.000424 | 0.022893 | 0.094604 | 0.018765 | 0.714772 | 0.000322 | 0.000899 |
| 10 | centroid | 0.006382 | 0.000405 | 0.022405 | 0.091547 | 0.018739 | 0.712456 | 0.000329 | 0.000906 |
| 50 | chunk | 0.006685 | 0.000423 | 0.023525 | 0.258807 | 0.077128 | 4.047336 | 0.000357 | 0.003957 |
| 50 | centroid | 0.006507 | 0.000450 | 0.024047 | 0.260822 | 0.076171 | 4.058367 | 0.000347 | 0.003814 |

The candidate chunk read dominates the chunk leg at 4.05 s of its 4.97 s on the 50-course basis. Resolution, engine creation, the head check and disposal lie in the millisecond range, and serialization lies at or below 4.1 ms. The warmup pair totals, which include both readbacks, were 0.6897, 4.3000 and 19.6440 s. They are not part of the recorded medians. The two whole-leg wall medians are plotted below.

![Whole-leg wall medians for the chunk-pair composition and the vectorized centroid composition on the three fixed pools, where the two legs lie within one percent of each other.](/docs/charts/recommendation-vectorization-composition-legs.svg)

The Python centroid scorer cost 2.7038 s on the 50-course basis against 6.5703 s for the product scorer, while the vectorized chunk scorer cost 0.5380 s. The centroid variant does not improve on that vectorized scorer. The composition totals confirm that the scorer is not the bottleneck.

## What the centroid variant changes

The approximation method and its full retained-course comparison are described in [Centroid coverage in recommendations](/docs/experiments/recommendations/centroid-coverage.md). Its quality limits apply to every outcome difference below.

| Basis | Comparison | Counts | Same set | Same order | Rank changes | Values | Add | Remove | Max overlap | Ties |
|---:|---|---:|---|---|---:|---:|---:|---:|---:|---:|
| 1 | A against saved product | 37 to 37 | yes | yes | 0 | 51 | 0 | 0 | 3.55e-14 | 0 |
| 1 | B against saved centroid | 37 to 37 | yes | yes | 0 | 55 | 0 | 0 | 3.55e-14 | 0 |
| 1 | A against B | 37 to 37 | yes | yes | 0 | 69 | 0 | 0 | 12.5083 | 0 |
| 10 | A against saved product | 69 to 69 | yes | yes | 0 | 128 | 0 | 0 | 3.55e-14 | 0 |
| 10 | B against saved centroid | 69 to 69 | yes | yes | 0 | 142 | 0 | 0 | 5.68e-14 | 0 |
| 10 | A against B | 69 to 69 | yes | yes | 0 | 143 | 0 | 0 | 20.4220 | 0 |
| 50 | A against saved product | 319 to 319 | yes | yes | 0 | 519 | 0 | 0 | 5.68e-14 | 27 |
| 50 | B against saved centroid | 311 to 311 | yes | yes | 0 | 567 | 0 | 0 | 7.11e-14 | 27 |
| 50 | A against B | 319 to 311 | no | no | 253 | 601 | 0 | 8 | 29.7677 | 27 |

The `Values` column counts every changed field instance. The `Max overlap` column is the largest absolute overlap delta. The `Ties` column counts adjacent exact score and relatedness pairs.

On the one-course and 10-course bases the centroid leg returns the same retained set and order as the chunk leg. Relatedness and score values differ by at most 2.13e-14, while every overlap value changes. On the 50-course basis the centroid leg retains 311 courses against 319, removes eight near duplicates and changes 253 ranks.

Of the 311 common retained courses, 225 overlap deltas are positive and 86 are negative. The minimum is -23.76225002053112, the maximum 29.767657934221624, the median 4.96675212310349 and the mean 5.21893313818033. Rank shifts run from one to eight places, with a median of six. The centroid leg against the saved centroid reference differs only in the last bits, with a largest overlap delta of 7.11e-14, so the same values stand within the stated precision.

Median-trim membership is identical across both algorithms and both saved references, with one, five and 25 courses kept. No derived flag changes and no course payload changes on any basis. No candidate has missing chunks or a missing profile.

The centroid leg's exclusion counts match the saved centroid diagnostics on every basis. The one-course basis has five relatedness-floor exclusions, the 10-course basis has 366, and the 50-course basis has 1,532 floor exclusions plus 31 near-duplicate exclusions. The saved product reference has 23 near-duplicate exclusions on basis 50, so the eight extra removals are the additional near duplicates. Chunk-leg exclusion reasons for candidates excluded in both legs were not recomputed.

All eight removed courses leave the retained set because the centroid strongest-course overlap reaches the 90 percent near-duplicate threshold. The relatedness and score values are unchanged within the last bits. These are approximation differences in overlap and near-duplicate rejection, not NumPy parity failures.

| Product rank | Code | Relatedness | Product overlap | Centroid overlap |
|---:|---|---:|---:|---:|
| 59 | MEDANPSTOI | 41.292551201656416 | 89.24819536639642 | 91.34682966790749 |
| 119 | ROBO.010 | 39.0913108158613 | 75.12567889903526 | 97.30423200560415 |
| 126 | MEDAHPAKÄY | 38.89277994110508 | 77.11359657366167 | 94.07053678529105 |
| 130 | MEDAKHETOI | 38.82236733991585 | 88.02511789671591 | 90.68670009547729 |
| 136 | MEDAAKUTOI | 38.52154799651026 | 89.8652792962407 | 92.358234521223 |
| 168 | SSR.GEN.110 | 37.16587835054464 | 65.61579426726132 | 94.52323528382232 |
| 274 | KAN.211 | 34.198519383821576 | 73.11929764716032 | 91.03604629534222 |
| 283 | MEDAINFERI | 33.98307251334506 | 78.18526924937319 | 94.6115727863048 |

## Failed attempts and corrections

The first planned composition invocation on the one-course basis completed a warmup pair and then raised `KeyError: 'readback'` while assembling the warmup record, because the per-leg record did not carry the readback carrier it had already measured. The fix added the returned value to the record. No composition arithmetic, timer, input, connection or database value changed.

The first correction completed the full measurement on the one-course basis and then raised `TypeError: Object of type SimilarityRecommendation is not JSON serializable` while writing the result. The fix converted and retained output payloads in a top-level field, kept the runtime model objects and byte strings out of the written result, and read the result count from the serialization step. Both fixes were checked without a database against the saved one-course inputs before the second correction ran.

The failed first invocation kept its record with the error, address-space check and process snapshot. The first correction left a truncated result payload before its writer raised, with no record. Both artifacts and both logs are preserved. The recorded one-course numbers come from the second correction, which ran the same code as the 10-course and 50-course bases with the recording and serialization corrections only.

Five processes ran in total: the failed planned attempt on the one-course basis, the failed first correction, the recorded second correction, and the recorded 10-course and 50-course bases. No further retry followed.

| # | Basis | Invocation | Outcome | Elapsed (s) | User CPU (s) | System CPU (s) | Peak RSS (MB) |
|---:|---:|---|---|---:|---:|---:|---:|
| 1 | 1 | Planned | Failed, record assembly | 1.471 | 1.990 | 0.091 | 134.5 |
| 2 | 1 | Correction 1 | Failed, payload serialization | 3.073 | 3.315 | 0.138 | 136.1 |
| 3 | 1 | Correction 2 | Recorded | 3.083 | 3.297 | 0.169 | 138.2 |
| 4 | 10 | Planned | Recorded | 14.990 | 12.446 | 0.607 | 369.8 |
| 5 | 50 | Planned | Recorded | 67.069 | 47.389 | 2.333 | 1,186.7 |

A later timing correction changed the centroid saving. The earlier centroid coverage measurements recorded a 6.95, 24.40 and 53.35 percent scorer saving for the Python centroid scorer. Its first baseline sample included construction of the captured scorer-input payloads, and every baseline sample included output model dumps, while the centroid timer ended when the scorer returned. The matched measurement under identical boundaries gives 4.80, 19.68 and 58.85 percent. The 53.35 percent figure was therefore not an algorithm-only speedup, and the matched values are the ones this report uses.

The vectorization batch ran six planned processes, three scoring and three paired reads. No process failed and no retry followed. Every paired sample ran below the fatal 60 s timer, every process ran below 180 s and every process ran below the 2.147 GB address-space limit. Each process ran alone after a free-memory check.

Every completed composition process opened eight read-only connections, one per leg, and recorded 32 rollback events. Every connection reported `default_transaction_read_only=on` and `statement_timeout=30s`. No product data was written and no write was attempted.

## Limitations

- The pools are fixed captured retrieval outputs. They establish no full-catalogue coverage, retrieval equivalence, semantic quality or recommendation quality.
- Scorer-only and read-only timings are not whole-request or HTTP latency. ANN retrieval, the next-course read, the serving identity wrapper and response delivery are outside every timing.
- Composition times one complete fixed-pool leg. It excludes capture observers, hashing and delivery, and it is not an HTTP request measurement.
- The scoring pair used a fixed product, centroid, then NumPy order, so cache warmth may favor the later calls. The composition pairs alternated order, but database and CPU cache warmth is uncontrolled.
- Process peak resident set size (RSS) is process-wide and includes capture decoding, carrier conversion, interpreter and library pages. It is not an algorithm-specific memory measurement.
- The dataset was resolved through a dataset receipt rather than the selected dataset, so its resolution cost differs from a request that resolves the selected dataset.
- The reads timer includes the product leg's Python field filtering and excludes connection startup.
- Exclusion reasons for candidates excluded under both variants were not recomputed.
- The measured centroid implementation computes coverage for candidates that the relatedness floor later excludes, which A does not. This is part of the measured B cost.
- The 50-course pool comes from a recovery capture with the timer-boundary deviation stated above.
- A rank, value or membership match does not establish semantic correctness.
- The preservation result is scoped to the fixed pools and does not establish a general behavior-preserving guarantee.
- Last-bit differences are reported exactly. Byte equality is not claimed.

## Setup details

| Item | Value |
|---|---|
| Hardware | 4-core aarch64 server, 23.6 GB of RAM |
| Python | 3.14.3 |
| NumPy | 2.4.6 |
| BLAS | scipy-openblas 0.3.31 (build 188.0) |
| BLAS configuration | `USE64BITINT DYNAMIC_ARCH NO_AFFINITY neoversev2 MAX_THREADS=64` |
| Array dtype | float64 |
| Thread limits | `OPENBLAS_NUM_THREADS=1`, `OMP_NUM_THREADS=1`, `MKL_NUM_THREADS=1`, `BLIS_NUM_THREADS=1`, `VECLIB_MAXIMUM_THREADS=1` |
| SQL policy | Read-only transaction, 30 s statement timeout |
| Address-space limit | 2.147 GB (2,147,483,648 bytes) |
| Process limit | 180 s |
| Paired sample limit | 60 s |

The NumPy interpreter was a disposable virtual environment that exposed the base interpreter's NumPy and BLAS read-only, and the project packages read-only through `PYTHONPATH`. No package install or upgrade ran, and the project environment, dependency files and product dependencies were not modified.

| # | Basis | Mode | Outcome | Elapsed (s) | User CPU (s) | System CPU (s) | Peak RSS (MB) |
|---:|---:|---|---|---:|---:|---:|---:|
| 1 | 1 | Scoring | Completed | 1.282 | 1.866 | 0.104 | 124.2 |
| 2 | 10 | Scoring | Completed | 7.595 | 8.075 | 0.223 | 359.6 |
| 3 | 50 | Scoring | Completed | 43.650 | 43.385 | 0.633 | 1,176.0 |
| 4 | 1 | Reads | Completed | 1.700 | 2.115 | 0.131 | 144.3 |
| 5 | 10 | Reads | Completed | 10.800 | 8.331 | 0.726 | 363.0 |
| 6 | 50 | Reads | Completed | 50.154 | 30.306 | 2.889 | 1,176.0 |

Elapsed is the process snapshot taken from a marker after the module's imports and before evidence serialization. It excludes interpreter startup and the module's imports, and it includes the run work and the load of the shared scoring code. The process peaks are process-wide and include capture parsing, carrier conversion, interpreter and library pages.

## Where the line ended

The measurements did not promote either change by themselves. The float64 NumPy scorer and the descriptive-only projected read were selected and applied in the product, and [Recommendations](/docs/backend/search-and-discovery/recommendations.md) states the scoring and the read that the product serves. The product scorer computes the same formula on float64 arrays, and the descriptive path filters content and outcomes in SQL while the all-field read keeps its behavior. The applied scorer accepts the measured last-bit differences against the fixed pools, with a largest relatedness and score difference of 2.1316282072803006e-14 and a largest overlap difference of 5.684341886080802e-14.

Centroid coverage was not selected and was dropped. It adds no consistent composition saving after vectorization and narrow reads, and on the 50-course basis it removes eight near duplicates and changes 253 ranks. Its approximation differences are outcome changes, not a parity failure.

Speed and outcome are kept apart. The NumPy scorer is faster and returns the product outcome. The projected read is faster and returns identical carriers. The centroid variant is not faster once the chunk scorer is vectorized, and it changes outcomes on the largest pool. The selections are recorded outcomes, and they do not by themselves establish semantic or recommendation quality.

## Untested questions

- Whole-request latency. The fixed-pool savings have not been translated into an HTTP measurement that includes ANN retrieval, the next-course read, the serving identity wrapper and response delivery. Untested.
- Candidate read cost. The candidate chunk read is the largest composition stage on the 50-course basis. Whether a different read shape, cache or transport lowers it is untested here.
- Centroid quality. Whether the eight near-duplicate removals improve or worsen recommendations was not measured. Untested.
