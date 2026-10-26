# Runtime, storage and serving experiments

Nine pages trace how the system reads stored data into memory, caches it between calls, serves it under load, and captures the catalogue.

The line follows one stored row from the database to a response. It begins with the shape of a read and the memory that shape retains, continues through a cache that keeps read results between calls, and ends on the served HTTP path, where worker count, request cost, placement, admission and a memory ceiling decide what a request waits for. A final report turns to the other end of the pipeline, one capture of the public curriculum and the replay of its stored evidence.

The changes that touched a read were judged against the product result. A read projection, a narrower scope, a streamed read, a cache or a different representation counted only when its output matched the product, and where an outcome changed, the change was reported as behavior-altering. That criterion separates the lines that preserved results from those that only measured a cost.

The accounts do not form one cohort. The dated read and serving runs fall between 19 and 24 October 2026. The two captures began on 11 September 2026, and the full-catalogue projection carries no recorded run date. The measured accounts used separate builds, datasets and payload sets, and their values do not add across reports.

## The question the line asked

Five questions ran through the category.

1. Can the product's full-catalogue reads select fewer columns and a narrower identity scope without changing their output?
2. How much client memory does each read shape retain, and what do float32 storage, a normalized projection, a prepared cache and compression cost?
3. Does a bounded per-process cache shorten a repeated heavy recommendation call, and do its retained bytes fit four serving processes?
4. What does one served read cost end to end, how many [worker processes](/docs/reference/glossary.md#administration) should run behind the front router, and which limits keep the interactive path responsive while heavy work runs?
5. What does one capture of the public curriculum produce, and can its stored evidence be verified and normalized without reading the source again?

A sixth thread connects them. Each measurement had to state its own boundary: one read, one fixed-pool composition, one process, one HTTP request, one load cell, one whole-service profile. The line treats those boundaries as results, not as details, because a saving measured at one boundary does not carry to another.

The measurements that read the catalogue used one captured snapshot of 11,086 represented courses, of which 4,543 were active, 9,901 eligible module versions and 58,962 teaching-text [chunks](/docs/reference/glossary.md#capture-and-data-preparation) with stored BGE-M3 vectors. The [catalogue the experiments read](/docs/experiments/README.md#the-catalogue-the-experiments-read) and the evidence labels are stated on the section index.

## The order of the line

The order below is conceptual, not the order in which the runs were taken. It follows a row from the read, to the memory it occupies, to the cache that keeps it, to the request that serves it, and finally to the capture that produced the catalogue.

### Reading the stored data

[Data loading and connection overheads](/docs/experiments/runtime-storage-and-serving/data-loading-and-connection-overheads.md) asked two questions that share a catalogue but not an input set or a timing boundary. The first was whether the full-catalogue reads could be narrowed. The represented-course summary read returns the official summary columns plus the representative identity, the coverage read is one aggregate `GROUP BY` query that materializes no chunk entity, and the graph read seeds its target and retained identities in one eager read and reads the rest through a per-compilation cache.

The `search`, `prerequisites` and `--coverage` JSON outputs were byte-identical by SHA-256 to their pre-change outputs on the full catalogue. Unified search fell from 15.5 to 19.0 seconds to 2.6 to 2.9 seconds, the prerequisites command for `COMP.CS.500` from about 14.5 seconds to 2.35 to 2.44 seconds, and the coverage command from 18.6 seconds to 6.14 seconds. The represented summary read fell from 4.15 to 1.04 seconds and the full-scope coverage read from 13.5 to 0.28 seconds. The run date of that projection was not recorded.

The second question asked what one fixed-pool recommendation composition costs. Three nested bases of one, 10 and 50 courses drew candidate pools of 42, 435 and 1,874 ranked courses. Wall medians for one complete composition were 0.1868, 1.5798 and 10.5724 seconds in fresh mode, 0.1207, 1.5215 and 10.7306 seconds in reused mode, and 0.0526, 0.7880 and 6.6311 seconds in prepared mode. At the 10-course and 50-course bases the candidate chunk read and the scalar product scorer carried most of the time. Dataset and settings resolution measured about 0.006 seconds, engine creation 0.0004 seconds, the first connection and schema-head check about 0.023 seconds, and serialization at or below 0.0041 seconds.

Holding the engine across repetitions changed the measured composition by -35.37, -3.69 and +1.50 percent. The direction is not consistent, and the single-course difference is not an engine-creation saving because engine creation itself is 0.0004 seconds. Prepared mode is experiment-local reuse, not a product cache. That composition and the full-catalogue projection are separate measurements, and the 10.5724-second value is not a whole-command time.

The basis-50 pool came from a recovery capture. The first attempt completed the product work and then raised `MemoryError` while serializing the fixed input at a 1,399.3 MB process peak. The recovery used separate 60-second timers for the product command and for serialization, where one cumulative timer through both was intended, and the composition samples each used one fatal 60-second timer through serialization.

[Read memory, compact projections and response serialization](/docs/experiments/runtime-storage-and-serving/read-memory-and-serialization.md) then measured what each read shape retains. It kept five memory measures apart: array bytes, resident memory, process peak, Python-traced memory and object-graph bytes. On the 50-course basis the full chunk read of 11,405 candidate rows added 233.9 MB and set a 753.2 MB process peak. The descriptive read added 18.7 MB, and the streamed read held a 31.36 MB float32 matrix and one bounded partition.

The matched bounded read is the category's paired memory result. Both legs used the same 1,874 candidate triples and the same float64 consumer. The materialized leg returned 319 of 319 results with zero membership, order, value or flag changes and all 27 exact tie pairs, at a 546.9 MB process peak. The bounded leg returned the same result at 171.5 MB, a 375.4 MB lowering, at a cost of about two seconds per recorded sample, 17 to 20 percent slower.

The same report corrected two earlier readings. The first projection size was 5.09 MB, a sum over four fields per entry that omitted three normalized strings, containers and dataclass overhead. The full object graph is 22.5 MB, 12.4 MB for courses and 10.1 MB for modules with shared strings counted once. The first lexical comparison found 14 of 16 cells identical. The reference had received an unscoped course list in the active-only cells, so the two earlier cells were unverified, and the corrected comparison gives 16 of 16 for each of exact, substring and fuzzy matching.

Float32 halved the array bytes on every basis. It is a byte result, not a parity result. On the fixed pools the float32 deltas stayed below the 0.0307 and 0.135 percentage-point margins, and no sampled candidate crossed a threshold or changed membership, order or a derived flag. That is a sampled classification, not a guarantee for other inputs, and no bitwise equality is claimed.

Reused direct-prerequisite context removed all 63 compile statements and reproduced the compilation digest with 0.89 MB of retained raw facts.

The sixth gzip level reduced the saved report by 13.0 percent and the synthetic payload by 11.1 percent against the first level at about 2.1 times the CPU. The ninth gzip level reduced a further 2.2 and 3.7 percent at 1.4 and 2.2 times the CPU of the sixth level. Every level decoded to identical bytes. This is a compression result with no HTTP measurement.

### Retaining results between calls

[Descriptive chunk caching](/docs/experiments/runtime-storage-and-serving/descriptive-chunk-caching.md) asked whether a bounded per-process cache of descriptive chunk rows shortens a repeated heavy recommendation call. An entry is keyed by the read triple of group identity, course-unit identity and representative source hash, and holds the ordered chunk rows for that triple. Two nominal bounds ran, 33.554 MB at 248 entries and 67.109 MB at 497 entries, on a 50-course basis and a 200-course basis.

The comparison threshold was the larger of the two cases' own warm spreads. The 33.554 MB bound shortened the 50-course warm maximum by 0.645 seconds and the median by 0.697 seconds beyond the 0.138-second spread, and was 0.545 seconds slower at the maximum and 0.500 seconds slower at the median on the 200-course basis beyond the 0.234-second spread. The 67.109 MB bound shortened the 50-course maximum by 1.152 seconds and the median by 1.276 seconds beyond the 0.163-second spread. At the 200-course basis it shortened the maximum by 0.195 seconds and the median by 0.214 seconds, less than the 0.399-second spread. No smaller qualifying bound exists, because the 33.554 MB bound loses at the larger basis.

An eager lookup projection moved the build to process start but shortened no heavy call, because the recommendation path does not read that projection. The build took 1.830 seconds of wall time for the 50-course basis and 1.685 seconds for the 200-course basis. A compact projection retained 17.9 MB against 28.0 MB, a saving of 10.1 MB, 36.2 percent, and matched all 16 lexical cells and the catalogue report, but its matcher wall time was not isolated, so its no-slowdown condition is unproven. Both were skipped.

The first recommendation was that no facility be added. That outcome was reversed. The applied cache holds 497 entries at 137,794 bytes per entry, a 68.484 MB accounted chunk term, and it was selected as a budget trade-off. The benefit measurements did not change. The measured benefit is confined to the 50-course basis, and the 200-course saving lies within its own spread. The selection is not a finding that the larger basis tail improves.

A second measurement called the product recommendation command with the implemented cache. The separate 50-course basis returned 319 results, and the reproduction used the first 50 identities of the 200-course basis and returned 432, so its values do not extend the 319-result case.

The baseline warm calls were 9.082554 to 9.194772 seconds and the cache warm calls 7.937882 to 8.026672 seconds, with a 1.168100-second maximum and 1.170300-second median saving against the larger 0.112218-second warm spread. All four report digests were identical.

The 50-course exact reference is the product digest written by that run, not a fixed pre-change digest. The saved report has the same 319 results in the same order with identical payloads, flags, nulls and ties, and differs only in the last bits, at a maximum absolute delta of 2.1316282072803006e-14 for relatedness and score and 5.684341886080802e-14 for overlap. The retention assertion measured 68.938 MB against a 68.484 MB accounted term, 0.454 MB or 0.663 percent above it.

The cause is a heavier first-50 mix, and the four-process budget holds. Four configured shares hold 632.344 MB inside the 1.074 GB aggregate, six shares fit and seven do not. The 14 accepted cases ran on four revisions of the measurement program, one of which only built the 200-course basis, so the cases are not one uniform revision.

### Profiling the served request

[Endpoint load profiling and bottleneck attribution](/docs/experiments/runtime-storage-and-serving/endpoint-load-profiling.md) recorded what one read cost on the served path, first as a whole-service profile and then as a CPU attribution. The profile of 19 October 2026 made 59 HTTP requests, sequential except one three-way concurrency check, against a serving tree with two uvicorn worker processes and synchronous handlers. It excluded prerequisites and ran without a front router, admission control, response compression or a browser solver. Its wall times, CPU times and response sizes describe that build only.

The four search modes cost 1.75 to 1.98 seconds, with 0.86 to 0.93 seconds of Python work and an inferred database estimate of about 1.1 seconds for the lexical modes. A basis-50 recommendation cost 8.22 to 8.49 seconds warm and 15.87 seconds cold, with 5.41 seconds of Python work and 2.96 sampled database seconds. Three simultaneous recommendation reads took 9.69, 14.70 and 14.90 seconds against 8.3 seconds alone, about 1.7 times the throughput rather than three. The worker resident set grew from about 85 to 89 MB to 328 MB and 504 MB and was not returned to the operating system.

A graph and route profile over 10 courses and both activity scopes gave 20 valid rows. The largest graph read cost 28.40 seconds and 92.98 MB, compressed with `gzip -9` to 3.55 MB. The largest route read cost 30.34 seconds and 28.9 route CPU seconds. A browser solver performs the route work on the client, so the server route seconds include work that a site with the browser solver does not run on the server. Gzip reduced the large bodies by about 14 to 40 times, a correction from an earlier 14 to 26 times summary. One target, `YKT.SOA.303`, has no valid row. Its graph requests ran past the 240-second client timeout, and the server workers kept computing both graph and route for about 30 minutes at 1.7 to 1.8 GB each until the service was restarted. A closed client connection does not cancel a synchronous handler.

The 22 October 2026 attribution answered a different question on a four-worker build. It read whole-container CPU counters once a second. In three heavy basis-50 runs web carried 69.8 to 85.2 percent of total CPU, the database 14.7 to 30.0 percent and embedding 0.1 to 0.2 percent. In three valid light mixed runs web carried 43.3 to 46.8 percent, the database 45.0 to 50.3 percent and embedding 4.0 to 8.3 percent. The counters cover whole containers, so the database and embedding shares are bounds rather than one site's exclusive cost. The profile ranked nine optimization candidates and implemented none, so no estimated saving is a measured gain.

### Producing the catalogue

[Curriculum capture and replay](/docs/experiments/runtime-storage-and-serving/curriculum-capture-and-replay.md) closes the line at the source. Two runs answer different parts and are not two points on one scale. A fresh capture for the 2026-2027 [curriculum periods](/docs/reference/glossary.md#courses-and-the-catalogue), started on 11 September 2026, completed in 125.49 seconds, stored 6,071 responses and recorded 17,020 course snapshots and 3,724 module snapshots. Its source-free verification returned an identical report with the same manifest, stored-response and source-snapshot digests. At the time of that run, verification used four full object replay passes and the pass count did not grow with the closure group count.

A second capture covered the full catalogue and began on 11 September 2026. It stored 14,405 responses and recorded 24,932 course objects and 15,553 module objects across 21 curriculum periods from 2006 to 2026. A replay started from that verified manifest and ran twice. It reconciled the 24,932 captured course objects as 24,931 normalized course versions and one explicit null-code exclusion, with 88 unresolved course groups, zero new versions, zero changed versions and an unchanged SQL summary. The record does not explain why each unresolved group was empty.

No explicit capture duration is recorded for the full manifest, so the full capture serves as a normalization and replay source, not as a timing result. The two captures are not compared on speed or scale. The timed capture's elapsed value and its manifest timestamp span also differ, with no recorded reconciliation of their boundaries, as the capture report explains.

The null-code rule excludes only an explicit `code: null`. A missing or blank code is malformed and stops normalization, and a coded version under the same canonical group is eligible. An earlier revision left a stale normalized projection when a version later arrived with an explicit null code. The corrected reconciliation removes the stored version and its cascaded payload, and that rule stands.

The historical method is not the supported operation. Source-free replay verified and normalized a stored manifest without a source client. Live-source ingestion with a resumable capture is the supported operation. It starts a fresh capture or resumes a retained one, then normalizes the completed capture in one transaction. It is not a source-free rebuild of a saved capture. [Ingestion](/docs/backend/catalogue/ingestion.md) describes the stage.

## Serving workers, the front router and admission

The served path has one account in three parts, measured between 19 and 23 October 2026 and applied through 24 October. [Serving load measurement method](/docs/experiments/runtime-storage-and-serving/serving-load-method.md) states what the parts share: the server, the load client, the traffic profiles, the interactive probe, the frozen payloads, the warm-up and reported spans, and the memory guards. It applies to the HTTP serving accounts only. It does not cover the in-process read and cache studies above, browser rendering, a user study or a general capacity rating.

The three parts are sequential in the argument. The first compares worker counts. The second prices one request, measures heavy capacity and tests how the serving tree places heavy work, including a store that was measured and then removed. The third tunes the admission limits, compares four load meters and runs the serving memory proof.

### The worker-count comparison

[Serving workers and admission](/docs/experiments/runtime-storage-and-serving/serving-workers-and-admission.md) compared two, three and four worker processes on frozen load profiles. The normal profile offered 44 operations a minute with a course-summaries probe every two seconds. Heavy profiles added heavy virtual users. Two comparisons ran on 22 October 2026. The first issued 39 invocations, of which 13 were valid server evidence and 21 were transport-invalid after a thread-per-connection relay exhausted its address-space cap at about 50 connections. The second used an asyncio relay and produced 18 records, 16 valid, one invalidated by a relay reset classification and one memory-bound.

The first comparison's own valid flag marked the 21 relay-failure runs as valid. It sampled resident memory rather than address space and ignored a nonzero relay exit, and the batch did not stop at the first address-space exhaustion. The classification from the exit code and the client error codes gives the 13 valid runs reported here, and the later cells are measured runs rather than a compliant batch.

At normal load the overall p50 and p95 were flat across the three counts, within 82 ms in the second comparison. The fixed normal mix is the only direct CPU comparison. Two workers used 0.33946 CPU-seconds per request, three 0.36259 and four 0.36148, so four raised the normal cost by 6.5 percent and three by 6.8 percent. Aggregate normal resident memory was 600.277 MB at two, 914.309 MB at three and 1,061.298 MB at four.

Under heavy traffic four workers had the lowest interactive probe p95, p99 and maximum at every level from five to 12 heavy virtual users. The four-worker probe p95 range was 196.78 to 357.77 ms and the two-worker range 365.76 to 425.77 ms, and the ranges do not overlap. The heavy-12 overall p95 fell from 6,223.14 ms at two workers to 5,291.22 at three and 4,652.37 at four. Heavy 12 is the top of the measured ladder, not a measured knee. No cell in that comparison reached a server rate limit, and the comparison established no sustainable rate for any count.

The light ladder of the worker comparison exists only for two workers. At 50 users the cell served every request with no errors but the interactive probe p95 was 1,091.78 ms, above the one-second bound, so the level is non-graceful. At 100 users the two workers exhausted their 2.684 GB per-process address-space caps, 178 of 479 requests failed or timed out, and the cgroup peak was 2.378 GB of the 6.442 GB scope. That level measures the instrument's cap, not a server rate. Light 200 was not run, and the three- and four-worker light levels were skipped, so no light result exists for three or four workers.

Both comparisons recommended two workers. The selection that followed reversed that recommendation and chose four. It weighed the four-worker heavy tail, which was lowest at every level, against 6.5 percent more normal CPU per request and more memory, and it gave the heavy class three admission slots beside one worker left for interactive traffic. Four workers are the selected operating point, and the fixed normal mix favors two on CPU and memory. The heavy CPU per request cannot test the CPU clause because the count of basis-50 calls inside a heavy run differed between cells.

### Request cost, heavy placement and the store that was removed

[Serving cost and routing](/docs/experiments/runtime-storage-and-serving/serving-cost-and-routing.md) priced each request class and tested placement. A first cost pass drove one request at a time through the application in one process. The means span more than two orders of magnitude, from 0.020982 core-seconds for basis-50 summaries to 9.329324 for a basis-50 recommendation. A material variant pass measured 90 variants. Including inactive courses raised a basis-50 recommendation from 10.419672 to 13.498728 core-seconds and a basis-200 recommendation from 23.908396 to 33.093459, the largest measured input. A long inactive semantic search cost 1.253250.

The first pass put only the basis-50 recommendation above a 1.0 core-second line and proposed that class as the only heavy one. The material variants superseded that proposal. At that line the heavy set also contains basis-200 recommendations in both scopes, next courses at basis 50 with inactive courses and basis 200 in both scopes, long exact and semantic searches with inactive courses, the largest full graph in both scopes and the three served-dataset spot checks. The implemented policy classifies from the request route and shape against configured cutoffs, not from that measured list.

One heavy virtual user completed 6.476 basis-50 calls a minute at 10.202 web core-seconds a call, 1.105 of the four cores and 1.584 total cores with the database and embedding containers. Two virtual users completed 4.986 calls a minute and three completed 8.973, 1.386 times the one-user rate. Two users are the knee of that ladder. The heavy connections did not spread. One worker carried 98.7 percent of web CPU at one virtual user and 99.4 percent at three, and two users split 49.26 and 50.20 percent across two workers. The four-worker aggregate heavy rate is therefore unmeasured, and no value is inferred from the one-worker figures.

The light ladder on the same setup was graceful at 20 and 50 users, with probe p95 of 142 and 493 ms. At 100 users it was invalid under the 2.684 GB heavy cap, then valid and non-graceful after only the light cap was raised to 3.758 GB, with a probe p95 of 9,412.88 ms and 43 timeouts or non-2xx responses. Light 200 is unmeasured.

The account also records a store that was measured and then removed. On 21 October 2026 a Redis 7.4.2 container ran with one Unix socket, no TCP port, no persistence and no network, holding only opaque admission state. At 100,000 keys the kernel cgroup charge peaked at 22.421504 MB and retained 22.159360 MB after the database was empty, while Redis logical `used_memory` had returned to 1.373520 MB. The logical maximum stayed below the 67.108864 MB `maxmemory` and the largest kernel peak was 16.7 percent of the 134.217728 MB container limit. A job queue was rejected because it stores payloads and results and adds a separate worker lifecycle to synchronous commands. The study set no product budget. The admission state lives in the front router process, and the serving design holds no Redis.

The first distribution gate failed. Three concurrent heavy virtual users put 60.35 percent of web CPU on one worker with a new connection per request, above the half rule, and that worker's resident peak reached 1.731 GB against a 1.611 GB stop. Kept-alive mode passed at 35.17 percent, but the rule required either mode, so the gate failed and measured no curve. The front router then placed each admitted heavy read on a worker that carried no other heavy read. The same check passed at 30.80 percent with new connections and 36.25 percent kept alive, with no overlapping heavy intervals on a worker, every worker carrying heavy work, and worker peaks from 714.555 MB to 811.192 MB. The gate completed eight heavy recommendations in each mode in 120 seconds. It answers placement and memory, not throughput.

### The admission limits, the load meter and the memory ceiling

[Serving load and admission limits](/docs/experiments/runtime-storage-and-serving/serving-load-and-limits.md) validated the committed limits, tuned two values and compared four load meters on 44 selected cells. A load meter is the rule that turns whole-host CPU and admitted requests into a load score and a load regime. The validation ran the committed 10-second CPU-only meter, not the score meter that was later applied, so its regime shares and policy values at a level do not describe the applied behavior.

The interactive probe p95 stayed between 95 and 388 ms from one to 50 heavy users. Heavy p50 rose from 12,755 ms at one user to 34,138 ms at two and 65,664 ms at three, then settled between 64,718 and 67,822 ms from three to 16 users. No request was refused below 24 users. At 24 and 32 users the queue caps refused 3,299 and 3,431 requests, and at 50 users the saturated cap refused 63,970. The probe degraded to p50 260 ms and p95 388 ms at 50 users with no errors. The light side carried 50 and 100 users without a refusal. Light 200 was not graceful, with 215 dropped iterations, a probe p95 of 28,437 ms and the server at 0.996 of four cores.

Raising the saturated heavy budget from 24 to 40 core-seconds raised completed heavy calls from five, five, five and four to eight, eight, eight and nine at three, six, 12 and 24 virtual users, and lowered the three-user heavy p50 from 65,664 to 43,707 ms. The comparison is not paired, because the 40-core-second runs ran later and the background CPU moved. Raising the light floor from 0.25 to 0.5 changed nothing measurable at these loads, so the applied floor is 0.25.

Four meters ran on the same eleven traffic shapes. Two further meter variants were not run, one for budget and one because its trigger was not met. The [load score](/docs/backend/interfaces/admission-control.md#the-load-score) of the selected meter combines three terms over 60 seconds.

```text
score = 1.0 x whole_host_cpu_utilisation_over_60s
      + 0.012 x light_admissions_in_60s
      + 0.004 x heavy_admissions_or_running_in_60s
```

It completed 49 heavy-alone calls against 42, 47 and 43 for the other three meters, and 91 calls over all ten heavy cells against 79, 88 and 82. Beside 12 normal users it put the four mixed cells from two to five heavy users wholly in the saturated regime and lowered the worst normal-user search p95 to 3,920 ms, against 8,903 ms under the 10-second CPU meter, 9,448 ms under the 60-second CPU meter and 4,279 ms under the CPU-only variant with the lower release line, which had no regime series. It did not restore the normal-only reference, and its mixed search p95 was 1.5 to 3.7 times its own reference. Each normal-traffic cell holds eight completed samples per search class, so those tails describe a small sample. One selected run per cell, with varying background load on the server, is not a replicated causal estimate.

The score meter's reference cell took four attempts, three of them instrument-invalid. That exceeds the single permitted repeat and is not extra independent confirmation of the meter.

The score meter was implemented in the front router and applied. One disposable run checked it on the product tree. Every one of the 121 sampled lines equalled the configured weighted sum of its own terms, and every position and latch followed the configured lines. The final 30 seconds of heavy-alone traffic stayed in the middle regime, and the mixed window reached and held saturation for 76 of its 91 samples. That run establishes that the implemented meter computes the selected score and latch. It is not an additional load study.

The applied settings are four worker processes, admission control on, a saturated heavy budget of 40 core-seconds, a 60-second score window, weights of 1.0, 0.012 and 0.004, and headroom, saturation and release lines of 0.60, 1.05 and 0.90. The heavy slot count caps at three. The other admission values keep the values they had before the selection.

The memory ceiling is a second, separate bound. The [retained-cache aggregate](/docs/backend/interfaces/web-server.md#the-dataset-scoped-retained-caches) of 1.074 GB bounds the sum of the per-process cache shares. It is configuration arithmetic, not a measured resident set. One configured share is 158.086 MB, four shares are 632.344 MB, six fit and seven exceed the aggregate. The 4.295 GB value is the cgroup limit the memory proof ran under, and it bounds the supervisor, the front router and the four workers together for memory and memory plus swap.

A disposable kernel proof ran one allocator under a 268.435 MB memory and memory-plus-swap limit. Both limits read the same value, the child ended with SIGKILL rather than `MemoryError`, both maximum-usage files reached the limit, `memory.failcnt` ended at 0 and the kernel logged one cgroup out-of-memory kill. The product tree then ran under 4.295 GB with a peak of 0.410 GB during startup and light reads. A separate proof with the configured settings summed six independent process high-water marks to 2.788 GB against the 4.295 GB proof limit, which is not a simultaneous peak. No heavy load ran under the 4.295 GB proof limit.

## Headline results

| Report | Recorded date | Question | Result that stands |
|---|---|---|---|
| Data loading and connection overheads | 21 October 2026, and an unrecorded earlier date | Can full-catalogue reads be narrowed, and where does a fixed-pool composition spend its time? | Byte-identical command outputs, unified search at 2.6 to 2.9 seconds from 15.5 to 19.0 seconds, and a 10.5724-second basis-50 composition dominated by the candidate read and scorer, with no consistent engine-reuse gain |
| Read memory, compact projections and response serialization | 21 October 2026 | What does each read shape retain, and what do representation changes cost? | A bounded read reproduced 319 of 319 results at 171.5 MB against 546.9 MB, about 2 seconds slower, a 22.5 MB projection with 16 of 16 cells per matcher, and float32 halving bytes without a lossless guarantee |
| Descriptive chunk caching | 21 and 22 October 2026 | Does a bounded cache shorten a repeated heavy call, and does it fit four processes? | A 497-entry cache selected and applied, a 1.170300-second median saving on a 432-result reproduction beyond a 0.112218-second spread, 0.663 percent above its accounted term yet inside the 1.074 GB aggregate |
| Endpoint load profiling and bottleneck attribution | 19 and 22 October 2026 | What does one read cost end to end, and where does CPU go? | A basis-50 recommendation at 8.22 to 8.49 seconds warm and 15.87 seconds cold, three at once about 1.7 times the throughput, a largest graph of 28.40 seconds and 92.98 MB, and heavy runs at 69.8 to 85.2 percent web CPU |
| Serving workers and admission | 22 October 2026 | How many worker processes, and what admission settings? | Both comparisons recommended two, four had the lowest heavy probe tail at 196.78 to 357.77 ms against 365.76 to 425.77 ms at 6.5 percent more normal CPU, and four were selected |
| Serving cost and routing | 21 and 22 October 2026 | What does a request class cost, and how is heavy work placed? | 0.020982 to 9.329324 core-seconds by class, 6.476 heavy calls a minute on one worker, an unmeasured four-worker aggregate, Redis measured and removed, and the router passing the gate at 30.80 and 36.25 percent |
| Serving load and admission limits | 22 to 24 October 2026 | Which limits and meter keep the interactive path responsive? | A probe of 95 to 388 ms from 1 to 50 heavy users, 40 core-seconds raising completions to 8, 8, 8 and 9, the score meter at 49 heavy-alone calls against 42, 47 and 43, and a 3,920 ms worst mixed search tail against 8,903 and 9,448 ms |
| Curriculum capture and replay | 11 September 2026 (captures) | What does one capture produce, and can its evidence be replayed? | 125.49 seconds, 6,071 responses and 17,020 plus 3,724 snapshots in one run, and a separate 14,405-response capture reconciled to 24,931 versions with one explicit null-code exclusion and 88 unresolved course groups in two replays |

The line ends with one applied read projection, one applied cache and one applied serving shape. The full-catalogue projection and the chunk cache are the storage results. Four worker processes, admission control on, the 40-core-second saturated budget and the score meter are the serving result. Gzip level 6 is applied to responses of at least 500 bytes. The 4.295 GB serving-tree proof limit is the cgroup limit the memory proof ran under. The capture line ends with a recorded scale and a replay method that is not the supported operation.

## Corrections and reversals

| Earlier record | Correction | Result that stands |
|---|---|---|
| The lexical projection held 5.09 MB | The sum covered four strings per entry and omitted normalized strings, containers and dataclass overhead | 22.5 MB of object graph, 12.4 MB for courses and 10.1 MB for modules |
| The first lexical comparison found 14 of 16 cells identical, with two non-identical cells | The reference received an unscoped course list in the active-only cells, which made the two earlier cells unverified | The corrected comparison gives 16 of 16 for each matcher |
| The 753.2 MB peak was read as the baseline for 171.5 MB | That peak belongs to an earlier 11,405-row full chunk read from a 139.8 MB baseline | The paired result is 546.9 to 171.5 MB, a 375.4 MB lowering at about 2 seconds per sample |
| The 33.554 and 134.218 MB cache bounds were read as product budgets | They count array bytes or object-graph bytes, and the four course facts of 0.53 to 0.83 MB do not exercise either bound | In the prepared-matrix test the 33.554 MB bound holds one matrix and evicts the second, the 134.218 MB bound holds both, and four course facts cause no eviction |
| The first basis-50 capture completed the product work and then raised `MemoryError` while serializing the fixed input at a 1,399.3 MB process peak | A recovery capture used separate 60-second timers for the product command and for serialization, where one cumulative timer through both was intended | The recovery supplied the pool, and each composition sample used one fatal 60-second timer through serialization |
| The direct-prerequisite reuse comparison answered the reuse question | Its first pass made no candidate eligible, and both official passes ran zero statements, so the comparison had nothing to compare | A later nonempty comparison removed all 63 statements with an identical compilation digest on one basis |
| No descriptive chunk cache was recommended | A 497-entry cache at 137,794 bytes per entry, a 68.484 MB accounted chunk term, was selected and applied as a budget trade-off | The 50-course saving stands, the 200-course saving lies within spread, and the applied cache is 0.663 percent above its accounted term yet fits the aggregate |
| The large graph bodies compressed by 14 to 26 times | The 65.76 MB body becomes 1.66 MB, a 39.6-fold reduction | The calculated range from the table is about 14 to 40 times |
| The first worker comparison's own valid flag marked 21 relay-failure runs as valid | It sampled resident memory rather than address space, ignored a nonzero relay exit, and the batch did not stop at the first address-space exhaustion | 13 valid runs and 21 transport-invalid runs, with the later cells measured but not a compliant batch |
| Both worker comparisons recommended two workers | Four workers met the heavy-tail clause but raised normal CPU by 6.5 percent, and the selection weighed that trade-off | Four worker processes, admission control on and a 40-core-second saturated budget were selected and applied |
| Three concurrent heavy users put 60.35 percent of web CPU on one worker and tripped the worker memory stop | That tree had no front router, so heavy reads were not placed on distinct workers | The front router passed the same check at 30.80 and 36.25 percent, with every worker carrying heavy work, and the earlier gate measured no curve |
| Only the basis-50 recommendation was above the 1.0 core-second heavy line | The material variants measured longer queries, inactive scopes and larger bases | The heavy set includes basis-200 recommendations, inactive next courses, long inactive searches and the largest graphs, and the policy classifies by route and shape |
| A light-100 attempt under the heavy cap was read as a server limit | It ran under the 2.684 GB heavy address-space cap and logged 17 `MemoryError` lines while the cgroup stayed below its 6.442 GB limit | The corrected run under the 3.758 GB light cap is valid and non-graceful, and light 200 is unmeasured |
| An earlier null-code reconciliation kept a normalized projection | A version that later arrived with an explicit null code left stale rows | The corrected reconciliation removes the version and its cascaded payload |
| Source-free replay was the verification and normalization method | A different method starts or resumes a live-source capture and normalizes it in one transaction | The historical four-pass replay and the two replays are recorded, and live-source ingestion is the supported operation |
| A Redis store was part of the admission design | Its footprint was measured at 1,000, 10,000 and 100,000 keys and no product budget followed | The admission state lives in the front router process, and the serving design holds no Redis |

Three further corrections bound the serving numbers. The first distribution gate's instrument needed two corrections before its own values were usable. Its first pass measured a load-tool timestamp span and kept no per-second series, and the corrected pair selected a 51-second tail because the client clock ran about 57 seconds ahead of the server. Recomputed on the server clock, the new-connection share stayed far above half and the kept-alive share far below, so the verdict did not change. The record also mixed the client and server clocks in the admission cost pass, which moved the saved knee utilisation from 2.3789 to a recomputed 1.9320 of four cores. That was an analysis correction, and no cell was invalidated or rerun for it.

The workload itself changed after the first cost pass. The first heavy policy set a capacity fraction of 0.45, a ceiling of 1.8 core-seconds a second, 108 core-seconds a minute and 11 whole basis-50 users at its floor. The material variants and the applied curves superseded that policy. The 90 percent ceiling of 5.829 basis-50 calls a minute describes one worker's measured capacity, and it was not selected as policy.

## Where the results were applied

| Change | Status | Evidence scope |
|---|---|---|
| Projected represented-summary read, one summary read per unified search, aggregate coverage read, scoped graph read | Selected and applied | Full catalogue, with byte-identical command outputs |
| Streamed bounded read and float32 storage | Measured, no promotion | Fixed pools of 42, 435 and 1,874 ranked candidates on one pinned dataset |
| Normalized lexical projection | Measured, no promotion | The full catalogue of 11,086 courses and 9,901 eligible module versions |
| Prepared matrix and course-fact caches | Measured, no promotion | The fixed 50-course basis for the matrices and the four largest-row courses for the facts |
| Gzip level 6 | Applied | The application compresses responses of at least 500 bytes at level 6. The samples covered a 152,191-byte saved basis-50 report and a 1,274,526-byte synthetic payload |
| Descriptive chunk cache at 497 entries and 137,794 bytes per entry, a 68.484 MB accounted chunk term | Selected and applied | Two serial bases, a 432-result reproduction and four-process arithmetic |
| Redis admission store | Measured, then removed | 1,000, 10,000 and 100,000 keys on one container |
| Four worker processes, admission control on, saturated budget of 40 core-seconds, score meter | Selected and applied | Two worker comparisons, admission ladders and 44 meter cells |
| Serving-tree proof limit of 4.295 GB | Measured | A kernel proof at 268.435 MB and a startup check under a 4.295 GB cgroup limit |
| Checkpointed concurrent capture and null-code reconciliation | Applied | One fresh capture and two replays of a separate manifest |
| Source-free replay | Historical | One verification and two replays |

The fixed-pool overhead measurement made no product change. The read, memory and cache reports left the bounded read, float32, the normalized lexical projection and the prepared caches unpromoted. The compression samples measured levels 1, 6 and 9 and support level 6 as the size and CPU compromise, and the application compresses responses of at least 500 bytes at level 6. The endpoint profile changed nothing and implemented none of its nine candidates.

## The boundaries of the shared methods

The serving method page applies to the HTTP serving accounts only. It states that it does not cover the in-process read and cache studies, browser rendering, a user study or a general capacity rating. The read, memory and cache reports carry their own method in their own pages: fixed captured pools, one pinned dataset resolved through its dataset receipt, one process at a time, the scalar product scorer, and no HTTP request. The read and memory reports used a fatal 60-second sample timer for the number variants and reference, the lexical timing loop, the gzip samples and every read sequence, under a 2.147 GB address-space cap. The array stages, the cache six-call sequence and the prerequisite passes had no in-process timer. The cache report used a 480-second sample timer under the same address-space cap.

The three reports also used different input sets. The data-loading and read-memory lines used bases of one, 10 and 50 courses with candidate pools of 42, 435 and 1,874 ranked courses and descriptive rows of 137, 1,771 and 7,657. The cache line used a separate 50-course basis of 319 results, a 200-course basis of 629 results and a 50-course prefix of that basis that returns 432 results. Those sets are not interchangeable.

No single build, dataset or payload set holds across the category. The 19 October endpoint profile did not read the pinned dataset and ran on a two-worker synchronous build with no front router. The worker comparisons ran on separate product trees, the second with the lookup projection, the source-fact cache and the chunk cache. The admission cost pass held that second tree, and the admission tuning and meter batches each recorded their own tree. The capture runs are separate from all of them. The full-catalogue projection has no recorded run date.

The frozen payloads did not use one set of scope flags. The two worker comparisons and the admission cost pass used a frozen set whose searches include inactive courses and whose basis-50 heavy read is active-only. The later admission and meter batches used active-only searches and a basis-50 recommendation that includes inactive courses. The large-input pass measured each large variant in both scopes. A rate or a latency is named with its batch, profile and window.

The heavy planning virtual user runs one operation per iteration on a 37-operation cycle with an eight to 15 second think time. The cycle holds 20 structure reads, five comparison reads, five basis-50 recommendations, five searches and two graph reads. A 120-second mixed cell therefore draws zero to four basis-50 calls in its reported window, and its per-request CPU is not a fixed-mix comparison. The ramp is the controlled series for the heavy class, and the normal profile is the only fixed-mix comparison across worker counts.

Memory measures are not interchangeable. Array bytes, resident memory, the process high-water mark, Python-traced memory, object-graph bytes, a cgroup charge and an address-space limit answer different questions. The 546.9 and 171.5 MB values are process peaks, the 233.9 MB value is resident growth, 22.5 MB is an object graph, 31.36 MB is an array buffer, 1.074 GB is configured cache arithmetic and 4.295 GB is a cgroup bound. The 2.684 and 3.758 GB caps are per-process address space, not resident memory.

The memory-plus-swap guard is proven per pass, not once for the line. The serving batches wrote and read back both limits at 6.442 GB. The total-CPU acceptance could not set the memory-plus-swap limit on the server and recorded it unlimited. The records disagree on that facility, and no single combined guard claim covers every run. Each pass proves what it recorded.

Timing boundaries also differ. The 19 October profile reports client-observed single-request wall times. The k6 serving cells report client wall time from send to last byte. Worker process CPU, whole-server CPU and whole-host busy CPU are three further counters. The graph stage split ran in process and does not add to the HTTP graph time. The fixed-pool compositions exclude HTTP, retrieval, the next-course read and response delivery. No value in one boundary becomes a value in another.

## What the line does not establish

- No general capacity or user latency. The line ran on a 4-core aarch64 server with 23.6 GB of RAM, on one catalogue, with a synthetic client and no browser. The user counts are rate parameters and virtual users, not people.
- No sustainable rate for the worker-count comparison and no heavy knee on that comparison's heavy ladder. Heavy 12 was the top of that ladder and every worker-count cell was graceful there. The separate capacity ladder has a knee at two virtual users, but one worker carried 98.7 percent of web CPU at one virtual user and 99.4 percent at three, so it is not a four-worker capacity result.
- No four-worker aggregate heavy capacity. The one- and three-user runs put 98.7 and 99.4 percent of web CPU on one worker, so the per-worker rate is not a four-worker rate.
- No heavy load under the 4.295 GB proof limit. The kernel proof used a 268.435 MB limit, the startup check ran under 4.295 GB with light reads only, and the summed high-water marks are not a simultaneous peak.
- No whole-request HTTP latency for the read, memory and cache reports. They ran one process at a time, and their composition totals exclude retrieval, the next-course read and delivery.
- The cache benefit is confined to the 50-course basis and one call sequence. The 200-course saving is within its own spread, and the warm-tail saving under the configured worker count, the front router and admission was not measured.
- The fixed pools are the product's retrieval outputs for three nested bases, not a full-catalogue sample. The line establishes no retrieval, semantic or recommendation quality.
- The fresh capture timing is one run. Its hardware, source condition, step split, checkpoint size and concurrency are unrecorded. The full capture has no explicit recorded duration, and the two captures are not compared on speed or scale.
- Float32 is sampled on fixed pools. The margins are 0.0307 and 0.135 percentage points, and no guarantee applies to other inputs.
- Many cells are single observations. The read and array timings are single passes after one warmup, a heavy cell can hold one basis-50 completion, a normal-traffic cell holds eight search samples per class, and each meter cell is one run.
- The 19 October profile describes a build without the front router, admission, compression or a browser solver. Its absolute values do not describe a site that runs the front router and admission.
- The Redis study measured one version, one kernel and one server with one client, and set no budget.
- The projection measurement carries no memory measurement and no stage decomposition, so the attribution of its reduction to the narrower projection is an interpretation.

## Untested questions

Each question below is untested.

- Whether the score meter lowers normal-user latency in a repeated, paired run with controlled background load on the server. No measured meter restored the normal-only reference.
- Whether the serving tree stays within the 4.295 GB proof limit under the heavy load that produced a 3.437 GB aggregate worker resident peak, and what the true simultaneous peak of the six processes is.
- What four-worker heavy capacity a connection distribution that reaches all workers would measure.
- Whether the cache warm-tail saving holds under the configured worker count, the front router and admission control.
- Whether a second requested basis moves the measured cache above or below its accounted term in the same direction as the 50-course prefix.
- Whether a pre-tokenized matcher consumes the 11.5 MB title token graph and saves query time.
- Whether the float32 deltas stay below the margins on other pools, languages or query inputs.
- Whether a second timed capture on the same machine and source reproduces 125.49 seconds.
- Whether the four-worker heavy tail advantage holds in a repeated fixed-mix heavy run, where the basis-50 count inside each run is the same.
