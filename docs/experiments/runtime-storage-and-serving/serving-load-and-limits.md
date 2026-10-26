# Serving load and admission limits

This report measures the admission policy under heavy and light load, compares four load meters, and records the selected settings and the memory proof.

**Evidence status:** Comparative. **Run dates:** 22 to 24 October 2026.

## The question

[Admission control](/docs/backend/interfaces/admission-control.md) prices each API read in core-seconds and limits it by class, cookie and load regime. The first question was whether the implemented limits keep the interactive probe near its idle latency while the server has headroom, bend it without a cliff as the server saturates, share capacity fairly among heavy users, and move regimes promptly on a 10-second whole-host CPU window.

The second question was which load meter should drive the regimes. A load meter is the rule that turns whole-host CPU and admitted activity into a load score and a regime. The two CPU-only meters that recorded a regime series did not consistently separate a few heavy users alone from the same heavy users beside normal traffic. The third question was which values to apply, and whether the serving tree fits a fixed memory ceiling.

The line measured the starting values first, tuned two of the three allowed knobs, compared four meters on the same eleven traffic shapes, and applied one meter. The tuning runs were validation and proposals. The selection and the memory ceiling came after them.

This is the last part of a three-part account of the serving workers, the front router and admission control. It covers the load meter, the admission limits and their tuning. [Serving workers and admission](/docs/experiments/runtime-storage-and-serving/serving-workers-and-admission.md) covers the worker-count comparison and the selection that ended it. [Serving cost and routing](/docs/experiments/runtime-storage-and-serving/serving-cost-and-routing.md) covers request cost, heavy placement and routing. [Serving load measurement method](/docs/experiments/runtime-storage-and-serving/serving-load-method.md) states the load profiles, the interactive probe and the payloads shared with the endpoint profiles.

## Setup and measurement definitions

### The instance and the traffic

Each router-era run started one disposable serving tree from the captured catalogue snapshot described in [the catalogue the experiments read](/docs/experiments/README.md#the-catalogue-the-experiments-read): four worker processes behind one [front router](/docs/reference/glossary.md#administration), on loopback ports, with the pinned dataset and admission enabled. A relay process carried a 536,870,912-byte address-space cap and forwarded each request to the serving instance. The two gate pairs ran before the front router existed, as four uvicorn worker processes behind a relay under the same cap. The load generator was k6 v2.3.0, run outside the server, and it opened either a new connection per request or kept-alive connections, depending on the run. The run used a 4-core aarch64 server with 23.6 GB of RAM.

The heavy profile sent one basis-50 recommendation that included inactive courses back to back, and a basis-50 course-summaries probe every two seconds. A basis-50 read is one whose basis holds 50 courses. The light profile ran the normal 44-operation cycle with active-only searches, at a stated number of users. A normal user is one client of that cycle. The meter comparison added a mixed profile of heavy users beside 12 normal users.

Latency percentiles exclude the first 20 seconds of a steady run. Ramp runs use the whole timeline. A steady heavy run lasted 120 seconds, and the two ramp runs used 60-second stages. Each meter cell repeated the same eleven traffic shapes: no heavy user with 12 normal users, one to five heavy users alone, and one to five heavy users beside 12 normal users. A cell is one traffic shape measured on one meter, and a virtual user (VU) is one heavy client. The meter tables name the cells h1 to h5 for one to five heavy users alone, b1 to b5 for the same heavy users beside 12 normal users, and n12 for 12 normal users alone.

### What a measurement counts

A completion is a 200 response from a heavy read. A refusal is a 429 response with `Retry-After`. A heavy call whose completion is missing or later than the measured window counts as in flight and is excluded from completions, so every meter cell with heavy users records one to three such calls. Per-user completions are read from each virtual user's own count, not from all responses, so fairness is read from completed work.

Each search p50 or p95 is the maximum of that percentile across the exact, substring and semantic classes, not a percentile of pooled search requests. Each selected normal-traffic cell holds eight completed samples per search class, so its tails describe a small sample.

The whole-host meter divides the busy CPU of every process on the server by the four cores. The load client ran outside the server, so its CPU is outside the measurement. The instance's own share is stated beside the whole-host total, and the residual other-host CPU is the difference. The load generator's clock ran about 55 to 57 seconds ahead of the server. Every meter run measured the offset and mapped every sample onto the server clock before selecting a window or a regime timeline.

## Validation of the starting limits

The first check was the distribution gate. It asked whether one worker process carried more than half of the four workers' web CPU over the middle 90 seconds of a run, in either connection mode. In the tree before the front router, with a new connection per request, three concurrent basis-50 inactive recommendations put 60.35% of the web CPU on one worker process, and that worker process reached an RSS peak of 1,730.510848 MB, above the 1.611 GB stop. Kept-alive connections put 35.17% at the highest. A failure in either connection mode failed the gate, so the line stopped before any curve was measured.

Its instrument needed two corrections before its own numbers were usable. The first pass measured a load-tool timestamp span and kept no per-second series. The corrected pair saved the series, and a second defect selected a 51-second tail because the load client's clock ran about 57 seconds ahead of the server-stamped samples. Recomputed on the server clock, the new-connection share stayed far above half and the kept-alive share far below, so the verdict did not change.

The front router then [placed each heavy request on a worker process](/docs/backend/interfaces/admission-control.md#placement-on-a-worker-process) that carried no other heavy request. The distribution gate ran again on that serving tree, in both connection modes, and passed: a maximum worker CPU share of 30.80% with a new connection per request and 36.25% kept alive, no worker process with overlapping heavy intervals, every worker process carrying heavy work, and worker process RSS peaks from 714.555392 MB to 811.19232 MB against the 1.611 GB stop. The later tuning pass reused that successful gate result and ran no further gate load. The runs below then measured the limits themselves.

### The heavy ladder

Eleven steady runs stepped one, two, three, five, six, eight, 12, 16, 24, 32 and 50 heavy users. The heavy columns count completed 200 responses only, and refusals are 429 responses with `Retry-After`.

| VUs | 200 | p50 ms | p95 ms | 429 | Probe p50 | Probe p95 | Per-VU 200 | Running / waiting max |
|---:|---:|---:|---:|---:|---:|---:|---|---|
| 1 | 8 | 12,755 | 14,630 | 0 | 65 | 95 | 8 | 1 / 0 |
| 2 | 6 | 34,138 | 45,774 | 0 | 73 | 143 | 3 / 3 | 2 / 1 |
| 3 | 5 | 65,664 | 66,924 | 0 | 75 | 166 | 2 / 1 / 2 | 1 / 2 |
| 5 | 5 | 66,253 | 102,367 | 0 | 74 | 134 | 1 / 1 / 1 / 1 / 1 | 1 / 4 |
| 6 | 5 | 67,822 | 108,357 | 0 | 75 | 132 | 1 / 1 / 1 / 1 / 1 | 1 / 5 |
| 8 | 5 | 66,499 | 104,849 | 0 | 76 | 102 | 1 / 1 / 1 / 1 / 1 | 1 / 7 |
| 12 | 5 | 64,718 | 104,531 | 0 | 77 | 147 | 1 / 1 / 1 / 1 / 1 | 1 / 11 |
| 16 | 5 | 65,460 | 104,812 | 0 | 73 | 115 | 1 / 1 / 1 / 1 / 1 | 1 / 15 |
| 24 | 4 | 65,319 | 88,077 | 3,299 | 92 | 198 | 1 / 1 / 1 / 1 | 2 / 22 |
| 32 | 5 | 78,883 | 111,923 | 3,431 | 84 | 178 | 1 / 1 / 1 / 1 / 1 | 2 / 30 |
| 50 | 4 | 70,236 | 108,534 | 63,970 | 260 | 388 | 4 VUs, one each | 1 / 16 |

The interactive probe p95 stayed between 95 and 388 ms at every level. At one heavy user the server utilisation was already 0.545 of four cores, and the probe p95 was 95 ms. At two users the heavy p50 rose from 12,755 ms to 34,138 ms, the measured two-call knee, and the two virtual users completed three calls each. At three users the server utilisation crossed 0.8, the running heavy count fell to one, and the heavy p50 rose to 65,664 ms while the probe p95 was 166 ms.

From three to 16 heavy users the heavy class held at five completions per window with a p50 of 64,718 to 67,822 ms, and the probe p95 stayed between 102 and 166 ms. At three users the three virtual users completed two, one and two calls. From three to 16 users the waiting depth grew from two to 15. From five to 16 users every completing virtual user took one completion. No refusal occurred below 24 users because the waiting count stayed under the middle 32-ticket cap and the saturated 16-ticket cap.

At 24 and 32 users the queue caps bound. The runs refused 3,299 and 3,431 requests with `Retry-After`, and the probe p95 was 198 and 178 ms. The regime alternated between middle and saturated, so the waiting peak was 22 and 30, while a ticket that joined during a saturated sample was refused by the 16-ticket cap. Four and five distinct virtual users each completed one call.

At 50 users the saturated 16-ticket cap bound throughout and 63,970 requests were refused. The probe degraded to p50 260 ms and p95 388 ms with no errors, and four virtual users completed one call each. The client resent immediately instead of waiting for `Retry-After`, so the refusal count measures admission refusals per offered request, not the completion rate of a compliant client.

The chart below shows the heavy p50 at all eleven measured levels.

![Heavy p50 rises from 12,755 ms at one virtual user to 34,138 ms at two, then lies between 64,718 and 78,883 ms from three to 50 virtual users. The eleven bars are the eleven measured levels.](/docs/charts/runtime-serving-load-heavy-ladder.svg)

The second chart shows the interactive probe p95 at the same eleven levels.

![The interactive probe p95 stays between 95 and 198 ms from one to 32 virtual users and reaches 388 ms at 50. The eleven bars are the eleven measured levels.](/docs/charts/runtime-serving-load-probe-ladder.svg)

The heavy-class step at the saturation bound is the policy's stated behaviour. The heavy class yields its own responsiveness first. Whether a rise from 12,755 ms at one user to 65,664 ms at three is a cliff is a policy judgement, not a measurement result. The measured levels skip four users, so a step at the headroom slot count plus one is not isolated. The five-user result matches the three-user result in completions and is close in probe latency.

### The light ladder

Three steady runs carried the normal 44-operation cycle at 50, 100 and 200 users.

| Users | Offered a minute | Dropped iterations | Probe p50 / p95 ms | Search p50 / p95 ms | Structure p50 / p95 ms | Server utilisation |
|---:|---:|---:|---|---|---|---:|
| 50 | 110 | 0 | 64 / 102 | 987 / 1,150 | 199 / 247 | 0.485 |
| 100 | 220 | 0 | 109 / 424 | 2,329 / 4,555 | 371 / 1,275 | 0.780 |
| 200 | 440 | 215 | 8,471 / 28,437 | 30,692 / 48,884 | 25,876 / 44,144 | 0.996 |

Light 50 stayed inside the one-second interactive probe bound. Light 100 had no failed request and no refusal, with an interactive p95 of 424 ms and searches at 4,555 ms p95. Light 200 exceeded the bound. The server was at 0.996, the interactive p95 was 28,437 ms, searches reached 48,884 ms p95, and 215 scheduled iterations were dropped. The arrival-rate pool and the CPU bound it, and no light request was refused at any level, so no per-user light limit bound. Light 400 was not run because light 200 exceeded the bound.

All four workers carried light work at light 100, from 0.183 to 0.352 of the web CPU each. The interpretation that the light side is a capacity bound of the shared server rather than a per-user limit follows from the absence of light refusals and from the server utilisation at light 200. It is an interpretation, not a separately controlled comparison.

### The load-window ramps

The heavy ramp stepped through seven 60-second stages over 420 seconds, at the heavy user counts in the table. The regime and the utilisation come from the router's one-second series.

| Stage | VUs | Utilisation mean / min / max | Last 20 s regimes | Oscillations |
|---:|---:|---|---|---:|
| 0 | 1 | 0.781 / 0.537 / 1.001 | middle, saturated | 2 |
| 1 | 2 | 0.848 / 0.629 / 1.001 | middle, saturated | 2 |
| 2 | 3 | 0.894 / 0.716 / 1.002 | middle, saturated | 2 |
| 3 | 5 | 0.914 / 0.634 / 1.003 | middle, saturated | 2 |
| 4 | 3 | 0.844 / 0.615 / 1.001 | middle, saturated | 2 |
| 5 | 2 | 0.857 / 0.680 / 1.001 | middle, saturated | 2 |
| 6 | 1 | 0.824 / 0.629 / 1.002 | middle, saturated | 2 |

The first regime transition after each of the six stage boundaries occurred at 60.0, 124.0, 185.0, 253.0, 304.0 and 362.0 seconds, so within 13 seconds of the boundary. The regime also flipped between middle and saturated 36 times in the 420 seconds, at intervals from one to 44 seconds. The regime was not steady in the last 20 seconds of any stage, and it oscillated twice per stage. It moved promptly and did not settle. Heavy completions totalled 17 over the 420 seconds, with a heavy p50 of 48,790 ms, a heavy p95 of 111,452 ms, a probe p95 of 182 ms and a waiting peak of four.

The light ramp stepped 110, 220, 440, 220 and 110 operations a minute.

| Stage | Offered a minute | Utilisation mean / min / max | Last 20 s regimes | Oscillations |
|---:|---:|---|---|---:|
| 0 | 110 | 0.768 / 0.506 / 1.002 | middle, saturated | 1 |
| 1 | 220 | 0.869 / 0.671 / 1.004 | saturated | 0 |
| 2 | 440 | 1.001 / 0.995 / 1.005 | saturated | 0 |
| 3 | 220 | 0.993 / 0.908 / 1.022 | saturated | 0 |
| 4 | 110 | 0.988 / 0.736 / 1.041 | middle, saturated | 1 |

The corrected run completed every response with status 200 except one client-side request error, had no refusals, and dropped 115 scheduled iterations in the whole run. The light mix crossed the middle band early and stayed saturated from 96.6 to 299.6 seconds. The rate drop at 240 seconds reached the middle regime at 299.63 seconds, 60 seconds after the drop, because in-flight normal requests drained slowly. The earlier down-step at 180 seconds produced no middle sample at all. The interactive probe p50 was 455 ms and p95 9,344 ms, with search classes at p50 22 to 24 seconds and p95 37 to 40 seconds.

### Identity rotation

Six concurrent basis-50 inactive recommendations ran for 60 seconds, each with a fresh anonymous cookie. Four calls completed, one on each of four distinct virtual users, with no refusals. The heavy p50 was 41,134 ms and p95 53,137 ms, the probe p95 was 104 ms, the running heavy count peaked at three and the waiting count at five. A rotated identity receives a fresh per-user budget, and the shared slots and queue bound it.

## Corrections and invalid runs

### The clock and the window

Three instrument corrections bear on the numbers above. The gate originally selected its 90-second window from the load tool's timestamps against server-stamped samples, which selected a 51-second tail. The saved per-second series allowed the window to be recomputed on the server clock without another load run, and the new-connection share stayed far above half under every offset tested.

The tuning driver then selected its run window and ramp timeline from the load tool's clock, which truncated a 120-second run to about 68 seconds of the sampler. It was changed to the server-clock span before the first measured run. Recomputed on a saved gate run, the server-clock window gave worker shares of 0.1573, 0.2489, 0.2966 and 0.2971, consistent with that run's 90-second values of 0.153, 0.2324, 0.3066 and 0.308. Every meter run measured the offset, 55.1 to 55.2 seconds, and mapped each sample onto the server clock.

### The invalid light ramp

The first light ramp ran under the heavy per-process address-space cap of 2.684 GB instead of the light cap of 3.758 GB. One worker logged 240 `MemoryError` lines, 239 requests answered 500 and 122 scheduled iterations were dropped. The automated guards did not flag the non-2xx responses, which is a gap in the guard. The run is invalid as light-mix evidence and is not used. The corrected run with the light cap is the evidence above, and it is the one diagnosed correction of the pass that repeated a run. No other run was repeated for a different number.

### The single forwarded 500

One forwarded probe request answered 500 in the light-100 cell at 105 seconds. The router log recorded connect and read errors to a worker process, the worker processes did not restart, and no other valid run shows a 500. It is one request in 433. The cause was not established in that pass.

A later diagnosis attributed it to the router reusing a worker process's idle keep-alive connection. The router opens a fresh connection for every forwarded read, so that reuse is not in the measured design. The later diagnosis is an interpretation of one event, not a reproduced failure.

### Teardown and background CPU

The measurement router served the same application without the product entry's five-second graceful-shutdown bound, so in-flight heavy responses held it past a 30-second SIGTERM wait. The router exited through SIGKILL in 17 of 25 tuning runs and 21 of 49 meter runs. The product entry carries the five-second bound, and a launcher smoke stopped in 0.6 seconds. The bound itself is measured in the memory proof below.

The background load on the server changed during the whole line. Three idle samples before the tuning pass measured 0.653, 0.616 and 0.352 busy core-seconds per second, which is 0.088 to 0.163 of the four cores. A sample during the pass measured 1.357 core-seconds per second, 0.339 of the four cores. The residual other-host CPU ranged from 0.46 to 1.79 core-seconds per second across the tuning pass.

Before the meter pass the idle samples were 0.351, 0.347 and 0.603, and the background load on the server varied during that pass. The per-run server utilisation spanned 0.184 to 0.925, and the residual other-host CPU 0.377 to 0.986. A regime boundary therefore carries that spread, and no comparison here is paired on background.

## Tuning the saturated budget and the light floor

### The saturated budget at 40 core-seconds

The starting saturated heavy budget was 24 core-seconds. A basis-50 inactive recommendation is charged 19.142 core-seconds, the configured total of web, database and embedding CPU, so 24 covered one charge and part of a second. The tuning cycle ran the four heavy levels whose behaviour that budget shaped, with the saturated budget set to 40 core-seconds, above two charges of 38.284 core-seconds.

| VUs | 200 | p50 ms | p95 ms | 429 | Probe p95 ms | Per-VU 200 | Running / waiting max |
|---:|---:|---:|---:|---:|---:|---|---|
| 3 | 8 | 43,707 | 57,357 | 0 | 113 | 4 / 2 / 2 | 3 / 2 |
| 6 | 8 | 58,838 | 99,283 | 0 | 147 | 2 / 1 / 1 / 1 / 1 / 2 | 3 / 5 |
| 12 | 8 | 77,937 | 107,566 | 0 | 126 | 1 / 1 / 1 / 1 / 1 / 1 / 1 / 1 | 3 / 11 |
| 24 | 9 | 69,002 | 116,045 | 4,489 | 143 | 1 / 1 / 1 / 1 / 1 / 1 / 1 / 1 / 1 | 3 / 22 |

Against the starting budget at the same levels, 40 raised completions from five, five, five and four to eight, eight, eight and nine. At three users it lowered the heavy p50 from 65,664 ms to 43,707 ms and the probe p95 from 166 ms to 113 ms. At six and 12 users the probe p95 was 147 and 126 ms against 132 and 147 ms. At 24 users the refused count was close to the starting budget's, 4,489 against 3,299, and nine distinct virtual users completed one call each. The running heavy count reached three in these runs, and no guard tripped.

The chart compares the two budgets at the four measured levels.

![Heavy completions at three, six, 12 and 24 heavy virtual users under the two saturated budgets. Completions rise from five, five, five and four under 24 core-seconds to eight, eight, eight and nine under 40.](/docs/charts/runtime-serving-load-budget-completion.svg)

The comparison is not paired. The 40 core-second runs ran later than their 24 core-second counterparts, and the background CPU moved between them. The completion gain and the lower three-user p50 are measured, and the attribution to the budget alone is bounded by that confound.

### The light floor at 0.5

The light floor scales the per-user light rate and concurrency at saturation. The starting floor was 0.25, which serves 30 operations a minute and two at once. A floor of 0.5 doubles those limits.

| Cell | Users | Dropped | Probe p50 / p95 ms | Search p50 / p95 ms | Server utilisation |
|---|---:|---:|---|---|---:|
| Starting, 100 | 100 | 0 | 109 / 424 | 2,329 / 4,555 | 0.780 |
| Floor 0.5, 100 | 100 | 0 | 108 / 314 | 2,212 / 4,434 | 0.787 |
| Starting, 200 | 200 | 215 | 8,471 / 28,437 | 30,692 / 48,884 | 0.996 |
| Floor 0.5, 200 | 200 | 232 | 7,699 / 22,973 | 32,857 / 49,671 | 0.992 |

The floor changed nothing measurable at these loads, because the per-user light rate never approached the scaled limit. Light 100 moved from a probe p95 of 424 ms to 314 ms and a search p95 of 4,555 ms to 4,434 ms, and light 200 moved from 28,437 ms to 22,973 ms probe p95 and from 48,884 ms to 49,671 ms search p95. The differences are inside the run-to-run and background spread. The applied floor is 0.25.

A mixed run with the floor at 0.5 placed six heavy virtual users beside 20 normal users at 44 operations a minute. Five heavy calls completed, one on each of five distinct virtual users, with no refusals, a heavy p50 of 57,303 ms, a probe p95 of 280 ms, normal searches at p50 1,300 ms, the running heavy count at three and the waiting count at five. The server was at 0.916.

### The third cycle

The third tuning cycle would run only when a measured failure named one of the three allowed knobs. No light refusal occurred at any measured level, so the light rate was not named. The saturated interactive tail was not explained by the light floor, because raising it changed nothing measurable. The stalled saturated heavy completion beside a responsive interactive probe named the saturated budget, and the 40 core-second cycle measured that knob. A third value for the same knob had no named failure behind it, so the third cycle was not run. The pass used two of the three cycles, and light 400 and the wider light continuation were unmeasured.

## Comparing the load meters

### The four meters

The validation above ran the starting CPU-only meter. The meter comparison asked whether a different meter separates heavy users alone from the same heavy users beside normal traffic by placing them in different [load regimes](/docs/backend/interfaces/admission-control.md#the-load-regimes). Four meters ran on the same eleven cell shapes, from one to five heavy users, alone and beside 12 normal users, which is 44 measured cells.

| Meter | Window | Headroom | Saturation | Release | What it measures |
|---|---:|---:|---:|---:|---|
| A | 10 s | 0.50 | 0.80 | none | Whole-host CPU only |
| B | 60 s | 0.60 | 0.90 | 0.80 | Whole-host CPU only, with a latch |
| S | 60 s | 0.60 | 1.05 | 0.90 | Whole-host CPU plus light and heavy activity |
| C1 | 60 s | 0.60 | 0.90 | 0.70 | Whole-host CPU only, with a lower release |

A ran a 10-second window with headroom 0.5, saturation 0.8 and no hysteresis. B ran a 60-second window with headroom 0.6, saturation 0.9 and a latch that entered at 0.9 and released below 0.8. S is the fitted score meter. C1 is B with the release line at 0.7.

A, B and S have a regime series for all eleven cells. C1 has latency and completion evidence for eleven cells and no regime series, because its state sampler stopped on an attribute fault before its first line and every timeline is empty.

### The fitted score

S combines three terms over 60 seconds.

```text
score = 1.0 x whole_host_cpu_utilisation_over_60s
      + 0.012 x light_admissions_in_60s
      + 0.004 x heavy_admissions_or_running_in_60s
```

The [load score](/docs/backend/interfaces/admission-control.md#the-load-score) has a headroom line of 0.60, a saturation line of 1.05 and a release line of 0.90. A score at or above 1.05 sets the saturation latch, and a latched site returns below 0.90. The fit used the measured B CPU means and maxima and the measured light and heavy admissions. Its estimated reference score was 0.49, and its estimated mixed means were 1.15 to 1.18. Those are sizing estimates, not measured simultaneous score maxima.

The fit used average admissions per minute rather than the instantaneous trailing count. Its estimate for two heavy users, 0.792 + 0.004 x 4.5 = 0.810, maps to about 82.7 core-seconds, not the 57 to 72 range written before the S runs. The measured S budgets were 58 to 64 core-seconds. The measured heavy-window maximum reached seven at five heavy users, so the heavy term reached 0.028 rather than an estimated maximum of 0.020. These fit approximations do not change the saved S measurements.

### Heavy completions and mixed-traffic latency

| Meter | h1 | h2 | h3 | h4 | h5 | Heavy alone | Ten heavy cells |
|---|---:|---:|---:|---:|---:|---:|---:|
| A | 10 | 9 | 8 | 7 | 8 | 42 | 79 |
| B | 9 | 10 | 9 | 9 | 10 | 47 | 88 |
| S | 9 | 10 | 10 | 8 | 12 | 49 | 91 |
| C1 | 8 | 8 | 9 | 8 | 10 | 43 | 82 |

With one to five heavy users alone, S completed 49 heavy calls over the five heavy-alone cells, against 42 for A, 47 for B and 43 for C1. The totals over all ten heavy cells were 79 for A, 88 for B, 91 for S and 82 for C1. At five heavy users S completed 12 calls with a p50 of 49,712 ms, against eight and 63,845 ms for A, 10 and 67,700 ms for B and 10 and 68,339 ms for C1. At four heavy users S completed eight against B's nine, and its p50 was 63,780 ms against B's 59,320 ms.

The chart compares the two completion totals across the four meters.

![Heavy-alone completions and all ten heavy-cell completions for meters A, B, S and C1. S completes 49 heavy-alone calls against 42 for A, 47 for B and 43 for C1, and 91 over all ten cells against 79, 88 and 82.](/docs/charts/runtime-serving-load-meter-completions.svg)

Beside 12 normal users, S put the four mixed cells from two to five heavy users wholly in the saturated regime with the latch held. Its normal search p95 was 3,121, 1,561, 2,715 and 3,920 ms at those cells. A measured 3,063, 8,903, 5,943 and 5,026 ms, B 2,379, 9,448, 5,928 and 5,150 ms, and C1 3,577, 4,279, 3,533 and 3,819 ms.

| Meter | b1 | b2 | b3 | b4 | b5 | Own reference | Worst ratio |
|---|---:|---:|---:|---:|---:|---:|---:|
| A | 1,495 | 3,063 | 8,903 | 5,943 | 5,026 | 1,056 | 8.43 |
| B | 1,794 | 2,379 | 9,448 | 5,928 | 5,150 | 1,026 | 9.21 |
| S | 1,904 | 3,121 | 1,561 | 2,715 | 3,920 | 1,070 | 3.66 |
| C1 | 1,826 | 3,577 | 4,279 | 3,533 | 3,819 | 1,518 | 2.82 |

S lowered the worst mixed search tail from 8,903 ms under A and 9,448 ms under B to 3,920 ms, but it did not restore the normal-only reference. Its search p95 was 1.5 to 3.7 times its own reference. The probe p95 under S was 110, 132, 106 and 152 ms against 86 ms for its own reference. The one-heavy cell was in the middle regime at 1,904 ms of search p95.

The chart compares the worst mixed search tail across the four meters.

![Worst normal-user search p95 in the five cells that place heavy users beside 12 normal users. S peaks at 3,920 ms against 8,903 ms for A and 9,448 ms for B, with C1 at 4,279 ms.](/docs/charts/runtime-serving-load-mixed-search.svg)

### Regime separation and fairness

Each cell gives the share of its measured window in the headroom, middle and saturated regimes, and a share of zero is omitted.

| Cell | A | B | S | C1 |
|---|---|---|---|---|
| n12 | 100% headroom | 100% headroom | 99.2% headroom, 0.8% middle | n/a |
| h1 | 50.8% headroom, 49.2% middle | 100% headroom | 86.7% headroom, 13.3% middle | n/a |
| h2 | 10.0% headroom, 50.0% middle, 40.0% saturated | 72.5% middle, 27.5% saturated | 100% middle | n/a |
| h3 | 25.0% middle, 75.0% saturated | 55.5% middle, 44.5% saturated | 100% middle | n/a |
| h4 | 4.2% headroom, 35.0% middle, 60.8% saturated | 50.8% middle, 49.2% saturated | 100% middle | n/a |
| h5 | 8.3% headroom, 19.2% middle, 72.5% saturated | 56.7% middle, 43.3% saturated | 100% middle | n/a |
| b1 | 20.0% headroom, 80.0% middle | 67.5% headroom, 32.5% middle | 100% middle | n/a |
| b2 | 2.5% headroom, 37.5% middle, 60.0% saturated | 55.8% middle, 44.2% saturated | 100% saturated | n/a |
| b3 | 37.8% middle, 62.2% saturated | 42.5% middle, 57.5% saturated | 100% saturated | n/a |
| b4 | 0.8% headroom, 42.5% middle, 56.7% saturated | 50.0% middle, 50.0% saturated | 100% saturated | n/a |
| b5 | 3.3% headroom, 29.2% middle, 67.5% saturated | 57.5% middle, 42.5% saturated | 100% saturated | n/a |

| Meter | h2 | h3 to h5 | b2 to b5 |
|---|---|---|---|
| A | 2 slots, 57 cs | 1 slot, 40 cs | 1 slot, 40 cs |
| B | 2 slots, 66 cs | 2 slots, 52 to 56 cs | 2 slots, 49 to 57 cs |
| S | 2 slots, 64 cs | 2 slots, 58 to 62 cs | 1 slot, 40 cs |
| C1 | n/a | n/a | n/a |

S alone held two to five heavy users alone out of saturation while holding their mixed counterparts saturated for the whole measured window. A and B had overlapping regime shares in those two states. Under B the absolute CPU mean differences between the three-to-five-user heavy-alone cells and their mixed twins were 0.003 to 0.012. The two-user pair differed by 0.033 and the one-user pair by 0.090. The light-activity term therefore supplies a signal beyond CPU, which is an interpretation consistent with those differences, not an isolated causal result.

Every one of the 44 measured cells recorded no 429 and no `Retry-After`. The heavy queue caps did not bind at one to five heavy users. The light count was zero in a heavy-only cell and about 26 admissions a minute beside 12 normal users, and the probe is free and outside that count.

### Evidence gaps in the meter comparison

The comparison is 44 selected cells, one run per cell, not a complete grid. No meter won every cell. S completed fewer calls than B at four heavy users, and its mixed search p95 at two heavy users, 3,121 ms, was higher than B's 2,379 ms and A's 3,063 ms. The evidence is one selected run per cell with varying background load on the server, not a replicated estimate of an isolated causal effect.

C1 has no regime series, so its regime shares, effective utilisation and the policy values at its mean are unmeasured. Its 44-cell comparison therefore contains 33 cells with regime evidence and 11 with latency and completion evidence only. The recorded pass flags and guards on those runs do not prove the timeline requirement.

Three attempts at the S reference cell preceded the selected run. One stopped on a missing meter attribute before the load run. Two completed about 181 seconds each with empty regime timelines after sampler faults, and both were recorded as passed because the driver did not check the sampler output. They are invalid as measurements and excluded. The reference cell took four attempts in all, which exceeded the one repeat allowed for that cell. That is an execution deviation, not extra independent confirmation of S.

One A cell is invalid because three browser files changed during it, so the measured product was not the same before and after. Its repeat is the evidence. C2, B with a 90-second window, was triggered by a measured peak-to-peak raw utilisation of 0.279 at three heavy users and six regime transitions at one heavy user, but 36.5 minutes of the load budget were left against its 39 minutes, so it was not run. C3, a CPU plus light-activity meter, was not triggered because S separated the two states. Missing evidence is not a passing proof.

## The score meter in the serving process

The selected meter was implemented in the front router and applied. One disposable run checked the implementation on the product tree: four worker processes behind the front router, admission on, the selected weights and lines, and a 60-second window. Three heavy clients each held their own cookie and issued the basis-50 inactive recommendation, then waited five seconds. Twelve normal clients each searched every 10 seconds. One request per client was in flight at a time.

The heavy-alone period lasted 90.0 seconds and the mixed period 91.2 seconds. Heavy traffic answered 13 requests with 200, and light traffic answered 81 with 200. There were no refusals, no 5xx and no driver errors, so the per-user budget and the queue caps did not bind at three heavy users. Heavy responses took 13,369 to 43,752 ms and light responses 1,007 to 19,145 ms.

| Observed window | Samples | CPU utilisation | Light count max | Heavy count max | Score | Position | Saturated samples |
|---|---:|---|---:|---:|---|---|---:|
| Final 30 s of heavy alone | 30 | 0.7495 to 0.8395 | 0 | 6 | 0.7657 to 0.8515 | 0.3681 to 0.5588 | 0 |
| Mixed | 91 | 0.7721 to 0.9341 | 63 | 6 | 0.7962 to 1.3212 mean, 1.651 peak | 0.4359 to 1.0 | 76 |

Every one of the 121 sampled lines in the two measurement periods equalled the configured weighted sum of its own terms within the printed precision, and every position and latch followed the configured lines. No fault was recorded. The final 30 seconds of heavy traffic stayed in the middle regime and never entered saturation, because every score in that window was above the 0.60 headroom line. The regime of the earlier part of the heavy-alone period is not asserted. The mixed window reached saturation and held it for 76 of its 91 samples. Its peak sample reads CPU 0.883, 63 light admissions in the trailing window and three heavy admissions or running.

```text
1.0 x 0.883 + 0.012 x 63 + 0.004 x 3 = 1.651
```

The mixed window held one heavy slot, a queue cap of 16 and a budget of 40 core-seconds at its saturated position, and at most two heavy tickets waited. The background load on the server measured 0.602 busy core-seconds per second with the disposable tree stopped. Because the score counts every process on the server, that background is part of the CPU term.

The run also measured memory. The scope peaked at 2,636,525,568 bytes of a 6.442 GB limit, `memory.failcnt` was 0, and swap growth was 0. Swap was already effectively full at the start, so zero growth does not exercise growth headroom. Teardown ended each of the five processes on SIGTERM with exit -15 and left no listener. The router logged one shutdown line because two in-flight requests outlived its five-second graceful bound.

This is one run. It establishes that the implemented meter computes the selected score and latch, and that its policy values follow, not that it improves latency or capacity. It is not an additional load study.

## Selected settings

| Setting | Applied value | Meaning |
|---|---|---|
| `WEB_WORKERS` | 4 | Four worker processes behind the front router |
| `ADMISSION_ENABLED` | `true` | The front router classifies the nine fixed API POST paths, and a free read takes no limit |
| `ADMISSION_HEAVY_BUDGET_CORE_SECONDS` | 120 | Heavy budget at the headroom line |
| `ADMISSION_HEAVY_BUDGET_SATURATED_CORE_SECONDS` | 40 | Heavy budget at saturation |
| `ADMISSION_HEAVY_SLOTS` | 3 | Heavy slots at headroom, capped at three by four workers |
| `ADMISSION_HEAVY_QUEUE_HEADROOM_LIMIT` | 64 | Waiting heavy reads at headroom |
| `ADMISSION_HEAVY_QUEUE_MIDDLE_LIMIT` | 32 | Waiting heavy reads in the middle regime |
| `ADMISSION_HEAVY_QUEUE_SATURATED_LIMIT` | 16 | Waiting heavy reads at saturation |
| `ADMISSION_LIGHT_OPERATIONS_PER_MINUTE` | 120 | Light rate at headroom |
| `ADMISSION_LIGHT_BURST` | 20 | Light burst |
| `ADMISSION_LIGHT_CONCURRENCY` | 8 | Light concurrency at headroom |
| `ADMISSION_LIGHT_LOAD_FLOOR` | 0.25 | Share of the light limits at saturation |
| `ADMISSION_WINDOW_SECONDS` | 60 | Heavy budget window |
| `ADMISSION_LOAD_WINDOW_SECONDS` | 60 | Score window |
| `ADMISSION_SCORE_CPU_WEIGHT` | 1.0 | CPU term weight |
| `ADMISSION_SCORE_LIGHT_WEIGHT` | 0.012 | Light admission weight |
| `ADMISSION_SCORE_HEAVY_WEIGHT` | 0.004 | Heavy admission or running weight |
| `ADMISSION_SCORE_HEADROOM` | 0.60 | Headroom line |
| `ADMISSION_SCORE_SATURATION` | 1.05 | Saturation line |
| `ADMISSION_SCORE_RELEASE` | 0.90 | Release line |

The serving configuration applies four worker processes, admission on and a saturated heavy budget of 40 core-seconds. The other admission keys hold the values they had before the selection. The selected score meter adds a 60-second load window, the three weights and the three score lines above. With four worker processes the heavy slot count caps at three, so three slots run below a load position of one half, two from one half up to saturation and one at saturation.

The example configuration carries the same values, four workers, admission on and 40 core-seconds. Heavy work was placed on at most three worker processes with one heavy read each, and all four carried light work, so the four-worker count matches the measured curve. At light 100 their shares were 0.183 to 0.352 of the web CPU.

## The memory ceiling

### The retained-cache aggregate and the cgroup ceiling

The serving tree has two different memory bounds, and they are not interchangeable. The [retained-cache aggregate](/docs/backend/interfaces/web-server.md#the-dataset-scoped-retained-caches) bounds the sum of the per-process cache shares. The cgroup ceiling bounds the memory of the whole tree.

The per-process cache share is the lookup projection bytes plus the source-cache entries times their entry size plus the chunk-cache entries times their entry size. One process holds 158,086,050 bytes, four processes hold 632,344,200 bytes, and the aggregate is 1,073,741,824 bytes (1.074 GB), which leaves 441,397,624 bytes of headroom. Six shares, 948,516,300 bytes, fit the aggregate, and seven shares, 1,106,602,350 bytes, exceed it. The settings validator refuses a worker count whose share product exceeds the aggregate. Nothing measures a cache at runtime.

The cgroup ceiling is separate. The final memory proof ran under a cgroup limit of 4,294,967,296 bytes (4.295 GB) for memory and the same value for memory plus swap, and the supervisor, the router and the four workers all ran inside that one cgroup. That value was the budget for the six processes together, and it is the serving-tree proof limit.

### The kernel proof and the measured limits

The ceiling was proved in two steps. A disposable proof ran one allocator under a 268.435 MB memory limit. Both the memory limit and the memory-plus-swap limit read 268.435 MB in every sample. The allocator child returned -9 from SIGKILL, not `MemoryError`, and both maximum-usage files reached the limit. `memory.failcnt` ended at 0, and `memory.oom_control` reported `oom_kill 1`. The kernel log recorded one memory-cgroup OOM kill of the allocator process. That is kernel enforcement of the ceiling on the server.

The measured tree then ran with `memory.limit_in_bytes` and `memory.memsw.limit_in_bytes` both at 4,294,967,296 bytes. Its peak usage was 409,788,416 bytes (0.410 GB), `memory.failcnt` was 0 and no OOM kill occurred. The shell, the documentation shell, the feature read and the HTTPS shell answered 200, and the settings read reported four workers and admission on. The server had booted with `swapaccount=1` on its kernel command line, the memory-plus-swap limit and usage files existed, and the server ran systemd 239 on cgroup v1.

| Figure | Bytes | GB |
|---|---:|---:|
| Retained-cache aggregate bound | 1,073,741,824 | 1.074 |
| Serving-tree proof limit, memory and memory plus swap | 4,294,967,296 | 4.295 |
| Summed `VmHWM` of six processes | 2,787,553,280 | 2.788 |
| Cgroup maximum usage | 409,788,416 | 0.410 |
| Kernel proof ceiling | 268,435,456 | 0.268 |
| Highest aggregate worker RSS | 3,437,277,184 | 3.437 |
| Highest single worker RSS | 994,643,968 | 0.995 |
| Worker RSS stop | 1,610,612,736 | 1.611 |

The chart compares the memory bounds with the measured peaks.

![The serving-tree proof limit is 4.295 GB, the summed process high-water marks are 2.788 GB and the retained-cache aggregate is 1.074 GB. The cgroup maximum usage is 0.410 GB and the kernel proof ceiling is 0.268 GB.](/docs/charts/runtime-serving-load-memory-envelope.svg)

The earlier proof ran the same six processes under a 6.442 GB memory limit with the memory-plus-swap limit unlimited and no swap free. All 11 requests answered 200, and three basis-50 recommendations were in flight after two seconds. The summed `VmHWM` of the six processes was 2,787,553,280 bytes (2.788 GB) against the 4.295 GB bound. That sum adds six independent high-water marks and is not a simultaneous peak.

The product router exited 5,479 ms after SIGTERM, inside the 5.5-second allowance of the router's 5.0-second graceful shutdown plus the supervisor's 0.5-second stop poll. It was above the 5.0-second assertion the run carried, so that assertion failed and the trailing teardown assertions were not recorded. Each in-flight request ended with an empty reply and a client connection error. The proof therefore passed its memory bound and its request checks, but it is not a blanket pass.

The ceiling work ran no load cell, load generator run, browser check or database suite. It is a kernel-enforcement proof and a startup check, not a sizing run under heavy load. The 0.410 GB peak was measured during startup and light reads.

## What the evidence supports

The measurements support these statements. The starting limits held the interactive probe between 95 and 388 ms from one to 50 heavy users, completed heavy work at every level, refused nothing below 24 users, and bound the middle and saturated queue caps from 24 users. The light side carried 50 and 100 users without a refusal and lost 215 scheduled iterations at 200. The 40 core-second saturated budget raised heavy completions from four or five to eight or nine in the four measured cells. The selected score meter held two to five heavy users alone out of saturation and held their mixed counterparts saturated, completed the most heavy-alone calls, and lowered the worst mixed search p95 from 8,903 and 9,448 ms to 3,920 ms. The kernel proof enforced a memory ceiling, and the measured tree ran well below that ceiling during startup and light reads.

The evidence does not support a claim that any meter wins every cell, that S restores normal-user latency to its reference, that the selected meter causes the latency difference in isolation, or that the memory ceiling holds under heavy load. The validation ran a 10-second CPU-only meter, so its regime boundaries, slot counts and budget at a given level do not describe the applied 60-second score meter. The tuning comparisons are not paired on background. The meter comparison is one run per cell with a small search sample. The ceiling is not a sizing run.

## Limitations

- Each measured cell is one run. No repetition, variance or confidence interval is recorded. No run was repeated for a different number. The two exceptions are the one diagnosed light-cap correction, which repeated an invalid run, and the S reference cell, which took four attempts.
- The whole-host CPU meter includes every process on the server. The residual other-host CPU ranged from 0.46 to 1.79 core-seconds per second in the tuning pass and 0.377 to 0.986 in the meter pass, and the background load on the server varied during the meter pass. The reference search p95 moved from 1,026 to 1,518 ms across the four meter references, so each ratio carries that spread.
- The search tails rest on eight completed samples per class in each normal-traffic cell. The probe is one synthetic course-summaries read, not a browser session.
- Completions exclude one to three in-flight calls per meter cell. The 50-user refusal count comes from a client that resends immediately and ignores `Retry-After`, so it is not a compliant-client completion rate.
- The validation ran the 10-second CPU-only meter. The 60-second score meter was selected later, so the validation's regime shares and policy values at a level are not the applied behaviour.
- C1 has no regime series. C2 was not run for budget, and C3 was not triggered. Normal-user latency at the reference level while three to five heavy users run was not measured.
- The meter fit used average admissions per minute, and its estimates differ from the measured budgets and the measured heavy term. The fit approximations do not change the saved measurements.
- The earlier load proof ran under a 6.442 GB memory limit with the memory-plus-swap limit unlimited and no swap free, and it carried three in-flight recommendations. The final memory proof ran under 4.295 GB for memory and the same value for memory plus swap, and the check ran during startup and light reads, not under heavy load. The summed `VmHWM` is not a simultaneous peak, and swap was effectively full in the earlier proof, so zero swap growth there does not exercise growth headroom.
- The worker RSS stop is 1.611 GB, and the highest single worker RSS in the meter pass was 0.995 GB.
- The measurement router omitted the product's five-second shutdown bound, so in-flight heavy responses held it past a 30-second SIGTERM wait and it exited through SIGKILL in 17 of 25 tuning runs and 21 of 49 meter runs. The product-router proof in the memory run recorded a 5,479 ms exit, inside the 5.5-second allowance of the 5.0-second graceful bound plus the 0.5-second stop poll and above the 5,000 ms assertion that run carried, so that assertion failed.

## Untested questions

- Whether the selected score meter lowers normal-user latency under a repeated, paired run with controlled background load on the server is untested.
- Whether the serving tree stays within the 4.295 GB proof limit under the heavy load that produced the 3.437 GB aggregate worker RSS, and what the true simultaneous peak of the six processes is, are untested.
- Whether C2's 90-second window would reduce regime transitions without losing S's separation, and whether any meter can restore normal-user search latency to its reference, are untested.
