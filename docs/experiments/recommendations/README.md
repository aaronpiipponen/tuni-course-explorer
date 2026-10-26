# Recommendation experiments

Four experiments trace how recommendations score a basis, why the command ran slowly, and whether a cheaper coverage step or a preserved formula could cut the cost.

## The question the line asked

[Recommendations](/docs/backend/search-and-discovery/recommendations.md) rank courses whose teaching text is close to the completed [basis](/docs/reference/glossary.md#prerequisites-and-routes), after the [next courses](/docs/reference/glossary.md#discovery-and-the-structure-of-studies) for the same request. A recommendation should deepen or connect the topics of the basis, and it should not repeat teaching that the basis already contains. A [near-duplicate](/docs/reference/glossary.md#discovery-and-the-structure-of-studies) cut enforces the second requirement by removing a candidate outright.

Four questions followed. The first asked which starting values separate useful neighbors from repeats, and whether counts and example names could support that choice. The second asked where a command that took 24.345 to 25.449 seconds spent its time, and whether request-local work could remove the cost without changing the output. The third asked whether one centroid vector per course could replace the chunk-pair coverage step and save scorer time. The fourth asked whether the same formula, evaluated on float64 arrays and read through a narrower SQL projection, could cost less without changing the recommended set.

The line holds two kinds of change apart. A formula-preserving change alters how the same computation runs, so the recommended set, order and flags must match. A formula-changing approximation alters what is computed, so the outcome may change and its speed gain does not carry the earlier result with it. The line also keeps four timing boundaries apart: one scorer call, one read, one fixed-pool composition leg, and one complete command.

## The order of the line

[Recommendation scoring calibration](/docs/experiments/recommendations/scoring-calibration.md) opened the line on 10 October 2026. It fixed the request, the model and the rest of the policy, checked the relatedness floor at 0.80 and 0.85 on three baskets, recorded 0.55 results for the one-course basket alone, and ran an expanded basket at the selected floor. The floor is a similarity cut. It does not measure whether a course is a sensible next step, and the check recorded counts and example names rather than relevance judgments. The near-duplicate share of 75 percent, the value that removes a candidate outright, and the overlap penalty weight of 0.30 were left at their starting values and were not varied. No rejected candidate was reviewed.

[Recommendation latency diagnosis and remediation](/docs/experiments/recommendations/latency-diagnosis-and-remediation.md) asked where that time went. The small baskets spent it in the next-course stage. A profiled one-course next-course run resolved an occurrence 9,942 times and produced about 11.45 million requirement occurrences, with profiler overhead included in its 89.833 seconds. The 49-course basket spent 21.692 of an unprofiled 24.311 seconds in overlap and result computation. Two request-local changes followed, one for occurrence resolution and one for overlap preparation. They preserved every captured report, with scored values within 1e-9, and the target of about one second was not met.

[Centroid coverage in recommendations](/docs/experiments/recommendations/centroid-coverage.md) tested one unit-mean vector per course in place of the chunk pairs, on three fixed pools of 42, 435 and 1,874 candidates. The approximation preserved set and order on the two smaller pools and changed both on the 50-course pool. Its scorer saving did not survive as a composition saving after the formula-preserving work, and the candidate was dropped.

[Recommendation vectorization and narrow reads](/docs/experiments/recommendations/vectorization-and-narrow-reads.md) measured two formula-preserving changes on the same three pools, a float64 NumPy scorer and a projected read of content and outcomes rows. It then compared centroid coverage against the vectorized chunk-pair leg on identical reads. The two formula-preserving changes were selected and applied. Centroid coverage was not.

The reading order is conceptual, not a single measurement sequence. The four reports share one captured catalogue, one 4-core aarch64 server and a read-only database, but not an input set, a scoring scale or a timing boundary.

## Headline results

| Report | Run date | Question | Result that stands |
|---|---|---|---|
| Recommendation scoring calibration | 10 October 2026 | Which relatedness floor separates neighbors from repeats? | 0.80 kept as a starting floor, with 19, 13 and three results on the three baskets and one, one and none at 0.85 |
| Recommendation latency diagnosis and remediation | 10 October 2026 | Where did a 24.345 to 25.449 second command spend its time? | Occurrence scans on the small baskets and overlap on the 49-course basket, then 1.644 to 2.760 seconds after two request-local changes, with the target unmet |
| Centroid coverage in recommendations | 21 October 2026 | Does one centroid per course save scorer time, and what changes? | 58.85 percent scorer saving on the 50-course pool, eight removals and 253 of 311 ranks changed, then dropped for no consistent fixed-pool composition saving |
| Recommendation vectorization and narrow reads | 21 October 2026 | Can the same formula cost less? | 91.81 percent scorer and 26.31 percent read wall-median saving on the 50-course pool, with the same set and order as the product on all three pools, applied |

## Shared ground and its boundaries

All four reports read one captured catalogue. It holds 11,086 courses, each counted once through a representative version (4,543 active), and 58,962 teaching-text [chunks](/docs/reference/glossary.md#capture-and-data-preparation). The vectors are stored BGE-M3 embeddings with 1,024 components, so no embedding request ran in any measurement. Each run used read-only PostgreSQL with pgvector on a 4-core aarch64 server with 23.6 GB of RAM. No GPU or model-provider call took part.

The inputs were fixed rather than sampled at run time. The early line fixed four baskets on 10 October 2026, and the expanded basket reused the computing basket's next courses. The later line fixed 200 active course identities with a selection seed of 20261021 and derived nested bases of one, 10 and 50 courses from them. The later series took three recorded samples after one warmup, so those values are medians, not a distribution or a confidence interval. The earlier line recorded three runs per basket and reports no warmup. Cache warmth was not controlled.

No measurement is a web request. The matched and later scorer timers exclude capture loading, payload construction, output dumps, serialization and disk work. The early centroid baseline included payload construction in its first sample and output dumps in every sample. The read timer covers both repository reads and the Python field filter. A composition leg covers resolution, reads, scoring and serialization inside one fixed pool, and excludes approximate retrieval, the next-course read and delivery. Complete command values cover input resolution through JSON serialization. No concurrent load is recorded.

## Changing the formula and preserving it

Centroid coverage changes the formula. It replaces every candidate-basis chunk pair with one unit-mean vector per course, so character counts leave the coverage calculation and the whole-basis meter and the strongest-course meter become the same value. The relatedness profile, thresholds, tie order and output type are the same. The product's relatedness and coverage steps are described in [Coverage and ranking](/docs/backend/search-and-discovery/coverage-and-ranking.md).

On the one-course and 10-course pools the retained set, the order and every relatedness and score value matched, while every overlap value changed. On the 50-course pool the approximation retained 311 courses against 319, removed eight and changed 253 of the 311 common ranks. No course was added. All eight removals crossed the 90 percent near-duplicate threshold under centroid coverage and sat below it under chunk pairs, which raised the near-duplicate count from 23 to 31. The overlap delta among the 311 common courses ran from -23.7623 to +29.7677 percentage points, with a mean of +5.2189, so the meter was neither a uniform inflation nor a uniform reduction.

The scorer-only comparison put the two scorers under the same timer on identical inputs. The centroid scorer's wall median fell by 58.85 percent on the 50-course pool, from 6.570340 to 2.703793 seconds. That saving did not become a consistent fixed-pool composition saving. With both legs on the same projected read and float64 arrays, the centroid leg was 1.35 percent faster on the one-course pool, 0.68 percent faster on the 10-course pool and 0.84 percent slower on the 50-course pool, differences of 0.0019, 0.0065 and 0.0420 seconds. The candidate chunk read dominated the leg at 4.05 seconds of 4.97 seconds on the 50-course pool. Centroid coverage was dropped.

The two formula-preserving changes were measured one at a time and then together. The float64 NumPy scorer returned the product retained set and order on all three pools and lowered the wall median by 78.75 percent on the one-course pool, 86.27 percent on the 10-course pool and 91.81 percent on the 50-course pool, where 6.570340 seconds became 0.537979 seconds. The projected read returned identical carriers and lowered the read wall median by 32.04, 30.57 and 26.31 percent, with 5.315186 seconds becoming 3.916760 seconds on the 50-course pool.

The preservation claim covers set, order, flags, equal exclusion outcomes and median-trim membership, and it includes the 27 adjacent exact score and relatedness tie pairs that cover 41 courses on the 50-course pool. It is not bitwise. Across the three pools the largest relatedness and score difference was 2.1316282072803006e-14 and the largest overlap difference 5.684341886080802e-14. No input lacked chunks or a profile. No tolerance was applied, and no nonzero delta was treated as zero. The two changes were selected and applied. The product scorer computes the same formula on float64 arrays, and the descriptive path filters content and outcomes in SQL.

## The cohorts and scales that do not mix

The early and later measurements use different bases and a different scoring scale. A count, a floor or a saving from one does not transfer to the other.

| Element | Early line | Later line |
|---|---|---|
| Basis construction | Three fixed baskets plus an expanded basket built from three computing seeds and 46 computing next courses | 200 active identities, first 50 compatible representatives, nested prefixes of one, 10 and 50 |
| Basis sizes | 1, 3, 3 and 49 | 1, 10 and 50 |
| Prerequisite mode | Partially covered (`at_least_one`) | All (`all`) |
| Relatedness | Greatest raw chunk cosine, mapped to 0 to 100 | Hub-centred similarity to a trimmed basis profile |
| Overlap | Whole basis at once, with a 0.79 strong-match floor | One basis course at a time, calibrated between 0.20 and 0.90 |
| Relatedness floor | 0.80 | 0.33 |
| Near-duplicate share | 75 percent | 90 percent |
| Overlap weight | 0.30 | 0.0 |

The two columns are not comparable. A 0.80 floor on a greatest-chunk scale and a 0.33 floor on a hub-centred scale are different cuts, and the 75 percent and 90 percent shares are measured against different overlap definitions. The 0.80, 75 and 0.30 values are the early experiment's starting values, not the product's policy. The later runs used the configured policy of 0.33, 90 percent and 0.0.

A count does not cross cohorts either. The early expanded basket returned 30 results at its 30-result cap on a 49-course basis, so its qualified count is unknown. The later 50-course pool held 1,874 ranked candidates and retained 319, and it is a different input set. The early 49-course basis and the later 50-course basis are different constructions, not two versions of one cohort, and the two cohorts share the catalogue rather than a candidate pool.

The later line ran with the overlap weight at 0.0, so score equalled relatedness and the changed overlap meter could not affect the score. A configuration where the overlap meter penalizes score was not measured.

## Corrections and reversals

| Earlier record | Correction | Result that stands |
|---|---|---|
| The centroid scorer fell 6.95, 24.40 and 53.35 percent against the product scorer | The first baseline sample included payload construction and every baseline sample included output dumps, while the centroid timer ended at scorer return | Matched falls of 4.80, 19.68 and 58.85 percent, so the two smaller falls were overstated and the 50-course fall understated |
| A 48-course sorted basis was the stress basket | It dropped one seed by sorting and was not the intended construction, and one of its three runs hit the 30-second cap | A 49-course basis with the seeds in request order and the inactive seed kept, whose three runs took 24.822, 24.944 and 25.449 seconds |
| The first 50-course capture was recorded as completed and given a digest, although no file had been written | Its serializer raised `MemoryError` under the 2.147 GB address-space cap, no fixed input was written, and the batch did not stop as its own rule required | A separate recovery saved the capture at a 1,033.28 MB process peak in 80 seconds and supplied the 50-course comparison, with split 60-second timers as a recorded deviation |
| The first two composition processes were read as two correction runs | One planned run failed while assembling its warmup record, the first correction failed while serializing its result, and five processes ran in total | The recorded one-course numbers come from the second correction, which ran the same code as the other two pools |

The latency target was not met. The complete command fell from a range of 24.345 to 25.449 seconds to a range of 1.644 to 2.760 seconds, and the residual was left without a claim that the target had been reached. No further optimization loop ran.

## What the line applied

| Change | Status | Evidence scope |
|---|---|---|
| float64 NumPy scorer evaluating the product formula | Selected and applied | Three fixed pools of 42, 435 and 1,874 candidates |
| Descriptive-only projected read, filtering content and outcomes in SQL | Selected and applied | The same three pools |
| Request-local occurrence index and once-prepared overlap | Applied, with final reports captured from the product | Four fixed baskets, including the 49-course basket |
| Centroid coverage | Dropped | The same three pools |

No recommendation threshold was selected as a product setting. The measured 0.80 floor, 75 percent share and 0.30 weight were starting values, and the 0.33 floor, 90 percent share and 0.0 weight were the configured policy the later runs read.

## What the line does not establish

- No report carries a relevance judgment, a user study or a recommendation-quality measurement. A count, a retained set, a rank or a meter is an arithmetic outcome.
- The fixed pools are the product's retrieval outputs for fixed bases, not a full-catalogue sample. They establish no retrieval equivalence and no coverage of other subjects.
- The complete command is not a web request. No web server, admission control, worker forwarding, response delivery or concurrent load was measured.
- The early candidate pool came from an approximate nearest read with 40 chunks per basis chunk, a shortlist cap of 100 and a result cap of 30, all of the measured build. Every early count is conditional on those cuts.
- The centroid memory figures are Python allocation traces for one scorer call or process-wide resident peaks. They do not isolate per-algorithm memory.
- The scorer, read and composition savings are separate measurements on separate timers, so they do not add up to a command or request saving.

## Untested questions

Each question below is untested.

- Whether a human rating agrees with the retained sets, ranks and meters, including the eight centroid removals and 253 rank changes on the 50-course pool.
- Whether the early floor and share transfer to a humanities or social-science basis, or to a single course outside computing.
- Whether a configuration where the overlap meter penalizes the score changes the centroid outcome, since the later line ran at a weight of 0.0.
- Whether a cheaper coverage step, such as candidate chunks against basis course centroids, preserves the chunk-pair retained set.
- Whether the request-local changes hold their times and report parity under concurrent load and on a web request path. Whether the 1.23-second nearest query and 0.45-second overlap stage can fall further without a stored change or another index.
