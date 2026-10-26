# Admission control

Admission control applies cookie-scoped rate and concurrency limits, estimated-cost heavy budgets, and global heavy slots with a waiting queue and refusals to the nine fixed API POST paths.

## What admission control limits

With `ADMISSION_ENABLED` true, the [front router](/docs/reference/glossary.md#administration) decides for every POST to one of the nine fixed API paths whether the read is served, waits or is refused. A GET, a shell document, a static asset, an unknown path and a POST outside that set pass without a limit. A [worker process](/docs/reference/glossary.md#administration) applies no admission rule of its own.

Admission expresses a read's cost in core-seconds, estimated from the configured curve or the fixed search charge, and a prerequisite graph is charged the elapsed seconds recorded for an earlier build. The front router charges a heavy read that cost against its cookie's budget, so the limits bound the reads a cookie starts and the cost charged for them. The charge is fixed when the front router admits the read, and the read's CPU use after admission does not change it.

The example `config/admission.toml` sets `ADMISSION_ENABLED` to `true`, so a copy that uses the example file gives every read on the nine API paths an admission class, queues a heavy read that finds no free slot while its queue has room, and sets the `tce_anon` cookie on every response under `/api/`. A site with admission enabled needs at least two worker processes, because the global heavy slots cap at one fewer than `WEB_WORKERS` and at least one worker process carries no heavy work.

The front router takes the whole policy when it starts, so a changed key reaches a site when the web server restarts. Its admission counters, tickets and graph costs live in process memory, so a replacement front router starts with empty admission state. A dataset read uses the serving dataset, and the front router appends one request record for every HTTP request, refused or served.

## The three admission classes

A read's [admission class](/docs/reference/glossary.md#administration) follows its route and its request body, and a prerequisite graph also follows the cost recorded for an earlier build. Every browser follows the same rules.

| Class | Reads | What applies |
|---|---|---|
| Free | `POST /api/features` and `POST /api/course-summaries` | Nothing. A free read takes no token, enters no queue and is counted against no limit. |
| Light | `POST /api/search` without inactive courses, `POST /api/catalogue`, `POST /api/comparison`, `POST /api/study-structure`, a recommendation or next-courses read below its heavy basis, and a graph read that is unmeasured or below the heavy cutoff | One token from the cookie's light bucket and one place in its light concurrency. |
| Heavy | A search that includes inactive courses, a recommendation or next-courses read at or above its heavy basis, and a graph read with a recorded cost at or above `ADMISSION_GRAPH_HEAVY_SECONDS` | The cookie's heavy budget, then a global heavy slot through the queue. |

The heavy class follows the request shape alone, except for a prerequisite graph:

- `POST /api/search` is heavy unless the body sets `include_inactive` to false. An absent flag reads inactive courses, and that is the request model's default, so a search without the flag is heavy.
- A recommendation or a next-courses read is heavy from its heavy basis size upward. The read takes the active-only scope unless the body sets `active_only` to false, and only an explicit false selects the scope that includes inactive courses.
- `POST /api/prerequisites` is heavy only when an earlier build with the same cache field cost at least `ADMISSION_GRAPH_HEAVY_SECONDS`. A graph's first read is light, and a following read of the same field at or above the cutoff is heavy.

The graph cache field holds the target string the request sends and the three toggles. An official code and the canonical identity of the same course therefore hold separate entries, and requests that share a target string and flags share the recorded cost whatever their course sets.

A build is recorded when the request's target string is the root's canonical identity in the report or an exact official code of the root course. Each of those spellings is its own cache field, and each is measured on its own. A request that sends any other spelling of the course is served and its graph resolved, and its field holds no recorded cost, so every read of that field is light. The browser sends the canonical identity its course data holds, so its builds are recorded.

A recorded cost belongs to the serving dataset identity, and a build recorded under another identity clears the cache.

The basis size of a recommendation or next-courses read is the number of distinct nonblank identifier strings in the basis the read uses. A `selected` basis uses the selected courses, or the completed courses when the selected list is empty, and every other basis uses the completed courses. A body that is not a JSON object takes the request defaults, so an unparseable search body is priced as a search that includes inactive courses.

The example sets both recommendation cutoffs to five courses, the active-only next-courses cutoff to 63 courses and the inactive one to 26, the graph cutoff to 1.0 second, and the fixed cost of a search that includes inactive courses to 2.5 core-seconds. The curve that turns a basis size into a heavy read's estimated cost is on [Web server](/docs/backend/interfaces/web-server.md#admission-control).

The diagram follows one API request through its class, its checks, its placement and its record.

![One API request takes the free, light or heavy class. A free read passes straight to a worker process, a light read takes the light limits, and a heavy read takes the cookie's heavy budget and then a global slot from a first-in-first-out queue. A failed check answers 429, an admitted heavy read runs on a worker process that carries no other heavy read, and every HTTP request ends in one request record.](/docs/diagrams/admission-control.svg)

A free read passes to a worker process without a check. A light read takes the light limits, and a heavy read takes the cookie's heavy budget and then a global slot from the queue. A read that fails a check answers 429 without reaching a worker process, an admitted heavy read is placed on a worker process that carries no other heavy read, and the front router appends one request record for every HTTP request.

## The anonymous cookie

With admission enabled, one anonymous cookie identifies a browser. The front router sets `tce_anon` to 32 lowercase hexadecimal characters on every response it sends for a path under `/api/`, with `Max-Age` of `ADMISSION_COOKIE_MAX_AGE_SECONDS` (2592000 seconds, 30 days, in the example), `Path=/`, `HttpOnly`, `Secure` and `SameSite=Lax`. A refused read carries the same header as a served one.

A request whose cookie is absent or malformed receives a freshly minted value, and the front router limits that value like any other. The limits follow the cookie, so a client that presents a fresh cookie with every request starts each budget full, while the shared heavy slots and the queue cap the heavy reads the site runs and holds at once.

A cookie's light and heavy counters become eligible for removal once the identity has been idle for `ADMISSION_IDENTITY_TTL_SECONDS` (3600 seconds in the example) and holds no light read, heavy ticket or place in the queue. The front router sweeps once per TTL interval, so an idle identity can last past the configured time until the next sweep.

## The light limits

One cookie holds a bucket of `ADMISSION_LIGHT_BURST` tokens (20 in the example) and refills it at `ADMISSION_LIGHT_OPERATIONS_PER_MINUTE` (120 operations a minute at the headroom line in the example). Every light read takes one token. The burst is the bucket's capacity and holds its configured value in every regime.

The same cookie may run `ADMISSION_LIGHT_CONCURRENCY` light reads at once (eight at the headroom line in the example). The refill rate and the concurrency scale by one load factor that is one at the headroom line and `ADMISSION_LIGHT_LOAD_FLOOR` at saturation (0.25 in the example), and the concurrency is floored at one. At saturation the example therefore serves 30 light operations a minute and two at once.

A light read that finds the cookie's concurrency in use or its balance below one token answers 429.

## The heavy budget

One cookie holds a heavy bucket whose capacity is the current budget: `ADMISSION_HEAVY_BUDGET_CORE_SECONDS` at the headroom line (120 core-seconds in the example) and `ADMISSION_HEAVY_BUDGET_SATURATED_CORE_SECONDS` at saturation (40 in the example). Between the two lines the budget falls linearly. The bucket refills over `ADMISSION_WINDOW_SECONDS` (60 seconds in the example) at the budget divided by the window. The measured effect of that saturated budget on heavy completions is recorded in [Serving load and admission limits](/docs/experiments/runtime-storage-and-serving/serving-load-and-limits.md#the-saturated-budget-at-40-core-seconds).

A heavy read is charged its cost. A read whose cost is above the budget is charged the whole budget, so it passes while the bucket is full and fails once the balance has fallen below the budget. A read whose charge the balance cannot cover answers 429 at once. A read that is refused at the queue cap gets its charge back.

## The load score

The front router combines three terms into one load score over a window of `ADMISSION_LOAD_WINDOW_SECONDS` seconds (60 in the example): the whole host's CPU utilisation, the light reads admitted in the window and the heavy reads admitted or running in it. `ADMISSION_SCORE_CPU_WEIGHT`, `ADMISSION_SCORE_LIGHT_WEIGHT` and `ADMISSION_SCORE_HEAVY_WEIGHT` set the three weights (1.0, 0.012 and 0.004 in the example). The weights and the fitted score behind them are recorded in [Serving load and admission limits](/docs/experiments/runtime-storage-and-serving/serving-load-and-limits.md#the-fitted-score).

The CPU utilisation is the host's busy CPU core-seconds over the window divided by the window length and the host's core count. It covers every process on the host, including work outside this site. The front router samples the host CPU once a second, and every admission reads the values the last sample stored.

A light admission and a heavy start count for one window. A heavy read whose start leaves the window while it runs counts once until it ends. A queued read, a refused read and a read cancelled before it starts count nothing.

A sample that cannot read the host CPU logs one error and treats the site as unloaded. The CPU utilisation, the score, the counts and the regime fall to their unloaded values. The front router holds the activity timestamps, so the next good sample counts the activity already admitted and stores no outage interval.

## The load regimes

The front router derives one load position from the score and a saturation latch. A score at or above `ADMISSION_SCORE_SATURATION` sets the latch, and a latched site is saturated until the score falls below `ADMISSION_SCORE_RELEASE`, so a score below the saturation line can be saturated. A score below the release line clears the latch, and the site then takes the regime the score names.

A score at or below `ADMISSION_SCORE_HEADROOM` is headroom, and a score above it and below the saturation line is middle unless the latch holds the site at saturation.

While the site is saturated, every limit reads a load position of 1. Otherwise the position is 0 at or below the headroom line and the score's own position between the two lines. The light limits and the heavy budget move with that position. The table gives the regimes and the bounds the example configuration produces.

| Regime | Score | Light rate and concurrency | Heavy budget | Heavy slots | Queue cap |
|---|---|---|---|---|---|
| Headroom | at or below 0.60 | 120 a minute and 8 at once | 120 core-seconds | 3 (`ADMISSION_HEAVY_SLOTS`, capped at one fewer than `WEB_WORKERS`) | 64 waiting reads |
| Middle | above 0.60 and below 1.05, unless the latch holds | falls linearly | falls linearly from 120 to 40 core-seconds | falls from three to two | 32 waiting reads |
| Saturated | at or above 1.05, then held until the score falls below 0.90 | `ADMISSION_LIGHT_LOAD_FLOOR` of the headroom values, 30 a minute and 2 at once | 40 core-seconds | one | 16 waiting reads |

The example sets `ADMISSION_SCORE_HEADROOM` to 0.60, `ADMISSION_SCORE_SATURATION` to 1.05, `ADMISSION_SCORE_RELEASE` to 0.90 and `ADMISSION_LIGHT_LOAD_FLOOR` to 0.25.

## The heavy slots and the queue

The global heavy slots are `ADMISSION_HEAVY_SLOTS` at the headroom line and fall to one at saturation. The count is capped at one fewer than `WEB_WORKERS` and floored at one, so the example's four worker processes cap the count at three: three slots while the load position is below one half, two from one half up to saturation, and one at saturation. An admitted heavy read holds its slot until its response body ends.

A heavy read that finds no free slot joins a first-in-first-out queue and waits without a time limit. A read joins the queue while it holds fewer waiting reads than the regime's cap, which is `ADMISSION_HEAVY_QUEUE_HEADROOM_LIMIT` at headroom, `ADMISSION_HEAVY_QUEUE_MIDDLE_LIMIT` in the middle regime and `ADMISSION_HEAVY_QUEUE_SATURATED_LIMIT` at saturation. A waiting read holds its place when the cap drops, and a read that finds the queue at its cap answers 429 at once.

## Placement on a worker process

The front router places an admitted heavy read on a worker process that carries no other heavy read, and it picks the least busy such process, with the lowest index on a tie. A light read goes to the least busy worker process, which may carry a heavy read.

A read holds its worker process until its response body ends. The router opens one connection per forwarded read and reuses none. A failed connection to a worker process ends the request with status 500, and the read is not retried or moved to another process. The measured distribution of that placement is recorded in [Serving cost and routing](/docs/experiments/runtime-storage-and-serving/serving-cost-and-routing.md).

## Refusals

| Refusal | When it happens |
|---|---|
| Light concurrency | The cookie already runs the current concurrency of light reads. |
| Light balance | The cookie's light balance is below one token. |
| Heavy balance | The charge is more than the cookie's heavy balance. |
| Queue cap | The queue already holds the current cap of waiting heavy reads. |

Every refusal is status 429 with the body `{"detail": "Too much traffic"}` and `Retry-After` set to `ADMISSION_RETRY_AFTER_SECONDS` (5 seconds in the example). The response carries the anonymous cookie. A refused read reaches no worker process and counts nothing in the load score.

## The usage record of a refused read

The front router appends one [request record](/docs/backend/interfaces/web-server.md#the-request-usage-record) for every HTTP request it answers, so a refusal adds a record with status 429 and the read's fixed route label. The record holds the start hour, the route label, the status and the duration, and no cookie, identity, body or query. The [usage report](/docs/backend/interfaces/command-line.md#the-request-usage-report) counts those records and gives each route's request count and mean duration, so a refusal raises its route's count and mean and its 429 appears in the record alone.

## Settings that move the bounds

The table gives the value the example configuration sets for each key, and every admission key lives in `config/admission.toml`.

| Setting | Bound | Example |
|---|---|---|
| `ADMISSION_ENABLED` | Whether the front router limits reads at all. | `true` |
| `ADMISSION_LIGHT_OPERATIONS_PER_MINUTE` | The refill rate of one cookie's light bucket at the headroom line. | 120 |
| `ADMISSION_LIGHT_BURST` | The light tokens one cookie's bucket holds. | 20 |
| `ADMISSION_LIGHT_CONCURRENCY` | The light reads one cookie runs at once at the headroom line. | 8 |
| `ADMISSION_LIGHT_LOAD_FLOOR` | The share of the headroom light limits that applies at saturation. | 0.25 |
| `ADMISSION_HEAVY_BUDGET_CORE_SECONDS` | One cookie's heavy budget for a window at the headroom line. | 120 |
| `ADMISSION_HEAVY_BUDGET_SATURATED_CORE_SECONDS` | The same budget at saturation. | 40 |
| `ADMISSION_WINDOW_SECONDS` | The window one heavy budget refills over. | 60 |
| `ADMISSION_HEAVY_SLOTS` | The global heavy slots at the headroom line, before the cap at one fewer than `WEB_WORKERS`. | 3 |
| `ADMISSION_HEAVY_QUEUE_HEADROOM_LIMIT` | The waiting heavy reads the queue admits at the headroom line. | 64 |
| `ADMISSION_HEAVY_QUEUE_MIDDLE_LIMIT` | The waiting heavy reads the queue admits in the middle regime. | 32 |
| `ADMISSION_HEAVY_QUEUE_SATURATED_LIMIT` | The waiting heavy reads the queue admits at saturation. | 16 |
| `ADMISSION_SCORE_HEADROOM` | The score at or below which the site is in headroom. | 0.60 |
| `ADMISSION_SCORE_SATURATION` | The score at or above which the site is saturated. | 1.05 |
| `ADMISSION_SCORE_RELEASE` | The score below which a saturated site leaves saturation. | 0.90 |
| `ADMISSION_LOAD_WINDOW_SECONDS` | The window of CPU samples and admitted activity the score measures. | 60 |
| `ADMISSION_SCORE_CPU_WEIGHT`, `ADMISSION_SCORE_LIGHT_WEIGHT`, `ADMISSION_SCORE_HEAVY_WEIGHT` | The three weights of the load score. | 1.0, 0.012, 0.004 |
| `ADMISSION_GRAPH_HEAVY_SECONDS` | The measured cost from which a graph read is heavy. | 1.0 |
| `ADMISSION_SEARCH_INACTIVE_COST_CORE_SECONDS` | The fixed cost of a search that includes inactive courses. | 2.5 |
| `ADMISSION_RECOMMENDATION_ACTIVE_HEAVY_BASIS`, `ADMISSION_RECOMMENDATION_INACTIVE_HEAVY_BASIS` | The basis size from which a recommendation is heavy in each scope. | 5, 5 |
| `ADMISSION_NEXT_COURSES_ACTIVE_HEAVY_BASIS`, `ADMISSION_NEXT_COURSES_INACTIVE_HEAVY_BASIS` | The basis size from which a next-courses read is heavy in each scope. | 63, 26 |
| `ADMISSION_IDENTITY_TTL_SECONDS` | The idle time after which a cookie's counters become eligible for removal. | 3600 |
| `ADMISSION_COOKIE_MAX_AGE_SECONDS` | The cookie's lifetime in the browser. | 2592000 |
| `ADMISSION_RETRY_AFTER_SECONDS` | The delay a refusal states in `Retry-After`. | 5 |

`WEB_WORKERS` in `config/web.toml` caps the heavy slots, and a site with admission enabled needs at least two worker processes. [Configuration](/docs/backend/configuration.md#subsystem-keys) lists every key row and its constraints.
