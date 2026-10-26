# Serving load measurement method

This page states the shared method of the endpoint load profiles and the serving worker, front router and admission measurements.

The endpoint load measurements and the serving measurements follow this method, and it sets the limits of what their numbers can claim. It covers the request path under client load. It does not cover the in-process read and cache studies, browser rendering, a user study or a general capacity rating.

## What the method covers

The line runs from 19 to 24 October 2026 and has four kinds of measurement. The endpoint profiles of 19 October recorded single requests across the endpoint shapes it covered and one three-way concurrency check. They also split a graph read into stages and measured the route cost beside it. The serving batches of 22 October compared one server under changed worker counts, ran a serial per-class cost pass, a large-input cost pass, a heavy ramp, a light ladder and a total-CPU admission acceptance. The admission and meter batches of 22 and 23 October ran the front router on the measured curves and compared traffic shapes and load meters. The memory ceiling check of 24 October proved a kernel-enforced cgroup limit and measured a startup peak.

The endpoint profile is a profile, not a load test. It records wall time, process CPU, response size, and where a stage split was available, an inferred or measured database and embedding share of one request. The serving batches are controlled comparisons. Each comparison holds its dataset, request bodies, client version and reporting rules fixed while it changes one serving condition at a time. They do not share one build or one payload set across the whole line, and the endpoint profile did not read the pinned dataset.

The line selected and applied four worker processes, admission on, a saturated heavy budget of 40 core-seconds and the score meter. Earlier cells measured two and three workers, other admission values and other meters. The method covers those cells. The applied setting is the end point of the line, not a condition of every run. The process tree and route surface are described in [Web server](/docs/backend/interfaces/web-server.md), and the admission rules in [Admission control](/docs/backend/interfaces/admission-control.md).

The endpoint profile is reported in [Endpoint load profiling and bottleneck attribution](/docs/experiments/runtime-storage-and-serving/endpoint-load-profiling.md). The worker comparisons are in [Serving workers and admission](/docs/experiments/runtime-storage-and-serving/serving-workers-and-admission.md). The cost, capacity and acceptance measurements are in [Serving cost and routing](/docs/experiments/runtime-storage-and-serving/serving-cost-and-routing.md). The admission tuning and load-meter comparison are in [Serving load and admission limits](/docs/experiments/runtime-storage-and-serving/serving-load-and-limits.md).

## The server and the load client

The serving batches used a 4-core aarch64 server with 23.6 GB of RAM. The endpoint profile of 19 October ran on a 4-core 2 GHz aarch64 server. The k6 batches used k6 v2.3.0 as a separate client process, and the same version generated every k6 load cell. The endpoint load profile of 19 October used a small sequential HTTP client for 59 requests, with one three-way concurrency check, so its wall times are single-request observations rather than k6 load cells. It ran against the two-worker build of that date, with synchronous request handlers. The graph and route profile of the same date used one repetition per course and setting.

The k6 client records the time from its send to the last response byte, so every k6 latency in the serving line is a client wall time. It sent the API POST paths under test and the fixed probe. The total-CPU acceptance used temporary measurement clients on the server and sent one request at a time. Its wall seconds are client-observed and are not k6 cells. The catalogue path was excluded from the serving profiles because its response is 4.3 MB uncompressed and its size would dominate a profile without representing one interactive read.

The server's only write on the serving path is the request record. The pinned dataset stayed read-only. The record contains the start hour, route label, status and duration, so a refusal is recorded like a served request. The record is described under [the request usage record](/docs/backend/interfaces/web-server.md#the-request-usage-record).

## Batch inputs: datasets, payloads and scopes

### Datasets

A pinned dataset is one captured curriculum database fixed before the first cell. Each disposable instance starts against that database directly, with no selected dataset, so the site reads its configured database, and every cell of that batch reads the same rows. The dataset receipt and schema head were recorded for the pinned dataset, and the read-only checks below state which cells verified that no row changed.

One worker-count run read the configured database instead of the pinned dataset, as context only. It is not a comparison cell, because it read a different dataset from the pinned one, and the running process was never stopped, restarted or reconfigured. One large-input pass also ran three spot inputs against a second dataset on a disposable instance. Those three inputs are spot checks, not a worker or admission comparison.

### Payload sets

A frozen payload is a request body written before the first measured cell and read unchanged by every cell in its batch. The k6 drivers verify the payload file hash before a run. Freezing removes payload drift, so a difference between two cells of one batch comes from the serving condition under test and not from a changed query, basis or scope.

Three payload sets cover the main comparisons, and they do not hold the same requests. The frozen serving set of the worker comparisons, the admission cost pass and its ramp, and the large-input capacity runs holds exact, substring and semantic search with `include_inactive` true, a study-structure read, graph reads with `active_only` true and false, a comparison pair, next-courses on a basis of three with `active_only` true, recommendations on bases of three and 50 with `active_only` true, and course summaries on a basis of 50. It holds no fuzzy query and no module lookup. Fuzzy search and module lookup were measured in the 19 October endpoint profile only, and no serving cell issued them.

The large-input set of 22 October measures short and long exact, substring and semantic search in both scopes, next-courses on bases of three, 50 and 200 in both scopes, recommendations on bases of 50 and 200 in both scopes, summaries on bases of 50 and 200, a comparison pair, the largest study structure, and two graph targets in both active scopes with the recommended and inferred toggles at four basis sizes. It adds three spot inputs on a second dataset. Each variant is a separate body, and its scope is part of the variant.

The admission set of the admission tuning and meter batches sends normal-user searches with `include_inactive` false, a graph read with `active_only` true, a comparison pair, a study-structure read, next-courses and recommendations on a basis of three with `active_only` true, summaries on a basis of 50, and the heavy recommendation on a basis of 50 with `active_only` false.

The total-CPU acceptance built its own small set: three small-basis recommendation bodies with active and inactive scope, one inactive search, one active-scope search, one graph target and the load-meter observations. It is an acceptance run, not a comparison series, and its bodies are not one of the three payload sets.

### Scope flags

The active scope is a frozen field of the body. For a search, `include_inactive` true reads courses outside the activity window. For a next-courses or recommendation read, `active_only` false does the same. The field value belongs to the frozen body rather than to a per-run choice. The batches did not use one value.

The two worker comparisons, the admission cost pass and its ramp, and the large-input capacity runs used the frozen serving set, so their searches read inactive courses and their basis-50 heavy read was active-only. The light worker ladder reuses the normal cycle of that set and keeps the same search scope. It is not an active-only ladder. The admission and meter batches use `include_inactive` false for normal-user searches and `active_only` false for the heavy basis-50 recommendation. Their graph and basis-3 reads stay active-only. The large-input pass measured each large variant in both scopes and does not replace either setting. No single set of scope flags holds across the line.

A [basis](/docs/reference/glossary.md#prerequisites-and-routes) is the set of courses a next-courses or recommendation read treats as covered.

## Traffic profiles

The line changed the traffic profile on purpose. Each profile answers a different question, and no profile is a stand-in for another.

| Profile | Batch | Client shape | Offered rate | Run length | Reported window |
|---|---|---|---|---|---|
| Normal | Worker, admission cost | 20 users at 22 operations per 10 minutes each, plus one probe every 2 s | 44 operations a minute | 180 s | Whole run, after the cold search is removed |
| Planning heavy | Worker, admission cost | Normal mix plus N heavy VUs, with the odd VU ids on the 37-operation planning cycle, one operation per iteration with an 8 to 15 s think time | 44 operations a minute plus the heavy operations | 120 s | Last 100 s |
| Graph heavy | Worker, admission cost | Normal mix plus N heavy VUs, with the even VU ids on the 28-operation graph cycle, one operation per iteration with an 8 to 15 s think time | 44 operations a minute plus the heavy operations | 120 s | Last 100 s |
| Back-to-back heavy | Large input | N heavy VUs, one basis-50 recommendation per iteration, no think time, plus the probe | As fast as each VU completes | 120 s | Last 100 s |
| Heavy ramp | Admission cost | Basis-50 VUs stepped from 1 to 5, a 5 s step to each target and a 55 s hold | Stepwise | 300 s | Whole timeline |
| Light arrival | Worker, large input | The normal cycle with the user count raised to 50 or 100 | `users × 0.036667` operations a second | 120 s | Last 100 s |
| Admission heavy ladder | Admission | Basis-50 inactive recommendation back to back at 1 to 50 VUs, plus the probe | As fast as each VU completes | 120 s | Last 100 s |
| Admission light ladder | Admission | The normal cycle with active-only searches at 50, 100 or 200 users | `users × 0.036667` operations a second | 120 s | Last 100 s |
| Load-window ramp | Admission | Heavy VUs at 1, 2, 3, 5, 3, 2 and 1, or a light arrival at 110, 220, 440, 220 and 110 operations a minute | 60 s stages | 420 s or 300 s | Whole timeline |
| Meter profile | Meter | 12 normal users alone, 1 to 5 heavy VUs alone, or 12 normal users beside 1 to 5 back-to-back heavy VUs | 26.4 normal operations a minute plus the heavy operations | 180 s | First 60 s excluded, next 120 s |
| Two heavy clients | Worker | Two VUs sending basis-50 recommendations back to back with no think time | Maximal | 60 s | Whole run |

The probe is one course-summaries read every 2 s. It is the interactive read and it is free of admission, so its latency shows whether the interactive path stays responsive while heavy work runs. A probe p95 below 1 s is the interactive bound the line uses. The probe is not one of the 44 normal operations.

The meter profile compares load meters. A load meter is the rule that turns measured CPU and admitted activity into a load score and a regime. The 23 October comparison measured four such rules, including the starting one, a wider whole-host one, the selected score meter and a variant of the wider one with a lower release line.

The mixed heavy script of the worker comparisons chooses a planning or a graph direction by VU parity. An odd VU id runs the planning cycle and an even VU id runs the graph cycle. The planning cycle is the 37-operation multiset of 20 structure reads, five comparison reads, five basis-50 recommendations, five searches and two graph reads. The graph cycle is the 28-operation multiset of 20 graph reads, five searches, one comparison read, one structure read and one basis-3 recommendation, so it has no basis-50 recommendation.

Each VU starts at `(VU id × 7) mod cycle length` and advances one operation per iteration with its own think time. The 37-operation planning cycle therefore spans 37 iterations, not one iteration. A 120 s mixed cell issues one operation per iteration, so a VU completes a few operations, and the five basis-50 slots may fall inside or outside the reported window. A mixed heavy cell drew 0 to 4 basis-50 calls in its reported window. The ramp, not the mixed cell, is the controlled series for the heavy class.

## Virtual users, user counts and offered rate

A virtual user (VU) is one client loop. The loop runs its script until the run ends. A heavy VU in the planning or graph script runs one operation per iteration, then sleeps 8 to 15 s, and advances its cursor by one operation. A back-to-back VU, as in the heavy ramp, the large-input ladder and the admission heavy ladder, sends its heavy read every iteration with no think time.

A user count in the arrival script is a rate parameter, not a concurrent session. The script offers:

```text
arrival (operations per second) = users × 0.036667
```

Twenty users therefore offer 44 operations a minute, which is the normal mix, and 50 users offer 1.83 operations a second. The normal cycle holds 24 search operations, 10 structure reads, five graph reads, three comparison reads, and one recommendation and one next-courses read that swap place each cycle.

Offered rate is the rate the client attempts. It is not throughput. When requests wait in an admission queue, or a failed connection or a slow response holds a VU, the completed rate falls below the offered rate. The measurements give the offered profile and the completed count so the two are not confused.

## Warm-up, reported spans and percentiles

Each disposable batch warms its instance before its k6 client starts. The warm-up order includes a cold exact-code search and one read of each payload class used by the cell. The endpoint load profile warmed each shape and ran it three times, and its wall column gives the range over those repetitions. The total-CPU acceptance ran one idle instance and sent one request at a time. Its small-basis totals use one warm call and three measured calls per body. The cold exact-code search takes 3.5 to 4.3 s and is excluded from the reported percentiles. Its cost belongs to the first read of a fresh process, not to the steady state.

A steady heavy or light cell of the 22 October and admission tuning batches excludes its first 20 s. The excluded part covers the client start and the start offset of the heavy VUs. A normal cell reports its whole 180 s run after the cold search is removed. A ramp reports the whole timeline because the step is the subject, not a steady state. The 23 October meter profile runs 180 s and excludes its first 60 s as settle, then reports 120 s. That window is not a 20 s exclusion.

The fifth step of the admission cost ramp ends at the end of the 300 s scenario, so only one basis-50 call completed inside its window. Its completion count and rate are instrument-bound, and its p50 rests on one sample.

Sample counts differ by profile and window. The table gives the counts the method uses to read a percentile.

| Profile | Reported window | Recorded samples |
|---|---|---|
| Normal | 180 s | 91 probe samples |
| Planning heavy | Last 100 s | 0 to 4 basis-50 calls and 49 to 51 probe samples |
| Back-to-back heavy | Last 100 s and the full run for the rate | 13, 10 and 18 basis-50 completions over the full run at 1, 2 and 3 VUs, with 11, 10 and 18 in the reported window |
| Light arrival, worker ladder, 100 users | Last 100 s | 34 probe samples in the two-worker cell that stopped on its address-space cap |

These counts belong to different profiles and measured intervals. A range of 0 to 18 would mix the mixed heavy cells and the back-to-back cells. A range of 34 to 91 would mix a light-100 cell with a normal cell. Neither range describes one cell's reported window.

The latency tables report p50, p95 and p99, and usually the sample maximum. The percentiles are not averaged across cells, and a percentile from one cell is not a capacity bound. A p99 over 50 samples is close to the maximum, and a p50 over one sample is one call, not a central estimate. The measurement gives the sample count beside the percentile for that reason.

When a row gives one search p95, it is the largest of the exact, substring and semantic class p95 values, not a percentile of pooled search requests. Pooling would weight a class by how many requests happened to reach it.

## Why the profiles are not one cohort

A cohort is a fixed set of runs compared on the same inputs. The line has several cohorts, not one. The profiles change the arrival shape, the concurrent count, the request mix, the run length, the reported window and, in the admission batches, the scope flags.

The inputs also changed between batches. The endpoint profile of 19 October ran on the two-worker build with synchronous handlers. The two worker comparisons ran on separate product trees, the second with the lookup projection, the source-fact cache and the chunk cache. The admission cost pass held the second tree. The pinned dataset stayed the same across the serving batches, and the large-input pass added three spot inputs on a second dataset. The large-input pass and the admission tuning and meter batches each recorded their own product tree. A comparison holds its inputs fixed inside its batch, and a difference between batches can come from the build, the dataset, the payload set or the profile.

The only fixed-mix comparison across worker counts is the normal profile. It offers the same 44 operations a minute and the same request mix at every worker count. A mixed heavy cell adds a variable number of basis-50 calls, from 0 to 4 in a reported window, depending on where each planning VU starts in its 37-operation cycle and how long a recommendation takes. A heavy CPU per request therefore reflects that mix and is not comparable with another heavy cell. The heavy-class comparison is read from the ramp, where the VU count is the controlled variable, and from the back-to-back heavy ladder.

The light ladder of the worker comparisons raises the arrival rate of the normal cycle and keeps the frozen serving set, so its searches read inactive courses. The admission light ladder uses active-only searches. A rate from either light ladder is not a heavy rate, and the two light ladders are not one series.

The 23 October meter profile is a third shape. It runs 12 normal users beside 1 to 5 back-to-back heavy VUs, with 12 normal users alone and heavy VUs alone as its references. It is not the 20-user normal mix with a 37-operation planning cycle. Its measured window starts after a 60 s settle.

The admission tuning batch also measured one mixed cell with six heavy VUs beside 20 normal users at 44 operations a minute. That cell is not the 37-operation planning cycle of the worker comparisons and not the meter profile. Its heavy read is the inactive basis-50 recommendation.

A total across profiles would weight the slowest class by its share in whichever profile happened to include it. The method does not produce that total. Each comparison stays inside one batch and one profile, and a rate or a percentile is named with its profile, its window and its cell.

## Latency, CPU and server load

Four counters answer different questions. The client wall time is what a client waited. The worker process CPU is what the server spent. The whole-server CPU shows where the server spent it. The whole-host busy figure shows how much of the server the site and everything else used.

| Layer | What the counter is | What it includes | What it cannot separate |
|---|---|---|---|
| Client wall latency | Time from the client's send to the last response byte | Client, relay, front router, worker process, database and embedding service | The server stage shares |
| Worker process CPU | User and system CPU time of the worker processes over the sampler window | Python route work, database driver, serialization and compression, all threads of each worker | Time a request waits on a lock, a query, the embedding service or a heavy slot |
| Whole-server CPU | Worker tree CPU plus the database and embedding container counters | The instance's supervisor, front router and workers, the database and the embedding service | Another site's reads inside a shared container, and the relay's own CPU |
| Whole-host busy CPU | Busy CPU of every process on the server over the load window, divided by the window and the core count | The instance, the relay, other sessions and system work | Which process caused the busy time |

The gap between wall time and process CPU is waiting, not idle CPU. The serial first cost pass on the four-worker build measured an active-only basis-50 recommendation at 9.33 web core-seconds per call. That is a serial in-process cost for the active-only payload, not a price for the inactive heavy read. The large-input pass measured the inactive basis-50 recommendation at 13.50 web core-seconds per call. At higher concurrency the wall time of a basis-50 call grows to tens of seconds while measured web CPU at the knee is 1.93 of the four cores. Web CPU is not the bound, and the calls wait. The measurement does not sample the embedding service, so it does not establish which stage the wait sits on. The method makes no stronger causal claim than the measurement supports.

A request that waits for a heavy slot has wall time and no worker CPU at all. A cell whose CPU seconds exceed its wall seconds is running work concurrently.

The per-worker distribution is read from each worker's share of the web CPU, the combined CPU of the worker processes, not from its request count. In the capacity runs, request counts per worker were not observable without a product change. The CPU share and the request share can point at different workers, because one basis-50 call costs far more than one summaries call. A worker with many cheap requests can carry a small CPU share. The worker order in a record is the spawn order, not a stable identity.

The database and embedding counters cover whole containers. A read from another process sharing the counter in the same window is inside the delta. The per-class database share is therefore an estimate with that contamination, and the measurement states it rather than presenting the counter as the cell's exclusive cost. The worker and front-router counters are the disposable instance's own processes.

The whole-host busy figure is read from the kernel counter. It is not the instance's CPU plus a flat background allowance. The method measures the background in the same window, reports the residual other-host CPU and its spread, and does not subtract a fixed idle value. That is why a regime boundary carries a spread across cells.

The per-class costs come from a separate serial pass that sends one request at a time. A load cell sends overlapping requests, so its CPU is not the sum of class costs. The method compares the serial prediction with the measured CPU and reports the ratio. It does not add an idle baseline to either side. The class shares apportioned from overlapping request intervals are estimates, not an additive split.

## Server-clock alignment

The client clock and the server clock did not agree. Across the passes the client ran about 54 to 57 seconds ahead of the server. The measured values were 54.1 s in one batch, about 54 s in another, about 55 s in a third, 55.1 to 55.2 s in a fourth and about 57 s in a fifth. The offset was stable within a pass and was measured before a run or from the last client sample and the client exit.

The server sampler writes one row a second on the server clock. A window selected with client timestamps lands shifted by the offset. The worker-distribution judgement uses the middle 90 s of a 120 s run on the server clock. The whole-run share field, windowed on client timestamps, is not used for the judgement. One gate pair's saved window selected a 51 s tail in place of the middle 90 s. Its per-worker numbers are superseded by a window recomputed from the saved per-second series, and the corrected window can differ from the run centre by about 2 s because the sampler brackets the client run. The verdict does not turn on that difference.

The clock correction has a scope. In the admission cost batch, the saved per-step ramp CPU and core-utilisation fields mixed the two clocks. The analysis recomputed them with the measured 54.11 s offset, and the ramp table uses the recomputed values. That batch's per-class apportionment fields were not used. The large-input batch used neither its per-step nor its per-class apportionment fields. The saved records are not rewritten. This is an analysis correction, not a run correction. No cell is invalidated and no cell is rerun for the offset.

The load score has its own window. A 10 s window and a 60 s window were measured, and the selected score meter uses a 60 s window. A 10 s score can cross a regime boundary and return within one 60 s stage, and the method reports that oscillation rather than smoothing it. The run window and the score window are different measurements and are not substituted for each other. The score and its window are described under [the load score](/docs/backend/interfaces/admission-control.md#the-load-score).

## The relay and its two forms

The 19 October endpoint profile did not use a relay. Its sequential client sent to the running site, and the one concurrency check did the same. The context run also connected directly to the running site, with no relay. The disposable k6 cells from 22 October forward sent each request through a relay to the serving instance. The total-CPU acceptance sent one request at a time from a client on the server, with no relay. A relay figure therefore applies to the batches that used one, not to the endpoint profile, the context run or the acceptance run.

The relay is part of the measurement path, not part of the server capacity. Its own CPU stayed below half a core-second per run in the worker-count line, between 0.18 and 0.36 s per run in the high-load pass, and below 0.15 percent of measured total CPU in the large-input capacity runs. The distribution check ran the client in two connection modes, a fresh connection per request and kept-alive connections, and read the worker share in each.

The first relay created one thread per incoming connection and ran under a 536.871 MB address-space cap. At about 50 client connections it exhausted the cap and exited with a thread-creation error. The samples after that point are instant connection errors, not server responses. The affected heavy, ramp and light-50 cells are transport-invalid. They are not server limits, and their successful prefix is an observation only. The driver's "timed-out request" label came from treating any non-zero client error code as a timeout, and it does not mean the server timed out a request.

The replacement relay runs on one asyncio event loop and opens one upstream connection per incoming connection. It holds no thread and no process per connection. Its capacity check opened 128 connections and completed 128 round trips under the same 536.871 MB cap with no error. A second check completed 256 of 256. The check is an echo test against a local server, not the application. It proves that the transport carries those connections. It is not a load test, a throughput result or a server capacity proof, and the method does not use it as one.

One worker-count run was invalidated because the relay counted the client's connection resets at the end of a run as relay errors. The correction counted a peer reset as a close and kept a failed connection or an unexpected exception as an error. No payload, rate or duration changed.

## Memory bounds and guards

The line uses several memory instruments, not one. They are not interchangeable, and a failure under one is not evidence about another.

| Bound | Value | Applies to | What it bounds |
|---|---|---|---|
| Per-process address space, heavy cells | 2.684 GB | The launcher, every worker process and the resource tracker | Virtual address space, not resident memory |
| Per-process address space, light cells | 3.758 GB | Cells that carry the normal mix | Virtual address space, not resident memory |
| Memory cgroup fence | 6.442 GB | One disposable instance tree | Memory charged to the cgroup, including page cache |
| Memory-plus-swap cgroup fence | 6.442 GB, where both limits were read back | One disposable instance tree | Memory plus swap charged to the cgroup |
| Retained cache aggregate | 1.074 GB | The configured worker caches | The configured sum of the per-process shares, not a measured resident set |
| Worker RSS stop | 1.611 GB | One worker process | Resident set of one worker |
| Start floor and abort floor | 6.442 GB and 3.758 GB of available memory | The server before and during a run | Server memory pressure |
| Swap growth stop | 0.268 GB | One run | Swap growth during the run |
| The cgroup limit the memory proof ran under | 4.295 GB | The memory proof's six-process tree, for memory and memory-plus-swap | Its total memory and swap |

A per-process address-space limit bounds virtual address space, not resident memory. A process can fail an allocation under it while the cgroup is far from its memory ceiling. The first worker-count line ran the launcher, every worker and the resource tracker under a 1.611 GB limit. A basis-50 recommendation ramp raised MemoryError in a worker, and the server replaced the worker. That is an instrument limit, not a server rate. The following worker-count line sized the heavy cap from the measured virtual peak of one and two concurrent basis-50 calls plus headroom, rounded up to the next 268.435 MB boundary, and applied 2.684 GB. It was sized from that measurement rather than assumed.

A light cell that carries the normal mix needed more virtual address space. A light-100 cell ran under the 2.684 GB heavy cap and logged MemoryError lines and failed requests while the cgroup peak was 3.364 GB against the 6.442 GB limit. That cell is invalid as a rate point. The correction raised only the light cap to 3.758 GB and kept the cgroup fence, the floors, the swap stop, the worker RSS stop and the relay cap. The corrected cell has no MemoryError line and is a valid but non-graceful server result. Both cells are reported. A light-window ramp in the admission tuning batch ran under the heavy cap, logged 240 MemoryError lines and is invalid as light-mix evidence. The cap was corrected for the light cells and the run was repeated. Both runs stay reported.

A cgroup memory limit is enforced by the kernel OOM killer, which kills the process. A per-process address-space limit makes an allocation fail inside the process. The signatures differ, and a MemoryError is not evidence that the cgroup ceiling was reached. The memory-plus-swap fence is a separate kind of instrument. It writes `memory.limit_in_bytes` and `memory.memsw.limit_in_bytes` to the same value and reads both back.

The 6.442 GB memory-plus-swap fence applies only where both limits were written and read back. The worker comparisons, the admission cost pass and its ramp, the large-input capacity runs, the admission tuning runs and the meter runs wrote both values at 6.442 GB and read them back. The total-CPU acceptance wrote 6.442 GB to the memory limit and left the memory-plus-swap limit unlimited, because the server could not set that limit without swap accounting. That run proves the memory bound alone. The evidence disagrees on whether the server could set the memory-plus-swap limit. One group of runs reads it back at the fence value, and the acceptance run leaves it unlimited. The disagreement is unresolved. The method reports the per-batch evidence and does not present one combined proof for the whole line. It does not treat the missing facility as a passed guard.

The retained cache aggregate is a separate figure. It is the configured bound on the sum of the per-process cache shares, 1.074 GB. It is not a measured resident set, and the observed RSS is larger because the interpreter, the database driver and the request working set sit on top of the caches.

The disposable load batches apply these guards per run. A start floor checks available memory before the run, an abort floor checks it during the run, a swap-growth stop checks the swap change, and a worker RSS stop checks one worker. The total-CPU acceptance ran under the memory scope and recorded its own guard values. No guard tripped on a valid cell. A guard trip marks the cell invalid. It does not become a server limit. The address-space stops described above are instrument stops, and their cells are reported as invalid rather than as server limits.

The 4.295 GB limit is not part of the experimental fence. It is the cgroup limit the memory proof ran under, not a product setting, and it is tighter than the 6.442 GB experimental fence. The proof ran the supervisor, the front router and four worker processes inside it, for memory and for memory plus swap.

## One cell at a time and read-only data

A cell is one measured condition, such as one worker count with one traffic profile and level, run on a fresh disposable instance with its own relay and client. In the load-meter comparison, a cell is one traffic shape measured with one meter. The driver warms the instance, runs the scenario, stops the tree and checks that no process survives before the next cell. No two heavy cells share a server process, so a worker's retained cache, address space and admission state do not carry into another cell.

The endpoint profile of 19 October is not a set of disposable cells. It sent sequential requests to one running site, and the context run reused the running site without stopping or reconfiguring it. The total-CPU acceptance is one idle run with one request at a time, not a series of disposable cells.

The front router's admission state lives in its process memory. A fresh router therefore starts with empty counters, which is what a cell needs. A replacement router also starts empty, and the method does not compare a cell across a router replacement. Heavy placement puts an admitted heavy read on a worker process that carries no other heavy read, and the method reads the result from each worker's CPU share rather than from a request count. The placement rule is described under [placement on a worker process](/docs/backend/interfaces/admission-control.md#placement-on-a-worker-process).

The pinned database is read-only. The batches that report a tuple-counter check read the insert, update and delete counters of its user tables before and after the cell and found them unchanged. The total-CPU acceptance used the pinned database and left the configuration files unchanged. The context run served a different dataset, so no counter check applies to it. No migration, ingestion, embedding, inference, translation or administration command runs during a cell. The only write is the request record that the front router appends for every HTTP request, including a refusal. The record is a count delta on a shared file, so it can include requests from another process in the same window. It is not an exclusive attribution and it is not a catalogue write.

A cell is invalid if the measured product tree changes during the run. The fence compares the product paths, not the documentation paths, so a documentation-only change does not invalidate a cell and a product change does. One admission cost run was marked invalid because the check compared every path, including documentation files, and a documentation-only change landed during it while the product tree stayed identical. The check was corrected to compare only product paths. One meter cell is invalid because three browser files changed during it, and its repeat is the evidence. One context attempt failed only in the client's output copy and recorded no summary. The correction changed the copy paths, and no payload, scenario, rate or duration changed.

## Corrections that bound the evidence

The table lists the method failures that change how a number is read. A failed cell stays reported. A corrected cell is reported with its correction.

| Correction | What happened | Consequence for the evidence |
|---|---|---|
| Client timeout did not cancel server work | One graph and route profile point ran past the 240 s client timeout, and the server workers kept computing for about 30 minutes at 1.72 to 1.83 GB each until the service was restarted | A client timeout is not an endpoint cost, and that point is a failed attempt |
| Thread-per-connection relay | The first relay created one thread per incoming connection under the 536.871 MB cap and exited with a thread-creation error at about 50 connections. 21 of 39 driver invocations were transport-invalid | The affected cells are not server limits, and only their successful prefix is an observation |
| Async relay | The replacement holds no thread per connection. 128 of 128 connections completed round trips under the same cap, and a second check completed 256 of 256 | The transport carries those connections. The check is not a load or capacity proof |
| Heavy address-space cap on light cells | A light-100 cell and a light-window ramp ran under the 2.684 GB heavy cap and logged MemoryError lines and failed requests. The failures were address-space failures, not cgroup-memory failures | The cells are invalid as rate or light-mix evidence. The light cap was raised to 3.758 GB, and the corrected cells are reported separately |
| Clock mixing | The client clock ran about 54 to 57 seconds ahead. A client-stamped window selected a 51 s tail instead of the middle 90 s, and saved per-step fields mixed the two clocks | The distribution uses the server-clock middle 90 s. The admission cost ramp table uses per-step CPU recomputed with 54.11 s, and its per-class apportionment fields are not used. No cell is invalidated or rerun |
| Distribution gate | The first gate pair used a whole-span client window and could not be recomputed. The corrected pair saved a per-second series and measured the worker shares in both connection modes | The first pair is superseded. The gate measures concentration, not throughput |
| Product-tree identity check | One admission cost run was invalidated when documentation-only files changed during it while the product tree stayed identical. The check compared every path rather than the product paths | The check was corrected to compare product paths. The run recorded 160 requests with no error, timeout or non-2xx response, but it is not used |
| Load-meter state sampler | The state sampler failed and left an empty regime timeline in eleven runs of one meter variant and in two score-meter reference attempts. A third attempt stopped before the load run and left no measurement | The eleven cells have measured latency and completions but no regime series. The two completed reference attempts are invalid for the full comparison, and the selected reference is reported. The failed attempts stay reported |
| Memory-plus-swap unavailable | The total-CPU acceptance could not set the memory-plus-swap limit and records it as unlimited | That cell proves the memory bound alone. The other batches read both limits back. The disagreement is unresolved |
| Relay reset classification | One worker-count run was invalidated because the relay counted the client's connection resets as relay errors | The correction counted a peer reset as a close. No payload, rate or duration changed |
| Large-input driver path | The first large-input capacity batch stopped before k6 because the driver looked for a script in the wrong directory | The correction resolved each script from its own directory. No k6 time was spent and no run record exists |

## What the method does not establish

The method measures HTTP service under a synthetic client. It does not measure browser latency, rendering, interaction or the network from a browser. A client wall time is not a user-perceived time.

The user counts are rate parameters and VUs, not people. The line is not a user study. It does not measure satisfaction or task completion, and it does not replay a traffic mix observed in use.

The serving results are specific to one 4-core aarch64 server with 23.6 GB of RAM. The line does not share one build or one payload set across all its batches, and the endpoint profile did not read the pinned dataset. Each comparison holds its inputs fixed inside its batch, and a difference between batches can come from the build, the dataset, the payload set or the profile. The method does not turn any batch into a general capacity rating. A rate from the normal profile is not a capacity for the heavy profile, and a heavy rate from one worker count is not a rate for four.

The endpoint profile of 19 October predates the front router. It measured the server of that build one endpoint at a time, with two workers and synchronous handlers, and its process CPU includes the Python route work of that build. It is not a measurement of the 22 and 23 October shape. The serving line's first worker runs also used a relay to the server's HTTP listener before the front router existed. A wall time or CPU figure from one line is not a figure for the other.

A tail from a small sample is not a population tail. A heavy cell with one basis-50 completion has one sample, and its p50 is that sample. The measurement says so and does not present it as a stable percentile.

The method does not claim that every guard was available on every run. The memory-plus-swap facility was set in some batches and unavailable in the acceptance run. The method reports the per-batch evidence and does not promise a uniform success across all runs, all servers or all kernel settings.

The method is not a reproduction package. It states the conditions a reader needs to interpret the numbers. It does not promise a rerun or claim that a rerun would reproduce the values.
