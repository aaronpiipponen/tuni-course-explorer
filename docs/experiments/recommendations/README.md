# Recommendation experiments

Eight reports measure how recommendations score a basis, where a recommendation request spends its time, and which cheaper step keeps the same result.

## The question the line asks

[Recommendations](/docs/backend/search-and-discovery/recommendations.md) rank courses whose teaching text is close to the completed [basis](/docs/reference/glossary.md#prerequisites-and-routes), after the [next courses](/docs/reference/glossary.md#discovery-and-the-structure-of-studies) for the same request. A recommendation should deepen or connect the topics of the basis, and it should not repeat teaching that the basis already contains. A [near-duplicate](/docs/reference/glossary.md#discovery-and-the-structure-of-studies) cut enforces the second requirement by removing a candidate outright.

The line asked three kinds of question.

- Which policy values separate useful neighbours from repeats, and whether counts and example names can support that choice.
- Where a recommendation request spends its time, and which change inside the request removes that cost without changing the result.
- Which cheaper step keeps the recommended set: a coarser coverage formula, a narrower read, an earlier filter or a stored neighbour table.

The line holds two kinds of change apart. A formula-preserving change alters how the same computation runs, so the recommended set, order and flags must match. A formula-changing approximation alters what is computed, so the outcome may change and its speed gain does not carry the earlier result with it.

A preservation claim here covers the set, the order, the flags, equal exclusion outcomes and median-trim membership. It is not bitwise, because float64 arithmetic accumulates in a different order, so the numeric meters may differ in their last binary digits. Each comparison states its own bound. The whole-report latency comparison accepted a difference of at most 1e-9 and observed zero. The array-scorer and prefilter comparisons applied no tolerance, and the array scorer reports a largest relatedness and score delta of 2.13e-14 and a largest overlap delta of 5.68e-14. The centroid legs reproduced their saved references within the last binary digits, and the native scorer reports a largest relatedness and score delta of 6.4e-14 and a largest overlap delta of 1.1e-13.

## Shared ground

### One catalogue and the fixed selections

All eight reports read one captured catalogue. The [Experiments](/docs/experiments/README.md#the-catalogue-the-experiments-read) section states its counts. The vectors are stored BGE-M3 embeddings with 1,024 components, so the scorer, read and composition measurements read stored vectors.

A cohort here is one fixed input set that a series of measurements reuses, and a pool is the ranked candidate set that the product's retrieval and eligibility output holds for one basis.

The 10 October 2026 line fixed four baskets. The three named baskets are one programming course, a three-course computing set and a three-course math-heavy set, and they name requested course codes that resolve to canonical identities through the [course resolver](/docs/reference/glossary.md#search-and-comparison). The fourth takes the three computing identities in request order, then the 46 next-course results of the computing basket in report order, removes duplicates and keeps the first 50. Canonical deduplication left 49 courses, and one of them is inactive.

The 21 October 2026 line drew 200 active course identities that have a completed descriptive chunk compatible with the embedding configuration, with the selection seed 20261021. It resolved their representative versions once and took the first 50 compatible representatives in shortlist order. The bases of one, 10 and 50 courses are nested prefixes of that order. Four reports share that selection: centroid coverage, vectorization and narrow reads, composition overheads, and the course-centroid prefilter.

Three of those reports ran on fixed pools that held 42, 435 and 1,874 ranked candidates, with 137, 1,771 and 7,657 candidate chunk rows and two, 39 and 209 basis chunk rows. The prefilter shares the selection and the nested bases and ran on a disposable copy of the selected dataset.

The 28 to 30 October 2026 studies used other selections. The nearest-neighbour read used bases of five, 20 and 40 courses that are prefixes of one fixed representative order, and a separate endpoint comparison drew 38 cases at bases from three to 500 from a fixed pool of 500 courses. The paired scorer matrix used bases of 20, 40, 50 and 60 courses from one fixed selection, in an active-only and an including-inactive scope. The matched endpoint matrix drew its bases from a 500-course workload pool.

The early candidate pool came from an approximate nearest read with 40 chunks per basis chunk, a shortlist of 100 candidates and a result cap of 30. The 21 October pools are the product's own retrieval and eligibility outputs for the three nested bases, after its next-course exclusions. The selections share the catalogue rather than a candidate pool.

### Hardware the reports name

The scoring calibration names a four-core aarch64 server with 24.1 GB of RAM, and the latency diagnosis states no machine. The four studies on the 21 October 2026 selection state no RAM value: the vectorization and composition records name a four-core aarch64 server, and the centroid coverage and prefilter records state no machine.

The paired scorer matrix names a four-core aarch64 Neoverse N1 server with 24.1 GB of RAM, with PostgreSQL 18.6 and pgvector 0.8.6 in a container. The matched endpoint matrix ran over four workers under a 2.31 GB web cap, and the native product measurements ran on a four-core aarch64 server that states no RAM value. The nearest-neighbour runs state no hardware.

[The hardware](/docs/experiments/README.md#the-hardware) section states the other records of the period.

### The request and policy settings

The four studies on the 21 October 2026 selection read the configured policy. The 10 October 2026 line used its own starting values, and a value does not cross the two columns.

| Element | 10 October 2026 line | 21 October 2026 selection |
|---|---|---|
| Basis sizes | 1, 3, 3 and 49 | 1, 10 and 50 |
| Prerequisite mode | Partially covered (`at_least_one`) | All (`all`) |
| Relatedness | Greatest raw chunk cosine, mapped to 0 to 100 | Hub-centred similarity to a trimmed basis vector |
| Overlap | Whole basis at once, with a strong-match cosine floor of 0.79 | One basis course at a time, calibrated between 0.20 and 0.90 |
| `RECOMMENDATION_CHUNK_TOP_K` | 40 | 40 |
| `RECOMMENDATION_MIN_RELATEDNESS` | 0.80 starting value, checked at 0.55, 0.80 and 0.85 | 0.33 |
| `RECOMMENDATION_NEAR_DUPLICATE_PERCENT` | 75 percent starting value | 90 percent |
| `RECOMMENDATION_OVERLAP_PENALTY_WEIGHT` | 0.30 starting value | 0.0 |
| `COMPARISON_OVERLAP_FLOOR` | No calibrated mapping | 0.20 |
| `COMPARISON_OVERLAP_CEILING` | No calibrated mapping | 0.90 |

The four studies recorded `basis=completed`, `mode=all`, `display_language=en`, `include_inferred=false` and `active_only=true`. The early line used `mode=at_least_one`. The stored-cohort tie-break diagnosis covered three inactive bases, the separate 38-case endpoint comparison ran in active and inactive scope and with and without inferred prerequisites, and the paired scorer matrix ran in both activity scopes, so no single request applies to the whole line.

The nearest-neighbour read also states `RECOMMENDATION_CHUNK_TOP_K` = 40, and the native scoring report does not state this policy set, so the table describes the two earlier cohorts.

The measured build of the early line shortlisted at most 100 candidates (`RECOMMENDATION_CANDIDATE_LIMIT`), kept at most 30 results (`RECOMMENDATION_MAX_RESULTS`) and counted a candidate chunk as covered at a cosine of 0.79 (`COMPARISON_STRONG_MATCH_MIN_SCORE`). The product reads none of those three keys, so its list is cut by the relatedness floor and the near-duplicate rule alone.

The 0.80 floor, the 75 percent share and the 0.30 weight are the early experiment's starting values, not the product's policy. A 0.80 floor on a greatest-chunk scale and a 0.33 floor on a hub-centred scale are different cuts.

### Sample structure and cache warmth

The studies recorded different numbers of samples and controlled cache state differently.

| Study | Warm-up | Recorded samples | Reported value |
|---|---|---|---|
| Latency diagnosis | None | Three complete commands per basket | Each run listed |
| Centroid coverage | One warm-up, and one paired warm-up for the matched scorer measurement | Three | Median |
| Vectorization and narrow reads | One warm-up | Three | Median |
| Composition overheads | One warm-up per cell | Three | Median |
| Course-centroid prefilter | One warm-up pair per basis | Three pairs | Median |
| Nearest-neighbour endpoints | Two warm-up calls | Five | Median |
| Paired scorer matrix | Two warm-up calls | Five | Median |
| Matched endpoint matrix | Not stated | Three distinct report-cache misses | Mean |

Cache warmth was not controlled in the latency, centroid, vectorization and composition series. The prefilter ran with a cold next-course source cache and no descriptive chunk cache. The nearest-neighbour endpoints and the paired scorer matrix report warm values after their warm-up calls, and the paired matrix also reports a report-cache-miss value. The matched endpoint matrix measured three distinct report-cache misses. No series gives a distribution or a confidence interval.

### What the measurements did not include

No report carries a relevance judgment, a user study or a recommendation-quality measurement. A retained set, a rank, a meter or a saving is an arithmetic outcome. No rejected candidate was reviewed in the early line, and the later comparisons set one computation against another rather than against a reader's preference.

The scorer, read, composition and complete-command values come from one process at a time.

## Timing boundaries

The line keeps five boundaries apart, and a saving at one does not carry to another. A core-second is one CPU core busy for one second.

| Boundary | What it covers |
|---|---|
| One scorer call | Conversion, hub subtraction, unit normalization, course points, the median trim, the matrix products, threshold arithmetic, result construction and sort. It excludes capture loading, output dumps, serialization and retrieval. |
| One read | Both repository reads and the field filter. It excludes connection startup, retrieval, scoring and serving. |
| One fixed-pool composition leg | Dataset and settings resolution, engine creation, the first connection and schema head check, the reads, array preparation, scoring, report construction and serialization inside one saved pool. It excludes approximate retrieval, the next-course read, capture observers, hashing and delivery. |
| One served recommendation route cost | One call through the served route, reported as a median in milliseconds for the nearest-neighbour endpoints, or as endpoint core-seconds for the native matrices, where the matched matrix sums the web, database and embedding components. |
| One complete command | Input resolution, settings, the next-course command, database and vector work, overlap and ranking, and JSON serialization. |

The scorer, read, composition and complete-command values were measured in process, not through a web request. The nearest-neighbour medians drove the served recommendation route, and the matched endpoint matrix ran over four workers on one host. Neither measured concurrent load.

The composition's stage segments account for its total, and their separately reported medians sum to 10.5728 s against a 10.5724 s total at basis 50. Separate medians need not add exactly. The latency report's stage values are separate measurements of nested work and do not sum to its command. Its unprofiled expanded command listed stages that summed to 24.287 s against a 24.311 s command. A separate next-course value comes from a different call than the recommendation rows it sits beside.

## Headline results

| Report | Run dates | Question | Result that stands |
|---|---|---|---|
| [Recommendation scoring calibration](/docs/experiments/recommendations/scoring-calibration.md) | 10 October 2026 | Which relatedness floor separates neighbours from repeats? | 0.80 kept as the starting floor, with 19, 13 and three results at 0.80, one, one and none at 0.85, and 22 on the one-course basket at 0.55 |
| [Recommendation latency diagnosis and remediation](/docs/experiments/recommendations/latency-diagnosis-and-remediation.md) | 10 October 2026 | Where did a command of 24.345 to 25.449 seconds spend its time? | Occurrence resolution on the small baskets and overlap on the 49-course basket, then complete commands of 1.644 to 2.760 seconds, with the one-second target unmet |
| [Centroid coverage in recommendations](/docs/experiments/recommendations/centroid-coverage.md) | 21 October 2026 | Does one vector per course save scorer time, and what changes? | 58.85 percent scorer saving on the 50-course pool, the same set and order on the two smaller pools, eight removals and 253 of 311 ranks changed, and no consistent composition saving |
| [Recommendation vectorization and narrow reads](/docs/experiments/recommendations/vectorization-and-narrow-reads.md) | 21 October 2026 | Can the same formula cost less? | 91.81 percent scorer and 26.31 percent read wall-median saving on the 50-course pool, with the same set and order on all three pools |
| [Recommendation composition overheads](/docs/experiments/recommendations/recommendation-composition-overheads.md) | 21 October 2026 | Where does one fixed-pool composition spend its time? | Candidate chunk read at 4.0299 seconds and scoring at 6.1915 of a 10.5724-second fresh composition at basis 50, and no consistent engine-reuse saving |
| [Course-centroid candidate prefilter](/docs/experiments/recommendations/centroid-candidate-prefilter.md) | 27 October 2026 | Can a stored centroid apply the relatedness floor before the measured read? | The same set, order and meters on every recorded pair, and a 50-course stage from 7.947 to 3.408 seconds |
| [Nearest-neighbour retrieval for recommendations](/docs/experiments/recommendations/nearest-neighbour-retrieval.md) | 28 October 2026, and 29 to 30 October 2026 | Why did the nearest-chunk read return fewer than 40 rows per chunk, and can the rows be stored? | An iterative scan filled every chunk, and a stored table at 128 rows per query chunk lowered the basis 20 served median from 1,480.2 to 231.1 ms, with 3,200 of 3,320 rows at basis 20 after exclusions |
| [Native recommendation scoring](/docs/experiments/recommendations/native-recommendation-scoring.md) | 28 to 30 October 2026 | Can the scoring arithmetic move to native code with the same result? | The same candidates, order, meters and derived-text flag, with a maximum relatedness and score delta of 6.4e-14 and fewer core-seconds in every measured endpoint |

## How the reports connect

[Recommendation scoring calibration](/docs/experiments/recommendations/scoring-calibration.md) fixed the request, the model and the rest of the policy, then chose the starting floor from counts and example names. [Recommendation latency diagnosis and remediation](/docs/experiments/recommendations/latency-diagnosis-and-remediation.md) asked where a 24-second command spent its time and removed two costs inside the request. [Recommendation composition overheads](/docs/experiments/recommendations/recommendation-composition-overheads.md) then measured where one fixed-pool composition spends its time, and whether holding one database engine across repetitions lowers it.

[Centroid coverage in recommendations](/docs/experiments/recommendations/centroid-coverage.md) replaced the chunk-pair coverage step with one [course centroid](/docs/reference/glossary.md#discovery-and-the-structure-of-studies) per course and recorded the change it made in the set, the order and the meters. The same report compares the two coverage steps on identical reads and arrays. [Recommendation vectorization and narrow reads](/docs/experiments/recommendations/vectorization-and-narrow-reads.md) measured two formula-preserving changes one at a time and then together.

[Course-centroid candidate prefilter](/docs/experiments/recommendations/centroid-candidate-prefilter.md) applies the relatedness floor from the shared centroid matrix before the candidate summaries and chunks are read. [Nearest-neighbour retrieval for recommendations](/docs/experiments/recommendations/nearest-neighbour-retrieval.md) explains why the direct scan under-filled, measures the iterative scan, and measures the stored table that answers a request in place of the per-request scan, including the cutoff tie-break that fixes which row survives inside an exact-score cohort.

The stored-cohort diagnosis and the endpoint comparison are separate. The three inactive bases of 20, 50 and 60 courses changed by one, one and three identities, and the stored-cohort diagnosis covers those bases. The 38-case endpoint comparison at bases from three to 500 returned 32 cases with identical identities, order and values. The six that differ are the two active cases at basis three, the two active cases at basis 40 and the two inactive cases at basis 200, and those six differences are recorded at the final-list level with no stored-cohort diagnosis.

[Native recommendation scoring](/docs/experiments/recommendations/native-recommendation-scoring.md) moved the arithmetic and the overlap loop to native code. The product scorer runs as native code, and that report measures it against the Python scorer on the same candidates.

## What the line applied

| Change | Status | Evidence scope |
|---|---|---|
| Native scorer evaluating the product formula on float64 arrays | Applied in the product | The paired scorer matrix at bases 20, 40, 50 and 60 in both activity scopes, and the matched endpoint matrix |
| Course-centroid prefilter before the summary read, from the shared centroid matrix | Applied in the product | Three nested bases on a disposable copy, with the same set, order and meters on every recorded pair |
| Stored neighbour table at 128 rows per query chunk, built with the iterative scan | Applied in the product | 4,709,120 rows for 36,790 query chunks, with the retained-set difference recorded |
| float64 array scorer evaluating the product formula | Applied on the measured build | Three fixed pools of 42, 435 and 1,874 candidates |
| Descriptive-only read of content and outcomes rows | Applied on the measured build | The same three pools, with identical carriers |
| Request-local occurrence index and once-prepared overlap | Applied on the measured build | Four fixed baskets, with every captured report preserved within 1e-9 |
| Centroid coverage | Dropped | The same three fixed pools |

The product scorer runs as native code and computes the product formula on float64 arrays. A recommendation request reads its candidate chunk rows from the shared descriptive chunk store, without a database read. [Recommendation ranking](/docs/backend/search-and-discovery/recommendation-ranking.md) states those reads and formulas, and [Native recommendation scoring](/docs/experiments/recommendations/native-recommendation-scoring.md) measures the scorer.

No threshold from the early calibration was selected as a product setting. The configured policy holds a 0.33 relatedness floor, a 90 percent near-duplicate share and a 0.0 overlap penalty weight, and the four studies on the 21 October 2026 selection read it.

The centroid column read on the served path and the admission curves fitted from served requests are measured in [Served read path](/docs/experiments/runtime-storage-and-serving/served-read-path.md) and [Serving request cost and admission curves](/docs/experiments/runtime-storage-and-serving/serving-request-cost-and-admission.md).

## Limits shared by the line

- No report measures recommendation quality. A retained set, a rank or a meter is not evidence that a reader would prefer one list to another.
- The fixed pools are the product's retrieval outputs for fixed bases, not a full-catalogue sample. They establish no retrieval equivalence and no coverage of other subjects.
- A saving measured on one boundary does not carry to another. The scorer, read, composition and complete-command savings are separate measurements and do not add to one total.
- The early and later selections use different bases and a different scoring scale. A floor, a count or a saving from one does not transfer to the other.
- The stored neighbour read under-fills after request exclusions, returning 644 of 720, 3,200 of 3,320 and 6,640 of 6,840 rows on the bases of five, 20 and 40 courses. It is an approximation for those exclusions, and the direct query is its reference.
- The prefilter saving was measured on a disposable copy of the selected dataset, with a cold next-course source cache and no descriptive chunk cache.
- The centroid memory figures are Python allocation traces for one scorer call or process-wide resident peaks. They do not isolate per-algorithm memory.
- The values measured in process are not web request latency. The served-route measurements carry no concurrent load, so none of them is a server capacity result.

## Untested questions

Each question below is untested.

- Whether a human rating agrees with the retained sets, ranks and meters, including the eight centroid removals and 253 rank changes on the 50-course pool.
- Whether the early floor and share transfer to a humanities or social-science basis, or to a single course outside computing.
- Whether an overlap penalty weight above zero changes scores and the centroid outcome, since the later line ran at a weight of 0.0.
- Whether more than 128 stored rows per query chunk closes the exclusion gap at an acceptable table size and build time, and whether a second direct scan only for chunks that under-fill recovers the direct rows.
- Whether the prefilter pays on a basis larger than 50 courses, how much of its saving the shared float64 chunk store removes on a warm serving path, and whether a float32 centroid store keeps the same retained set near the floor.
- Whether whole-request latency meets the fixed-pool savings, including approximate retrieval, the next-course read, the serving identity wrapper and response delivery.
- Whether a shared, process-independent chunk matrix removes the marshalling cost of the native scorer, and whether candidate discovery is the next stage to move at bases 50 and 60.
- What causes the six differing endpoint cases, and whether they change what a reader prefers.
