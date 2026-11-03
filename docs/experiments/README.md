# Experiments

The experiments record what the project measured about prerequisite inference, search and translation, recommendations, graph routes and serving, with the methods, results and open questions behind each.

The section groups the work into five areas. Each area overview introduces every report in its line, and this page states the shared setup once and the questions that cross the areas. Every value belongs to the report that measured it. The reports do not share one build, one payload set or one warm state, and each report states the input set, model versions, settings and timing boundary its numbers need. The [glossary](/docs/reference/glossary.md) defines the product terms the reports use.

## The catalogue the experiments read

The experiments that read the catalogue used one captured snapshot of the Tampere University curriculum from the public curriculum source, not the invented example dataset that an installation loads. The capture covers the academic years 2006-2007 to 2026-2027, with a three-year activity window set by `ACTIVE_ACADEMIC_YEAR_WINDOW`.

The analysis snapshot holds 11,086 courses, each counted once through a representative version, of which 4,543 are active. It holds 9,901 eligible module versions and 58,962 teaching-text chunks, each with a stored BGE-M3 vector of 1,024 components. The catalogue carries teaching text in Finnish and English. These counts describe that snapshot, not every dataset revision or capture run.

A capture count and a normalized catalogue count measure different things. A capture stores course and module objects, and normalization reconciles them into the course versions a catalogue read counts. [Curriculum capture and replay](/docs/experiments/runtime-storage-and-serving/curriculum-capture-and-replay.md) owns what one capture stores, how its manifest is verified and how a source-free replay normalizes it.

## The hardware

Inference, reranking and prompt work ran on an AMD Radeon RX 9070 XT (16 GB model) on ROCm 7.2.1, in a machine with 33.4 GB of usable RAM. The translation model ran on the same card model, and the hardware record for its GPU names ROCm without a version.

Many search, recommendation, graph and serving measurements name a 4-core aarch64 Neoverse N1 server with 24.1 GB of RAM. Several native comparisons of 28 to 31 October 2026 name that server with PostgreSQL 18.6 and pgvector 0.8.6.

The capacity ladders name a 4-core aarch64 server with a 4.295 GB web cap. The capture records state no hardware. A hardware specification in this section belongs to the report that recorded it, and no value is carried from another line.

## Evidence status

Each report carries one label in a short line near the top, describing the evidence behind its main result. A report that holds more than one kind of evidence carries the label of its main result. The label describes the evidence, not the quality of the page or the weight of the result.

| Label | What the evidence is |
|---|---|
| Exploratory | The first measurements of a question, which set its cohorts and parameters rather than settle a comparison. |
| Comparative | Two or more variants measured on the same inputs, where the difference between them carries the claim. |
| Observational | A read of a running system or a profile of its behavior, with no variant measured against it. |
| Corrected | A line where a measurement changed the main result, reported with the result that stands. |
| Reproduced | The result was obtained again in an independent rerun. |

Each method page carries one label as well. An area overview carries none, because it reports no single result.

## What a report states

Each report keeps observation, interpretation, a failed hypothesis and an untested question apart. An observed result is what a measurement returned. An interpretation is what the report reads in that result. A failed approach is a finding, stated with what was tried, how it was measured, what it produced and why it failed. An untested question is one the line did not measure.

A report states the result that stands. Each report states the baselines a follow-up compares against, and each states the settings, cohort and timing boundary its numbers need.

## Inference

The inference line asked whether one local language model could propose direct prerequisites and equivalence groups for every active course from teaching text alone. It separated fit and throughput, candidate retrieval, the packet the model sees, judging, confidence, prompt and schema tuning, held-out quality and the full-catalogue run. The [Inference experiments](/docs/experiments/inference/README.md) overview introduces all nine reports.

On 150 held-out targets, Qwen3.8-27B IQ3-MIX returned 150 valid results, and the blind judge marked 111 of its 178 findings supported, including 54 of 100 required findings. The model and a policy with no confidence cutoff, no finding filter and no demotion were selected on 29 September 2026. The full run then published all 4,543 active targets in one cycle, 2,348 with a prerequisite expression and 2,195 complete empty, with 4,520 served locally and 23 oversize packets sent whole to DeepSeek V4.1 Flash. [Held-out local model quality](/docs/experiments/inference/held-out-model-quality.md) and [full-catalogue inference run](/docs/experiments/inference/full-catalogue-inference-run.md) own the results.

The candidate cut, not the pool, bounds recall. Judged support is not the official record, because it counts only emitted findings, and the 2,195 empty sets cannot separate a correct empty answer from an omission. A supported share counts supported findings over emitted findings, while the packet comparison used a weighted score that counts a partly supported finding as 0.5. The two are not interchangeable. Every saved answer is one sample, and no human agreement measurement exists. [Candidate retrieval and reranking](/docs/experiments/inference/candidate-retrieval-and-reranking.md), [candidate packet selection](/docs/experiments/inference/candidate-packet-selection.md) and [reference answers and judging](/docs/experiments/inference/reference-answers-and-judging.md) own the evidence.

## Search and translation

The search and translation lines asked two separate questions. Translation asked whether a generated translation retrieves its official counterpart without breaking search. Search asked whether a cheaper exact read, a bounded approximate index, SQL lexical matching, or one normalized projection with a native fuzzy scorer could preserve the product's result. The [Search and translation experiments](/docs/experiments/search-and-translation/README.md) overview introduces all five reports.

TranslateGemma 12B at Q5_K_M retrieved its paired official counterpart first in 59 of 60 cases, a within-cell retrieval proxy rather than a rating of fluency, terminology or reader preference. The product semantic read is the packed exact relation, which used 7.6 times fewer core-seconds than the product SQL with every measured result equal. The normalized lookup projection and native fuzzy stage were applied, with all 16 cells for each of the three matchers equal and all 64 score-array comparisons finding zero differences. [Machine translation as retrieval-preserving transformation](/docs/experiments/search-and-translation/translation-and-retrieval.md), [packed exact semantic search](/docs/experiments/search-and-translation/packed-exact-semantic-search.md) and [lexical lookup projection and native fuzzy matching](/docs/experiments/search-and-translation/lexical-lookup-projection-and-native-fuzzy.md) own the results.

The alternatives did not all survive. A centred SQL read was exact and faster per query, and no read from that comparison was selected. No approximate index setting returned the exact set for all four vectors. SQL lexical forms needed explicit `C` collation on the three text keys to match the order in all 32 sampled cells, and no SQL form was selected. The search measurements stop at different boundaries, and none measures a browser together with the network and rendering. Preservation is not relevance. [Exact and approximate semantic retrieval](/docs/experiments/search-and-translation/semantic-retrieval.md) and [lexical matching equivalence and collation](/docs/experiments/search-and-translation/lexical-matching-and-collation.md) own the failures.

## Recommendations

The recommendation line asked how recommendations score a basis, where a request spends its time, and which cheaper step keeps the recommended set. A formula-preserving change alters how the same computation runs, while a formula-changing approximation alters what is computed. The [Recommendation experiments](/docs/experiments/recommendations/README.md) overview introduces all eight reports.

On identical candidate inputs, the product scorer returned the same candidates, order, meters and derived-text flag as the Python scorer, with fewer core-seconds at every measured scorer endpoint. The course-centroid candidate prefilter and the stored neighbour table were selected and applied. At the five-course basis, the stored table returns 644 of 720 rows after request exclusions, so it is an approximation for those exclusions. Centroid coverage was dropped because it removed eight courses and changed 253 of 311 common ranks on the 50-course pool. [Native recommendation scoring](/docs/experiments/recommendations/native-recommendation-scoring.md), [course-centroid candidate prefilter](/docs/experiments/recommendations/centroid-candidate-prefilter.md), [nearest-neighbour retrieval for recommendations](/docs/experiments/recommendations/nearest-neighbour-retrieval.md) and [centroid coverage in recommendations](/docs/experiments/recommendations/centroid-coverage.md) own the results.

No report measures recommendation quality. A retained set, a rank, a meter or a saving is an arithmetic outcome, and no relevance judgment or user study exists.

## Graph and route algorithms

The graph and route line asked whether the exact minimum-credit route can be trusted on the full catalogue, what it may claim after its allocation limit, why four graph roots failed to prepare, and whether one report can carry the calculation and the drawing from two identities. The [Graph and route algorithm experiments](/docs/experiments/graph-and-route-algorithms/README.md) overview introduces all seven reports.

The exact route is bounded at 700,000 compact nodes with one greedy restart, and the three approximate routes charge 204.00, 211.00 and 194.00 new credits. All 506 compared scenarios returned the same route in the Python and TypeScript implementations, and four of the 510 were not compared because preparation failed. The compact report, which carries the calculation and the drawing from two identities, kept 104 of 110 cases identical, allowed 82 drawings and refused 28 at the 500-element drawing allowance. The native compiler, identities, projection and record view were applied, and every compared output was byte-identical. [Minimum-credit routes](/docs/experiments/graph-and-route-algorithms/minimum-credit-routes.md), [route solver parity](/docs/experiments/graph-and-route-algorithms/route-solver-parity.md), [compact graph identity](/docs/experiments/graph-and-route-algorithms/compact-graph-identity.md), [graph report payload and projection](/docs/experiments/graph-and-route-algorithms/graph-report-payload-and-projection.md) and [native prerequisite compilation and identity](/docs/experiments/graph-and-route-algorithms/native-prerequisite-compilation.md) own the results.

The applied cycle cut, which drops an occurrence whose offered equivalent already sits on the ancestor path, finishes the four roots as complete commands in 2.36 to 3.01 seconds. Those commands prepared the graph structure and did not run the route calculation. In the separate route comparison, state and total new credits were preserved, but structure equality was not established. Structural route deduplication was not promoted. No measurement joins compilation, search, projection and payload into one route latency, and no compressed body was rendered in a browser. The approximate totals are not minima. [Cyclic graph compilation cost](/docs/experiments/graph-and-route-algorithms/cyclic-graph-compilation.md) and [structural route deduplication](/docs/experiments/graph-and-route-algorithms/structural-route-deduplication.md) own those results.

## Runtime, storage and serving

The runtime, storage and serving line followed one stored row from the database to a response and to the capture that produced the catalogue. It asked what each read shape retains, what an artifact set and shared stores save, what one request costs, how many simulated users a stack serves before light throughput stops growing, and what one capture produces. The [Runtime, storage and serving experiments](/docs/experiments/runtime-storage-and-serving/README.md) overview introduces the thirteen reports and the [serving load method](/docs/experiments/runtime-storage-and-serving/serving-load-method.md).

The full-catalogue read projection was applied with byte-identical command outputs. The bounded read returned the same 319 results at a 171.5 MB process peak against 546.9 MB, about two seconds slower, and was not adopted. The descriptive chunk cache was selected and applied on the measured build, and the artifact set and shared stores cut the mixed-load total by 14.6 percent. The product answers descriptive chunk reads from the shared serving store. Four worker processes and admission control are applied, with a saturated heavy budget of 40 core-seconds. [Full-catalogue read projection](/docs/experiments/runtime-storage-and-serving/full-catalogue-read-projection.md), [read memory and bounded reads](/docs/experiments/runtime-storage-and-serving/read-memory-and-bounded-reads.md), [descriptive chunk caching](/docs/experiments/runtime-storage-and-serving/descriptive-chunk-caching.md), [serving artifact build and shared stores](/docs/experiments/runtime-storage-and-serving/serving-artifact-build-and-shared-stores.md) and [serving request cost and admission curves](/docs/experiments/runtime-storage-and-serving/serving-request-cost-and-admission.md) own the results.

On workload version 3, the build with the native libraries served 40.041 light requests a second at 750 users, the highest of the four stacks, and its mixed profile served 33.093 at 500 users before a 91.2 percent fall at 750. The capacity ladders ran before `WEB_MALLOC_ARENA_MAX = 2` was applied, and no ladder ran with the cap. The analysed capture evidence is one externally timed capture of one curriculum period and two source-free replays of a separate full-catalogue capture, and the two captures are not compared on speed or scale. [Serving capacity](/docs/experiments/runtime-storage-and-serving/serving-capacity.md), [web memory and allocator retention](/docs/experiments/runtime-storage-and-serving/web-memory-and-allocator-retention.md) and [curriculum capture and replay](/docs/experiments/runtime-storage-and-serving/curriculum-capture-and-replay.md) own those results.

## What the experiments establish across areas

### Preservation is not quality

The section keeps two questions apart. One asks whether a change returns the same result, and the other asks whether the result is useful. The packed exact relation, the lookup projection with native fuzzy matching, the native recommendation scorer, the course-centroid prefilter, the read projection and the native prerequisite stages preserved their measured results and were applied. The centroid coverage, the stored neighbour table, the approximate semantic index and the greedy route restart changed an outcome, and each is reported as an approximation or a dropped alternative. No preservation measurement becomes a quality measurement.

### Two proxies stand in for a property

Judged support reports what a judge found in the supplied teaching text, not what the university requires, and it counts only the findings a model emitted. The translation result reports whether generated text retrieves its official counterpart within a cell, not whether a reader would accept the translation. Both informed a selection, and neither is a product-quality score. The supported share and the weighted judged support score answer different questions and are not interchangeable.

### Savings stop at their boundary

Every saving stops at the boundary it was measured on. Core-seconds, wall time, one database read, one in-process command, one HTTP request and one capacity level are separate measurements, and values from one do not add to another. The section has no paired browser measurement that joins query embedding, the read, the network and rendering. The capacity ladders use a synthetic client, and their user counts are virtual users. The cohorts are small and fixed, and one case moves a ten-case translation cell's rate by 0.10.

### Memory values do not compose

The memory results are of different kinds and do not compose. A process peak, a Python object-graph size, a cgroup charge, a container cap and an address-space limit answer different questions. A sum of the section's memory values would describe no measured process.

### A measured candidate is not an applied setting

The reports separate a measured candidate from an applied setting. The packed exact relation, the lookup projection with native fuzzy matching, the native recommendation scorer, the course-centroid prefilter, the stored neighbour table, the read projection, the artifact set and shared stores, four worker processes, admission control with a saturated heavy budget of 40 core-seconds, gzip level 6 and `WEB_MALLOC_ARENA_MAX = 2` were selected and applied. The centroid coverage, structural route deduplication, the approximate semantic index and the SQL lexical forms were not. A measured value is not the product's behavior unless the report states the selection.

## Open questions across the areas

Each question below is untested. None has a measurement in the section, and the area overviews carry further untested questions of their own.

- Human judgement and omissions. No agreement measurement exists between the blind judge and a human reader, no relevance rating covers a retained recommendation set or a changed rank, and no human rating covers translation fluency, terminology or adequacy. No measurement compares a published inferred set against the university's official prerequisite record, so an omitted true prerequisite is uncounted. [Held-out local model quality](/docs/experiments/inference/held-out-model-quality.md), [centroid coverage](/docs/experiments/recommendations/centroid-coverage.md) and [machine translation as retrieval-preserving transformation](/docs/experiments/search-and-translation/translation-and-retrieval.md) state the limits behind these questions.
- A second sample and a repeated run. Every saved inference answer is one sample, the full-catalogue run has no unchanged rerun and no changed-source recalculation, and the capture analysis covers one externally timed capture. [Full-catalogue inference run](/docs/experiments/inference/full-catalogue-inference-run.md) and [curriculum capture and replay](/docs/experiments/runtime-storage-and-serving/curriculum-capture-and-replay.md) state the evidence.
- Query and language breadth. Four stored semantic vectors, four fixed lexical strings over two display languages for the projection comparison, eight queries for the fuzzy score parity, and 60 translation cases are not a random sample of the catalogue's input, field, length or language mix. Only Finnish and English have a measured result. [Exact and approximate semantic retrieval](/docs/experiments/search-and-translation/semantic-retrieval.md), [lexical lookup projection and native fuzzy matching](/docs/experiments/search-and-translation/lexical-lookup-projection-and-native-fuzzy.md) and [machine translation as retrieval-preserving transformation](/docs/experiments/search-and-translation/translation-and-retrieval.md) state the cohorts.
- A paired browser measurement. No measurement joins the query embedding request, the database read, network transfer and browser rendering under concurrent load. [Exact and approximate semantic retrieval](/docs/experiments/search-and-translation/semantic-retrieval.md) and [served read path](/docs/experiments/runtime-storage-and-serving/served-read-path.md) state the boundaries.
- Capacity with the applied arena cap and above 750 users. No capacity ladder ran with `WEB_MALLOC_ARENA_MAX = 2`, and the light-only ladder of the build with the native libraries stopped at 750 users while its rate was rising. [Serving capacity](/docs/experiments/runtime-storage-and-serving/serving-capacity.md) and [web memory and allocator retention](/docs/experiments/runtime-storage-and-serving/web-memory-and-allocator-retention.md) state the ladders and the cap.
- Stored neighbour rows and the packed relation. Whether more than 128 stored rows per query chunk closes the exclusion gap without an unacceptable table size or build time, whether the different stored set changes the recommendations a reader sees, and whether the packed relation's update path for another embedding generation costs less than a full rebuild. [Nearest-neighbour retrieval for recommendations](/docs/experiments/recommendations/nearest-neighbour-retrieval.md) and [packed exact semantic search](/docs/experiments/search-and-translation/packed-exact-semantic-search.md) state the measurements.
- A larger basis for the prefilter. Whether the course-centroid prefilter pays on a basis larger than 50 courses, how much of its saving the shared float64 chunk store removes on a warm serving path, and whether a float32 centroid store keeps the same retained set near the floor. [Course-centroid candidate prefilter](/docs/experiments/recommendations/centroid-candidate-prefilter.md) states the measurement.
