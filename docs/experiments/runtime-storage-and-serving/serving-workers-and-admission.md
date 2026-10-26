# Serving workers and admission

This first part measures two, three and four worker processes under frozen load profiles and states the four-worker selection and its admission settings.

**Evidence status:** Comparative. **Run dates:** 22 October 2026.

## The question

The serving account asked how many [worker processes](/docs/reference/glossary.md#administration) to run behind one front router, what each kind of read costs, and which limits keep interactive reads responsive while heavy work runs. It was measured in two stages. The first stage compared worker process counts on frozen load profiles. The second implemented [admission control](/docs/backend/interfaces/admission-control.md) and tuned its limits.

This page covers the worker-process-count stage and the selection that ended it. The cells served the application as two, three or four worker processes behind a relay, so the comparison measures the worker processes rather than the front router's placement in the rest of the account. Admission entered the account after the worker process count was chosen.

The account continues on two pages. [Serving cost and routing](/docs/experiments/runtime-storage-and-serving/serving-cost-and-routing.md) covers request cost, heavy placement and routing. [Serving load and admission limits](/docs/experiments/runtime-storage-and-serving/serving-load-and-limits.md) covers the load meter, the admission limits and their tuning. A shared method page, [Serving load measurement method](/docs/experiments/runtime-storage-and-serving/serving-load-method.md), states the load profiles, the interactive probe and the fixed payloads once.

## Fixed inputs and instruments

Both comparisons used the pinned dataset and frozen payloads written before the first measured run. No product code, configuration, service or schema changed for a cell, and every cell ran as one disposable instance.

The normal profile is a constant arrival of 44 operations a minute in aggregate, which is 20 users at 22 operations per 10 minutes each, with one course-summaries read every 2 seconds. The summaries read is the interactive probe. A normal run lasts 3 minutes.

A heavy run adds heavy virtual users to the same normal traffic and lasts 2 minutes. The first comparison added 1, 2, 3, 5 or 6 heavy virtual users. The second added 5, 6, 8 or 12. Each heavy virtual user advances one operation around its cycle per iteration, with an 8 to 15 second think time and a start offset of `(VU id × 7) mod cycle length`. The first 20 seconds are excluded from every heavy percentile.

The light levels reuse the normal mix and raise the arrival rate with `users × 0.036667` operations a second, so 50 users is 1.83 operations a second. A light run lasts 2 minutes.

The worker-process comparisons used searches with `include_inactive=true` and the basis-50 recommendation with `active_only=true`. The later admission measurements changed those flags, so their heavy payload and normal searches are different inputs.

| Item | Value |
|---|---|
| Dataset | The pinned dataset, held fixed across both comparisons |
| Normal load | 20 users, 44 operations a minute in aggregate, one summaries probe every 2 seconds |
| Heavy load | Normal traffic plus 1, 2, 3, 5 or 6 heavy virtual users, then 5, 6, 8 or 12 |
| Light load | Normal mix measured at 50 and 100 users, 0.036667 operations a second per user. The 200-user level was not run. |
| Heavy read | Basis-50 active-only recommendation |
| Fixed input | A 200-identity basis file and frozen payloads written before the first run |
| Cold search | Exact-code search of 3.5 to 3.8 seconds, then 3.5 to 4.3 seconds, excluded |
| Hardware | 4-core aarch64 server, 23.6 GB of RAM |
| Load client | k6 v2.3.0, run outside the server |
| Memory scope | 6.442 GB of memory and of memory plus swap, 6,442,450,944 bytes each |
| Start floor | 6.442 GB of available memory before every run |
| Abort guards | Available memory below 3.758 GB, swap growth above 268.435 MB, or worker-process RSS above 1.611 GB |
| Per-process address space | 1.611 GB in the first comparison, 2.684 GB in the second, relay 0.537 GB |
| Isolation | One disposable instance per cell, fixed payloads, no product change |

The [retained caches](/docs/backend/interfaces/web-server.md#the-dataset-scoped-retained-caches) carry the lookup projection, the prerequisite source facts and the descriptive chunks. The memory accounting in both comparisons uses the same three retained facilities. The second comparison ran the final build with all three caches present.

Every run recorded the database's tuple insert, update and delete counters before and after. All 37 decision-cell records of the first comparison and all 18 records of the second matched before and after. The dataset was not written.

## The first comparison

The first comparison issued 39 run invocations. The classification below comes from the relay exit code and the k6 error codes.

| Class | Runs | Meaning |
|---|---:|---|
| Valid server evidence | 13 | Normal load and the valid heavy levels at the three counts |
| Context run | 1 | A different selected dataset, context only |
| Instrument | 3 | Two virtual users sending the heavy read back to back for 60 seconds |
| Transport-invalid | 21 | Relay address-space exhaustion, mostly instant connection errors |
| Failed first attempt | 1 | The output copy path failed and saved no summary |
| Memory-bound | 0 | None in this comparison |
| Total | 39 | |

The failed attempt ran the full 182.24 seconds with 223 requests and no request failure, but both output copies failed with a protocol error about the file name, so the run saved no summary or raw output. The correction changed the two copy paths and nothing else. The measured k6 wall time was 4,878.4 seconds, 81.3 minutes, inside the 115-minute cap.

### Normal load at 20 users, first comparison

The two-, three- and four-worker cells served the same normal load at 1.2239, 1.2222 and 1.228 operations a second. The p50 was 198, 197 and 192 ms and the p95 was 2,053, 2,123 and 2,058 ms, within 70 ms of one another. The search family dominated both the latency and the CPU.

| Worker processes | Requests | Rate (op/s) | p50 (ms) | p95 (ms) | p99 (ms) | max (ms) | Probe p50 (ms) | Probe p95 (ms) | CPU (s/req) | Aggregate RSS (MB) | Cold (s) |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2 | 223 | 1.2239 | 198 | 2053 | 2394 | 3712 | 63 | 306 | 0.35094 | 640.242 | 3.598 |
| 3 | 223 | 1.2222 | 197 | 2123 | 2267 | 4237 | 61 | 285 | 0.36112 | 882.192 | 3.768 |
| 4 | 224 | 1.228 | 192 | 2058 | 2284 | 3815 | 61 | 151 | 0.36429 | 1,164.976 | 3.659 |

The context run read a different dataset, so it is not a decision cell. Its overall p95 of 2,193 ms and probe p95 of 412 ms are on the same order as the two-worker disposable cell.

The normal p95 is flat across the three counts. The probe differs in the other direction: four worker processes reached 151 ms against 306 ms at two. That difference rests on one run of about 90 probe samples, and the second comparison did not repeat it.

### The heavy ladder

The valid ladder reached heavy 5 at two worker processes and heavy 3 at three and four worker processes. At every cell the next attempted level was transport-invalid, so the heavy knee was not observed. The upward levels 8, 12, 16, 24, 32 and 50 were not run because no cell stayed on the ladder. At every valid level every request returned 2xx, no connection error was recorded, and the probe p95 stayed below one second.

| Worker processes | Valid heavy levels | Probe p95 at each valid level (ms) | Highest valid level | Probe p50/p95/p99/max at that level (ms) |
|---:|---|---|---:|---|
| 2 | 1, 2, 3, 5 | 239 / 402 / 278 / 450 | 5 | 91 / 450 / 683 / 695 |
| 3 | 1, 2, 3 | 439 / 204 / 204 | 3 | 61 / 204 / 361 / 389 |
| 4 | 1, 2, 3 | 280 / 254 / 189 | 3 | 62 / 189 / 320 / 394 |

The heavy series at two worker processes was not monotonic. The overall p95 ran 2,089, 4,300, 2,166 and 4,828 ms at levels 1, 2, 3 and 5, and the probe p95 ran 239, 402, 278 and 450 ms. Run-to-run variance dominates at this sample size.

### The relay failure that ended the ladder

The relay created one thread per accepted connection. It exhausted its 0.537 GB address-space cap with `RuntimeError: can't start new thread` at about 50 client connections. That failure made 21 runs transport-invalid: heavy 6 at two worker processes, heavy 5 at three and four worker processes, all five saturation ramps at every cell, and light 50 at every cell.

The samples after the crash are instant connection errors with no HTTP status, not server responses. Before the crash, three heavy cells had returned a usable prefix. At three-worker heavy 5, 151 requests returned 200 with a p95 of 3,955 ms and a maximum of 23,824 ms. At four-worker heavy 5, 24 requests returned 200 with a p95 of 5,287 ms and a maximum of 5,415 ms. At two-worker heavy 6, 48 requests returned 200 with a p95 of 2,180 ms and a maximum of 3,625 ms.

The light-50 runs failed the same way. k6 allocated 52 virtual users at the 50-user level, the relay exited with the same thread error about six seconds into every run, and every request after it failed instantly with error code 1212 or 1000. The server answered every request that reached it: 9, 7 and 6 requests returned 200 with medians of 2.05 to 2.48 seconds. No sample is near the 120-second request timeout. The "timed-out request" label is a generic label for any non-empty k6 error code, not a server timeout. The first light ladder stopped at 50, so light 100, light 200 and the conditional 400 and 800 continuation were not run.

The five saturation ramps are transport-invalid for the same reason. The structure, graph and compare ramps reached 12 to 18 operations a second for one or two 15-second segments before the relay died. The search ramp reached only 1.0 to 1.5 operations a second. None of these is a server rate bound.

The recommendation ramps also produced a server-side signal. At 20 concurrent virtual users a worker process raised `MemoryError` while fetching rows under the 1.611 GB per-process address-space cap, and the server returned 143, 14 and 6 HTTP 500 responses at two, three and four worker processes. At two and four workers uvicorn replaced the dead worker with a replacement spawn child. That is an instrument cap, not a product memory limit.

### Two corrections in the first comparison

The first correction is the classification. The first classification marked the 21 relay-failure runs as valid and non-graceful. It sampled resident memory rather than address space, and it did not treat a nonzero relay exit as a run failure. The transport-invalid class above replaces that classification.

The second correction is the stop rule. The first address-space exhaustion happened in the two-worker heavy-6 run, and the batch did not stop. It continued through the remaining two-worker runs, the whole three-worker and four-worker matrices, and the three light-50 runs. Each subsequent run started a fresh instance and passed its own scope, memory, RSS and read-only checks, but the batch as a whole did not meet its stop rule. The subsequent runs are reported as measured runs, not as a compliant batch.

### What the first comparison recommended

The valid evidence did not show that three or four worker processes raised sustainable throughput or improved normal latency enough to justify their cost. The normal p95 was flat. CPU per request was lowest at two worker processes, at 0.35094 against 0.36112 and 0.36429. Aggregate RSS rose from 640.242 MB at two worker processes to 882.192 MB at three and 1,164.976 MB at four. The accounted aggregate for four worker processes sat inside the configured budget, but the extra memory bought no measured capacity or tail.

The recommendation was to keep two worker processes. No heavy knee, light ceiling or sustainable rate came out of the run, so the recommendation rested on the fixed normal mix and on the absence of a gain that justified the extra processes.

## The high-load relay comparison

The second comparison replaced the thread-per-connection relay with one asyncio event loop that holds no thread or process per connection. A capacity check opened 128 connections, held all of them before any payload moved, echoed one payload through each and closed them. It completed 128 of 128 round trips with a peak of 128 simultaneous connections, exit code 0 and no error lines, under the same 0.537 GB address-space cap.

The per-process cap was measured rather than assumed. One uncapped one-worker instance was warmed with the cold search and the warm-up order, then sent the basis-50 recommendation once and twice at the same moment. Its `VmPeak` was 998.920 MB for one request and 1,353.335 MB for two, and the applied cap was 2.684 GB, 2,684,354,560 bytes. At those two levels the requests took 11.61, 12.71 and 12.93 seconds.

The first measured normal run was invalidated by one diagnosed correction. It completed the full 180 seconds with 223 requests, no failures and a p95 of 2,108.19 ms, but the relay logged five `ConnectionResetError(104, 'Connection reset by peer')` lines in the second after the last request. k6 closes its pooled connections at run end, and the relay counted a peer-initiated close as a fault. The relay was changed to count `ConnectionResetError` and `BrokenPipeError` as closed connections. A failure to connect and every other exception counted as error lines. No scenario, payload, cell, level or cap changed. The invalid run was repeated once, and its 180.45 seconds count in the measured budget.

The pass produced 18 runs. 16 are valid measured runs, one is the invalidated first normal attempt, and one is the memory-bound light-100 run. The measured k6 wall time was 2,466.65 seconds, 41.1 minutes, inside the 90-minute budget.

### Normal load at 20 users, high-load comparison

| Worker processes | Requests | Rate (op/s) | p50 (ms) | p95 (ms) | p99 (ms) | max (ms) | Probe p50 (ms) | Probe p95 (ms) | CPU (s/req) | Aggregate RSS (MB) |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2 | 222 | 1.2309 | 195.75 | 2061.72 | 2185.91 | 2409.13 | 60.98 | 232.13 | 0.33946 | 600.277 |
| 3 | 224 | 1.2284 | 196.19 | 2100.76 | 2339.75 | 3790.26 | 62.54 | 290.65 | 0.36259 | 914.309 |
| 4 | 223 | 1.2362 | 201.56 | 2128.76 | 3447.52 | 3888.55 | 63.54 | 337.36 | 0.36148 | 1,061.298 |

The normal p50 and p95 are the same across the three counts within 82 ms. The two-worker-process probe p95 spans 232.13 to 291.96 ms across its two attempts, so the normal probe spread of one cell is about 60 ms. The three-worker-process value of 290.65 ms lies inside that span, and the four-worker-process value of 337.36 ms lies 45 ms above it.

The next chart shows the normal-load probe p95 across both comparisons. Four worker processes were lowest in the first comparison and highest in the second, and the difference between the counts is small beside the heavy-load differences below.

![Normal-load interactive probe p95 for two, three and four worker processes in the first comparison and the high-load relay comparison. Four worker processes were lowest in the first comparison and highest in the second.](/docs/charts/runtime-serving-workers-normal-probe.svg)

The fixed-mix normal run is the only direct CPU comparison between counts. Two worker processes used 0.33946 CPU-seconds per request, three used 0.36259 and four used 0.36148. Four worker processes raised the normal CPU per request by 6.5 percent and three worker processes by 6.8 percent against two.

The next chart shows the normal CPU per request across both comparisons.

![Normal-load CPU per request for two, three and four worker processes in the first comparison and the high-load relay comparison. The two-worker-process cell is lowest in both comparisons, and four worker processes cost about 6.5 percent more per request in the high-load comparison.](/docs/charts/runtime-serving-workers-normal-cpu.svg)

### The heavy ladder from 5 to 12

Every cell was graceful at every attempted level. The heavy series ran 5, 6, 8 and 12 heavy virtual users beside the 20 normal users, with 0 request errors, 0 timeouts and 0 non-2xx responses. The interactive probe stayed below one second at every level. Heavy 12 is the top of the measured ladder, not a measured knee.

| Worker processes | Level | Requests | Overall p95 (ms) | Probe p50 (ms) | Probe p95 (ms) | Probe p99 (ms) | Probe max (ms) | CPU (s/req) |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2 | 5 | 196 | 4842.75 | 95.44 | 365.76 | 508.12 | 519.8 | 0.71301 |
| 2 | 6 | 211 | 2122.59 | 75.7 | 425.77 | 474.26 | 506.08 | 0.36777 |
| 2 | 8 | 231 | 2295.98 | 68.21 | 367.77 | 412.54 | 413.41 | 0.31351 |
| 2 | 12 | 254 | 6223.14 | 149.09 | 411.37 | 644.95 | 798.64 | 0.94339 |
| 3 | 5 | 198 | 4010.46 | 69.73 | 312.63 | 422.37 | 477.35 | 0.63061 |
| 3 | 6 | 211 | 2295.97 | 64.92 | 298.05 | 504.56 | 552.32 | 0.44038 |
| 3 | 8 | 225 | 4949.67 | 71.04 | 378.91 | 498.83 | 566.09 | 0.62996 |
| 3 | 12 | 267 | 5291.22 | 75.75 | 442.45 | 516.09 | 521.35 | 0.55753 |
| 4 | 5 | 196 | 3440.86 | 63.18 | 196.78 | 293.13 | 358.92 | 0.64199 |
| 4 | 6 | 215 | 2201.13 | 61.01 | 301.23 | 388.0 | 425.06 | 0.34163 |
| 4 | 8 | 225 | 3208.49 | 76.12 | 289.4 | 395.59 | 406.58 | 0.57747 |
| 4 | 12 | 266 | 4652.37 | 93.4 | 357.77 | 487.91 | 491.91 | 0.71966 |

Four worker processes had the lowest probe p95, p99 and maximum at every level. Their probe p95 range of 196.78 to 357.77 ms did not overlap the two-worker-process range of 365.76 to 425.77 ms. Three worker processes were lower than two at levels 5 and 6 and higher at levels 8 and 12 on p95. The heavy-12 overall p95 fell from 6,223.14 ms at two worker processes to 5,291.22 at three and 4,652.37 at four.

![Heavy-load interactive probe p95 with 20 normal users plus 5, 6, 8 or 12 heavy virtual users. Four worker processes have the lowest value at every level, and their p95 range does not overlap the two-worker-process range.](/docs/charts/runtime-serving-workers-heavy-probe.svg)

The per-request CPU under heavy traffic is not comparable across runs at a given level. The heavy cycle contains five basis-50 recommendations per 37 operations, and how many of them fall inside a two-minute run depends on where each virtual user starts and how long each recommendation takes. At heavy 8 the two-worker-process run drew no basis-50 request and the four-worker-process run drew three. At heavy 5 the two-worker-process run drew four against three at four worker processes. A basis-50 recommendation costs 10.7 to 35.8 seconds of latency and a large share of the run's CPU, so a heavy CPU figure reflects that mix rather than the worker process count.

No cell reached a server rate limit. The heavy-12 offered rate was 2.03 to 2.17 operations a second. The sustainable rate is not established for any count.

### The light ladder and its cap

The light ladder exists only for two worker processes. At 50 users the two-worker-process cell served all 281 requests with no errors, but the interactive probe p95 was 1,091.78 ms, above the one-second bound, so the level is non-graceful. The search family reached p50 5.6 to 6.0 seconds. This is a server latency result at the offered rate, not a transport failure.

| Worker processes | Users | Requests | Errors | Timeouts | Non-2xx | Probe p50 (ms) | Probe p95 (ms) | Probe p99 (ms) | Probe max (ms) | Class |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 2 | 50 | 281 | 0 | 0 | 0 | 252.99 | 1091.78 | 1431.79 | 1594.05 | Measured, non-graceful |
| 2 | 100 | 479 | 178 | 178 | 178 | 1641.0 | 5775.41 | 6837.96 | 7342.74 | Memory-bound |
| 2 | 200 | not run | | | | | | | | Not run |
| 3 | 50, 100, 200 | skipped | | | | | | | | Skipped |
| 4 | 50, 100, 200 | skipped | | | | | | | | Skipped |

The 100-user run is memory-bound, not CPU-bound. The instance log holds 17 `MemoryError` lines, including `RuntimeError: can't start new thread` from the anyio thread pool. The two worker processes reached 1,232.093 MB and 1,114.436 MB RSS under the 2.684 GB per-process cap, and 178 of 479 requests failed or timed out. The cgroup peak was 2,377.568 MB of the 6.442 GB scope, `memory.failcnt` was 0, swap growth was 0, and available memory was 9.26 GB or more. Neither the scope nor the server's memory bound was reached. The two worker processes exhausted their own address-space caps. The teardown needed SIGKILL and the instance exit code is -9.

The 100-user level therefore measures the instrument's cap, not a server rate or CPU limit. Light 200 was not run because the pass stopped at 100. The three- and four-worker-process light levels were skipped, because the two-worker-process ladder was non-graceful at 50 users and memory-bound at 100. No light result exists for three or four worker processes, and none is inferred.

## What the worker-process comparisons support

The normal mix is flat across the three counts. The difference that holds across the heavy ladder is the interactive tail, which favours four worker processes at every level from 5 to 12. The cost is 6.5 percent more normal CPU per request and more memory. Aggregate normal RSS was 600.277 MB at two, 914.309 MB at three and 1,061.298 MB at four in the high-load comparison, against 640.242 MB, 882.192 MB and 1,164.976 MB in the first.

| Worker processes | Accounted aggregate (B) | Measured aggregate (B) | First normal RSS (MB) | High-load normal RSS (MB) |
|---:|---:|---:|---:|---:|
| 2 | 316,172,100 | 317,080,248 | 640.242 | 600.277 |
| 3 | 474,258,150 | 475,620,372 | 882.192 | 914.309 |
| 4 | 632,344,200 | 634,160,496 | 1,164.976 | 1,061.298 |

Both comparisons recommended two worker processes. The rule for another count required valid data showing that three or four worker processes lower the interactive tail or raise the sustainable rate without a CPU-seconds-per-request increase. Four worker processes met the tail clause at every heavy level. The fixed-mix normal CPU rose 6.5 percent, and the heavy CPU per request could not test the clause because the basis-50 count differed between runs. No cell raised the offered rate. The second comparison therefore did not meet the stated rule cleanly either, and its recommendation was also to keep two worker processes.

## The selection of four workers

The selection that followed reversed the two-worker-process recommendation: four worker processes, not two. It was a trade-off rather than a benchmark win, and it rested on four reasons. The selection weighed the heavy tail first. The four-worker-process tail was the lowest at every level of the high-load ladder. Its normal probe p95 of 337 ms remained below the one-second interactive bound. Four worker processes also gave the heavy class three admission slots beside one worker process left for interactive traffic.

The admission work that followed supported that placement. With four worker processes behind one front router and admission on, heavy work was placed on at most three worker processes, one heavy read per worker process, and the fourth worker process carried light and interactive traffic. The interactive probe p95 ranged from 95 to 388 ms from 1 to 50 heavy virtual users. The light load spread across all four worker processes.

The tuning also supported the saturated heavy budget. Raising it from 24 to 40 core-seconds increased completed heavy calls from 5, 5, 5 and 4 to 8, 8, 8 and 9 at 3, 6, 12 and 24 virtual users, and lowered the three-user heavy p50 from 65.7 to 43.7 seconds. Every other admission value stayed as it was.

The selection was made and applied: four worker processes, admission on, and a saturated heavy budget of 40 core-seconds. The fixed normal mix favours two worker processes on CPU and memory. Four worker processes are therefore the selected operating point, not an unqualified winner of the worker process count comparison.

## The applied values and the memory limit

| Setting | Applied value |
|---|---|
| Worker processes | 4 |
| Admission | On |
| Saturated heavy budget | 40 core-seconds |
| Retained cache budget | 1.074 GB, 1,073,741,824 bytes |
| Accounted share of four worker processes | 632.3442 MB, 632,344,200 bytes |

The retained cache budget and the accounted share are configuration arithmetic. One worker process's share is `33,554,432 + 8,000 × 7,006 + 497 × 137,794 = 158,086,050` bytes. Four worker processes hold 632,344,200 bytes against the 1.074 GB budget. The configuration refuses a worker process count whose share product exceeds that budget, and no cache is measured at runtime. The two figures are not resident memory and not the total service bound. Observed RSS is larger because it carries the interpreter, the database driver and the request working set.

The cgroup limit the memory proof ran under is 4.295 GB (4,294,967,296 bytes) for memory and for memory plus swap. That limit and the kernel proof are described in [Serving load and admission limits](/docs/experiments/runtime-storage-and-serving/serving-load-and-limits.md#the-retained-cache-aggregate-and-the-cgroup-ceiling).

The example configuration sets four worker processes, admission on and 40 core-seconds.

## Limits and corrections

- The first comparison's classification was misleading. It marked 21 relay-failure runs as valid because it sampled resident memory and ignored a nonzero relay exit. The classification from the exit code and k6 error codes is the one this page reports.
- The first batch did not stop at the first address-space exhaustion. Its subsequent cells started fresh instances and passed their own checks, but the batch did not meet its stop rule.
- The recommendation `MemoryError` under the 1.611 GB cap is an instrument limit, not a product memory limit. The per-request recommendation working set was not measured here.
- The light-100 memory bound is the 2.684 GB per-process instrument cap, not a server rate or CPU limit. No light level above the 20-user normal profile is graceful for two worker processes, and no light level exists for three or four worker processes.
- Heavy CPU per request is not a fixed-mix comparison. The count of basis-50 recommendations inside a two-minute run differs, so only the normal run compares CPU per request between worker process counts.
- Normal probe differences are small. The first comparison's four-worker 151 ms came from one run, and the two-worker probe p95 spans 232.13 to 291.96 ms across its two high-load attempts. The high-load four-worker normal probe p95 of 337.36 ms is 45 ms above that span.
- No sustainable rate and no heavy knee were measured. Heavy 12 is the top of the second ladder, and every cell was graceful there. The heavy class was bounded by the offered load, not by a measured server limit.
- The measurements come from the pinned dataset on a 4-core aarch64 server with 23.6 GB of RAM. They do not establish behavior on other hardware or other catalogues.
- The admission tuning ran against other work on the server of 0.46 to 1.79 core-seconds a second, and the 40-core-second levels ran after their 24-core-second counterparts. The selected budget was read against that spread.
- The 4.295 GB cgroup limit is the one the memory proof ran under, and the allocator proof tested the cgroup mechanism rather than a serving workload at that limit.

## Untested questions

- A repeated fixed-mix heavy comparison, with the same number of basis-50 recommendations inside each run, would test whether the four-worker tail advantage holds without the heavy-mix confound. It was not run.
- A light ladder for three and four worker processes, on a transport and per-process address-space cap that carry 100 and 200 users without exhausting the instrument, would measure the light side of those counts. It was not run, and no result is inferred.
- A higher offered rate, or the same rates on different hardware, would test whether the four-worker tail advantage holds beyond the measured ladder. No sustainable rate was established, so that question is open.

## The rest of the account

[Serving cost and routing](/docs/experiments/runtime-storage-and-serving/serving-cost-and-routing.md) covers request cost, heavy placement and routing. [Serving load and admission limits](/docs/experiments/runtime-storage-and-serving/serving-load-and-limits.md) covers the load meter, the admission limits and the tuning ladder. [Serving load measurement method](/docs/experiments/runtime-storage-and-serving/serving-load-method.md) covers the load profiles, the interactive probe and the fixed payloads shared by the load reports. This page and those pages form one account of serving worker processes, the front router and admission.
