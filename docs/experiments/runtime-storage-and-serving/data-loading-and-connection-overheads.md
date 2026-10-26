# Data loading and connection overheads

This report measures how much fixed-pool recommendation latency comes from dataset resolution, database reads, engine lifetimes, preparation, scoring and serialization, and how an earlier read projection changed full-catalogue commands.

**Evidence status:** Comparative. **Run date:** 21 October 2026.

## The question

[Recommendations](/docs/backend/search-and-discovery/recommendations.md) rank courses whose teaching text is close to the completed [basis](/docs/reference/glossary.md#prerequisites-and-routes). A recommendation command loads the basis and candidate courses, reads their descriptive [chunks](/docs/reference/glossary.md#capture-and-data-preparation), prepares the scorer inputs, scores the candidates and serializes a report. The line asked two questions about that path.

The first question asked whether the product's full-catalogue reads could select fewer columns and a narrower identity scope without changing their results. The second asked how much of a fixed-pool recommendation composition comes from dataset and settings resolution, summary and chunk reads, engine and session lifetimes, preparation, the product scorer and report serialization. The composition ran the same fixed pool in fresh, reused and prepared modes.

The two questions share the captured catalogue but not an input set or a timing boundary. The first measured full-catalogue command and read wall times. The second measured one composition on each of three saved recommendation pools. The full-catalogue 2.6 to 2.9 s search and the 0.28 s full-scope coverage are not the fixed-pool 10.5724 s basis 50 composition. They are separate measurements. The full-catalogue projection figures come from an earlier measurement whose run date was not recorded.

A fixed-pool composition is one complete recommendation composition on a saved candidate pool. It resolves settings, reads summaries and descriptive chunks, prepares the saved objects, scores, builds the report and serializes it. It excludes approximate nearest-neighbour retrieval, the next-course read, capture observers, hashing, the serving identity wrapper and response delivery.

The product scorer in this line is the scalar implementation of the recommendation formula that the measurement used. No float64 NumPy scorer and no centroid coverage scorer ran.

## The catalogue and the two measurement lines

The captured catalogue held 11,086 represented courses, of which 4,543 were active, and 58,962 teaching-text chunks. The stored chunk vectors are BGE-M3 embeddings with 1,024 components. The fixed-pool line ran no embedding model and was measured on a 4-core aarch64 server with 23.6 GB of RAM.

The full-catalogue projection measured the product's search, prerequisite and coverage commands and two repository reads on that catalogue. The fixed-pool line drew three nested bases from a saved selection. The selection seed was 20261021. It fixed 200 stored active course identities that had a completed descriptive chunk compatible with the embedding configuration, resolved their representative versions once, and took the first 50 compatible representatives in shortlist order. The 10-course and single-course bases are prefixes of that order.

Each candidate pool is the product's saved retrieval and eligibility output for one basis, after its next-course exclusions. The pools held 42, 435 and 1,874 ranked candidates. No extraction, selection, approximate retrieval or pool variant ran for this line.

| Basis | Basis chunk rows | Ranked candidates | Retained by the saved report | Candidate chunk rows |
|---|---:|---:|---:|---:|
| 1 | 2 | 42 | 37 | 137 |
| 10 | 39 | 435 | 69 | 1,771 |
| 50 | 209 | 1,874 | 319 | 7,657 |

The fixed request used `basis=completed`, `mode=all`, `display_language=en`, `include_inferred=false` and `active_only=true`, with the selected set equal to the completed set equal to each basis. The recommendation settings were:

| Setting | Value |
|---|---:|
| `RECOMMENDATION_CHUNK_TOP_K` | 40 |
| `RECOMMENDATION_MIN_RELATEDNESS` | 0.33 |
| `RECOMMENDATION_NEAR_DUPLICATE_PERCENT` | 90 |
| `RECOMMENDATION_OVERLAP_PENALTY_WEIGHT` | 0.0 |
| `COMPARISON_OVERLAP_FLOOR` | 0.20 |
| `COMPARISON_OVERLAP_CEILING` | 0.90 |

The 50-course pool came from a recovery capture. Its first capture completed the product work and then failed while serializing under the 2.147 GB address-space cap. A separate recovery saved the capture and supplied the pool. The recovery used separate 60 s timers for the product command and for serialization, where the intended boundary was one cumulative timer through both. That is a recorded deviation in the capture, not in the composition samples. The capture and its deviation are described in [Centroid coverage in recommendations](/docs/experiments/recommendations/centroid-coverage.md#the-basis-50-failure-and-recovery). This report reuses that recorded context and does not remeasure the capture.

## The full-catalogue read projection

The projection narrowed both the columns and the identity scope of the full-catalogue reads. The represented-course summary read returns the shared official summary columns plus the selected representative identity. It returns no full course versions, teaching texts, curriculum periods, prerequisite rows or substitution rows. Unrepresented courses are absent. A selected representative with no persisted version raises the same missing-version error as the full course read.

The summary is built by the same shared summary builder as the full read, so the field mapping has one source of truth. Unified search performs one represented-summary read per query and passes the result to each lexical and semantic method. A method called on its own without that shared result reads for itself. The read protocols behind these paths are described in [Curriculum reads](/docs/backend/catalogue/curriculum-reads.md).

The coverage read is one aggregate `GROUP BY` query. It materializes no chunk entity, no stored text and no vector. It emits all 12 field, language and origin cells in enum order, including cells whose counts are zero, and sets the total chunk count to the sum of the buckets. Aggregate status counts equal the per-cell sums.

The graph read seeds the target and retained course identities in one eager read, prefetches the direct inputs, then reads every other referenced course or module lazily through a per-compilation cache. It shares its loaders with the full reads, so identity filtering is the only behavioral difference. An identity absent from the database resolves to missing, and the hard-fail cases have the same outcomes.

The projection changed no result. The `search`, `prerequisites` and `--coverage` commands, described in [Command line](/docs/backend/interfaces/command-line.md), produced JSON outputs byte-identical by SHA-256 to their pre-change outputs on the full catalogue. The change was checked by targeted tests, a network-free suite of 330 passed and 56 skipped tests, a disposable-database integration gate of 21 passed tests, and the byte-identical command outputs.

| Measurement | Boundary | Before (s) | After (s) |
|---|---|---:|---:|
| Unified search | Command | 15.5 to 19.0 | 2.6 to 2.9 |
| Prerequisites `COMP.CS.500` | Command | about 14.5 | 2.35 to 2.44 |
| `--coverage` | Command | 18.6 | 6.14 |
| Represented summary read | Read | 4.15 | 1.04 |
| Full-scope coverage | Read | 13.5 | 0.28 |

The `--coverage` command includes work beyond the coverage read, so the command row and the read row are separate. The represented summary read stands in place of a full course read that took 4.15 s. The full-scope coverage read is the aggregate query alone.

The chart plots unified search at the lower bounds of both ranges. The prerequisite before value is approximately 14.5 s, and its after value is the lower bound of the 2.35 to 2.44 s range. The other three rows are plotted as recorded.

![Full-catalogue command and read wall times before and after the projection. Unified search uses both range minima, prerequisites uses an approximate before value and the after range minimum, and the other reads use their recorded values.](/docs/charts/runtime-loading-full-catalogue-reads.svg)

The outputs were byte-identical and the reads became faster. The measurement does not decompose a command, so attributing the command reduction to the narrower read is an interpretation.

> [!IMPORTANT]
> The full-catalogue figures and the fixed-pool composition figures are different measurements. The 2.6 to 2.9 s search and the 0.28 s full-scope coverage are full-catalogue timings. The 10.5724 s basis 50 figure is one fixed-pool composition with the scalar product scorer. They are not a before-and-after pair and do not add up.

## Fixed pools, modes and timing boundaries

Each recorded cell ran one process in one measurement mode.

| Mode | What the composition does |
|---|---|
| Fresh | Resolves the named receipt and settings, creates a database engine and session factory, checks the schema head on the first connection, reads summaries and descriptive chunks, prepares, scores, builds the report and serializes. |
| Reused | Holds one experiment-local engine across repetitions and uses fresh sessions for the reads. Engine creation and the first connection and head check are measured in setup, outside the composition samples. Final disposal is outside the samples but inside the process. |
| Prepared | Uses the saved in-memory summaries and chunks, the validated settings and the product scorer. It opens no database connection and records the receipt head. Preparation, scoring, report construction and serialization are separate segments. |

Fresh and reused read the captured summaries through the represented-summary read. They read descriptive chunks through the product descriptive projection, which selects completed, non-null chunks for the captured embedding configuration and projects content and outcomes only. The read returns the chunks in the requested order. The readback compares the returned objects with the saved ones outside the primary timings.

Every mode called the product recommendation service on its read or saved objects and wrapped its output in the product report. Serialization was `model_dump(mode='json')` plus `json.dumps(..., ensure_ascii=False, separators=(',', ':'))`. It excludes the serving identity wrapper of the web response. No HTTP request ran.

| Timer | Covers | Excludes |
|---|---|---|
| Composition sample | Resolution, engine creation, first connect and head check, summary read, basis chunk read, candidate chunk read, preparation, scoring, report construction and serialization | Approximate retrieval, next-course read and compiler, capture observers, hashing, serving identity wrapper, response delivery and HTTP |
| Prepared composition | Preparation of saved objects, scoring, report construction and serialization | Database I/O, engine creation, connection and head check |
| Process | Everything from a marker after product imports, including setup, capture decode, warmup, three recorded samples and cleanup | Interpreter startup and product imports |

The composition total is measured directly. The stage segments are nested inside that total and are not additive independent timings. No saved next-course or whole-command estimate is added to the composition total.

Each cell ran one warmup and three recorded repetitions. Each composition sample ran under one fatal 60 s timer that enclosed serialization and was not reset for individual stages. Each process had a 180 s limit and a 2.147 GB address-space cap. One heavy process ran at a time after a free-memory check.

Every connection ran with `default_transaction_read_only=on` and a `statement_timeout` of 30 s. The connection observer confirmed both on every connection and rolled back every read. Fresh processes opened four connections, reused processes one and prepared processes none. The observer's setting checks and rollbacks lie inside the measured segments.

## Composition results

Recorded wall medians for one complete composition:

| Basis | Fresh (s) | Reused (s) | Prepared (s) |
|---:|---:|---:|---:|
| 1 | 0.1868 | 0.1207 | 0.0526 |
| 10 | 1.5798 | 1.5215 | 0.7880 |
| 50 | 10.5724 | 10.7306 | 6.6311 |

Recorded CPU medians:

| Basis | Fresh (s) | Reused (s) | Prepared (s) |
|---:|---:|---:|---:|
| 1 | 0.1510 | 0.0982 | 0.0524 |
| 10 | 1.2546 | 1.2240 | 0.7837 |
| 50 | 8.3232 | 8.5755 | 6.5517 |

The chart shows the wall medians by mode.

![Wall medians for the fixed-pool recommendation composition on the single-course, 10-course and 50-course bases in fresh, reused and prepared modes, with prepared fastest on every basis.](/docs/charts/runtime-loading-composition-modes.svg)

Reused against fresh changed the measured composition by -35.37, -3.69 and +1.50 percent. The direction is not consistent across the three bases. Engine creation itself is about 0.0004 s inside a fresh composition, so the single-course difference is not an engine-creation saving. The single-course reused cell also recorded a summary read of 0.0146 s against 0.0488 s fresh, while the 50-course reused cell recorded a slightly higher scoring time. The recorded changes do not show a consistent engine-reuse saving. That is an interpretation of the mode differences, not a decomposition of the engine's share.

Prepared against fresh changed the composition by -71.83, -50.12 and -37.28 percent. Prepared mode removes database I/O and reconstitutes the saved objects in memory. Its preparation segment took 0.0024, 0.0674 and 0.2133 s. The prepared reduction is a measurement of experiment-local reuse, not a product cache, pool or invalidation policy.

The 10.5724 s basis 50 median is one fixed-pool composition. It is not a whole-command time and not a full-catalogue search.

## Where the composed time goes

The stage medians for the single-course basis:

| Segment | Fresh (s) | Reused (s) | Prepared (s) |
|---|---:|---:|---:|
| Named receipt and settings resolution | 0.0066 | 0.0063 | not run |
| Engine creation | 0.0004 | outside samples | not run |
| First connect and schema head | 0.0231 | outside samples | not run |
| Summary read | 0.0488 | 0.0146 | not run |
| Basis chunk read | 0.0066 | 0.0037 | not run |
| Candidate chunk read | 0.0499 | 0.0476 | not run |
| Engine disposal | 0.0003 | outside samples | not run |
| Preparation | 0.0000 | 0.0000 | 0.0024 |
| Scoring | 0.0512 | 0.0478 | 0.0497 |
| Serialization | 0.0005 | 0.0005 | 0.0005 |
| Total | 0.1868 | 0.1207 | 0.0526 |

The stage medians for the 10-course basis:

| Segment | Fresh (s) | Reused (s) | Prepared (s) |
|---|---:|---:|---:|
| Named receipt and settings resolution | 0.0064 | 0.0064 | not run |
| Engine creation | 0.0004 | outside samples | not run |
| First connect and schema head | 0.0234 | outside samples | not run |
| Summary read | 0.0915 | 0.0833 | not run |
| Basis chunk read | 0.0184 | 0.0150 | not run |
| Candidate chunk read | 0.7191 | 0.7075 | not run |
| Engine disposal | 0.0003 | outside samples | not run |
| Preparation | 0.0002 | 0.0002 | 0.0674 |
| Scoring | 0.7176 | 0.7062 | 0.7197 |
| Serialization | 0.0009 | 0.0009 | 0.0009 |
| Total | 1.5798 | 1.5215 | 0.7880 |

The stage medians for the 50-course basis:

| Segment | Fresh (s) | Reused (s) | Prepared (s) |
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

The chart shows the basis 50 fresh stage costs.

![Nested stage wall medians for the basis 50 fresh composition, with the candidate chunk read and scoring dominating and resolution, engine creation, the head check, preparation and serialization in the millisecond range.](/docs/charts/runtime-loading-stage-costs.svg)

At bases 10 and 50 the candidate chunk read and the product scorer carry most of the composed time. Resolution measures 0.0063 to 0.0066 s, engine creation 0.0004 s, the first connection and head check 0.0231 to 0.0234 s, disposal 0.0003 to 0.0004 s and serialization 0.0005 to 0.0041 s. Engine creation is lazy and opens no connection, so its 0.0004 s is not a connection cost. The first connection and schema head check is the larger connection cost.

On the single-course basis the summary read and the scorer are comparable to the candidate read, and the head check is a larger share of the total. The stage shares differ across the bases.

The cheap micro-operations repeated at most 10 times in each process:

| Operation | Median wall (s) | Scope |
|---|---:|---|
| Named-receipt settings resolution | 0.0058 to 0.0061 | Includes the search and embedding settings loads and the identity comparison |
| Engine creation and disposal | 0.0002 | Opens no connection |
| Live selected-pointer metadata | 0.0013 to 0.0014 | Returns a different dataset identity, discards the settings and opens no connection |

The live selected-pointer observation is separate metadata. It was never used for a captured read. The named-receipt resolution is the path that the composition used.

## The dataset identity stop

The first planned process ran the single-course basis in fresh mode. It decoded and verified the fixed capture first. The selection digest, capture digest, basis prefix, saved output digest, candidate pool digest and both descriptive chunk digests all matched. The live resolver then returned a different selected dataset identity than the captured one. The runner compared the values and stopped with an input mismatch.

The stop occurred before the connection observer was installed and before any engine existed. The process opened no database connection, issued no SQL and attempted no write. It produced no composition timing. It recorded 0.688 s wall, 1.273 s user CPU, 0.104 s system CPU and a 109.77 MB process peak, with zero connections.

The stop followed the dataset identity check. The attempt is preserved as a failed process and was not averaged into a result. It left eight unrun cells.

The recovery did not continue those eight cells. It defined a separate nine-cell matrix against the same captures, three bases by three modes. It is not a continuation of the stopped attempt and not a rebaseline.

The recovery resolved the captured dataset through its own [dataset receipt](/docs/reference/glossary.md#administration) instead of the live selected-dataset pointer. It read the configured database components, loaded the receipt for the captured identity and pinned every captured-dataset engine to the receipt's database name. The receipt identity, verification revision and connected schema head had to equal the captured values.

The pin resolves a captured dataset by its dataset receipt, and the serving path resolves the [selected dataset](/docs/reference/glossary.md#administration). A separately labelled metadata observation read the live selected-dataset pointer and discarded its settings. It returned the other selected identity in every process, opened no connection and was never used for a captured read.

The captured dataset was retained and readable, so the recovery could resolve it by receipt. Every captured read used the pin. The live pointer path was not used for a captured read.

## The readback correction

The first recovery process ran the single-course basis in fresh mode. It completed one composition and its product output matched the saved baseline exactly. It then stopped because the candidate descriptive read digest differed from the saved full chunk digest.

The saved candidate set includes NAME chunks. The product descriptive read selects CONTENT and OUTCOMES only. The saved full set is 221 chunks. The descriptive subset is 137 chunks, and its digest equals the live read on the pinned dataset. The summary read matched every saved summary and the scorer output matched the saved report. No data or identity mismatch was present.

One read-only diagnostic process pinned the captured dataset, compared the descriptive read with the saved objects and wrote no product data. It is not a matrix measurement and produced no timing.

The correction compared the descriptive read with the descriptive fields of the saved objects and kept the full chunk digests as fixed-input identity evidence. The rerun opened four connections, ran one warmup and three recorded repetitions, and matched the saved output and serialization exactly. The single-course fresh results come from that rerun.

The failed process produced no used composition timing. No timing was fabricated for it. Both correction invocations were used and zero remained.

## Parity and the process records

Each mode and basis reproduced the saved report. Fresh and reused readback also reproduced the saved summary objects and the descriptive chunks. Every recorded sample matched the saved similarity results exactly and reproduced the saved serialized report.

| Basis | Summaries | Basis descriptive chunks | Candidate descriptive chunks | Candidate full chunk rows | Results | Serialized bytes |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 43 | 2 | 137 | 221 | 37 | 16,054 |
| 10 | 445 | 39 | 1,771 | 2,641 | 69 | 29,989 |
| 50 | 1,924 | 209 | 7,657 | 11,405 | 319 | 152,191 |

The candidate full chunk rows include NAME chunks. The descriptive rows select content and outcomes only. The summary count is one per captured basis and candidate identity.

The process records list every measurement attempt:

| # | Process | Basis | Mode | Outcome | Wall (s) | User CPU (s) | System CPU (s) | Peak RSS (MB) | Connections |
|---:|---|---:|---|---|---:|---:|---:|---:|---:|
| 1 | First planned | 1 | fresh | failed, dataset identity mismatch | 0.688 | 1.273 | 0.104 | 109.77 | 0 |
| 2 | Recovery | 1 | fresh | failed, readback comparison | 0.732 | 1.576 | 0.132 | 133.76 | not recorded |
| 3 | Recovery | 1 | reused | recorded | 1.605 | 2.434 | 0.131 | 134.14 | 1 |
| 4 | Recovery | 1 | prepared | recorded | 1.090 | 1.999 | 0.155 | 121.86 | 0 |
| 5 | Recovery | 10 | fresh | recorded | 11.391 | 10.628 | 0.409 | 370.48 | 4 |
| 6 | Recovery | 10 | reused | recorded | 11.095 | 10.447 | 0.424 | 371.34 | 1 |
| 7 | Recovery | 10 | prepared | recorded | 7.012 | 7.792 | 0.219 | 371.90 | 0 |
| 8 | Recovery | 50 | fresh | recorded | 62.075 | 52.078 | 1.700 | 1,186.98 | 4 |
| 9 | Recovery | 50 | reused | recorded | 62.491 | 52.995 | 1.698 | 1,186.93 | 1 |
| 10 | Recovery | 50 | prepared | recorded | 42.478 | 42.592 | 0.630 | 1,187.04 | 0 |
| 11 | Corrected rerun | 1 | fresh | recorded | 1.812 | 2.636 | 0.135 | 134.24 | 4 |

Wall is the elapsed time from a marker set after product imports. Interpreter startup and imports lie outside the marker, so a short process can show more user CPU than wall. Peak RSS is process-wide and is reported in MB, converted at 1,024 bytes per recorded unit. The failed readback process completed one composition before it stopped, and its process record has no connection observation. The diagnostic process is not listed because it produced no timing. The single-course fresh results come from the corrected rerun, not from the failed readback process.

The measurement budget allowed one initial process, up to nine recovery processes and two diagnosed correction invocations. Nine recovery processes ran, one failed, and both correction invocations were used. Zero remained. No process exceeded 180 s, no sample exceeded 60 s and no process exceeded the 2.147 GB address-space cap. The longest recorded sample was 10.73 s, the longest warmup 10.88 s and the longest process 62.49 s.

The composition medians are per sample. A process also includes setup, capture decode, warmup, three recorded samples and cleanup, so a process time is much larger than a composition median. Helper import took 0.058 to 0.077 s per process. Capture decode and fixed-input verification took 0.34 to 0.35 s for the single-course basis, 3.24 to 3.27 s for the 10-course basis and 13.82 to 14.39 s for the 50-course basis. Named-receipt resolution in setup took 0.0112 to 0.0118 s. Reused engine setup took 0.095 to 0.101 s for creation and 0.029 to 0.031 s for the first connection and head check.

## What the line applied

The projected represented-summary read, the one summary read per unified search, the aggregate coverage read and the scoped graph read are part of the product's read path. The full-catalogue outputs were byte-identical.

The overhead measurement made no product change. Fresh, reused and prepared are measurement modes. Prepared mode is experiment-local reuse. No product cache, connection pool or invalidation policy was created. The measurement makes no product-promotion recommendation.

## What the results do not establish

- The fixed pools are the product's retrieval outputs for three nested bases, not a full-catalogue sample. They establish no retrieval equivalence, semantic quality or recommendation quality.
- The composition is not an HTTP request. Approximate retrieval, the next-course read and compiler, capture observers, hashing, the serving identity wrapper and response delivery are outside every timing. No server latency is claimed.
- Nested stage segments share the outer total and are not additive. No saved next-course or whole-command estimate is added to the composition. The saved baselines are context, not this line's measurements.
- Dataset resolution pins a captured dataset by its dataset receipt rather than the selected-dataset pointer. Its cost differs from the serving path's resolution.
- Prepared mode is experiment-local. It creates no product cache, pool or invalidation policy.
- Only the scalar product scorer ran. No float64 NumPy scorer, centroid coverage scorer or alternative scoring variant ran in this line. The matched scorer and read measurements in [Recommendation vectorization and narrow reads](/docs/experiments/recommendations/vectorization-and-narrow-reads.md) are reused as context, not rerun.
- Engine reuse changed the composition by -35.37, -3.69 and +1.50 percent. The direction is not consistent. The line makes no connection-pool or engine-reuse recommendation.
- Three recorded repetitions per cell give medians, not distributions or confidence intervals. Database and CPU cache warmth was uncontrolled.
- Peak RSS is process-wide. It is not a per-stage memory measurement.
- The composition was not measured through the live selected-pointer path.
- The 50-course pool came from a recovery capture with the recorded timer deviation. Its first capture failed with `MemoryError` while serializing the fixed input.
- The readback correction changed the comparison, not the output. The failed process produced no used timing.
- The projection measurements are command and read wall times. They carry no memory measurement and are not HTTP latency.
- The projection work did not include HNSW indexing or path-solver dominance pruning.
- No recommendation-quality judgment ran. A retained course, rank or wall time is not a quality measure.

## Setup details

| Item | Value |
|---|---|
| Hardware | 4-core aarch64 server, 23.6 GB of RAM |
| Python | 3.14.3 |
| Catalogue | 11,086 represented courses, 4,543 active, 58,962 teaching-text chunks |
| Vectors | BGE-M3, 1,024 components, no embedding model ran in the fixed-pool line |
| Selection | Seed 20261021, 200 active identities, first 50 compatible representatives, nested bases of 1, 10 and 50 |
| Candidate pools | 42, 435 and 1,874 ranked candidates |
| Request | `basis=completed`, `mode=all`, `display_language=en`, `include_inferred=false`, `active_only=true` |
| SQL policy | Read-only transaction, 30 s statement timeout |
| Address-space cap | 2,147,483,648 bytes (2.147 GB) |
| Process limit | 180 s |
| Sample limit | One fatal 60 s timer through serialization |
| Repetitions | One warmup and three recorded repetitions per cell, up to 10 for cheap micro-operations |
| Thread limits | `OPENBLAS_NUM_THREADS=1`, `OMP_NUM_THREADS=1`, `MKL_NUM_THREADS=1`, `BLIS_NUM_THREADS=1`, `VECLIB_MAXIMUM_THREADS=1` |

One heavy process ran at a time after a free-memory check. The thread variables were set before product imports. Every connection reported `default_transaction_read_only=on` and a `statement_timeout` of 30 s. Every read rolled back and no write was attempted.

The basis 50 pool came from the recovery capture described above. The first capture failed under the address-space cap. The recovery capture used split 60 s timers as a recorded deviation. The composition samples in this report each used one fatal 60 s timer through serialization.

## Untested questions

- Whole-request HTTP latency, including approximate retrieval, the next-course read, the serving identity wrapper and response delivery. Untested.
- Whether a product connection pool or engine reuse helps under concurrent requests or at other pool sizes. The line measured one process at a time on three fixed pools. Untested.
- Whether live selected-pointer resolution changes the composition cost, since the line pinned a named receipt. Untested.
