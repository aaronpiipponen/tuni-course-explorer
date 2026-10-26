# Recommendation latency diagnosis and remediation

This report traces four fixed baskets whose complete recommendation commands took 24.345 to 25.449 seconds, the two request-local costs found, and the 1.644 to 2.760 second result.

**Evidence status:** Comparative. **Run date:** 10 October 2026.

## The question

[Recommendations](/docs/backend/search-and-discovery/recommendations.md) list courses whose teaching text is similar to the whole [basis](/docs/reference/glossary.md#prerequisites-and-routes), after the complete [next-course](/docs/reference/glossary.md#discovery-and-the-structure-of-studies) report for the same inputs. The design target was about one second on the server for a basis of up to 50 courses. Four fixed baskets measured 24.345 to 25.449 seconds per complete command before any diagnosis. The line asked where that time went, whether the cost sat in the database, the approximate vector read or application computation, and whether request-local changes could remove it without stored change, an additional index or a different result.

Latency is the only subject. The selection and tuning of the relatedness floor, the near-duplicate percentage and the overlap penalty belong to [Recommendation scoring calibration](/docs/experiments/recommendations/scoring-calibration.md). The effect of the basis centroid on the courses reached belongs to [Centroid coverage in recommendations](/docs/experiments/recommendations/centroid-coverage.md), and score-preserving vectorization belongs to [Recommendation vectorization and narrow reads](/docs/experiments/recommendations/vectorization-and-narrow-reads.md).

All times are complete command wall seconds unless a row states another boundary. The command includes input resolution, settings, database and vector work and JSON serialization. A 30-second cap was external to the product and stopped a run that reached it.

## Baskets and command boundary

| Basket | Basis | Basis size | Next courses | Similarity results |
|---|---|---|---:|---:|
| One course | `COMP.CS.100` | 1 | 25 | 19 |
| Computing | `COMP.CS.100`, `COMP.CS.110`, `COMP.CS.140` | 3 | 46 | 13 |
| Math-heavy | `MATH.MA.110`, `MATH.MA.120`, `MATH.MA.210` | 3 | 23 | 3 |
| Expanded computing | Three computing seeds and 46 computing next courses, deduplicated (49 actual) | 49 | 31 | 30 |

The one-course, computing and math-heavy baskets name requested course codes that resolve to canonical identities through the shared course lookup. The expanded computing basket began with the three computing identities in request order, followed by the 46 next-course results from the same computing basket in report order. Canonical deduplication left 49 courses, within the first-50 cap. One computing seed is inactive, and an inactive course is a valid basis course. The expanded basket is the 49-course stress basis.

The expanded basket returned 30 similarity results, equal to the measured build's result cap. The uncapped count after overlap removal was not measured, so the full qualifying set is unknown. The measured build's shortlist cap held the courses kept from the nearest hits for full scoring at 100, but its actual occupancy was not measured.

The three keys `RECOMMENDATION_CANDIDATE_LIMIT`, `RECOMMENDATION_MAX_RESULTS` and `COMPARISON_STRONG_MATCH_MIN_SCORE` belonged to the measured build. The product reads none of the three.

| Setting in the measured build | Key | Value used by the runs |
|---|---|---:|
| Chunks per basis chunk | `RECOMMENDATION_CHUNK_TOP_K` | 40 |
| Candidate shortlist | `RECOMMENDATION_CANDIDATE_LIMIT` | 100 |
| Result cap | `RECOMMENDATION_MAX_RESULTS` | 30 |
| Relatedness floor | `RECOMMENDATION_MIN_RELATEDNESS` | 0.80 |
| Near-duplicate share | `RECOMMENDATION_NEAR_DUPLICATE_PERCENT` | 75 |
| Overlap penalty weight | `RECOMMENDATION_OVERLAP_PENALTY_WEIGHT` | 0.30 |
| Strong-match cosine floor | `COMPARISON_STRONG_MATCH_MIN_SCORE` | 0.79 |

The latency runs changed none of these values. The product's recommendation list is cut by the relatedness floor and the near-duplicate rule alone, so it has no configured length limit. The tuning of the similarity thresholds belongs to the scoring report.

Every timed recommendation invocation was a separate complete command. It resolved the requested identities, read settings, ran the next-course command, read basis and candidate vectors, ran the nearest query, computed overlap and ranking, and serialized the report. Three runs per basket are listed. No concurrent load is recorded. Every database transaction was read-only. No GPU, model provider, stored-vector write, schema change or configuration change took place.

## Initial complete timings

| Basket | Basis size | Separate next course (s) | Three complete recommendation runs (s) |
|---|---:|---:|---|
| One course | 1 | 24.425 | 24.345, 24.467, 24.465 |
| Computing | 3 | 24.512 | 25.270, 25.426, 25.331 |
| Math-heavy | 3 | 24.213 | 24.395, 24.457, 24.545 |
| Expanded computing | 49 | 1.015 | 25.449, 24.944, 24.822 |

The small baskets took 24.345 to 25.426 seconds, and their separate next-course calls took 24.213 to 24.512 seconds. The next-course stage therefore accounted for the small-basket cost, and the recommendation stage was not its source. The expanded basket's next-course call took 1.015 seconds, while its complete recommendation took 24.822 to 25.449 seconds. The recommendation and vector work accounted for that cost. The separate next-course calls are different invocations, so these values are not stage sums.

The same command through the [command-line script](/docs/backend/interfaces/command-line.md) took 25.85 seconds including process startup and JSON output. The initial target miss was left without a stored change. A diagnosis followed to ask why the two basket sizes produced similar command times.

### The 48-course sample

An earlier stress attempt built its basis by sorting the three computing seed identities and removing the inactive seed. It held 48 courses. Its first run was stopped at the 30-second cap, and its other two runs took 23.492 and 23.763 seconds. That basis was not the intended construction and did not supply the acceptance inputs. The corrected basis kept the seeds in request order and retained the inactive seed. Its three runs are the values in the table above and are the acceptance values for the 49-course basis.

## Small-basket diagnosis

The one-course next-course command ran under Python's `cProfile` profiler and completed in 89.833 seconds. The profiler adds overhead, so the value is not a command wall time and is not compared with the table above. The profile recorded 63 SQL reads over 0.382 SQL seconds. The next-course outcome evaluation took 87.043 seconds. It resolved an occurrence 9,942 times, and those resolutions took 86.236 seconds and yielded about 11.45 million requirement occurrences from repeated whole-tree searches. An occurrence is one position in a requirement tree. The calls came from next-course coverage for course slots and substitution slots. The database reads and the compiler were not the dominant cost.

### The identity lookup check

A disposable prototype outside the product replaced the repeated whole-tree search with a first-object identity lookup and the same root fallback. It returned a complete one-course next-course report in 1.925 seconds and recorded 63 SQL reads over 0.353 SQL seconds. This isolated the computational cause. It did not establish report equality with the pre-change command and was not a product change.

An attempt to profile the expanded recommendation stopped at an external 110-second cap. No profiled large-basket breakdown exists. The unprofiled run below supplied the attribution.

## Expanded-basket diagnosis

### Stage attribution

The unprofiled expanded recommendation completed in 24.311 seconds.

| Stage | Seconds |
|---|---:|
| Next-course command | 0.907 |
| Basis summaries | 0.034 |
| Basis vectors (305, including name vectors the command discarded) | 0.137 |
| Nearest descriptive query (207 input chunks, 1,550 hits) | 1.239 |
| Current hit summaries (601) | 0.086 |
| Candidate vectors (480) | 0.192 |
| Recommendation overlap and result service | 21.692 |

The listed stages sum to 24.287 seconds against the 24.311-second command. The 56 SQL reads took 1.510 seconds, and the nearest query's SQL execution took 1.085 seconds. The overlap and result stage took 21.692 seconds and included the near-duplicate check, the overlap meters, scoring and ordering. It was application computation over the read vectors, not SQL execution.

The nearest query's plan read a `VALUES` list, applied a lateral `LIMIT`, joined by nested loops and used `Index Scan using ix_course_embedding_chunks_embedding_hnsw`, ordered by cosine distance to the input vector. HNSW is an approximate nearest-neighbor graph index. The index was present and was used by the nearest query. The 21.692-second overlap cost was application computation, so no planner forcing or additional index was needed for it. Basis and candidate reads each happened once, outside candidate loops.

### The overlap prototype

A disposable prototype outside the product compared same-language content and outcomes, kept character weights, the inclusive floor, clipped cosine and equal averaging across common languages. It computed each symmetric chunk-pair product once, tracked covered flags in both directions, and skipped only pairs whose two flags were already covered.

Preparing the whole basis for each candidate produced a 2.718-second overlap stage. Preparing it once for all candidates produced a 0.417-second stage.

A first-candidate check matched the earlier overlap exactly at 57.04419676182141 in one direction and 1.8986328498639349 in the other. The earlier comparison took 0.270 seconds. That is one candidate's arithmetic, not a whole-report equivalence proof. It did not establish that a product change would preserve every result.

Combining the identity lookup and the once-prepared overlap returned a complete expanded recommendation in 2.945 seconds, including an extra earlier first-candidate overlap call. The next-course stage took 0.528 seconds, the nearest query 1.240 seconds, and the overlap wrapper 0.724 seconds including the earlier comparison and preparation. The combined diagnostic did not reach one second. It did not establish that the residual required stored change. It supported one bounded product remediation.

## Request-local remediation

The remediation made two changes.

1. Occurrence resolution. One first-occurrence identity index is built inside the request's database session and discarded with it. It replaces repeated whole-tree searches while preserving the first positional occurrence and the root fallback.
2. Overlap preparation. The descriptive basis is normalized once per request. Each candidate-basis chunk product is computed once and reused for the candidate-to-basis coverage and the per-basis-course near-duplicate check. Character weights and the configured floor and ceiling are the same.

Recommendation filtering uses the shared overlap calibration. The approximate nearest-neighbor read and the HNSW index did not change. No stored vector, schema or configuration value changed. The composition check compares the embedded next-course report with a separate next-course call.

## Final measurements and parity

### Report parity

Before the product changes, four next-course reports and four recommendation reports were captured under the same 30-second cap. All eight completed. The final reports were captured after the changes, and only whitespace formatting followed the run.

After the changes, each separate next-course report equalled its saved pre-change report object, including order and coverage. Each recommendation report embedded the same next-course report. The third run of each basket kept the initial similarity result identities and order. Shared course report objects, derived flags and overlap availability matched. Relatedness, score and available overlap differed by no more than 1e-9, and the observed differences were zero.

The acceptance checks also confirmed that every similarity result was canonical-unique, active, disjoint from the basis and the next-course set, at or above the configured raw floor, below the inclusive near-duplicate cutoff when overlap was available, scored by the configured penalty formula and within the measured build's result cap.

The four-basket parity check, not the one-candidate arithmetic check, established whole-report parity within the stated tolerance on these inputs.

### Complete command times

| Basket | Basis size | Separate next course (s) | Three complete recommendation runs (s) | Next courses | Similarity results |
|---|---:|---:|---|---:|---:|
| One course | 1 | 1.804 | 1.644, 1.648, 1.699 | 25 | 19 |
| Computing | 3 | 1.554 | 1.705, 1.728, 1.738 | 46 | 13 |
| Math-heavy | 3 | 1.598 | 1.693, 1.741, 1.705 | 23 | 3 |
| Expanded computing | 49 | 0.530 | 2.697, 2.760, 2.700 | 31 | 30 |

The three small baskets took 1.644 to 1.741 seconds, and the expanded basket took 2.697 to 2.760 seconds. The command-line script took 3.241 seconds including process startup and JSON output.

The chart shows the three complete recommendation runs for each basket after the changes.

![Three complete recommendation runs for the one-course, computing, math-heavy and expanded 49-course baskets after remediation, showing 1.644 to 1.741 seconds on the small baskets and 2.697 to 2.760 seconds on the expanded basket.](/docs/charts/recommendation-latency-final-runs.svg)

### Stage costs

| Basket | Embedded next course (s) | Nearest chunks (s) | Basis vector reads (s) | Candidate vector reads (s) | Overlap and results (s) |
|---|---|---|---|---|---|
| One course | 1.496, 1.502, 1.559 | 0.029, 0.025, 0.024 | 0.010, 0.008, 0.008 | 0.048, 0.047, 0.047 | 0.015, 0.015, 0.015 |
| Computing | 1.585, 1.592, 1.558 | 0.041, 0.039, 0.040 | 0.014, 0.013, 0.014 | 0.031, 0.030, 0.030 | 0.013, 0.013, 0.013 |
| Math-heavy | 1.614, 1.578, 1.558 | 0.054, 0.048, 0.047 | 0.014, 0.013, 0.014 | 0.013, 0.013, 0.013 | 0.006, 0.006, 0.007 |
| Expanded computing | 0.489, 0.590, 0.540 | 1.257, 1.230, 1.258 | 0.129, 0.126, 0.124 | 0.191, 0.193, 0.189 | 0.484, 0.452, 0.447 |

Each cell lists the first, second and third run. On the expanded basket, the nearest query took 1.230 to 1.258 seconds and the overlap and result stage 0.447 to 0.484 seconds. The embedded next-course stage took 0.489 to 0.590 seconds. The basis and candidate vector reads were below 0.2 seconds each. The stage values are separate measurements and do not sum to the complete command.

The final nearest query's bounded plan again used the same HNSW index. No additional index or stored change was part of the remediation.

The chart shows the three stage measurements for the expanded basket.

![Embedded next-course, nearest-chunk, vector-read and overlap-result stage costs for the expanded 49-course basket across three runs, showing the nearest query and overlap stage dominate the 2.7-second command.](/docs/charts/recommendation-latency-stage-costs.svg)

### Remaining latency

The expanded recommendation takes about 2.7 seconds, mainly the 1.23-second nearest query and the 0.45-second overlap and result stage. The separate small-basket next-course calls took 1.554 to 1.804 seconds, and complete small-basket recommendations 1.644 to 1.741 seconds. The approximately one-second target was not met. The residual was left without a claim that the target had been met. These measurements do not establish that meeting the target would require stored change. No stored change or additional index was made, and no further optimization loop ran.

## Measurement boundaries

| Measurement | Boundary | Result |
|---|---|---|
| Initial complete recommendation | Complete command with JSON serialization, external 30-second cap | 24.345 to 25.449 seconds |
| Initial separate next course | Complete next-course command, external 30-second cap | 24.213 to 24.512 seconds on the small baskets, 1.015 seconds on the expanded basket |
| Profiled one-course next course | Complete next-course command under `cProfile`, profiler overhead included | 89.833 seconds |
| Disposable identity lookup | Complete one-course next-course command outside the product | 1.925 seconds |
| Disposable overlap, per candidate | Overlap stage only | 2.718 seconds |
| Disposable overlap, prepared once | Overlap stage only | 0.417 seconds |
| Disposable combined recommendation | Complete expanded recommendation with an extra earlier overlap call | 2.945 seconds |
| Final complete recommendation | Complete command with JSON serialization, external 30-second cap | 1.644 to 2.760 seconds |
| Final command-line script | Process startup and JSON output included | 3.241 seconds |

The profiled value includes profiler overhead. The disposable values are diagnostics outside the product. The final rows are product measurements. The 30-second, 65-second and 110-second caps were external. A cap is not a product timeout.

The separate next-course column comes from different calls than the recommendation rows. The command-line row includes process startup, which the command rows do not. Stage values are separate from complete command values.

## What the results do not establish

- The four baskets, the captured catalogue and one 4-core aarch64 server with 23.6 GB of RAM do not establish a latency bound for other bases, other data or a loaded server. No concurrent load is reported.
- These are complete command times, not web request-path latency. No web server, [admission control](/docs/backend/interfaces/admission-control.md) or concurrent request was measured.
- The report makes no claim about semantic quality, ranking quality or scoring calibration. Those belong to the linked recommendation reports.
- The one-candidate overlap check is arithmetic evidence for one pair. It is not a whole-report equality proof. The parity check covers four baskets.
- The 89.833-second profile includes profiler overhead and is not comparable with wall-clock commands.
- The expanded profile stopped at the external 110-second cap, so no profiled stage breakdown exists for that basket.
- The measurements do not establish that the remaining latency requires stored change, an additional index or a schema change. They also do not establish that no request-local improvement remains.
- The 48-course sample is not a stress result.
- The records show no separate warmup, controlled cache warmth or concurrent load. The runs are three repeated invocations, not a warm and cold comparison.
- The result count of 30 on the expanded basket equals the measured build's cap. The uncapped count after overlap removal was not measured.

## Setup details

| Item | Value |
|---|---|
| Hardware | 4-core aarch64 server, 23.6 GB of RAM |
| Accelerator | none, no GPU access |
| Remote stages | none ran |
| Embedding model | `BAAI/bge-m3`, 1,024 components |
| Embedding configuration | SHA-256 `926180fdf7044ef858f0224d4712cebebf71beb107010c41f1ab418b80c60560` |
| Vectors | stored representative content and learning-outcome chunks, no embedding request |
| Database | PostgreSQL with pgvector and an HNSW index on the chunk embedding column |
| Access | read-only transactions |
| Baskets | four fixed baskets, three recommendation runs each |
| External caps | 30 seconds for acceptance and final runs, 110 seconds for the first expanded profile, 65 seconds and 30 seconds for later bounded checks |
| Warmup | no separate warmup reported |
| Concurrent load | none reported |

Every request used `basis=completed`, `mode=at_least_one`, `display_language=en`, `include_inferred=false` and `active_only=true`. Only chunks with the matching embedding configuration hash participated.

## Open questions

- Whether the 1.23-second nearest query and the 0.45-second overlap stage can be reduced further inside the request without changing the approximate index or stored data. Untested.
- Whether the same request-local changes hold their latency and report parity on other bases, a larger catalogue or a server under concurrent load. Untested.
- Whether a web request path that adds admission control, worker forwarding and response transfer meets the same times. Untested.
