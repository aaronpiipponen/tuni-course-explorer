# Serving cost and routing

This report measures what serving one request costs, what the four-worker setup carries, and how the front router places heavy work without a Redis store.

**Evidence status:** Corrected. **Run dates:** 21 and 22 October 2026.

## The question

This is the middle part of a three-part account of the serving worker processes, the [front router](/docs/reference/glossary.md#administration) and [admission control](/docs/backend/interfaces/admission-control.md). The worker-process-count comparison is [Serving workers and admission](/docs/experiments/runtime-storage-and-serving/serving-workers-and-admission.md), the applied limits are [Serving load and admission limits](/docs/experiments/runtime-storage-and-serving/serving-load-and-limits.md), and the shared load method is [Serving load measurement method](/docs/experiments/runtime-storage-and-serving/serving-load-method.md). This part covers the Redis footprint study, the measured cost of each request class and input variant, the capacity of one heavy user and of the light user ladder, the total-CPU pricing acceptance, the first distribution gate and its correction through the front router.

Three questions ran through the line. What transient memory does an opaque admission state need, and can that state live in a router process instead of a store? What does one request cost in core-seconds, and which inputs cross the heavy line? Does the four-worker setup spread heavy work across its worker processes, or does one worker process carry it?

Costs are CPU core-seconds unless a row states another boundary. A web cost is the serving process's CPU counter. A database or embedding cost is the whole container's counter, so it can include reads from other work on the same container in the same window. All memory sizes are decimal GB and MB. The measured runs used the pinned dataset and, for three spot checks, the served dataset.

## The Redis footprint study

On 21 October 2026 a disposable Redis 7.4.2 container ran with one Unix socket, no TCP port, no persistence and no network. The client stored only opaque state for an admission design that was measured and then dropped: half the keys were counters stored as strings set by `INCR`, and half were tickets stored as hashes with `created_ms` and a unit cost of one. Keys were generated deterministically with BLAKE2b from the case index. No identity, course, job, request body, profile, cookie or IP value entered a key or a value.

The container limit was 134.218 MB, `maxmemory` was 67.109 MB with `noeviction`, and the client ran in an isolated scratch environment under a 0.537 GB address-space cap. The client used redis-py 8.1.0 on Python 3.14.3. Its highest process high-water mark was about 34.3 MB, which is measurement client memory rather than product worker process or browser memory. The measurement ran on a 5.15 Linux kernel with the cgroup v1 memory controller, and the supervisor read the limit and usage from the container's cgroup files.

Each case populated one database, set one absolute `PEXPIREAT` deadline at the server time plus 2,000 ms on every key, and waited for `DBSIZE` to reach zero within 10 s. It then took three snapshots about 0.5 s apart. One population and one expiry were recorded per case, with no warmup. The three post-expiry snapshots are repeated reads of one retained state, not three independent population trials.

| Quantity (MB) | 1,000 keys | 10,000 keys | 100,000 keys |
|---|---:|---:|---:|
| Baseline Redis `used_memory` | 1.190768 | 1.190736 | 1.190704 |
| Baseline kernel cgroup charge | 9.367552 | 9.363456 | 9.371648 |
| Population-sampled kernel peak | 14.802944 | 14.712832 | 22.421504 |
| Run peak Redis `used_memory` | 1.504640 | 2.686624 | 13.483296 |
| Retained Redis `used_memory` after zero keys | 1.388432 | 1.378160 | 1.373520 |
| Retained kernel cgroup charge after zero keys | 9.998336 | 11.128832 | 22.159360 |
| Redis `dataset.bytes` at population | 0.282992 | 0.606992 | 3.846992 |

The kernel charge stays far above the Redis logical charge at every size, and the kernel charge outlives the keys.

![Kernel cgroup peak and retained charge are far above the Redis logical run peak at every key count, and both kernel figures reach their largest value at 100,000 keys.](/docs/charts/runtime-serving-cost-redis-footprint.svg)

At 100,000 keys the kernel charge peaked at 22.421504 MB and retained 22.159360 MB after `DBSIZE` was zero, within 0.262144 MB of its peak, while Redis logical `used_memory` had returned to 1.373520 MB. The observation window was about 1.5 s after the database emptied, so this is a short-window retention result, not a claim about decay over minutes. The largest run peak `used_memory` was 13.483296 MB, below the 67.109 MB `maxmemory`, and the largest kernel peak was 16.7 percent of the 134.218 MB container limit.

The allocator shows retention from a third direction. Resident allocator pages stayed high, with active and allocated pages below the resident figure.

| Case | Allocator resident after expiry (MB) | Allocator active after expiry (MB) | Allocator allocated after expiry (MB) |
|---:|---:|---:|---:|
| 1,000 | 16.187392 | 14.417920 | 5.525864 |
| 10,000 | 17.563648 | 13.697024 | 3.940608 |
| 100,000 | 27.525120 | 18.350080 | 3.674928 |

Redis self-reported RSS is a fourth measure, and it is not the kernel charge. It was higher than the cgroup value in every case.

| Case | Baseline `used_memory_rss` (MB) | Population peak RSS (MB) | Run peak RSS (MB) | Retained RSS (MB) |
|---:|---:|---:|---:|---:|
| 1,000 | 15.360000 | 15.998976 | 16.330752 | 16.330752 |
| 10,000 | 15.368192 | 16.244736 | 17.313792 | 17.313792 |
| 100,000 | 15.368192 | 23.904256 | 28.348416 | 28.348416 |

The five memory figures answer different questions and do not substitute for one another.

| Measure | Scope |
|---|---|
| `used_memory` | Redis logical allocator accounting. The run peak includes transient server allocation during later snapshot and arming work, measured 0.155544, 0.465088 and 3.584440 MB above the post-populate peak. It does not mean live key bytes. |
| `used_memory_rss` | Redis self-reported resident or allocator-backed value, close to the allocator resident figure but not identical. It was 28.348416 MB against a 22.421504 MB kernel charge at 100,000 keys, so it is not a budget for system RAM. |
| Kernel cgroup charge | The kernel's charge for the owned container, including the process image, allocator pages and page-cache effects. Its floor of about 9.37 MB is not dataset bytes. |
| `dataset.bytes` | Redis dataset accounting. At 1,000 keys the per-key sample implies 0.032 MB of counters and 0.052 MB of tickets while `dataset.bytes` reports 0.282992 MB. At 100,000 keys the sample implies 3.2 MB and 5.2 MB while `dataset.bytes` reports 3.846992 MB. The scopes are not reconciled. |
| `clients.normal` | Redis server-side allocation for the connected client, 0.023168 to 0.037760 MB. It is not the client process. |

The expiry itself completed cleanly at every size. All three cases reached `DBSIZE` zero inside the 10 s bound with no missing deadline.

| Case | Keys | Arm time (s) | Post-arm time to empty (s) |
|---:|---:|---:|---:|
| 1,000 | 1,000 | 0.014 | 2.321 |
| 10,000 | 10,000 | 0.160 | 1.970 |
| 100,000 | 100,000 | 1.451 | 1.031 |

The 100,000-key case spent 1.451 s of its 2 s window arming the keys, so its observed post-arm wait was 1.031 s. The total from the server-time deadline to empty was not longer than the 2 s expiry plus the 10 s wait bound.

### What the study did not settle

The arithmetic in the study proposed per-container allowances near the small-state and 100,000-key peaks and marked them unvalidated. A smaller enforced container cap was unmeasured. Pending request bodies, an RQ job payload, product worker process memory, a second instance and concurrent clients were also unmeasured. The study set no budget for the serving design, TTL, proxy rule, abuse limit, capacity or implementation.

RQ was rejected on two grounds. It stores job payloads and results in Redis, which the measured boundary excluded, and the feature routes are synchronous commands that return a final report, whereas RQ adds asynchronous enqueueing, job identifiers, result retrieval and a separate queue worker lifecycle. No RQ, product limiter, worker process, queue or admission code was implemented in this study.

The security and configuration choices stayed open. They included the anonymous cookie's lifetime, scope, renewal and rotation, the lifetime, truncation and salt of short-lived IP-derived keys, the trusted proxy hops and headers, transient key prefixes, TTLs, cleanup and rotation, capacity and cost policy, store access and operation, and any memory approval. None became a product value here.

### Failures and cleanup

The first 1,000-key attempt failed before the client started. The supervisor's cgroup mount parser used an awk variable name that the awk on the server rejected. The fixture was cleaned, the container and socket directory were verified gone, and the variable was renamed. The case ran once more after that one diagnosed correction, with no blind retry and no cap change. A setup-log line later failed on shell quoting. It wrote no measurement, and the value was recorded separately from the mount table.

Each measured container was removed with `docker rm -f` without `-v`. The image declares `VOLUME /data`, so four anonymous volumes remained. They were attributed to these runs by creation time and the anonymous-volume label, because no saved mount record or container-event mapping proves that ownership. The four `_data` directories were empty. They were removed and their absence verified. Absence does not prove ownership at deletion. One anonymous volume created on 6 October 2026 was left untouched. The supervisor change to `docker rm -f -v` and to verify each recorded volume was checked statically and not exercised by a new measured container.

The Redis line ends with no product budget. The store did not survive into the serving design, and the front router holds the admission state in process memory with no Redis container, socket or service.

## Request cost by class and input

The first cost pass loaded the application in one process on the pinned dataset and drove one POST at a time through the ASGI interface with gzip accepted and the body discarded undecoded. Each class got one untimed warm call and three timed repeats of five calls. CPU is the `time.process_time()` delta over a repeat divided by five. The pass recorded 176 requests in 4 minutes 19 seconds, and every response was gzip.

| Class | Mean (core-seconds per call) | Repeat range |
|---|---:|---|
| Search, exact | 0.933849 | 0.902131 to 0.953604 |
| Search, substring | 0.950417 | 0.942070 to 0.958411 |
| Search, semantic | 0.983512 | 0.976172 to 0.997089 |
| Structure | 0.066904 | 0.063096 to 0.073082 |
| Graph, two small payloads | 0.083734 | 0.074413 to 0.087432 |
| Compare | 0.107675 | 0.100427 to 0.115569 |
| Recommendation, basis 3 | 0.275784 | 0.266377 to 0.291839 |
| Recommendation, basis 50 | 9.329324 | 8.934359 to 10.061704 |
| Next courses, basis 3 | 0.126763 | 0.115414 to 0.134464 |
| Summaries, basis 50 | 0.020982 | 0.020016 to 0.021466 |

The measured means span more than two orders of magnitude, and the two cheapest interactive reads sit far below the recommendation class.

![Per-class mean web cost spans more than two orders of magnitude, from 0.020982 core-seconds for basis-50 summaries to 9.329324 for the basis-50 recommendation.](/docs/charts/runtime-serving-cost-classes.svg)

The database is an adjacent cost, not part of the web figure. One basis-50 recommendation read 3.95 to 3.98 database CPU-seconds per call beside 9.33 web core-seconds, and a search read about 1.12 database CPU-seconds per call beside 0.93 to 0.98 web core-seconds. The database carries the larger share of a search and the web process carries the larger share of a basis-50 recommendation. The database counter covers the whole container, so reads from other work on the same container can enter it.

The class costs summed over the normal mixed run predicted 77.110 core-seconds against 81.280 measured, a ratio of 0.9487. The prediction sat 5.1 percent below the measurement because the in-process pass excludes HTTP parsing, event-loop cost and the four-worker launcher. The ratio was reported and was not used to adjust any cost.

### Material input variants

A second pass measured 90 variants on the pinned dataset and three spot checks on the served dataset. Cheap variants got one warm call and three repeats of five calls. Expensive variants got one warm call and three single calls. The pinned pass returned 200 for every response and recorded 600 requests in 890 seconds. The served pass recorded 48 requests in 280 seconds.

The scope flag and the query length move a search more than the class name does.

| Variant | Web (core-seconds) | Database (core-seconds) | Wall p50/p95 (ms) |
|---|---:|---:|---|
| Exact, short query, inactive courses | 0.912731 | 1.117386 | 1844 / 1963 |
| Exact, short query, active only | 0.374722 | 0.526880 | 909 / 952 |
| Exact, ten-code query, inactive courses | 1.078708 | 1.126700 | 2317 / 2380 |
| Semantic, 25-word query, inactive courses | 1.253250 | 1.113323 | 2250 / 2380 |
| Structure, largest programme | 0.611996 | 0.936850 | 1614 / 1742 |
| Compare, fixed pair | 0.107949 | 0.093527 | 190 / 240 |
| Summaries, basis 200 | 0.031735 | 0.031772 | 58 / 60 |

The inactive scope is the expensive side for search, about 2.4 times the web cost and 2.1 times the database cost of the active-only scope on the short queries. Structure and compare stay below one core-second. Summaries are the cheapest measured class.

Recommendation and next courses scale with the basis and the scope.

| Variant | Web (core-seconds) | Database (core-seconds) | Wall p50/p95 (ms) |
|---|---:|---:|---|
| Recommendation, basis 50, active only | 10.419672 | 3.976182 | 8722 / 9878 |
| Recommendation, basis 50, inactive courses | 13.498728 | 5.599464 | 12720 / 12795 |
| Recommendation, basis 200, active only | 23.908396 | 11.336523 | 21492 / 23273 |
| Recommendation, basis 200, inactive courses | 33.093459 | 15.466511 | 31319 / 31328 |
| Next courses, basis 50, active only | 0.749295 | 0.147104 | 854 / 979 |
| Next courses, basis 50, inactive courses | 1.609683 | 0.156203 | 1748 / 1933 |
| Next courses, basis 200, active only | 1.295932 | 0.853629 | 2167 / 2214 |
| Next courses, basis 200, inactive courses | 2.612813 | 1.058436 | 3646 / 3825 |

Including inactive courses raised recommendation basis 50 from 10.419672 to 13.498728 and basis 200 from 23.908396 to 33.093459. It raised next courses basis 50 by 2.15 times and basis 200 by 2.02 times. The largest measured input was recommendation basis 200 with inactive courses, at 33.093459 web core-seconds and 15.466511 database CPU-seconds per call.

![Including inactive courses raises the mean web cost of a recommendation at both basis 50 and basis 200, and the basis effect is larger than the scope effect.](/docs/charts/runtime-serving-cost-material-variants.svg)

The graph measurement is a matrix of target, toggles, active scope and basis size. Within this matrix the drawing counts did not change with the basis.

| Graph state | Courses | Nodes | Edges | Elements | Web (core-seconds) |
|---|---:|---:|---:|---:|---:|
| PSY.324, both toggles, active only | 79 | 253 | 371 | 624 | 0.7006 to 0.7203 |
| PSY.324, both toggles, inactive courses | 248 | 564 | 1,170 | 1,734 | 0.922242 to 0.939821 |
| KAT.MARK.399, both toggles, active only | 66 | 370 | 629 | 999 | 1.039508 to 1.055916 |
| KAT.MARK.399, both toggles, inactive courses | 248 | 749 | 1,273 | 2,022 | 1.239842 to 1.285230 |

The largest graph is KAT.MARK.399 with inactive courses and both toggles on, at 248 courses, 749 nodes, 1,273 edges and 2,022 elements, for 1.285230 core-seconds. Every graph in the matrix exceeded the 500-element display limit, so each response carried the drawing counts and no display graph. That is the product's drawing allowance, not a failed request. The PSY.324 graph carries 564 nodes and 1,170 edges at 0.922242 to 0.939821 core-seconds.

The served dataset moved no input by more than about 9 percent except the graph's larger node and edge counts.

| Served-dataset spot check | Web (core-seconds) | Database (core-seconds) | Wall p50/p95 (ms) |
|---|---:|---:|---|
| PSY.324 full graph | 1.004780 | 0.225005 | 1282 / 1349 |
| Recommendation basis 50, inactive courses | 14.688188 | 5.625632 | 12876 / 14503 |
| Next courses basis 50, inactive courses | 1.564153 | 0.154033 | 1673 / 1853 |

The served graph carried 617 nodes and 1,274 edges against 564 and 1,170 on the pinned dataset, at 1.004780 against 0.922242 core-seconds. The served recommendation basis-50 cost 14.688188 against 13.498728, and the served next-courses cost 1.564153 against 1.609683. The three spot checks are too few to call a dataset effect.

### The heavy line moved after the first pass

The first pass put only recommendation basis 50 above 1.0 core-seconds and proposed that class as the only heavy one. The material variants superseded that proposal. At a 1.0 core-second line the heavy set also contains recommendation basis 200 in both scopes, next courses basis 50 with inactive courses and basis 200 in both scopes, the long exact and semantic search with inactive courses, the largest full graph in both scopes, and the three served-dataset spot checks. Search substring long with inactive courses (0.950485) and graph PSY.324 full with inactive courses (0.922242) stay below the line.

The implemented policy does not use that measured list as its class list. It classifies from the request route and shape against configured cutoffs, and the curves and cutoffs are on the [web server](/docs/backend/interfaces/web-server.md#admission-control). The measured set is evidence for where the line falls, not a selected class table.

## Heavy capacity and the light ladder

### The first ramp and its clock correction

The first pass also ran a five-step basis-50 ramp beside the normal mix and the interactive probe. The ramp stepped to one, two, three, four and five virtual users, reached each count over 5 s and held it for 55 s, and the step window was the at-target part. The knee was step 2. The basis-50 p50 rose from 10,711.26 ms at one virtual user to 28,942.79 ms at two, 2.702 times, while the probe p95 was 330.92 ms, below the 1,000 ms interactive bound. The measured web utilisation at the knee was 1.9320 of four cores.

Web utilisation rose from 1.5705 to 2.6665 cores across the five steps and never reached four, so web CPU was not the bound and the calls waited on the recommendation path. The database container was sampled and the embedding service was not, so the wait's owner was not measured. Step 5 completed one basis-50 call because the 300 s scenario ended with requests in flight. Its completion rate and p50 are instrument-bound and are not a server collapse.

The saved per-step CPU windows mixed the server clock with the k6 clock, which ran 54.1 s ahead. The saved knee utilisation of 2.3789 came from the shifted windows. A recomputation with the measured offset gives 1.9320, and the saved per-class CPU apportionment fields are unused. No run was invalidated and no measurement was rerun for the offset.

The first heavy-level run of the pass was invalid because the checkout revision moved during it, although the product tree did not change. The correction changed the identity check, added a continuation driver, re-froze the input manifest and reran only that run. The invalid record stayed in place and was not used. Every later run verified the re-frozen manifest.

The first policy drew its values from that ramp and the first pass's one-payload-per-class means: a capacity fraction of 0.45, C = 1.8 core-seconds a second, C × W = 108 core-seconds a minute, heavy slots of 3 falling to 1, and recommendation-50 as the only heavy class. Its heavy floor allowed 11 whole recommendation-50 users within C × W. The material variant pass measured long queries, inactive scopes and larger bases that the first payloads did not cover. Those measurements superseded the class proposal. A long inactive semantic search measured 1.253250 against 0.983512 for the first semantic mean, and recommendation basis 200 with inactive courses measured 33.093459.

### The measured heavy ladder

Each capacity run started a disposable instance with four worker processes and one relay, waited for the feature read, warmed seven payloads and started k6. The heavy runs issued basis-50 recommendations back to back with one summaries probe every 2 s and no normal mix. The reported window excluded the first 20 s.

| Heavy VUs | Completed calls, full / reported | Full-run calls per minute | Web core-seconds per call | Web CPU seconds | Web cores | Total cores |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 13 / 11 | 6.476 | 10.202 | 132.63 | 1.105 | 1.584 |
| 2 | 10 / 10 | 4.986 | 29.618 | 296.18 | 2.468 | 2.898 |
| 3 | 18 / 18 | 8.973 | 14.840 | 267.12 | 2.226 | 2.867 |

One heavy VU completed 13 calls in 120.45 s, or 6.476 calls a minute, at 10.202 web core-seconds a call. It used 1.1011 web core-seconds a second, 1.105 of the four cores, and 1.584 total cores with the database and embedding containers. The chart shows the full-run rate at the three heavy levels.

![The measured full-run basis-50 rate falls from 6.476 calls a minute at one heavy virtual user to 4.986 at two, then rises to 8.973 at three.](/docs/charts/runtime-serving-cost-heavy-capacity.svg)

The ceiling that lets one heavy user use 90 percent of that measured capacity is arithmetic on one worker process's measured rate, not a selected policy.

| Quantity | Value |
|---|---:|
| Full-run rate | 6.476 calls per minute |
| Reported-window rate | 6.600 calls per minute |
| Web core-seconds per call | 10.202 |
| Web capacity used | 1.1011 core-seconds per second |
| 90 percent ceiling in cores | 0.9910 core-seconds per second |
| 90 percent ceiling in core-seconds per minute | 59.461 |
| 90 percent ceiling in calls | 5.829 calls per minute |
| Total CPU of the run | 1.584 cores of four |
| Web CPU of the run | 1.105 cores of four |

Two VUs completed 4.986 calls a minute, 23 percent below one VU, at 29.618 web core-seconds a call. Three VUs completed 8.973 calls a minute, 1.386 times the one-VU rate, at 14.840 web core-seconds a call. Relative to one VU the three rates are 1.000, 0.770 and 1.386, and the per-VU rates are 6.476, 2.493 and 2.991 calls a minute. Two VUs are the knee of this ladder.

The heavy connections did not spread across the worker processes. One worker process carried 98.7 percent of web CPU at one VU and 99.4 percent at three VUs. Two VUs split 49.26 and 50.20 percent across two worker processes. The four-worker-process aggregate heavy rate is therefore unmeasured, and no value is inferred from the one-worker-process figures. The per-run web, database, embedding and relay shares belong to the endpoint load profiling part of this category and are not repeated here.

### The light ladder

The light ladder ran on the same setup with four worker processes, the normal 44-operation cycle at the user count and the same probe.

| Light users | k6 seconds | Full-run requests | Reported requests | Full-run operations per minute | Probe p50/p95/p99/max (ms) | Timeouts and non-2xx | `MemoryError` lines | Status |
|---:|---:|---:|---:|---:|---|---:|---:|---|
| 20 | 180.36 | 222 | 199 | 73.85 | 60 / 142 / 459 / 482 | 0 | 0 | Graceful |
| 50 | 122.31 | 282 | 234 | 138.34 | 136 / 493 / 1030 / 1341 | 0 | 0 | Graceful |
| 100, 2.684 GB cap | 132.93 | 438 | 399 | 197.70 | 3558 / 7377 / 10498 / 10959 | 119 | 17 | Invalid |
| 100, 3.758 GB cap | 150.34 | 398 | 354 | 158.84 | 3728 / 9413 / 11288 / 12060 | 43 | 0 | Valid, non-graceful |

Light 20 and light 50 were graceful, with probe p95 142 and 493 ms. The offered rate was 44 normal operations plus 30 probes a minute at 20 users, and 110 plus 30 at 50 users. Their full-run rates were 73.85 and 138.34 operations a minute.

The first light-100 attempt failed as an instrument. It ran under the 2.684 GB per-process address-space cap and recorded 17 `MemoryError` lines including a thread-start failure, 119 timeouts and non-2xx responses among its 438 full-run requests (399 in the reported window), and seven worker process identifiers from restarts. The 6.442 GB scope peaked at 3.36355328 GB with no fail count and no swap growth, so the scope was not the limit.

One correction raised only the light per-process address-space cap to 3.758 GB and left the scope, the start and abort floors, the swap stop, the worker memory stop, the relay cap and the teardown rules unchanged. Four worker processes plus the launcher reserve more virtual address space than the heavy cap allows. The corrected run had no `MemoryError` line, exactly four worker process identifiers, 43 timeouts and non-2xx responses out of 398 full-run requests (354 reported), and a probe p95 of 9,412.88 ms. Its scope peak was 3.714998272 GB, 57.7 percent of the 6.442 GB bound, with no fail count and no swap growth. The run is valid and non-graceful.

The ladder stops between 50 and 100 users. The first attempt is kept and is not used as a graceful point. Light 200 is unmeasured.

## Total-CPU pricing acceptance

One request was priced by all server CPU it uses from the start of processing to the response being sent, in core-seconds: the serving process, the database and the embedding service. A prerequisite graph was priced by its elapsed monotonic seconds over the same span, which includes database wait and compression, and only when the handler built the target's graph. The ten-key meter was the whole-host busy CPU against the machine's core count, summed over ten one-second keys that every worker process's sampler wrote.

The acceptance ran one disposable instance with four worker processes, admission enabled, a disposable Redis container and every admission value from the tracked file except the socket path. It served one request at a time on an otherwise idle server. The background load on the server was 0.379 core-seconds a second, 0.0948 of four cores.

| Recommendation body | Configured estimate at the measured revision | Three samples | Mean | Range |
|---|---:|---|---:|---|
| Basis 3, inactive courses | 1.0 | 0.7236, 0.7201, 0.8250 | 0.7563 | 0.7201 to 0.8250 |
| Basis 10, inactive courses | 3.70193 | 2.1830, 2.2030, 2.2790 | 2.2217 | 2.1830 to 2.2790 |
| Basis 3, active only | 0.4658 | 0.4720, 0.4729, 0.4586 | 0.4678 | 0.4586 to 0.4729 |

Each body was one warm call and three single measured calls. CPU is the sum of the instance's scope counter and the whole database and embedding container counters, divided by the calls. All nine calls answered 200. The two inactive totals fell below the estimates configured at the measured revision because the below-50 segment was an estimate through the cutoff point. The active basis-3 total matched its 0.4658 origin cost within 0.4 percent.

The applied inactive recommendation curve was then selected from the measured endpoints. It has an origin of 0.7563 core-seconds at basis 3, a slope of 0.39118 and a basis-50 total of 19.142 core-seconds, and the inactive recommendation heavy cutoff is basis 5. The measured revision had carried an origin estimate of 1.0 and a cutoff at basis 3. The basis-10 total of 2.2217 stays below the applied line, and that is the recorded reading of the two endpoints.

The measured revision ran with a heavy budget that fell from 120 to 24 core-seconds, heavy slots of 3, and queue caps of 64, 32 and 16 waiting reads. The later selection set the saturation budget to 40 core-seconds and retained the headroom budget, slot count and queue caps. A heavy read that finds no slot joins a first-in-first-out queue and waits without a time limit. The queue cap refuses only a read that finds the queue full.

### The ten-key meter

The ten keys of that meter hold one second each, written by every worker process's sampler. A deterministic check read ten keys that followed an observed sample transition and compared their sum with `/proc/stat` busy time at the same two instants.

| Window | Stored ten-key sum (core-seconds) | `/proc/stat` delta (core-seconds) | Relative difference |
|---|---:|---:|---:|
| Aligned ten-key window | 3.8100 | 3.8500 | 0.0104 |
| First window anchored on the reading second | 3.4900 | 3.2000 | 0.0906 |
| Second window anchored on the reading second | 3.9800 | 3.5800 | 0.1117 |

The aligned window agreed within 1.04 percent. The two anchored windows overshot because a key holds the interval that leads into its second, and four clustered worker processes write one key per second, so their sums count one boundary interval the `/proc` delta does not. Every window stayed far below 40 core-seconds, so the four worker processes do not each add the whole-host total.

The applied router reads one load score over a 60-second window, weighted from whole-host CPU, light admissions and heavy activity. The score, its weights and its lines are on the [admission-control page](/docs/backend/interfaces/admission-control.md).

### Caps and classes

The harness pinned the ten keys every quarter second and confirmed each regime by the heavy bucket the instance applied before a queue observation.

| Observation | Result |
|---|---|
| Headroom, inactive search | 200, heavy bucket 117.5 tokens, the 120 budget minus the 2.5 charge |
| Headroom, search with `include_inactive` false | 200, no heavy bucket |
| Headroom, three slots held and 64 waiting | 429 with `Retry-After: 5` |
| Saturation, probe inactive search | 200, heavy bucket 21.5 tokens, the 24 budget minus the 2.5 charge |
| Saturation, one slot held and 16 waiting | 429 with `Retry-After: 5` |
| Saturation, one slot held and one queued inactive search | Waited with one ticket, then answered 200 when the slot was released |

The first saturation refusal attempt hung for 120 seconds. The request joined the queue while the sampled utilisation was below the saturation bound and then waited without a time limit, as the policy states. The harness added a regime probe before each queue observation and a longer pin interval, then repeated the observations. No product code changed and the run was not repeated for independent confidence.

### The graph cost record

The first graph request sent an official code and stored no cost because its target was not the canonical identity. The repeated request sent the canonical identity and answered 200 in 1.3927 client-observed seconds, and the instance stored 1.3791899060015567 seconds under the canonical field, a difference of 0.97 percent. The graph field count was two. The same target's full inactive graph cost 1.285230 web core-seconds in the in-process pass, so the stored elapsed value was 7.3 percent above it. A CPU-bound build on an idle server explains the direction, and the stored value includes database wait and compression that a thread CPU measure does not.

The acceptance recorded only the canonical spelling. The front router records a build when the request's target string is the canonical identity or an exact official code of the root course, and each spelling is its own field measured on its own. The canonical-only record is therefore a narrower field set than the implemented router keeps.

The scope limit was 6.442 GB. The acceptance ran with its memory-plus-swap limit unlimited, so only its memory bound is proven. Swap growth was 0, both fail counters were 0, and the scope peak was 0.903856128 GB. The acceptance is one run at one request at a time on an otherwise idle server and is not a contention or latency curve.

## The failed distribution gate

Three constant heavy virtual users sent basis-50 inactive recommendations back to back for 120 s, with one basis-50 summaries probe every 2 s. Latency excluded the first 20 s. The share is each worker process's part of the four worker processes' web CPU over the middle 90 seconds, recomputed from the saved per-second series on the server clock.

| Item | New connection per request | Kept alive |
|---|---|---:|
| k6 wall seconds | 120.63 | 120.62 |
| k6 requests | 70 | 67 |
| Heavy completions | 9 | 6 |
| Worker process CPU seconds, by worker process | 0.28 / 63.92 / 25.48 / 136.50 | 81.52 / 77.77 / 86.78 / 0.64 |
| Worker process CPU share, by worker process | 0.12 / 28.26 / 11.27 / 60.35 percent | 33.04 / 31.52 / 35.17 / 0.26 percent |
| Maximum worker process share | 60.35 percent | 35.17 percent |
| Heavy p50 / p95 / p99 (ms) | 33,957.49 / 43,986.58 / 44,689.87 | 43,208.21 / 45,449.99 / 45,471.21 |
| Probe p95 / p99 (ms) | 136.90 / 189.37 | 194.88 / 319.03 |
| Server load mean | 0.7854 | 0.8678 |
| Highest worker process memory peak | 1.730510848 GB | 0.822382592 GB |
| Aggregate worker process memory peak | 3.886206976 GB | 2.461351936 GB |

With a new connection per request, one worker process carried 60.35 percent of the web CPU, above the half rule, and the run also recorded a worker process memory peak of 1.730510848 GB against the 1.611 GB stop. Kept-alive mode put 35.17 percent at its highest and passed every guard. The rule was either mode, so the gate failed and the work stopped before any other run. No curve was measured and no candidate value exists from this gate. The chart shows each worker process's share in the corrected pair.

![One worker process carries 60.35 percent of web CPU with a new connection per request, while kept-alive mode keeps the highest share at 35.17 percent.](/docs/charts/runtime-serving-cost-distribution-shares.svg)

### Instrument corrections

The first gate pair used a whole-span instrument. It measured a k6-timestamp span and held the per-second CPU rows in memory only, so neither the intended middle-90-second value nor a whole-run value could be recomputed. Its numbers are kept for transparency and are not used for the verdict.

| First pair, not used for the verdict | New connection | Kept alive |
|---|---:|---:|
| k6 requests | 69 | 70 |
| Slice worker process CPU share | 52.20 / 15.52 / 1.26 / 31.02 percent | 0.08 / 41.89 / 57.51 / 0.52 percent |
| Slice request share | 38.75 / 11.25 / 22.50 / 27.50 percent | 0 / 6.17 / 17.28 / 76.54 percent |

The corrected pair saved the per-second series and exposed a second defect. k6 stamped its samples with its own clock, about 57 seconds ahead of the server clock, and the driver applied the k6 start and end to rows stamped on the server clock. The selected window was a 51-second tail, not the middle 90 seconds. A recomputation centred a 90-second window inside the sampler span, which brackets k6 by about two seconds, and wrote the window beside the unchanged per-second series. The driver records the server-clock k6 start and end from then on. The new-connection share is far above half under every window offset tested, and the kept-alive share far below it, so the two-second uncertainty does not change the verdict.

The first form of the gate result stated that the same worker process carried the most requests and the most CPU in the first kept-alive run. The corrected table separates them. In that run 76.54 percent of the requests and 57.51 percent of the CPU sat on different worker processes.

An attempt at 18:02 UTC completed its k6 run and then failed before writing its record, on a missing input field. Its run directory was deleted before the corrected pair, so its measurement is not reported. That deletion departs from the rule that saved outputs stay unchanged and is disclosed here. Two harness defects were fixed before the first saved run. A counted launch called a replaced exec function recursively, and a remote hash check had a PowerShell brace error. Those attempts reached no k6 request.

The gate is two minutes per mode with 6 to 9 heavy completions. It answers concentration and memory only. It does not measure the heavy ladder, the light ladder, the queue caps and waits, the ten-second load-window response, fairness, failure paths, identity rotation or any tuning cycle. At saturation one heavy slot runs, so a long basis-50 call carries most of a worker process's CPU and a small number of completions can move the share.

## The front router and placement

One supervisor owns the configured listener and one ephemeral loopback listener for each of four worker processes, and it starts one front router on the configured listener and one plain worker process on each worker listener, as [the web server page](/docs/backend/interfaces/web-server.md#the-launcher-and-the-environment-handoff) describes.

An admitted heavy read runs on the least busy worker process that carries no heavy read, with the lowest index on a tie. A light or free read runs on the least busy worker process, which may carry a heavy read. One heavy slot fewer than `WEB_WORKERS` keeps a worker process free. A read holds its worker process until its response body ends. The router opens one connection per forwarded read and reuses none. A failed connection to a worker process ends the request with status 500, and the read is not retried or moved.

With admission off, every request goes to the least busy worker process with no cookie, classification, ticket, graph record or refusal, and the router appends one request record. The supervisor keeps every listening socket open. When the router or a worker process exits, a replacement starts on the same descriptor and the same serving generation. The other children keep serving, no port changes and no request is replayed. Only the exited process's in-flight requests fail, and a request routed to a worker process in the sub-second gap after it exits answers 500. A replacement router starts with empty admission state. `WEB_RESPAWN_EXIT_LIMIT` exits of one role inside `WEB_RESPAWN_WINDOW_SECONDS` stop every child and return nonzero for systemd. SIGTERM and SIGINT stop every child and return zero.

The admission counters, activity timestamps, tickets, queue entries and dataset-scoped graph costs live in the front router's process memory, with no persistence and no second store, as [admission control](/docs/backend/interfaces/admission-control.md) describes.

### Acceptance

The disposable acceptance ran four counted worker processes, one harness router, the tracked admission values and admission enabled as a process override only.

1. The feature read answered 200. `Set-Cookie` held `tce_anon` as 32 lowercase hexadecimal characters with `Max-Age=2592000`, `Path=/`, `HttpOnly`, `Secure` and `SameSite=Lax`. The request appended exactly one request record.
2. Three basis-50 inactive recommendations ran on three worker processes. A basis-3 inactive recommendation answered 200 while all three heavy slots were held. A basis-5 inactive recommendation stayed pending and raised the waiting count from 0 to 1. All five requests answered 200 and appended five recommendation records.
3. With the headroom and saturation lines overridden to 0.01 and 0.02 in the process only, the saturated state showed one running heavy request and 16 waiting. A seventeenth heavy request answered 429 in 0.0017 s with `{"detail": "Too much traffic"}` and `Retry-After: 5`. Releasing the slot let the first waiting ticket answer 200, and the second stayed pending. The four completed or refused requests appended four records.
4. The router's utilisation series tracked a separate `/proc/stat` window over 10 aligned samples with a maximum difference of 0.0378 and a mean of 0.019. Every sample selected the saturated regime, and the observed one slot with a 16-ticket cap is that regime's policy.
5. With admission off, a search answered 200 with no cookie and appended exactly one search record.

The heavy budget refusal was also exercised in the saturated instance. A second basis-50 inactive recommendation from the same cookie answered 429 with the same body and `Retry-After: 5`.

### The distribution check that passed

The check ran the same gate script, payloads, rates and durations in both connection modes, with four counted worker processes, one router and one relay. The relay capacity check was not repeated, and its saved result of 256 of 256 connections stands.

| Item | New connection per request | Kept alive |
|---|---|---:|
| k6 wall seconds | 120.60 | 120.54 |
| k6 requests | 58 | 57 |
| Heavy completions | 8 | 8 |
| Worker process CPU seconds, by worker process | 38.62 / 58.66 / 77.38 / 77.73 | 35.27 / 42.41 / 75.15 / 86.91 |
| Worker process CPU share, by worker process | 15.30 / 23.24 / 30.66 / 30.80 percent | 14.71 / 17.69 / 31.35 / 36.25 percent |
| Maximum worker process share | 30.80 percent | 36.25 percent |
| Heavy p50 / p95 / p99 (ms) | 47,757.85 / 55,031.08 / 55,365.64 | 43,912.60 / 56,984.37 / 57,006.26 |
| Probe p95 / p99 (ms) | 104.03 / 250.70 | 104.34 / 123.97 |
| Aggregate worker process memory peak | 2.996342784 GB | 2.972516352 GB |
| Router RSS peak | 71.84384 MB | 72.249344 MB |
| Router CPU seconds | 0.49 | 0.49 |
| Scope peak | 2.708742144 GB | 2.672779264 GB |
| Database / embedding / relay CPU seconds | 57.672 / 0.429 / 0.10 | 57.320 / 0.416 / 0.03 |

Both modes passed. No worker process recorded overlapping heavy intervals, with a maximum overlap of one on every worker process. Every worker process carried at least one heavy request. Each worker process's peak stayed between 714.555392 and 811.192320 MB, below the 1.611 GB stop. The highest share was 30.80 percent with new connections and 36.25 percent kept alive, both below half.

### Teardown, corrections and what the check does not say

Both runs stopped the router with SIGKILL after the 30-second SIGTERM wait, with three heavy requests in flight, and stopped the worker processes with SIGTERM. No process survived and both ports were free. The router exit of -9 is the measurement's wait bound, not an in-flight failure. The router bounds its own graceful shutdown at five seconds, and a disposable smoke stopped a supervisor with SIGTERM in 0.6 s with an empty tree and no listener. That bound was not exercised with an in-flight heavy request, because the distribution check ran before it.

A correction after the measurement added one guard so an identity that still holds a running light ticket is not expired, and one assertion to the adapted queue test. The correction lies outside the forwarding, placement, meter, usage and graph-cost seams that the acceptance and the check exercised. The focused tests and the full network-free suite were rerun on the corrected tree. The disposable acceptance and the distribution check were not repeated.

The check completed 8 heavy recommendations in each mode in 120 seconds, because one such request takes about 40 to 57 seconds at the measured working set. It answers placement and memory, not throughput. It reused the saved relay check and did not re-measure the graph build end to end through the router. The marker, the header strip, the elapsed measure and the cost cache are covered by tests, and the earlier graph-cost acceptance stands.

## The result that stands

The line ends with four worker processes, admission on, and a saturated heavy budget of 40 core-seconds. The selected meter and the other applied limits are covered in [Serving load and admission limits](/docs/experiments/runtime-storage-and-serving/serving-load-and-limits.md). The worker process count and admission limits are applied configuration, and the front router is the serving shape. The Redis study contributed no budget, and no Redis remains in the front-router design.

The measured cost of one basis-50 recommendation is 9.329324 core-seconds in the first pass and 10.419672 in the active-only variant pass, rising to 33.093459 at basis 200 with inactive courses. A long inactive semantic search costs 1.253250. The heavy class follows the request route and shape, not the load generator's label, because four of the five classes the heavy scenario named are light by measured cost.

One heavy user measured 6.476 basis-50 calls a minute on the worker process that carried it. The four-worker-process aggregate is unmeasured because the connections concentrated on one worker process at one and three VUs. The light ladder was graceful at 50 users and non-graceful at 100, and light 200 is unmeasured.

The first distribution gate failed at 60.35 percent with a new connection per request and also tripped the worker process memory stop. The front router's placement passed the same check at 30.80 percent with new connections and 36.25 percent kept alive, with no overlapping heavy intervals and every worker process carrying work. That correction is the result that stands.

Two results were not the selected policy. The 90 percent ceiling of 5.829 basis-50 calls a minute describes one worker process's measured capacity. The first policy also set 108 core-seconds a minute and 11 whole recommendation-50 users at its floor. The material variants and the applied curves superseded that policy.

## Limits

- The Redis study used one Redis version, one client version, one kernel and one server, with one container and one client at a time. It measured three sizes, one population each, and a short post-expiry window. It measured no concurrency, HTTP load, fairness, pending body, product client, second instance or total system memory.
- The first cost pass ran in one process without HTTP, with one warm call and three repeats of five calls for every class. The variant pass used the same warm call, three repeats of five calls for a cheap variant and three single calls for an expensive one. The database and embedding counters are whole-container. The graph drawing counts do not vary with the basis, so the matrix does not measure a basis effect on graph cost.
- The capacity pass measured one worker process's heavy rate at three concurrency levels. The four-worker-process aggregate, sustained rates above three concurrent basis-50 calls, light 200 and admission behavior itself are unmeasured.
- The total-CPU acceptance is one idle-server run at one request at a time. It carries no contention adjustment and is not a latency curve. Its memory-plus-swap ceiling is unverified because that run could not set the swap limit. It was not repeated for independent confidence.
- The distribution gate is two minutes per mode with 6 to 9 heavy completions. It measures concentration and memory, not the ladders, queue waits, fairness, failure paths or an identity rotation.
- The router acceptance and the distribution check were not repeated after that correction. The five-second router shutdown bound was not exercised with an in-flight heavy request. The relay capacity check was not repeated.
- The load client's clock ran 54.1 seconds ahead of the server in the cost and capacity passes and about 57 seconds ahead in the gate pass. The saved per-step and per-class CPU apportionment fields that mix the two clocks are not used.

## Setup details

The disposable copies of the site ran on a 4-core aarch64 server with 23.6 GB of RAM. The load client ran k6 v2.3.0 outside the server and reached the instance through one asyncio relay with a 0.537 GB address-space cap. The relay completed 128 of 128 connections in the cost passes and its saved 256 of 256 result stood for the gate and router checks.

The instances served the pinned dataset, with `SELECTED_DATASET_ENABLED=0`, and the served dataset for three spot checks. Both databases were at schema head `20261014_0018`. The basis file held 200 identities, and a body's basis size is the number of distinct nonblank identifier strings it contains. A `selected` basis uses the selected courses, or the completed courses when the selection is empty. Every other basis uses the completed courses.

The heavy scenarios sent one basis-50 recommendation per virtual user iteration with no think time and one summaries probe every 2 s. The light scenarios sent the 44-operation normal cycle at the user count with the same probe. The reported window excluded the first 20 s. The in-process passes drove one POST at a time through the ASGI interface, with gzip accepted, and timed with `time.process_time()` or the container CPU counters as the row states.

Every capacity and gate run started under a 6.442 GB memory and memory-plus-swap scope, wrote that value into both kernel files and read both back. The start floor was 6.442 GB of available memory and the abort floor was 3.758 GB. The swap-growth stop was 268.435 MB, the worker memory stop was 1.611 GB, the heavy per-process address space was 2.684 GB, the corrected light per-process address space was 3.758 GB, and the relay address space was 0.537 GB.

Before k6, the gate and router runs warmed seven requests: features, basis-50 summaries, exact search, structure, active graph, compare and one basis-50 inactive recommendation. The gate and router runs used four worker processes by `WEB_WORKERS=4`. Every run stopped its relay and instance, found no survivor process, and left both ports free. The serving tree's process list and the pinned database's tuple counters were unchanged before and after every run.

## Untested questions

- What four-worker-process heavy capacity would a connection distribution that reaches all worker processes measure? The one and three VU runs put 98.7 and 99.4 percent of web CPU on one worker process, so no aggregate value exists.
- Would 100 light users be graceful with a larger working set or a different connection pattern, and where does the ladder fail between 50 and 100? The corrected run was non-graceful and 200 users were not run.
- How do the 16-ticket saturated queue and the unbounded first-in-first-out wait distribute over a longer saturation, and what share of the recommendation wait belongs to the embedding service? The gate did not sample the embedding service and the queue observation was a single release.
