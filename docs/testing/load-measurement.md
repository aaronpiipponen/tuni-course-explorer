# Serving load measurement

The serving load tooling measures request cost and served load on a disposable stack from one shared workload and one machine configuration.

## What the tool measures

The tooling has two measurement entry points and one fitting step. The cost matrix sends the workload's request bodies one at a time against a fresh disposable supervisor and records the web, database and embedding core-seconds around each call. The k6 entry point produces a run bundle for the configured load client, and its summarizer turns each completed level and the server-side counters into one recorded result. A saturation view applies the light-throughput stop rule over a profile's level results.

Both entry points read `tools/load/workload.json` and the machine configuration at `tools/load/machine.toml`. A change to the pool, the user generation, the cycles or the capacity section starts a different baseline, and a result records the workload version it used. Additional matrix cases add measured bases without changing the capacity baseline. The tooling never imports experiment code.

The measured process tree is the product supervisor, its router and its workers. The supervisor and every descendant sit in one cgroup pair that the launcher creates for the run. The disposable database and the embedding provider are containers, and their own cgroups supply those two components. Every counter read raises when its cgroup file is missing, so a missing counter never becomes a zero.

## Database and checkout

The measurements run against a disposable database whose name ends with `_test`. The launcher refuses any other database name. The database must carry the schema and the derived search tables its checkout expects, and the checkout must carry or reach its serving artifacts.

The launcher runs one disposable checkout copy. A commit argument extracts that commit into `data/load/checkouts/` with `git archive`. A checkout argument uses a copy as it is. The tool refuses the live checkout, any checkout whose data root resolves to the live `data/` directory, and any checkout that is a Git work tree, so a disposable copy comes from `git archive` or from rsync without `.git`. The copy's own `data/usage/requests` receives the run's request records, and the result records that file's line count before and after the run.

A checkout that serves the embedding features reads its artifact family under the `--admin-state-root` directory. The product's serving artifact command writes that family and its derived tables, as [Serving artifact build](/docs/backend/text-and-vectors/serving-artifact-build.md) states.

The checkout's native libraries are files that its serving processes map at load time. Overwriting the bytes of a mapped library changes the code a running worker executes and crashes it, so a replacement writes the library to a separate file and renames it over the library path. `scripts/build_native.py` replaces the serving libraries that way, and a running stack serves the build it mapped until its processes restart.

## Machine configuration

Copy `examples/load/machine.toml` to `tools/load/machine.toml` and replace its values with the machine's own. `data/load/` holds the run state, the copied checkouts, the bundles, the counter records and the results.

The `[stack]` and `[worker]` sections hold these values:

| Key | Meaning |
|---|---|
| `web_host`, `web_port` | The loopback address the supervisor binds |
| `web_workers` | The worker processes the supervisor forks |
| `web_memory_mib` | The memory cap the run's cgroup enforces, in MiB |
| `database_host`, `database_port`, `database_user` | The disposable measurement database server |
| `embedding_host`, `embedding_port` | The loopback embedding provider |
| `database_container`, `embedding_container` | The containers whose cgroups supply the database and embedding counters |
| `cpu_cgroup_root`, `memory_cgroup_root` | The writable parent of the run's cgroup pair |
| `host`, `user`, `directory`, `k6` | The load client and its paths |
| `tunnel_host`, `tunnel_user`, `tunnel_port` | The SSH target the load client reaches to open its forward |
| `forward_port` | The loopback port on the load client that carries the forward |

The database name and the administrative state root are command arguments rather than machine values. `launcher.py start` and `matrix.py` require `--database` and `--admin-state-root`, and `k6.py bundle` requires `--database`. The database name must end with `_test`, and the state root must lie inside the disposable checkout.

The stack, database and embedding hosts must be `127.0.0.1`, so a measurement never binds a public interface. The load client is outside the server. It reaches the stack through one SSH local forward that it opens to the stack's loopback port, and every k6 command sends to `http://127.0.0.1:<forward_port>`. The bundle's run commands print that forward.

The database password is not a machine configuration value. The disposable cluster uses the synthetic password the launcher carries, and `TCE_LOAD_DATABASE_PASSWORD` overrides it for a cluster with its own value.

## The workload file

`tools/load/workload.json` holds one versioned workload. A change to the file increments its `version` field, and the matrix result, the k6 summary and the fit record that version. The file holds these sections:

| Section or field | Contents |
|---|---|
| `note` | A free-text description of the workload |
| `seed` | The seed of the pool ranking and of every simulated user's random stream |
| `display_language` | The display language of the search, recommendation and next-course request bodies |
| `pool` | The 500 course identities the simulated users draw from |
| `graph_selected` | The 30 historical course codes the matrix supplies as graph selections |
| `users.light`, `users.heavy` | The starting basis range, the inference setting, the inactive-scope probability and the study root count of each user class |
| `users.add_probability`, `users.remove_probability` | The chance that one behaviour-loop iteration adds or removes one pool course |
| `users.think_time_seconds_min`, `users.think_time_seconds_max` | The pause range after each response |
| `users.target_from_basis_probability` | The chance that a graph target or a comparison course comes from the user's basis |
| `cycles.light`, `cycles.heavy` | The fixed interleaved operation order of each user class |
| `capacity` | The shared user ladder, the level length, the settle window, the saturation rise, the heavy-user interval and the profile names |
| `matrix` | The cost matrix cases, its warm-up bodies, its sample count and its miss sample count |

The `pool` section holds 500 course identities the users draw their basis from. The tooling checks that the list is non-empty, that every entry is a non-empty string and that no identity repeats, and it reads each identity's stored context from the database.

A light user starts with 10 to 20 pool courses, sends active-only requests, disables inference on every request and sends one study root. A heavy user starts with 50 to 100 pool courses, enables inference on every prerequisite, recommendation and next-course request and sends 20 study roots. A heavy scope-aware request, which is a prerequisite, recommendation, next-course or search request, chooses active-only scope with probability 0.8 and including-inactive scope with probability 0.2.

Both classes draw the add and the remove chance independently before every request. The starting ranges are not bounds on the evolving basis. After each response each user waits a pause drawn uniformly from 5 to 20 seconds from its own seeded random stream. The pause is the last draw of the iteration, so it adds one value to the stream without shifting any request draw. A graph target or a comparison course comes from the current basis with probability 0.5 and from the pool otherwise. A search query is a pool course's full English title, its Finnish title when no English title exists, or its code.

The light cycle holds 12 title searches, 12 code searches, 10 study requests, five prerequisite drawings, three comparisons, one recommendation and one next-course request. The heavy cycle holds 10 title searches, 10 code searches, 10 study requests, seven prerequisite drawings, three comparisons, two recommendations and two next-course requests. The `cycles` arrays state the order. A non-search operation follows a search except at a few adjacent pairs, so no run of three non-search operations occurs in either cycle. Each user starts at the cycle position `(user number × 7) mod cycle length` and advances one operation per iteration.

The user generator seeds one random stream from the workload seed and the user number, so the same seed and user number produce the same starting basis and the same request sequence on every stack. The `user_class` k6 tag names the simulated light or heavy class. It is not the product's per-request admission class.

## The capacity ladder

The capacity section holds one shared ladder: 10, 20, 40, 60, 80, 100, 150, 200, 250, 300, 400, 500, 750, 1000, 1500, 2000 and 3000 users. Each level runs for 300 seconds from its first request. k6 waits up to 30 seconds after that for an in-flight request, and the drain is outside the measured window. The first 30 seconds of a level is its settle window, and the remaining 270 seconds is its measured window. The summarizer reports both windows, and the `saturation` command applies the stop rule to the measured window. A larger coarse level is added to the file when light throughput continues to rise at the largest level.

The `light_only` profile makes every user light. The `mixed` profile makes every user whose number is a multiple of `capacity.heavy_every` heavy and every other user light. The workload sets `heavy_every` to 10, so a level of 10 or more users holds 90 percent light users and at least one heavy user. Every level is one k6 invocation with a constant user count. Users one to n of a level hold the same seeds and the same request sequences as users one to n of the previous level. One virtual user holds one simulated user's state, and no arrival-rate executor hands iterations to arbitrary users.

The saturation rule stops one stack and profile combination after the first level whose light successful requests per second in the measured window rise less than 10 percent over the previous level, or fall. Heavy refusals and heavy latency never stop a combination. The `saturation` command computes the rule from the per-level results.

## The cost matrix

Run the matrix against a prepared checkout copy:

```bash
./.venv/bin/python tools/load/matrix.py \
  --checkout /path/to/disposable/checkout \
  --name matrix-1 \
  --database course_explorer_test \
  --admin-state-root data/admin-cpu-test
```

The launcher starts a fresh supervisor and a fresh cgroup pair. The matrix builds its payload context from the measured stack's environment, so the explicit study version follows the measured copy's curriculum year. The matrix resolves the pool's codes, titles and study roots from the database, sends each warm-up body the configured warm-up sample count, then sends each case. A case with a cache records the configured number of misses on distinct request bodies of the same shape, then the configured number of samples on the first body. A recommendation or next-courses miss takes distinct pool offsets of the same basis size, and a search miss takes distinct pool courses. A body whose cache key the run already requested is skipped, so every miss sample is a genuine miss. The result labels each sample with the cache event it produced.

A search case without a cache records one distinct pool query per sample, and every other case without a cache records the configured number of warm samples. Any status other than 200 stops the run with the case label, the status and the start of the response body. `--no-instrument` starts the stack without the cache-event wrapper, and the matrix accepts it only when no case needs a cache event.

The result is `data/load/results/<name>.json`. Its `cases` list holds the request body, every sample and a per-state summary with the median, mean, minimum, maximum and standard deviation. Its `memory` object holds current and peak bytes for the three components. Its `background` object holds the whole-host busy core-seconds less the measured component core-seconds.

Its `fit_inputs` list holds one entry per measured case that has an admission class, with its class, its explicit `include_inferred` value, its basis size, the mean, median and range of total core-seconds over its miss samples, the sample count, the median elapsed seconds and the report's result count. The admission fit reads `fit_inputs` directly. Inference is not an admission dimension, so an inference-enabled recommendation, next-course or graph case carries the same class as the official request at that route and scope, and the fit uses the inference-enabled rows of a recommendation or next-courses class because the capacity workload enables inference on its heavy requests.

Each case may set `accept_gzip` to true to ask for the compressed catalogue body, and the result records the response encoding. A study case may set `include_unavailable_roots` to send 18 available roots and two unavailable ones, or `explicit_version` to send one root with its explicit current module version.

The matrix uses the five chosen graph targets and the 30 historical selected course codes. It sends every prerequisite, recommendation and next-course case in both its official form and an inference-enabled form at the same target, basis and activity scope. It sends the graph cases with the request model's `active_only` default of false. It records each graph target's drawing element count and solver piece count beside its cost. The matrix also records the largest graph target's elapsed cost, so a class below the graph heavy threshold is visible in the result.

## The admission fit

Fit the admission curves from one matrix result:

```bash
./.venv/bin/python tools/load/fit.py data/load/results/matrix-1.json
```

The fit reads the result's `fit_inputs` and keeps the inference-enabled rows of each recommendation and next-courses class. It averages the rows of one basis size and gives every measured basis equal weight. Each input is a mean over distinct cache misses of one request shape, and each point carries its sample count, minimum and maximum. Each curve is `base + head * min(n, knee) + tail * max(0, n - knee)`, with the configured origin and nonnegative coefficients. The tool searches every integer knee between the smallest and largest measured basis, solves each of the eight subsets of the three coefficients with NumPy least squares, and checks each candidate curve against the measured crossing. The selected curve is the candidate that passes the crossing check with the smallest squared residual. A class whose candidates all miss the check reports its smallest-residual candidate and the failed check.

The crossing check holds two conditions:

- The curve's prediction at each measured basis around the first measured crossing, and one basis on each side, lies inside that point's measured range.
- The applied cutoff falls after the last measured basis below the threshold and at or before the first measured basis at or above it.

It reports the measured spread, every knee and its residual, and the residual after the costs and slopes are rounded to five decimal places. The origin cost is `base + head * origin` and the tail cost is `base + head * knee`. It also reports the smallest basis where the rounded curve reaches the configured threshold, and the measured inactive-search cost and graph elapsed costs. The tool writes no product value by itself.

## The k6 bundle

Build a run bundle from the workload and the measurement database:

```bash
./.venv/bin/python tools/load/k6.py bundle \
  --name run-1 \
  --database course_explorer_test
```

The bundle is `data/load/bundles/run-1/`. It holds `workload.json`, the resolved `payload-context.json`, `bundle.json`, `lib.js`, `warmup.js`, `light.js`, `mixed.js` and `run-command.txt`. `bundle.json` records the bundle name, the workload version and seed, the dataset, the capacity values and the worker forward. The payload context resolves the pool titles, codes and study roots from the measurement database. It takes the academic year that selects the explicit study version from `CURRENT_ACADEMIC_YEAR` in the environment it receives, and the product's normalization settings validate that value. `k6.py bundle` passes the year of the tooling checkout that runs it.

`lib.js` loads the workload and payload context once through k6's `SharedArray`, so every virtual user reads one shared copy. It gives every simulated user one stateful basis, one random generator seeded from the workload seed and that user's number, the class cycle and the class request rules. The profile scripts open one connection per request, because the pause between requests exceeds the server's keep-alive timeout and a reused idle connection fails with EOF.

`warmup.js` sends the workload's warm-up bodies for the configured warm-up sample count in one virtual-user iteration. `light.js` runs one light-only level. `mixed.js` runs one mixed level. Both profile scripts read the level's total user count from `LEVEL` and set one constant-vus scenario.

`run-command.txt` holds the copy command for the load client, the SSH local forward, the fixed warm-up and one command for every level of both profiles. Each command sets `BASE_URL` from `forward_port`. Each level command writes a raw JSON file named after the profile and the level. The level script's `handleSummary` writes the matching summary file with the run duration, options, thresholds and metrics. The tool never contacts the load client.

Every profile request carries `user_class` and `operation` as k6 tags. Each response adds one point to the `request_duration` trend with those tags and its response status. The profile scripts use `constant-vus` only, so each virtual user holds its own state for its whole life. The profile scripts set `http.expectedStatuses(200, 429)`, so an admission refusal is an expected response. A request that receives no server response records status 0 and adds to the `transport_failure` counter. One threshold fails the run: `unexpected_status: ['count==0']` fails on any status other than 200, 429 or 0. The profile scripts record one clock offset from the first response's `Date` header.

## A capacity run

Start one stack and keep it for one stack and profile combination:

```bash
./.venv/bin/python tools/load/launcher.py start \
  --checkout /path/to/disposable/checkout \
  --name load-1 \
  --database course_explorer_test \
  --admin-state-root data/admin-cpu-test
```

`./.venv/bin/python tools/load/launcher.py status --name load-1` prints the state the launcher recorded for that stack, and a name with no recorded stack fails with an error.

Open the bundle's SSH local forward on the load client and keep it open for the combination. Run the bundle's warm-up command once against the fresh stack.

Each level is one k6 command from `run-command.txt`. Start the counter sampler on the server before that command and stop it after the command:

```bash
./.venv/bin/python tools/load/k6.py counters --name load-1 \
  --seconds 360 --output data/load/results/counters-load-1-10.json
```

The sampler duration covers the level, its start and its 30-second drain.

The sampler writes one sample every 0.25 seconds with the three cumulative CPU counters, the web cgroup's current memory and the server clock. It records the memory state and the whole-host CPU at its start and its end. Every 5 seconds it also records the web cgroup's `memory.stat` counters and each web process's resident size, so a memory trend separates anonymous growth from file cache and attributes it to a process. A `SIGINT` or `SIGTERM` ends it and writes the file.

Copy the level's summary and raw files back to the bundle, then summarize that level:

```bash
./.venv/bin/python tools/load/k6.py summarize \
  --k6-summary data/load/bundles/run-1/summary-light_only-10.json \
  --k6-raw data/load/bundles/run-1/raw-light_only-10.json \
  --counters data/load/results/counters-load-1-10.json \
  --cache-events data/load/stacks/load-1/cache-events.jsonl \
  --profile light_only --users 10 \
  --output data/load/results/load-1-light_only-10.json
```

Run the next level of the same profile on the same stack, with a fresh counter record. A fresh stack and one fixed warm-up precede the other profile. After the levels of one profile, apply the saturation rule:

```bash
./.venv/bin/python tools/load/k6.py saturation \
  --results data/load/results/load-1-light_only-10.json \
            data/load/results/load-1-light_only-20.json \
  --output data/load/results/load-1-light_only-saturation.json
```

The saturation result lists each level's light successful requests per second, its rise over the previous level, its light success latency, its light refusal rate and its light refused latency. It sets `stop_level` to the first level that meets the stop rule.

Stop the stack after the combination:

```bash
./.venv/bin/python tools/load/launcher.py stop --name load-1
```

The launcher stops only the supervisor it started and removes only the cgroup pair and, for a commit checkout, the copy it created. A recorded process whose command line or cgroup does not match its state file is left alone.

## The summarizer result

The summarizer writes one JSON document with these parts:

| Part | Contents |
|---|---|
| `profile`, `users` | The profile and the level's total user count |
| `window` | The counter sampler's start, end and length |
| `k6` | The k6 test duration, the configured level length and settle window, the thresholds and the k6 metric values |
| `requests` | The response status counts, the admission refusals and the client transport failures |
| `windows` | The full, settle and measured windows, each with overall, per-class and per-operation traffic |
| `cache` | The hit and miss counts and the hit rate of the next-course report cache and the query-embedding cache |
| `core_seconds` | The total web, database and embedding core-seconds, their per-class and per-operation shares, and the unattributed part |
| `memory` | The web, database and embedding current and peak bytes from the sampler, and the web cgroup's `memory.stat` values and per-process resident sizes at the start and end |
| `memory_series` | The web cgroup's current bytes, `memory.stat` counters and per-process resident sizes every 5 seconds |
| `background` | The whole-host busy core-seconds less the measured core-seconds |
| `usage` | The disposable copy's request record line count before and after the run |

Each traffic group reports successful requests and 429 refusals separately. It holds the attempt count, the successful count and throughput, the successful latency p50, p95, p99 and maximum, the refusal count and throughput, the refusal latency and the refusal rate. Successful latency never mixes with refused latency.

The full window is the configured 300 seconds from the first request. The settle window is its first 30 seconds, and the measured window is the remaining 270 seconds. A request that completes during the 30-second drain after the level is outside every window. The summarizer fails a run whose k6 duration ends before the configured level.

The per-class and per-operation core-seconds are an apportionment, not a direct per-request counter. Each counter interval's CPU is shared equally among the requests that overlap it on the server clock, and the unattributed part holds the intervals with no overlapping request. The per-class value rests on the clock offset from the response `Date` header, whose resolution is one second. A class value therefore describes a run's share of the measured CPU, and a single request's share is not separable from another request that overlaps it.

The cache event log is written by a measurement wrapper that adds no product route and calls the wrapped cache method and logs the result. A stack without a named cache leaves it unpatched. The log names the cache, the event (hit, miss or put), the process and the time. It holds no query text and no course content. The wrapper writes one event per cache call from inside the measured web cgroup.

## Failure rules

The tooling fails with an explicit error when a machine value is missing, a stack or database host is not loopback, a cgroup parent is absent or not writable, a port is bound, a checkout or database guard fails, a supervisor descendant leaves the enforcing cgroup, a counter file is absent, the stack returns a status other than 200 for a matrix body, a cache case produces no cache event, a k6 run returns a status other than 200, 429 or a client transport failure, a k6 run reports a failed request that no client transport failure explains, a raw export holds no status-tagged request point, a level ends before its configured length, a level has no light request, or a saturated mixed level is below one heavy user. A workload body that the serving API rejects fails at its first request and is never adapted.
