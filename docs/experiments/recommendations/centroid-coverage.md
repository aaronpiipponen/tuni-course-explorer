# Centroid coverage in recommendations

Course-centroid coverage is an approximation of the exact chunk-pair overlap that the recommendation scorer computes, measured here for runtime, memory and outcome changes.

**Evidence status:** Corrected. **Run date:** 21 October 2026.

## The question

[Recommendations](/docs/reference/glossary.md#discovery-and-the-structure-of-studies) rank candidate courses by the similarity of their teaching text to the completed [basis](/docs/reference/glossary.md#prerequisites-and-routes). Each result also carries an overlap meter, and a candidate whose text overlaps one basis course above a configured share is left out as a [near-duplicate](/docs/reference/glossary.md#discovery-and-the-structure-of-studies). The exact coverage step compares every descriptive [chunk](/docs/reference/glossary.md#capture-and-data-preparation) of a candidate with every descriptive chunk of the basis. That work grows with the product of the candidate chunk count and the basis chunk count.

The experiment asked how much scorer time and memory a coarser coverage step would save, and which recommendation outcomes would change. The alternative replaces chunk pairs with one centroid vector per course. It keeps the relatedness profile, thresholds, tie order and every other part of the scorer, and substitutes coverage only. A separate composition measurement asked whether the alternative would add value after formula-preserving vectorization and narrowed reads.

The exact chunk-pair scorer defines the reference outcome. No relevance judgment, user study or recommendation-quality measurement ran. The outcomes in this report are arithmetic: the retained set, order, exclusion reason, overlap meter, relatedness and score.

## Fixed pools and bases

The captured catalogue held 11,086 courses, each counted once through a representative version (4,543 active), and 58,962 teaching-text chunks. The fixed sample was drawn once from 200 stored active course identities that had a completed descriptive chunk compatible with the embedding configuration. The identities were resolved once through the product's represented-course summaries, and the first 50 compatible representatives in shortlist order formed the 50-course basis. The 10-course and single-course bases are the first 10 and the first representative of that same order, so the three bases are nested. The selection seed was 20261021.

Each request used `basis=completed`, `mode=all`, `display_language=en`, `include_inferred=false` and `active_only=true`, with selected courses equal to completed courses equal to the basis. The candidate pools were the product's actual retrieval and eligibility outputs for each basis, after its next-course exclusions. They were not restricted to the 200 identities used for selection.

| Setting | Value |
|---|---|
| `RECOMMENDATION_CHUNK_TOP_K` | 40 |
| `RECOMMENDATION_MIN_RELATEDNESS` | 0.33 |
| `RECOMMENDATION_NEAR_DUPLICATE_PERCENT` | 90 |
| `RECOMMENDATION_OVERLAP_PENALTY_WEIGHT` | 0.0 |
| `COMPARISON_OVERLAP_FLOOR` | 0.20 |
| `COMPARISON_OVERLAP_CEILING` | 0.90 |

The pools held 42, 435 and 1,874 ranked candidates for the single-course, 10-course and 50-course bases. The chunk counts show why the coverage step grows:

| Basis | Basis chunk rows | Candidate chunk rows | Chunk pairs, upper bound |
|---|---:|---:|---:|
| 1 | 2 | 137 | 274 |
| 10 | 39 | 1,771 | 69,069 |
| 50 | 209 | 7,657 | 1,600,313 |

The pair count is an upper bound because candidates below the relatedness floor never reach the coverage products. The chunk rows are the descriptive content and learning-outcomes chunks available for each course, in either language. The vectors are stored BGE-M3 embeddings with 1,024 components, so no embedding model ran during the measurements.

## The coverage formulas

Both formulas begin from hub-centred unit vectors. Content chunks subtract the embedding hub, and learning-outcomes chunks subtract the outcomes hub. Candidate and basis chunks are pooled without a language filter, so a Finnish chunk can match an English chunk. The relatedness profile is shared and identical in both variants.

For a candidate course, let `u_i` be the hub-centred unit vector of candidate chunk `i` and `w_i` its character count. Let `v_j` be the hub-centred unit vector of basis chunk `j`, and let `g(j)` be the basis course of that chunk. The calibration maps a raw cosine ratio `r` to a percentage:

```text
overlap_percent(r) = 100 * clip((r - 0.20) / (0.90 - 0.20), 0, 1)
```

The exact chunk-pair formula computes:

```text
covered = sum over i of w_i * max(0, max over j of u_i . v_j)
whole_basis_overlap = overlap_percent(covered / sum over i of w_i)
strongest_course_overlap = max over basis courses g of
  overlap_percent((sum over i of w_i * max(0, max over j in g of u_i . v_j))
                  / sum over i of w_i)
```

A candidate is excluded as a near-duplicate when `strongest_course_overlap` reaches 90 percent. The whole-basis meter is the character-weighted mean of each candidate chunk's best match anywhere in the basis. The strongest-course meter repeats that calculation inside each single basis course. A broad basis therefore retains a candidate that shares content with many basis courses, and a candidate that duplicates one basis course is removed. The product applies its near-duplicate cut one basis course at a time, on its own overlap scale, as [Coverage and ranking](/docs/backend/search-and-discovery/coverage-and-ranking.md) describes.

The centroid alternative compresses each course to one vector. For candidate centroid `c` and basis course centroid `b_g`:

```text
c = unit(mean of the candidate's hub-centred unit chunk vectors)
b_g = unit(mean of basis course g's hub-centred unit chunk vectors)
s_g = max(0, c . b_g)
whole_basis_overlap = overlap_percent(max over g of s_g)
strongest_course_overlap = max over g of overlap_percent(s_g)
```

Because the calibration is monotonic, the centroid variant's whole-basis overlap and its strongest-course overlap are the same value. Every basis course centroid is compared, and the maximum is taken. The candidate's chunks contribute equally through the centroid, and their character counts play no part in coverage.

Relatedness is identical in both variants. The basis course centroids are first compared with their own unit mean, and only those at or above the median cosine are kept. The unit mean of the kept centroids is the profile `p`, and relatedness is `100 * max(0, c . p)`. The trim kept one, five and 25 course centroids on the three bases. A single-course basis has no trim.

Only coverage is substituted. The relatedness floor, near-duplicate threshold, overlap penalty, name-and-code tie order and output type are the same. With `RECOMMENDATION_OVERLAP_PENALTY_WEIGHT=0.0`, score equals relatedness in both variants. The product's own policy for the relatedness floor, near-duplicate share and overlap penalty is stated in [Recommendations](/docs/backend/search-and-discovery/recommendations.md).

## Scorer runtime

### Recorded series and their boundaries

The first measurements recorded three samples per scorer series. The basis 50 capture ran after two earlier captures and produced a comparison only after a recovery, described below. The recorded medians were:

| Basis | Chunk-pair samples (s) | Centroid samples (s) | Chunk-pair median (s) | Centroid median (s) | Recorded fall | Whole command (s) |
|---|---|---|---|---|---:|---:|
| 1 | 0.0498, 0.0481, 0.0483 | 0.0447, 0.0449, 0.0451 | 0.0483 | 0.0449 | 6.95 percent, 0.00336 s | 1.391 |
| 10 | 0.7535, 0.7497, 0.7530 | 0.5657, 0.5692, 0.5932 | 0.7530 | 0.5692 | 24.40 percent, 0.18374 s | 13.096 |
| 50 | 6.4686, 6.4536, 6.6264 | 3.0178, 2.9817, 3.0780 | 6.4686 | 3.0178 | 53.35 percent, 3.4508 s | 29.306 |

Process CPU medians fell by 7.10, 24.55 and 53.76 percent in the same series. These recorded falls are not an algorithm-only speedup. The timers had different boundaries. The first chunk-pair sample was the product scorer call inside the extraction command, and it included construction of the captured scorer-input payload as well as output model dumps. The other two chunk-pair samples called only the scorer on captured inputs, and they included output model dumps. The centroid samples ended when the scorer returned, before the output dumps. The recorded series therefore compared a broader chunk-pair timer with a narrower centroid timer. The 53.35 percent figure on basis 50 compares those series and is not the isolated coverage difference.

The whole command took 1.391 s, 13.096 s and 29.306 s. It includes the next-course read, approximate nearest-neighbor (ANN) retrieval, chunk reads, capture observers and payload hashing. The recorded scorer fall equals 0.24 percent of the single-course command, 1.40 percent of the 10-course command and 11.78 percent of the 50-course command. Those fractions are not an observed alternative whole-command speedup. No uninstrumented alternative whole command was measured.

### Matched measurement

A separate measurement put the product scorer, the centroid scorer and a formula-preserving vectorized scorer in each timed sample on identical captured inputs. One fatal 60 s timer enclosed the three calls. The product and centroid calls used the same raw carriers, settings and output type, with preparation and result construction inside their timers. This report uses those two legs. The vectorized leg belongs to the formula-preserving comparison.

| Basis | Product samples (s) | Centroid samples (s) | Product median (s) | Centroid median (s) | Wall fall | CPU median fall |
|---|---|---|---|---|---:|---:|
| 1 | 0.047290, 0.048221, 0.047667 | 0.045379, 0.047442, 0.045232 | 0.047667 | 0.045379 | 4.80 percent, 0.002288 s | 4.79 percent, 0.002269 s |
| 10 | 0.743603, 0.754062, 0.768027 | 0.605629, 0.605267, 0.608107 | 0.754062 | 0.605629 | 19.68 percent, 0.148432 s | 19.74 percent, 0.148516 s |
| 50 | 6.268246, 6.570340, 6.950881 | 2.706332, 2.703793, 2.701002 | 6.570340 | 2.703793 | 58.85 percent, 3.866547 s | 58.93 percent, 3.863571 s |

The matched centroid scorer reproduced the saved centroid output on all three bases, including the eight removals and 253 rank changes on basis 50. The correction changes the earlier picture in both directions. On the single-course and 10-course bases the recorded falls were overstated, at 6.95 and 24.40 percent against matched falls of 4.80 and 19.68 percent. On the 50-course basis the recorded fall was understated, at 53.35 percent against a matched fall of 58.85 percent. The matched figures are the ones that stand as the scorer comparison.

The chart shows the matched wall medians.

![Matched wall time for the chunk-pair and centroid scorers on the three fixed bases, with the centroid scorer faster on every basis and the gap widest on the 50-course basis.](/docs/charts/recommendation-centroid-scorer-wall.svg)

The fixed call order in each sample was product, centroid, then the vectorized scorer. Cache warmth may favor the later calls, so the centroid saving is bounded by that order. The measurement is scorer-only. It excludes capture loading, output serialization, diagnostics, hashing, ANN retrieval and HTTP serving.

## Which outcomes change

The retained sets and order were identical on the single-course and 10-course bases. Every overlap value changed, and every relatedness and score value was exactly equal. On the 50-course basis the centroid variant retained 311 courses against 319, removed eight and changed 253 of the 311 common ranks. No course was added.

| Basis | Ranked candidates | Retained, chunk-pair | Retained, centroid | Removed | Ranks changed | Relatedness-floor exclusions | Near duplicates, chunk-pair | Near duplicates, centroid |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 42 | 37 | 37 | 0 | 0 | 5 | 0 | 0 |
| 10 | 435 | 69 | 69 | 0 | 0 | 366 | 0 | 0 |
| 50 | 1,874 | 319 | 311 | 8 | 253 | 1,532 | 23 | 31 |

The chart shows the retained counts and the changed ranks.

![Retained course counts under chunk-pair and centroid coverage and the count of changed ranks, showing no change on the single-course and 10-course bases and eight removals with 253 rank changes on the 50-course basis.](/docs/charts/recommendation-centroid-retained.svg)

All eight removals fail the 90 percent near-duplicate test under centroid coverage. Their chunk-pair overlap was below the threshold and their centroid overlap was above it. The baseline near-duplicate count was 23 and the centroid count was 31. Both variants excluded 1,532 candidates at the 33 percent relatedness floor. No candidate lacked chunks or a profile.

| Chunk-pair rank | Code | Relatedness | Chunk-pair overlap | Centroid overlap |
|---:|---|---:|---:|---:|
| 59 | `MEDANPSTOI` | 41.2926 | 89.2482 | 91.3468 |
| 119 | `ROBO.010` | 39.0913 | 75.1257 | 97.3042 |
| 126 | `MEDAHPAKÄY` | 38.8928 | 77.1136 | 94.0705 |
| 130 | `MEDAKHETOI` | 38.8224 | 88.0251 | 90.6867 |
| 136 | `MEDAAKUTOI` | 38.5215 | 89.8653 | 92.3582 |
| 168 | `SSR.GEN.110` | 37.1659 | 65.6158 | 94.5232 |
| 274 | `KAN.211` | 34.1985 | 73.1193 | 91.0360 |
| 283 | `MEDAINFERI` | 33.9831 | 78.1853 | 94.6116 |

For these eight courses the centroid overlap is also their centroid strongest-course overlap. The relatedness values are identical, so the removals come from coverage alone. The rank shifts of the common courses were one to eight places, with a median of six. The scores are identical, so the shifts follow from renumbering after the eight removals.

Every common retained course changed its overlap value on every basis. The direction was mixed:

| Basis | Common retained courses | Positive overlap deltas | Negative overlap deltas |
|---|---:|---:|---:|
| 1 | 37 | 26 | 11 |
| 10 | 69 | 61 | 8 |
| 50 | 311 | 225 | 86 |

The chart shows the two directions by basis.

![Counts of positive and negative whole-basis overlap deltas under centroid coverage, showing mixed directions on every basis and a larger positive count on the 50-course basis.](/docs/charts/recommendation-centroid-overlap-deltas.svg)

On basis 50 the overlap delta had a mean of +5.2189, a median of +4.9668, a minimum of -23.7623 and a maximum of +29.7677 percentage points. The exact deltas are mixed in sign and size, so the centroid meter is neither a uniform inflation nor a uniform reduction of chunk-pair overlap. The hypothesis that centroid coverage would preserve the recommendation set failed on the 50-course basis.

The change is an approximation effect in the overlap meter and the near-duplicate rejection. It is not evidence that the removals are wrong, and it is not evidence that the recommendations improve. No quality judgment was measured.

## Memory

The scorer trace is the `tracemalloc` peak for the Python allocations of the scorer call. It is not the peak resident set of the coverage formula alone. Process peak RSS is process-wide and includes database reads, capture parsing, carrier conversion, interpreter pages and written payloads. It is not a controlled per-algorithm memory comparison.

| Basis | Chunk-pair trace (MB) | Centroid trace (MB) | Trace change | Capture process peak (MB) | Centroid process peak (MB) |
|---|---:|---:|---:|---:|---:|
| 1 | 0.601 | 0.634 | +5.57 percent | 142.78 | 110.88 |
| 10 | 2.485 | 2.519 | +1.34 percent | 498.16 | 356.53 |
| 50, first capture | not recorded | not recorded | not recorded | 1,399.3 | not run |
| 50, recovery | 10.329 | 10.319 | -0.10 percent | 1,033.28 | 1,175.13 |

The trace was 5.57 percent larger on the single-course basis, 1.34 percent larger on the 10-course basis and 0.10 percent smaller on the 50-course basis. The Python allocations range from 0.6 MB to 10.3 MB, so the trace says little about the memory of a serving process.

The capture process also performed the database reads, next-course compilation, ANN retrieval and fixed-input write. Its own payload snapshot before writing was 132.45 MB on the single-course basis and 364.09 MB on the 10-course basis. Writing the 5.4 MB and 64 MB fixed inputs raised the process peaks to the table values. The basis 50 recovery centroid loaded a 289.41 MB fixed input and built candidate objects. Its process peak was higher than the recovery capture peak, but the measurements did not isolate the cause. The centroid processes opened no database connection. The RSS values in the table do not isolate the memory of either coverage formula.

## The basis 50 failure and recovery

The first basis 50 capture completed its product work and then failed while saving its input. It recorded 49.811795 s user CPU, 1.148843 s system CPU, a 1,399.3 MB process peak, two read-only connections and 22 rollback events. The serializer raised `MemoryError` while encoding the capture under the 2.147 GB address-space cap. No fixed input file was written.

The batch nevertheless recorded the capture as completed and gave it a digest, although no file had been written. That record is kept as failed evidence. No basis 50 coverage result came from that attempt.

The batch then ran the single-course and 10-course centroid measurements. That continued after a failure that required an immediate stop, so the batch did not comply with its own stop rule. The two measurements are preserved and are reported as comparisons of the single-course and 10-course bases, not as 50-course coverage.

The writer was corrected in three ways. It writes JSON in bounded chunks, it repeats no payload in a capture's completion entry, and its digest comes from the exact-file write. The failed attempt was not repeated in that batch.

A separately authorized recovery then saved the basis 50 capture and ran its comparison. The recovery capture took 80 s wall and peaked at 1,033.28 MB. The recovery centroid took 111 s wall and peaked at 1,175.13 MB. Both ran once, one at a time, after a free-memory check. The dataset identity, selection, settings, both hubs and the 50 basis identities matched the fixed input.

| Process | Outcome | Wall (s) | Peak RSS (MB) |
|---|---|---:|---:|
| Basis 1 capture | completed | 2 | 142.78 |
| Basis 10 capture | completed | 18 | 498.16 |
| Basis 50 capture, first | failed, `MemoryError` | 62 | 1,399.3 |
| Basis 1 centroid | completed | 1 | 110.88 |
| Basis 10 centroid | completed | 14 | 356.53 |
| Basis 50 recovery capture | completed | 80 | 1,033.28 |
| Basis 50 recovery centroid | completed | 111 | 1,175.13 |

Seven processes ran against a ceiling of nine. The three captures, the two centroid comparisons, the recovery capture and the recovery centroid are all counted. The recovery used one 60 s timer around the product command and a separate 60 s timer around serialization, not one cumulative timer through both, so no cumulative-cap pass is claimed. The 180 s process limit and the 2.147 GB address-space cap held in every process.

## Composition after vectorization

A separate measurement paired formula-preserving vectorized chunk coverage with descriptive-field-only reads on the same fixed bases, then swapped only the coverage step. On the single-course, 10-course and 50-course bases the centroid leg was 1.35 and 0.68 percent faster and 0.84 percent slower than the chunk leg. Those differences were 0.0019 s, 0.0065 s and 0.0420 s of recorded wall median, below one percent of the pair and inside run noise.

The candidate chunk read dominated the composition at 4.05 s of the 4.97 s chunk leg on basis 50. The vectorized chunk scorer already cost 0.5380 s on that basis. The centroid scorer did not improve on the vectorized scorer. Centroid coverage therefore adds no consistent fixed-pool composition saving after vectorization and narrowed reads, and the centroid candidate was dropped. The full composition matrix is in [Vectorization and narrow reads](/docs/experiments/recommendations/vectorization-and-narrow-reads.md).

That result removes the runtime case for centroid coverage. The scorer-only saving is measured under matched boundaries, but it does not survive as a composition or whole-request saving once the formula-preserving vectorization removes most of the scoring time. The centroid variant changes outcomes on basis 50, and it has no quality validation.

The centroid change and the formula-preserving vectorization gain must not be combined into one equivalent speedup. Vectorization preserves the product formula and changes only last binary digits. Centroid coverage changes the formula, removes courses and changes ranks. They answer different questions and are not additive.

## What the results do not establish

- The fixed pools are the product's retrieval outputs for three nested bases, not a full-catalogue sample. They establish no retrieval equivalence, full-catalogue coverage or recommendation quality.
- No relevance judgment, user study or held-out recommendation comparison ran. A retained set, rank or overlap value is not a quality measure.
- With `RECOMMENDATION_OVERLAP_PENALTY_WEIGHT=0.0`, score equals relatedness. A configuration where the overlap meter penalizes score was not measured, so the score effect of the changed overlap is untested.
- The matched saving is a scorer-only measurement. It excludes capture loading, retrieval, serialization, diagnostics, HTTP serving and response delivery.
- The fixed call order may favor the centroid call through cache warmth.
- Process RSS is process-wide and is not per-algorithm memory. The traced peak covers Python allocations for the scorer call only.
- The recovery used split 60 s timers rather than one cumulative timer through capture serialization, so the recovery has a recorded timer deviation.
- The centroid candidate was dropped after the composition measurement.

## Setup details

The work ran on a 4-core aarch64 server with 23.6 GB of RAM. One heavy process ran at a time after a free-memory check. Each process had a 180 s wall limit and a 2.147 GB address-space cap. Every scorer sample ran under a 60 s fatal timer.

The scorer used Python 3.14.3 and NumPy 2.4.6 with scipy-openblas 0.3.31 (build 188.0) in the matched measurement. The earlier scorer measurements used the product Python implementation. The thread environment set `OPENBLAS_NUM_THREADS=1`, `OMP_NUM_THREADS=1`, `MKL_NUM_THREADS=1`, `BLIS_NUM_THREADS=1` and `VECLIB_MAXIMUM_THREADS=1` before product imports.

Every database session ran with `default_transaction_read_only=on` and a 30 s statement timeout. The capture processes opened two or three connections and rolled back their reads. The centroid processes opened no connection. No write was attempted.

Each centroid series ran one warmup before its recorded samples, and the matched measurement ran one paired warmup before three recorded paired samples. Database and CPU cache warmth was not controlled. Three recorded samples per series give medians, not a distribution or a confidence interval.

## Open questions

- Whether a cheaper coverage step, such as comparing candidate chunks with basis course centroids, preserves the chunk-pair retained set. Untested.
- Whether centroid coverage changes scores and order when `RECOMMENDATION_OVERLAP_PENALTY_WEIGHT` is above zero. Untested.
- Whether the eight removals and 253 rank changes are acceptable in use, and whether they improve or worsen recommendations. No user or quality measurement ran. Untested.
